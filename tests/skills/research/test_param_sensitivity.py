from __future__ import annotations

import pytest

from skills.research.param_sensitivity import param_sweep
from tests.fixtures.market_data import make_panel


def test_param_sweep_evaluates_each_parameter(monkeypatch) -> None:
    panel = make_panel(symbols=("AAA", "BBB", "CCC"), periods=8)

    def factor_func(data, window):
        return data["close"].pct_change(window, fill_method=None)

    def fake_full_stat(stat_df, n):
        first_value = stat_df["fac_val"].dropna().iloc[0]
        return (
            {"IC_mean": first_value, "IC_std": 1.0, "IC_IR": first_value, "t_stat": 1.0},
            None,
            None,
            None,
        )

    monkeypatch.setattr("skills.analyze.factor_analysis.full_stat", fake_full_stat)

    result = param_sweep(factor_func, "window", [1, 2], n=1, data=panel)

    assert result["param_value"].tolist() == [1, 2]
    assert set(result.columns) == {"param_value", "IC_mean", "IC_std", "IC_IR", "t_stat"}


def test_param_sweep_requires_explicit_data() -> None:
    def factor_func(data, window):
        return data["close"].pct_change(window, fill_method=None)

    with pytest.raises(ValueError, match="explicit data"):
        param_sweep(factor_func, "window", [1], n=1)
