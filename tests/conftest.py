from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

matplotlib.use("Agg", force=True)


@pytest.fixture(scope="session")
def strategy_report_data_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from scripts.run_strategy_reports import (
        CSI300_FUTURE_SYMBOL,
        GOLD_FUTURE_SYMBOL,
        ML_FUTURE_SYMBOLS,
        RULE_FUTURE_SYMBOLS,
    )
    from tests.fixtures.market_data import write_strategy_report_data

    root = tmp_path_factory.mktemp("strategy-report-data")
    symbols = [
        *RULE_FUTURE_SYMBOLS,
        *ML_FUTURE_SYMBOLS,
        CSI300_FUTURE_SYMBOL,
        GOLD_FUTURE_SYMBOL,
    ]
    return write_strategy_report_data(root, symbols)
