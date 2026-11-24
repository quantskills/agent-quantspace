"""Opt-in live checks of live_trade against the real sources, during trading hours.

Run with ``uv run python -m pytest -m live -rs -q``. Each check skips outside its session
(A-share stocks and funds 09:36–11:30 and 13:06–15:00; rebar also 21:06–23:00; today's
14:50 daily run 14:51–15:00), without
PandaData credentials, or without the PandaAI client. Everything runs on a temporary data
root and only previews: nothing is pushed to IM, written to ``data/``, or ordered, except
the SimNow round trips, which run only when ``QS_LIVE_ORDERS_ACCOUNT`` names a SimNow
account: one hot-rolled coil contract is opened and closed by the order step alone and
once more through the daily path. Hot-rolled coil leaves a rebar strategy on the same
account alone. The contract is PandaData's hot-rolled coil dominant, or
``QS_LIVE_ORDERS_CONTRACT`` (such as ``HC2701.SHF``), which lets the client check and the
order step run without PandaData credentials.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from tests.live.conftest import (
    AFTER_CUTOFF,
    EQUITY_WINDOWS,
    RB_DAY_WINDOWS,
    RB_WINDOWS,
    require_session,
)

pytestmark = pytest.mark.live

ROOT = Path(__file__).resolve().parents[2]
# Sina posts equity bars within a minute; futures bars arrive in batches up to 3 minutes late.
MAX_AGE = {"stock": timedelta(minutes=7), "future": timedelta(minutes=10)}


def _dominant(client, product: str = "RB") -> str:
    from skills.live_trade.feeds import load_calendar, upcoming_trading_date

    day = upcoming_trading_date(datetime.now(), load_calendar(client, datetime.now().date()))
    stamp = day.strftime("%Y%m%d")
    table = client.get_future_dominant(stamp, stamp, underlying_symbol=[product])
    if table is None or table.empty:
        pytest.skip(f"PandaData has no {product} dominant contract for {day}")
    return str(table["symbol"].iloc[-1])


def _order_contract(request) -> str:
    """``QS_LIVE_ORDERS_CONTRACT``, else today's hot-rolled coil dominant from PandaData."""
    from skills.live_trade.execution import product_of
    from skills.live_trade.panda_cli import require_actual_contract

    contract = os.environ.get("QS_LIVE_ORDERS_CONTRACT", "").strip()
    if not contract:
        return _dominant(request.getfixturevalue("panda_client"), "HC")
    contract = require_actual_contract(contract)
    if product_of(contract) != "HC":
        pytest.fail(
            f"QS_LIVE_ORDERS_CONTRACT must be hot-rolled coil, such as HC2701.SHF: {contract}"
        )
    return contract


def _equal_weights(panel: pd.DataFrame) -> pd.DataFrame:
    close = panel["close"].unstack("symbol").sort_index()
    return close.notna().astype(float).div(close.shape[1])


def _due_bar(state, now: datetime) -> datetime:
    """The newest bar whose delay has passed and whose deadline has not."""
    ends = [datetime.fromisoformat(value) for value in state.bar_ends]
    due = [
        end
        for end in ends
        if end + timedelta(seconds=state.delay_seconds)
        <= now
        < end + timedelta(seconds=state.deadline_seconds)
    ]
    if not due:
        pytest.skip(f"no bar of {state.trading_date} is due at {now:%H:%M:%S}")
    return due[-1]


# --------------------------------------------------------------------------- Sina bars


@pytest.mark.parametrize("kind", ["stock", "fund", "future"])
def test_sina_bars_are_recent_and_finished(kind, panda_client):
    from skills.ingest.akshare_bars import fetch_intraday_bars

    windows = RB_WINDOWS if kind == "future" else EQUITY_WINDOWS
    now = require_session(windows, kind)
    symbol = {"stock": "000001.SZ", "fund": "510300.SH"}.get(kind) or _dominant(panda_client)

    result = fetch_intraday_bars([symbol], "5m", now=now)

    assert result.errors == {}, result.errors
    bars = result.bars
    assert not bars.empty and (bars["eob"] <= pd.Timestamp(result.as_of)).all()
    latest = pd.Timestamp(bars["eob"].max())
    age = pd.Timestamp(now) - latest
    assert age <= MAX_AGE["future" if kind == "future" else "stock"], (symbol, latest, now)
    assert (bars[["open", "high", "low", "close"]] > 0).all().all()
    assert (bars["high"] >= bars["low"]).all() and (bars["volume"] >= 0).all()


# --------------------------------------------------------------------------- minute feed


def _feed(spec, client, root):
    from skills.live_trade.feeds import MinuteFeed

    return MinuteFeed(spec, client, data_root=root)


