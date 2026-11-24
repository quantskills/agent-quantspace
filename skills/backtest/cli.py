"""File-based portfolio execution and construction commands."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skills.cli.io import (
    check_output,
    frame_summary,
    json_safe,
    load_panel,
    read_frame,
    write_frame,
    write_json,
)
from skills.cli.models import CLIError, CLIModel, CommandResult, OutputOptions, PanelSource
from skills.cli.registry import Command


def _has_panel_source(args) -> bool:
    return args.panel is not None or bool(args.symbols) or args.symbols_file is not None


def _close_returns(args):
    """Daily close-to-close returns (date x symbol) from a panel source."""
    close = load_panel(args)["close"].unstack("symbol").sort_index()
    return close, close.pct_change(fill_method=None)


class RunInput(PanelSource):
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
    weights: Path = Field(description="Date by symbol target weights table (eob index or column).")
    commission: float = Field(ge=0, description="One-way commission rate, e.g. 0.0002.")
    slippage_bp: float = Field(ge=0, description="One-way slippage in basis points.")
    trade_at: Literal["open", "close"] = Field(
        default="close", description="Execution price field."
    )
    signal_lag: int = Field(default=1, ge=0, description="Bars between signal and execution.")
    enforce_trade_constraints: bool = Field(
        default=False,
        description="Apply suspension and limit masks; the panel needs is_suspended, "
        "is_limit_up and is_limit_down.",
    )
    unit: Literal["percent", "lots"] = Field(
        default="percent",
        description="Unit of --weights: percent (share of capital) or lots (a futures lot is "
        "one contract, a stock or fund lot 100 shares; whole numbers).",
    )
    capital: float | None = Field(
        default=None, gt=0, description="Starting capital; required with --unit lots."
    )
    multipliers: Path | None = Field(
        default=None,
        description="JSON object of contract multipliers by --weights symbol; required for "
        "futures with --unit lots (a continuous symbol takes its product's multiplier).",
    )
    contracts: Path | None = Field(
        default=None,
        description="Lots: trading day by continuous symbol table of actual contracts. "
        "Default: the stored dominant tables (qs ingest contracts); with --symbols the "
        "contracts they name are loaded too.",
    )
    adjusted_frequency: str | None = Field(
        default=None,
        description="Lots: store directory with post-adjusted bars of the stocks and funds "
        "(for example 1d_adj), so dividends count; required when --weights holds them.",
    )
    out_dir: Path | None = Field(
        default=None,
        description="Optional directory for result.parquet, executed_weights.parquet and "
        "metrics.json (plus executed_lots.parquet with --unit lots).",
    )
    overwrite: bool = Field(
        default=False, description="Allow replacement of existing output files."
    )

    @model_validator(mode="after")
    def check_unit_options(self):
        lots_only = [
            name
            for name in ("capital", "multipliers", "contracts", "adjusted_frequency")
            if getattr(self, name) is not None
        ]
        if self.unit == "percent" and lots_only:
            raise ValueError(f"{', '.join(lots_only)} only apply to --unit lots")
        if self.unit == "lots" and self.capital is None:
            raise ValueError("--unit lots needs --capital")
        return self


def _lots_inputs(args: RunInput, weights) -> dict:
    """The panel and the lots-only options of VectorBacktester for --unit lots."""
    import pandas as pd

    from skills.backtest.units import is_continuous_future, is_futures_symbol
    from skills.cli.io import data_manager, read_json, resolve_symbols

    continuous = [str(symbol) for symbol in weights.columns if is_continuous_future(symbol)]
    contracts = None
    if continuous:
        if args.contracts is not None:
            contracts = read_frame(args.contracts)
            if "date" in contracts.columns:
                contracts = contracts.set_index("date")
            contracts.index = pd.to_datetime(contracts.index)
        else:
            contracts = data_manager(args.data_root).read_dominant(continuous)
    source = args.model_copy(update={"start": None, "end": None})
    if contracts is not None and args.panel is None:
        named = sorted({str(code) for code in contracts.stack().dropna().unique()})
        symbols = resolve_symbols(args.symbols, args.symbols_file)
        extra = [code for code in named if code not in symbols]
        source = source.model_copy(update={"symbols": [*symbols, *extra], "symbols_file": None})
    adjusted = None
    stocks = [str(symbol) for symbol in weights.columns if not is_futures_symbol(symbol)]
    if stocks and args.adjusted_frequency:
        adjusted = data_manager(args.data_root).read_symbols(
            stocks, frequency=args.adjusted_frequency
        )
    multipliers = read_json(args.multipliers) if args.multipliers else None
    if multipliers is not None and not isinstance(multipliers, dict):
        raise CLIError("INVALID_INPUT", "--multipliers must be a JSON object")
    return {
        "data": load_panel(source),
        "unit": "lots",
        "capital": args.capital,
        "multipliers": multipliers,
        "contracts": contracts,
        "adjusted": adjusted,
    }


class RunData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metrics: dict[str, float | None] = Field(
        description="BacktestResult.metrics, unchanged; nonfinite values become null."
    )
    annual_returns: dict[str, float | None] = Field(
        description="Calendar-year compounded returns from annual_return_metrics."
    )
    activity: dict[str, float | None] = Field(
        description="Trade days and active-day ratio from activity_metrics."
    )
    rows: int = Field(description="Number of result dates.")
    start: str | None = Field(description="First result date.")
    end: str | None = Field(description="Last result date.")


def run(args: RunInput) -> CommandResult:
    from skills.backtest import VectorBacktester, activity_metrics, annual_return_metrics

    paths = (
        {
            "result_df": args.out_dir / "result.parquet",
            "executed_weights": args.out_dir / "executed_weights.parquet",
            "metrics": args.out_dir / "metrics.json",
        }
        if args.out_dir
        else {}
    )
    if args.out_dir and args.unit == "lots":
        paths["executed_lots"] = args.out_dir / "executed_lots.parquet"
    for path in paths.values():
        check_output(path, overwrite=args.overwrite, data_root=args.data_root)
    weights = read_frame(args.weights)
    # start/end bound the result frame only; execution keeps the full price history.
    if args.unit == "lots":
        options = _lots_inputs(args, weights)
    else:
        options = {"data": load_panel(args.model_copy(update={"start": None, "end": None}))}
    result = VectorBacktester(
        trade_at=args.trade_at,
        signal_lag=args.signal_lag,
        commission=args.commission,
        slippage_bp=args.slippage_bp,
        start_date=args.start,
        end_date=args.end,
        enforce_trade_constraints=args.enforce_trade_constraints,
        **options,
    ).run(weights)
    metrics = json_safe(result.metrics)
    annual = json_safe(annual_return_metrics(result.result_df))
    activity = json_safe(activity_metrics(result.result_df))
    info = frame_summary(result.result_df, preview=0)
    artifacts = []
    if paths:
        artifacts = [
            write_frame(
                result.result_df,
                paths["result_df"],
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="result_df",
            ),
            write_frame(
                result.executed_weights,
                paths["executed_weights"],
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="executed_weights",
            ),
            write_json(
                {"metrics": metrics, "annual_returns": annual, "activity": activity},
                paths["metrics"],
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="metrics",
            ),
        ]
        if "executed_lots" in paths:
            artifacts.append(
                write_frame(
                    result.executed_lots,
                    paths["executed_lots"],
                    overwrite=args.overwrite,
                    data_root=args.data_root,
                    name="executed_lots",
                )
            )
    warnings = (
        ["nonfinite metrics were converted to null"]
        if any(value is None for value in [*metrics.values(), *annual.values()])
        else []
    )
    return CommandResult(
        data=RunData(
            metrics=metrics,
            annual_returns=annual,
            activity=activity,
            rows=info["rows"],
            start=info["start"],
            end=info["end"],
        ),
        artifacts=artifacts,
        warnings=warnings,
    )


class WeighInput(OutputOptions, PanelSource):
    output: Path = Field(description="Destination weights table.")
    votes: Path = Field(description="Date by symbol vote matrix; nonzero means selected.")
    returns: Path | None = Field(
        default=None,
        description="Date by symbol asset returns; otherwise close-to-close returns of a panel source.",
    )
    method: Literal["equal", "risk_parity", "inverse_variance", "epo"] = Field(
        default="equal", description="WEIGHT_METHODS key."
    )
    lookback: int | None = Field(
        default=None,
        gt=0,
        description="Trailing return window; defaults to the method default (60, epo 1200).",
    )
    min_periods: int | None = Field(
        default=None,
        gt=0,
        description="Minimum trailing observations; defaults to the method default (20, epo 60).",
    )
    lambda_: float = Field(default=10.0, alias="lambda", description="EPO risk aversion.")
    shrink_w: float = Field(default=0.2, ge=0, le=1, description="EPO correlation shrinkage.")

    @model_validator(mode="after")
    def one_return_source(self):
        if self.returns is not None and _has_panel_source(self):
            raise ValueError("provide returns or a panel source, not both")
        return self


class WeighData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: str = Field(description="Weighting method.")
    rows: int = Field(description="Number of dates.")
    columns: list[str] = Field(description="Symbol columns.")
    start: str | None = Field(description="First date.")
    end: str | None = Field(description="Last date.")
    preview: list[dict] = Field(description="Small weight preview.")


def weigh(args: WeighInput) -> CommandResult:
    from skills.backtest.weighting import WEIGHT_METHODS

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    votes = read_frame(args.votes)
    if args.method == "equal":
        result = WEIGHT_METHODS["equal"](votes)
    else:
        if args.returns is None and not _has_panel_source(args):
            raise CLIError(
                "INVALID_INPUT", "non-equal weighting requires --returns or a panel source"
            )
        returns = read_frame(args.returns) if args.returns else _close_returns(args)[1]
        if not votes.columns.isin(returns.columns).all():
            raise CLIError("INVALID_INPUT", "returns table is missing voted symbol columns")
        params = {
            key: value
            for key, value in (("lookback", args.lookback), ("min_periods", args.min_periods))
            if value is not None
        }
        if args.method == "epo":
            params.update(lambda_=args.lambda_, shrink_w=args.shrink_w)
        result = WEIGHT_METHODS[args.method](votes, returns_df=returns, **params)
    artifact = write_frame(
        result, args.output, overwrite=args.overwrite, data_root=args.data_root, name="weights"
    )
    return CommandResult(
        data=WeighData(method=args.method, **frame_summary(result, preview=args.preview)),
        artifacts=[artifact],
    )


class OverlayInput(OutputOptions, PanelSource):
    output: Path = Field(description="Destination scaled weights table.")
    weights: Path = Field(description="Date by symbol weights to scale.")
    index_close: Path | None = Field(
        default=None,
        description="Benchmark close table with an eob index and one value column; "
        "required by index_trend.",
    )
    market_breadth: dict | None = Field(
        default=None,
        description='apply_market_breadth_scale options, e.g. {"breadth_threshold": 0.3, '
        '"scale_below": 0.5, "ma_period": 20}.',
    )
    index_trend: dict | None = Field(
        default=None,
        description='apply_index_trend_scale options, e.g. {"scale_downtrend": 0.5, "ma_period": 120}.',
    )
    vol_target: dict | None = Field(
        default=None,
        description='apply_portfolio_vol_targeting options, e.g. {"vol_target": 0.1, "lookback": 60}.',
    )

    @model_validator(mode="after")
    def check_overlays(self):
        if not (self.market_breadth or self.index_trend or self.vol_target):
            raise ValueError("provide at least one of market_breadth, index_trend or vol_target")
        if self.index_trend and self.index_close is None:
            raise ValueError("index_trend requires index_close")
        return self


def overlay(args: OverlayInput) -> CommandResult:
    from skills.backtest.filters import apply_portfolio_filters

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    weights = read_frame(args.weights)
    close, returns = _close_returns(args)
    index_close = None
    if args.index_close is not None:
        table = read_frame(args.index_close)
        if table.shape[1] != 1:
            raise CLIError("INVALID_INPUT", "index_close needs exactly one value column")
        index_close = table.iloc[:, 0]
    result = apply_portfolio_filters(
        weights,
        close,
        returns,
        index_close=index_close,
        market_breadth_config=args.market_breadth,
        index_trend_config=args.index_trend,
        vol_target_config=args.vol_target,
    )
    artifact = write_frame(
        result, args.output, overwrite=args.overwrite, data_root=args.data_root, name="weights"
    )
    return CommandResult(
        data=WeighData(method="overlay", **frame_summary(result, preview=args.preview)),
        artifacts=[artifact],
    )


class CombineInput(OutputOptions):
    returns: Path = Field(
        description="Strategy daily returns: eob index or column plus one column per strategy."
    )
    method: Literal["equal", "risk_parity", "custom"] = Field(
        default="equal", description="StrategyCombiner method."
    )
    weights: dict[str, float] = Field(
        default_factory=dict, description="Custom strategy weights, normalized to sum to one."
    )
    lookback: int = Field(default=60, gt=0, description="Risk parity volatility window.")

    @model_validator(mode="after")
    def check_weights(self):
        if self.method == "custom" and not self.weights:
            raise ValueError("custom method requires weights")
        if self.method != "custom" and self.weights:
            raise ValueError("weights apply only to the custom method")
        return self


class CombineData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategies: list[str] = Field(description="Combined strategy columns.")
    weights: dict[str, float | None] = Field(description="Applied strategy weights.")
    metrics: dict[str, float | None] = Field(
        description="StrategyCombiner metrics except weights; returns are additive (cumsum)."
    )
    rows: int = Field(description="Number of combined dates.")


def combine(args: CombineInput) -> CommandResult:
    from skills.backtest.combiner import StrategyCombiner

    if args.output:
        check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    returns = read_frame(args.returns)
    if returns.empty or returns.shape[1] < 1:
        raise CLIError("INVALID_INPUT", "returns needs at least one strategy column")
    if args.method == "custom":
        unknown = sorted(set(args.weights) - set(map(str, returns.columns)))
        if unknown:
            raise CLIError("INVALID_INPUT", f"weights name unknown strategies: {unknown}")
    combiner = StrategyCombiner(
        {str(name): returns[name] for name in returns.columns},
        method=args.method,
        custom_weights=args.weights or None,
        lookback=args.lookback,
    )
    result = combiner.run()
    metrics = dict(combiner.metrics)
    weights = metrics.pop("weights")
    artifacts = (
        [
            write_frame(
                result,
                args.output,
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="combined",
            )
        ]
        if args.output
        else []
    )
    return CommandResult(
        data=CombineData(
            strategies=[str(name) for name in returns.columns],
            weights=json_safe(weights),
            metrics=json_safe(metrics),
            rows=len(result),
        ),
        artifacts=artifacts,
    )


class CostInput(CLIModel):
    time: str = Field(description='A-share trigger timestamp, e.g. "2026-09-23 14:50".')
    sell_price: float | None = Field(
        default=None, gt=0, description="Sell price of a single T trade; needs buyback_price."
    )
    buyback_price: float | None = Field(
        default=None, gt=0, description="Buyback price of a single T trade; needs sell_price."
    )

    @model_validator(mode="after")
    def paired_prices(self):
        if (self.sell_price is None) != (self.buyback_price is None):
            raise ValueError("sell_price and buyback_price go together")
        return self


class CostData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: str = Field(description="Parsed trigger timestamp.")
    layer: str = Field(description="Cost layer for the trigger time.")
    cost_bp: int = Field(description="Round-trip cost in basis points for the layer.")
    gross_bp: float | None = Field(description="Single T gross PnL in basis points.")
    net_bp: float | None = Field(description="Single T net PnL in basis points after cost.")


def cost(args: CostInput) -> CommandResult:
    import pandas as pd

    from skills.backtest.cost_model import (
        cost_bp_for_trigger_time,
        cost_layer_for_trigger_time,
        single_T_pnl_bp,
    )

    timestamp = pd.Timestamp(args.time)
    cost_bp = cost_bp_for_trigger_time(timestamp)
    gross = net = None
    if args.sell_price is not None:
        gross, net = single_T_pnl_bp(args.sell_price, args.buyback_price, cost_bp)
    return CommandResult(
        data=CostData(
            time=str(timestamp),
            layer=cost_layer_for_trigger_time(timestamp),
            cost_bp=cost_bp,
            gross_bp=gross,
            net_bp=net,
        )
    )


COMMANDS = [
    Command(
        "backtest.run",
        RunInput,
        RunData,
        run,
        "Execute target weights through VectorBacktester with costs and metrics.",
        side_effects=("writes-output",),
        priority="P0",
    ),
    Command(
        "backtest.weigh",
        WeighInput,
        WeighData,
        weigh,
        "Convert a vote matrix into portfolio weights.",
        side_effects=("writes-output",),
    ),
    Command(
        "backtest.overlay",
        OverlayInput,
        WeighData,
        overlay,
        "Scale weights with market breadth, index trend, or volatility targeting.",
        side_effects=("writes-output",),
        priority="P2",
    ),
    Command(
        "backtest.combine",
        CombineInput,
        CombineData,
        combine,
        "Blend strategy return streams with StrategyCombiner.",
        side_effects=("writes-output",),
        priority="P2",
    ),
    Command(
        "backtest.cost",
        CostInput,
        CostData,
        cost,
        "Look up the A-share trigger-time cost layer and single T PnL.",
        priority="P2",
    ),
]
