"""File-based diagnostics over factors, return streams and time series."""

from __future__ import annotations

import math
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skills.cli.io import (
    check_output,
    json_safe,
    load_panel,
    read_frame,
    read_json,
    read_panel,
    write_bytes,
    write_frame,
    write_json,
)
from skills.cli.models import CLIError, CLIModel, CommandResult, PanelSource
from skills.cli.registry import Command

RegimeMasksFile = dict[str, Path]

SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")


def _has_nonfinite(value) -> bool:
    if isinstance(value, Mapping):
        return any(_has_nonfinite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_nonfinite(item) for item in value)
    if isinstance(value, float):
        return not math.isfinite(value)
    return False


def _warnings(value) -> list[str]:
    return ["nonfinite values were converted to null"] if _has_nonfinite(value) else []


def _records(frame) -> list[dict]:
    return json_safe(frame.to_dict(orient="records"))


def _column(path: Path, column: str):
    frame = read_frame(path)
    if column not in frame:
        raise ValueError(f"input requires column {column!r}")
    return frame[column]


def _read_factors(paths: Mapping[str, Path], directions: Mapping[str, int] | None = None):
    """Read wide factor tables, oriented by `directions` when given."""
    frames = {name: read_frame(path) for name, path in paths.items()}
    if directions is None:
        return frames
    from skills.strategy.cross_sectional.factor_combination import orient_factor_frames

    return orient_factor_frames(frames, directions)


def _value_series(path: Path, names=("fac_val", "value")):
    """Return the single value column of a long (symbol, eob) table."""
    frame = read_panel(path)
    for name in names:
        if name in frame:
            return frame[name]
    if len(frame.columns) == 1:
        return frame.iloc[:, 0]
    raise ValueError(f"{path} requires one value column or one of {', '.join(names)}")


class ICInput(PanelSource):
    factor: Path = Field(
        description="Long factor table indexed by symbol and eob with one value column."
    )
    horizon: int = Field(default=1, gt=0, description="Rebalance period n in bars.")
    groups: int = Field(default=5, ge=2, description="Number of factor quantile groups g.")
    pearson: bool = Field(default=False, description="Use Pearson IC instead of rank IC.")
    out_dir: Path | None = Field(
        default=None,
        description="Optional directory for ic_series, group_return and turnover Parquet files.",
    )
    tearsheet: Path | None = Field(
        default=None,
        description="Optional .png path for the 4-panel factor tearsheet "
        "(generate_factor_tearsheet).",
    )
    name: str | None = Field(
        default=None,
        description="Factor label on the tearsheet; defaults to the --factor file stem.",
    )
    namespace: str = Field(
        default="-", description="Namespace label printed in the tearsheet title."
    )
    overwrite: bool = Field(default=False, description="Replace existing output files.")


class ICData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ic_stats: dict[str, float | int | None] = Field(
        description="IC_stat dictionary, unchanged (IC_mean, IC_IR, t_stat, ...)."
    )
    group_mean_return: dict[str, float | None] = Field(
        description="Mean daily return of each factor group G1..Gg."
    )
    ic_rows: int = Field(description="Number of IC dates.")
    group_rows: int = Field(description="Number of grouped return dates.")
    turnover_rows: int = Field(description="Number of turnover dates.")


def _tearsheet_png(args, ic, groups, turnover, stats) -> bytes:
    from skills.analyze.tearsheet import generate_factor_tearsheet

    with tempfile.TemporaryDirectory() as directory:
        path = generate_factor_tearsheet(
            factor_id=args.name or args.factor.stem,
            namespace=args.namespace,
            ic_series=ic,
            group_return=groups,
            turnover=turnover,
            ic_stat=stats,
            n=args.horizon,
            output_dir=directory,
        )
        return Path(path).read_bytes()


