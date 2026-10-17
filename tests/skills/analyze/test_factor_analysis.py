from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from skills.analyze.factor_analysis import (
    filter_extreme_MAD,
    get_Performance_analysis,
    group_stat,
    maxdrawdown,
    winsorize_percentile,
    winsorize_std,
)


def test_maxdrawdown_returns_peak_to_trough_loss() -> None:
    nav = pd.Series([1.0, 1.2, 0.9, 1.1])

    assert maxdrawdown(nav) == pytest.approx(0.25)


def test_performance_analysis_reports_expected_terminal_nav() -> None:
    nav = pd.Series(
        [1.0, 1.1, 1.2, 1.1, 1.25, 1.3],
        index=pd.date_range("2024-01-01", periods=6),
    )

    result = get_Performance_analysis(nav, year_day=252)

    assert result[0] == pytest.approx(1.3)
    assert result[2] > 0.0
    assert result[5] > 0.0


def test_winsorization_helpers_clip_outliers() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 100.0])

    assert filter_extreme_MAD(values, n=1).max() < 100.0
    assert winsorize_std(values, n=1).max() < 100.0
    assert winsorize_percentile(values, left=0.25, right=0.75).max() == pytest.approx(27.25)


def _noise_panel(n_days: int = 120, n_symbols: int = 50, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    symbols = [f"SHSE.{600000 + i}" for i in range(n_symbols)]
    close = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0, 0.01, (n_days, n_symbols)), axis=0),
        index=dates,
        columns=symbols,
    )
    factor = pd.DataFrame(rng.normal(size=(n_days, n_symbols)), index=dates, columns=symbols)
    panel = pd.concat(
        [close.stack().rename("close"), factor.stack().rename("fac_val")], axis=1
    )
    panel.index.names = ["eob", "symbol"]
    return panel


def test_group_stat_returns_are_daily_regardless_of_rebalance_period() -> None:
    panel = _noise_panel()
    daily = panel["close"].unstack("symbol").pct_change().shift(-1)

    group_return, _ = group_stat(panel, n=5, g=5)

    # Each row is a one-day return: equal-weight mean of all groups (equal sized)
    # must equal the cross-sectional mean of that day's one-day forward return.
    benchmark = group_return.mean(axis=1)
    expected = daily.mean(axis=1).reindex(benchmark.index)
    pd.testing.assert_series_equal(benchmark, expected, check_names=False, check_freq=False)


def test_group_stat_benchmark_nav_does_not_inflate_with_rebalance_period() -> None:
    panel = _noise_panel()

    navs = {}
    for n in (1, 5, 20):
        group_return, _ = group_stat(panel, n=n, g=5)
        navs[n] = (1 + group_return.mean(axis=1)).prod()

    # Same universe, same daily returns -> equal-weight benchmark NAV is (almost)
    # independent of n; only the dropped tail rows differ.
    assert navs[5] == pytest.approx(navs[1], rel=0.02)
    assert navs[20] == pytest.approx(navs[1], rel=0.02)
