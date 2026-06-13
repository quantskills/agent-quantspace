from __future__ import annotations

import pandas as pd
import pytest

from skills.construct.combiner import StrategyCombiner


def test_strategy_combiner_equal_method_averages_returns() -> None:
    idx = pd.date_range("2024-01-01", periods=3)
    combiner = StrategyCombiner(
        {"a": pd.Series([0.01, 0.02, 0.03], index=idx), "b": pd.Series([0.03, 0.02, 0.01], index=idx)},
        method="equal",
    )

    result = combiner.run()

    assert result["combined_return"].tolist() == pytest.approx([0.02, 0.02, 0.02])
    assert combiner.metrics["weights"] == {"a": 0.5, "b": 0.5}


def test_strategy_combiner_custom_weights_are_normalized() -> None:
    idx = pd.date_range("2024-01-01", periods=2)
    combiner = StrategyCombiner(
        {"a": pd.Series([0.10, 0.10], index=idx), "b": pd.Series([0.0, 0.0], index=idx)},
        method="custom",
        custom_weights={"a": 3.0, "b": 1.0},
    )

    result = combiner.run()

    assert result["combined_return"].tolist() == pytest.approx([0.075, 0.075])
