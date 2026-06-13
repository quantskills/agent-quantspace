from __future__ import annotations

import pandas as pd
import pytest

from skills.analyze.attribution_core import (
    compute_category_pnl,
    compute_symbol_pnl,
    make_category_neutral_benchmark,
    normalize_weight_ledger,
)


def test_attribution_core_computes_symbol_and_category_pnl() -> None:
    dates = pd.date_range("2024-01-01", periods=2, name="date")
    weights = pd.DataFrame({"AAA": [0.6, 0.4], "BBB": [0.4, 0.6]}, index=dates)
    returns = pd.DataFrame(
        {
            "date": [dates[0], dates[0], dates[1], dates[1]],
            "symbol": ["AAA", "BBB", "AAA", "BBB"],
            "ret_1d_fwd": [0.01, -0.02, 0.02, 0.01],
        }
    )
    category_map = pd.DataFrame(
        {"symbol": ["AAA", "BBB"], "category": ["equity", "bond"]}
    )

    ledger = normalize_weight_ledger(weights, strategy_id="demo")
    pnl = compute_symbol_pnl(ledger, returns)
    category_pnl = compute_category_pnl(pnl, category_map)

    assert set(ledger.columns) == {"date", "strategy_id", "symbol", "weight"}
    assert pnl["net_contrib"].sum() == pytest.approx(0.012)
    assert set(category_pnl["category"]) == {"equity", "bond"}


def test_category_neutral_benchmark_equal_weights_within_categories() -> None:
    dates = pd.date_range("2024-01-01", periods=1)
    symbol_returns = pd.DataFrame(
        {
            "date": [dates[0], dates[0], dates[0]],
            "symbol": ["AAA", "BBB", "CCC"],
            "ret_1d_fwd": [0.01, 0.02, 0.03],
        }
    )
    category_map = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "category": ["risk", "risk", "defensive"],
        }
    )

    benchmark = make_category_neutral_benchmark(symbol_returns, category_map)

    assert benchmark.loc[benchmark["symbol"].eq("CCC"), "weight"].iloc[0] == pytest.approx(0.5)
    assert benchmark.loc[benchmark["category"].eq("risk"), "weight"].sum() == pytest.approx(0.5)
