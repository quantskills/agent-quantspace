from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pandas as pd
import pytest

from skills.strategy import (
    MarketDataReader,
    StrategyContext,
    StrategyResult,
    WeightGenerator,
)


def test_strategy_context_stores_run_identity_and_is_frozen() -> None:
    context = StrategyContext(
        strategy_id="public_time_series",
        run_id="run-001",
        variant_id="rule-ma-atr",
        domain="time_series",
    )

    assert context.strategy_id == "public_time_series"
    assert context.variant_id == "rule-ma-atr"
    with pytest.raises(FrozenInstanceError):
        context.run_id = "changed"  # type: ignore[misc]


def test_weight_generator_returns_target_weights_and_diagnostics() -> None:
    weights = pd.DataFrame(
        {"SHSE.510300": [1.0]},
        index=pd.DatetimeIndex(["2026-01-02"], name="eob"),
    )

    class FixedGenerator:
        def generate_weights(
            self,
            data: Any,
            context: StrategyContext,
        ) -> StrategyResult:
            return StrategyResult(
                target_weights=weights,
                diagnostics={"strategy_id": context.strategy_id},
            )

    generator: WeightGenerator = FixedGenerator()
    result = generator.generate_weights(
        data={},
        context=StrategyContext(
            strategy_id="public_time_series",
            run_id="run-001",
            variant_id=None,
            domain="time_series",
        ),
    )

    pd.testing.assert_frame_equal(result.target_weights, weights)
    assert result.diagnostics == {"strategy_id": "public_time_series"}


def test_market_data_reader_port_matches_current_read_symbols_shape() -> None:
    class MemoryReader:
        def read_symbols(self, symbols: list[str], frequency: str = "1d") -> pd.DataFrame:
            index = pd.MultiIndex.from_product(
                [symbols, pd.to_datetime(["2026-01-02"])],
                names=["symbol", "eob"],
            )
            return pd.DataFrame({"close": 1.0}, index=index)

    reader: MarketDataReader = MemoryReader()
    panel = reader.read_symbols(["SHSE.510300"])

    assert panel.index.names == ["symbol", "eob"]
