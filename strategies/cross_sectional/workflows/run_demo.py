"""Run the public cross-sectional rotation demo."""

from __future__ import annotations

from collections.abc import Sequence

from skills.store.data_manager import DataManager
from skills.strategy.cross_sectional import ModularBacktester
from strategies.cross_sectional.factors import momentum_score, volatility_score

DEFAULT_SYMBOLS = ("SHSE.510300", "SHSE.510500", "SZSE.159915", "SHSE.513100")


def load_panel(
    symbols: Sequence[str] = DEFAULT_SYMBOLS,
    *,
    frequency: str = "1d",
):
    """Load the demo's explicit symbols as a standard market panel."""
    data_manager = DataManager()
    return data_manager.read_symbols(list(symbols), frequency=frequency)


def main() -> None:
    """Build target weights and execute them through ``VectorBacktester``."""
    panel = load_panel()
    factor_configs = [
        {
            "func": momentum_score,
            "kwargs": {"lookback": 20},
            "name": "momentum",
            "direction": 1,
        },
        {
            "func": volatility_score,
            "kwargs": {"lookback": 20},
            "name": "low_vol",
            "direction": 1,
        },
    ]
    backtester = ModularBacktester(
        data=panel,
        factor_configs=factor_configs,
        top_pct=0.5,
        commission=0.0002,
        slippage_bp=2.0,
        rebalance_freq=5,
    )
    backtester.run()
    print("Cross-sectional demo metrics:")
    for key, value in backtester.metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
