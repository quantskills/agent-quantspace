from __future__ import annotations

import pandas as pd

from strategies.time_series.workflows.run_cashflow_split_2014_2023 import (
    family_config_counts,
    rank_in_sample,
)


def test_family_config_counts_cover_prior_strategy_searches() -> None:
    counts = family_config_counts()

    assert counts == {
        "mean_reversion": 1944,
        "donchian_atr_core": 360,
        "vol_recovery_stage1": 594,
        "trend_breakout": 13,
    }


def test_in_sample_ranking_rewards_fold_stability() -> None:
    frame = pd.DataFrame(
        [
            {
                "candidate": "unstable",
                "max_drawdown": 0.10,
                "trade_days": 10.0,
                "total_return": 2.0,
                "calmar_ratio": 3.0,
                "sharpe_ratio": 2.0,
                "median_fold_excess": 0.10,
                "worst_fold_excess": -0.50,
            },
            {
                "candidate": "stable",
                "max_drawdown": 0.12,
                "trade_days": 10.0,
                "total_return": 1.5,
                "calmar_ratio": 2.5,
                "sharpe_ratio": 1.8,
                "median_fold_excess": 0.30,
                "worst_fold_excess": 0.05,
            },
        ]
    )

    ranked = rank_in_sample(frame)

    assert ranked.iloc[0]["candidate"] == "stable"

