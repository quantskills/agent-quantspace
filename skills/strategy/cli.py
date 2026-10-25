"""Target-weight construction commands over reusable strategy types."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skills.cli.io import (
    check_output,
    factor_function,
    frame_summary,
    import_function,
    json_safe,
    load_panel,
    read_frame,
    resolve_symbols,
    write_frame,
    write_json,
)
from skills.cli.models import CLIError, CommandResult, OutputOptions, PanelSource
from skills.cli.registry import Command

CONDITION_OPS = {
    "lt": lambda values, bound: values < bound,
    "le": lambda values, bound: values <= bound,
    "gt": lambda values, bound: values > bound,
    "ge": lambda values, bound: values >= bound,
}


class WeightsData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: int = Field(description="Number of dates.")
    columns: list[str] = Field(description="Symbol columns.")
    start: str | None = Field(description="First date.")
    end: str | None = Field(description="Last date.")
    preview: list[dict] = Field(description="First weight rows.")


def _write_weights(args, weights, name="weights"):
    artifact = write_frame(
        weights, args.output, overwrite=args.overwrite, data_root=args.data_root, name=name
    )
    return CommandResult(
        data=WeightsData(**frame_summary(weights, preview=args.preview)), artifacts=[artifact]
    )


class TopNInput(OutputOptions):
    output: Path = Field(description="Destination target-weight table.")
    scores: Path = Field(description="Date by symbol score table; higher is better.")
    top_n: int = Field(gt=0, description="Names held per date.")
    gross_exposure: float = Field(default=1.0, ge=0, description="Total weight per date.")


def top_n(args: TopNInput) -> CommandResult:
    from skills.strategy.cross_sectional import top_n_weights

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    weights = top_n_weights(
        read_frame(args.scores), top_n=args.top_n, gross_exposure=args.gross_exposure
    )
    return _write_weights(args, weights)


class SignalWeightsInput(OutputOptions):
    output: Path = Field(description="Destination one-column target-weight table.")
    signal: Path = Field(description="Signal table with an eob index or column.")
    column: str = Field(
        default="signal", description="Signal column; values are clipped to [-1, 1]."
    )
    symbol: str = Field(description="QuantSpace symbol that receives the weights.")
    exposure: float = Field(default=1.0, description="Weight multiplier.")


def signal_weights(args: SignalWeightsInput) -> CommandResult:
    from skills.strategy.time_series import signal_to_single_asset_weights

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    table = read_frame(args.signal)
    if args.column not in table.columns:
        raise CLIError("INVALID_INPUT", f"Signal table has no column {args.column!r}")
    weights = signal_to_single_asset_weights(
        table[args.column], symbol=resolve_symbols([args.symbol])[0], exposure=args.exposure
    )
    return _write_weights(args, weights)


class HoldInput(PanelSource, OutputOptions):
    output: Path = Field(description="Destination daily target-weight table.")
    weights: Path = Field(description="Signal-day target weights (date by symbol).")


def hold_calendar(args: HoldInput) -> CommandResult:
    from skills.strategy.cross_sectional import hold_weights_on_calendar

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    panel = load_panel(args)
    dates = panel.index.get_level_values("eob").unique().sort_values()
    symbols = panel.index.get_level_values("symbol").unique()
    weights = hold_weights_on_calendar(read_frame(args.weights), dates=dates, symbols=symbols)
    return _write_weights(args, weights)


class CombineInput(OutputOptions):
    factors: dict[str, Path] = Field(
        description="Raw factor tables by name, each date by symbol, e.g. mom=mom.parquet."
    )
    directions: dict[str, int] = Field(
        description="Direction for every factor: 1 if larger is better, -1 otherwise."
    )
    method: Literal[
        "equal_rank", "equal_vote", "rolling_ic", "rolling_icir", "max_ic", "max_icir"
    ] = Field(description="Combination method.")
    normalization: Literal["rank", "zscore"] = Field(
        default="rank", description="Daily cross-sectional normalization."
    )
    top_n: int = Field(default=3, gt=0, description="Assets selected from the composite score.")
    ic_history: Path | None = Field(
        default=None,
        description="IC of direction-oriented factors (pass --directions to analyze ic-surface); "
        "required by rolling and max methods. Either a date by factor table, or the tidy "
        "daily_ic table written by analyze ic-surface (factor, horizon, lag, eob, ic), which "
        "also needs --ic-horizon.",
    )
    ic_horizon: int | None = Field(
        default=None,
        description="Horizon of the tidy daily_ic rows to use; required for a tidy --ic-history "
        "and rejected for a wide one.",
    )
    ic_lag: int = Field(
        default=0, ge=0, description="Lag of the tidy daily_ic rows to use (tidy input only)."
    )
    correlation_history: Path | None = Field(
        default=None,
        description="Tidy table with eob, factor_a, factor_b, correlation, computed on "
        "direction-oriented ranked factors (analyze factor-correlation --directions writes it); "
        "required by max methods.",
    )
    availability_delay: int | None = Field(
        default=None,
        ge=0,
        description="Bars before an IC becomes known (signal_lag + horizon); required by "
        "rolling and max methods.",
    )
    lookback: int = Field(default=252, gt=0, description="Rolling IC window.")
    min_periods: int = Field(default=126, gt=0, description="Minimum IC observations.")
    max_weight: float = Field(default=0.5, gt=0, le=1, description="Cap on one factor's weight.")
    correlation_shrinkage: float = Field(
        default=0.5, ge=0, le=1, description="Shrink factor correlations toward identity."
    )
    out_dir: Path = Field(
        description="Directory for factor_weights, composite_scores and target_weights Parquet files."
    )

    @model_validator(mode="after")
    def check_inputs(self):
        if not self.factors:
            raise ValueError("factors cannot be empty")
        if self.method not in ("equal_rank", "equal_vote") and self.availability_delay is None:
            raise ValueError(f"{self.method} requires availability_delay")
        if self.ic_history is None and self.ic_horizon is not None:
            raise ValueError("ic_horizon requires ic_history")
        return self


class CombineData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: str = Field(description="Combination method.")
    factors: list[str] = Field(description="Combined factor names.")
    rows: int = Field(description="Number of dates.")
    start: str | None = Field(description="First date.")
    end: str | None = Field(description="Last date.")
    latest_factor_weights: dict[str, float | None] = Field(
        description="Factor weights on the last date."
    )


def _read_tidy(path):
    """Read a long table and keep eob as a column."""
    frame = read_frame(path)
    return frame.reset_index() if frame.index.name == "eob" else frame


TIDY_IC_COLUMNS = {"factor", "horizon", "lag", "ic"}


def _read_ic_history(args):
    """Read --ic-history as a wide date by factor table, pivoting a tidy daily_ic first."""
    frame = read_frame(args.ic_history)
    if not TIDY_IC_COLUMNS.issubset(frame.columns):
        if args.ic_horizon is not None or args.ic_lag != 0:
            raise CLIError(
                "INVALID_INPUT",
                "ic_horizon and ic_lag only apply to a tidy daily_ic table "
                "(columns factor, horizon, lag, eob, ic); this ic_history is a wide table",
            )
        return frame
    if frame.index.name == "eob":
        frame = frame.reset_index()
    if "eob" not in frame.columns:
        raise CLIError("INVALID_INPUT", "tidy ic_history requires an eob column")
    if args.ic_horizon is None:
        horizons = sorted(frame["horizon"].unique().tolist())
        raise CLIError(
            "INVALID_INPUT",
            f"tidy ic_history requires --ic-horizon; available horizons: {horizons}",
        )
    chosen = frame[(frame["horizon"] == args.ic_horizon) & (frame["lag"] == args.ic_lag)]
    if chosen.empty:
        available = sorted(
            {
                (int(h), int(lag))
                for h, lag in frame[["horizon", "lag"]].drop_duplicates().to_numpy()
            }
        )
        raise CLIError(
            "INVALID_INPUT",
            f"ic_history has no rows for horizon={args.ic_horizon} lag={args.ic_lag}; "
            f"available (horizon, lag): {available}",
        )
    if chosen.duplicated(["eob", "factor"]).any():
        raise CLIError(
            "INVALID_INPUT",
            f"ic_history has duplicated (eob, factor) rows for horizon={args.ic_horizon} "
            f"lag={args.ic_lag}",
        )
    wide = chosen.pivot(index="eob", columns="factor", values="ic").sort_index()
    wide.columns.name = None
    missing = sorted(set(args.factors) - set(wide.columns))
    if missing:
        raise CLIError("INVALID_INPUT", f"ic_history has no IC for factors: {missing}")
    return wide


def combine(args: CombineInput) -> CommandResult:
    from skills.strategy.cross_sectional import DynamicFactorWeightConfig, combine_factor_scores

    paths = {
        name: args.out_dir / f"{name}.parquet"
        for name in ("factor_weights", "composite_scores", "target_weights")
    }
    for path in paths.values():
        check_output(path, overwrite=args.overwrite, data_root=args.data_root)
    ic_history = _read_ic_history(args) if args.ic_history else None
    dynamic = (
        None
        if args.availability_delay is None
        else DynamicFactorWeightConfig(
            availability_delay=args.availability_delay,
            lookback=args.lookback,
            min_periods=args.min_periods,
            max_weight=args.max_weight,
            correlation_shrinkage=args.correlation_shrinkage,
        )
    )
    result = combine_factor_scores(
        {name: read_frame(path) for name, path in args.factors.items()},
        method=args.method,
        directions=args.directions,
        normalization=args.normalization,
        top_n=args.top_n,
        ic_history=ic_history,
        correlation_history=_read_tidy(args.correlation_history)
        if args.correlation_history
        else None,
        dynamic_config=dynamic,
    )
    artifacts = [
        write_frame(
            getattr(result, name),
            path,
            overwrite=args.overwrite,
            data_root=args.data_root,
            name=name,
        )
        for name, path in paths.items()
    ]
    targets = result.target_weights
    summary = frame_summary(targets, preview=0)
    latest = result.factor_weights.iloc[-1].to_dict() if len(result.factor_weights) else {}
    return CommandResult(
        data=CombineData(
            method=args.method,
            factors=list(args.factors),
            rows=summary["rows"],
            start=summary["start"],
            end=summary["end"],
            latest_factor_weights=json_safe(latest),
        ),
        artifacts=artifacts,
    )


class FactorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    indicator: str | None = Field(default=None, description="Public skills.compute indicator name.")
    function: str | None = Field(
        default=None, description="Importable module:name factor callable."
    )
    params: dict = Field(default_factory=dict, description="Factor keyword arguments.")
    name: str | None = Field(
        default=None, description="Factor name; defaults to the function name."
    )
    direction: Literal[-1, 1] = Field(
        default=1, description="1 ranks larger values first, -1 smaller."
    )

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.indicator) == bool(self.function):
            raise ValueError("Exactly one of indicator or function is required")
        return self


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["lt", "le", "gt", "ge"] = Field(description="Comparison applied to filter values.")
    value: float = Field(description="Comparison bound.")


class ExitFilterItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    function: str = Field(
        description="Importable module:name filter, e.g. "
        "skills.strategy.cross_sectional.exits:drawdown_from_high_filter."
    )
    params: dict = Field(default_factory=dict, description="Filter keyword arguments.")
    name: str | None = Field(default=None, description="Filter name.")
    condition: Condition | None = Field(
        default=None,
        description="Keep a position while the condition holds; omitted keeps values >= 0, "
        "the backtester default.",
    )


class CsRunInput(PanelSource):
    start: str | None = Field(
        None,
        description="First result date (start_date); earlier bars still load. "
        "Pass a trimmed --panel from `qs store read` to limit history.",
    )
    end: str | None = Field(
        None,
        description="Last result date (end_date); later bars still load. "
        "Pass a trimmed --panel from `qs store read` to limit history.",
    )
    factors: list[FactorItem] = Field(description="Entry factors voted into the Top-pct selection.")
    exit_filters: list[ExitFilterItem] = Field(
        default_factory=list, description="Exit filters applied to selected weights."
    )
    top_pct: float = Field(default=0.2, gt=0, le=1, description="Fraction of names selected.")
    trade_at: Literal["open", "close"] = Field(
        default="close", description="Execution price field."
    )
    signal_lag: int = Field(default=1, ge=0, description="Bars between signal and execution.")
    commission: float = Field(default=0.0002, ge=0, description="One-way commission rate.")
    slippage_bp: float = Field(ge=0, description="One-way slippage in basis points.")
    rebalance_freq: str = Field(
        default="1", description="D, W, M, or a positive number of bars between rebalances."
    )
    weight_method: Literal["equal", "risk_parity", "inverse_variance", "epo"] = Field(
        default="equal", description="WEIGHT_METHODS key for selected names."
    )
    vol_target: float | None = Field(default=None, gt=0, description="Optional volatility target.")
    exposure_policy: Literal["keep_cash", "renormalize", "allocate_defensive"] = Field(
        default="keep_cash", description="What happens to weight removed by exit filters."
    )
    defensive_symbols: list[str] = Field(
        default_factory=list, description="Symbols for the allocate_defensive policy."
    )
    out_dir: Path | None = Field(
        default=None,
        description="Optional directory for signal_weights, executed_weights, result Parquet "
        "files and metrics.json.",
    )
    overwrite: bool = Field(
        default=False, description="Allow replacement of existing output files."
    )


class CsRunData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metrics: dict[str, float | None] = Field(
        description="ModularBacktester.metrics, unchanged; nonfinite values become null."
    )
    weight_stats: dict[str, int] = Field(description="Days with positive signal weight per symbol.")
    rows: int = Field(description="Number of result dates.")
    start: str | None = Field(description="First result date.")
    end: str | None = Field(description="Last result date.")


def _factor_configs(items):
    configs = []
    for item in items:
        func = factor_function(item.indicator, item.function)
        config = {"func": func, "kwargs": dict(item.params), "direction": item.direction}
        if item.name:
            config["name"] = item.name
        configs.append(config)
    return configs


def _exit_configs(items):
    configs = []
    for item in items:
        config = {"func": import_function(item.function), "kwargs": dict(item.params)}
        if item.name:
            config["name"] = item.name
        if item.condition is not None:
            op, bound = CONDITION_OPS[item.condition.op], item.condition.value
            config["condition"] = lambda values, _op=op, _bound=bound: _op(values, _bound)
        configs.append(config)
    return configs


def cs_run(args: CsRunInput) -> CommandResult:
    from skills.strategy.cross_sectional import ModularBacktester

    names = ("signal_weights", "executed_weights", "result_df")
    paths = {name: args.out_dir / f"{name}.parquet" for name in names} if args.out_dir else {}
    if args.out_dir:
        paths["metrics"] = args.out_dir / "metrics.json"
    for path in paths.values():
        check_output(path, overwrite=args.overwrite, data_root=args.data_root)
    backtester = ModularBacktester(
        # start/end bound the result frame only; factors keep their warm-up history.
        load_panel(args.model_copy(update={"start": None, "end": None})),
        _factor_configs(args.factors),
        top_pct=args.top_pct,
        trade_at=args.trade_at,
        signal_lag=args.signal_lag,
        commission=args.commission,
        slippage_bp=args.slippage_bp,
        start_date=args.start,
        end_date=args.end,
        exit_filters=_exit_configs(args.exit_filters),
        rebalance_freq=args.rebalance_freq,
        weight_method=args.weight_method,
        vol_target=args.vol_target,
        exposure_policy=args.exposure_policy,
        defensive_symbols=resolve_symbols(args.defensive_symbols),
    )
    result_df = backtester.run()
    metrics = json_safe(backtester.metrics)
    artifacts = []
    if paths:
        frames = {
            "signal_weights": backtester.signal_weights,
            "executed_weights": backtester.executed_weights,
            "result_df": result_df,
        }
        artifacts = [
            write_frame(
                frames[name],
                paths[name],
                overwrite=args.overwrite,
                data_root=args.data_root,
                name=name,
            )
            for name in names
        ]
        artifacts.append(
            write_json(
                {"metrics": metrics},
                paths["metrics"],
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="metrics",
            )
        )
    summary = frame_summary(result_df, preview=0)
    return CommandResult(
        data=CsRunData(
            metrics=metrics,
            weight_stats={str(k): int(v) for k, v in backtester.get_weight_stats().items()},
            rows=summary["rows"],
            start=summary["start"],
            end=summary["end"],
        ),
        artifacts=artifacts,
        warnings=["nonfinite metrics were converted to null"]
        if any(value is None for value in metrics.values())
        else [],
    )


COMMANDS = [
    Command(
        "strategy.top-n",
        TopNInput,
        WeightsData,
        top_n,
        "Equal-weight the top N scores on each date.",
        side_effects=("writes-output",),
    ),
    Command(
        "strategy.signal-weights",
        SignalWeightsInput,
        WeightsData,
        signal_weights,
        "Turn a single-asset signal into target weights.",
        side_effects=("writes-output",),
    ),
    Command(
        "strategy.hold-calendar",
        HoldInput,
        WeightsData,
        hold_calendar,
        "Forward-hold signal-day weights across a panel's trading calendar.",
        side_effects=("writes-output",),
    ),
    Command(
        "strategy.combine",
        CombineInput,
        CombineData,
        combine,
        "Combine raw factors into composite scores and Top-N weights.",
        side_effects=("writes-output",),
    ),
    Command(
        "strategy.cs-run",
        CsRunInput,
        CsRunData,
        cs_run,
        "Run a factor-voting Top-pct cross-sectional strategy with ModularBacktester.",
        side_effects=("writes-output",),
    ),
]
