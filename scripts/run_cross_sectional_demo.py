"""Run the public cross-sectional rotation demo."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills.store.data_manager import DataManager  # noqa: E402
from strategies.cross_sectional.factors import momentum_score, volatility_score  # noqa: E402
from strategies.cross_sectional.modular_backtester import ModularBacktester  # noqa: E402

DEFAULT_POOL_ID = "sample_etf_rotation"


def _load_panel(pool_id: str = DEFAULT_POOL_ID):
    dm = DataManager()
    coverage = dm.check_pool_coverage(pool_id)
    missing = coverage.loc[coverage["status"] != "OK", "symbol"].tolist()
    if missing:
        raise FileNotFoundError(
            f"Missing daily Parquet files under {dm.root / 'market' / '1d'} for symbols: {missing}"
        )
    return dm.load_pool_data(pool_id)


def main() -> None:
    panel = _load_panel()
    factor_configs = [
        {"func": momentum_score, "kwargs": {"lookback": 20}, "name": "momentum", "direction": 1},
        {"func": volatility_score, "kwargs": {"lookback": 20}, "name": "low_vol", "direction": 1},
    ]
    bt = ModularBacktester(
        data=panel,
        factor_configs=factor_configs,
        top_pct=0.5,
        commission=0.0002,
        slippage_bp=2.0,
        rebalance_freq=5,
    )
    bt.run()
    print("Cross-sectional demo metrics:")
    for key, value in bt.metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
