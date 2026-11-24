"""Per-strategy delivery ledger: the last fully delivered target and per-channel results."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from skills.store.files import replace_file

from .contracts import DeliveryResult, Signal

_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
# Names Windows reserves for devices, with or without an extension.
_WINDOWS_DEVICE = re.compile(r"(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?", re.IGNORECASE)
# Signals kept in the ledger; older entries are dropped oldest first.
MAX_SIGNALS = 50


def validate_strategy_id(strategy_id: str) -> str:
    """Strategy ids name a ledger folder, so they must be one safe path segment on every OS."""
    if (
        not isinstance(strategy_id, str)
        or not _SEGMENT.fullmatch(strategy_id)
        or ".." in strategy_id
        or strategy_id.endswith(".")
        or _WINDOWS_DEVICE.fullmatch(strategy_id)
    ):
        raise ValueError(
            f"Invalid strategy id {strategy_id!r}: use letters, digits, '_', '-', or '.'"
        )
    return strategy_id


def write_json_atomic(path: Path, payload: Any, *, default: Callable | None = None) -> None:
    """Write ``payload`` as UTF-8 JSON through a temporary file, so readers never see half."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False, default=default)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text + "\n")
        replace_file(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class SignalLedger:
    """State under ``<data_root>/live/<strategy_id>/ledger.json``.

    ``base`` is the last target delivered to every configured channel; new signals are diffed
    against it. A signal that reached only some channels keeps the old base, so a rerun builds
    the same signal id and sends it only to the channels that have not received it.
    """

    def __init__(self, strategy_id: str, data_root: str | Path | None = None):
        from skills.store.workspace import resolve_workspace_paths

        self.strategy_id = validate_strategy_id(strategy_id)
        root = resolve_workspace_paths(data_root=data_root).data_root
        self.path = root / "live" / self.strategy_id / "ledger.json"

    def _read(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "strategy_id": self.strategy_id, "base": None, "signals": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, state: dict) -> None:
        write_json_atomic(self.path, state)

    def base_unit(self) -> str | None:
        """Unit of the delivered base (``percent`` for ledgers older than units), or None."""
        base = self._read()["base"]
        return base.get("unit", "percent") if base else None

    def base_weights(self, unit: str | None = None) -> dict[str, float]:
        """The delivered base; empty when there is none or, given ``unit``, it is in another
        unit (the strategy changed units, so its baseline starts over)."""
        base = self._read()["base"]
        if not base or (unit is not None and base.get("unit", "percent") != unit):
            return {}
        return dict(base["weights"])

    def delivered_channels(self, signal_id: str) -> set[str]:
        entry = self._read()["signals"].get(signal_id, {})
        return {name for name, item in entry.get("deliveries", {}).items() if item.get("ok")}

    def record(
        self, signal: Signal, results: Iterable[DeliveryResult], channels: Iterable[str]
    ) -> bool:
        """Store delivery results; returns whether every channel has now received the signal."""
        state = self._read()
        now = datetime.now().isoformat(timespec="seconds")
        entry = state["signals"].setdefault(
            signal.signal_id,
            {"as_of": signal.as_of, "target": signal.target, "deliveries": {}},
        )
        for result in results:
            previous = entry["deliveries"].get(result.channel, {})
            if previous.get("ok"):
                continue
            entry["deliveries"][result.channel] = {
                "ok": result.ok,
                "detail": result.detail,
                "at": now,
            }
        delivered = {name for name, item in entry["deliveries"].items() if item.get("ok")}
        complete = set(channels) <= delivered
        if complete:
            entry["complete"] = True
            state["base"] = {
                "signal_id": signal.signal_id,
                "as_of": signal.as_of,
                "weights": signal.target,
            }
            if signal.unit != "percent":
                state["base"]["unit"] = signal.unit
        signals = state["signals"]
        for stale in list(signals)[: max(0, len(signals) - MAX_SIGNALS)]:
            del signals[stale]
        self._write(state)
        return complete


__all__ = [
    "MAX_SIGNALS",
    "SignalLedger",
    "validate_strategy_id",
    "write_json_atomic",
]
