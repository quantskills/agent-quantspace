from __future__ import annotations

from pathlib import Path

from scripts.run_strategy_reports import generate_reports


def test_generated_strategy_reports_have_html_and_png_artifacts(
    tmp_path: Path,
    strategy_report_data_root: Path,
) -> None:
    paths = generate_reports(
        data_root=strategy_report_data_root,
        reports_root=tmp_path,
    )

    assert len(paths) == 5
    for report_path in paths:
        slug = report_path.parent.name
        image_path = tmp_path / "strategy_examples" / f"{slug}_performance.png"
        text = report_path.read_text(encoding="utf-8")
        assert report_path.name == "index.html"
        assert report_path.parent.parent.name == "strategy_examples"
        assert image_path.exists()
        assert (report_path.parent / "params.json").is_file()
        assert "data:image/png;base64," in text
        assert "<h2>证据与指标</h2>" in text
