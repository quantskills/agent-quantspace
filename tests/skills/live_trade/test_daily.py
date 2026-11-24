"""Daily strategies at 14:50: PandaData closes up to yesterday plus today's Sina 14:50 price."""

from __future__ import annotations

from datetime import date, datetime, time

import pandas as pd
import pytest

from skills.ingest.akshare_bars import SinaQuote
from skills.live_trade.daily import DailyNotReady, load_daily_bars
from skills.live_trade.execution import ExecutionResult
from skills.live_trade.runner import RunLog, run_live, stop_file
from skills.live_trade.spec import Instrument

from .conftest import FEISHU
from .fakes import FRIDAY, MONDAY, FakePandaData, FakeSina

AT = datetime(2026, 11, 23, 14, 50)
AFTER = datetime(2026, 11, 23, 14, 51)
STOCK = Instrument(symbol="601998.SH", asset="stock")
FUND = Instrument(symbol="510300.SH", asset="fund")
RB = Instrument(symbol="RB_DOMINANT.SHF", asset="future")


def _client() -> FakePandaData:
    client = FakePandaData()
    client.daily_until = FRIDAY  # at 14:50 PandaData has no bar of the day yet
    return client


def _quotes(pre_close=None, day="2026-11-23", failing=()):
    """Sina quotes whose previous close is yesterday's close unless ``pre_close`` says."""

    def fetch(symbols):
        quotes = {
            symbol: SinaQuote(
                symbol, (pre_close or {}).get(symbol, 10.0), 10.0, 10.0, day, "14:50:30"
            )
            for symbol in symbols
            if symbol not in failing
        }
        return quotes, dict.fromkeys(failing, "ConnectionError: quote")

    return fetch


def _load(items, client=None, sina=None, now=AFTER, quotes=None, **kwargs):
    return load_daily_bars(
        client or _client(),
        items,
        "2026-10-01",
        MONDAY,
        now=now,
        akshare=sina,
        pause=0,
        quotes=quotes or _quotes(),
        **kwargs,
    )


def _sina(**prices) -> FakeSina:
    sina = FakeSina()
    for code, close in prices.items():
        sina.add(code, (datetime(2026, 11, 23, 14, 49), close - 0.5), (AT, close))
    return sina


def test_today_is_the_1450_price_times_todays_factor():
    closes = _load([STOCK, FUND], sina=_sina(sh601998=11.0, sh510300=4.0))

    assert pd.Timestamp(closes.raw_close.index[-2]).date() == FRIDAY
    assert pd.Timestamp(closes.raw_close.index[-1]).date() == MONDAY
    assert closes.raw_close.loc["2026-11-23"].to_dict() == {"601998.SH": 11.0, "510300.SH": 4.0}
    # 601998's factor is 2.1 since Thursday, 510300's 1.5: yesterday's carries over.
    assert closes.close.loc["2026-11-23"].to_dict() == pytest.approx(
        {"601998.SH": 23.1, "510300.SH": 6.0}
    )
    assert closes.close.loc["2026-11-20"].to_dict() == pytest.approx(
        {"601998.SH": 21.0, "510300.SH": 15.0}
    )
    assert closes.factors == {"601998.SH": 2.1, "510300.SH": 1.5}
    assert closes.cutoff == AT and closes.notes[:2] == [
        "说明：",
        "- 当日收盘价取 14:50 的价格，当天 K 线由新浪 1 分钟线聚合",
    ]


def test_adjust_none_signals_on_raw_closes():
    closes = _load([FUND], sina=_sina(sh510300=4.0), adjust="none")

    assert closes.close.equals(closes.raw_close) and closes.factors == {"510300.SH": 1.0}


def test_symbols_of_one_asset_can_be_passed_as_strings():
    closes = load_daily_bars(
        _client(),
        ["510300.SH"],
        "2026-10-01",
        MONDAY,
        asset="fund",
        now=AFTER,
        akshare=_sina(sh510300=4.0),
        pause=0,
        quotes=_quotes(),
    )
    assert list(closes.raw_close.columns) == ["510300.SH"]
    with pytest.raises(ValueError, match="asset="):
        load_daily_bars(FakePandaData(), ["510300.SH"], "2026-10-01", MONDAY)


def test_before_the_cutoff_bar_is_finished_it_is_not_ready():
    sina = FakeSina()
    sina.add("sh510300", (datetime(2026, 11, 23, 14, 49), 4.0), (AT, 4.1))

    with pytest.raises(DailyNotReady, match="14:50 的 K 线.*14:49"):
        _load([FUND], sina=sina, now=datetime(2026, 11, 23, 14, 49, 30))


def test_a_sina_failure_is_not_ready():
    sina = _sina(sh510300=4.0)
    sina.failing.add("sh510300")

    with pytest.raises(DailyNotReady, match="ConnectionError"):
        _load([FUND], sina=sina)


