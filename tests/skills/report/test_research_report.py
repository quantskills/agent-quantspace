from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from skills.report import (
    ReportFigure,
    ReportTable,
    ResearchReport,
    list_research_studies,
    write_research_bundle,
    write_research_catalog,
)

_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
    b"\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)

_NINE_TITLES = [
    "研究问题",
    "数据与样本",
    "假设与方法",
    "执行约定",
    "证据与指标",
    "图表",
    "对照与稳健性",
    "限制与下一步",
    "复现与产物",
]


def _make_report(**overrides: object) -> ResearchReport:
    payload: dict[str, object] = {
        "namespace": "lesson_09",
        "slug": "if_ma10_atr",
        "title": "IF MA10 + ATR 研究报告",
        "question": "MA10 与 ATR 规则能否在 IF 上取得正期望？",
        "universe": ["CFFEX.IF"],
        "frequency": "1d",
        "sample_start": "2024-01-01",
        "sample_end": "2026-07-01",
        "in_sample_end": "2025-12-31",
        "out_of_sample_start": "2026-01-01",
        "hypothesis": "短均线突破叠加波动过滤。",
        "method_notes": ["信号在收盘生成，下一根开盘成交。"],
        "execution": {"trade_at": "open", "commission": 0.0001},
        "metrics": {"sharpe_ratio": 1.5, "max_drawdown": -0.25},
        "metrics_source": "BacktestResult.metrics",
        "figures": [ReportFigure(name="equity", caption="策略净值曲线", png=_PNG)],
        "tables": [
            ReportTable(
                name="metrics_table",
                caption="调用方提供的指标表",
                frame=pd.DataFrame({"metric": ["sharpe_ratio"], "value": [1.5]}),
            )
        ],
        "caveats": ["样本较短，不能外推到其他品种。"],
        "next_steps": ["补充成本敏感性。"],
        "reproduce_command": "uv run python -m strategies.time_series.workflows.run_demo",
        "visibility": "private",
        "domain": "time_series",
        "kind": "research",
        "tags": ["rule", "futures"],
        "as_of": "2026-08-15",
        "notes": [],
    }
    payload.update(overrides)
    return ResearchReport(**payload)  # type: ignore[arg-type]


def test_write_research_bundle_happy_path(tmp_path: Path) -> None:
    study_dir = write_research_bundle(_make_report(), reports_root=tmp_path)

    index_path = study_dir / "index.html"
    params_path = study_dir / "params.json"
    assert index_path.is_file()
    assert params_path.is_file()
    assert not (tmp_path / "catalog.html").exists()

    html = index_path.read_text(encoding="utf-8")
    for title in _NINE_TITLES:
        assert f"<h2>{title}</h2>" in html
    assert "1.5" in html
    assert "sharpe_ratio" in html
    assert "data:image/png;base64," in html
    assert "本报告未做" in html
    assert 'lang="zh-CN"' in html
    assert 'href="../../catalog.html"' in html
    assert html.count("返回目录") >= 2

    params = json.loads(params_path.read_text(encoding="utf-8"))
    assert params["metrics"] == {"sharpe_ratio": 1.5, "max_drawdown": -0.25}
    assert params["metrics_source"] == "BacktestResult.metrics"
    assert params["namespace"] == "lesson_09"
    assert params["slug"] == "if_ma10_atr"
    assert params["visibility"] == "private"


def test_figure_from_source_path_is_inlined(tmp_path: Path) -> None:
    png_path = tmp_path / "equity.png"
    png_path.write_bytes(_PNG)
    report = _make_report(
        figures=[
            ReportFigure(
                name="from_disk",
                caption="从已有 PNG 读取并内嵌",
                source_path=str(png_path),
            )
        ]
    )

    study_dir = write_research_bundle(report, reports_root=tmp_path / "reports")
    html = (study_dir / "index.html").read_text(encoding="utf-8")
    assert "data:image/png;base64," in html
    assert "<img" in html


def test_missing_question_raises_without_writing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="question"):
        write_research_bundle(_make_report(question=""), reports_root=tmp_path)
    assert not list(tmp_path.rglob("index.html"))


def test_missing_metrics_source_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="metrics_source"):
        write_research_bundle(_make_report(metrics_source=""), reports_root=tmp_path)
    assert not list(tmp_path.rglob("index.html"))


@pytest.mark.parametrize(
    ("namespace", "slug"),
    [
        ("../x", "ok"),
        ("a/b", "ok"),
        ("ok", "a/b"),
        ("ok", ".."),
        ("", "ok"),
        ("ok", ""),
    ],
)
def test_unsafe_namespace_slug_raises(tmp_path: Path, namespace: str, slug: str) -> None:
    with pytest.raises(ValueError):
        write_research_bundle(
            _make_report(namespace=namespace, slug=slug),
            reports_root=tmp_path,
        )
    assert not list(tmp_path.rglob("index.html"))


