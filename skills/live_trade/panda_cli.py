"""Locate and call the CLI that ships with the PandaAI live-trading client.

The client bundles ``panda-live-trading`` and keeps CTP credentials itself; QuantSpace only
calls that CLI and never reads the client's files, database, or internal HTTP API.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import is_futures_symbol

CLI_ENV = "PANDA_LIVE_CLI"
CLI_NAME = "panda-live-trading"
# The macOS client's bundled CLI: its launcher runs on the client's own runtime
# (``ELECTRON_RUN_AS_NODE=1``) and prefers a newer official npm install when there is one.
CLIENT_APP = Path("/Applications/PandaAI.app")
CLIENT_RUNTIME = CLIENT_APP / "Contents/MacOS/PandaAI"
BUNDLED_CLI = CLIENT_APP / "Contents/Resources/cli/bundled-launcher.mjs"
# The Windows client runs the same way from its install folder: ``PandaAI.exe`` and, under
# ``resources\cli``, the launcher, or in clients without one (seen 2026-11-24, CLI 0.1.11)
# the CLI itself. The folder is the one the installer registered, else a default one.
WINDOWS_RUNTIME = "PandaAI.exe"
WINDOWS_ENTRIES = ("resources/cli/bundled-launcher.mjs", "resources/cli/panda-live-trading.mjs")
WINDOWS_DEFAULT_DIRS = (("LOCALAPPDATA", "Programs/PandaAI"), ("ProgramFiles", "PandaAI"))
_UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
# Oldest CLI whose commands and JSON fields this Skill was checked against.
MIN_CLI_VERSION = (0, 1, 11)
# SimNow accounts use broker 9999; only they may ever run without a human confirming.
SIMNOW_BROKER_ID = "9999"
# The CLI records these in its audit trail for every call.
ACTOR_ID = "quantspace-live-trade"


# What the CLI answers when the client is closed (it talks to the running client).
CLIENT_UNREACHABLE = "fetch failed"
CLIENT_DOWN_HINT = "（连不上 PandaAI 客户端：先打开客户端并登录，再重试）"


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
        "ELECTRON_RUN_AS_NODE": "1",
        "PANDA_LIVE_ACTOR": "AI",
        "PANDA_LIVE_ACTOR_ID": ACTOR_ID,
    }


def _command_for(path: str | Path) -> list[str] | None:
    path = Path(path).expanduser()
    if path.suffix in (".mjs", ".js"):
        node = shutil.which("node")
        return [node, str(path)] if node and path.is_file() else None
    return [str(path)] if path.is_file() else None


def _registered_windows_dirs() -> list[Path]:
    """Install folders the PandaAI installer registered in the Windows uninstall list."""
    import winreg

    def value(entry, name: str) -> str:
        try:
            return str(winreg.QueryValueEx(entry, name)[0]).strip()
        except OSError:
            return ""

    keys = [
        (winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY),
        (winreg.HKEY_LOCAL_MACHINE, _UNINSTALL_KEY),
        (winreg.HKEY_LOCAL_MACHINE, _UNINSTALL_KEY.replace("Software", r"Software\WOW6432Node")),
    ]
    found = []
    for hive, path in keys:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        with root:
            for index in itertools.count():
                try:
                    name = winreg.EnumKey(root, index)
                except OSError:
                    break
                try:
                    entry = winreg.OpenKey(root, name)
                except OSError:
                    continue
                with entry:
                    if value(entry, "DisplayName").lower() != "pandaai":
                        continue
                    location = value(entry, "InstallLocation").strip('"')
                    # ``DisplayIcon`` is "<folder>\PandaAI.exe" or "<folder>\PandaAI.exe",0.
                    icon = value(entry, "DisplayIcon").split(",")[0].strip('"')
                    if location or icon:
                        found.append(Path(location) if location else Path(icon).parent)
    return found


def client_bundles(
    platform: str | None = None, environ: Mapping[str, str] | None = None
) -> list[tuple[Path, Path]]:
    """``(runtime, CLI entry)`` pairs where the PandaAI client may keep its CLI, best first."""
    if (platform or sys.platform) != "win32":
        return [(CLIENT_RUNTIME, BUNDLED_CLI)]
    environ = os.environ if environ is None else environ
    folders = _registered_windows_dirs()
    folders += [
        Path(environ[name]) / sub for name, sub in WINDOWS_DEFAULT_DIRS if environ.get(name)
    ]
    return [
        (folder / WINDOWS_RUNTIME, folder / entry)
        for folder in dict.fromkeys(folders)
        for entry in WINDOWS_ENTRIES
    ]


def discover_cli() -> list[str] | None:
    """Command prefix for the CLI: ``PANDA_LIVE_CLI``, the client bundle, then ``PATH``."""
    configured = os.environ.get(CLI_ENV)
    if configured:
        return _command_for(configured)
    for runtime, entry in client_bundles():
        if runtime.is_file() and entry.is_file():
            return [str(runtime), str(entry)]
    found = shutil.which(CLI_NAME)
    return [found] if found else None


def cli_version(command: list[str], timeout: float = 15.0) -> str:
    """Run ``--version``; raises ``subprocess.CalledProcessError`` or ``TimeoutError``."""
    try:
        completed = subprocess.run(
            [*command, "--version"],
            capture_output=True,
            # The CLI prints UTF-8 everywhere; Windows would otherwise decode it as GBK.
            encoding="utf-8",
            errors="replace",
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


def _json(text: str | None) -> Any:
    try:
        return json.loads(text) if text and text.strip() else None
    except ValueError:
        return None


def run_cli(
    command: list[str],
    *args: str,
    timeout: float = 30.0,
    env: Mapping[str, str] | None = None,
) -> Any:
    """Run one CLI command and return its ``data``.

    ``env`` adds variables such as ``PANDA_LIVE_TRACE_ID`` for the client's audit trail.
    Raises ``PandaCliError`` when the CLI answers ``ok: false`` or prints no JSON, and
    ``TimeoutError`` when it does not finish in time.
    """
    try:
        completed = subprocess.run(
            [*command, *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env={**_cli_env(), **(env or {})},
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"{CLI_NAME} {' '.join(args)} timed out") from exc
    # A failed command prints its ``ok: false`` envelope on stderr and exits 1.
    payload = _json(completed.stdout)
    if payload is None:
        payload = _json(completed.stderr)
    if payload is None:
        detail = (completed.stderr or completed.stdout).strip()[:200]
        raise PandaCliError(
            f"{CLI_NAME} {args[0] if args else ''} printed no JSON "
            f"(exit {completed.returncode}): {detail}"
        )
    if not isinstance(payload, dict) or not payload.get("ok"):
        error = payload.get("error") if isinstance(payload, dict) else None
        error = error if isinstance(error, dict) else {}
        message = error.get("message") or f"{CLI_NAME} failed"
        if CLIENT_UNREACHABLE in message.lower():
            message += CLIENT_DOWN_HINT
        raise PandaCliError(message, error.get("code"))
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
    "CLIENT_RUNTIME",
    "CLI_ENV",
    "CLI_NAME",
    "MIN_CLI_VERSION",
    "SIMNOW_BROKER_ID",
    "PandaAccount",
    "PandaCliError",
    "capability_problems",
    "cli_version",
    "client_bundles",
    "discover_cli",
    "list_accounts",
    "require_actual_contract",
    "run_cli",
    "version_problem",
]
