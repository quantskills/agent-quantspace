"""Shared guards for the opt-in live checks: trading sessions, credentials, the client CLI."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

ZONE = ZoneInfo("Asia/Shanghai")
# Inside these windows the last finished 5-minute bar is at most a few minutes old.
EQUITY_WINDOWS = ((time(9, 36), time(11, 30)), (time(13, 6), time(15, 0)))
RB_WINDOWS = (
    (time(9, 6), time(10, 15)),
    (time(10, 36), time(11, 30)),
    (time(13, 36), time(15, 0)),
    (time(21, 6), time(23, 0)),
)
# Day sessions only: a daily run's cut-off is a bar of the trading day itself.
RB_DAY_WINDOWS = RB_WINDOWS[:3]
# From when the 14:50 bar has settled until midnight: a daily run of today works then (it
# trades before 15:00; Sina keeps today's 1-minute bars after the close).
AFTER_CUTOFF = ((time(14, 51), time(23, 59)),)


def now() -> datetime:
    return datetime.now(ZONE).replace(tzinfo=None, microsecond=0)


def require_session(windows, what: str) -> datetime:
    """The current time, or skip when it is outside ``windows`` on a weekday."""
    current = now()
    inside = current.weekday() < 5 and any(start <= current.time() <= end for start, end in windows)
    if not inside:
        pytest.skip(f"{what} is not in a trading session at {current:%a %H:%M}")
    return current


@pytest.fixture(scope="session")
def panda_client():
    """A PandaData client, or skip when the SDK or its credentials are missing."""
    try:
        from skills.ingest import PandaDataClient

        return PandaDataClient()
    except Exception as exc:  # noqa: BLE001 - any setup problem is a skip, not a failure
        pytest.skip(f"PandaData is not available: {type(exc).__name__}: {exc}")


@pytest.fixture(scope="session")
def panda_cli():
    """The PandaAI client CLI command, or skip when it is not installed."""
    from skills.live_trade.panda_cli import discover_cli

    command = discover_cli()
    if command is None:
        pytest.skip("PandaAI client CLI not found")
    return command
