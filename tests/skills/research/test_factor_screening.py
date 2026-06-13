from __future__ import annotations

import pandas as pd

from skills.research.factor_screening import _build_stat_df, screen_all_indicators
from tests.fixtures.market_data import make_panel


def test_build_stat_df_matches_factor_analysis_shape() -> None:
    panel = make_panel(symbols=("AAA", "BBB"), periods=4)
    factor = panel["close"].pct_change(fill_method=None)

    stat_df = _build_stat_df(panel["close"], factor)

    assert stat_df.index.names == ["eob", "symbol"]
    assert list(stat_df.columns) == ["close", "fac_val"]


def test_screen_all_indicators_ranks_by_absolute_ic_ir(monkeypatch) -> None:
    panel = make_panel(symbols=("AAA", "BBB", "CCC"), periods=8)

    def fake_discover_indicators():
        return {
            "weak": lambda group: group["close"].pct_change(fill_method=None),
            "strong": lambda group: group["close"].pct_change(2, fill_method=None),
        }

    def fake_full_stat(stat_df, n, g, plot=False):
        value = -5.0 if stat_df["fac_val"].notna().sum() <= 18 else 2.0
        return (
            {"IC_IR": value, "IC_mean": value / 10, "IC_std": 1.0},
            pd.Series([value]),
            pd.DataFrame({"low": [0.0], "high": [0.01]}),
            pd.DataFrame({"turnover": [0.2]}),
        )

    monkeypatch.setattr("skills.compute.indicators.discover_indicators", fake_discover_indicators)
    monkeypatch.setattr("skills.analyze.factor_analysis.full_stat", fake_full_stat)

    ranking = screen_all_indicators(
        pool="demo",
        n=1,
        g=2,
        top_k=1,
        persist=False,
        data=panel,
    )

    assert ranking.loc[0, "indicator"] == "strong"
    assert ranking.loc[0, "IC_IR"] == -5.0
