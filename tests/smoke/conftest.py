"""Session fixtures: a trimmed copy of the real local data and the shared command chain.

Each fixture runs real ``qs`` commands once against the copy and hands the result to the
tests that check it, so a single test can run alone. Nothing here writes to the source
data root.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from tests.smoke.runner import (
    ADJUSTED_SYMBOLS,
    INDEX_SYMBOL,
    SYMBOLS,
    Work,
    artifact_paths,
    copy_trimmed,
    make_work,
    qs,
    required_files,
    snapshot,
)

FACTORS = {"mom": ("roc", 10), "rev": ("roc", 3), "rsi": ("rsi", 14)}
DIRECTIONS = {"mom": 1, "rev": -1, "rsi": -1}
HORIZONS = (1, 5, 10)
COMBINE_HORIZON = 5
SIGNAL_LAG = 1


@pytest.fixture(scope="session")
def source_root():
    from skills.store.workspace import resolve_workspace_paths

    root = resolve_workspace_paths().data_root
    missing = [str(path) for path in required_files(root) if not path.is_file()]
    if missing:
        pytest.skip(f"required local data files are missing: {missing}")
    return root


@pytest.fixture(scope="session")
def source_snapshot(source_root):
    return snapshot(source_root)


@pytest.fixture(scope="session")
def work(tmp_path_factory, source_root, source_snapshot) -> Work:
    base = tmp_path_factory.mktemp("smoke")
    data_root = base / "data"
    copy_trimmed(source_root, data_root)
    yield make_work(base, data_root)
    assert snapshot(source_root) == source_snapshot, "the source data root was modified"


@pytest.fixture(scope="session")
def panel(work):
    envelope = qs(
        work, "store", "read", "--symbols", ",".join(SYMBOLS), "--output", "panel.parquet",
        "--preview", "0",
    )  # fmt: skip
    return {"envelope": envelope, "path": artifact_paths(envelope)["panel"]}


@pytest.fixture(scope="session")
def factors(work, panel):
    paths, envelopes = {}, {}
    for name, (indicator, period) in FACTORS.items():
        envelopes[name] = qs(
            work, "compute", "factor", "--panel", str(panel["path"]), "--indicator", indicator,
            "-p", f"period={period}", "--layout", "wide", "--output", f"{name}.parquet",
        )  # fmt: skip
        paths[name] = artifact_paths(envelopes[name])["factor"]
    return {"paths": paths, "envelopes": envelopes}


def _factor_args(factors):
    return [
        item for name, path in factors["paths"].items() for item in ("--factors", f"{name}={path}")
    ]


@pytest.fixture(scope="session")
def surface(work, panel, factors):
    envelope = qs(
        work, "analyze", "ic-surface", "--panel", str(panel["path"]), *_factor_args(factors),
        "--directions", json.dumps(DIRECTIONS), "--horizons", ",".join(map(str, HORIZONS)),
        "--lags", "0,1,2", "--signal-lag", str(SIGNAL_LAG), "--out-dir", "surface", "--preview", "0",
    )  # fmt: skip
    return {"envelope": envelope, "paths": artifact_paths(envelope)}


@pytest.fixture(scope="session")
def correlation(work, factors):
    envelope = qs(
        work, "analyze", "factor-correlation", *_factor_args(factors),
        "--directions", json.dumps(DIRECTIONS), "--window", "60", "--min-periods", "30",
        "--top-n", "3", "--out-dir", "correlation",
    )  # fmt: skip
    return {"envelope": envelope, "paths": artifact_paths(envelope)}


@pytest.fixture(scope="session")
def combined(work, factors, surface, correlation):
    """Lesson-06 dynamic weights: oriented IC + oriented rank correlations -> combine."""
    envelope = qs(
        work, "strategy", "combine", *_factor_args(factors),
        "--directions", json.dumps(DIRECTIONS), "--method", "max_ic", "--top-n", "3",
        "--ic-history", str(surface["paths"]["daily_ic"]), "--ic-horizon", str(COMBINE_HORIZON),
        "--correlation-history", str(correlation["paths"]["correlation_history"]),
        "--availability-delay", str(SIGNAL_LAG + COMBINE_HORIZON), "--lookback", "60",
        "--min-periods", "30", "--max-weight", "0.6", "--out-dir", "combined", "--preview", "0",
    )  # fmt: skip
    return {"envelope": envelope, "paths": artifact_paths(envelope)}


@pytest.fixture(scope="session")
def targets(work, factors):
    envelope = qs(
        work, "strategy", "top-n", "--scores", str(factors["paths"]["mom"]), "--top-n", "3",
        "--output", "targets.parquet", "--preview", "0",
    )  # fmt: skip
    return {"envelope": envelope, "path": artifact_paths(envelope)["weights"]}


@pytest.fixture(scope="session")
def backtest_run(work, panel, targets):
    envelope = qs(
        work, "backtest", "run", "--panel", str(panel["path"]), "--weights", str(targets["path"]),
        "--commission", "0.0002", "--slippage-bp", "1", "--out-dir", "run", "--preview", "0",
    )  # fmt: skip
    return {"envelope": envelope, "paths": artifact_paths(envelope)}


@pytest.fixture(scope="session")
def combined_run(work, panel, combined):
    envelope = qs(
        work, "backtest", "run", "--panel", str(panel["path"]),
        "--weights", str(combined["paths"]["target_weights"]), "--commission", "0.0002",
        "--slippage-bp", "1", "--out-dir", "combined_run", "--preview", "0",
    )  # fmt: skip
    return {"envelope": envelope, "paths": artifact_paths(envelope)}


@pytest.fixture(scope="session")
def candidates(work, backtest_run, combined_run):
    """Daily returns of the two real backtests side by side."""
    frame = pd.DataFrame(
        {
            "mom_top3": pd.read_parquet(backtest_run["paths"]["result_df"])["return"],
            "combined_top3": pd.read_parquet(combined_run["paths"]["result_df"])["return"],
        }
    ).dropna()
    path = work.dir / "candidates.parquet"
    frame.to_parquet(path)
    return path


@pytest.fixture(scope="session")
def index_close(work):
    """Benchmark close of the real index, one value column."""
    path = work.dir / "index_close.parquet"
    close = pd.read_parquet(work.data_root / "market" / "1d" / f"{INDEX_SYMBOL}.parquet")[["close"]]
    close.to_parquet(path)
    return path


@pytest.fixture(scope="session")
def single_bars(work):
    """One real symbol's bars (eob index) as the label commands expect."""
    return work.data_root / "market" / "1d" / "SHSE.510300.parquet"


@pytest.fixture(scope="session")
def adjusted_symbols():
    return ADJUSTED_SYMBOLS
