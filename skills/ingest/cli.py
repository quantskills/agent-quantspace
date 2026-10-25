"""Agent-facing PandaData ingestion commands.

A thin transport layer over :class:`skills.ingest.PandaDataClient` and the
``skills.ingest.panda_future_tick`` downloader: parse and validate inputs, call
the existing public entry points the way a Python caller would, write files, and
return output models. Table outputs go to files (``--output``) or to the managed
market store (``--write``); stdout carries summaries and previews only.
"""

from __future__ import annotations

import importlib
import inspect
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from skills.cli.io import (
    check_output,
    data_manager,
    json_safe,
    parse_times,
    resolve_symbols,
    validate_symbol,
    write_frame,
)
from skills.cli.models import Artifact, CLIError, CLIModel, CommandResult, OutputOptions
from skills.cli.registry import Command
from skills.ingest.symbol_map import try_to_quantspace_symbol

SDK_HINT = "uv sync --extra panda_data"
CREDENTIAL_HINT = (
    "Set PANDA_DATA_USERNAME and PANDA_DATA_PASSWORD in the environment or .env; "
    "credentials are never command flags."
)
OHLCV = ("open", "high", "low", "close", "volume")
# panda_data limits daily requests to a span of under five years.
DAILY_CHUNK_DAYS = 365 * 5 - 2
FUND_DAILY_METHODS = {
    "none": "get_fund_daily",
    "pre": "get_fund_daily_pre",
    "post": "get_fund_daily_post",
}
# The client authenticates itself; raw access to init_token would only bypass that.
RAW_EXCLUDED = frozenset({"init_token"})


# ---------------------------------------------------------------------------
# Shared input types and helpers
# ---------------------------------------------------------------------------