def test_equity_minute_feed_refreshes_updates_and_previews_a_bar(tmp_path, panda_client):
    from skills.live_trade.minute import refresh_day, run_bar
    from skills.live_trade.spec import Instrument, LiveSpec

    now = require_session(EQUITY_WINDOWS, "A-share stocks and funds")
    spec = LiveSpec(
        strategy_id="live_check_equity",
        frequency="5m",
        instruments=(
            Instrument(symbol="000001.SZ", asset="stock"),
            Instrument(symbol="510300.SH", asset="fund"),
        ),
        warmup_bars=20,
    )
    feed = _feed(spec, panda_client, tmp_path)

    refreshed = refresh_day(spec, feed, _equal_weights, now=now, data_root=tmp_path)
    assert refreshed.status == "refreshed", refreshed.detail
    assert refreshed.trade_date == now.date().isoformat()
    state = feed.state()
    assert set(state.factors) == {"000001.SZ", "510300.SH"}
    assert all(value > 0 for value in state.factors.values())
    bar = _due_bar(state, now)

    outcome = run_bar(spec, feed, _equal_weights, bar=bar, now=now, data_root=tmp_path)

    assert outcome.status in {"preview", "unchanged"}, (outcome.status, outcome.detail)
    prices = outcome.delivery.signal.prices
    assert set(prices) == {"000001.SZ", "510300.SH"} and all(p > 0 for p in prices.values())
    closes = feed.raw_closes()
    # A bar run late may find the next one stored too.
    assert pd.Timestamp(closes.index.max()) >= pd.Timestamp(bar)
    sources = set(feed.panel()["source"]) if "source" in feed.panel() else set()
    assert not sources or {"pandadata", "akshare_sina"} <= sources


def test_futures_minute_feed_refreshes_updates_and_previews_a_bar(tmp_path, panda_client):
    from skills.live_trade.minute import refresh_day, run_bar
    from skills.live_trade.spec import Instrument, LiveSpec

    now = require_session(RB_WINDOWS, "rebar")
    spec = LiveSpec(
        strategy_id="live_check_rb",
        frequency="5m",
        instruments=(Instrument(symbol="RB_DOMINANT.SHF", asset="future"),),
        warmup_bars=48,
        adjust="none",
    )
    feed = _feed(spec, panda_client, tmp_path)

    refreshed = refresh_day(spec, feed, _equal_weights, now=now, data_root=tmp_path)
    assert refreshed.status == "refreshed", refreshed.detail
    state = feed.state()
    assert state.contracts["RB_DOMINANT.SHF"] == _dominant(panda_client)
    assert state.multipliers["RB_DOMINANT.SHF"] == 10
    bar = _due_bar(state, now)

    outcome = run_bar(spec, feed, _equal_weights, bar=bar, now=now, data_root=tmp_path)

    if outcome.status == "stale":
        pytest.xfail(f"Sina futures bars lag (measured 1-3 minutes): {outcome.detail}")
    assert outcome.status in {"preview", "unchanged"}, (outcome.status, outcome.detail)


# Daily workflows: module, strategy id, capital.
DAILY_WORKFLOWS = [
    (
        "strategies.cross_sectional.workflows.live_asset_class_rotation",
        "asset_class_rotation",
        "100000",
    ),
    ("strategies.cross_sectional.workflows.live_stock_ma_gap_1d", "stock_ma_gap_1d", "1000000"),
    ("strategies.time_series.workflows.live_rb_ma_atr_1d", "rb_ma_atr_1d", "100000"),
]


# --------------------------------------------------------------------------- daily at 14:50


def _daily_cutoff(kind: str) -> tuple[datetime, datetime]:
    """``(now, cut-off)``: 14:50 once it has passed today, else a recent bar of the session."""
    from tests.live.conftest import now as current

    moment = current()
    if moment.weekday() < 5 and any(a <= moment.time() <= b for a, b in AFTER_CUTOFF):
        return moment, moment.replace(hour=14, minute=50, second=0)
    moment = require_session(RB_DAY_WINDOWS if kind == "future" else EQUITY_WINDOWS, kind)
    lag = timedelta(minutes=5 if kind == "future" else 2)
    return moment, (moment - lag).replace(second=0)


