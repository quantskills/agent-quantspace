from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from scripts.generate_sample_data import generate_sample_data

ROOT = Path(__file__).resolve().parents[2]


def _run_module(module: str, data_root) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "QUANTSPACE_DATA_ROOT": str(data_root)}
    return subprocess.run(
        [sys.executable, "-m", module],
        check=True,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )


def test_public_demo_scripts_run_against_sample_data(tmp_path) -> None:
    data_root = generate_sample_data(tmp_path)

    cross_sectional = _run_module("strategies.cross_sectional.workflows.run_demo", data_root)
    time_series = _run_module("strategies.time_series.workflows.run_demo", data_root)

    assert "Cross-sectional demo metrics:" in cross_sectional.stdout
    assert "Time-series demo metrics:" in time_series.stdout
