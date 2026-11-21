"""One live run of a strategy: check the day and the data, diff targets, push, and log the run.

A strategy workflow supplies a ``load`` callable that refreshes its data and returns the full
target-weight table; this module never imports strategy code. ``run_live`` is idempotent per
trade date: the signal ledger prevents duplicate pushes and the run log records whether the
day is finished, so a scheduler may call it again after a crash, a sleep, or a retry.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .contracts import DeliveryResult, Signal, TargetSnapshot, build_signal
from .ledger import SignalLedger, validate_strategy_id
from .notify import channel_name, format_signal, load_notify_urls, send_notifications
from .sizing import SizedTarget, size_targets

# Run statuses that finish a trade date; the others are retried by the next scheduled run.
DONE_STATUSES = frozenset({"sent", "unchanged", "already_sent", "not_trading_day"})
RETRY_STATUSES = frozenset({"stale", "partial", "failed"})
EXIT_CODES = {
    "stale": 3,
    "partial": 4,
    "failed": 4,
    "error": 1,
    "test_partial": 4,
    "test_failed": 4,
}
# Trade dates kept in the run log; older ones are dropped oldest first.
MAX_RUN_DAYS = 90


class NoChannelsError(RuntimeError):
    """``write`` was requested but no IM webhook is configured."""


@dataclass(frozen=True)
class Delivery:
    """A signal, its message, and what happened when it was (or would be) sent."""

    signal: Signal
    title: str
    body: str
    sized: dict[str, SizedTarget] | None
    channels: list[str]
    status: str
    results: list[DeliveryResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def deliver_signal(
    snapshot: TargetSnapshot,
    ledger: SignalLedger,
    *,
    write: bool,
    urls: Sequence[str] | None = None,
    capital: float | None = None,
    multipliers: Mapping[str, float] | None = None,
    lot_size: int = 100,
    test: bool = False,
) -> Delivery:
    """Diff ``snapshot`` against the ledger base and, with ``write``, push it to every channel.

    Status is ``preview`` (no ``write``), ``unchanged``, ``sent``, ``already_sent``, ``partial``,
    or ``failed``. Channels that already received the same signal id are skipped, so a rerun
    after a partial delivery only retries the failed channels.

    A ``test`` delivery sends the whole target as a marked test message to every channel and
    never reads or writes the ledger, so it can run at any time without touching live state.
    """
    urls = load_notify_urls() if urls is None else list(urls)
    signal = build_signal(snapshot, {} if test else ledger.base_weights())
    sized = None
    if capital is not None:
        targets = {change.symbol: change.target for change in signal.changes}
        sized = {
            item.symbol: item
            for item in size_targets(
                targets,
                capital,
                signal.prices,
                multipliers=dict(multipliers or {}),
                lot_size=lot_size,
            )
        }
    title, body = format_signal(signal, sized, test=test)
    channels = [channel_name(url) for url in urls]
    delivery = {
        "signal": signal,
        "title": title,
        "body": body,
        "sized": sized,
        "channels": channels,
    }
    if signal.is_empty:
        return Delivery(**delivery, status="unchanged")
    if not write:
        return Delivery(**delivery, status="preview")
    if not urls:
        raise NoChannelsError("No IM webhook is configured")
    if test:
        results = send_notifications(title, body, urls)
        oks = [item.ok for item in results]
        status = "sent" if all(oks) else ("partial" if any(oks) else "failed")
        return Delivery(**delivery, status=status, results=results)
    done = ledger.delivered_channels(signal.signal_id)
    pending = [url for url in urls if channel_name(url) not in done]
    results = send_notifications(title, body, pending) if pending else []
    complete = ledger.record(signal, results, channels)
    if not pending:
        status = "already_sent"
    elif complete:
        status = "sent"
    else:
        status = "partial" if any(item.ok for item in results) else "failed"
    skipped = [name for name in channels if name in done]
    return Delivery(**delivery, status=status, results=results, skipped=skipped)


class RunLog:
    """Per-trade-date run results under ``<data_root>/live/<strategy_id>/runs.json``."""

    def __init__(self, strategy_id: str, data_root: str | Path | None = None):
        from skills.store.workspace import resolve_workspace_paths

        self.strategy_id = validate_strategy_id(strategy_id)
        root = resolve_workspace_paths(data_root=data_root).data_root
        self.path = root / "live" / self.strategy_id / "runs.json"

    def _read(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "strategy_id": self.strategy_id, "runs": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, state: dict) -> None:
        runs = state["runs"]
        for stale in sorted(runs)[: max(0, len(runs) - MAX_RUN_DAYS)]:
            del runs[stale]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=".runs.", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def get(self, trade_date: date) -> dict | None:
        return self._read()["runs"].get(trade_date.isoformat())

    def is_done(self, trade_date: date) -> bool:
        entry = self.get(trade_date)
        return bool(entry and entry["status"] in DONE_STATUSES)

    def record(
        self, trade_date: date, status: str, detail: str = "", signal_id: str | None = None
    ) -> None:
        state = self._read()
        entry = state["runs"].setdefault(trade_date.isoformat(), {"attempts": 0, "alerts": []})
        entry.update(
            status=status,
            detail=detail,
            signal_id=signal_id,
            at=datetime.now().isoformat(timespec="seconds"),
            attempts=entry["attempts"] + 1,
        )
        self._write(state)

    def claim_alert(self, trade_date: date, kind: str) -> bool:
        """Mark an alert of ``kind`` as sent for the day; False when it already was."""
        state = self._read()
        entry = state["runs"].setdefault(trade_date.isoformat(), {"attempts": 0, "alerts": []})
        entry.setdefault("status", "pending")
        if kind in entry["alerts"]:
            return False
        entry["alerts"].append(kind)
        self._write(state)
        return True


def send_alert(
    strategy_id: str,
    trade_date: date,
    kind: str,
    message: str,
    *,
    urls: Sequence[str] | None = None,
) -> list[DeliveryResult]:
    """Push an alert to every channel; the title always contains ``QuantSpace``."""
    urls = load_notify_urls() if urls is None else list(urls)
    if not urls:
        return []
    title = f"QuantSpace 告警 | {strategy_id}"
    body = f"交易日：{trade_date.isoformat()}\n类型：{kind}\n{message}"
    return send_notifications(title, body, urls)


@dataclass(frozen=True)
class LiveInputs:
    """What a strategy workflow hands to ``run_live`` for one trade date."""

    weights: pd.DataFrame
    prices: pd.DataFrame | None = None
    multipliers: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RunOutcome:
    strategy_id: str
    trade_date: str
    status: str
    detail: str = ""
    delivery: Delivery | None = None
    alerts: list[DeliveryResult] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES.get(self.status, 0)


_ALERT_TEXT = {
    "stale": "到最后一次计划运行时，数据仍未更新到当天，今天没有生成信号。",
    "error": "运行出错，今天的信号没有生成。",
    "failed": "信号没有送达任何 IM 通道。",
    "partial": "信号只送达了部分 IM 通道。",
}


def run_live(
    strategy_id: str,
    load: Callable[[], LiveInputs],
    *,
    trade_date: date,
    is_trading_day: bool,
    write: bool = False,
    final: bool = False,
    capital: float | None = None,
    lot_size: int = 100,
    data_root: str | Path | None = None,
    urls: Sequence[str] | None = None,
    test: bool = False,
) -> RunOutcome:
    """Run one strategy for ``trade_date`` and report what happened.

    Statuses: ``not_trading_day``; ``done`` when the day already finished; ``stale`` when the
    weights do not reach ``trade_date`` yet; ``error`` when loading or sizing raised; otherwise
    the delivery status. With ``write`` the run is logged and alerts go out for errors and, on
    the ``final`` attempt of the day, for stale data or incomplete delivery, once per kind.

    ``test`` checks the IM path at any hour: it skips the trading-day and freshness checks,
    uses the last weights row at or before ``trade_date``, and with ``write`` sends the whole
    target as a marked test message. It never touches the ledger or the run log and never
    alerts; its statuses are ``preview``, ``test_sent``, ``test_partial``, ``test_failed``,
    or ``error``.
    """
    if test:
        return _run_test(strategy_id, load, trade_date, write, capital, lot_size, data_root, urls)
    runs = RunLog(strategy_id, data_root)
    alerts: list[DeliveryResult] = []

    def finish(status: str, detail: str = "", delivery: Delivery | None = None) -> RunOutcome:
        if write:
            signal_id = delivery.signal.signal_id if delivery else None
            runs.record(trade_date, status, detail, signal_id)
            alert = status == "error" or (final and status in RETRY_STATUSES)
            if alert and runs.claim_alert(trade_date, status):
                text = _ALERT_TEXT[status] + (f"\n{detail}" if detail else "")
                alerts.extend(send_alert(strategy_id, trade_date, status, text, urls=urls))
        return RunOutcome(strategy_id, trade_date.isoformat(), status, detail, delivery, alerts)

    if not is_trading_day:
        return finish("not_trading_day")
    if write and runs.is_done(trade_date):
        previous = runs.get(trade_date) or {}
        return RunOutcome(strategy_id, trade_date.isoformat(), "done", previous.get("status", ""))
    try:
        inputs = load()
        weights = inputs.weights.sort_index()
        if weights.empty:
            raise ValueError("the strategy returned an empty weights table")
        last = pd.Timestamp(weights.index[-1]).normalize()
        day = pd.Timestamp(trade_date)
        if last < day:
            return finish(
                "stale",
                f"最新权重日期 {last.date().isoformat()}，早于交易日 {trade_date.isoformat()}",
            )
        if last > day:
            raise ValueError(f"weights reach {last.date()} after the trade date {trade_date}")
        snapshot = TargetSnapshot.from_frames(weights, strategy_id, prices=inputs.prices)
        delivery = deliver_signal(
            snapshot,
            SignalLedger(strategy_id, data_root),
            write=write,
            urls=urls,
            capital=capital,
            multipliers=inputs.multipliers,
            lot_size=lot_size,
        )
    except Exception as exc:  # noqa: BLE001 - any failure must be logged and alerted
        return finish("error", f"{type(exc).__name__}: {exc}")
    return finish(delivery.status, delivery=delivery)


def _run_test(strategy_id, load, trade_date, write, capital, lot_size, data_root, urls):
    label = trade_date.isoformat()
    try:
        inputs = load()
        snapshot = TargetSnapshot.from_frames(
            inputs.weights, strategy_id, as_of=trade_date, prices=inputs.prices
        )
        delivery = deliver_signal(
            snapshot,
            SignalLedger(strategy_id, data_root),
            write=write,
            urls=urls,
            capital=capital,
            multipliers=inputs.multipliers,
            lot_size=lot_size,
            test=True,
        )
    except Exception as exc:  # noqa: BLE001 - reported, never alerted
        return RunOutcome(strategy_id, label, "error", f"{type(exc).__name__}: {exc}")
    status = delivery.status if delivery.status == "preview" else f"test_{delivery.status}"
    return RunOutcome(strategy_id, label, status, delivery=delivery)


__all__ = [
    "DONE_STATUSES",
    "Delivery",
    "LiveInputs",
    "NoChannelsError",
    "RunLog",
    "RunOutcome",
    "deliver_signal",
    "run_live",
    "send_alert",
]
