"""D11: percent futures orders size a weight once and hold the lots until it changes."""

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
    assert saved["capital"] == 100_000
    assert saved["symbols"][RB] == {
        "weight": 1.0,
        "lots": 3,
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
            for symbol in (RB, HC)
        }
    )
    prices = pd.DataFrame(
        {
            RB: 3300 * np.exp(np.cumsum(rng.normal(0, 0.004, len(index)))),
            HC: 3100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(index)))),
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
    pd.testing.assert_frame_equal(held[[RB, HC]], expected[[RB, HC]], check_names=False)
    # The prices did move across rounding edges: sizing every bar would differ.
    fresh = np.trunc(weights * 250_000 / (prices * 10))
    assert (fresh != expected).any().any()


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
