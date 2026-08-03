from __future__ import annotations

from skills.report.renderer import ReportRenderer, png_to_data_uri


def test_png_to_data_uri_encodes_png_bytes() -> None:
    uri = png_to_data_uri(b"\x89PNG\r\n\x1a\nabc")

    assert uri.startswith("data:image/png;base64,")


def test_report_renderer_renders_known_template(tmp_path) -> None:
    renderer = ReportRenderer(output_dir=tmp_path)

    html = renderer.render("backtest_report", {"title": "Demo"})
    path = renderer.save(html, "demo.html")

    assert "Demo" in html
    assert path.read_text(encoding="utf-8") == html


def test_factor_report_uses_artifact_namespace(tmp_path) -> None:
    renderer = ReportRenderer(output_dir=tmp_path)

    html = renderer.render(
        "factor_report",
        {
            "title": "Factor screen",
            "namespace": "macro_weekly",
            "n": 5,
            "as_of": "2026-07-22",
            "ranking_chart": None,
            "ranking_html": "<table></table>",
        },
    )

    assert "Namespace:" in html
    assert "macro_weekly" in html