def factor_ic(args: ICInput) -> CommandResult:
    from skills.analyze.factor_analysis import full_stat

    names = ("ic_series", "group_return", "turnover")
    paths = {name: args.out_dir / f"{name}.parquet" for name in names} if args.out_dir else {}
    if args.tearsheet is not None and args.tearsheet.suffix.lower() != ".png":
        raise CLIError("INVALID_INPUT", f"tearsheet must be a .png file: {args.tearsheet}")
    for path in [*paths.values(), *([args.tearsheet] if args.tearsheet else [])]:
        check_output(path, overwrite=args.overwrite, data_root=args.data_root)
    panel = load_panel(args)
    if "close" not in panel:
        raise ValueError("panel requires close column")
    values = _value_series(args.factor)
    frame = panel[["close"]].copy()
    frame["fac_val"] = values.reindex(panel.index)
    frame = frame.reorder_levels(["eob", "symbol"]).sort_index()
    stats, ic, groups, turnover = full_stat(
        frame, n=args.horizon, g=args.groups, rank_IC=not args.pearson, verbose=False, plot=False
    )
    tables = {"ic_series": ic.to_frame("IC"), "group_return": groups, "turnover": turnover}
    artifacts = [
        write_frame(
            tables[name], path, overwrite=args.overwrite, data_root=args.data_root, name=name
        )
        for name, path in paths.items()
    ]
    if args.tearsheet is not None:
        artifacts.append(
            write_bytes(
                _tearsheet_png(args, ic, groups, turnover, stats),
                args.tearsheet,
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="tearsheet",
            )
        )
    stats = json_safe(stats)
    means = json_safe(groups.mean().to_dict())
    return CommandResult(
        data=ICData(
            ic_stats=stats,
            group_mean_return=means,
            ic_rows=len(ic),
            group_rows=len(groups),
            turnover_rows=len(turnover),
        ),
        artifacts=artifacts,
        warnings=_warnings({**stats, **means}),
    )


class ICSurfaceInput(PanelSource):
    factors: dict[str, Path] = Field(
        description="Wide factor tables (date by symbol) by name, e.g. mom=mom.parquet."
    )
    price_field: str = Field(
        default="close", description="Panel column used as the execution price."
    )
    horizons: list[int] = Field(description="Forward return horizons in bars.")
    lags: list[int] = Field(
        default_factory=lambda: [0], description="Extra signal-use delays in bars; 0 is Horizon IC."
    )
    signal_lag: int = Field(default=1, ge=0, description="Bars between signal and execution.")
    directions: dict[str, int] | None = Field(
        default=None,
        description="Optional direction (1 or -1) for every factor; the factors are oriented "
        "with orient_factor_frames before the IC is computed. Pass the same directions as "
        "strategy combine when the daily_ic feeds combine --ic-history.",
    )
    segments: dict[str, tuple[str | None, str | None]] | None = Field(
        default=None,
        description='Named [start, end] summary windows, e.g. {"is": ["2015-01-01", '
        '"2019-12-31"]}; null bounds are open. Omitted means one "full" segment.',
    )
    min_cross_section: int = Field(
        default=6, gt=0, description="Minimum symbols per date for an IC observation."
    )
    out_dir: Path | None = Field(
        default=None, description="Optional directory for summary and daily_ic Parquet files."
    )
    overwrite: bool = Field(default=False, description="Replace existing output files.")


class ICSurfaceData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: list[dict] = Field(
        description="One row per factor, segment, horizon and lag: ic_mean, icir, HAC "
        "t/se/p, confidence interval and effective_dates."
    )
    daily_rows: int = Field(description="Rows in the tidy daily IC table.")


