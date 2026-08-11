from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from skills.compute.features import (
    DEFAULT_LOGDIFF_LAGS,
    default_logdiff_shifts,
    make_logdiff_features,
    make_logdiff_panel_features,
)
from tests.fixtures.market_data import make_ohlcv


def test_make_logdiff_features_default_dimension_and_column_names() -> None:
    bars = make_ohlcv(np.linspace(100.0, 120.0, 80))

    features = make_logdiff_features(bars)

    assert features.shape == (len(bars), 1440)
    assert features.columns.tolist()[0] == "logdiff_open_open1_shift0"
    assert features.columns.tolist()[-1] == "logdiff_low_low25_shift25"
    assert len(features.columns) == len(set(features.columns))


def test_default_logdiff_shifts_matches_reference_lookback_five() -> None:
    assert default_logdiff_shifts(5) == (0, 1, 2, 3, 4, 5, 10, 15, 20, 25)
    assert len(DEFAULT_LOGDIFF_LAGS) == 9
    assert 4 * 4 * len(DEFAULT_LOGDIFF_LAGS) * len(default_logdiff_shifts(5)) == 1440


def test_make_logdiff_features_head_nan_warmup() -> None:
    bars = make_ohlcv(np.linspace(100.0, 130.0, 60))
    features = make_logdiff_features(bars, lags=(1,), shifts=(0, 1, 5))

    assert features.iloc[0].isna().all()
    assert features["logdiff_close_close1_shift0"].iloc[1:].notna().all()
    assert features["logdiff_close_close1_shift1"].iloc[:2].isna().all()
    assert features["logdiff_close_close1_shift1"].iloc[2:].notna().all()
    assert features["logdiff_close_close1_shift5"].iloc[:6].isna().all()
    assert np.isfinite(features.iloc[6]["logdiff_close_close1_shift5"])


def test_make_logdiff_features_has_no_future_leakage() -> None:
    bars = make_ohlcv(np.linspace(100.0, 200.0, 50))
    baseline = make_logdiff_features(
        bars,
        lags=(1, 2),
        shifts=(0, 1),
        lookback=2,
    )

    mutated = bars.copy()
    mutated.loc[mutated.index[-5]:, ["open", "high", "low", "close"]] *= 2.0
    perturbed = make_logdiff_features(
        mutated,
        lags=(1, 2),
        shifts=(0, 1),
        lookback=2,
    )

    cutoff = len(bars) - 5
    pd.testing.assert_frame_equal(
        baseline.iloc[:cutoff],
        perturbed.iloc[:cutoff],
        check_dtype=False,
    )


def test_make_logdiff_features_maps_non_positive_prices_to_nan() -> None:
    bars = make_ohlcv(np.linspace(100.0, 130.0, 30))
    bars.loc[bars.index[10], ["open", "high", "low"]] = 0.0

    features = make_logdiff_features(bars, lags=(1,), shifts=(0,), lookback=1)

    assert np.isfinite(features.to_numpy()[~np.isnan(features.to_numpy())]).all()
    assert features["logdiff_open_open1_shift0"].iloc[10:12].isna().all()
    assert features["logdiff_close_close1_shift0"].iloc[10] == pytest.approx(
        np.log(bars["close"].iloc[10]) - np.log(bars["close"].iloc[9])
    )


def test_make_logdiff_panel_features_returns_clean_symbol_panel() -> None:
    frames = []
    for symbol, base in (("SHSE.510300", 100.0), ("SZSE.159915", 50.0)):
        bars = make_ohlcv(np.linspace(base, base * 1.3, 90))
        bars.loc[bars.index[80], ["open", "high", "low"]] = 0.0
        bars["symbol"] = symbol
        frames.append(bars.reset_index().set_index(["symbol", "eob"]))
    panel = pd.concat(frames).sort_index()

    features = make_logdiff_panel_features(panel, lags=(1, 2), shifts=(0, 1), lookback=2)

    assert features.index.names == ["symbol", "eob"]
    assert features.notna().all().all()
    assert np.isfinite(features.to_numpy()).all()
    assert features.index.is_monotonic_increasing
    assert set(features.index.get_level_values("symbol")) == {"SHSE.510300", "SZSE.159915"}
    dropped = panel.index.difference(features.index)
    assert len(dropped) > 0


def test_make_logdiff_panel_features_rejects_empty_panel() -> None:
    empty = pd.DataFrame(
        {column: [] for column in ["open", "high", "low", "close", "volume"]},
        index=pd.MultiIndex.from_arrays(
            [[], pd.DatetimeIndex([])],
            names=["symbol", "eob"],
        ),
    )

    with pytest.raises(ValueError, match="panel cannot be empty"):
        make_logdiff_panel_features(empty)


def test_make_logdiff_features_rejects_invalid_inputs() -> None:
    bars = make_ohlcv(np.linspace(100.0, 110.0, 10))

    with pytest.raises(ValueError, match="lookback must be positive"):
        make_logdiff_features(bars, lookback=0)

    with pytest.raises(ValueError, match="missing OHLC columns"):
        make_logdiff_features(bars.drop(columns=["open"]))