def test_list_research_studies_skips_csv_only_folder(tmp_path: Path) -> None:
    csv_only = tmp_path / "old_csv_run"
    csv_only.mkdir()
    (csv_only / "results.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    write_research_bundle(_make_report(), reports_root=tmp_path)
    studies = list_research_studies(tmp_path)

    assert len(studies) == 1
    assert studies[0]["slug"] == "if_ma10_atr"
    assert studies[0]["index_html"] == "lesson_09/if_ma10_atr/index.html"


def test_list_research_studies_requires_both_params_and_index(tmp_path: Path) -> None:
    params_only = tmp_path / "lesson_09" / "params_only"
    params_only.mkdir(parents=True)
    (params_only / "params.json").write_text("{}\n", encoding="utf-8")

    html_only = tmp_path / "lesson_09" / "html_only"
    html_only.mkdir(parents=True)
    (html_only / "index.html").write_text("<html></html>\n", encoding="utf-8")

    assert list_research_studies(tmp_path) == []


def test_missing_figure_source_does_not_write(tmp_path: Path) -> None:
    report = _make_report(
        figures=[
            ReportFigure(
                name="missing",
                caption="源文件不存在",
                source_path=str(tmp_path / "does_not_exist.png"),
            )
        ]
    )
    with pytest.raises(ValueError, match="source_path"):
        write_research_bundle(report, reports_root=tmp_path)
    assert not list(tmp_path.rglob("index.html"))
    assert not list(tmp_path.rglob("params.json"))


def test_write_research_catalog_links_study_and_visibility(tmp_path: Path) -> None:
    write_research_bundle(_make_report(), reports_root=tmp_path)
    write_research_bundle(
        _make_report(
            namespace="strategy_examples",
            slug="demo",
            title="Demo Strategy",
            visibility="public_example",
            kind="public_example",
        ),
        reports_root=tmp_path,
    )
    readme = tmp_path / "README.md"
    readme.write_text("keep me\n", encoding="utf-8")

    catalog_path = write_research_catalog(tmp_path)
    html = catalog_path.read_text(encoding="utf-8")
    assert catalog_path == tmp_path / "catalog.html"
    assert "lesson_09/if_ma10_atr/index.html" in html
    assert "strategy_examples/demo/index.html" in html
    assert "private" in html
    assert "public_example" in html
    assert (tmp_path / "catalog.json").is_file()
    assert readme.read_text(encoding="utf-8") == "keep me\n"
    assert not (tmp_path / "strategy_examples" / "index.html").exists()


def test_section_seven_says_not_done_without_robustness(tmp_path: Path) -> None:
    study_dir = write_research_bundle(_make_report(), reports_root=tmp_path)
    html = (study_dir / "index.html").read_text(encoding="utf-8")
    marker = html.split("<h2>对照与稳健性</h2>", 1)[1]
    rest = marker.split("<h2>", 1)[0]
    assert "本报告未做" in rest


def test_public_example_visibility_still_writes_namespace_slug(tmp_path: Path) -> None:
    study_dir = write_research_bundle(
        _make_report(visibility="public_example"),
        reports_root=tmp_path,
    )
    assert study_dir == tmp_path / "lesson_09" / "if_ma10_atr"
    assert (study_dir / "index.html").is_file()
    assert not (tmp_path / "strategy_examples").exists()


def test_written_files_use_lf_and_cjk_font_stack(tmp_path: Path) -> None:
    study_dir = write_research_bundle(_make_report(), reports_root=tmp_path)
    html_bytes = (study_dir / "index.html").read_bytes()
    params_bytes = (study_dir / "params.json").read_bytes()
    html = html_bytes.decode("utf-8")
    assert b"\r\n" not in html_bytes
    assert b"\r\n" not in params_bytes
    assert "Microsoft YaHei" in html
    assert "PingFang SC" in html
    assert "Hiragino Sans GB" in html


def test_list_research_studies_reads_utf8_bom(tmp_path: Path) -> None:
    study_dir = write_research_bundle(_make_report(), reports_root=tmp_path)
    params_path = study_dir / "params.json"
    params_path.write_bytes(b"\xef\xbb\xbf" + params_path.read_bytes())
    studies = list_research_studies(tmp_path)
    assert studies[0]["slug"] == "if_ma10_atr"
    assert studies[0]["index_html"] == "lesson_09/if_ma10_atr/index.html"
    assert "\\" not in studies[0]["index_html"]
