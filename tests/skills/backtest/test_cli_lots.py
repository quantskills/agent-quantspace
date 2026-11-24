"""``qs backtest run --unit lots``: the same result as ``VectorBacktester(unit="lots")``."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from skills.backtest import VectorBacktester
from skills.store.data_manager import DataManager

DAYS = pd.to_datetime(["2025-08-27", "2025-08-28", "2025-08-29", "2025-09-01", "2025-09-02"])


def invoke(capsys, *args):
    from skills.cli import main

    code = main(list(args))
    return code, json.loads(capsys.readouterr().out)


def bars(values) -> pd.DataFrame:
    close = pd.Series(values, index=pd.DatetimeIndex(DAYS, name="eob"), dtype=float)
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1.0})


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "data"
    dm = DataManager(str(root))
    dm.save_symbol("RB_DOMINANT.SHF", bars([3000, 3010, 3120, 3130, 3125]))
    dm.save_symbol("RB2510.SHF", bars([3000, 3010, 3020, np.nan, np.nan]))
    dm.save_symbol("RB2601.SHF", bars([3090, 3100, 3120, 3130, 3125]))
    dm.save_dominant(
        "RB_DOMINANT.SHF",
        pd.Series(["RB2510.SHF"] * 2 + ["RB2601.SHF"] * 3, index=DAYS),
    )
    weights = pd.DataFrame({"RB_DOMINANT.SHF": [2, 2, 2, 2, 2]}, index=DAYS)
    weights.index.name = "eob"
    weights.to_parquet(tmp_path / "lots.parquet")
    (tmp_path / "multipliers.json").write_text('{"RB_DOMINANT.SHF": 10}')
    return root


def test_lots_run_loads_the_stored_contracts_and_matches_the_api(store, tmp_path, capsys):
    out = tmp_path / "out"
    code, response = invoke(
        capsys,
        "backtest",
        "run",
        "--symbols",
        "RB_DOMINANT.SHF",
        "--data-root",
        str(store),
        "--weights",
        str(tmp_path / "lots.parquet"),
        "--commission",
        "0.0001",
        "--slippage-bp",
        "0",
        "--signal-lag",
        "0",
        "--unit",
        "lots",
        "--capital",
        "100000",
        "--multipliers",
        str(tmp_path / "multipliers.json"),
        "--out-dir",
        str(out),
    )
    assert code == 0, response
    dm = DataManager(str(store))
    expected = VectorBacktester(
        dm.read_symbols(["RB_DOMINANT.SHF", "RB2510.SHF", "RB2601.SHF"]),
        signal_lag=0,
        commission=0.0001,
        slippage_bp=0.0,
        unit="lots",
        capital=100_000,
        multipliers={"RB_DOMINANT.SHF": 10},
        contracts=dm.read_dominant(["RB_DOMINANT.SHF"]),
    ).run(pd.read_parquet(tmp_path / "lots.parquet"))
    assert response["data"]["metrics"]["total_pnl"] == pytest.approx(500.0)
    assert response["data"]["metrics"] == pytest.approx(expected.metrics)
    stored = pd.read_parquet(out / "executed_lots.parquet")
    pd.testing.assert_frame_equal(stored, expected.executed_lots, check_freq=False)


def test_lots_options_need_the_lots_unit(store, tmp_path, capsys):
    code, response = invoke(
        capsys,
        "backtest",
        "run",
        "--symbols",
        "RB_DOMINANT.SHF",
        "--data-root",
        str(store),
        "--weights",
        str(tmp_path / "lots.parquet"),
        "--commission",
        "0",
        "--slippage-bp",
        "0",
        "--capital",
        "100000",
    )
    assert code != 0 and "only apply to --unit lots" in json.dumps(response)
    code, response = invoke(
        capsys,
        "backtest",
        "run",
        "--symbols",
        "RB_DOMINANT.SHF",
        "--data-root",
        str(store),
        "--weights",
        str(tmp_path / "lots.parquet"),
        "--commission",
        "0",
        "--slippage-bp",
        "0",
        "--unit",
        "lots",
    )
    assert code != 0 and "--capital" in json.dumps(response)
