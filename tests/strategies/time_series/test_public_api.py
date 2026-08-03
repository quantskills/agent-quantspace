from __future__ import annotations

import subprocess
import sys

import strategies.time_series as time_series


def test_domain_package_does_not_reexport_strategy_type_or_concrete_ml_symbols() -> None:
    for name in [
        "SignalEngine",
        "TimeSeriesBacktester",
        "TimeSeriesConfig",
        "xgboost_triple_barrier_weights",
    ]:
        assert not hasattr(time_series, name)


def test_domain_package_import_does_not_eagerly_load_xgboost() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import strategies.time_series; "
            "raise SystemExit(int('xgboost' in sys.modules))",
        ],
        check=False,
    )

    assert completed.returncode == 0
