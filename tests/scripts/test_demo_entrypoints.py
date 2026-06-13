from __future__ import annotations

import os
import subprocess
import sys

from scripts.generate_sample_data import generate_sample_data


def _run_script(script: str, data_root) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "QUANTSPACE_DATA_ROOT": str(data_root)}
    return subprocess.run(
        [sys.executable, script],
        check=True,
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
    )


def test_public_demo_scripts_run_against_sample_data(tmp_path) -> None:
    data_root = generate_sample_data(tmp_path)

    cross_sectional = _run_script("scripts/run_cross_sectional_demo.py", data_root)
    time_series = _run_script("scripts/run_time_series_demo.py", data_root)

    assert "Cross-sectional demo metrics:" in cross_sectional.stdout
    assert "Time-series demo metrics:" in time_series.stdout
