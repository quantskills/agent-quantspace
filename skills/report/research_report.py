"""Complete HTML research-report payload, bundle writer, and catalog."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from skills.report.renderer import ReportRenderer, relative_catalog_href
from skills.store.workspace import resolve_workspace_paths

_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_RESERVED_NAMES = frozenset(
    {"README.md", "README-zh.md", "catalog.html", "catalog.json"}
)
_ALLOWED_VISIBILITY = frozenset({"private", "public_example"})
_ALLOWED_KIND = frozenset({"research", "dashboard", "public_example"})
_ROBUSTNESS_RE = re.compile(
    r"robust|sensitivity|comparison|benchmark|对照|稳健|敏感性|\boos\b",
    re.IGNORECASE,
)
_PARAMS_FIELDS = (
    "namespace",
    "slug",
    "title",
    "kind",
    "domain",
    "visibility",
    "tags",
    "sample_start",
    "sample_end",
    "metrics",
    "metrics_source",
    "as_of",
)


@dataclass
class ReportFigure:
    """One chart in a research report; PNG bytes are inlined into HTML."""

    name: str
    caption: str
    png: bytes | None = None
    source_path: str | None = None

    def __post_init__(self) -> None:
        _validate_figure(self)


@dataclass
class ReportTable:
    """One table in a research report; rendered to HTML, never Markdown."""

    name: str
    caption: str
    frame: pd.DataFrame | None = None
    html: str | None = None

    def __post_init__(self) -> None:
        _validate_table(self)


@dataclass
class ResearchReport:
    """Structured payload for a nine-section HTML research archive."""

    namespace: str
    slug: str
    title: str
    question: str
    universe: list[str]
    frequency: str
    sample_start: str
    sample_end: str
    in_sample_end: str | None
    out_of_sample_start: str | None
    hypothesis: str
    method_notes: list[str]
    execution: dict[str, Any]
    metrics: dict[str, Any]
    metrics_source: str
    figures: list[ReportFigure]
    tables: list[ReportTable]
    caveats: list[str]
    next_steps: list[str]
    reproduce_command: str
    visibility: str
    domain: str = ""
    kind: str = "research"
    tags: list[str] = field(default_factory=list)
    as_of: str | None = None
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        validate_research_report(self)


def validate_research_report(report: ResearchReport) -> None:
    """Raise ``ValueError`` if the payload cannot be written."""
    _require_safe_segment(report.namespace, "namespace")
    _require_safe_segment(report.slug, "slug")
    _require_nonempty_str(report.question, "question")
    _require_nonempty_str(report.metrics_source, "metrics_source")
    if not isinstance(report.metrics, dict):
        raise ValueError("metrics must be a dict")
    if report.visibility not in _ALLOWED_VISIBILITY:
        raise ValueError(
            "visibility must be one of "
            f"{sorted(_ALLOWED_VISIBILITY)}; got {report.visibility!r}"
        )
    if report.kind not in _ALLOWED_KIND:
        raise ValueError(
            f"kind must be one of {sorted(_ALLOWED_KIND)}; got {report.kind!r}"
        )
    for figure in report.figures:
        _validate_figure(figure)
    for table in report.tables:
        _validate_table(table)


def write_research_bundle(
    report: ResearchReport,
    reports_root: str | Path | None = None,
) -> Path:
    """Validate, render, and write ``reports/<namespace>/<slug>/``.

    Returns the study directory. Does not write ``catalog.html``.
    """
    validate_research_report(report)
    resolved_figures = _resolve_figures(report.figures)
    evidence_tables, robustness_tables = _split_tables(report.tables)
    robustness_notes, other_notes = _split_notes(report.notes)
    root = _resolve_reports_root(reports_root)
    study_dir = root / report.namespace / report.slug
    written_files = ["index.html", "params.json"]
    metrics_rows: list[dict[str, Any]] | None = None
    if report.metrics:
        written_files.append("artifacts/metrics.csv")
        metrics_rows = [
            {"metric": str(key), "value": _to_jsonable(value)}
            for key, value in report.metrics.items()
        ]

    context = _bundle_context(
        report,
        resolved_figures=resolved_figures,
        evidence_tables=evidence_tables,
        robustness_tables=robustness_tables,
        robustness_notes=robustness_notes,
        other_notes=other_notes,
        written_files=written_files,
        catalog_href=relative_catalog_href(study_dir, root),
    )
    renderer = ReportRenderer(output_dir=root)
    html = renderer.render("research_report", context)
    params_text = json.dumps(_params_payload(report), ensure_ascii=False, indent=2) + "\n"

    renderer.save(html, Path(report.namespace) / report.slug / "index.html")
    (study_dir / "params.json").write_text(params_text, encoding="utf-8", newline="\n")
    if metrics_rows is not None:
        artifacts_dir = study_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(metrics_rows).to_csv(
            artifacts_dir / "metrics.csv",
            index=False,
            encoding="utf-8",
            lineterminator="\n",
        )
    return study_dir


def list_research_studies(reports_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Return studies that have both ``params.json`` and ``index.html``."""
    root = _resolve_reports_root(reports_root)
    if not root.exists():
        return []

    studies: list[dict[str, Any]] = []
    for params_path in sorted(root.rglob("params.json")):
        study_dir = params_path.parent
        try:
            relative = study_dir.relative_to(root)
        except ValueError:
            continue
        if any(part in _RESERVED_NAMES for part in relative.parts):
            continue
        if not (study_dir / "index.html").is_file():
            continue
        try:
            payload = json.loads(params_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        record = dict(payload)
        index_html = (relative / "index.html").as_posix()
        record["index_html"] = index_html
        record["study_dir"] = relative.as_posix()
        studies.append(record)
    studies.sort(key=lambda item: (str(item.get("namespace", "")), str(item.get("slug", ""))))
    return studies


def write_research_catalog(
    reports_root: str | Path | None = None,
) -> Path:
    """Write ``catalog.html`` and ``catalog.json`` under ``reports_root``."""
    root = _resolve_reports_root(reports_root)
    root.mkdir(parents=True, exist_ok=True)
    records = [_catalog_record(item) for item in list_research_studies(root)]
    records.sort(key=lambda item: (str(item.get("namespace", "")), str(item.get("slug", ""))))

    html = ReportRenderer(output_dir=root).render(
        "catalog",
        {
            "title": "研究报告目录",
            "studies": records,
            "as_of": date.today().isoformat(),
            "study_count": len(records),
        },
    )
    catalog_html = ReportRenderer(output_dir=root).save(html, "catalog.html")
    (root / "catalog.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return catalog_html


def _resolve_reports_root(reports_root: str | Path | None) -> Path:
    if reports_root is not None:
        return Path(reports_root)
    return resolve_workspace_paths().reports_root


def _require_nonempty_str(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_safe_segment(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not _SAFE_SEGMENT_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} must be a safe path segment "
            f"(letters, digits, underscore, hyphen); got {value!r}"
        )


def _validate_figure(figure: ReportFigure) -> None:
    has_png = bool(figure.png)
    has_source = bool(figure.source_path)
    if not has_png and not has_source:
        raise ValueError(f"figure {figure.name!r} needs png or source_path")


def _validate_table(table: ReportTable) -> None:
    has_frame = table.frame is not None
    has_html = bool(table.html)
    if not has_frame and not has_html:
        raise ValueError(f"table {table.name!r} needs frame or html")


def _resolve_figures(figures: list[ReportFigure]) -> list[ReportFigure]:
    resolved: list[ReportFigure] = []
    for figure in figures:
        png = figure.png if figure.png else _read_figure_png(figure)
        resolved.append(
            ReportFigure(
                name=figure.name,
                caption=figure.caption,
                png=png,
                source_path=figure.source_path,
            )
        )
    return resolved


def _read_figure_png(figure: ReportFigure) -> bytes:
    if not figure.source_path:
        raise ValueError(f"figure {figure.name!r} needs png or source_path")
    path = Path(figure.source_path)
    if not path.is_file():
        raise ValueError(
            f"figure {figure.name!r} source_path does not exist: {figure.source_path}"
        )
    return path.read_bytes()


def _table_html(table: ReportTable) -> str:
    if table.html:
        return table.html
    if table.frame is None:
        raise ValueError(f"table {table.name!r} needs frame or html")
    return table.frame.style.to_html()


def _is_robustness_text(*parts: str | None) -> bool:
    text = " ".join(part for part in parts if part)
    return bool(text) and _ROBUSTNESS_RE.search(text) is not None


def _split_tables(
    tables: list[ReportTable],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    evidence: list[dict[str, str]] = []
    robustness: list[dict[str, str]] = []
    for table in tables:
        payload = {
            "name": table.name,
            "caption": table.caption,
            "html": _table_html(table),
        }
        if _is_robustness_text(table.name, table.caption):
            robustness.append(payload)
        else:
            evidence.append(payload)
    return evidence, robustness


def _split_notes(notes: list[str]) -> tuple[list[str], list[str]]:
    robustness: list[str] = []
    other: list[str] = []
    for note in notes:
        if _is_robustness_text(note):
            robustness.append(note)
        else:
            other.append(note)
    return robustness, other


def _bundle_context(
    report: ResearchReport,
    *,
    resolved_figures: list[ReportFigure],
    evidence_tables: list[dict[str, str]],
    robustness_tables: list[dict[str, str]],
    robustness_notes: list[str],
    other_notes: list[str],
    written_files: list[str],
    catalog_href: str,
) -> dict[str, Any]:
    has_robustness = bool(robustness_tables or robustness_notes)
    return {
        "title": report.title,
        "namespace": report.namespace,
        "slug": report.slug,
        "question": report.question,
        "universe": report.universe,
        "frequency": report.frequency,
        "sample_start": report.sample_start,
        "sample_end": report.sample_end,
        "in_sample_end": report.in_sample_end,
        "out_of_sample_start": report.out_of_sample_start,
        "hypothesis": report.hypothesis,
        "method_notes": report.method_notes,
        "execution": {str(key): _to_jsonable(value) for key, value in report.execution.items()},
        "metrics": {str(key): _to_jsonable(value) for key, value in report.metrics.items()},
        "metrics_source": report.metrics_source,
        "figures": resolved_figures,
        "evidence_tables": evidence_tables,
        "robustness_tables": robustness_tables,
        "robustness_notes": robustness_notes,
        "has_robustness": has_robustness,
        "caveats": report.caveats,
        "next_steps": report.next_steps,
        "reproduce_command": report.reproduce_command,
        "visibility": report.visibility,
        "domain": report.domain,
        "kind": report.kind,
        "tags": list(report.tags),
        "as_of": report.as_of,
        "notes": other_notes,
        "written_files": written_files,
        "catalog_href": catalog_href,
    }


def _params_payload(report: ResearchReport) -> dict[str, Any]:
    payload = {
        "namespace": report.namespace,
        "slug": report.slug,
        "title": report.title,
        "kind": report.kind,
        "domain": report.domain,
        "visibility": report.visibility,
        "tags": list(report.tags),
        "sample_start": report.sample_start,
        "sample_end": report.sample_end,
        "metrics": _to_jsonable(report.metrics),
        "metrics_source": report.metrics_source,
        "as_of": report.as_of,
    }
    return {key: payload[key] for key in _PARAMS_FIELDS}


def _catalog_record(study: dict[str, Any]) -> dict[str, Any]:
    metrics = study.get("metrics") if isinstance(study.get("metrics"), dict) else {}
    sample_start = study.get("sample_start") or ""
    sample_end = study.get("sample_end") or ""
    if sample_start and sample_end:
        sample = f"{sample_start} – {sample_end}"
    else:
        sample = sample_start or sample_end or "—"
    record = dict(study)
    record["sample"] = sample
    record["sharpe"] = _first_metric(metrics, "sharpe_ratio", "sharpe")
    record["max_drawdown"] = _first_metric(metrics, "max_drawdown")
    return record


def _first_metric(metrics: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in metrics.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def _to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return _to_jsonable(value.tolist())
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        number = float(value)
        if not np.isfinite(number):
            return None
        return number
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not np.isfinite(value):
            return None
        return value
    if isinstance(value, str):
        return value
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except (TypeError, ValueError):
            return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


__all__ = [
    "ReportFigure",
    "ReportTable",
    "ResearchReport",
    "list_research_studies",
    "validate_research_report",
    "write_research_bundle",
    "write_research_catalog",
]
