"""Agent-facing local market storage commands over DataManager."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from skills.cli.io import (
    check_output,
    data_manager,
    frame_summary,
    read_frame,
    resolve_symbols,
    validate_symbol,
    write_frame,
)
from skills.cli.models import CLIError, CLIModel, CommandResult, OutputOptions
from skills.cli.registry import Command

DATA_ROOT_HELP = "Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/."
FREQUENCY_HELP = (
    "Directory under data/market: real bar frequency plus optional _adj suffix, "
    "for example 1d, 1d_adj, 5m."
)
SYMBOLS_HELP = "QuantSpace symbols such as SHSE.510300; repeat flag or comma-separate."
SYMBOLS_FILE_HELP = "Text lines or JSON list of QuantSpace symbols."
# Namespaces whose per-namespace Parquet counts DataManager.info prints.
INFO_NAMESPACES = ("factors", "backtest")


def _missing_symbols(dm, symbols, frequency):
    stored = set(dm.list_symbols(frequency))
    return [symbol for symbol in symbols if symbol not in stored]


class InfoInput(CLIModel):
    data_root: Path | None = Field(default=None, description=DATA_ROOT_HELP)


class InfoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_root: str = Field(description="Resolved data root.")
    exists: bool = Field(description="Whether the data root exists.")
    frequencies: dict[str, int] = Field(
        description="Symbol count for every directory under data/market."
    )
    adj_factors: int = Field(description="Symbols with stored adjustment-factor events.")
    namespaces: dict[str, dict[str, int]] = Field(
        description="Parquet file count per artifact namespace under factors and backtest."
    )


def info(args: InfoInput) -> CommandResult:
    dm = data_manager(args.data_root)
    root = dm.root
    market = root / "market"
    frequencies = (
        {p.name: len(dm.list_symbols(p.name)) for p in sorted(market.iterdir()) if p.is_dir()}
        if market.is_dir()
        else {}
    )
    namespaces = {}
    for sub in INFO_NAMESPACES:
        directory = root / sub
        namespaces[sub] = (
            {
                p.name: len(list(p.rglob("*.parquet")))
                for p in sorted(directory.iterdir())
                if p.is_dir()
            }
            if directory.is_dir()
            else {}
        )
    return CommandResult(
        data=InfoOutput(
            data_root=str(root),
            exists=root.is_dir(),
            frequencies=frequencies,
            adj_factors=len(dm.list_adj_factors()),
            namespaces=namespaces,
        )
    )


class ListInput(CLIModel):
    kind: Literal["market", "adj-factor", "models"] = Field(
        default="market", description="Stored item kind."
    )
    frequency: str = Field(default="1d", description=FREQUENCY_HELP)
    namespace: str | None = Field(
        default=None, description="Model artifact namespace; required for models."
    )
    prefix: str | None = Field(default=None, description="Optional name prefix.")
    data_root: Path | None = Field(default=None, description=DATA_ROOT_HELP)
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum items per page.")
    offset: int = Field(default=0, ge=0, description="Number of matching items to skip.")


class ListOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(description="Stored item kind.")
    items: list[str] = Field(description="Matching symbols, or model ids newest first for models.")
    count: int = Field(description="Number of matching items.")
    truncated: bool = Field(description="Whether more matching items follow this page.")
    next_offset: int | None = Field(description="Offset for the next page, if any.")


def list_items(args: ListInput) -> CommandResult:
    dm = data_manager(args.data_root)
    if args.kind == "market":
        items = dm.list_symbols(args.frequency)
    elif args.kind == "adj-factor":
        items = dm.list_adj_factors()
    else:
        if not args.namespace:
            raise CLIError("INVALID_INPUT", "namespace is required for models")
        items = [
            str(meta["model_id"]) for meta in dm.list_models(args.namespace) if "model_id" in meta
        ]
    if args.prefix:
        items = [item for item in items if item.startswith(args.prefix)]
    count = len(items)
    page = items[args.offset : args.offset + args.limit]
    next_offset = args.offset + len(page) if args.offset + len(page) < count else None
    return CommandResult(
        data=ListOutput(
            kind=args.kind,
            items=page,
            count=count,
            truncated=next_offset is not None,
            next_offset=next_offset,
        )
    )


class ReadInput(OutputOptions):
    symbols: list[str] = Field(default_factory=list, description=SYMBOLS_HELP)
    symbols_file: Path | None = Field(default=None, description=SYMBOLS_FILE_HELP)
    frequency: str = Field(default="1d", description=FREQUENCY_HELP)
    start: str | None = Field(default=None, description="Inclusive start date.")
    end: str | None = Field(default=None, description="Inclusive end date.")
    fields: list[str] = Field(default_factory=list, description="Columns to retain.")


class ReadOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbols: list[str] = Field(description="Requested symbols.")
    frequency: str = Field(description="Market store directory.")
    rows: int = Field(description="Loaded panel rows.")
    start: str | None = Field(description="Earliest timestamp.")
    end: str | None = Field(description="Latest timestamp.")
    columns: list[str] = Field(description="Panel columns.")
    missing: list[str] = Field(description="Missing symbols.")
    preview: list[dict] = Field(description="First rows of the panel.")


def read(args: ReadInput) -> CommandResult:
    from skills.cli.io import load_panel
    from skills.cli.models import PanelSource

    symbols = resolve_symbols(args.symbols, args.symbols_file)
    if not symbols:
        raise CLIError("INVALID_INPUT", "symbols or symbols-file is required")
    if args.output:
        check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    dm = data_manager(args.data_root)
    missing = _missing_symbols(dm, symbols, args.frequency)
    if missing:
        raise CLIError(
            "NOT_FOUND",
            f"Missing {args.frequency} Parquet files for symbols: {missing}",
            3,
            details=missing,
            hint=f"Run `uv run qs store list --frequency {args.frequency}` to see stored symbols.",
        )
    panel = load_panel(
        PanelSource(
            symbols=symbols,
            frequency=args.frequency,
            data_root=args.data_root,
            start=args.start,
            end=args.end,
            fields=args.fields,
        )
    )
    summary = frame_summary(panel, args.preview)
    artifacts = (
        [
            write_frame(
                panel, args.output, overwrite=args.overwrite, data_root=args.data_root, name="panel"
            )
        ]
        if args.output
        else []
    )
    return CommandResult(
        data=ReadOutput(
            symbols=symbols,
            frequency=args.frequency,
            rows=summary["rows"],
            start=summary["start"],
            end=summary["end"],
            columns=summary["columns"],
            missing=[],
            preview=summary["preview"],
        ),
        artifacts=artifacts,
    )


class ImportInput(CLIModel):
    file: Path = Field(description="Input CSV file, as accepted by DataManager.import_*_csv.")
    layout: Literal["single", "combined"] = Field(
        default="single",
        description="single: one symbol per file (import_symbol_csv); "
        "combined: a symbol column splits the file (import_combined_csv).",
    )
    symbol: str | None = Field(default=None, description="QuantSpace symbol for single layout.")
    frequency: str = Field(default="1d", description=FREQUENCY_HELP)
    symbol_col: str = Field(default="symbol", description="Symbol column for combined layout.")
    time_col: str = Field(
        default="eob",
        description="Timestamp column. Values are parsed as UTC (offset-aware values keep their "
        "offset) and stored as naive Asia/Shanghai time, exactly like DataManager.import_*_csv.",
    )
    write: bool = Field(
        default=False, description="Write into managed market storage; otherwise a dry run."
    )
    overwrite: bool = Field(default=False, description="Allow replacing existing symbol files.")
    data_root: Path | None = Field(default=None, description=DATA_ROOT_HELP)


class ImportOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbols: list[str] = Field(description="Symbols in the input file.")
    rows: int = Field(description="Input rows.")
    saved: bool = Field(description="Whether files were written.")
    dry_run: bool = Field(description="Whether this was a write plan only.")
    frequency: str = Field(description="Managed market store directory.")
    planned_paths: list[str] = Field(description="Absolute per-symbol managed output paths.")
    existing: list[str] = Field(description="Planned symbols whose files already exist.")


def import_data(args: ImportInput) -> CommandResult:
    import pandas as pd

    if args.file.suffix.lower() != ".csv":
        raise CLIError("INVALID_INPUT", "store import reads CSV files")
    if args.layout == "single" and not args.symbol:
        raise CLIError("INVALID_INPUT", "symbol is required for single layout")
    if args.layout == "combined" and args.symbol:
        raise CLIError("INVALID_INPUT", "symbol applies only to single layout")
    frame = pd.read_csv(args.file)
    for column in (args.time_col, *([args.symbol_col] if args.layout == "combined" else [])):
        if column not in frame.columns:
            raise CLIError("INVALID_INPUT", f"Missing CSV column: {column}")
    symbols = (
        [args.symbol]
        if args.layout == "single"
        else sorted(str(value) for value in frame[args.symbol_col].unique())
    )
    for symbol in symbols:
        validate_symbol(symbol)
    dm = data_manager(args.data_root)
    paths = [dm.root / "market" / args.frequency / f"{symbol}.parquet" for symbol in symbols]
    existing = [symbol for symbol, path in zip(symbols, paths) if path.exists()]
    if args.write:
        if existing and not args.overwrite:
            raise CLIError(
                "CONFLICT",
                f"Stored symbol files already exist: {existing}; use --overwrite",
                details=existing,
            )
        if args.layout == "single":
            dm.import_symbol_csv(
                str(args.file), args.symbol, frequency=args.frequency, time_col=args.time_col
            )
        else:
            dm.import_combined_csv(
                str(args.file),
                frequency=args.frequency,
                symbol_col=args.symbol_col,
                time_col=args.time_col,
            )
    return CommandResult(
        data=ImportOutput(
            symbols=symbols,
            rows=len(frame),
            saved=args.write,
            dry_run=not args.write,
            frequency=args.frequency,
            planned_paths=[str(path.resolve()) for path in paths],
            existing=existing,
        )
    )


class ValidateInput(CLIModel):
    file: Path | None = Field(default=None, description="OHLCV Parquet/CSV file to validate.")
    symbols: list[str] = Field(default_factory=list, description="Stored symbols to validate.")
    frequency: str = Field(default="1d", description=FREQUENCY_HELP)
    data_root: Path | None = Field(default=None, description=DATA_ROOT_HELP)


class ValidateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passed: bool = Field(description="Whether all checks passed.")
    n_rows: int = Field(description="Checked rows.")
    nan_count: int = Field(description="Missing numeric values.")
    inf_count: int = Field(description="Infinite float values.")
    negative_price_count: int = Field(description="Negative price cells.")
    negative_volume_count: int = Field(description="Negative volumes.")
    high_lt_low_count: int = Field(description="Rows with high below low.")
    non_monotonic_index: bool = Field(description="Whether any index is unordered.")
    details: dict = Field(description="validate_ohlcv metadata, per symbol for stored symbols.")


REPORT_COUNTS = (
    "n_rows",
    "nan_count",
    "inf_count",
    "negative_price_count",
    "negative_volume_count",
    "high_lt_low_count",
)


def validate(args: ValidateInput) -> CommandResult:
    from dataclasses import asdict

    from skills.store.data_manager import validate_ohlcv

    symbols = resolve_symbols(args.symbols)
    if bool(args.file) == bool(symbols):
        raise CLIError("INVALID_INPUT", "Exactly one of file or symbols is required")
    if args.file:
        data = ValidateOutput(**asdict(validate_ohlcv(read_frame(args.file))))
    else:
        dm = data_manager(args.data_root)
        reports = {
            symbol: validate_ohlcv(dm.read_symbol(symbol, args.frequency)) for symbol in symbols
        }
        data = ValidateOutput(
            passed=all(report.passed for report in reports.values()),
            non_monotonic_index=any(report.non_monotonic_index for report in reports.values()),
            details={"by_symbol": {symbol: asdict(report) for symbol, report in reports.items()}},
            **{
                name: sum(getattr(report, name) for report in reports.values())
                for name in REPORT_COUNTS
            },
        )
    return CommandResult(data=data, exit_code=0 if data.passed else 1)


class CheckAdjustedInput(OutputOptions):
    symbols: list[str] = Field(default_factory=list, description=SYMBOLS_HELP)
    symbols_file: Path | None = Field(default=None, description=SYMBOLS_FILE_HELP)
    frequency: str = Field(default="1d_adj", description="Adjusted market store directory.")
    threshold: float = Field(default=0.2, ge=0, description="Relative price jump threshold.")


class CheckAdjustedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbols: list[str] = Field(description="Requested symbols.")
    missing: list[str] = Field(description="Requested symbols without a stored file; skipped.")
    issues: int = Field(description="Zero-volume or suspended rows with implausible jumps.")
    preview: list[dict] = Field(description="First issue rows.")


def check_adjusted(args: CheckAdjustedInput) -> CommandResult:
    import pandas as pd

    from skills.store.adjusted_quality import QUALITY_COLUMNS, find_zero_volume_price_jumps

    symbols = resolve_symbols(args.symbols, args.symbols_file)
    if not symbols:
        raise CLIError("INVALID_INPUT", "symbols or symbols-file is required")
    if args.output:
        check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    dm = data_manager(args.data_root)
    missing = _missing_symbols(dm, symbols, args.frequency)
    # Same scan as skills.store.adjusted_quality.scan_adjusted_market_data, which skips
    # missing files, without constructing a directory-creating DataManager.
    found = [
        find_zero_volume_price_jumps(
            dm.read_symbol(symbol, frequency=args.frequency),
            symbol=symbol,
            threshold=args.threshold,
        )
        for symbol in symbols
        if symbol not in missing
    ]
    found = [item for item in found if len(item) > 0]
    issues = pd.concat(found, ignore_index=True) if found else pd.DataFrame(columns=QUALITY_COLUMNS)
    artifacts = (
        [
            write_frame(
                issues,
                args.output,
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="issues",
            )
        ]
        if args.output
        else []
    )
    return CommandResult(
        data=CheckAdjustedOutput(
            symbols=symbols,
            missing=missing,
            issues=len(issues),
            preview=frame_summary(issues, args.preview)["preview"],
        ),
        artifacts=artifacts,
        warnings=[f"Skipped symbols without stored files: {missing}"] if missing else [],
        exit_code=1 if len(issues) else 0,
    )


class QueryInput(OutputOptions):
    sql: str = Field(
        description="DuckDB SQL; {data} is replaced by the data root, as in DataManager.query."
    )
    params: list = Field(
        default_factory=list, description="Positional parameters bound as $1, $2, ..."
    )


class QueryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: int = Field(description="Result rows.")
    columns: list[str] = Field(description="Result columns.")
    preview: list[dict] = Field(description="First result rows.")


def query(args: QueryInput) -> CommandResult:
    if args.output:
        check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    result = data_manager(args.data_root).query(args.sql, args.params or None)
    summary = frame_summary(result, args.preview)
    artifacts = (
        [
            write_frame(
                result,
                args.output,
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="query",
            )
        ]
        if args.output
        else []
    )
    return CommandResult(
        data=QueryOutput(
            rows=summary["rows"], columns=summary["columns"], preview=summary["preview"]
        ),
        artifacts=artifacts,
    )


COMMANDS = [
    Command(
        "store.info",
        InfoInput,
        InfoOutput,
        info,
        "Inspect the local data store inventory.",
        priority="P0",
    ),
    Command(
        "store.list",
        ListInput,
        ListOutput,
        list_items,
        "List stored market symbols, adjustment factors, or models.",
        priority="P0",
    ),
    Command(
        "store.read",
        ReadInput,
        ReadOutput,
        read,
        "Read stored symbols into a (symbol, eob) panel.",
        side_effects=("writes-output",),
        priority="P0",
    ),
    Command(
        "store.import",
        ImportInput,
        ImportOutput,
        import_data,
        "Import market bars from CSV into data/market.",
        side_effects=("writes-store",),
    ),
    Command(
        "store.validate",
        ValidateInput,
        ValidateOutput,
        validate,
        "Validate OHLCV quality; exit 1 when a check fails.",
    ),
    Command(
        "store.check-adjusted",
        CheckAdjustedInput,
        CheckAdjustedOutput,
        check_adjusted,
        "Scan adjusted bars for zero-volume price jumps; exit 1 when found.",
        side_effects=("writes-output",),
    ),
    Command(
        "store.query",
        QueryInput,
        QueryOutput,
        query,
        "Run DuckDB SQL over stored Parquet files (needs --extra query).",
        side_effects=("writes-output",),
        priority="P2",
    ),
]
