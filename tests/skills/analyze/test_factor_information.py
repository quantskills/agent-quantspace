from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from skills.analyze.factor_information import (
    ICInformationResult,
    compute_horizon_ic,
    compute_ic_information_surface,
    compute_lagged_ic,
    execution_forward_return_wide,
    mean_daily_factor_rank_correlation,
    rolling_factor_rank_correlation,
    summarize_ic_series,
    top_n_jaccard_overlap,
)


def _prices() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=12)
    return pd.DataFrame({f"s{i}": 100.0 + np.arange(12) * (i + 1) for i in range(6)}, index=dates)


def test_execution_forward_return_uses_both_horizon_and_lag() -> None:
    prices = _prices()
    got = execution_forward_return_wide(prices, horizon=3, lag=2, signal_lag=1)
    expected = prices.shift(-6).div(prices.shift(-3)).sub(1.0)
    pd.testing.assert_frame_equal(got, expected)


def test_information_surface_hac_and_segments() -> None:
    prices = _prices()
    factor = prices.pct_change(2, fill_method=None)
    result = compute_ic_information_surface(
        {"f": factor},
        prices,
        horizons=[1, 3],
        lags=[0, 2],
        segments={"full": (None, None), "late": ("2020-01-05", None)},
    )
    assert isinstance(result, ICInformationResult)
    summary, daily = result.summary, result.daily_ic
    assert len(summary) == 8
    assert set(summary["horizon"]) == {1, 3}
    assert {"hac_t", "hac_se", "ci_low", "ci_high", "effective_dates"}.issubset(summary)
    assert {"factor", "horizon", "lag", "eob", "ic"}.issubset(daily)


def test_horizon_and_lagged_wrappers_match_information_surface() -> None:
    prices = _prices()
    factor = prices.pct_change(2, fill_method=None)
    horizon = compute_horizon_ic({"f": factor}, prices, horizons=[1, 3])
    lagged = compute_lagged_ic({"f": factor}, prices, horizons=[1, 3], lags=[0, 2])
    surface = compute_ic_information_surface(
        {"f": factor}, prices, horizons=[1, 3], lags=[0, 2]
    )
    pd.testing.assert_frame_equal(
        horizon.summary.reset_index(drop=True),
        surface.summary.loc[surface.summary["lag"].eq(0)].reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(lagged.summary, surface.summary)


@pytest.mark.parametrize(
    ("horizons", "lags", "message"),
    [([], [0], "horizons"), ([0], [0], "horizons"), ([1], [], "lags"), ([1], [-1], "lags")],
)
def test_information_surface_rejects_invalid_grid(
    horizons: list[int], lags: list[int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        compute_ic_information_surface({"f": _prices()}, _prices(), horizons=horizons, lags=lags)


def test_hac_summary_uses_requested_lag() -> None:
    ic = pd.Series([0.1, -0.05, 0.2, 0.0, 0.15, -0.02])
    lag_zero = summarize_ic_series(ic, hac_lag=0)
    lag_three = summarize_ic_series(ic, hac_lag=3)
    assert lag_zero["hac_se"] != lag_three["hac_se"]


def test_direction_corrected_correlation_and_top3_overlap() -> None:
    dates = pd.date_range("2020-01-01", periods=5)
    a = pd.DataFrame(np.tile(np.arange(6), (5, 1)), index=dates)
    b = a * 10.0
    c = -a
    corr = mean_daily_factor_rank_correlation({"a": a, "b": b, "c": c})
    overlap = top_n_jaccard_overlap({"a": a, "b": b}, top_n=3)
    assert corr.loc["a", "b"] == 1.0
    assert corr.loc["a", "c"] == -1.0
    assert overlap.loc["a", "b"] == 1.0


def test_rolling_factor_rank_correlation_returns_tidy_pair_history() -> None:
    dates = pd.date_range("2020-01-01", periods=5)
    a = pd.DataFrame(np.tile(np.arange(6), (5, 1)), index=dates)
    b = a * 10.0
    c = -a
    history = rolling_factor_rank_correlation(
        {"a": a, "b": b, "c": c}, window=3, min_periods=2
    )
    assert list(history.columns) == ["factor_a", "factor_b", "eob", "correlation"]
    assert set(zip(history["factor_a"], history["factor_b"])) == {
        ("a", "b"),
        ("a", "c"),
        ("b", "c"),
    }
    latest = history.loc[history["eob"].eq(dates[-1])].set_index(["factor_a", "factor_b"])
    assert latest.loc[("a", "b"), "correlation"] == 1.0
    assert latest.loc[("a", "c"), "correlation"] == -1.0


def test_future_price_mutation_does_not_change_past_ic() -> None:
    prices = _prices()
    factor = prices.pct_change(fill_method=None)
    before = compute_ic_information_surface(
        {"f": factor}, prices, horizons=[1], lags=[0]
    ).daily_ic
    mutated = prices.copy()
    cutoff = dates_cutoff = prices.index[7]
    mutated.loc[mutated.index > cutoff] *= 3.0
    after = compute_ic_information_surface(
        {"f": factor}, mutated, horizons=[1], lags=[0]
    ).daily_ic
    # H=1, signal_lag=1 only uses prices through t+2.
    safe_end = dates_cutoff - pd.Timedelta(days=2)
    left = before.loc[before["eob"] <= safe_end, ["eob", "ic"]].reset_index(drop=True)
    right = after.loc[after["eob"] <= safe_end, ["eob", "ic"]].reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right)