def ic_surface(args: ICSurfaceInput) -> CommandResult:
    from skills.analyze.factor_information import compute_ic_information_surface

    paths = (
        {name: args.out_dir / f"{name}.parquet" for name in ("summary", "daily_ic")}
        if args.out_dir
        else {}
    )
    for path in paths.values():
        check_output(path, overwrite=args.overwrite, data_root=args.data_root)
    panel = load_panel(args)
    if args.price_field not in panel:
        raise ValueError(f"panel requires {args.price_field!r} column")
    result = compute_ic_information_surface(
        _read_factors(args.factors, args.directions),
        panel[args.price_field].unstack("symbol").sort_index(),
        horizons=args.horizons,
        lags=args.lags,
        signal_lag=args.signal_lag,
        segments=args.segments,
        min_cross_section=args.min_cross_section,
    )
    tables = {"summary": result.summary, "daily_ic": result.daily_ic}
    artifacts = [
        write_frame(
            tables[name], path, overwrite=args.overwrite, data_root=args.data_root, name=name
        )
        for name, path in paths.items()
    ]
    summary = _records(result.summary)
    return CommandResult(
        data=ICSurfaceData(summary=summary, daily_rows=len(result.daily_ic)),
        artifacts=artifacts,
        warnings=_warnings(summary),
    )


class FactorCorrelationInput(CLIModel):
    factors: dict[str, Path] = Field(
        description="Wide factor tables (date by symbol) by name, at least two, "
        "e.g. mom=mom.parquet."
    )
    directions: dict[str, int] | None = Field(
        default=None,
        description="Optional direction (1 or -1) for every factor; the factors are oriented "
        "with orient_factor_frames before ranking. Pass the same directions as strategy combine "
        "when feeding combine.",
    )
    segments: dict[str, tuple[str | None, str | None]] | None = Field(
        default=None,
        description='Named [start, end] summary windows, e.g. {"is": ["2015-01-01", '
        '"2019-12-31"]}; null bounds are open. Omitted means one "full" segment. '
        "Names are safe path segments (letters, digits, underscore, hyphen).",
    )
    window: int = Field(default=252, gt=0, description="Rolling correlation window in bars.")
    min_periods: int = Field(
        default=126, gt=0, description="Minimum observations in the rolling window."
    )
    top_n: int = Field(default=3, gt=0, description="Names per date in the Top-N overlap.")
    out_dir: Path | None = Field(
        default=None,
        description="Optional directory for correlation_<segment>, top_n_overlap_<segment> and "
        "correlation_history Parquet files; correlation_history feeds "
        "strategy combine --correlation-history.",
    )
    data_root: Path | None = Field(
        default=None,
        description="Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/.",
    )
    overwrite: bool = Field(default=False, description="Replace existing output files.")

    @model_validator(mode="after")
    def check_inputs(self):
        if len(self.factors) < 2:
            raise ValueError("factors needs at least two factors")
        if self.min_periods > self.window:
            raise ValueError("min_periods must not exceed window")
        if self.segments is not None and not self.segments:
            raise ValueError("segments cannot be empty")
        for name in self.segments or {}:
            if not SAFE_SEGMENT.fullmatch(name):
                raise ValueError(
                    f"segment name must be a safe path segment (letters, digits, underscore, "
                    f"hyphen); got {name!r}"
                )
        return self


class FactorCorrelationData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairs: list[list[str]] = Field(
        description="Factor pairs [factor_a, factor_b] in history order."
    )
    correlation: dict[str, dict[str, dict[str, float | None]]] = Field(
        description="Mean daily rank-correlation matrix by segment."
    )
    top_n_overlap: dict[str, dict[str, dict[str, float | None]]] = Field(
        description="Mean daily Top-N Jaccard overlap matrix by segment."
    )
    history_rows: int = Field(description="Rows in the tidy rolling correlation history.")


def _window(frame, start, end):
    """Rows with start <= date <= end; a None bound leaves that side open."""
    import pandas as pd

    keep = pd.Series(True, index=frame.index)
    if start is not None:
        keep &= frame.index >= pd.Timestamp(start)
    if end is not None:
        keep &= frame.index <= pd.Timestamp(end)
    return frame.loc[keep.to_numpy()]


