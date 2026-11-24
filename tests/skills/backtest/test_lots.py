"""``VectorBacktester(unit="lots")``: profit by quantity, rolls on actual contracts, T+1."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from skills.backtest import VectorBacktester, percent_to_lots
from skills.backtest.quantity import apply_tplus, trading_days
from skills.backtest.units import check_lots, check_lots_table

DAYS = pd.to_datetime(["2025-08-27", "2025-08-28", "2025-08-29", "2025-09-01", "2025-09-02"])


def panel(prices: dict[str, list[float]], index=DAYS, column="close") -> pd.DataFrame:
    frames = []
    for symbol, values in prices.items():
        frame = pd.DataFrame({column: values}, index=pd.DatetimeIndex(index, name="eob"))
        frame["symbol"] = symbol
        frames.append(frame.reset_index().set_index(["symbol", "eob"]))
    return pd.concat(frames).sort_index()


def futures_case():
    nan = np.nan
    data = panel(
        {
            # The continuous series jumps 100 on the roll day: the gap between contracts.
            "RB_DOMINANT.SHF": [3000, 3010, 3120, 3130, 3125],
            "RB2510.SHF": [3000, 3010, 3020, nan, nan],
            "RB2601.SHF": [3090, 3100, 3120, 3130, 3125],
        }
    )
    contracts = pd.DataFrame(
        {"RB_DOMINANT.SHF": ["RB2510.SHF"] * 2 + ["RB2601.SHF"] * 3}, index=DAYS
    )
    targets = pd.DataFrame({"RB_DOMINANT.SHF": [2, 2, 2, 2, 2]}, index=DAYS)
    return data, contracts, targets


def lots_bt(data, **kwargs) -> VectorBacktester:
    options = {
        "trade_at": "close",
        "signal_lag": 0,
        "commission": 0.0,
        "slippage_bp": 0.0,
        "unit": "lots",
        "capital": 100_000.0,
    }
    options.update(kwargs)
    return VectorBacktester(data, **options)


def test_futures_profit_follows_the_held_contract_through_a_roll():
    data, contracts, targets = futures_case()
    result = lots_bt(
        data, multipliers={"RB_DOMINANT.SHF": 10}, contracts=contracts, commission=0.0001
    ).run(targets)
    frame = result.result_df
    # 2 lots x 10 per point: +10 on the old contract, +10 into the roll bar on the old one,
    # then the new contract's own moves; the 100-point gap never shows up.
    assert frame["pnl"].tolist() == [200.0, 200.0, 200.0, -100.0]
    open_cost = 2 * 10 * 3000 * 0.0001
    roll_cost = (2 * 10 * 3020 + 2 * 10 * 3120) * 0.0001
    assert frame["cost"].iloc[0] == pytest.approx(open_cost)
    assert frame["cost"].iloc[2] == pytest.approx(roll_cost)
    assert frame["rolls"].tolist() == [0.0, 0.0, 1.0, 0.0]
    assert frame["equity_value"].iloc[-1] == pytest.approx(100_000 + 500 - open_cost - roll_cost)
    assert result.metrics["roll_count"] == 1.0
    assert result.metrics["total_pnl"] == pytest.approx(500.0)
    assert result.metrics["final_equity_value"] == pytest.approx(
        100_000 + result.metrics["total_pnl"] - result.metrics["total_cost"]
    )
    # Returns are net profit over the equity before the bar, so the curve ends where the
    # money does.
    assert frame["equity"].iloc[-1] == pytest.approx(frame["equity_value"].iloc[-1] / 100_000)
    assert result.executed_lots["RB_DOMINANT.SHF"].tolist() == [2.0] * 5
    assert result.executed_weights.iloc[0, 0] == pytest.approx(2 * 10 * 3000 / 100_000)


def test_the_last_bar_with_a_position_has_no_next_price_and_is_dropped():
    data, contracts, targets = futures_case()
    frame = (
        lots_bt(data, multipliers={"RB_DOMINANT.SHF": 10}, contracts=contracts)
        .run(targets)
        .result_df
    )
    assert frame.index[-1] == DAYS[-2]


def test_signal_lag_holds_the_row_from_the_next_bar():
    data, contracts, _ = futures_case()
    targets = pd.DataFrame({"RB_DOMINANT.SHF": [1, 0, 0, 0, 0]}, index=DAYS)
    result = lots_bt(
        data, multipliers={"RB_DOMINANT.SHF": 10}, contracts=contracts, signal_lag=1
    ).run(targets)
    assert result.executed_lots["RB_DOMINANT.SHF"].tolist() == [0.0, 1.0, 0.0, 0.0, 0.0]
    assert result.result_df["pnl"].loc[DAYS[1]] == pytest.approx(10 * (3020 - 3010))


def test_a_short_position_earns_when_the_price_falls():
    data = panel({"RB2601.SHF": [3100, 3090, 3080, 3070, 3060]})
    targets = pd.DataFrame({"RB2601.SHF": [-1] * 5}, index=DAYS)
    result = lots_bt(data, multipliers={"RB2601.SHF": 10}).run(targets)
    assert result.result_df["pnl"].tolist() == [100.0] * 4


def test_stocks_earn_the_adjusted_return_so_a_dividend_is_no_loss():
    raw = panel({"600000.SH": [10.0, 10.0, 9.5, 9.5, 9.6]})
    # Ex-dividend on the third day: the raw price drops 0.5, the adjusted one does not.
    adjusted = panel({"600000.SH": [20.0, 20.0, 20.0, 20.0, 20.0 * 9.6 / 9.5]})
    targets = pd.DataFrame({"600000.SH": [3, 3, 3, 3, 3]}, index=DAYS)
    result = lots_bt(raw, adjusted=adjusted).run(targets)
    pnl = result.result_df["pnl"]
    assert pnl.iloc[:3].tolist() == [0.0, 0.0, 0.0]
    # 3 lots = 300 shares, 0.1 up from 9.5.
    assert pnl.iloc[3] == pytest.approx(300 * 0.1)
    assert result.executed_weights.iloc[0, 0] == pytest.approx(300 * 10 / 100_000)


def test_stock_lots_need_adjusted_prices():
    raw = panel({"600000.SH": [10.0] * 5})
    targets = pd.DataFrame({"600000.SH": [1] * 5}, index=DAYS)
    with pytest.raises(ValueError, match="adjusted="):
        lots_bt(raw).run(targets)


def test_continuous_futures_need_the_contracts_table_and_a_multiplier():
    data, contracts, targets = futures_case()
    with pytest.raises(ValueError, match="contracts="):
        lots_bt(data, multipliers={"RB_DOMINANT.SHF": 10}).run(targets)
    with pytest.raises(ValueError, match="multiplier"):
        lots_bt(data, contracts=contracts).run(targets)


def test_a_missing_price_of_the_old_contract_on_the_roll_bar_is_an_error():
    data, contracts, targets = futures_case()
    data.loc[("RB2510.SHF", DAYS[2]), "close"] = np.nan
    with pytest.raises(ValueError, match="RB_DOMINANT.SHF"):
        lots_bt(data, multipliers={"RB_DOMINANT.SHF": 10}, contracts=contracts).run(targets)


@pytest.mark.parametrize(
    ("values", "message"),
    [([1.5] * 5, "whole number"), ([-1] * 5, "cannot be short")],
)
def test_invalid_lots_are_refused_not_rounded(values, message):
    raw = panel({"600000.SH": [10.0] * 5})
    targets = pd.DataFrame({"600000.SH": values}, index=DAYS)
    with pytest.raises(ValueError, match=message):
        lots_bt(raw, adjusted=raw).run(targets)


def test_options_match_the_unit():
    data = panel({"600000.SH": [10.0] * 5})
    with pytest.raises(ValueError, match="only apply to unit='lots'"):
        VectorBacktester(data, commission=0.0, slippage_bp=0.0, capital=1e5)
    with pytest.raises(ValueError, match="needs capital"):
        VectorBacktester(data, commission=0.0, slippage_bp=0.0, unit="lots")
    with pytest.raises(ValueError, match="unit must be"):
        VectorBacktester(data, commission=0.0, slippage_bp=0.0, unit="shares")


def test_margin_is_reported_not_enforced():
    data = panel({"RB2601.SHF": [3000.0] * 5})
    targets = pd.DataFrame({"RB2601.SHF": [5] * 5}, index=DAYS)
    result = lots_bt(
        data, multipliers={"RB2601.SHF": 10}, margin_rates={"RB2601.SHF": 0.1}, capital=10_000
    ).run(targets)
    assert result.result_df["margin_ratio"].iloc[0] == pytest.approx(5 * 10 * 3000 * 0.1 / 10_000)
    assert result.metrics["margin_over_equity_bars"] == 4.0
    assert result.executed_lots["RB2601.SHF"].iloc[-1] == 5.0


def test_percent_mode_is_unchanged_by_the_lots_options():
    data = panel({"510300.SH": [4.0, 4.1, 4.2, 4.1, 4.3]})
    weights = pd.DataFrame({"510300.SH": [1.0] * 5}, index=DAYS)
    result = VectorBacktester(data, commission=0.0, slippage_bp=0.0, signal_lag=0).run(weights)
    assert result.executed_lots is None
    assert result.result_df["raw_return"].iloc[0] == pytest.approx(4.1 / 4.0 - 1)


# --------------------------------------------------------------------- T+1 and trading days


def test_night_bars_belong_to_the_next_trading_day():
    eob = pd.to_datetime(
        ["2025-08-29 14:55", "2025-08-29 21:05", "2025-08-30 00:30", "2025-09-01 09:05"]
    )
    days = trading_days(eob)
    assert [day.date().isoformat() for day in days] == [
        "2025-08-29",
        "2025-09-01",
        "2025-09-01",
        "2025-09-01",
    ]


def test_stock_lots_bought_today_are_sold_on_the_next_day():
    eob = pd.to_datetime(
        ["2025-09-01 09:31", "2025-09-01 09:32", "2025-09-01 09:33", "2025-09-02 09:31"]
    )
    executed = pd.DataFrame(
        {"600000.SH": [2.0, 0.0, 0.0, 0.0], "IF2509.CFE": [1, 0, 1, 0]}, index=eob
    )
    held, blocked = apply_tplus(executed, trading_days(eob))
    assert held["600000.SH"].tolist() == [2.0, 2.0, 2.0, 0.0]
    assert blocked.tolist() == [0.0, 2.0, 2.0, 0.0]
    assert held["IF2509.CFE"].tolist() == [1, 0, 1, 0]


def test_intraday_stock_backtest_applies_t_plus_one():
    eob = pd.to_datetime(
        [
            "2025-09-01 09:31",
            "2025-09-01 09:32",
            "2025-09-01 09:33",
            "2025-09-02 09:31",
            "2025-09-02 09:32",
        ]
    )
    raw = panel({"600000.SH": [10.0, 10.1, 10.2, 10.3, 10.4]}, index=eob)
    targets = pd.DataFrame({"600000.SH": [1, 0, 0, 0, 0]}, index=eob)
    result = lots_bt(raw, adjusted=raw).run(targets)
    assert result.executed_lots["600000.SH"].tolist() == [1.0, 1.0, 1.0, 0.0, 0.0]
    assert result.metrics["blocked_sell_lots"] == 2.0


# --------------------------------------------------------------------- percent to lots (D11)


def test_percent_to_lots_resizes_only_when_the_weights_change():
    prices = pd.DataFrame(
        {"RB_DOMINANT.SHF": [3300.0, 3340.0, 3340.0, 3000.0], "510300.SH": [4.0, 4.0, 5.0, 5.0]},
        index=DAYS[:4],
    )
    weights = pd.DataFrame(
        {"RB_DOMINANT.SHF": [1.0, 1.0, 1.0, -0.5], "510300.SH": [0.5, 0.5, 0.0, 0.0]},
        index=DAYS[:4],
    )
    lots = percent_to_lots(weights, prices, capital=100_000, multipliers={"RB_DOMINANT.SHF": 10})
    # 100000 / 33000 = 3.03 -> 3; the drift to 3340 (2.99) keeps 3 until the weights change.
    assert lots["RB_DOMINANT.SHF"].tolist() == [3.0, 3.0, 3.0, -1.0]
    # 50000 / (4 x 100) = 125 lots of 100 shares.
    assert lots["510300.SH"].tolist() == [125.0, 125.0, 0.0, 0.0]


def test_percent_to_lots_needs_a_price_where_it_sizes():
    prices = pd.DataFrame({"510300.SH": [np.nan, 4.0]}, index=DAYS[:2])
    weights = pd.DataFrame({"510300.SH": [0.5, 0.5]}, index=DAYS[:2])
    with pytest.raises(ValueError, match="510300.SH"):
        percent_to_lots(weights, prices, capital=1e5)


def test_check_lots_helpers():
    assert check_lots({"RB2601.SHF": -2.0}) == {"RB2601.SHF": -2}
    table = pd.DataFrame({"600000.SH": [1, None]}, index=DAYS[:2])
    assert check_lots_table(table)["600000.SH"].tolist() == [1.0, 0.0]
