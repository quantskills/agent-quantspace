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


SMOKE_SKIP_REASON = (
    "smoke tests are opt-in: run `uv run python -m pytest -m smoke` "
    "(needs the real local data under data/market; it is only read, never written)"
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip smoke tests unless the user's -m expression mentions them.

    A hook rather than ``addopts = -m "not smoke"``: any user-supplied ``-m`` (for example
    ``-m "not policy"``) replaces addopts and would silently turn the smoke tests on.
    """
    if "smoke" in (config.getoption("markexpr") or ""):
        return
    skip = pytest.mark.skip(reason=SMOKE_SKIP_REASON)
    for item in items:
        if item.get_closest_marker("smoke") is not None:
            item.add_marker(skip)