def _yyyymmdd(value: str) -> str:
    text = value.strip()
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").strftime("%Y%m%d")
        if len(text) == 10:
            return datetime.strptime(text, "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError:
        pass
    raise ValueError(f"Invalid date {value!r}; use YYYY-MM-DD or YYYYMMDD")


# Accepts YYYY-MM-DD or YYYYMMDD and hands YYYYMMDD to the SDK.
Date = Annotated[str, AfterValidator(_yyyymmdd)]


def _check_order(model):
    start, end = getattr(model, "start", None), getattr(model, "end", None)
    if start and end and start > end:
        raise ValueError("start must be on or before end")
    return model


def _items(values) -> list[str]:
    """Split comma-separated entries, drop blanks and duplicates, keep order."""
    return list(
        dict.fromkeys(
            part.strip() for value in values or [] for part in str(value).split(",") if part.strip()
        )
    )


def _one_or_many(values):
    """A lone value is sent as a scalar, several as a list, none as None."""
    values = list(values or [])
    if not values:
        return None
    return values[0] if len(values) == 1 else values


def _today() -> str:
    return date.today().strftime("%Y%m%d")


def _quantspace(symbols: list[str]) -> list[str]:
    """Names the client returns for these requested symbols (QuantSpace format)."""
    return list(dict.fromkeys(try_to_quantspace_symbol(symbol) for symbol in symbols))


def _require_sdk():
    try:
        return importlib.import_module("panda_data")
    except ImportError as exc:
        raise CLIError(
            "MISSING_DEPENDENCY",
            f"panda_data SDK is not installed: {exc}",
            3,
            hint=SDK_HINT,
        ) from exc


def _require_credentials() -> None:
    if not os.environ.get("PANDA_DATA_USERNAME") or not os.environ.get("PANDA_DATA_PASSWORD"):
        raise CLIError(
            "MISSING_CREDENTIAL",
            "PANDA_DATA_USERNAME / PANDA_DATA_PASSWORD are not set",
            3,
            hint=CREDENTIAL_HINT,
        )


def _client():
    """A PandaDataClient, after confirming the SDK and credentials exist.

    The client loads ``.env`` from the working directory into the environment, so
    credentials are checked after construction. Both checks run before any request.
    """
    _require_sdk()
    from skills.ingest.panda_data import PandaDataClient

    client = PandaDataClient()
    _require_credentials()
    return client


def _translate(exc: Exception) -> CLIError:
    """Classify an SDK/client failure, looking through wrapped causes."""
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain and len(chain) < 8:
        chain.append(current)
        current = current.__cause__ or current.__context__
    for item in chain:
        text = str(item)
        if isinstance(item, ImportError) or "panda_data is not installed" in text:
            return CLIError("MISSING_DEPENDENCY", text, 3, hint=SDK_HINT)
        if "PANDA_DATA_USERNAME" in text or "PANDA_DATA_PASSWORD" in text:
            return CLIError("MISSING_CREDENTIAL", text, 3, hint=CREDENTIAL_HINT)
        if isinstance(item, TimeoutError):
            return CLIError("TIMEOUT", text or "PandaData request timed out", 124)
    message = str(exc) or type(exc).__name__
    if exc.__cause__ is not None:
        message = f"{message}: {exc.__cause__}"
    return CLIError("UPSTREAM_ERROR", message, 4)


def _call(function, *args, **kwargs):
    """Run an SDK/client call, turning failures into command errors."""
    try:
        return function(*args, **kwargs)
    except CLIError:
        raise
    except Exception as exc:
        raise _translate(exc) from exc


def _table(result, what: str):
    import pandas as pd

    if result is None:
        return pd.DataFrame()
    if isinstance(result, pd.DataFrame):
        return result
    if isinstance(result, pd.Series):
        return result.to_frame()
    if isinstance(result, (list, tuple)) and all(isinstance(row, dict) for row in result):
        return pd.DataFrame(list(result))
    raise CLIError("UPSTREAM_ERROR", f"{what} returned {type(result).__name__}, not a table", 4)


def _preview(frame, count: int) -> list[dict]:
    return json_safe(frame.head(count).to_dict("records"))


def _prepare_output(args) -> Path | None:
    """Validate an explicit --output before any request is made."""
    if not args.output:
        return None
    path = check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    if path.suffix.lower() not in (".csv", ".parquet", ".pq"):
        raise CLIError("INVALID_INPUT", "Table output must end in .parquet or .csv")
    return path


def _write_output(frame, args, name: str) -> list[Artifact]:
    if not args.output:
        return []
    return [
        write_frame(
            frame, args.output, overwrite=args.overwrite, data_root=args.data_root, name=name
        )
    ]


def _market_path(dm, frequency: str, symbol: str) -> Path:
    return dm.root / "market" / frequency / f"{symbol}.parquet"


def _adj_path(dm, symbol: str) -> Path:
    return dm.root / "adj_factor" / f"{symbol}.parquet"


def _returned_symbol(value) -> str:
    """A symbol from the provider becomes a file name, so it must be a plain name."""
    try:
        return validate_symbol(value)
    except ValueError as exc:
        raise CLIError(
            "UPSTREAM_ERROR", f"PandaData returned an unusable symbol: {exc}", 4
        ) from exc


def _guard_store_files(paths: dict[str, Path], overwrite: bool) -> None:
    for path in paths.values():
        if path.is_symlink():
            raise CLIError("INVALID_INPUT", f"Refusing to write through a symlink: {path}")
    existing = [symbol for symbol, path in paths.items() if path.exists()]
    if existing and not overwrite:
        raise CLIError(
            "CONFLICT",
            f"Stored files already exist for: {existing}; use --overwrite",
            2,
            details=existing,
        )


def _naive(index):
    return index.tz_localize(None) if index.tz is not None else index


def _clock(values):
    import pandas as pd

    text = pd.Series(list(values)).astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    padded = text.str.zfill(6)
    plain = padded.str[:2] + ":" + padded.str[2:4] + ":" + padded.str[4:6]
    return pd.TimedeltaIndex(pd.to_timedelta(text.where(text.str.contains(":"), plain)))


def _eob(frame, freq: str):
    """Timezone-naive bar timestamps from the SDK's time columns.

    Daily tables carry ``date``. Minute tables carry ``date`` plus ``minute``
    (``HHMMSS``); futures minute tables also carry ``datetime``.
    """
    columns = set(frame.columns)
    if freq != "1d" and "datetime" in columns:
        return _naive(parse_times(frame["datetime"]))
    if freq != "1d" and {"date", "minute"} <= columns:
        return _naive(parse_times(frame["date"])) + _clock(frame["minute"])
    if "date" in columns:
        return _naive(parse_times(frame["date"]))
    if "eob" in columns:
        return _naive(parse_times(frame["eob"]))
    needed = "date and minute" if freq != "1d" else "date"
    raise CLIError(
        "INVALID_INPUT",
        f"Returned bars lack the {needed} column(s)",
        hint="Keep the time columns when restricting --fields.",
    )


def _by_symbol(frame, requested: list[str]):
    """Rows per returned symbol, or None when they cannot be attributed."""
    if len(frame) == 0:
        return {}
    if "symbol" in frame.columns:
        return {str(symbol): rows for symbol, rows in frame.groupby("symbol", sort=False)}
    if len(requested) == 1:
        return {requested[0]: frame}
    return None


# ---------------------------------------------------------------------------
# ingest.bars
# ---------------------------------------------------------------------------


class SymbolSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(description="QuantSpace symbol as returned by the client.")
    rows: int = Field(description="Rows returned for this symbol.")
    start: str | None = Field(description="First bar timestamp, if the time columns are present.")
    end: str | None = Field(description="Last bar timestamp, if the time columns are present.")


class BarsInput(OutputOptions):
    asset: Literal["stock", "index", "future", "fund", "hk", "us"] = Field(
        description="Asset class. Listed ETF and LOF are fund, not stock."
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="QuantSpace (SHSE.510300) or native (510300.SH) symbols; "
        "repeat flag or comma-separate.",
    )
    symbols_file: Path | None = Field(
        None, description="Text lines or JSON list of symbols, instead of symbols."
    )
    start: Date = Field(description="Inclusive start date: YYYY-MM-DD or YYYYMMDD.")
    end: Date | None = Field(
        None, description="Inclusive end date: YYYY-MM-DD or YYYYMMDD; defaults to today."
    )
    freq: Literal["1d", "1m", "5m", "15m", "60m"] = Field(
        "1d",
        description="Real bar interval sent to PandaData (never 1d_adj). Only stock, index "
        "(1m only) and future have minute bars; the provider caps rows per minute request, "
        "so split long minute ranges across runs.",
    )
    adjust: Literal["none", "pre", "post"] = Field(
        "none",
        description="Fund price adjustment: none, pre (forward) or post (backward). Fund only.",
    )
    fields: list[str] = Field(
        default_factory=list, description="SDK fields subset; empty returns all columns."
    )
    indicator: str | None = Field(
        None, description="Stock pool code for daily stock bars only; empty means all stocks."
    )
    st: bool = Field(
        True,
        description="Include ST stocks; --no-st excludes them. Daily stock bars only.",
    )
    save_frequency: str | None = Field(
        None,
        description="Market store directory under data/market, for example 1d or 1d_adj "
        "(adjusted 1d bars). Without --write this is a dry run that only reports planned paths.",
    )
    write: bool = Field(
        False,
        description="Write bars into data/market/<save-frequency>/<symbol>.parquet; "
        "requires --save-frequency.",
    )

    check_order = model_validator(mode="after")(_check_order)


class BarsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset: str = Field(description="Requested asset class.")
    freq: str = Field(description="Requested bar interval.")
    adjust: str = Field(description="Fund adjustment mode.")
    start: str = Field(description="Request start, YYYYMMDD.")
    end: str = Field(description="Request end, YYYYMMDD.")
    requested_symbols: list[str] = Field(description="Requested symbols in QuantSpace format.")
    dry_run: bool = Field(description="True when nothing was fetched or written.")
    saved: bool = Field(description="Whether bars were written to the market store.")
    rows: int = Field(description="Rows fetched.")
    columns: list[str] = Field(description="Columns of the fetched table.")
    symbols: list[SymbolSummary] = Field(description="Per-symbol row counts and time span.")
    no_data: list[str] = Field(description="Requested symbols with no returned rows.")
    output: str | None = Field(description="Raw table artifact path, if --output was given.")
    target_frequency: str | None = Field(description="Market store directory, if any.")
    planned_paths: list[str] = Field(description="Store paths --write targets for the symbols.")
    written_paths: list[str] = Field(description="Store files actually written.")
    preview: list[dict] = Field(description="First rows of the raw table.")


def _validate_bars(args: BarsInput) -> list[str]:
    symbols = resolve_symbols(args.symbols, args.symbols_file)
    if not symbols:
        raise CLIError("INVALID_INPUT", "symbols or symbols-file is required")
    if args.asset in {"fund", "hk", "us"} and args.freq != "1d":
        raise CLIError(
            "INVALID_INPUT",
            f"{args.asset} bars are daily only; freq {args.freq} is unavailable",
        )
    if args.asset == "index" and args.freq not in {"1d", "1m"}:
        raise CLIError("INVALID_INPUT", "Index minute bars support only 1m")
    if args.adjust != "none" and args.asset != "fund":
        raise CLIError("INVALID_INPUT", "adjust applies only to fund bars")
    if (args.indicator or not args.st) and (args.asset != "stock" or args.freq != "1d"):
        raise CLIError("INVALID_INPUT", "indicator and no-st apply only to daily stock bars")
    if args.write and not args.save_frequency:
        raise CLIError("INVALID_INPUT", "--write requires --save-frequency")
    if args.save_frequency:
        validate_symbol(args.save_frequency)
    return symbols


def _daily_chunks(start: str, end: str) -> list[tuple[str, str]]:
    first = datetime.strptime(start, "%Y%m%d").date()
    last = datetime.strptime(end, "%Y%m%d").date()
    chunks = []
    while first <= last:
        stop = min(last, first + timedelta(days=DAILY_CHUNK_DAYS))
        chunks.append((first.strftime("%Y%m%d"), stop.strftime("%Y%m%d")))
        first = stop + timedelta(days=1)
    return chunks


def _fetch_bars(client, args: BarsInput, symbols: list[str], start: str, end: str):
    """Route to the matching client method; the table is returned as the client gives it."""
    import pandas as pd

    target = _one_or_many(symbols)
    fields = _items(args.fields) or None
    if args.asset == "fund":
        method = getattr(client, FUND_DAILY_METHODS[args.adjust])
        return _call(method, start, end, symbol=target, fields=fields)
    if args.freq != "1d":
        return _call(
            client.fetch_market_min_data,
            target,
            start,
            end,
            symbol_type=args.asset,
            fields=fields,
            frequency=args.freq,
        )
    frames = []
    for chunk_start, chunk_end in _daily_chunks(start, end):
        if args.asset == "hk":
            frames.append(
                _call(client.fetch_hk_daily, target, chunk_start, chunk_end, fields=fields)
            )
        elif args.asset == "us":
            frames.append(
                _call(client.fetch_us_daily, target, chunk_start, chunk_end, fields=fields)
            )
        else:
            frames.append(
                _call(
                    client.fetch_market_data,
                    target,
                    chunk_start,
                    chunk_end,
                    type=args.asset,
                    fields=fields,
                    indicator=args.indicator,
                    st=args.st,
                )
            )
    frames = [_table(frame, "bars") for frame in frames]
    return frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)


