"""D11: percent targets are sized once and hold their units until the weight changes.

Futures orders and the messages of every asset (stocks and funds in 100-share lots) use
the same record, which matches the backtest's ``percent_to_lots`` bar by bar.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from skills.backtest import percent_to_lots
from skills.live_trade.execution import ExecutionResult
from skills.live_trade.runner import LiveInputs, run_live
from skills.live_trade.sizing import SizedLots

from .conftest import FEISHU

RB = "RB_DOMINANT.SHF"
HC = "HC_DOMINANT.SHF"
ETF = "510300.SH"
STOCK = "601998.SH"
MULTIPLIERS = {RB: 10.0, HC: 10.0}
DAYS = ("2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26")


def texts(http) -> list[str]:
    return [json.loads(item["body"])["content"]["text"] for item in http.sent]


# --------------------------------------------------------------------------- the record


def test_price_drift_keeps_the_lots_a_weight_was_sized_to(tmp_path):
    record = SizedLots("rb_daily", tmp_path)
    common = {"capital": 100_000, "multipliers": MULTIPLIERS}

    assert record.hold({RB: 1.0}, {RB: 3300.0}, **common, as_of=date(2026, 11, 23)) == {RB: 3}
    # 100000 / 33400 = 2.99 would be 2 contracts; the weight did not change, so 3 stay.
    assert record.hold({RB: 1.0}, {RB: 3340.0}, **common, as_of=date(2026, 11, 24)) == {RB: 3}
    saved = json.loads(record.path.read_text(encoding="utf-8"))
    assert saved["capital"] == 100_000 and saved["lot_size"] == 100
    assert saved["symbols"][RB] == {
        "weight": 1.0,
        "lots": 3,
        "units": 3,
        "price": 3300.0,
        "sized_at": "2026-11-23",
    }
    assert record.path == tmp_path / "live" / "rb_daily" / "sized_lots.json"


def test_a_changed_weight_new_symbol_or_new_capital_is_sized_at_todays_price(tmp_path):
    record = SizedLots("rb_daily", tmp_path)
    first = record.hold(
        {RB: 1.0}, {RB: 3300.0}, capital=100_000, multipliers=MULTIPLIERS, as_of=date(2026, 11, 23)
    )
    assert first == {RB: 3}

    # The weight halves at 3340: 0.5 x 100000 / 33400 = 1.5 -> 1; HC is new: 0.5 x 100000 / 31000.
    changed = record.hold(
        {RB: 0.5, HC: 0.5},
        {RB: 3340.0, HC: 3100.0},
        capital=100_000,
        multipliers=MULTIPLIERS,
        as_of=date(2026, 11, 24),
    )
    assert changed == {RB: 1, HC: 1}

    # A new capital sizes everything again: 0.5 x 300000 / 33400 = 4.49, / 31000 = 4.84.
    recapitalised = record.hold(
        {RB: 0.5, HC: 0.5},
        {RB: 3340.0, HC: 3100.0},
        capital=300_000,
        multipliers=MULTIPLIERS,
        as_of=date(2026, 11, 25),
    )
    assert recapitalised == {RB: 4, HC: 4}

    # A short weight rounds toward zero too; a symbol left out of the target leaves the record.
    short = record.hold(
        {RB: -0.5}, {RB: 3340.0}, capital=300_000, multipliers=MULTIPLIERS, as_of=date(2026, 11, 26)
    )
    assert short == {RB: -4}
    assert set(record.read()["symbols"]) == {RB}


def test_a_zero_weight_is_zero_lots_without_a_price(tmp_path):
    record = SizedLots("rb_daily", tmp_path)
    held = record.hold(
        {RB: 1.0, HC: 0.0},
        {RB: 3300.0},
        capital=100_000,
        multipliers=MULTIPLIERS,
        as_of=date(2026, 11, 23),
    )
    assert held == {RB: 3, HC: 0}
    assert record.read()["symbols"][HC]["price"] is None


def test_sizing_errors_raise_and_leave_the_record_alone(tmp_path):
    record = SizedLots("rb_daily", tmp_path)
    record.hold(
        {RB: 1.0}, {RB: 3300.0}, capital=100_000, multipliers=MULTIPLIERS, as_of=date(2026, 11, 23)
    )
    before = record.path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="--capital is required"):
        record.hold({RB: 0.5}, {RB: 3300.0}, capital=None, as_of=date(2026, 11, 24))
    with pytest.raises(ValueError, match="missing or invalid price"):
        record.hold(
            {RB: 0.5}, {}, capital=100_000, multipliers=MULTIPLIERS, as_of=date(2026, 11, 24)
        )
    with pytest.raises(ValueError, match="needs a contract multiplier"):
        record.hold({RB: 0.5}, {RB: 3300.0}, capital=100_000, as_of=date(2026, 11, 24))
    assert record.path.read_text(encoding="utf-8") == before

    record.clear()
    assert not record.path.exists()
    # Without the record the next run sizes at its own price: 100000 / 33400 -> 2.
    again = record.hold(
        {RB: 1.0}, {RB: 3340.0}, capital=100_000, multipliers=MULTIPLIERS, as_of=date(2026, 11, 24)
    )
    assert again == {RB: 2}


def test_held_lots_match_the_backtests_percent_to_lots():
    rng = np.random.default_rng(11)
    index = pd.date_range("2026-01-05 09:05", periods=120, freq="5min", name="eob")
    levels = np.array([0.0, 0.25, 0.5, 1.0, -0.5])
    weights = pd.DataFrame(
        {
            symbol: pd.Series(rng.choice(levels, len(index)), index=index)
            .where(rng.random(len(index)) < 0.15)
            .ffill()
            .fillna(0.0)
            for symbol in (RB, HC, ETF, STOCK)
        }
    )
    weights[[ETF, STOCK]] = weights[[ETF, STOCK]].abs()  # no short stocks or funds
    prices = pd.DataFrame(
        {
            RB: 3300 * np.exp(np.cumsum(rng.normal(0, 0.004, len(index)))),
            HC: 3100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(index)))),
            ETF: 4.0 * np.exp(np.cumsum(rng.normal(0, 0.004, len(index)))),
            STOCK: 9.5 * np.exp(np.cumsum(rng.normal(0, 0.004, len(index)))),
        },
        index=index,
    )
    expected = percent_to_lots(weights, prices, capital=250_000, multipliers=MULTIPLIERS)

    import tempfile

    with tempfile.TemporaryDirectory() as root:
        record = SizedLots("parity", root)
        held = pd.DataFrame(
            [
                record.hold(
                    weights.loc[stamp].to_dict(),
                    prices.loc[stamp].to_dict(),
                    capital=250_000,
                    multipliers=MULTIPLIERS,
                    as_of=stamp.to_pydatetime(),
                )
                for stamp in index
            ],
            index=index,
        ).astype(float)
    # Futures units are contracts, stock and fund units shares: 100 to the lot.
    held[[ETF, STOCK]] = held[[ETF, STOCK]] / 100
    columns = [RB, HC, ETF, STOCK]
    pd.testing.assert_frame_equal(held[columns], expected[columns], check_names=False)
    # The prices did move across rounding edges: sizing every bar would differ.
    per_lot = pd.Series({RB: 10.0, HC: 10.0, ETF: 100.0, STOCK: 100.0})
    fresh = np.trunc(weights * 250_000 / prices.mul(per_lot, axis=1))
    differs = (fresh != expected[columns]).any()
    assert differs[[RB, HC]].any() and differs[[ETF, STOCK]].any()


# --------------------------------------------------------------------------- daily runs


def _daily(weights: list[float], prices: list[float], contract: str = "RB2701.SHF"):
    days = DAYS[: len(weights)]
    index = pd.DatetimeIndex(pd.to_datetime(list(days)), name="eob")

    def load() -> LiveInputs:
        return LiveInputs(
            weights=pd.DataFrame({RB: weights}, index=index),
            prices=pd.DataFrame({RB: prices}, index=index),
            multipliers={RB: 10.0},
            contracts={RB: contract},
        )

    return load


def _run_day(tmp_path, n, weights, prices, seen, contract="RB2701.SHF", **options):
    def execute(wanted, request_id):
        seen.append(dict(wanted))
        return ExecutionResult("filled")

    return run_live(
        "rb_daily",
        _daily(weights[:n], prices[:n], contract),
        trade_date=date.fromisoformat(DAYS[n - 1]),
        is_trading_day=True,
        write=True,
        data_root=tmp_path,
        urls=[FEISHU],
        execute=execute,
        **{"capital": 100_000, **options},
    )


def test_daily_orders_hold_the_lots_while_the_weight_stays(tmp_path, http):
    weights = [1.0, 1.0, 0.5, 0.5]
    prices = [3010.0, 3340.0, 3340.0, 2400.0]
    seen = []

    first = _run_day(tmp_path, 1, weights, prices, seen)
    second = _run_day(tmp_path, 2, weights, prices, seen)
    third = _run_day(tmp_path, 3, weights, prices, seen)
    fourth = _run_day(tmp_path, 4, weights, prices, seen)

    # 3010: 3.3 -> 3; 3340 at the same weight would be 2.99 -> 2, but 3 are held.
    # 0.5 at 3340: 1.5 -> 1; 2400 at the same weight would be 2.08 -> 2, but 1 is held.
    assert seen == [{"RB2701.SHF": n} for n in (3, 3, 1, 1)]
    assert [first.status, second.status, third.status, fourth.status] == [
        "sent",
        "unchanged",
        "sent",
        "unchanged",
    ]
    messages = [text for text in texts(http) if "调仓信号" in text]
    assert "目标 3 手" in messages[0] and "目标 1 手" in messages[1]
    assert SizedLots("rb_daily", tmp_path).read()["symbols"][RB]["sized_at"] == "2026-11-25"


def test_a_roll_moves_the_held_lots_to_the_new_contract(tmp_path, http):
    weights, prices, seen = [1.0, 1.0], [3010.0, 3340.0], []
    _run_day(tmp_path, 1, weights, prices, seen)
    _run_day(tmp_path, 2, weights, prices, seen, contract="RB2705.SHF")
    # The 3 contracts belong to RB_DOMINANT.SHF: after the roll they are 3 of RB2705.
    assert seen == [{"RB2701.SHF": 3}, {"RB2705.SHF": 3}]


def test_a_new_capital_resizes_the_daily_orders(tmp_path, http):
    weights, prices, seen = [1.0, 1.0], [3010.0, 3340.0], []
    _run_day(tmp_path, 1, weights, prices, seen)
    _run_day(tmp_path, 2, weights, prices, seen, capital=200_000)
    # 200000 / 33400 = 5.99 -> 5 at the second day's price.
    assert seen == [{"RB2701.SHF": 3}, {"RB2701.SHF": 5}]


def test_a_failed_im_push_does_not_resize_the_next_run(tmp_path, http):
    weights, prices, seen = [1.0, 1.0], [3010.0, 3340.0], []
    http.failing.add("open.feishu.cn")
    failed = _run_day(tmp_path, 1, weights, prices, seen)
    http.failing.clear()
    retried = _run_day(tmp_path, 2, weights, prices, seen)

    assert failed.status == "failed" and retried.status == "sent"
    # The ledger never took the first target, so the second day signals it again; the lots
    # are still the ones sized on the first day, in the order and in the message.
    assert seen == [{"RB2701.SHF": 3}, {"RB2701.SHF": 3}]
    assert "目标 3 手" in [text for text in texts(http) if "调仓信号" in text][-1]


def test_stopped_and_closed_runs_still_size_and_the_next_run_orders_those_lots(tmp_path, http):
    from skills.live_trade.runner import stop_file

    weights, prices, seen = [0.5, 0.5], [3310.0, 3340.0], []
    stop = stop_file("rb_daily", tmp_path)
    stop.parent.mkdir(parents=True)
    stop.touch()
    stopped = _run_day(tmp_path, 1, weights, prices, seen, capital=200_000)
    stop.unlink()
    traded = _run_day(tmp_path, 2, weights, prices, seen, capital=200_000)

    # Sized on the stopped day at 3310: 0.5 x 200000 / 33100 = 3.02 -> 3 (3340 would give 2).
    assert stopped.execution.status == "stopped" and "目标 3 手" in stopped.delivery.body
    assert seen == [{"RB2701.SHF": 3}]
    assert traded.execution.status == "filled"

    closed = _run_day(tmp_path / "closed", 1, weights, prices, seen, closed="收盘")
    assert closed.execution.status == "closed"
    assert SizedLots("rb_daily", tmp_path / "closed").read()["symbols"][RB]["lots"] == 1


def test_previews_tests_and_lots_strategies_keep_no_record(tmp_path, http):
    weights, prices = [1.0], [3010.0]
    record = SizedLots("rb_daily", tmp_path)

    run_live(
        "rb_daily",
        _daily(weights, prices),
        trade_date=date(2026, 11, 23),
        is_trading_day=True,
        capital=100_000,
        data_root=tmp_path,
        urls=[FEISHU],
        execute=lambda wanted, request_id: ExecutionResult("filled"),
    )
    run_live(
        "rb_daily",
        _daily(weights, prices),
        trade_date=date(2026, 11, 23),
        is_trading_day=True,
        write=True,
        test=True,
        capital=100_000,
        data_root=tmp_path,
        urls=[FEISHU],
    )
    assert not record.path.exists()

    seen = []
    _run_day(tmp_path, 1, weights, prices, seen)
    assert record.path.exists()
    # The strategy turns into a lots strategy: its orders take the lots, the record goes.
    lots = _run_day(tmp_path, 2, [1.0, 2.0], [3010.0, 3340.0], seen, unit="lots")
    assert lots.execution.status == "filled" and seen[-1] == {"RB2701.SHF": 2}
    assert not record.path.exists()


def test_a_daily_run_without_capital_signals_and_reports_the_order_error(tmp_path, http):
    seen = []
    outcome = _run_day(tmp_path, 1, [1.0], [3010.0], seen, capital=None)
    assert outcome.status == "sent" and outcome.execution.status == "error"
    assert "--capital" in outcome.execution.detail and seen == []
    assert not SizedLots("rb_daily", tmp_path).path.exists()


# --------------------------------------------------------------------------- minute bars


def _half_or_full(panel: pd.DataFrame) -> pd.DataFrame:
    """Half long above 3300, fully long above 3000, flat otherwise."""
    close = panel["close"].unstack("symbol").sort_index()
    return (close > 3000).astype(float) - (close > 3300).astype(float) * 0.5


def _minute_feed(tmp_path, sina):
    from skills.live_trade.feeds import MinuteFeed
    from skills.live_trade.minute import refresh_day

    from .fakes import RB_SPEC, FakePandaData

    feed = MinuteFeed(RB_SPEC, FakePandaData(), data_root=tmp_path, akshare=sina, pause=0)
    refresh_day(RB_SPEC, feed, _half_or_full, now=datetime(2026, 11, 20, 18), data_root=tmp_path)
    return feed


def _bar(feed, tmp_path, bar, now, seen, **options):
    from skills.live_trade.minute import run_bar

    from .fakes import RB_SPEC

    def execute(wanted, request_id):
        seen.append(dict(wanted))
        return ExecutionResult("filled")

    return run_bar(
        RB_SPEC,
        feed,
        _half_or_full,
        bar=bar,
        now=now,
        write=True,
        capital=200_000,
        data_root=tmp_path,
        urls=[FEISHU],
        execute=execute,
        **options,
    )


def test_minute_bars_hold_the_lots_while_the_weight_stays(tmp_path, http):
    from .fakes import FakeSina

    first, second = datetime(2026, 11, 20, 21, 5), datetime(2026, 11, 20, 21, 10)
    sina = FakeSina()
    sina.add("RB2701", (first, 3310.0))
    feed = _minute_feed(tmp_path, sina)
    seen = []

    one = _bar(feed, tmp_path, first, datetime(2026, 11, 20, 21, 5, 25), seen)
    sina.add("RB2701", (second, 3340.0))
    two = _bar(feed, tmp_path, second, datetime(2026, 11, 20, 21, 10, 25), seen)

    # Half long: 0.5 x 200000 / 33100 = 3.02 -> 3. At 3340 a fresh sizing would give
    # 2.99 -> 2 and sell one contract; the weight did not change, so 3 are held.
    assert seen == [{"RB2701.SHF": 3}, {"RB2701.SHF": 3}]
    assert one.status == "sent" and two.status == "unchanged"
    saved = SizedLots("rb_demo", tmp_path).read()["symbols"][RB]
    assert saved["sized_at"] == "2026-11-20T21:05:00" and saved["price"] == 3310.0


def test_a_sessions_closed_last_bar_sizes_and_the_next_session_orders_it(tmp_path, http):
    from .fakes import FakeSina

    last, monday = datetime(2026, 11, 20, 23, 0), datetime(2026, 11, 23, 9, 5)
    sina = FakeSina()
    sina.add("RB2701", (last, 3310.0))
    feed = _minute_feed(tmp_path, sina)
    seen = []

    closed = _bar(feed, tmp_path, last, datetime(2026, 11, 20, 23, 0, 45), seen)
    sina.add("RB2701", (monday, 3340.0))
    opened = _bar(feed, tmp_path, monday, datetime(2026, 11, 23, 9, 5, 25), seen)

    # Half long from 3310: 0.5 x 200000 / 33100 = 3.02 -> 3, sized on the closed bar. At
    # Monday's 3340 a fresh sizing would give 2.99 -> 2; the order holds the 3.
    assert closed.execution.status == "closed" and "目标 3 手" in closed.delivery.body
    assert opened.status == "unchanged" and opened.execution.status == "filled"
    assert seen == [{"RB2701.SHF": 3}]


def test_a_failed_bar_push_keeps_the_lots_for_the_next_bar(tmp_path, http):
    from .fakes import FakeSina

    first, second = datetime(2026, 11, 20, 21, 5), datetime(2026, 11, 20, 21, 10)
    sina = FakeSina()
    sina.add("RB2701", (first, 3310.0))
    feed = _minute_feed(tmp_path, sina)
    seen = []

    http.failing.add("open.feishu.cn")
    failed = _bar(feed, tmp_path, first, datetime(2026, 11, 20, 21, 5, 25), seen)
    http.failing.clear()
    sina.add("RB2701", (second, 3340.0))
    resent = _bar(feed, tmp_path, second, datetime(2026, 11, 20, 21, 10, 25), seen)

    assert failed.status == "failed" and resent.status == "sent"
    assert seen == [{"RB2701.SHF": 3}, {"RB2701.SHF": 3}]
    assert "目标 3 手" in resent.delivery.body


# --------------------------------------------------------------------------- stocks and funds


def test_stock_and_fund_units_are_whole_lots_held_while_the_weight_stays(tmp_path):
    record = SizedLots("etf_daily", tmp_path)
    common = {"capital": 100_000, "multipliers": {}}

    # 100000 / 4.01 = 24937 shares -> 249 lots of 100; 0.5 x 100000 / 9.5 -> 52 lots.
    first = record.hold({ETF: 1.0, STOCK: 0.0}, {ETF: 4.01}, **common, as_of=date(2026, 11, 23))
    assert first == {ETF: 24_900, STOCK: 0}
    # At 4.03 a fresh sizing gives 248 lots; the weight did not change, so 249 stay.
    drift = record.hold({ETF: 1.0, STOCK: 0.0}, {ETF: 4.03}, **common, as_of=date(2026, 11, 24))
    assert drift == {ETF: 24_900, STOCK: 0}
    changed = record.hold(
        {ETF: 0.5, STOCK: 0.5}, {ETF: 4.03, STOCK: 9.5}, **common, as_of=date(2026, 11, 25)
    )
    assert changed == {ETF: 12_400, STOCK: 5_200}
    assert record.read()["symbols"][STOCK] == {
        "weight": 0.5,
        "lots": 52,
        "units": 5_200,
        "price": 9.5,
        "sized_at": "2026-11-25",
    }
    # Another board lot is another sizing: everything is sized again.
    relotted = record.hold(
        {ETF: 0.5, STOCK: 0.5},
        {ETF: 4.03, STOCK: 9.5},
        **common,
        lot_size=200,
        as_of=date(2026, 11, 26),
    )
    assert relotted == {ETF: 12_400, STOCK: 5_200}
    assert record.read()["symbols"][ETF]["lots"] == 62


def _fund_daily(weights: list[float], prices: list[float]):
    days = DAYS[: len(weights)]
    index = pd.DatetimeIndex(pd.to_datetime(list(days)), name="eob")

    def load() -> LiveInputs:
        return LiveInputs(
            weights=pd.DataFrame({ETF: weights}, index=index),
            prices=pd.DataFrame({ETF: prices}, index=index),
        )

    return load


def _fund_day(tmp_path, n, weights, prices, **options):
    return run_live(
        "etf_daily",
        _fund_daily(weights[:n], prices[:n]),
        trade_date=date.fromisoformat(DAYS[n - 1]),
        is_trading_day=True,
        data_root=tmp_path,
        urls=[FEISHU],
        **{"write": True, "capital": 100_000, **options},
    )


def test_daily_fund_messages_hold_the_shares_the_weight_was_sized_to(tmp_path, http):
    weights, prices = [1.0, 1.0, 0.5], [4.01, 4.03, 4.03]
    record = SizedLots("etf_daily", tmp_path)

    http.failing.add("open.feishu.cn")
    failed = _fund_day(tmp_path, 1, weights, prices)
    http.failing.clear()
    resent = _fund_day(tmp_path, 2, weights, prices)
    assert record.read()["symbols"][ETF]["sized_at"] == "2026-11-23"
    halved = _fund_day(tmp_path, 3, weights, prices)

    assert failed.status == "failed" and resent.status == "sent" and halved.status == "sent"
    assert "目标 24900 股" in failed.delivery.body
    # The ledger never took day 1, so day 2 signals the same weight again: with the shares
    # sized on day 1 (24800 at 4.03 would be a fresh sizing).
    assert "目标 24900 股" in resent.delivery.body
    # The weight halves on day 3 and is sized at its price: 50000 / 4.03 -> 124 lots.
    assert "目标 12400 股" in halved.delivery.body
    assert record.read()["symbols"][ETF] == {
        "weight": 0.5,
        "lots": 124,
        "units": 12_400,
        "price": 4.03,
        "sized_at": "2026-11-25",
    }


def test_fund_previews_tests_runs_without_capital_and_lots_keep_no_record(tmp_path, http):
    weights, prices = [1.0, 1.0], [4.01, 4.03]
    record = SizedLots("etf_daily", tmp_path)

    preview = _fund_day(tmp_path, 1, weights, prices, write=False)
    assert "目标 24900 股" in preview.delivery.body
    _fund_day(tmp_path, 1, weights, prices, test=True)
    _fund_day(tmp_path, 1, weights, prices, capital=None)
    assert not record.path.exists()

    _fund_day(tmp_path / "lots", 1, weights, prices)
    assert SizedLots("etf_daily", tmp_path / "lots").path.exists()
    lots = run_live(
        "etf_daily",
        lambda: LiveInputs(
            weights=pd.DataFrame(
                {ETF: [3.0, 3.0]}, index=pd.DatetimeIndex(pd.to_datetime(DAYS[:2]), name="eob")
            ),
            prices=pd.DataFrame(
                {ETF: prices}, index=pd.DatetimeIndex(pd.to_datetime(DAYS[:2]), name="eob")
            ),
        ),
        trade_date=date(2026, 11, 24),
        is_trading_day=True,
        write=True,
        data_root=tmp_path / "lots",
        urls=[FEISHU],
        unit="lots",
    )
    assert lots.status == "sent" and "目标 3 手（300 股" in lots.delivery.body
    assert not SizedLots("etf_daily", tmp_path / "lots").path.exists()


def test_a_broken_record_still_signals_at_todays_prices_with_a_note(tmp_path, http):
    record = SizedLots("etf_daily", tmp_path)
    record.path.parent.mkdir(parents=True)
    record.path.write_text("{not json", encoding="utf-8")

    outcome = _fund_day(tmp_path, 1, [1.0], [4.01])

    assert outcome.status == "sent" and "目标 24900 股" in outcome.delivery.body
    assert "数量没有按记录换算（JSONDecodeError" in outcome.delivery.body
    assert record.path.read_text(encoding="utf-8") == "{not json"


def test_minute_stock_and_fund_bars_hold_their_shares(tmp_path, http):
    from skills.live_trade.feeds import MinuteFeed
    from skills.live_trade.minute import refresh_day, run_bar

    from .fakes import EQUITY_SPEC, FakePandaData, FakeSina

    def equal(panel: pd.DataFrame) -> pd.DataFrame:
        close = panel["close"].unstack("symbol").sort_index()
        return close.notna().astype(float) / close.shape[1]

    first, second = datetime(2026, 11, 20, 9, 35), datetime(2026, 11, 20, 9, 40)
    sina = FakeSina()
    sina.add("sh601998", (first, 9.5))
    sina.add("sh510300", (first, 4.0))
    feed = MinuteFeed(EQUITY_SPEC, FakePandaData(), data_root=tmp_path, akshare=sina, pause=0)
    refresh_day(EQUITY_SPEC, feed, equal, now=datetime(2026, 11, 20, 8, 30), data_root=tmp_path)

    def bar(when, now):
        return run_bar(
            EQUITY_SPEC,
            feed,
            equal,
            bar=when,
            now=now,
            write=True,
            capital=100_000,
            data_root=tmp_path,
            urls=[FEISHU],
        )

    http.failing.add("open.feishu.cn")
    one = bar(first, datetime(2026, 11, 20, 9, 35, 30))
    http.failing.clear()
    sina.add("sh601998", (second, 9.7))
    sina.add("sh510300", (second, 4.03))
    two = bar(second, datetime(2026, 11, 20, 9, 40, 30))

    # 50000 / 9.5 -> 52 lots, 50000 / 4.0 -> 125 lots. At 9.7 and 4.03 a fresh sizing gives
    # 51 and 124 lots; the weights did not change, so the shares stay.
    assert one.status == "failed" and two.status == "sent"
    for outcome in (one, two):
        assert "601998.SH：0.00% → 50.00%" in outcome.delivery.body
        assert "目标 5200 股" in outcome.delivery.body and "目标 12500 股" in outcome.delivery.body
    saved = SizedLots("eq_demo", tmp_path).read()["symbols"]
    assert {symbol: entry["units"] for symbol, entry in saved.items()} == {
        "510300.SH": 12_500,
        "601998.SH": 5_200,
    }