def test_a_stock_without_a_trade_today_keeps_the_previous_close():
    sina = _sina(sh510300=4.0)
    sina.add("sh601998", (datetime(2026, 11, 20, 15, 0), 10.0))

    early = datetime(2026, 11, 23, 14, 51)  # Sina may still post the minute
    with pytest.raises(DailyNotReady, match="601998.SH"):
        _load([STOCK, FUND], sina=sina, now=early)
    bars = _load([STOCK, FUND], sina=sina, now=datetime(2026, 11, 23, 14, 52, 30))

    today = bars.raw_panel.loc[("601998.SH", pd.Timestamp(MONDAY))].to_dict()
    # The quote's previous close (10.0), as PandaData's bar of a day without trades.
    assert today == {"open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "volume": 0.0}
    assert bars.close.loc["2026-11-23", "601998.SH"] == pytest.approx(21.0)
    assert bars.suspended == ("601998.SH",)
    assert bars.notes[-1] == "- 截至收盘价时刻没有成交（按前收盘价）：601998.SH"


def test_a_minute_without_trades_takes_the_last_trade_before_the_cutoff():
    """Sina has no bar for a minute nobody traded, as 510170.SH at 14:50 on 2026-11-23."""
    quiet = FakeSina()
    quiet.add(
        "sh510300", (datetime(2026, 11, 23, 9, 31), 4.0), (datetime(2026, 11, 23, 14, 49), 4.2)
    )

    with pytest.raises(DailyNotReady, match="14:49"):
        _load([FUND], sina=quiet, now=datetime(2026, 11, 23, 14, 51, 30))
    settled = _load([FUND], sina=quiet, now=datetime(2026, 11, 23, 14, 52))
    assert settled.raw_close.loc["2026-11-23", "510300.SH"] == 4.2

    quiet.add("sh510300", (datetime(2026, 11, 23, 14, 51), 4.3))  # a later bar is out
    later = _load([FUND], sina=quiet, now=datetime(2026, 11, 23, 14, 51, 30))
    assert later.raw_close.loc["2026-11-23", "510300.SH"] == 4.2
    assert later.raw_panel.loc[("510300.SH", pd.Timestamp(MONDAY)), "volume"] == 100.0


def test_a_stock_ex_date_uses_the_published_factor_or_the_previous_close():
    client = _client()
    client.ex_dates["601998.SH"] = ["20261123"]
    # Announced, unpublished, and the previous close did not move: wait.
    with pytest.raises(DailyNotReady, match="除权除息日"):
        _load([STOCK], client=client, sina=_sina(sh601998=11.0))

    # The exchange's previous close is the ex-dividend price: 10 -> 9.5.
    derived = _load(
        [STOCK], client=client, sina=_sina(sh601998=11.0), quotes=_quotes({"601998.SH": 9.5})
    )
    assert derived.factors["601998.SH"] == round(2.1 * 10 / 9.5, 6)

    client.published["601998.SH"] = {"20261123": 2.2}
    closes = _load([STOCK], client=client, sina=_sina(sh601998=11.0))
    assert closes.close.loc["2026-11-23", "601998.SH"] == pytest.approx(24.2)


def test_a_fund_ex_date_shows_in_the_previous_close():
    """PandaData publishes no fund dividends; the exchange's previous close tells them."""
    closes = _load([FUND], sina=_sina(sh510300=4.0), quotes=_quotes({"510300.SH": 9.8}))

    factor = round(1.5 * 10 / 9.8, 6)
    assert closes.factors == {"510300.SH": factor}
    assert closes.close.loc["2026-11-23", "510300.SH"] == pytest.approx(4.0 * factor)


def test_without_todays_previous_close_it_is_not_ready():
    with pytest.raises(DailyNotReady, match="前收盘价.*ConnectionError"):
        _load([FUND], sina=_sina(sh510300=4.0), quotes=_quotes(failing=("510300.SH",)))
    with pytest.raises(DailyNotReady, match="前收盘价.*2026-11-20"):
        _load([FUND], sina=_sina(sh510300=4.0), quotes=_quotes(day="2026-11-20"))


def test_a_published_day_takes_pandadatas_previous_close():
    client = FakePandaData()  # Monday is published
    client.pre_closes[("510300.SH", MONDAY)] = 9.8

    def no_quotes(symbols):
        raise AssertionError("a published day needs no Sina quote")

    closes = _load([FUND], client=client, sina=_sina(sh510300=4.0), quotes=no_quotes)
    assert closes.factors == {"510300.SH": round(1.5 * 10 / 9.8, 6)}


def test_futures_take_the_dominant_contract_including_the_night_session():
    sina = FakeSina()
    sina.add(
        "RB2701",
        (datetime(2026, 11, 20, 14, 50), 2990.0),  # Friday: not today's bar
        (datetime(2026, 11, 20, 21, 1), 2995.0),  # Friday night belongs to Monday
        (AT, 3010.0),
    )

    closes = _load([RB], sina=sina)

    assert closes.raw_close.loc["2026-11-23", "RB_DOMINANT.SHF"] == 3010.0
    assert closes.close.equals(closes.raw_close)
    assert closes.contracts == {"RB_DOMINANT.SHF": "RB2701.SHF"}
    assert closes.multipliers == {"RB_DOMINANT.SHF": 10.0}
    assert "- RB_DOMINANT.SHF 当前对应 RB2701.SHF" in closes.notes
    inputs = closes.inputs(closes.raw_close.notna().astype(float))
    assert inputs.contracts == closes.contracts and inputs.multipliers == closes.multipliers


def test_a_futures_bar_that_is_late_is_not_ready_rather_than_suspended():
    sina = FakeSina()
    sina.add("RB2701", (datetime(2026, 11, 23, 14, 47), 3000.0))

    with pytest.raises(DailyNotReady, match="RB2701.SHF.*14:47"):
        _load([RB], sina=sina)


def test_a_custom_cutoff_reads_that_bar():
    sina = _sina(sh510300=4.0)
    sina.add("sh510300", (datetime(2026, 11, 23, 13, 30), 3.9))

    closes = _load([FUND], sina=sina, cutoff=time(13, 30))

    assert closes.raw_close.loc["2026-11-23", "510300.SH"] == 3.9


def test_a_trade_date_that_is_not_a_trading_day_raises():
    with pytest.raises(ValueError, match="not a trading day"):
        load_daily_bars(FakePandaData(), [FUND], "2026-10-01", date(2026, 11, 22))


def test_run_live_reports_not_ready_as_stale_and_carries_the_notes(tmp_path):
    client = _client()

    def waiting():
        closes = _load([FUND], client=client, sina=FakeSina())
        return closes.inputs(closes.raw_close.notna().astype(float))

    stale = run_live(
        "etf_demo", waiting, trade_date=MONDAY, is_trading_day=True, data_root=tmp_path
    )
    assert stale.status == "stale" and "14:50" in stale.detail

    def ready():
        closes = _load([FUND], client=client, sina=_sina(sh510300=4.0))
        return closes.inputs(closes.raw_close.notna().astype(float))

    outcome = run_live(
        "etf_demo", ready, trade_date=MONDAY, is_trading_day=True, data_root=tmp_path, capital=1e5
    )
    assert outcome.status == "preview"
    assert outcome.delivery.signal.prices == {"510300.SH": 4.0}
    assert "当日收盘价取 14:50" in outcome.delivery.body


# --------------------------------------------------------------------------- futures orders


def _rb_inputs(weight: float = 1.0):
    sina = FakeSina()
    sina.add("RB2701", (AT, 3010.0))
    closes = _load([RB], sina=sina)
    weights = closes.raw_close.notna().astype(float) * weight
    return lambda: closes.inputs(weights)


def _executor(seen, status="filled"):
    def execute(wanted, request_id):
        seen.append((dict(wanted), request_id))
        return ExecutionResult(status, account="SimNow（100001）")

    return execute


def test_a_daily_futures_run_trades_whole_contracts_of_todays_contract(tmp_path, http, monkeypatch):
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    seen = []

    outcome = run_live(
        "rb_daily",
        _rb_inputs(),
        trade_date=MONDAY,
        is_trading_day=True,
        write=True,
        capital=100_000,
        data_root=tmp_path,
        execute=_executor(seen),
    )

    # 100000 / (3010 * 10) = 3.3 contracts of RB2701, rounded toward zero
    assert seen == [({"RB2701.SHF": 3}, "rb_daily:2026-11-23")]
    assert outcome.status == "sent" and outcome.execution.status == "filled"
    logged = RunLog("rb_daily", tmp_path).get(MONDAY)
    assert logged["execution"]["status"] == "filled"
    assert "RB_DOMINANT.SHF 当前对应 RB2701.SHF" in outcome.delivery.body


def test_a_daily_run_places_no_order_past_max_lots_or_with_the_stop_file(
    tmp_path, http, monkeypatch
):
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    seen = []
    common = {"trade_date": MONDAY, "is_trading_day": True, "write": True, "capital": 100_000}

    over = run_live(
        "rb_daily", _rb_inputs(), **common, data_root=tmp_path, execute=_executor(seen), max_lots=2
    )
    assert over.execution.status == "over_limit" and seen == []

    other = tmp_path / "other"
    stop_file("rb_daily", other).parent.mkdir(parents=True)
    stop_file("rb_daily", other).touch()
    stopped = run_live("rb_daily", _rb_inputs(), **common, data_root=other, execute=_executor(seen))
    assert stopped.execution.status == "stopped" and seen == []
    assert stopped.status == "sent"  # the signal still goes out


def test_orders_are_only_wired_for_futures(tmp_path, http, monkeypatch):
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    closes = _load([FUND], sina=_sina(sh510300=4.0))

    outcome = run_live(
        "etf_daily",
        lambda: closes.inputs(closes.raw_close.notna().astype(float)),
        trade_date=MONDAY,
        is_trading_day=True,
        write=True,
        capital=100_000,
        data_root=tmp_path,
        execute=_executor([]),
    )

    assert (
        outcome.execution.status == "error" and "only wired for futures" in outcome.execution.detail
    )


def test_daily_main_trades_with_account_at_the_cutoff(tmp_path, http, monkeypatch, capsys):
    import json

    from skills.live_trade.workflow import daily_main

    seen = []

    def execute_targets(trader, wanted, *, request_id):
        seen.append((trader.account, trader.env, dict(wanted), request_id))
        return ExecutionResult("filled", account=trader.account)

    client = FakePandaData()
    monkeypatch.setattr("skills.ingest.PandaDataClient", lambda: client)
    monkeypatch.setattr("skills.live_trade.panda_cli.discover_cli", lambda: ["panda-live-trading"])
    monkeypatch.setattr("skills.live_trade.execution.execute_targets", execute_targets)
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    load = _rb_inputs()

    code = daily_main(
        "rb_daily",
        lambda client, day, market_dir: load(),
        ["--date", "2026-11-23", "--write", "--capital", "100000", "--account", "100001"]
        + ["--now", "2026-11-23T14:51:05", "--data-root", str(tmp_path)],
    )

    report = json.loads(capsys.readouterr().out)
    assert (code, report["status"], report["execution"]["status"]) == (0, "sent", "filled")
    assert seen == [
        (
            "100001",
            {"PANDA_LIVE_TRACE_ID": "rb_daily-20261123T1450"},
            {"RB2701.SHF": 3},
            "rb_daily:2026-11-23",
        )
    ]


@pytest.mark.parametrize(
    "now", ["2026-11-23T15:00:00", "2026-11-23T14:49:00", "2026-11-24T14:51:00"]
)
def test_daily_main_orders_only_between_the_cutoff_and_the_day_close(
    now, tmp_path, http, monkeypatch, capsys
):
    """After 15:00 (a run made up late) or on another day the signal goes out, no order."""
    import json

    from skills.live_trade.workflow import daily_main

    seen = []

    def execute_targets(trader, wanted, *, request_id):
        seen.append(dict(wanted))
        return ExecutionResult("filled")

    monkeypatch.setattr("skills.ingest.PandaDataClient", lambda: FakePandaData())
    monkeypatch.setattr("skills.live_trade.panda_cli.discover_cli", lambda: ["panda-live-trading"])
    monkeypatch.setattr("skills.live_trade.execution.execute_targets", execute_targets)
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    load = _rb_inputs()

    code = daily_main(
        "rb_daily",
        lambda client, day, market_dir: load(),
        ["--date", "2026-11-23", "--write", "--capital", "100000", "--account", "100001"]
        + ["--now", now, "--data-root", str(tmp_path)],
    )

    report = json.loads(capsys.readouterr().out)
    assert (code, report["status"], report["execution"]["status"]) == (0, "sent", "closed")
    assert "14:50–15:00" in report["execution"]["detail"] and seen == []
    assert RunLog("rb_daily", tmp_path).get(date(2026, 11, 23))["execution"]["status"] == "closed"
    texts = [json.loads(item["body"])["content"]["text"] for item in http.sent]
    assert not [text for text in texts if "execution_" in text]


def test_todays_bar_adjusts_prices_but_not_volume():
    sina = FakeSina()
    sina.add(
        "sh601998",
        (datetime(2026, 11, 20, 15, 0), 9.0),  # Friday: not today's
        (datetime(2026, 11, 23, 9, 31), 10.5),
        (datetime(2026, 11, 23, 13, 1), 11.5),
        (AT, 11.0),
        (datetime(2026, 11, 23, 14, 51), 12.0),  # after the cut-off
    )

    bars = _load([STOCK], sina=sina)

    raw = bars.raw_panel.loc[("601998.SH", pd.Timestamp(MONDAY))].to_dict()
    # FakeSina bars: open = close, high = close + 1, low = close - 1, volume 50.
    assert raw == {"open": 10.5, "high": 12.5, "low": 9.5, "close": 11.0, "volume": 150.0}
    adjusted = bars.panel.loc[("601998.SH", pd.Timestamp(MONDAY))].to_dict()
    assert adjusted == pytest.approx(
        {"open": 22.05, "high": 26.25, "low": 19.95, "close": 23.1, "volume": 150.0}
    )
    assert list(bars.panel.columns) == ["open", "high", "low", "close", "volume"]
