"""Research archive, catalog and chart commands over the report Skill."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skills.cli.io import check_output, json_safe, read_frame, write_bytes
from skills.cli.models import Artifact, CLIError, CLIModel, CommandResult
from skills.cli.registry import Command

REPORTS_ROOT_HELP = "Reports root; otherwise QUANTSPACE_REPORTS_ROOT or repository reports/."


def _reports_root(value):
    from skills.store.workspace import resolve_workspace_paths

    return Path(value).expanduser().resolve() if value else resolve_workspace_paths().reports_root


class ListInput(CLIModel):
    reports_root: Path | None = Field(default=None, description=REPORTS_ROOT_HELP)
    namespace: str | None = Field(default=None, description="Only studies in this namespace.")


class ListOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reports_root: str = Field(description="Scanned reports root.")
    count: int = Field(description="Number of listed studies.")
    studies: list[dict[str, Any]] = Field(
        description="params.json records plus index_html and study_dir, sorted by namespace/slug."
    )


def list_studies(args: ListInput) -> CommandResult:
    from skills.report.research_report import list_research_studies

    root = _reports_root(args.reports_root)
    studies = list_research_studies(root)
    if args.namespace:
        studies = [item for item in studies if item.get("namespace") == args.namespace]
    return CommandResult(
        data=ListOutput(reports_root=str(root), count=len(studies), studies=json_safe(studies))
    )


class FigureItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="Figure name.")
    caption: str = Field(description="Figure caption.")
    source_path: Path = Field(
        description="PNG file inlined into the HTML, e.g. from qs report chart."
    )


class TableItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="Table name; robustness/comparison names render in section 7.")
    caption: str = Field(description="Table caption.")
    path: Path | None = Field(default=None, description="CSV or Parquet table rendered to HTML.")
    html: str | None = Field(default=None, description="Prerendered HTML table.")

    @model_validator(mode="after")
    def one_source(self):
        if (self.path is None) == (self.html is None):
            raise ValueError(f"table {self.name!r} needs exactly one of path or html")
        return self


class BundleInput(CLIModel):
    namespace: str = Field(description="Safe path segment: reports/<namespace>/<slug>/.")
    slug: str = Field(description="Safe path segment naming the study directory.")
    title: str = Field(description="Report title.")
    question: str = Field(description="Testable research question.")
    universe: list[str] = Field(description="Symbols studied.")
    frequency: str = Field(description="Bar frequency, e.g. 1d.")
    sample_start: str = Field(description="Sample start date.")
    sample_end: str = Field(description="Sample end date.")
    in_sample_end: str | None = Field(default=None, description="In-sample end, if split.")
    out_of_sample_start: str | None = Field(
        default=None, description="Out-of-sample start, if split."
    )
    hypothesis: str = Field(description="Why the signal might work and what it predicts.")
    method_notes: list[str] = Field(description="Implementation details.")
    execution: dict[str, Any] = Field(
        description="Execution conventions such as trade_at, signal_lag, commission, slippage_bp."
    )
    metrics: dict[str, Any] = Field(
        description="Metrics read from a backtest result; never invented."
    )
    metrics_source: str = Field(description="Where metrics came from, e.g. BacktestResult.metrics.")
    figures: list[FigureItem] = Field(description="Figures from PNG files; may be empty.")
    tables: list[TableItem] = Field(description="Evidence tables; may be empty.")
    caveats: list[str] = Field(description="Weaknesses and confounders.")
    next_steps: list[str] = Field(description="Concrete follow-up tests.")
    reproduce_command: str = Field(description="Command that regenerates the evidence.")
    visibility: Literal["private", "public_example"] = Field(
        default="private", description="private by default; public_example for shared examples."
    )
    domain: str = Field(default="", description="Strategy domain label.")
    kind: Literal["research", "dashboard", "public_example"] = Field(
        default="research", description="Study kind."
    )
    tags: list[str] = Field(default_factory=list, description="Catalog tags.")
    as_of: str | None = Field(default=None, description="As-of date label.")
    notes: list[str] = Field(
        default_factory=list, description="Extra notes; robustness notes render in section 7."
    )
    reports_root: Path | None = Field(default=None, description=REPORTS_ROOT_HELP)
    catalog: bool = Field(
        default=False, description="Also rewrite catalog.html and catalog.json afterwards."
    )
    overwrite: bool = Field(default=False, description="Replace an existing study directory.")


class BundleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study_dir: str = Field(description="Written study directory.")
    files: list[str] = Field(description="Files written inside the study directory.")
    catalog: str | None = Field(description="Rewritten catalog.html, if requested.")


def bundle(args: BundleInput) -> CommandResult:
    from skills.report.research_report import (
        ReportFigure,
        ReportTable,
        ResearchReport,
        write_research_bundle,
        write_research_catalog,
    )

    root = _reports_root(args.reports_root)
    study = root / args.namespace / args.slug
    missing = [str(item.source_path) for item in args.figures if not item.source_path.is_file()]
    if missing:
        raise CLIError("NOT_FOUND", "Figure source files not found", exit_code=3, details=missing)
    existing = [name for name in ("index.html", "params.json") if (study / name).exists()]
    if existing and not args.overwrite:
        raise CLIError(
            "CONFLICT",
            f"Study already exists: {study}; use --overwrite",
            details=existing,
        )
    fields = args.model_dump(exclude={"figures", "tables", "reports_root", "catalog", "overwrite"})
    report = ResearchReport(
        **fields,
        figures=[
            ReportFigure(name=item.name, caption=item.caption, source_path=str(item.source_path))
            for item in args.figures
        ],
        tables=[
            ReportTable(
                name=item.name,
                caption=item.caption,
                frame=read_frame(item.path) if item.path else None,
                html=item.html,
            )
            for item in args.tables
        ],
    )
    study_dir = write_research_bundle(report, reports_root=root)
    catalog = write_research_catalog(root) if args.catalog else None
    files = sorted(
        path.relative_to(study_dir).as_posix() for path in study_dir.rglob("*") if path.is_file()
    )
    artifacts = [Artifact(name="study", path=str(study_dir), format="directory")]
    if catalog:
        artifacts.append(Artifact(name="catalog", path=str(catalog), format="html"))
    return CommandResult(
        data=BundleOutput(
            study_dir=str(study_dir), files=files, catalog=str(catalog) if catalog else None
        ),
        artifacts=artifacts,
    )


class CatalogInput(CLIModel):
    reports_root: Path | None = Field(default=None, description=REPORTS_ROOT_HELP)


class CatalogOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog: str = Field(description="Written catalog.html; catalog.json sits beside it.")
    count: int = Field(description="Studies in the catalog.")


def catalog(args: CatalogInput) -> CommandResult:
    from skills.report.research_report import list_research_studies, write_research_catalog

    root = _reports_root(args.reports_root)
    path = write_research_catalog(root)
    return CommandResult(
        data=CatalogOutput(catalog=str(path), count=len(list_research_studies(root))),
        artifacts=[
            Artifact(name="catalog", path=str(path), format="html"),
            Artifact(name="catalog_json", path=str(path.with_suffix(".json")), format="json"),
        ],
    )


CHARTS = {
    "equity-curve": "plot_equity_curve",
    "backtest-performance": "plot_backtest_performance",
    "factor-ranking": "plot_factor_ranking",
    "ic-heatmap": "plot_ic_heatmap",
    "horizon-ic": "plot_horizon_ic",
    "lagged-ic": "plot_lagged_ic",
    "factor-weight-history": "plot_factor_weight_history",
}


class ChartInput(CLIModel):
    kind: Literal[
        "equity-curve",
        "backtest-performance",
        "factor-ranking",
        "ic-heatmap",
        "horizon-ic",
        "lagged-ic",
        "factor-weight-history",
    ] = Field(
        description="equity-curve: one return column; backtest-performance: a backtest result "
        "table; factor-ranking: a screen ranking; ic-heatmap: factors by periods; horizon-ic and "
        "lagged-ic: an ic-surface summary; factor-weight-history: tidy eob/method/factor/weight "
        "records, or the wide factor_weights from strategy combine (labelled with params method)."
    )
    table: Path = Field(description="Input CSV or Parquet table.")
    column: str = Field(default="return", description="Return column for equity-curve.")
    title: str | None = Field(
        default=None, description="Chart title; the chart default if omitted."
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Other keyword arguments of the charts function, e.g. factors=[...] for "
        "horizon-ic or value_col for factor-ranking.",
    )
    output: Path = Field(description="Destination PNG file.")
    overwrite: bool = Field(default=False, description="Replace an existing PNG.")


class ChartOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(description="Rendered chart kind.")
    function: str = Field(description="skills.report.charts function used.")
    bytes: int = Field(description="PNG size.")


def _weight_records(table, method):
    """Tidy eob/method/factor/weight records, as plot_factor_weight_history pivots them."""
    if {"factor", "weight"}.issubset(table.columns):
        # read_frame moved the eob column into the index.
        return table.reset_index()
    # strategy combine writes one method's weights as a wide eob x factor table.
    records = (
        table.rename_axis(index="eob")
        .reset_index()
        .melt(id_vars="eob", var_name="factor", value_name="weight")
        .dropna(subset=["weight"])
    )
    return records.assign(method=method)


def chart(args: ChartInput) -> CommandResult:
    from skills.report import charts

    if args.output.suffix.lower() != ".png":
        raise CLIError("INVALID_INPUT", "Chart output must end in .png")
    check_output(args.output, overwrite=args.overwrite)
    table = read_frame(args.table)
    kwargs = dict(args.params)
    if args.title is not None:
        kwargs["title"] = args.title
    if args.kind == "equity-curve":
        if args.column not in table:
            raise ValueError(f"table requires column {args.column!r}")
        table = table[args.column]
    elif args.kind == "factor-weight-history":
        default = inspect.signature(charts.plot_factor_weight_history).parameters["method"].default
        table = _weight_records(table, kwargs.get("method", default))
    name = CHARTS[args.kind]
    png = getattr(charts, name)(table, **kwargs)
    artifact = write_bytes(png, args.output, overwrite=args.overwrite, name="chart")
    return CommandResult(
        data=ChartOutput(kind=args.kind, function=f"charts.{name}", bytes=len(png)),
        artifacts=[artifact],
    )


COMMANDS = [
    Command(
        "report.list",
        ListInput,
        ListOutput,
        list_studies,
        "List research studies that have index.html and params.json.",
        priority="P0",
    ),
    Command(
        "report.bundle",
        BundleInput,
        BundleOutput,
        bundle,
        "Write a nine-section HTML research archive with write_research_bundle.",
        side_effects=("writes-output",),
    ),
    Command(
        "report.catalog",
        CatalogInput,
        CatalogOutput,
        catalog,
        "Rewrite catalog.html and catalog.json under the reports root.",
        side_effects=("writes-output",),
    ),
    Command(
        "report.chart",
        ChartInput,
        ChartOutput,
        chart,
        "Render one skills.report.charts PNG from a table.",
        side_effects=("writes-output",),
    ),
]
