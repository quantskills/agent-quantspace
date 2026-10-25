"""A store -> factor -> targets -> backtest -> perf chain through the installed qs script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests.fixtures.market_data import make_ohlcv, write_symbol_parquet

SYMBOLS = ["SHSE.510300", "SHSE.510500", "SHSE.512100", "SZSE.159915"]


def qs(cwd: Path, *args: str) -> dict:
    script = Path(sys.executable).with_name("qs")
    if not script.exists():
        pytest.skip("qs console script is not installed in this environment")
    completed = subprocess.run(
        [str(script), *args], cwd=cwd, capture_output=True, text=True, timeout=180
    )
    assert completed.stdout.count("\n") == 1, completed.stdout
    envelope = json.loads(completed.stdout)
    assert completed.returncode == 0 and envelope["ok"], (envelope, completed.stderr[-2000:])
    return envelope


def test_cli_chain_equals_the_python_api(tmp_path):
    from skills.analyze.attribution_counterfactual import performance_metrics
    from skills.backtest import VectorBacktester
    from skills.compute.indicators import discover_indicators
    from skills.compute.wrappers import Factor
    from skills.store.data_manager import DataManager
    from skills.strategy.cross_sectional import top_n_weights

    root = tmp_path / "data"
    for index, symbol in enumerate(SYMBOLS):
        rng = np.random.default_rng(42 + index)
        write_symbol_parquet(
            root, symbol, make_ohlcv(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, 200))))
        )
    work = tmp_path / "work"
    work.mkdir()

    qs(
        work,
        "store",
        "read",
        "--symbols",
        ",".join(SYMBOLS),
        "--data-root",
        str(root),
        "--output",
        "panel.parquet",
    )
    factor = qs(
        work,
        "compute",
        "factor",
        "--panel",
        "panel.parquet",
        "--indicator",
        "roc",
        "-p",
        "period=10",
        "--layout",
        "wide",
        "--output",
        "mom.parquet",
    )
    qs(
        work,
        "strategy",
        "top-n",
        "--scores",
        "mom.parquet",
        "--top-n",
        "2",
        "--output",
        "targets.parquet",
    )
    run = qs(
        work,
        "backtest",
        "run",
        "--panel",
        "panel.parquet",
        "--weights",
        "targets.parquet",
        "--commission",
        "0.0002",
        "--slippage-bp",
        "1",
        "--out-dir",
        "run",
    )
    perf = qs(work, "analyze", "perf", "--returns", "run/result.parquet")
    # The commands only read the store, so it gains no folders.
    assert sorted(path.name for path in root.iterdir()) == ["market"]

    panel = DataManager(data_root=str(root)).read_symbols(SYMBOLS, frequency="1d")
    wrapper = Factor(discover_indicators()["roc"], period=10)
    scores = wrapper.calculate(panel, dropna=True).rename("value").unstack("symbol").sort_index()
    targets = top_n_weights(scores, top_n=2)
    expected = VectorBacktester(data=panel, commission=0.0002, slippage_bp=1.0).run(targets)

    assert factor["data"]["name"] == wrapper.name
    pd.testing.assert_frame_equal(
        pd.read_parquet(work / "run" / "result.parquet"), expected.result_df
    )
    assert run["data"]["metrics"] == pytest.approx(expected.metrics)
    assert perf["data"]["metrics"] == pytest.approx(
        performance_metrics(expected.result_df["return"])
    )