@pytest.mark.parametrize("kind", ["fund", "stock", "future"])
def test_daily_bars_end_with_todays_bar_from_sina(kind, panda_client):
    """Today's bar is the 1-minute bars of the trading day up to the cut-off."""
    from skills.ingest.akshare_bars import fetch_intraday_bars
    from skills.live_trade.daily import SESSION_GAP, DailyNotReady, load_daily_bars
    from skills.live_trade.feeds import load_calendar
    from skills.live_trade.spec import Instrument

    now, cutoff = _daily_cutoff(kind)
    symbol = {"fund": "510300.SH", "stock": "000001.SZ", "future": "RB_DOMINANT.SHF"}[kind]
    try:
        bars = load_daily_bars(
            panda_client,
            [Instrument(symbol=symbol, asset=kind)],
            "2025-01-02",
            now.date(),
            cutoff=cutoff.time(),
            now=now,
        )
    except DailyNotReady as exc:
        if kind == "future":
            pytest.xfail(f"Sina futures bars lag (measured 1-3 minutes): {exc}")
        raise

    previous = load_calendar(panda_client, now.date()).previous(now.date())
    days = [pd.Timestamp(day).date() for day in bars.raw_close.index[-2:]]
    assert days == [previous, now.date()]
    contract = bars.contracts[symbol]
    minute = fetch_intraday_bars([contract], "1m", now=now).bars
    since = datetime.combine(previous, SESSION_GAP)
    minute = minute[(minute["eob"] > since) & (minute["eob"] <= cutoff)].sort_values("eob")
    today = bars.raw_panel.loc[(symbol, pd.Timestamp(now.date()))]
    assert today["close"] == float(minute["close"].iloc[-1]) > 0
    assert today["low"] <= min(today["open"], today["close"]) <= today["high"]
    if kind == "future":
        # Futures bars keep changing for a minute or two; only the shape is checked.
        assert today["volume"] > 0
        assert bars.factors[symbol] == 1.0 and contract == _dominant(panda_client)
        assert bars.multipliers[symbol] == 10
    else:
        assert today["open"] == float(minute["open"].iloc[0])
        assert today["high"] == float(minute["high"].max())
        assert today["low"] == float(minute["low"].min())
        assert today["volume"] == float(minute["volume"].sum())
        # Today's factor is yesterday's post/raw ratio unless today is an ex-date.
        factor = bars.factors[symbol]
        assert factor == pytest.approx(
            bars.close.iloc[-2][symbol] / bars.raw_close.iloc[-2][symbol], rel=1e-5
        )
        assert bars.close.iloc[-1][symbol] == pytest.approx(today["close"] * factor)


@pytest.mark.parametrize(("module", "strategy_id", "capital"), DAILY_WORKFLOWS)
def test_daily_workflow_previews_today_at_1450(
    module, strategy_id, capital, tmp_path, panda_client
):
    require_session(AFTER_CUTOFF, "today's 14:50 daily run")

    code, report = _workflow(module, "--data-root", str(tmp_path), "--capital", capital)

    assert code == 0 and report["status"] in {"preview", "unchanged"}, report
    assert report["trade_date"] == datetime.now().date().isoformat()
    target = report["target"] or {}
    assert all(0 <= value <= 1 + 1e-9 for value in target.values())
    assert sum(target.values()) <= 1 + 1e-9
    if report["status"] == "preview":
        assert "当日收盘价取 14:50 的价格" in report["message"]
    assert not (tmp_path / "live" / strategy_id / "ledger.json").exists()


# --------------------------------------------------------------------------- workflows


def _workflow(module: str, *args: str) -> tuple[int, dict]:
    completed = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    try:
        report = json.loads(completed.stdout)
    except ValueError:
        pytest.fail(
            f"{module} printed no JSON (exit {completed.returncode}): {completed.stderr[-800:]}"
        )
    return completed.returncode, report


@pytest.mark.parametrize(("module", "strategy_id", "capital"), DAILY_WORKFLOWS)
def test_daily_workflow_previews_the_last_trading_day(
    module, strategy_id, capital, tmp_path, panda_client
):
    """Any time: the last trading day's run at its 14:50 bar, which Sina still serves."""
    from skills.live_trade.feeds import load_calendar

    today = datetime.now().date()
    day = max(d for d in load_calendar(panda_client, today).days if d < today)

    code, report = _workflow(
        module, "--date", day.isoformat(), "--data-root", str(tmp_path), "--capital", capital
    )

    assert code == 0 and report["status"] in {"preview", "unchanged"}, report
    assert report["trade_date"] == day.isoformat()
    target = report["target"] or {}
    assert all(0 <= value <= 1 + 1e-9 for value in target.values())
    assert sum(target.values()) <= 1 + 1e-9
    assert not (tmp_path / "live" / strategy_id / "ledger.json").exists()


def test_rb_minute_workflow_refreshes_and_previews_the_due_bar(tmp_path, panda_client):
    module = "strategies.time_series.workflows.live_rb_ma_cross_5m"
    now = require_session(RB_WINDOWS, "rebar")

    code, refreshed = _workflow(module, "--refresh", "--data-root", str(tmp_path))
    assert code == 0 and refreshed["status"] == "refreshed", refreshed
    from skills.live_trade.feeds import read_feed_state

    bar = _due_bar(read_feed_state("rb_ma_cross_5m", tmp_path), now)
    code, report = _workflow(module, "--bar", bar.isoformat(), "--data-root", str(tmp_path))

    if report["status"] == "stale":
        pytest.xfail(f"Sina futures bars lag: {report['detail']}")
    assert code == 0 and report["status"] in {"preview", "unchanged"}, report
    assert report["execution"] is None