def factor_correlation(args: FactorCorrelationInput) -> CommandResult:
    from skills.analyze.factor_information import (
        mean_daily_factor_rank_correlation,
        rolling_factor_rank_correlation,
        top_n_jaccard_overlap,
    )
    from skills.strategy.cross_sectional.factor_combination import rank_factor_frames

    segments = args.segments or {"full": (None, None)}
    paths = {}
    if args.out_dir:
        for segment in segments:
            paths[f"correlation_{segment}"] = args.out_dir / f"correlation_{segment}.parquet"
            paths[f"top_n_overlap_{segment}"] = args.out_dir / f"top_n_overlap_{segment}.parquet"
        paths["correlation_history"] = args.out_dir / "correlation_history.parquet"
    for path in paths.values():
        check_output(path, overwrite=args.overwrite, data_root=args.data_root)
    ranked = rank_factor_frames(_read_factors(args.factors, args.directions))
    tables = {}
    for segment, (start, end) in segments.items():
        tables[f"correlation_{segment}"] = mean_daily_factor_rank_correlation(
            ranked, start=start, end=end
        )
        tables[f"top_n_overlap_{segment}"] = top_n_jaccard_overlap(
            {name: _window(frame, start, end) for name, frame in ranked.items()},
            top_n=args.top_n,
        )
    history = rolling_factor_rank_correlation(
        ranked, window=args.window, min_periods=args.min_periods
    )
    tables["correlation_history"] = history
    artifacts = [
        write_frame(
            tables[name], path, overwrite=args.overwrite, data_root=args.data_root, name=name
        )
        for name, path in paths.items()
    ]
    matrices = [name for name in tables if name != "correlation_history"]
    names = list(ranked)
    data = FactorCorrelationData(
        pairs=[[left, right] for i, left in enumerate(names) for right in names[i + 1 :]],
        correlation={
            segment: json_safe(tables[f"correlation_{segment}"].to_dict(orient="index"))
            for segment in segments
        },
        top_n_overlap={
            segment: json_safe(tables[f"top_n_overlap_{segment}"].to_dict(orient="index"))
            for segment in segments
        },
        history_rows=len(history),
    )
    return CommandResult(
        data=data,
        artifacts=artifacts,
        warnings=["nonfinite values were converted to null"]
        if any(tables[name].isna().to_numpy().any() for name in matrices)
        else [],
    )


class PerfInput(CLIModel):
    returns: Path = Field(
        description="Dated table of periodic returns, such as a backtest result table."
    )
    column: str = Field(default="return", description="Return column in the input table.")
    annualization: int = Field(default=252, gt=0, description="Periods per year.")


class PerfData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metrics: dict[str, float | None] = Field(
        description="performance_metrics: ann_return, max_drawdown, calmar, sharpe, "
        "worst_20d, total_return."
    )
    rows: int = Field(description="Input observation count.")


def perf(args: PerfInput) -> CommandResult:
    from skills.analyze.attribution_counterfactual import performance_metrics

    series = _column(args.returns, args.column)
    metrics = performance_metrics(series, annualization=args.annualization)
    return CommandResult(
        data=PerfData(metrics=json_safe(metrics), rows=len(series)), warnings=_warnings(metrics)
    )


class DrawdownsInput(CLIModel):
    returns: Path = Field(description="Dated periodic returns table.")
    column: str = Field(default="return", description="Return column.")
    top_n: int = Field(default=5, gt=0, description="Maximum number of episodes.")
    min_depth: float = Field(default=0.0, ge=0, description="Minimum drawdown depth.")


class DrawdownsData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episodes: list[dict] = Field(
        description="Deepest episodes: episode_id, peak, trough, recovery, maxdd, episode_return."
    )
    rows: int = Field(description="Number of reported episodes.")


def drawdowns(args: DrawdownsInput) -> CommandResult:
    from skills.analyze.attribution_counterfactual import find_drawdown_episodes

    result = find_drawdown_episodes(
        _column(args.returns, args.column), top_n=args.top_n, min_depth=args.min_depth
    )
    return CommandResult(data=DrawdownsData(episodes=_records(result), rows=len(result)))


