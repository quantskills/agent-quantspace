from __future__ import annotations

import pandas as pd

from skills.analyze.tearsheet import generate_namespace_summary_report


def test_namespace_summary_report_reads_namespaced_factor_artifacts(tmp_path, monkeypatch) -> None:
    namespace = "macro_weekly"
    summary_dir = tmp_path / "data" / "factor_test" / namespace
    summary_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "factor_id": ["roc__10"],
            "n": [5],
            "IC_IR": [0.8],
        }
    ).to_parquet(summary_dir / "summary.parquet", index=False)
    monkeypatch.setenv("QUANTSPACE_DATA_ROOT", str(tmp_path / "data"))
    output_path = tmp_path / "reports" / "summary.html"

    result = generate_namespace_summary_report(namespace, output_path=output_path)

    assert result == str(output_path)
    html = output_path.read_text(encoding="utf-8")
    assert "Factor Summary — macro_weekly" in html
    assert "roc__10" in html