# --------------------------------------------------------------------------- PandaAI client


def test_client_cli_is_connected_with_a_usable_simnow_account(panda_cli, request):
    from skills.live_trade.execution import PandaTrader, check_account
    from skills.live_trade.panda_cli import cli_version, list_accounts, run_cli, version_problem

    require_session(RB_WINDOWS, "rebar")
    assert version_problem(cli_version(panda_cli)) is None
    simnow = [a for a in list_accounts(panda_cli) if a.is_simnow and a.cli_eligible]
    if not simnow:
        pytest.skip("no SimNow account with CLI mode on")
    trader = PandaTrader(panda_cli, simnow[0].code)
    check_account(trader)
    assert trader.connection().get("cli_ready") is True
    symbol = os.environ.get("QS_LIVE_ORDERS_CONTRACT", "").strip() or _dominant(
        request.getfixturevalue("panda_client")
    )
    quote = run_cli(panda_cli, "quote", "--account", simnow[0].code, "--symbol", symbol)
    assert quote["ready"] and not quote["stale"] and quote["quote"]["last"] > 0


def test_simnow_round_trip_opens_and_closes_one_contract(panda_cli, request):
    """Hot-rolled coil, not rebar: closing it must not flatten a rebar strategy's position."""
    from skills.live_trade.execution import PandaTrader, execute_targets

    account = os.environ.get("QS_LIVE_ORDERS_ACCOUNT")
    if not account:
        pytest.skip("set QS_LIVE_ORDERS_ACCOUNT to a SimNow account code to place orders")
    require_session(RB_WINDOWS, "hot-rolled coil")
    contract = _order_contract(request)
    trader = PandaTrader(panda_cli, account, trace_id="qs-live-check")

    opened = execute_targets(trader, {contract: 1}, request_id="live-check:open")
    closed = execute_targets(trader, {contract: 0}, request_id="live-check:close")

    assert opened.status == "filled" and opened.after == {contract: 1}, opened.to_dict()
    assert closed.status == "filled" and closed.after == {}, closed.to_dict()


def test_daily_futures_target_trades_on_simnow_then_flattens(panda_cli, panda_client, tmp_path):
    """A daily futures run's orders: today's dominant hot-rolled coil, one contract, then flat.

    Hot-rolled coil, not rebar, so a rebar strategy running on the same account is left alone.
    """
    from skills.live_trade.daily import DailyNotReady, load_daily_bars
    from skills.live_trade.execution import PandaTrader, execute_targets
    from skills.live_trade.runner import RunLog, futures_lots, trade_target
    from skills.live_trade.spec import Instrument

    account = os.environ.get("QS_LIVE_ORDERS_ACCOUNT")
    if not account:
        pytest.skip("set QS_LIVE_ORDERS_ACCOUNT to a SimNow account code to place orders")
    now = require_session(RB_DAY_WINDOWS, "hot-rolled coil")
    symbol = "HC_DOMINANT.SHF"
    try:
        closes = load_daily_bars(
            panda_client,
            [Instrument(symbol=symbol, asset="future")],
            "2025-01-02",
            now.date(),
            cutoff=(now - timedelta(minutes=5)).replace(second=0).time(),
            now=now,
        )
    except DailyNotReady as exc:
        pytest.xfail(f"Sina futures bars lag: {exc}")
    price = float(closes.raw_close.iloc[-1][symbol])
    contract = closes.contracts[symbol]
    # One contract's notional is about 1.5 times the target, so it rounds down to one.
    capital = price * closes.multipliers[symbol] * 1.5
    wanted = futures_lots(
        {symbol: 1.0},
        {symbol: price},
        contracts=closes.contracts,
        multipliers=closes.multipliers,
        capital=capital,
    )
    assert wanted == {contract: 1}
    trader = PandaTrader(panda_cli, account, trace_id="qs-live-daily-check")

    def execute(lots, request_id):
        return execute_targets(trader, lots, request_id=request_id)

    opened, _ = trade_target(
        "live_check_daily",
        now.date(),
        f"信号日：{now.date()}",
        lambda: wanted,
        execute,
        request_id="live-check:daily-open",
        runs=RunLog("live_check_daily", tmp_path),
        urls=[],
    )
    closed = execute_targets(trader, {contract: 0}, request_id="live-check:daily-close")

    assert opened.status == "filled" and opened.after == {contract: 1}, opened.to_dict()
    assert closed.status == "filled" and closed.after == {}, closed.to_dict()
