"""Locate and call the CLI that ships with the PandaAI live-trading client.

The client bundles ``panda-live-trading`` and keeps CTP credentials itself; QuantSpace only
calls that CLI and never reads the client's files, database, or internal HTTP API.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import is_futures_symbol

CLI_ENV = "PANDA_LIVE_CLI"
CLI_NAME = "panda-live-trading"
# Where the macOS client installs its bundled CLI entry.
BUNDLED_CLI = Path("/Applications/PandaAI.app/Contents/Resources/cli/bin/panda-live-trading.mjs")
# Oldest CLI whose commands and JSON fields this Skill was checked against.
MIN_CLI_VERSION = (0, 1, 11)
# SimNow accounts use broker 9999; only they may ever run without a human confirming.
SIMNOW_BROKER_ID = "9999"
# The CLI records these in its audit trail for every call.
ACTOR_ID = "quantspace-live-trade"


class PandaCliError(RuntimeError):
    """The CLI answered ``ok: false`` or could not be run; ``code`` is the CLI's error code."""

    def __init__(self, message: str, code: Any = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PandaAccount:
    """One trading account as the client's ``accounts`` command reports it."""

    account_id: int
    code: str
    name: str
    broker_id: str
    company: str
    mode: str
    running_asset_units: int
    runtime_state_known: bool
    cli_eligible: bool
    unavailable_reason: str

    @property
    def is_simnow(self) -> bool:
        return self.broker_id == SIMNOW_BROKER_ID

    @classmethod
    def from_cli(cls, item: Mapping[str, Any]) -> PandaAccount:
        return cls(
            account_id=int(item["realAccountId"]),
            code=str(item.get("accountCode", "")),
            name=str(item.get("accountName", "")),
            broker_id=str(item.get("brokerId", "")),
            company=str(item.get("companyName", "")),
            mode=str(item.get("accountMode", "")),
            running_asset_units=int(item.get("runningAssetUnitCount") or 0),
            runtime_state_known=bool(item.get("cliRuntimeStateKnown")),
            cli_eligible=bool(item.get("cliEligible")),
            unavailable_reason=str(item.get("cliUnavailableReason") or ""),
        )


def _cli_env() -> dict[str, str]:
    return {
        **os.environ,
        "PANDA_LIVE_UPDATE_CHECK": "off",
        "PANDA_LIVE_ACTOR": "AI",
        "PANDA_LIVE_ACTOR_ID": ACTOR_ID,
    }


def _command_for(path: str | Path) -> list[str] | None:
    path = Path(path).expanduser()
    if path.suffix in (".mjs", ".js"):
        node = shutil.which("node")
        return [node, str(path)] if node and path.is_file() else None
    return [str(path)] if path.is_file() else None


def discover_cli() -> list[str] | None:
    """Command prefix for the CLI: ``PANDA_LIVE_CLI``, the client bundle, then ``PATH``."""
    configured = os.environ.get(CLI_ENV)
    if configured:
        return _command_for(configured)
    bundled = _command_for(BUNDLED_CLI)
    if bundled:
        return bundled
    found = shutil.which(CLI_NAME)
    return [found] if found else None


def cli_version(command: list[str], timeout: float = 15.0) -> str:
    """Run ``--version``; raises ``subprocess.CalledProcessError`` or ``TimeoutError``."""
    try:
        completed = subprocess.run(
            [*command, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
            env=_cli_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"{CLI_NAME} --version timed out") from exc
    return completed.stdout.strip()


def version_problem(version: str) -> str | None:
    """Why ``version`` is too old or unreadable, or ``None`` when it is supported."""
    try:
        found = tuple(int(part) for part in version.strip().split(".")[:3])
    except ValueError:
        return f"cannot read {CLI_NAME} version {version!r}"
    if found < MIN_CLI_VERSION:
        wanted = ".".join(map(str, MIN_CLI_VERSION))
        return f"{CLI_NAME} {version} is older than {wanted}; update the PandaAI client"
    return None


def run_cli(command: list[str], *args: str, timeout: float = 30.0) -> Any:
    """Run one CLI command and return its ``data``.

    Raises ``PandaCliError`` when the CLI answers ``ok: false`` or prints no JSON, and
    ``TimeoutError`` when it does not finish in time.
    """
    try:
        completed = subprocess.run(
            [*command, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_cli_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"{CLI_NAME} {' '.join(args)} timed out") from exc
    try:
        payload = json.loads(completed.stdout)
    except ValueError:
        detail = (completed.stderr or completed.stdout).strip()[:200]
        raise PandaCliError(
            f"{CLI_NAME} {args[0] if args else ''} printed no JSON "
            f"(exit {completed.returncode}): {detail}"
        ) from None
    if not isinstance(payload, dict) or not payload.get("ok"):
        error = payload.get("error") if isinstance(payload, dict) else None
        error = error if isinstance(error, dict) else {}
        raise PandaCliError(error.get("message") or f"{CLI_NAME} failed", error.get("code"))
    return payload.get("data")


def list_accounts(command: list[str]) -> list[PandaAccount]:
    """Accounts the client knows, with whether each may be used through the CLI."""
    return [PandaAccount.from_cli(item) for item in run_cli(command, "accounts") or []]


def capability_problems(capabilities: Mapping[str, Any]) -> list[str]:
    """Client features this Skill relies on that ``capabilities`` does not declare."""
    problems = []
    if not (capabilities.get("contract") or {}).get("supported"):
        problems.append("contract specs (multiplier, tick) are not supported")
    if capabilities.get("batchLimitTimeCondition") != "GFD":
        problems.append("batch plans do not freeze GFD limit orders")
    return problems


def require_actual_contract(symbol: str) -> str:
    """Return a futures symbol unchanged if the client can trade it, else raise ``ValueError``.

    The client CLI takes PandaData codes such as ``RB2701.SHF`` as they are. It matches
    orders and positions by actual contract, so a dominant-continuous ``RB_DOMINANT.SHF``
    has to be resolved to a delivery month first.
    """
    if not is_futures_symbol(symbol):
        raise ValueError(f"{symbol} is not a futures contract")
    if symbol.rpartition(".")[0].upper().endswith("_DOMINANT"):
        raise ValueError(f"{symbol} is a continuous symbol; resolve it to an actual contract")
    return symbol


__all__ = [
    "ACTOR_ID",
    "BUNDLED_CLI",
    "CLI_ENV",
    "CLI_NAME",
    "MIN_CLI_VERSION",
    "SIMNOW_BROKER_ID",
    "PandaAccount",
    "PandaCliError",
    "capability_problems",
    "cli_version",
    "discover_cli",
    "list_accounts",
    "require_actual_contract",
    "run_cli",
    "version_problem",
]