class OverfitInput(CLIModel):
    candidates: Path = Field(description="Date by candidate returns table.")
    tests: list[Literal["dsr", "pbo", "pbo-sensitivity", "spa", "bootstrap", "rolling"]] = Field(
        default_factory=lambda: ["dsr", "pbo"],
        description="Diagnostics: deflated Sharpe, CSCV PBO, PBO split grid, Reality Check "
        "and SPA, block bootstrap of the mean return, rolling metric slices.",
    )
    benchmark_col: str | None = Field(
        default=None, description="Optional benchmark column excluded from candidate tests."
    )
    n_trials: int | None = Field(
        default=None,
        gt=0,
        description="Trial count for the deflated Sharpe; defaults to the candidate column count.",
    )
    benchmark_sr: float = Field(
        default=0.0, description="Benchmark Sharpe for the deflated Sharpe."
    )
    n_splits: int = Field(default=4, gt=1, description="Even number of CSCV blocks for PBO.")
    split_values: list[int] = Field(
        default_factory=lambda: [8, 10, 12, 16],
        description="CSCV block counts for pbo-sensitivity.",
    )
    promotion_threshold: float = Field(
        default=0.2, ge=0, le=1, description="PBO threshold reported by pbo-sensitivity."
    )
    n_bootstrap: int | None = Field(
        default=None,
        gt=0,
        description="Bootstrap replications; defaults per function (spa 500, bootstrap 200).",
    )
    block_size: int = Field(default=20, gt=0, description="Bootstrap block length.")
    seed: int | None = Field(
        default=None, ge=0, description="Random seed; omitted leaves the bootstrap unseeded."
    )
    windows: list[int] = Field(
        default_factory=lambda: [252, 504, 756], description="Rolling metric windows."
    )
    annualization: int = Field(default=252, gt=0, description="Observations per year.")


class OverfitData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: dict[str, Any] = Field(description="Named diagnostic results and table records.")


def overfit(args: OverfitInput) -> CommandResult:
    from skills.analyze.attribution_robustness import (
        block_bootstrap_metric,
        deflated_sharpe_ratio,
        pbo_from_candidate_returns,
        pbo_sensitivity_from_candidate_returns,
        rolling_metric_slices,
    )
    from skills.analyze.attribution_stat_tests import summarize_stat_tests

    frame = read_frame(args.candidates)
    if frame.empty:
        raise ValueError("candidates must contain returns")
    if args.benchmark_col is not None and args.benchmark_col not in frame:
        raise ValueError(f"benchmark column {args.benchmark_col!r} is not in candidates")
    columns = [column for column in frame if column != args.benchmark_col]
    if not columns:
        raise ValueError("candidates must contain at least one non-benchmark column")
    bootstrap = {} if args.n_bootstrap is None else {"n_bootstrap": args.n_bootstrap}
    selected = set(args.tests)
    results: dict[str, Any] = {}
    if "dsr" in selected:
        results["dsr"] = {
            str(column): deflated_sharpe_ratio(
                frame[column],
                n_trials=args.n_trials or len(columns),
                benchmark_sr=args.benchmark_sr,
                annualization=args.annualization,
            )
            for column in columns
        }
    if "pbo" in selected:
        pbo = pbo_from_candidate_returns(
            frame[columns], n_splits=args.n_splits, annualization=args.annualization
        )
        details = pbo.pop("details")
        results["pbo"] = {
            **pbo,
            "details_rows": len(details),
            "details": details.head(args.preview).to_dict(orient="records"),
        }
    if "pbo-sensitivity" in selected:
        results["pbo_sensitivity"] = pbo_sensitivity_from_candidate_returns(
            frame[columns],
            split_values=args.split_values,
            annualization=args.annualization,
            promotion_threshold=args.promotion_threshold,
        ).to_dict(orient="records")
    if "spa" in selected:
        results["spa"] = summarize_stat_tests(
            frame,
            benchmark_col=args.benchmark_col,
            block_size=args.block_size,
            random_state=args.seed,
            **bootstrap,
        ).to_dict(orient="records")
    if "bootstrap" in selected:
        results["bootstrap"] = {
            str(column): block_bootstrap_metric(
                frame[column],
                lambda values: float(values.mean()),
                block_size=args.block_size,
                random_state=args.seed,
                **bootstrap,
            )
            for column in columns
        }
    if "rolling" in selected:
        results["rolling"] = {
            str(column): rolling_metric_slices(
                frame[column], windows=args.windows, annualization=args.annualization
            ).to_dict(orient="records")
            for column in columns
        }
    return CommandResult(data=OverfitData(results=json_safe(results)), warnings=_warnings(results))