def _store_bars(rows, freq: str):
    """One symbol's returned rows as the OHLCV table DataManager stores (eob index)."""
    import pandas as pd

    keep = [name for name in OHLCV if name in rows.columns]
    if not keep:
        raise CLIError(
            "INVALID_INPUT",
            "Returned bars have no OHLCV columns, so there is nothing to store",
            hint="Do not restrict --fields below open/high/low/close/volume when using --write.",
        )
    bars = rows.reset_index(drop=True).loc[:, keep].copy()
    try:
        bars = bars.apply(pd.to_numeric)
    except (ValueError, TypeError) as exc:
        raise CLIError(
            "UPSTREAM_ERROR", f"PandaData returned non-numeric OHLCV values: {exc}", 4
        ) from exc
    bars.index = _eob(rows.reset_index(drop=True), freq).rename("eob")
    bars = bars.sort_index(kind="stable")
    duplicated = bars.index.duplicated(keep="last")
    return bars[~duplicated], int(duplicated.sum())


def bars(args: BarsInput) -> CommandResult:
    symbols = _validate_bars(args)
    start, end = args.start, args.end or _today()
    if start > end:
        raise CLIError("INVALID_INPUT", "start must be on or before end")
    requested = _quantspace(symbols)
    dm = data_manager(args.data_root)
    frequency = args.save_frequency
    planned = (
        {symbol: _market_path(dm, frequency, symbol) for symbol in requested} if frequency else {}
    )
    planned_paths = [str(path.resolve()) for path in planned.values()]
    _prepare_output(args)
    warnings: list[str] = []
    if frequency and frequency.removesuffix("_adj") != args.freq:
        warnings.append(
            f"save-frequency {frequency} does not match the {args.freq} bars being fetched."
        )

    def result(**values) -> CommandResult:
        base = {
            "asset": args.asset,
            "freq": args.freq,
            "adjust": args.adjust,
            "start": start,
            "end": end,
            "requested_symbols": requested,
            "dry_run": False,
            "saved": False,
            "rows": 0,
            "columns": [],
            "symbols": [],
            "no_data": [],
            "output": None,
            "target_frequency": frequency,
            "planned_paths": planned_paths,
            "written_paths": [],
            "preview": [],
        }
        artifacts = values.pop("artifacts", [])
        return CommandResult(
            data=BarsOutput(**{**base, **values}), artifacts=artifacts, warnings=warnings
        )

    if frequency and not args.write:
        if args.output:
            warnings.append("--output ignored: nothing is fetched without --write.")
        return result(dry_run=True)
    if args.write:
        _guard_store_files(planned, args.overwrite)

    client = _client()
    frame = _table(_fetch_bars(client, args, symbols, start, end), "bars")
    groups = _by_symbol(frame, requested)

    summaries = []
    for symbol, rows in (groups or {}).items():
        try:
            times = _eob(rows, args.freq)
        except (CLIError, ValueError, KeyError):
            times = []
        summaries.append(
            SymbolSummary(
                symbol=symbol,
                rows=len(rows),
                start=str(times.min()) if len(times) else None,
                end=str(times.max()) if len(times) else None,
            )
        )
    if groups is None:
        warnings.append("Returned rows carry no symbol column; per-symbol summaries are omitted.")
    no_data = [symbol for symbol in requested if symbol not in groups] if groups is not None else []
    if no_data and len(frame):
        warnings.append(f"No rows returned for: {no_data}")
    if len(frame) == 0:
        warnings.append("PandaData returned no rows.")

    prepared = {}
    if args.write and len(frame):
        if groups is None:
            raise CLIError(
                "INVALID_INPUT",
                "Returned bars lack a symbol column, so they cannot be split per symbol",
                hint="Keep symbol when restricting --fields.",
            )
        for symbol, rows in groups.items():
            stored, dropped = _store_bars(rows, args.freq)
            if dropped:
                warnings.append(f"{symbol}: dropped {dropped} duplicate timestamps (kept last).")
            prepared[_returned_symbol(symbol)] = stored
        # The store is keyed by returned symbols; re-check them before writing anything.
        _guard_store_files(
            {symbol: _market_path(dm, frequency, symbol) for symbol in prepared}, args.overwrite
        )

    artifacts = _write_output(frame, args, "bars")
    written = []
    for symbol, stored in prepared.items():
        dm.save_symbol(symbol, stored, frequency=frequency, source="panda_data")
        written.append(str(_market_path(dm, frequency, symbol).resolve()))
    return result(
        saved=bool(written),
        rows=len(frame),
        columns=list(map(str, frame.columns)),
        symbols=summaries,
        no_data=no_data,
        output=artifacts[0].path if artifacts else None,
        written_paths=written,
        preview=_preview(frame, args.preview),
        artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# ingest.adj-factor
# ---------------------------------------------------------------------------


class AdjFactorInput(OutputOptions):
    symbols: list[str] = Field(
        default_factory=list,
        description="Stock symbols (QuantSpace or native); empty queries the whole market.",
    )
    symbols_file: Path | None = Field(
        None, description="Text lines or JSON list of symbols, instead of symbols."
    )
    start: Date | None = Field(None, description="Inclusive start date: YYYY-MM-DD or YYYYMMDD.")
    end: Date | None = Field(None, description="Inclusive end date: YYYY-MM-DD or YYYYMMDD.")
    fields: list[str] = Field(
        default_factory=list, description="SDK fields subset; empty returns all columns."
    )
    write: bool = Field(
        False,
        description="Write one data/adj_factor/<symbol>.parquet per symbol (ex_date index). "
        "A bounded --start/--end stores only the events in that range. With neither "
        "--output nor --write the command is a dry run: nothing is fetched.",
    )

    check_order = model_validator(mode="after")(_check_order)


class AdjFactorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["explicit-symbols", "all-market"] = Field(description="Symbol selection scope.")
    requested_symbols: list[str] = Field(description="Requested symbols in QuantSpace format.")
    start: str | None = Field(description="Request start, YYYYMMDD.")
    end: str | None = Field(description="Request end, YYYYMMDD.")
    dry_run: bool = Field(description="True when nothing was fetched or written.")
    saved: bool = Field(description="Whether adjustment files were written to the store.")
    rows: int = Field(description="Adjustment events fetched.")
    columns: list[str] = Field(description="Columns of the fetched table.")
    symbols: list[str] = Field(description="Symbols with at least one returned event.")
    no_data: list[str] = Field(description="Requested symbols with no returned events.")
    output: str | None = Field(description="Raw table artifact path, if --output was given.")
    planned_paths: list[str] = Field(description="Store paths for explicitly requested symbols.")
    path_template: str | None = Field(
        description="Store path pattern when symbols are discovered from the response."
    )
    written_paths: list[str] = Field(description="Store files actually written.")
    preview: list[dict] = Field(description="First rows of the raw table.")


def _store_events(rows):
    """One symbol's adjustment events with an ex_date DatetimeIndex."""
    try:
        times = _naive(parse_times(rows["ex_date"]))
    except ValueError as exc:
        raise CLIError(
            "UPSTREAM_ERROR", f"PandaData returned unusable ex_date values: {exc}", 4
        ) from exc
    events = rows.drop(columns=["symbol", "ex_date"]).reset_index(drop=True)
    events.index = times.rename("ex_date")
    return events.sort_index(kind="stable")


def adj_factor(args: AdjFactorInput) -> CommandResult:
    symbols = resolve_symbols(args.symbols, args.symbols_file)
    requested = _quantspace(symbols)
    dm = data_manager(args.data_root)
    scope = "explicit-symbols" if requested else "all-market"
    planned = {symbol: _adj_path(dm, symbol) for symbol in requested}
    planned_paths = [str(path.resolve()) for path in planned.values()]
    template = None if requested else str((dm.root / "adj_factor" / "{symbol}.parquet").resolve())
    _prepare_output(args)
    warnings: list[str] = []

    def result(**values) -> CommandResult:
        base = {
            "scope": scope,
            "requested_symbols": requested,
            "start": args.start,
            "end": args.end,
            "dry_run": False,
            "saved": False,
            "rows": 0,
            "columns": [],
            "symbols": [],
            "no_data": [],
            "output": None,
            "planned_paths": planned_paths,
            "path_template": template,
            "written_paths": [],
            "preview": [],
        }
        artifacts = values.pop("artifacts", [])
        return CommandResult(
            data=AdjFactorOutput(**{**base, **values}), artifacts=artifacts, warnings=warnings
        )

    if not args.write and not args.output:
        return result(dry_run=True)
    if args.write:
        _guard_store_files(planned, args.overwrite)

    client = _client()
    frame = _table(
        _call(
            client.get_adj_factor,
            symbol=_one_or_many(symbols) or "",
            start_date=args.start,
            end_date=args.end,
            fields=_items(args.fields) or None,
        ),
        "get_adj_factor",
    )
    groups: dict[str, Any] = {}
    if len(frame) and "symbol" in frame.columns:
        groups = {str(symbol): rows for symbol, rows in frame.groupby("symbol", sort=False)}
    no_data = [symbol for symbol in requested if symbol not in groups] if len(frame) else []
    if len(frame) == 0:
        warnings.append("PandaData returned no adjustment events.")
    elif no_data:
        warnings.append(f"No events returned for: {no_data}")

    prepared = {}
    if args.write and len(frame):
        if not {"symbol", "ex_date"} <= set(frame.columns):
            raise CLIError(
                "INVALID_INPUT",
                "Adjustment events need symbol and ex_date columns to be stored",
                hint="Keep symbol and ex_date when restricting --fields.",
            )
        for symbol, rows in groups.items():
            prepared[_returned_symbol(symbol)] = _store_events(rows)
        _guard_store_files({symbol: _adj_path(dm, symbol) for symbol in prepared}, args.overwrite)

    artifacts = _write_output(frame, args, "adj_factor")
    written = []
    for symbol, events in prepared.items():
        dm.save_adj_factor(symbol, events, source="panda_data")
        written.append(str(_adj_path(dm, symbol).resolve()))
    return result(
        saved=bool(written),
        rows=len(frame),
        columns=list(map(str, frame.columns)),
        symbols=list(groups),
        no_data=no_data,
        output=artifacts[0].path if artifacts else None,
        written_paths=written,
        preview=_preview(frame, args.preview),
        artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# Reference data and ETF creation/redemption: one typed command per endpoint
# ---------------------------------------------------------------------------

SYMBOLS_HELP = "Symbols (QuantSpace or native); repeat flag or comma-separate."
FIELDS_HELP = "SDK fields subset; empty returns all columns."
START_HELP = "Inclusive start date: YYYY-MM-DD or YYYYMMDD."
END_HELP = "Inclusive end date: YYYY-MM-DD or YYYYMMDD."


class TableOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint: str = Field(description="PandaDataClient method that produced the table.")
    rows: int = Field(description="Rows returned.")
    columns: list[str] = Field(description="Columns of the returned table.")
    output: str | None = Field(description="Table artifact path, if --output was given.")
    preview: list[dict] = Field(description="First rows of the table.")


def _fetch_table(args, method: str, **kwargs) -> CommandResult:
    """Call one client method and report the table; the table itself goes to --output."""
    _prepare_output(args)
    client = _client()
    frame = _table(_call(getattr(client, method), **kwargs), method)
    artifacts = _write_output(frame, args, method.removeprefix("get_"))
    warnings = [] if len(frame) else ["PandaData returned no rows."]
    return CommandResult(
        data=TableOutput(
            endpoint=method,
            rows=len(frame),
            columns=list(map(str, frame.columns)),
            output=artifacts[0].path if artifacts else None,
            preview=_preview(frame, args.preview),
        ),
        artifacts=artifacts,
        warnings=warnings,
    )


class StockDetailInput(OutputOptions):
    symbols: list[str] = Field(
        default_factory=list, description="Stock symbols; empty returns all. " + SYMBOLS_HELP
    )
    market: str = Field("cn", description="Market code passed to get_stock_detail.")
    status: int | None = Field(None, description="Listing status filter.")
    fields: list[str] = Field(default_factory=list, description=FIELDS_HELP)


def stock_detail(args: StockDetailInput) -> CommandResult:
    return _fetch_table(
        args,
        "get_stock_detail",
        symbol=_one_or_many(_items(args.symbols)) or "",
        fields=_items(args.fields) or None,
        market=args.market,
        status=args.status,
    )


class FundDetailInput(OutputOptions):
    symbols: list[str] = Field(
        default_factory=list, description="Fund symbols, listed or *.OF. " + SYMBOLS_HELP
    )
    exchange: list[str] = Field(default_factory=list, description="Exchange filter, SH or SZ.")
    type: list[str] = Field(default_factory=list, description="Fund type filter.")
    operation_mode: list[str] = Field(default_factory=list, description="Operation mode filter.")
    etf_lof_type: list[str] = Field(
        default_factory=list, description="ETF or LOF subtype; ETF discovers listed ETFs."
    )
    is_class_fund: list[int] = Field(
        default_factory=list, description="Class-fund flag filter, 0 or 1."
    )
    index_fund_type: list[str] = Field(default_factory=list, description="Index fund type filter.")
    status: list[str] = Field(default_factory=list, description="Listing status filter, e.g. L.")
    fund_status: list[str] = Field(default_factory=list, description="Fund status filter.")
    fields: list[str] = Field(default_factory=list, description=FIELDS_HELP)


def fund_detail(args: FundDetailInput) -> CommandResult:
    return _fetch_table(
        args,
        "get_fund_detail",
        symbol=_one_or_many(_items(args.symbols)),
        exchange=_one_or_many(_items(args.exchange)),
        type=_one_or_many(_items(args.type)),
        operation_mode=_one_or_many(_items(args.operation_mode)),
        etf_lof_type=_one_or_many(_items(args.etf_lof_type)),
        is_class_fund=_one_or_many(args.is_class_fund),
        index_fund_type=_one_or_many(_items(args.index_fund_type)),
        status=_one_or_many(_items(args.status)),
        fund_status=_one_or_many(_items(args.fund_status)),
        fields=_items(args.fields) or None,
    )


class IndexDetailInput(OutputOptions):
    symbols: list[str] = Field(
        default_factory=list, description="Index symbols; empty returns all. " + SYMBOLS_HELP
    )
    status: int | None = Field(None, description="Index status filter.")
    fields: list[str] = Field(default_factory=list, description=FIELDS_HELP)


def index_detail(args: IndexDetailInput) -> CommandResult:
    return _fetch_table(
        args,
        "get_index_detail",
        symbol=_one_or_many(_items(args.symbols)) or "",
        status=args.status,
        fields=_items(args.fields) or None,
    )


class IndexIndicatorInput(OutputOptions):
    symbols: list[str] = Field(
        default_factory=list, description="Index symbols; empty returns all. " + SYMBOLS_HELP
    )
    start: Date | None = Field(None, description=START_HELP)
    end: Date | None = Field(None, description=END_HELP)
    fields: list[str] = Field(default_factory=list, description=FIELDS_HELP)

    check_order = model_validator(mode="after")(_check_order)


def index_indicator(args: IndexIndicatorInput) -> CommandResult:
    return _fetch_table(
        args,
        "get_index_indicator",
        symbol=_one_or_many(_items(args.symbols)) or "",
        start_date=args.start,
        end_date=args.end,
        fields=_items(args.fields) or None,
    )


class IndexWeightsInput(OutputOptions):
    start: Date = Field(description=START_HELP)
    end: Date = Field(description=END_HELP)
    index_symbol: list[str] = Field(
        default_factory=list,
        description="Index symbols, such as SHSE.000300 (QuantSpace or native).",
    )
    stock_symbol: list[str] = Field(
        default_factory=list, description="Constituent stock symbols to filter by."
    )
    fields: list[str] = Field(default_factory=list, description=FIELDS_HELP)

    check_order = model_validator(mode="after")(_check_order)


def index_weights(args: IndexWeightsInput) -> CommandResult:
    return _fetch_table(
        args,
        "get_index_weights",
        start_date=args.start,
        end_date=args.end,
        index_symbol=_one_or_many(_items(args.index_symbol)) or "",
        stock_symbol=_one_or_many(_items(args.stock_symbol)) or "",
        fields=_items(args.fields) or None,
    )


class IndustryDetailInput(OutputOptions):
    level: list[str] = Field(default_factory=list, description="Industry level filter.")
    fields: list[str] = Field(default_factory=list, description=FIELDS_HELP)


def industry_detail(args: IndustryDetailInput) -> CommandResult:
    return _fetch_table(
        args,
        "get_industry_detail",
        level=_one_or_many(_items(args.level)),
        fields=_items(args.fields) or None,
    )


class IndustryConstituentsInput(OutputOptions):
    industry_code: list[str] = Field(default_factory=list, description="Industry code filter.")
    stock_symbol: list[str] = Field(
        default_factory=list, description="Stock symbols whose industries to list."
    )
    level: str | None = Field(None, description="Industry level.")
    fields: list[str] = Field(default_factory=list, description=FIELDS_HELP)


def industry_constituents(args: IndustryConstituentsInput) -> CommandResult:
    return _fetch_table(
        args,
        "get_industry_constituents",
        industry_code=_one_or_many(_items(args.industry_code)),
        stock_symbol=_one_or_many(_items(args.stock_symbol)),
        level=args.level,
        fields=_items(args.fields) or None,
    )


class StockIndustryInput(OutputOptions):
    stock_symbol: str = Field(description="One stock symbol, QuantSpace or native.")
    level: str | None = Field(None, description="Industry level.")


def stock_industry(args: StockIndustryInput) -> CommandResult:
    return _fetch_table(
        args, "get_stock_industry", stock_symbol=args.stock_symbol.strip(), level=args.level
    )


class ConceptListInput(OutputOptions):
    concept: list[str] = Field(default_factory=list, description="Concept name or code filter.")
    start: Date | None = Field(None, description=START_HELP)
    end: Date | None = Field(None, description=END_HELP)

    check_order = model_validator(mode="after")(_check_order)


def concept_list(args: ConceptListInput) -> CommandResult:
    return _fetch_table(
        args,
        "get_concept_list",
        concept=_one_or_many(_items(args.concept)),
        start_date=args.start,
        end_date=args.end,
    )


class ConceptConstituentsInput(OutputOptions):
    concept: list[str] = Field(default_factory=list, description="Concept name or code filter.")
    concept_stock: list[str] = Field(
        default_factory=list, description="Stock symbols whose concepts to list."
    )
    start: Date | None = Field(None, description=START_HELP)
    end: Date | None = Field(None, description=END_HELP)
    fields: list[str] = Field(default_factory=list, description=FIELDS_HELP)

    check_order = model_validator(mode="after")(_check_order)


def concept_constituents(args: ConceptConstituentsInput) -> CommandResult:
    return _fetch_table(
        args,
        "get_concept_constituents",
        concept=_one_or_many(_items(args.concept)),
        concept_stock=_one_or_many(_items(args.concept_stock)),
        start_date=args.start,
        end_date=args.end,
        fields=_items(args.fields) or None,
    )


class EtfInput(OutputOptions):
    start: Date = Field(description=START_HELP)
    end: Date = Field(description=END_HELP)
    symbols: list[str] = Field(
        default_factory=list, description="ETF symbols; empty returns all. " + SYMBOLS_HELP
    )
    exchange: list[str] = Field(default_factory=list, description="Exchange filter, SH or SZ.")
    fields: list[str] = Field(default_factory=list, description=FIELDS_HELP)

    check_order = model_validator(mode="after")(_check_order)


def _etf(method: str):
    def handler(args: EtfInput) -> CommandResult:
        return _fetch_table(
            args,
            method,
            start_date=args.start,
            end_date=args.end,
            symbol=_one_or_many(_items(args.symbols)),
            exchange=_one_or_many(_items(args.exchange)),
            fields=_items(args.fields) or None,
        )

    handler.__name__ = method
    return handler


# ---------------------------------------------------------------------------
# ingest.raw
# ---------------------------------------------------------------------------


class RawInput(OutputOptions):
    method: str | None = Field(
        None, description="Public panda_data SDK function name, such as get_trade_cal."
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON object of keyword arguments passed unchanged to the SDK function. "
        "Symbols are NOT converted: use the SDK's native format (510300.SH). "
        "Returned symbol columns are converted to QuantSpace format.",
    )
    list: bool = Field(
        False, description="List the callable public SDK functions instead of calling one."
    )


class RawOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: str | None = Field(description="SDK function called, if any.")
    methods: list[str] = Field(description="Callable public SDK functions when listing.")
    rows: int = Field(description="Rows returned.")
    columns: list[str] = Field(description="Columns of the returned table.")
    output: str | None = Field(description="Table artifact path, if --output was given.")
    preview: list[dict] = Field(description="First rows of the table.")


def _sdk_functions(sdk) -> list[str]:
    return sorted(
        name
        for name in dir(sdk)
        if not name.startswith("_")
        and name not in RAW_EXCLUDED
        and inspect.isroutine(getattr(sdk, name, None))
    )


def raw(args: RawInput) -> CommandResult:
    if args.list:
        if args.method or args.params or args.output:
            raise CLIError("INVALID_INPUT", "--list takes no method, params or output")
        methods = _sdk_functions(_require_sdk())
        return CommandResult(
            data=RawOutput(
                method=None, methods=methods, rows=0, columns=[], output=None, preview=[]
            )
        )
    if not args.method:
        raise CLIError(
            "INVALID_INPUT",
            "method is required",
            hint="Run `uv run qs ingest raw --list` for callable SDK functions.",
        )
    _prepare_output(args)
    sdk = _require_sdk()
    if args.method not in _sdk_functions(sdk):
        raise CLIError(
            "INVALID_INPUT",
            f"Not a callable public panda_data function: {args.method}",
            hint="Run `uv run qs ingest raw --list` for callable SDK functions.",
        )
    client = _client()
    # PandaDataClient._call is the client's own path: it authenticates once and
    # converts returned symbol columns; input symbols are left untouched.
    frame = _table(_call(client._call, args.method, **args.params), args.method)
    artifacts = _write_output(frame, args, args.method.removeprefix("get_"))
    return CommandResult(
        data=RawOutput(
            method=args.method,
            methods=[],
            rows=len(frame),
            columns=list(map(str, frame.columns)),
            output=artifacts[0].path if artifacts else None,
            preview=_preview(frame, args.preview),
        ),
        artifacts=artifacts,
        warnings=[] if len(frame) else ["PandaData returned no rows."],
    )


# ---------------------------------------------------------------------------
# ingest.future-ticks
# ---------------------------------------------------------------------------

TICK_DEFAULT_ROOT = "data/export/panda_future_ticks"


class FutureTicksInput(CLIModel):
    underlying: str = Field(
        "SA", description="Futures underlying code, such as SA; ignored with --all-underlyings."
    )
    all_underlyings: bool = Field(
        False, description="Download every underlying serially into --output-root."
    )
    start: Date | None = Field(
        None, description="Inclusive start date; defaults to about five years before today."
    )
    end: Date | None = Field(None, description="Inclusive end date; defaults to today.")
    output_dir: Path | None = Field(
        None,
        description="Single-underlying output directory, relative to the workspace root. "
        f"Defaults to {TICK_DEFAULT_ROOT}/<underlying>.",
    )
    output_root: Path | None = Field(
        None,
        description="Root holding one subdirectory per underlying (all mode: the root itself); "
        f"all-underlyings mode defaults to {TICK_DEFAULT_ROOT}.",
    )
    workers: int | None = Field(
        None, ge=1, description="Worker processes; the downloader default is min(4, CPU count)."
    )
    symbol_batch_size: int = Field(8, ge=1, description="Contract symbols per request batch.")
    progress_every: int = Field(1, ge=1, description="Progress report interval, in tasks.")
    max_retries: int = Field(3, ge=0, description="Retries per task.")
    retry_sleep: float = Field(2.0, ge=0, description="Seconds between retries.")
    retry_failed_rounds: int = Field(2, ge=0, description="Extra rounds for failed tasks.")
    http_timeout: int = Field(60, gt=0, description="HTTP timeout in seconds.")
    stall_timeout: int = Field(
        300, gt=0, description="Seconds without completed futures before the pool is terminated."
    )
    provider_timeout_threshold: int = Field(
        3, ge=1, description="Timeouts of one symbol-day before it counts as a provider gap."
    )
    allow_provider_timeout_gaps: bool = Field(
        False, description="Treat repeatedly timed-out symbol-days as acceptable gaps."
    )
    fallback_on_batch_timeout: bool = Field(
        True,
        description="Retry a timed-out batch symbol by symbol; --no-fallback-on-batch-timeout "
        "disables it.",
    )
    compression: str = Field("zstd", description="Parquet compression codec.")
    compression_level: int = Field(9, description="Parquet compression level.")
    overwrite: bool = Field(
        False, description="Discard existing tick outputs and download again; otherwise resume."
    )
    include_dominant: bool = Field(False, description="Include dominant continuous contracts.")
    refresh_discovery: bool = Field(False, description="Refresh contract discovery.")
    combine: bool = Field(
        True, description="Write combined per-contract files; --no-combine skips them."
    )
    monthly_output: bool = Field(False, description="Write monthly output files.")
    month_by_month: bool = Field(
        True, description="Run month by month; --no-month-by-month disables it."
    )
    min_free_disk_gb: float = Field(
        100.0, ge=0, description="All-underlyings mode pauses below this free disk space, in GB."
    )
    limit_tasks: int = Field(0, ge=0, description="Debug limit on tasks; 0 means no limit.")
    limit_underlyings: int = Field(
        0, ge=0, description="Debug limit on underlyings; 0 means no limit."
    )
    priority_underlyings: str = Field(
        "", description="Comma-separated underlyings processed before the rest."
    )
    data_root: Path | None = Field(
        None,
        description="Managed data root, used only to keep tick output out of its store "
        "namespaces; otherwise QUANTSPACE_DATA_ROOT or repository data/.",
    )

    check_order = model_validator(mode="after")(_check_order)


class FutureTicksOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    underlying: str = Field(description="Requested underlying; unused in all mode.")
    all_underlyings: bool = Field(description="Whether all-underlyings mode ran.")
    output_dir: str = Field(description="Resolved output directory.")
    status: Literal["ok", "failed"] = Field(description="Downloader outcome.")
    exit_code: int = Field(description="Downloader exit code; 1 when tasks failed.")
    argv: list[str] = Field(description="Arguments passed to the downloader.")


# (model field, downloader option) for options that always carry a value.
TICK_VALUE_OPTIONS = (
    ("symbol_batch_size", "--symbol-batch-size"),
    ("progress_every", "--progress-every"),
    ("max_retries", "--max-retries"),
    ("retry_sleep", "--retry-sleep"),
    ("retry_failed_rounds", "--retry-failed-rounds"),
    ("http_timeout", "--http-timeout"),
    ("stall_timeout", "--stall-timeout"),
    ("provider_timeout_threshold", "--provider-timeout-threshold"),
    ("compression", "--compression"),
    ("compression_level", "--compression-level"),
    ("min_free_disk_gb", "--min-free-disk-gb"),
    ("limit_tasks", "--limit-tasks"),
    ("limit_underlyings", "--limit-underlyings"),
    ("priority_underlyings", "--priority-underlyings"),
)
TICK_SWITCHES = (
    ("all_underlyings", "--all-underlyings"),
    ("allow_provider_timeout_gaps", "--allow-provider-timeout-gaps"),
    ("overwrite", "--overwrite"),
    ("include_dominant", "--include-dominant"),
    ("refresh_discovery", "--refresh-discovery"),
    ("monthly_output", "--monthly-output"),
)
# The downloader's switches are negative (--no-x); the model fields are positive so that
# the generated --x/--no-x flags work, and argparse's store_true flag is sent when False.
TICK_NEGATED_SWITCHES = (
    ("fallback_on_batch_timeout", "--no-fallback-on-batch-timeout"),
    ("combine", "--no-combine"),
    ("month_by_month", "--no-month-by-month"),
)


def _tick_argv(args: FutureTicksInput) -> tuple[list[str], str]:
    """Downloader argv for the model, plus the output path it will use."""
    if args.all_underlyings and args.output_dir:
        raise CLIError("INVALID_INPUT", "--output-dir is for one underlying; use --output-root")
    if args.output_dir and args.output_root:
        raise CLIError("INVALID_INPUT", "Use --output-dir or --output-root, not both")
    underlying = resolve_symbols([args.underlying])
    if len(underlying) != 1:
        raise CLIError("INVALID_INPUT", "underlying must be a single code")
    code = underlying[0]
    argv = ["--underlying", code]
    if args.start:
        argv += ["--start-date", args.start]
    if args.end:
        argv += ["--end-date", args.end]
    if args.all_underlyings:
        output = str(args.output_root or TICK_DEFAULT_ROOT)
        argv += ["--output-root", output]
    elif args.output_root:
        output = str(args.output_root)
        argv += ["--output-root", output]
    else:
        # The downloader's own default is the SA directory whatever the underlying is.
        output = str(args.output_dir or f"{TICK_DEFAULT_ROOT}/{code}")
        argv += ["--output-dir", output]
    if args.workers is not None:
        argv += ["--workers", str(args.workers)]
    for field, option in TICK_VALUE_OPTIONS:
        argv += [option, str(getattr(args, field))]
    argv += [option for field, option in TICK_SWITCHES if getattr(args, field)]
    argv += [option for field, option in TICK_NEGATED_SWITCHES if not getattr(args, field)]
    return argv, output


def future_ticks(args: FutureTicksInput) -> CommandResult:
    from skills.ingest import panda_future_tick as tick

    argv, output = _tick_argv(args)
    code = argv[1]
    base = Path(output).expanduser()
    resolved = (tick.ROOT / base).resolve()
    if args.output_root and not args.all_underlyings:
        resolved = resolved / code
    if resolved.exists() and not resolved.is_dir():
        raise CLIError("INVALID_INPUT", f"Tick output is not a directory: {resolved}")
    # An existing directory is resumed by the downloader's manifests; only the managed
    # store namespaces are off limits.
    check_output(
        resolved / "__qs_tick_output_probe__.parquet", overwrite=True, data_root=args.data_root
    )
    _require_sdk()
    tick.load_dotenv()
    _require_credentials()
    try:
        status = tick.main(argv)
    except SystemExit as exc:
        raise CLIError(
            "INVALID_INPUT", f"The tick downloader rejected its arguments (exit {exc.code})"
        ) from exc
    except CLIError:
        raise
    except Exception as exc:
        raise _translate(exc) from exc
    return CommandResult(
        data=FutureTicksOutput(
            underlying=args.underlying,
            all_underlyings=args.all_underlyings,
            output_dir=str(resolved),
            status="ok" if status == 0 else "failed",
            exit_code=status,
            argv=argv,
        ),
        exit_code=status,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

NETWORK_OUTPUT = ("network", "writes-output")

COMMANDS = [
    Command(
        "ingest.bars",
        BarsInput,
        BarsOutput,
        bars,
        "Fetch stock, index, future, fund, HK or US bars; optionally store them.",
        side_effects=("network", "writes-output", "writes-store"),
        priority="P0",
    ),
    Command(
        "ingest.adj-factor",
        AdjFactorInput,
        AdjFactorOutput,
        adj_factor,
        "Fetch stock adjustment-factor events; optionally store them per symbol.",
        side_effects=("network", "writes-output", "writes-store"),
    ),
    Command(
        "ingest.ref.stock-detail",
        StockDetailInput,
        TableOutput,
        stock_detail,
        "Fetch stock basic information (get_stock_detail).",
        side_effects=NETWORK_OUTPUT,
    ),
    Command(
        "ingest.ref.fund-detail",
        FundDetailInput,
        TableOutput,
        fund_detail,
        "Fetch fund and ETF metadata (get_fund_detail).",
        side_effects=NETWORK_OUTPUT,
    ),
    Command(
        "ingest.ref.index-detail",
        IndexDetailInput,
        TableOutput,
        index_detail,
        "Fetch index basic information (get_index_detail).",
        side_effects=NETWORK_OUTPUT,
    ),
    Command(
        "ingest.ref.index-indicator",
        IndexIndicatorInput,
        TableOutput,
        index_indicator,
        "Fetch index valuation indicators (get_index_indicator).",
        side_effects=NETWORK_OUTPUT,
    ),
    Command(
        "ingest.ref.index-weights",
        IndexWeightsInput,
        TableOutput,
        index_weights,
        "Fetch index constituent weights (get_index_weights).",
        side_effects=NETWORK_OUTPUT,
    ),
    Command(
        "ingest.ref.industry-detail",
        IndustryDetailInput,
        TableOutput,
        industry_detail,
        "Fetch the industry taxonomy (get_industry_detail).",
        side_effects=NETWORK_OUTPUT,
    ),
    Command(
        "ingest.ref.industry-constituents",
        IndustryConstituentsInput,
        TableOutput,
        industry_constituents,
        "Fetch industry constituents (get_industry_constituents).",
        side_effects=NETWORK_OUTPUT,
    ),
    Command(
        "ingest.ref.stock-industry",
        StockIndustryInput,
        TableOutput,
        stock_industry,
        "Fetch one stock's industry classification (get_stock_industry).",
        side_effects=NETWORK_OUTPUT,
    ),
    Command(
        "ingest.ref.concept-list",
        ConceptListInput,
        TableOutput,
        concept_list,
        "Fetch the concept list (get_concept_list).",
        side_effects=NETWORK_OUTPUT,
    ),
    Command(
        "ingest.ref.concept-constituents",
        ConceptConstituentsInput,
        TableOutput,
        concept_constituents,
        "Fetch concept constituents (get_concept_constituents).",
        side_effects=NETWORK_OUTPUT,
    ),
    Command(
        "ingest.etf.limits",
        EtfInput,
        TableOutput,
        _etf("get_fund_etf_cr_limits"),
        "Fetch ETF creation/redemption limits (get_fund_etf_cr_limits).",
        side_effects=NETWORK_OUTPUT,
        priority="P2",
    ),
    Command(
        "ingest.etf.net",
        EtfInput,
        TableOutput,
        _etf("get_fund_etf_cr_net"),
        "Fetch ETF net creation/redemption and fund flows (get_fund_etf_cr_net).",
        side_effects=NETWORK_OUTPUT,
        priority="P2",
    ),
    Command(
        "ingest.etf.constituents",
        EtfInput,
        TableOutput,
        _etf("get_fund_etf_constituents"),
        "Fetch ETF creation/redemption baskets (get_fund_etf_constituents).",
        side_effects=NETWORK_OUTPUT,
        priority="P2",
    ),
    Command(
        "ingest.etf.list",
        EtfInput,
        TableOutput,
        _etf("get_fund_etf_cr"),
        "Fetch ETF creation/redemption lists (get_fund_etf_cr).",
        side_effects=NETWORK_OUTPUT,
        priority="P2",
    ),
    Command(
        "ingest.raw",
        RawInput,
        RawOutput,
        raw,
        "Call any public panda_data SDK function, or list them.",
        side_effects=NETWORK_OUTPUT,
        positional=("method",),
    ),
    Command(
        "ingest.future-ticks",
        FutureTicksInput,
        FutureTicksOutput,
        future_ticks,
        "Run the long-running futures tick downloader; exit 1 when tasks fail.",
        side_effects=NETWORK_OUTPUT,
        priority="P2",
    ),
]
