"""Agent-facing commands for reusable computation."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skills.cli.io import (
    check_output,
    data_manager,
    factor_function,
    import_function,
    load_panel,
    read_frame,
    resolve_symbols,
    write_frame,
)
from skills.cli.models import CLIError, CLIModel, CommandResult, OutputOptions, PanelSource
from skills.cli.registry import Command


class IndicatorsListInput(CLIModel):
    pass


class IndicatorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="Indicator name.")
    signature: str = Field(description="Callable signature.")
    summary: str = Field(description="First docstring line.")


class IndicatorsListOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    indicators: list[IndicatorItem] = Field(
        description="Public indicators found by discover_indicators."
    )


class IndicatorsShowInput(CLIModel):
    name: str = Field(description="Public indicator name.")


class IndicatorsShowOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="Indicator name.")
    signature: str = Field(description="Callable signature.")
    defaults: dict = Field(description="Keyword parameters and their default values.")
    docstring: str = Field(description="Full indicator documentation.")


def _indicator(name: str):
    return factor_function(indicator=name)


def indicators_list(args: IndicatorsListInput) -> CommandResult:
    from skills.compute.indicators import discover_indicators

    values = [
        IndicatorItem(
            name=name,
            signature=str(inspect.signature(func)),
            summary=(inspect.getdoc(func) or "").split("\n")[0],
        )
        for name, func in sorted(discover_indicators().items())
    ]
    return CommandResult(data=IndicatorsListOutput(indicators=values))


def indicators_show(args: IndicatorsShowInput) -> CommandResult:
    func = _indicator(args.name)
    signature = inspect.signature(func)
    return CommandResult(
        data=IndicatorsShowOutput(
            name=args.name,
            signature=str(signature),
            defaults={
                name: parameter.default
                for name, parameter in signature.parameters.items()
                if parameter.default is not inspect.Parameter.empty
            },
            docstring=inspect.getdoc(func) or "",
        )
    )


class FactorInput(PanelSource, OutputOptions):
    output: Path = Field(description="Destination factor table; values never go to stdout.")
    indicator: str | None = Field(default=None, description="Public indicator name.")
    function: str | None = Field(
        default=None,
        description="Importable module:name callable, e.g. a generated mined factor.",
    )
    params: dict = Field(default_factory=dict, description="Factor keyword parameters.")
    call: Literal["per-symbol", "panel"] = Field(
        default="per-symbol",
        description="per-symbol: Factor(func, **params).calculate on each symbol; "
        "panel: func(panel, **params) must return a Series aligned to the panel.",
    )
    keep_na: bool = Field(default=False, description="Keep warm-up NaN rows (Factor dropna=False).")
    layout: Literal["long", "wide"] = Field(
        default="long",
        description="long: symbol, eob, value columns; wide: eob x symbol like Factor.cal_df.",
    )

    @model_validator(mode="after")
    def validate_source(self):
        if bool(self.indicator) == bool(self.function):
            raise ValueError("Exactly one of indicator or function is required")
        return self


class FactorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="Factor name in Factor wrapper form, e.g. roc(period=20).")
    rows: int = Field(description="Number of output table rows.")
    symbols: list[str] = Field(description="Input symbols.")
    start: str | None = Field(description="Earliest factor timestamp.")
    end: str | None = Field(description="Latest factor timestamp.")
    nan_ratio: float = Field(description="Fraction of missing factor values.")
    output: str = Field(description="Output artifact path.")


def factor(args: FactorInput) -> CommandResult:
    import pandas as pd

    from skills.compute.wrappers import Factor

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    func = _indicator(args.indicator) if args.indicator else import_function(args.function)
    panel = load_panel(args)
    wrapper = Factor(func, **args.params)
    if args.call == "per-symbol":
        values = wrapper.calculate(panel, dropna=not args.keep_na)
    else:
        values = func(panel, **args.params)
        if not isinstance(values, pd.Series) or not values.index.equals(panel.index):
            raise CLIError(
                "INVALID_INPUT", "Panel callable must return a Series aligned to the panel"
            )
        values = values.astype("float64")
        if not args.keep_na:
            values = values.dropna()
    values = values.rename("value")
    frame = values.reset_index() if args.layout == "long" else values.unstack("symbol").sort_index()
    artifact = write_frame(
        frame, args.output, overwrite=args.overwrite, data_root=args.data_root, name="factor"
    )
    times = values.index.get_level_values("eob")
    return CommandResult(
        data=FactorOutput(
            name=wrapper.name,
            rows=len(frame),
            symbols=sorted(panel.index.get_level_values("symbol").unique().tolist()),
            start=str(times.min()) if len(times) else None,
            end=str(times.max()) if len(times) else None,
            nan_ratio=float(values.isna().mean()) if len(values) else 0.0,
            output=artifact.path,
        ),
        artifacts=[artifact],
    )


class FeaturesInput(PanelSource, OutputOptions):
    output: Path = Field(description="Destination (symbol, eob) feature table.")
    factors: list[str] = Field(
        default_factory=lambda: ["open", "close", "high", "low"],
        description="OHLC columns paired in log differences.",
    )
    lags: list[int] = Field(
        default_factory=lambda: [1, 2, 3, 4, 5, 10, 15, 20, 25],
        description="Lags of the right-hand price.",
    )
    shifts: list[int] | None = Field(
        default=None, description="Feature shifts; defaults to default_logdiff_shifts(lookback)."
    )
    lookback: int = Field(default=5, gt=0, description="Lookback used for default shifts.")


class FeaturesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: int = Field(description="Model-ready feature rows (non-finite rows dropped).")
    features: int = Field(description="Feature column count.")
    symbols: list[str] = Field(description="Symbols with feature rows.")
    start: str | None = Field(description="Earliest feature timestamp.")
    end: str | None = Field(description="Latest feature timestamp.")
    output: str = Field(description="Output artifact path.")


def features(args: FeaturesInput) -> CommandResult:
    from skills.compute.features import make_logdiff_panel_features

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    result = make_logdiff_panel_features(
        load_panel(args),
        factors=args.factors,
        lags=args.lags,
        shifts=args.shifts,
        lookback=args.lookback,
    )
    artifact = write_frame(
        result, args.output, overwrite=args.overwrite, data_root=args.data_root, name="features"
    )
    times = result.index.get_level_values("eob")
    return CommandResult(
        data=FeaturesOutput(
            rows=len(result),
            features=result.shape[1],
            symbols=sorted(result.index.get_level_values("symbol").unique().tolist()),
            start=str(times.min()) if len(times) else None,
            end=str(times.max()) if len(times) else None,
            output=artifact.path,
        ),
        # A 1440-column list would dominate the envelope; columns follow the logdiff naming rule.
        artifacts=[artifact.model_copy(update={"columns": []})],
    )


class ForwardInput(OutputOptions):
    output: Path = Field(description="Destination label table.")
    bars: Path = Field(description="Single-symbol OHLCV file with a close column.")
    horizon: int = Field(default=1, gt=0, description="Forward bar horizon.")
    up_threshold: float = Field(default=0.0, description="Label 1 above this forward return.")
    down_threshold: float = Field(default=0.0, description="Label -1 below minus this magnitude.")


class BarrierInput(OutputOptions):
    output: Path = Field(description="Destination label table.")
    bars: Path = Field(description="Single-symbol OHLCV file with a close column.")
    lookback: int = Field(default=5, gt=0, description="Volatility scaling horizon (L).")
    pt_sl: float = Field(default=1.0, gt=0, description="Profit and stop volatility multiplier.")
    t_limit: int = Field(default=10, gt=0, description="Maximum holding bars.")


class FrameOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: int = Field(description="Output rows.")
    columns: list[str] = Field(description="Output columns.")
    output: str = Field(description="Output artifact path.")


def _write_labels(args, frame, name):
    artifact = write_frame(
        frame, args.output, overwrite=args.overwrite, data_root=args.data_root, name=name
    )
    return CommandResult(
        data=FrameOutput(rows=len(frame), columns=list(frame.columns), output=artifact.path),
        artifacts=[artifact],
    )


def forward_return(args: ForwardInput) -> CommandResult:
    from skills.compute.label_maker import ForwardReturnLabelMaker

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    labels = ForwardReturnLabelMaker(
        data=read_frame(args.bars),
        horizon=args.horizon,
        up_threshold=args.up_threshold,
        down_threshold=args.down_threshold,
    ).generate_labels()
    return _write_labels(args, labels, "labels")


def triple_barrier(args: BarrierInput) -> CommandResult:
    from skills.compute.label_maker import TripleBarrierLabelMaker

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    labels = TripleBarrierLabelMaker(
        data=read_frame(args.bars), L=args.lookback, pt_sl=args.pt_sl, t_limit=args.t_limit
    ).generate_labels()
    return _write_labels(args, labels, "labels")


class ResampleInput(OutputOptions):
    output: Path = Field(description="Destination 5-minute table.")
    input: Path = Field(description="A-share one-minute OHLCV file with an eob index or column.")


def resample(args: ResampleInput) -> CommandResult:
    from skills.compute.resample import resample_to_5m

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    result = resample_to_5m(read_frame(args.input))
    artifact = write_frame(
        result, args.output, overwrite=args.overwrite, data_root=args.data_root, name="bars_5m"
    )
    return CommandResult(
        data=FrameOutput(rows=len(result), columns=list(result.columns), output=artifact.path),
        artifacts=[artifact],
    )


class AdjustInput(CLIModel):
    symbols: list[str] = Field(description="QuantSpace symbols with raw bars and adj_factor files.")
    frequency: str = Field(default="1d", description="Raw market store directory, e.g. 1d or 1m.")
    output: Path | None = Field(
        default=None, description="Output file for exactly one symbol, outside managed storage."
    )
    write: bool = Field(
        default=False,
        description="Write <frequency>_adj files into managed market storage; otherwise a dry run.",
    )
    overwrite: bool = Field(default=False, description="Allow replacing existing output.")
    data_root: Path | None = Field(
        default=None,
        description="Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/.",
    )


class AdjustOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbols: list[str] = Field(description="Processed symbols.")
    rows: int = Field(description="Total adjusted rows.")
    saved: bool = Field(description="Whether adjusted data was written.")
    dry_run: bool = Field(description="Whether no output was written.")
    target_frequency: str = Field(description="Adjusted market store directory.")
    planned_paths: list[str] = Field(description="Absolute output paths for the requested symbols.")
    unadjusted: list[str] = Field(
        description="Symbols without adj_factor events; load_adjusted copies their raw bars."
    )


def adjust(args: AdjustInput) -> CommandResult:
    from skills.compute.adjust import load_adjusted

    dm = data_manager(args.data_root)
    symbols = resolve_symbols(args.symbols)
    if not symbols:
        raise CLIError("INVALID_INPUT", "symbols are required")
    if args.output and args.write:
        raise CLIError("INVALID_INPUT", "choose --output or --write, not both")
    if args.output and len(symbols) != 1:
        raise CLIError("INVALID_INPUT", "--output takes exactly one symbol; use --write for many")
    target_frequency = f"{args.frequency}_adj"
    managed = [dm.root / "market" / target_frequency / f"{symbol}.parquet" for symbol in symbols]
    raw_missing = [
        symbol
        for symbol in symbols
        if not (dm.root / "market" / args.frequency / f"{symbol}.parquet").exists()
    ]
    if raw_missing:
        raise CLIError(
            "NOT_FOUND",
            f"Missing {args.frequency} raw bars for symbols: {raw_missing}",
            3,
            details=raw_missing,
        )
    adjusted = set(dm.list_adj_factors())
    unadjusted = [symbol for symbol in symbols if symbol not in adjusted]
    warnings = (
        [f"No adj_factor events for {unadjusted}; their output equals the raw bars."]
        if unadjusted
        else []
    )
    if not args.write and not args.output:
        return CommandResult(
            data=AdjustOutput(
                symbols=symbols,
                rows=0,
                saved=False,
                dry_run=True,
                target_frequency=target_frequency,
                planned_paths=[str(path.resolve()) for path in managed],
                unadjusted=unadjusted,
            ),
            warnings=warnings,
        )
    if args.write:
        existing = [symbol for symbol, path in zip(symbols, managed) if path.exists()]
        if existing and not args.overwrite:
            raise CLIError(
                "CONFLICT",
                f"Adjusted files already exist: {existing}; use --overwrite",
                details=existing,
            )
        paths = managed
    else:
        paths = [check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)]
    artifacts = []
    total = 0
    for symbol, path in zip(symbols, paths):
        result = load_adjusted(symbol, frequency=args.frequency, data_root=str(dm.root))
        if args.write:
            dm.save_symbol(symbol, result, frequency=target_frequency, source="adjust")
        else:
            artifacts.append(
                write_frame(
                    result, path, overwrite=args.overwrite, data_root=args.data_root, name=symbol
                )
            )
        total += len(result)
    return CommandResult(
        data=AdjustOutput(
            symbols=symbols,
            rows=total,
            saved=True,
            dry_run=False,
            target_frequency=target_frequency,
            planned_paths=[str(Path(path).resolve()) for path in paths],
            unadjusted=unadjusted,
        ),
        artifacts=artifacts,
        warnings=warnings,
    )


COMMANDS = [
    Command(
        "compute.indicators.list",
        IndicatorsListInput,
        IndicatorsListOutput,
        indicators_list,
        "List public indicators with signatures.",
        priority="P0",
    ),
    Command(
        "compute.indicators.show",
        IndicatorsShowInput,
        IndicatorsShowOutput,
        indicators_show,
        "Show one indicator's signature, defaults, and docstring.",
        priority="P0",
        positional=("name",),
    ),
    Command(
        "compute.factor",
        FactorInput,
        FactorOutput,
        factor,
        "Calculate an indicator or module:name factor on a panel.",
        side_effects=("writes-output",),
        priority="P0",
    ),
    Command(
        "compute.features",
        FeaturesInput,
        FeaturesOutput,
        features,
        "Build model-ready OHLC log-difference features for a panel.",
        side_effects=("writes-output",),
    ),
    Command(
        "compute.labels.forward-return",
        ForwardInput,
        FrameOutput,
        forward_return,
        "Create forward-return threshold labels for one symbol.",
        side_effects=("writes-output",),
    ),
    Command(
        "compute.labels.triple-barrier",
        BarrierInput,
        FrameOutput,
        triple_barrier,
        "Create triple-barrier labels for one symbol.",
        side_effects=("writes-output",),
    ),
    Command(
        "compute.resample",
        ResampleInput,
        FrameOutput,
        resample,
        "Resample A-share one-minute bars to five-minute bars.",
        side_effects=("writes-output",),
    ),
    Command(
        "compute.adjust",
        AdjustInput,
        AdjustOutput,
        adjust,
        "Forward-adjust stored raw bars with adj_factor events.",
        side_effects=("writes-output", "writes-store"),
    ),
]
