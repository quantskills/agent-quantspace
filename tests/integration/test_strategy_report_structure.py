from __future__ import annotations

from pathlib import Path

from scripts.run_strategy_reports import generate_reports


def test_generated_strategy_reports_have_html_and_png_artifacts(
    tmp_path: Path,
    strategy_report_data_root: Path,
) -> None:
    output_dir = tmp_path / "reports"

    paths = generate_reports(data_root=strategy_report_data_root, report_dir=output_dir)

    report_paths = [path for path in paths if path.name != "index.html"]
    assert len(report_paths) == 5
    for report_path in report_paths:
        image_path = output_dir / f"{report_path.stem}_performance.png"
        text = report_path.read_text(encoding="utf-8")
        assert report_path.suffix == ".html"
        assert image_path.exists()
        assert "data:image/png;base64," in text
        assert "<h2>Metrics</h2>" in text