class StationarityInput(CLIModel):
    series: Path = Field(description="Dated table such as OHLCV bars or a single series.")
    column: str = Field(default="close", description="Value column to analyze.")
    windows: list[int] = Field(
        default_factory=lambda: [20, 40, 60],
        description="Trailing windows; the analyze_time_series default is 20, 40, 60.",
    )

    @model_validator(mode="after")
    def positive_windows(self):
        if not self.windows or any(window <= 0 for window in self.windows):
            raise ValueError("windows must be positive")
        return self


class StationarityData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    windows: dict[str, dict] = Field(
        description="Hurst, ADF and KPSS diagnostics by trailing window."
    )


def stationarity(args: StationarityInput) -> CommandResult:
    from skills.analyze.ts_analysis import TimeSeriesAnalyzer

    analyzer = TimeSeriesAnalyzer(_column(args.series, args.column))
    analyzer.analyze_windows(args.windows)
    results = {str(window): value for window, value in analyzer.results.items()}
    skipped = [window for window in args.windows if window not in analyzer.results]
    warnings = _warnings(results)
    if skipped:
        warnings.append(f"windows skipped (too short or failed): {skipped}")
    return CommandResult(data=StationarityData(windows=json_safe(results)), warnings=warnings)


class PreflightInput(PanelSource):
    spec_json: Path = Field(
        description="Analyze-native SpecSnapshot JSON file.",
        json_schema_extra={"x-json-file-model": "skills.analyze.contracts:SpecSnapshot"},
    )
    protocol_json: Path = Field(
        description="Analyze-native ProtocolSnapshot JSON file.",
        json_schema_extra={"x-json-file-model": "skills.analyze.contracts:ProtocolSnapshot"},
    )
    allowed_fields: list[str] = Field(
        default_factory=list, description="Optional permitted input columns."
    )


class EvaluateInput(PreflightInput):
    values: Path = Field(
        description="Long factor values on exactly the panel's (symbol, eob) index, e.g. from "
        "`qs compute factor --keep-na`."
    )
    valid_mask: Path | None = Field(
        default=None,
        description="Optional long boolean validity table; defaults to non-missing values.",
    )
    backtest: bool = Field(
        default=True, description="Run the formal backtest section; --no-backtest skips it."
    )
    regime_masks_json: Path | None = Field(
        default=None,
        description="Optional JSON file mapping regime names to long boolean mask tables.",
        json_schema_extra={"x-json-file-model": "skills.analyze.cli:RegimeMasksFile"},
    )
    output: Path | None = Field(
        default=None, description="Optional full AnalyzeResult JSON output."
    )
    overwrite: bool = Field(default=False, description="Replace an existing output file.")


class EvaluationData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    completion_status: str = Field(description="Overall completion status.")
    hard_failed: bool = Field(description="Whether a hard contract failure occurred.")
    sections: dict[str, str] = Field(description="Status of each evaluation section.")
    failed_findings: list[dict] = Field(description="Findings that did not pass.")
    metrics: dict[str, float | int | str | bool | None] = Field(
        description="Available named metrics."
    )


def _snapshot(path, kind):
    from skills.analyze.contracts import ProtocolSnapshot, SpecSnapshot

    raw = read_json(path)
    if not isinstance(raw, dict):
        raise ValueError(f"{kind} JSON must be an object")
    return (SpecSnapshot if kind == "spec" else ProtocolSnapshot)(**raw)


def _summary(result):
    public = result.to_public_dict()
    return EvaluationData(
        completion_status=public["completion_status"],
        hard_failed=result.hard_failed,
        sections={item["name"]: item["status"] for item in public["sections"]},
        failed_findings=[item for item in public["findings"] if not item.get("passed", True)],
        metrics={
            item["name"]: item["value"]
            for item in public["metrics"]
            if item.get("unavailable_reason") is None
        },
    )


