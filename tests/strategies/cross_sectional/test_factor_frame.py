from __future__ import annotations

from strategies.cross_sectional.factor_frame import FactorFrameBuilder
from strategies.cross_sectional.factors import momentum_score
from tests.fixtures.market_data import make_panel


def test_factor_frame_builder_adds_long_and_wide_outputs() -> None:
    panel = make_panel(symbols=("AAA", "BBB"), periods=6)

    result = FactorFrameBuilder(
        panel,
        [{"func": momentum_score, "kwargs": {"lookback": 2}, "name": "mom"}],
    ).build()

    assert "factor__mom" in result.factor_df.columns
    assert list(result.factor_pivots) == ["mom"]
    assert result.factor_pivots["mom"].columns.tolist() == ["AAA", "BBB"]
    assert result.factor_df.index.equals(panel.index)
