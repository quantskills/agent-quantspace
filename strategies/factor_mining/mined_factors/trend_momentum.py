"""Trend/momentum factor candidates for the governed mining workflow."""

from __future__ import annotations

import pandas as pd

from skills.compute.indicators import roc


def roc_close(group: pd.DataFrame, period: int = 20) -> pd.Series:
    """Rate of change of one symbol's close over ``period`` bars."""
    return roc(group, period=period).astype("float64")


CANDIDATES = (
    {
        "factor_id": "etf18-roc-20",
        "family": "trend_momentum",
        "hypothesis": (
            "ETFs with the higher 20-day close return keep outperforming over the next 20 bars."
        ),
        "expected_direction": "long_high",
        "required_fields": ("close",),
        "module": "strategies.factor_mining.mined_factors.trend_momentum",
        "name": "roc_close",
        "params": {"period": 20},
        "window": 20,
        "lag": 0,
        "warmup": 20,
        "missing_policy": "keep_nan",
        "availability_rule": "Only bars through close[t]; missing values stay NaN.",
        "output_dtype": "float64",
        "index_restore_policy": "restore_original_names_and_order",
        "applicable_regimes": ("trend",),
        "known_relations": (),
        "falsification_tests": (
            "Train and validation Rank-IC must have the same sign.",
            "Prefix recompute must reproduce values without future bars.",
        ),
    },
)
