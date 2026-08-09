from __future__ import annotations

import numpy as np
import pandas as pd

from skills.analyze.factor_information import (
    compute_horizon_ic,
    rolling_factor_rank_correlation,
)
from skills.backtest import VectorBacktester
from skills.strategy.cross_sectional import (
    DynamicFactorWeightConfig,
    apply_rebalance_schedule,
    combine_factor_scores,
    rank_factor_frames,
)


def _market() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range("2022-01-03", periods=180, name="eob")
    symbols = [f"TEST.S{i}" for i in range(6)]
    x = np.arange(len(dates), dtype=float)
    prices = pd.DataFrame(
        {
            symbol: 100.0
            * np.exp(0.0005 * (i + 1) * x + 0.02 * np.sin(x / (7.0 + i)))
            for i, symbol in enumerate(symbols)
        },
        index=dates,
    )
    panel = pd.concat(
        {
            symbol: pd.DataFrame(
                {
                    "open": prices[symbol],
                    "high": prices[symbol] * 1.01,
                    "low": prices[symbol] * 0.99,
                    "close": prices[symbol],
                    "volume": 1_000_000.0,
                },
                index=dates,
            )
            for symbol in symbols
        },
        names=["symbol", "eob"],
    )
    return prices, panel


def test_multifactor_information_to_costed_backtest_pipeline() -> None:
    prices, panel = _market()
    factors = {
        "mom5": prices.pct_change(5, fill_method=None),
        "mom10": prices.pct_change(10, fill_method=None),
        "reversal3": -prices.pct_change(3, fill_method=None),
    }
    ranked = rank_factor_frames(factors)
    information = compute_horizon_ic(
        factors, prices, horizons=[5], signal_lag=1, min_cross_section=6
    )
    ic_history = information.daily_ic.pivot(
        index="eob", columns="factor", values="ic"
    ).reindex(prices.index)
    correlations = rolling_factor_rank_correlation(ranked, window=20, min_periods=10)
    config = DynamicFactorWeightConfig(
        availability_delay=6,
        lookback=20,
        min_periods=10,
        max_weight=0.5,
        correlation_shrinkage=0.5,
    )

    for method in ["equal_rank", "equal_vote", "rolling_ic", "rolling_icir", "max_icir"]:
        kwargs = {}
        if method not in {"equal_rank", "equal_vote"}:
            kwargs = {"ic_history": ic_history, "dynamic_config": config}
        if method == "max_icir":
            kwargs["correlation_history"] = correlations
        combination = combine_factor_scores(ranked, method=method, top_n=3, **kwargs)
        targets = apply_rebalance_schedule(
            combination.target_weights, every=5, start=prices.index[30]
        )
        result = VectorBacktester(
            panel,
            trade_at="close",
            signal_lag=1,
            commission=0.0002,
            slippage_bp=3.0,
        ).run(targets)
        assert not result.result_df.empty
        assert np.isfinite(result.result_df["equity"]).all()
        assert combination.factor_weights.sum(axis=1).eq(1.0).all()