def preflight(args: PreflightInput) -> CommandResult:
    from skills.analyze.facade import AnalyzeFacade

    result = AnalyzeFacade().preflight(
        panel=load_panel(args),
        spec=_snapshot(args.spec_json, "spec"),
        protocol=_snapshot(args.protocol_json, "protocol"),
        allowed_fields=args.allowed_fields or None,
    )
    return CommandResult(data=_summary(result), exit_code=1 if result.hard_failed else 0)


def evaluate(args: EvaluateInput) -> CommandResult:
    from skills.analyze.facade import AnalyzeFacade

    if args.output:
        check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    protocol = _snapshot(args.protocol_json, "protocol")
    if protocol.require_prefix_recompute:
        raise ValueError(
            "protocol requires an issued prefix recompute capability, which only the "
            "factor-mining adapter can supply"
        )
    values = _value_series(args.values, names=("value", "fac_val"))
    valid = (
        _value_series(args.valid_mask, names=("valid_mask",)).astype(bool)
        if args.valid_mask
        else values.notna()
    )
    regime_masks = None
    if args.regime_masks_json:
        mapping = read_json(args.regime_masks_json)
        if not isinstance(mapping, dict):
            raise ValueError("regime_masks_json must map names to paths")
        regime_masks = {
            str(name): _value_series(Path(path), names=()).astype(bool)
            for name, path in mapping.items()
        }
    result = AnalyzeFacade().evaluate(
        panel=load_panel(args),
        spec=_snapshot(args.spec_json, "spec"),
        protocol=protocol,
        values=values,
        valid_mask=valid,
        allowed_fields=args.allowed_fields or None,
        include_backtest=args.backtest,
        regime_masks=regime_masks,
    )
    artifacts = (
        [
            write_json(
                result.to_public_dict(),
                args.output,
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="analyze_result",
            )
        ]
        if args.output
        else []
    )
    return CommandResult(
        data=_summary(result), artifacts=artifacts, exit_code=1 if result.hard_failed else 0
    )


COMMANDS = [
    Command(
        "analyze.factor-ic",
        ICInput,
        ICData,
        factor_ic,
        "IC statistics and grouped returns with full_stat.",
        side_effects=("read-only", "writes-output"),
        priority="P0",
    ),
    Command(
        "analyze.ic-surface",
        ICSurfaceInput,
        ICSurfaceData,
        ic_surface,
        "Execution-aligned factor x horizon x lag rank-IC surface with HAC summaries.",
        side_effects=("read-only", "writes-output"),
    ),
    Command(
        "analyze.factor-correlation",
        FactorCorrelationInput,
        FactorCorrelationData,
        factor_correlation,
        "Factor rank-correlation, Top-N overlap and rolling correlation history.",
        side_effects=("read-only", "writes-output"),
    ),
    Command(
        "analyze.perf",
        PerfInput,
        PerfData,
        perf,
        "Scalar performance metrics of a return stream.",
        priority="P0",
    ),
    Command(
        "analyze.drawdowns",
        DrawdownsInput,
        DrawdownsData,
        drawdowns,
        "List peak-to-trough drawdown episodes.",
    ),
    Command(
        "analyze.overfit",
        OverfitInput,
        OverfitData,
        overfit,
        "Deflated Sharpe, PBO, Reality Check/SPA, bootstrap and rolling diagnostics.",
    ),
    Command(
        "analyze.stationarity",
        StationarityInput,
        StationarityData,
        stationarity,
        "Hurst, ADF and KPSS over trailing windows.",
    ),
    Command(
        "analyze.preflight",
        PreflightInput,
        EvaluationData,
        preflight,
        "AnalyzeFacade hard checks of panel, spec and protocol.",
    ),
    Command(
        "analyze.evaluate",
        EvaluateInput,
        EvaluationData,
        evaluate,
        "Deterministic AnalyzeFacade evaluation of precomputed factor values.",
        side_effects=("read-only", "writes-output"),
    ),
]
