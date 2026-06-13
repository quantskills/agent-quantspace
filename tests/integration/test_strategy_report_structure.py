from __future__ import annotations

from pathlib import Path

from scripts.run_strategy_reports import generate_reports


def test_generated_strategy_reports_have_markdown_and_png_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "reports"

    paths = generate_reports(report_dir=output_dir)

    report_paths = [path for path in paths if path.name != "README.md"]
    assert len(report_paths) == 4
    for report_path in report_paths:
        image_path = output_dir / f"{report_path.stem}_performance.png"
        text = report_path.read_text(encoding="utf-8")
        assert image_path.exists()
        assert f"![Performance Chart]({image_path.name})" in text
        assert "## Metrics" in text
