from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]


def _sample_group() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=8, freq="D", name="eob")
    close = pd.Series([10.0, 10.5, 11.0, 10.8, 11.3, 11.9, 12.2, 12.6], index=index)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": np.arange(1_000, 1_008),
        },
        index=index,
    )


def _sample_panel() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=8, freq="D", name="eob")
    frames = []
    for symbol, base in [("AAA", 10.0), ("BBB", 20.0)]:
        close = pd.Series(base + np.arange(len(dates)) * (0.4 if symbol == "AAA" else -0.1), index=dates)
        frame = pd.DataFrame(
            {
                "open": close.shift(1).fillna(close.iloc[0]),
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": np.arange(1_000, 1_000 + len(dates)),
            }
        )
        frame["symbol"] = symbol
        frames.append(frame.reset_index())
    return pd.concat(frames).set_index(["symbol", "eob"]).sort_index()


def test_legacy_research_factor_libraries_are_not_shipped() -> None:
    old_cs_file = "j" + "q_etf_cs_library.py"
    old_ts_file = "j" + "q_ts_library.py"

    assert not (ROOT / "skills/compute" / old_cs_file).exists()
    assert not (ROOT / "skills/compute" / old_ts_file).exists()


def test_generic_time_series_factor_examples_export_small_public_api() -> None:
    module = importlib.import_module("skills.compute.ts_factor_examples")

    assert set(module.__all__) == {
        "ts_momentum",
        "ts_volatility",
        "ts_trend_slope",
        "ts_mean_reversion_zscore",
    }

    group = _sample_group()
    for name in module.__all__:
        result = getattr(module, name)(group, lookback=3)
        assert isinstance(result, pd.Series)
        assert result.index.equals(group.index)
        assert result.iloc[:2].isna().all()


def test_generic_cross_sectional_factor_examples_export_small_public_api() -> None:
    module = importlib.import_module("skills.compute.cs_factor_examples")

    assert set(module.__all__) == {
        "cs_momentum_score",
        "cs_volatility_score",
        "cs_trend_score",
        "cs_mean_reversion_score",
    }

    panel = _sample_panel()
    for name in module.__all__:
        result = getattr(module, name)(panel, lookback=3)
        assert isinstance(result, pd.Series)
        assert result.index.equals(panel.index)
        assert result.groupby(level="symbol").head(2).isna().all()
