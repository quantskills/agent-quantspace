from __future__ import annotations

import pandas as pd
import pytest

from skills.analyze.factor_analysis import (
    filter_extreme_MAD,
    get_Performance_analysis,
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
