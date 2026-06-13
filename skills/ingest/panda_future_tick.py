"""Download PandaAI futures tick data as Parquet files."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, as_completed, wait
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TICK_COLUMNS = [
    "symbol",
    "date",
    "timestamp",
    "mill_sec",
    "exchange",
    "underlying_symbol",
    "trading_date",
    "trading_code",
    "last",
    "volume",
    "amount",
    "turnover",
    "open",
    "high",
    "low",
    "limit_up",
    "limit_down",
    "open_interest",
    "pre_settelment",
    "pre_close",
    "ask",
    "ask_vol",
    "bid",
    "bid_vol",
]
FIVE_LEVEL_COLUMNS = ["ask", "ask_vol", "bid", "bid_vol"]
RESULT_COLUMNS = ["symbol", "date", "status", "rows", "bytes", "path", "error"]
FUTURE_DETAIL_FIELDS = [
    "symbol",
    "exchange",
    "trading_code",
    "underlying_symbol",
    "listed_date",
    "de_listed_date",
]


@dataclass(frozen=True)
class TickTask:
    symbol: str
    date: str
    output_path: str


@dataclass(frozen=True)
class TickBatchTask:
    date: str
    symbols: tuple[str, ...]
    chunks_dir: str

    def output_path(self, symbol: str) -> Path:
        return Path(self.chunks_dir) / safe_symbol_name(symbol) / f"{self.date}.parquet"


@dataclass(frozen=True)
class WorkerConfig:
    username: str
    password: str
    max_retries: int
    retry_sleep: float
    compression: str
    compression_level: int | None
    overwrite: bool
    http_timeout: int
    fallback_on_batch_timeout: bool


@dataclass(frozen=True)
class QualityReport:
    status: str
    monthly_files: int
    rows: int
    expected_symbol_days: int
    observed_symbol_days: int
    no_data_symbol_days: int
    provider_timeout_symbol_days: int
    missing_symbol_days: list[tuple[str, str]]
    invalid_files: list[dict[str, Any]]


@dataclass(frozen=True)
class UnderlyingRunResult:
    underlying: str
    status: str
    workers: int
    contracts: int
    active_symbol_days: int
    failed_tasks: int
    rows_downloaded: int
    output_dir: str
    error: str = ""


_WORKER_TOKEN_READY = False


def is_token_expired_error(message: str) -> bool:
    """Return True when PandaAI reports an expired authentication token."""
    return "token" in message.lower() and ("过期" in message or "expired" in message.lower())


def _refresh_worker_token(config: WorkerConfig) -> None:
    global _WORKER_TOKEN_READY

    _init_panda_data(config.username, config.password, http_timeout=config.http_timeout)
    _WORKER_TOKEN_READY = True


def safe_symbol_name(symbol: str) -> str:
    """Return a readable filesystem-safe symbol name."""
    return symbol.replace("/", "_").replace(":", "_")


def load_dotenv(env_path: Path | None = None) -> None:
    """Load simple KEY=VALUE entries from .env without overriding the shell."""
    path = env_path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def default_start_date(today: date | None = None) -> str:
    """Return a YYYYMMDD date roughly five calendar years before today."""
    current = today or date.today()
    try:
        start = current.replace(year=current.year - 5)
    except ValueError:
        start = current.replace(year=current.year - 5, day=28)
    return start.strftime("%Y%m%d")


def _configure_http_timeout(timeout_seconds: int) -> None:
    os.environ["JAVA_SERVICE_TIMEOUT"] = str(timeout_seconds)
    os.environ["HTTP_TIMEOUT"] = str(timeout_seconds)


def _init_panda_data(username: str, password: str, *, http_timeout: int = 60) -> Any:
    _configure_http_timeout(http_timeout)
    import panda_data  # noqa: PLC0415

    panda_data.init_token(username=username, password=password)
    return panda_data


def _future_tick_func() -> Any:
    import panda_data  # noqa: PLC0415

    fn = getattr(panda_data, "get_future_tick", None)
    if fn is not None:
        return fn

    from panda_data.readers.market_reader import get_future_tick  # noqa: PLC0415

    return get_future_tick


def _normalise_yyyymmdd(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y%m%d")
    text = str(value)
    if "-" in text or ":" in text:
        return pd.to_datetime(text).strftime("%Y%m%d")
    return text[:8]


def split_date_ranges(
    start_date: str, end_date: str, *, max_years: int = 5
) -> list[tuple[str, str]]:
    """Split a YYYYMMDD range into segments accepted by panda_data daily APIs."""
    start = pd.to_datetime(_normalise_yyyymmdd(start_date), format="%Y%m%d").date()
    end = pd.to_datetime(_normalise_yyyymmdd(end_date), format="%Y%m%d").date()
    if start > end:
        raise ValueError(f"start_date {start_date} is after end_date {end_date}")

    ranges: list[tuple[str, str]] = []
    current = start
    while current <= end:
        try:
            capped = current.replace(year=current.year + max_years)
        except ValueError:
            capped = current.replace(year=current.year + max_years, day=28)
        segment_end = min(capped, end)
        ranges.append((current.strftime("%Y%m%d"), segment_end.strftime("%Y%m%d")))
        current = segment_end + timedelta(days=1)
    return ranges


def month_key(value: Any) -> str:
    """Return YYYYMM for supported date-like values."""
    normalised = _normalise_yyyymmdd(value)
    if len(normalised) < 6:
        raise ValueError(f"Cannot derive month from {value!r}")
    return normalised[:6]


def sorted_underlyings(contracts: pd.DataFrame) -> list[str]:
    """Return sorted non-dominant futures underlying symbols."""
    if contracts.empty:
        return []
    df = contracts.copy()
    if "symbol" in df.columns:
        df = df[~df["symbol"].astype(str).str.contains("_DOMINANT", na=False)]
    return sorted(df["underlying_symbol"].dropna().astype(str).str.upper().unique().tolist())


def prioritize_underlyings(underlyings: list[str], priority: str | None) -> list[str]:
    """Move comma-separated priority underlyings to the front while preserving the rest."""
    if not priority:
        return underlyings
    priority_items = [item.strip().upper() for item in priority.split(",") if item.strip()]
    if not priority_items:
        return underlyings
    available = {underlying.upper(): underlying for underlying in underlyings}
    ordered: list[str] = []
    seen: set[str] = set()
    for item in priority_items:
        if item in available and item not in seen:
            ordered.append(available[item])
            seen.add(item)
    for underlying in underlyings:
        key = underlying.upper()
        if key not in seen:
            ordered.append(underlying)
            seen.add(key)
    return ordered


def effective_underlying_start_date(contracts: pd.DataFrame, requested_start_date: str) -> str:
    """Return max(requested start, earliest available listing date for an underlying)."""
    requested = _normalise_yyyymmdd(requested_start_date)
    if contracts.empty or "listed_date" not in contracts.columns:
        return requested

    listed_dates = contracts["listed_date"].dropna().map(_normalise_yyyymmdd)
    listed_dates = listed_dates[listed_dates.astype(str).str.len().eq(8)]
    if listed_dates.empty:
        return requested
    earliest_listing = str(listed_dates.min())
    return max(requested, earliest_listing)


def free_disk_below_threshold(*, free_bytes: int, min_free_gb: float) -> bool:
    """Return True when free bytes are below the configured GB threshold."""
    return free_bytes < min_free_gb * 1024**3


def free_disk_gb(path: Path) -> float:
    """Return available disk space for path, in GiB."""
    return shutil.disk_usage(path).free / 1024**3


def is_five_level_sequence(value: Any) -> bool:
    """Return True for list/array-like five-level order book values."""
    return (
        hasattr(value, "__len__") and not isinstance(value, (str, bytes, dict)) and len(value) == 5
    )


def parquet_kwargs(compression: str, compression_level: int | None = None) -> dict[str, Any]:
    """Return pandas parquet write arguments with a supported compression level."""
    kwargs: dict[str, Any] = {"compression": compression}
    if compression_level is not None and compression in {"brotli", "gzip", "zstd"}:
        kwargs["compression_level"] = compression_level
    return kwargs


def append_download_results(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    round_idx: int | None = None,
) -> None:
    """Append download rows to a CSV file for interruption-safe progress."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    if round_idx is not None:
        frame.insert(0, "round", round_idx)
    frame.to_csv(path, mode="a", index=False, header=not path.exists())


def empty_results_frame() -> pd.DataFrame:
    """Return an empty download results frame."""
    return pd.DataFrame(columns=RESULT_COLUMNS)


def read_download_results(path: Path) -> pd.DataFrame:
    """Read download results, tolerating missing files and older CSV schemas."""
    if not path.exists():
        return empty_results_frame()
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            return empty_results_frame()
        has_round_header = header == ["round", *RESULT_COLUMNS]
        for raw in reader:
            if not raw:
                continue
            if has_round_header and len(raw) == len(header):
                values = dict(zip(RESULT_COLUMNS, raw[1:], strict=False))
            elif len(raw) == len(RESULT_COLUMNS):
                values = dict(zip(RESULT_COLUMNS, raw, strict=False))
            elif len(raw) == len(RESULT_COLUMNS) + 1:
                values = dict(zip(RESULT_COLUMNS, raw[1:], strict=False))
            else:
                continue
            rows.append(values)
    frame = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    for column in RESULT_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame


def activity_pairs(daily_activity: pd.DataFrame) -> set[tuple[str, str]]:
    """Return normalized symbol-date pairs for an activity frame."""
    activity = daily_activity[["symbol", "date"]].copy()
    activity["date"] = activity["date"].map(_normalise_yyyymmdd)
    return {
        (str(row.symbol), str(row.date))
        for row in activity.drop_duplicates(["symbol", "date"]).itertuples(index=False)
    }


def read_pair_csv(path: Path) -> set[tuple[str, str]]:
    """Read a symbol-date CSV into a normalized pair set."""
    if not path.exists():
        return set()
    frame = pd.read_csv(path)
    if not {"symbol", "date"}.issubset(frame.columns):
        return set()
    return {
        (str(row.symbol), _normalise_yyyymmdd(row.date))
        for row in frame[["symbol", "date"]].dropna().itertuples(index=False)
    }


def write_pair_csv(path: Path, pairs: set[tuple[str, str]]) -> None:
    """Write normalized symbol-date pairs to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"symbol": symbol, "date": day} for symbol, day in sorted(pairs)],
        columns=["symbol", "date"],
    ).to_csv(path, index=False)


def collect_no_data_symbol_days(
    daily_activity: pd.DataFrame, chunks_dir: Path
) -> set[tuple[str, str]]:
    """Return symbol-date pairs whose chunk exists and has zero rows."""
    no_data: set[tuple[str, str]] = set()
    try:
        import pyarrow.parquet as pq  # noqa: PLC0415
    except Exception:
        pq = None

    for row in _activity_with_month(daily_activity).itertuples(index=False):
        symbol = str(row.symbol)
        day = str(row.date)
        path = chunks_dir / safe_symbol_name(symbol) / f"{day}.parquet"
        if not path.exists():
            continue
        try:
            if pq is not None:
                row_count = pq.ParquetFile(path).metadata.num_rows
            else:
                row_count = len(pd.read_parquet(path))
        except Exception:
            continue
        if row_count == 0:
            no_data.add((symbol, day))
    return no_data


def provider_timeout_symbol_days(
    results: pd.DataFrame,
    *,
    threshold: int,
) -> set[tuple[str, str]]:
    """Return symbol-date pairs that repeatedly failed with provider timeout errors."""
    if results.empty or threshold <= 0:
        return set()
    required = {"symbol", "date", "status", "error"}
    if not required.issubset(results.columns):
        return set()

    failed = results[
        results["status"].astype(str).eq("failed")
        & results["error"].astype(str).str.contains("timed out", case=False, na=False)
    ].copy()
    if failed.empty:
        return set()

    counts = failed.groupby(["symbol", "date"]).size()
    return {
        (str(symbol), _normalise_yyyymmdd(day))
        for (symbol, day), count in counts.items()
        if int(count) >= threshold
    }


def filter_results_to_pairs(
    results: pd.DataFrame,
    pairs: set[tuple[str, str]],
) -> pd.DataFrame:
    """Filter download results to a symbol-date pair set."""
    if results.empty or not pairs:
        return empty_results_frame()
    mask = list(
        zip(
            results["symbol"].astype(str),
            results["date"].map(_normalise_yyyymmdd),
            strict=False,
        )
    )
    return results[[pair in pairs for pair in mask]].copy()


def _activity_with_month(daily_activity: pd.DataFrame) -> pd.DataFrame:
    activity = daily_activity[["symbol", "date"]].copy()
    activity["date"] = activity["date"].map(_normalise_yyyymmdd)
    activity = activity[activity["date"].astype(str).str.len().eq(8)]
    activity["month"] = activity["date"].map(month_key)
    return activity.drop_duplicates(["symbol", "date"]).sort_values(["month", "symbol", "date"])


def discover_future_contracts(
    underlying_symbol: str,
    *,
    include_dominant: bool = False,
) -> pd.DataFrame:
    """Fetch PandaAI futures metadata and return contracts for one underlying."""
    import panda_data  # noqa: PLC0415

    df = panda_data.get_future_detail(
        fields=FUTURE_DETAIL_FIELDS,
        is_trading=None,
    )
    if df.empty:
        return df

    underlying = underlying_symbol.upper()
    contracts = df[df["underlying_symbol"].astype(str).str.upper().eq(underlying)].copy()
    if not include_dominant:
        contracts = contracts[~contracts["symbol"].astype(str).str.contains("_DOMINANT")]
    return contracts.sort_values("symbol").reset_index(drop=True)


def discover_all_future_contracts(*, include_dominant: bool = False) -> pd.DataFrame:
    """Fetch all PandaAI futures metadata."""
    import panda_data  # noqa: PLC0415

    df = panda_data.get_future_detail(
        fields=FUTURE_DETAIL_FIELDS,
        is_trading=None,
    )
    if df.empty or include_dominant:
        return df.sort_values("symbol").reset_index(drop=True)
    return (
        df[~df["symbol"].astype(str).str.contains("_DOMINANT", na=False)]
        .sort_values("symbol")
        .reset_index(drop=True)
    )


def fetch_daily_activity(
    symbols: list[str],
    start_date: str,
    end_date: str,
    *,
    symbol_chunk_size: int = 25,
    retries: int = 3,
) -> pd.DataFrame:
    """Use daily futures bars to identify traded symbol-date pairs."""
    import panda_data  # noqa: PLC0415

    frames: list[pd.DataFrame] = []
    date_ranges = split_date_ranges(start_date, end_date, max_years=5)
    for offset in range(0, len(symbols), symbol_chunk_size):
        chunk = symbols[offset : offset + symbol_chunk_size]
        for range_start, range_end in date_ranges:
            for attempt in range(1, retries + 1):
                try:
                    df = panda_data.get_market_data(
                        symbol=chunk,
                        start_date=range_start,
                        end_date=range_end,
                        type="future",
                        fields=["date"],
                    )
                    if not df.empty:
                        frames.append(df[["symbol", "date"]].copy())
                    break
                except Exception:
                    if attempt == retries:
                        raise
                    time.sleep(min(2**attempt, 15))

    if not frames:
        return pd.DataFrame(columns=["symbol", "date"])

    activity = pd.concat(frames, ignore_index=True)
    activity["date"] = activity["date"].map(_normalise_yyyymmdd)
    activity = activity.dropna(subset=["symbol", "date"])
    activity = activity[activity["date"].astype(str).str.len().eq(8)]
    return activity.drop_duplicates(["symbol", "date"]).sort_values(["symbol", "date"])


def build_tick_tasks(
    daily_activity: pd.DataFrame,
    chunks_dir: Path,
    *,
    overwrite: bool = False,
) -> list[TickTask]:
    """Build resumable symbol-date tick download tasks from daily activity."""
    tasks: list[TickTask] = []
    if daily_activity.empty:
        return tasks

    activity = daily_activity[["symbol", "date"]].copy()
    activity["date"] = activity["date"].map(_normalise_yyyymmdd)
    activity = activity.drop_duplicates(["symbol", "date"]).sort_values(["symbol", "date"])

    for row in activity.itertuples(index=False):
        symbol = str(row.symbol)
        day = str(row.date)
        output_path = chunks_dir / safe_symbol_name(symbol) / f"{day}.parquet"
        if output_path.exists() and not overwrite:
            continue
        tasks.append(TickTask(symbol=symbol, date=day, output_path=str(output_path)))
    return tasks


def build_tick_batch_tasks(
    daily_activity: pd.DataFrame,
    chunks_dir: Path,
    *,
    overwrite: bool = False,
    symbol_batch_size: int = 8,
) -> list[TickBatchTask]:
    """Build resumable date-level batch tasks from daily activity."""
    symbol_tasks = build_tick_tasks(daily_activity, chunks_dir, overwrite=overwrite)
    if not symbol_tasks:
        return []

    by_date: dict[str, list[str]] = {}
    for task in symbol_tasks:
        by_date.setdefault(task.date, []).append(task.symbol)

    batches: list[TickBatchTask] = []
    for day in sorted(by_date):
        symbols = sorted(set(by_date[day]))
        for offset in range(0, len(symbols), symbol_batch_size):
            batch = tuple(symbols[offset : offset + symbol_batch_size])
            batches.append(TickBatchTask(date=day, symbols=batch, chunks_dir=str(chunks_dir)))
    return batches


def filter_batch_tasks_excluding_pairs(
    tasks: list[TickBatchTask],
    excluded_pairs: set[tuple[str, str]],
) -> list[TickBatchTask]:
    """Remove symbol-date pairs from batch tasks while preserving resumable grouping."""
    if not excluded_pairs:
        return tasks

    filtered: list[TickBatchTask] = []
    for task in tasks:
        symbols = tuple(
            symbol
            for symbol in task.symbols
            if (symbol, _normalise_yyyymmdd(task.date)) not in excluded_pairs
        )
        if symbols:
            filtered.append(
                TickBatchTask(date=task.date, symbols=symbols, chunks_dir=task.chunks_dir)
            )
    return filtered


def _download_task(payload: tuple[TickTask, WorkerConfig]) -> dict[str, Any]:
    task, config = payload
    global _WORKER_TOKEN_READY

    output_path = Path(task.output_path)
    if output_path.exists() and not config.overwrite:
        return {
            "symbol": task.symbol,
            "date": task.date,
            "status": "skipped",
            "rows": None,
            "bytes": output_path.stat().st_size,
            "path": str(output_path),
            "error": "",
        }

    if not _WORKER_TOKEN_READY:
        _refresh_worker_token(config)

    last_error = ""
    attempt = 1
    token_refresh_retries = 1
    while attempt <= config.max_retries + token_refresh_retries:
        try:
            df = _future_tick_func()(symbol=task.symbol, date=task.date, fields=None)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            df.to_parquet(
                tmp_path,
                index=False,
                **parquet_kwargs(config.compression, config.compression_level),
            )
            tmp_path.replace(output_path)
            return {
                "symbol": task.symbol,
                "date": task.date,
                "status": "ok" if len(df) else "empty",
                "rows": int(len(df)),
                "bytes": output_path.stat().st_size,
                "path": str(output_path),
                "error": "",
            }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if is_token_expired_error(last_error) and token_refresh_retries > 0:
                _refresh_worker_token(config)
                token_refresh_retries -= 1
                continue
            if attempt < config.max_retries:
                time.sleep(config.retry_sleep * attempt)
        attempt += 1

    return {
        "symbol": task.symbol,
        "date": task.date,
        "status": "failed",
        "rows": None,
        "bytes": None,
        "path": str(output_path),
        "error": last_error,
    }


def _result_row(
    symbol: str,
    day: str,
    status: str,
    rows: int | None,
    output_path: Path,
    error: str = "",
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "date": day,
        "status": status,
        "rows": rows,
        "bytes": output_path.stat().st_size if output_path.exists() else None,
        "path": str(output_path),
        "error": error,
    }


def _download_batch_task(payload: tuple[TickBatchTask, WorkerConfig]) -> list[dict[str, Any]]:
    task, config = payload
    global _WORKER_TOKEN_READY

    chunks_dir = Path(task.chunks_dir)
    output_paths = {
        symbol: chunks_dir / safe_symbol_name(symbol) / f"{task.date}.parquet"
        for symbol in task.symbols
    }
    pending_symbols = [
        symbol
        for symbol, output_path in output_paths.items()
        if config.overwrite or not output_path.exists()
    ]
    skipped = [
        _result_row(symbol, task.date, "skipped", None, output_paths[symbol])
        for symbol in task.symbols
        if symbol not in pending_symbols
    ]
    if not pending_symbols:
        return skipped

    if not _WORKER_TOKEN_READY:
        _refresh_worker_token(config)

    last_error = ""
    attempt = 1
    token_refresh_retries = 1
    while attempt <= config.max_retries + token_refresh_retries:
        try:
            df = _future_tick_func()(symbol=pending_symbols, date=task.date, fields=None)
            rows: list[dict[str, Any]] = list(skipped)
            if df.empty:
                for symbol in pending_symbols:
                    output_path = output_paths[symbol]
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
                    df.to_parquet(
                        tmp_path,
                        index=False,
                        **parquet_kwargs(config.compression, config.compression_level),
                    )
                    tmp_path.replace(output_path)
                    rows.append(_result_row(symbol, task.date, "empty", 0, output_path))
                return rows

            grouped = {str(symbol): group for symbol, group in df.groupby("symbol", sort=False)}
            for symbol in pending_symbols:
                output_path = output_paths[symbol]
                group = grouped.get(symbol, df.iloc[0:0])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
                group.to_parquet(
                    tmp_path,
                    index=False,
                    **parquet_kwargs(config.compression, config.compression_level),
                )
                tmp_path.replace(output_path)
                rows.append(
                    _result_row(
                        symbol,
                        task.date,
                        "ok" if len(group) else "empty",
                        int(len(group)),
                        output_path,
                    )
                )
            return rows
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if is_token_expired_error(last_error) and token_refresh_retries > 0:
                _refresh_worker_token(config)
                token_refresh_retries -= 1
                continue
            if attempt < config.max_retries:
                time.sleep(config.retry_sleep * attempt)
        attempt += 1

    timed_out = "timed out" in last_error.lower()
    if len(pending_symbols) > 1 and (config.fallback_on_batch_timeout or not timed_out):
        fallback_rows = list(skipped)
        for symbol in pending_symbols:
            fallback_rows.append(
                _download_task(
                    (
                        TickTask(
                            symbol=symbol,
                            date=task.date,
                            output_path=str(output_paths[symbol]),
                        ),
                        config,
                    )
                )
            )
        return fallback_rows

    return [
        _result_row(symbol, task.date, "failed", None, output_paths[symbol], last_error)
        for symbol in pending_symbols
    ] + skipped


def _terminate_process_pool(pool: ProcessPoolExecutor) -> None:
    """Terminate stuck worker processes from a ProcessPoolExecutor."""
    processes = getattr(pool, "_processes", None)
    if not processes:
        return
    for process in list(processes.values()):
        if process.is_alive():
            process.terminate()
    deadline = time.time() + 10
    for process in list(processes.values()):
        remaining = max(0.0, deadline - time.time())
        process.join(timeout=remaining)
    for process in list(processes.values()):
        if process.is_alive():
            process.kill()


def run_task_batch(
    tasks: list[TickTask],
    config: WorkerConfig,
    *,
    workers: int,
    progress_every: int = 25,
    stall_timeout: int | None = None,
) -> pd.DataFrame:
    """Run tick download tasks in multiple processes."""
    if not tasks:
        return pd.DataFrame(columns=["symbol", "date", "status", "rows", "bytes", "path", "error"])

    rows: list[dict[str, Any]] = []
    started = time.time()
    completed = 0
    pool = ProcessPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(_download_task, (task, config)): task for task in tasks}
        pending = set(futures)
        while pending:
            done, pending = wait(
                pending,
                timeout=stall_timeout,
                return_when=FIRST_COMPLETED,
            )
            if not done:
                error = f"worker_stall_timeout after {stall_timeout}s"
                print(f"stalled task batch: {len(pending)} unfinished; {error}", flush=True)
                _terminate_process_pool(pool)
                for future in pending:
                    task = futures[future]
                    rows.append(
                        _result_row(
                            task.symbol,
                            task.date,
                            "failed",
                            None,
                            Path(task.output_path),
                            error,
                        )
                    )
                break
            for future in done:
                task = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = _result_row(
                        task.symbol,
                        task.date,
                        "failed",
                        None,
                        Path(task.output_path),
                        f"{type(exc).__name__}: {exc}",
                    )
                rows.append(result)
                completed += 1
                idx = completed
                if idx % progress_every == 0 or idx == len(tasks):
                    elapsed = time.time() - started
                    ok_count = sum(1 for row in rows if row["status"] in {"ok", "empty", "skipped"})
                    failed_count = sum(1 for row in rows if row["status"] == "failed")
                    print(
                        f"progress {idx}/{len(tasks)} ok={ok_count} failed={failed_count} "
                        f"elapsed={elapsed:.1f}s",
                        flush=True,
                    )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return pd.DataFrame(rows).sort_values(["symbol", "date"]).reset_index(drop=True)


def run_tick_batch_tasks(
    tasks: list[TickBatchTask],
    config: WorkerConfig,
    *,
    workers: int,
    progress_every: int = 25,
    result_sink: Path | None = None,
    result_round: int | None = None,
    stall_timeout: int | None = None,
) -> pd.DataFrame:
    """Run date-level tick batch tasks in multiple processes."""
    if not tasks:
        return pd.DataFrame(columns=["symbol", "date", "status", "rows", "bytes", "path", "error"])

    rows: list[dict[str, Any]] = []
    flushed = 0
    started = time.time()
    completed = 0
    pool = ProcessPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(_download_batch_task, (task, config)): task for task in tasks}
        pending = set(futures)
        while pending:
            done, pending = wait(
                pending,
                timeout=stall_timeout,
                return_when=FIRST_COMPLETED,
            )
            if not done:
                error = f"worker_stall_timeout after {stall_timeout}s"
                print(
                    f"stalled batch tasks: {len(pending)} unfinished; {error}",
                    flush=True,
                )
                _terminate_process_pool(pool)
                for future in pending:
                    task = futures[future]
                    for symbol in task.symbols:
                        rows.append(
                            _result_row(
                                symbol,
                                task.date,
                                "failed",
                                None,
                                task.output_path(symbol),
                                error,
                            )
                        )
                if result_sink is not None and len(rows) > flushed:
                    append_download_results(
                        result_sink,
                        rows[flushed:],
                        round_idx=result_round,
                    )
                break
            for future in done:
                task = futures[future]
                try:
                    batch_rows = future.result()
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    batch_rows = [
                        _result_row(
                            symbol,
                            task.date,
                            "failed",
                            None,
                            task.output_path(symbol),
                            error,
                        )
                        for symbol in task.symbols
                    ]
                rows.extend(batch_rows)
                completed += 1
                failed_rows = [row for row in batch_rows if row["status"] == "failed"]
                if failed_rows:
                    sample = failed_rows[0]
                    print(
                        f"failed batch date={sample['date']} symbols={len(failed_rows)} "
                        f"error={sample['error']}",
                        flush=True,
                    )
                idx = completed
                if idx % progress_every == 0 or idx == len(tasks):
                    if result_sink is not None:
                        append_download_results(
                            result_sink,
                            rows[flushed:],
                            round_idx=result_round,
                        )
                        flushed = len(rows)
                    elapsed = time.time() - started
                    ok_count = sum(1 for row in rows if row["status"] in {"ok", "empty", "skipped"})
                    failed_count = sum(1 for row in rows if row["status"] == "failed")
                    print(
                        f"progress batches {idx}/{len(tasks)} rows={len(rows)} "
                        f"ok={ok_count} failed={failed_count} elapsed={elapsed:.1f}s",
                        flush=True,
                    )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return pd.DataFrame(rows).sort_values(["symbol", "date"]).reset_index(drop=True)


def _legacy_run_task_batch(
    tasks: list[TickTask],
    config: WorkerConfig,
    *,
    workers: int,
    progress_every: int = 25,
) -> pd.DataFrame:
    """Run tick download tasks in multiple processes."""
    if not tasks:
        return pd.DataFrame(columns=["symbol", "date", "status", "rows", "bytes", "path", "error"])

    rows: list[dict[str, Any]] = []
    started = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_download_task, (task, config)) for task in tasks]
        for idx, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            rows.append(result)
            if idx % progress_every == 0 or idx == len(tasks):
                elapsed = time.time() - started
                ok_count = sum(1 for row in rows if row["status"] in {"ok", "empty", "skipped"})
                failed_count = sum(1 for row in rows if row["status"] == "failed")
                print(
                    f"progress {idx}/{len(tasks)} ok={ok_count} failed={failed_count} "
                    f"elapsed={elapsed:.1f}s",
                    flush=True,
                )

    return pd.DataFrame(rows).sort_values(["symbol", "date"]).reset_index(drop=True)


def _legacy_run_tick_batch_tasks(
    tasks: list[TickBatchTask],
    config: WorkerConfig,
    *,
    workers: int,
    progress_every: int = 25,
    result_sink: Path | None = None,
    result_round: int | None = None,
) -> pd.DataFrame:
    """Run date-level tick batch tasks in multiple processes."""
    if not tasks:
        return pd.DataFrame(columns=["symbol", "date", "status", "rows", "bytes", "path", "error"])

    rows: list[dict[str, Any]] = []
    flushed = 0
    started = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_download_batch_task, (task, config)) for task in tasks]
        for idx, future in enumerate(as_completed(futures), start=1):
            batch_rows = future.result()
            rows.extend(batch_rows)
            failed_rows = [row for row in batch_rows if row["status"] == "failed"]
            if failed_rows:
                sample = failed_rows[0]
                print(
                    f"failed batch date={sample['date']} symbols={len(failed_rows)} "
                    f"error={sample['error']}",
                    flush=True,
                )
            if idx % progress_every == 0 or idx == len(tasks):
                if result_sink is not None:
                    append_download_results(
                        result_sink,
                        rows[flushed:],
                        round_idx=result_round,
                    )
                    flushed = len(rows)
                elapsed = time.time() - started
                ok_count = sum(1 for row in rows if row["status"] in {"ok", "empty", "skipped"})
                failed_count = sum(1 for row in rows if row["status"] == "failed")
                print(
                    f"progress batches {idx}/{len(tasks)} rows={len(rows)} "
                    f"ok={ok_count} failed={failed_count} elapsed={elapsed:.1f}s",
                    flush=True,
                )

    return pd.DataFrame(rows).sort_values(["symbol", "date"]).reset_index(drop=True)


def combine_contract_chunks(
    symbols: list[str],
    chunks_dir: Path,
    contracts_dir: Path,
    *,
    compression: str,
    compression_level: int | None = None,
) -> pd.DataFrame:
    """Combine daily chunk Parquet files into one Parquet file per contract."""
    summary_rows: list[dict[str, Any]] = []
    contracts_dir.mkdir(parents=True, exist_ok=True)

    for symbol in sorted(symbols):
        symbol_dir = chunks_dir / safe_symbol_name(symbol)
        files = sorted(symbol_dir.glob("*.parquet"))
        if not files:
            summary_rows.append({"symbol": symbol, "chunks": 0, "rows": 0, "bytes": 0, "path": ""})
            continue

        frames = [pd.read_parquet(path) for path in files]
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        sort_cols = [col for col in ["date", "timestamp"] if col in df.columns]
        if sort_cols:
            df = df.sort_values(sort_cols).reset_index(drop=True)
        out_path = contracts_dir / f"{safe_symbol_name(symbol)}.parquet"
        df.to_parquet(
            out_path,
            index=False,
            **parquet_kwargs(compression, compression_level),
        )
        summary_rows.append(
            {
                "symbol": symbol,
                "chunks": len(files),
                "rows": int(len(df)),
                "bytes": out_path.stat().st_size,
                "path": str(out_path),
            }
        )

    return pd.DataFrame(summary_rows).sort_values("symbol").reset_index(drop=True)


def combine_monthly_chunks(
    daily_activity: pd.DataFrame,
    chunks_dir: Path,
    monthly_dir: Path,
    *,
    compression: str,
    compression_level: int | None = None,
    cleanup_chunks: bool = False,
) -> pd.DataFrame:
    """Combine daily contract chunks into one parquet file per underlying month."""
    monthly_dir.mkdir(parents=True, exist_ok=True)
    activity = _activity_with_month(daily_activity)
    summary_rows: list[dict[str, Any]] = []

    for month, group in activity.groupby("month", sort=True):
        frames: list[pd.DataFrame] = []
        chunk_paths: list[Path] = []
        chunk_pairs: set[tuple[str, str]] = set()
        missing = 0
        for row in group.itertuples(index=False):
            symbol = str(row.symbol)
            day = str(row.date)
            path = chunks_dir / safe_symbol_name(symbol) / f"{day}.parquet"
            if not path.exists():
                missing += 1
                continue
            frame = pd.read_parquet(path)
            frames.append(frame)
            chunk_paths.append(path)
            chunk_pairs.add((symbol, day))

        out_path = monthly_dir / f"{month}.parquet"
        if out_path.exists():
            try:
                existing = pd.read_parquet(out_path)
                for column in EXPECTED_TICK_COLUMNS:
                    if column not in existing.columns:
                        existing[column] = pd.NA
                existing = existing[EXPECTED_TICK_COLUMNS]
                if chunk_pairs and not existing.empty and "symbol" in existing.columns:
                    coverage_column = (
                        "trading_date" if "trading_date" in existing.columns else "date"
                    )
                    existing_dates = existing[coverage_column].map(_normalise_yyyymmdd)
                    existing_pairs = list(
                        zip(existing["symbol"].astype(str), existing_dates, strict=False)
                    )
                    existing = existing[[pair not in chunk_pairs for pair in existing_pairs]].copy()
                frames.insert(0, existing)
            except Exception:
                pass

        df = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=EXPECTED_TICK_COLUMNS)
        )
        for column in EXPECTED_TICK_COLUMNS:
            if column not in df.columns:
                df[column] = pd.NA
        df = df[EXPECTED_TICK_COLUMNS]
        sort_cols = [col for col in ["symbol", "timestamp"] if col in df.columns]
        if sort_cols and not df.empty:
            df = df.sort_values(sort_cols).reset_index(drop=True)

        tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
        df.to_parquet(
            tmp_path,
            index=False,
            **parquet_kwargs(compression, compression_level),
        )
        tmp_path.replace(out_path)

        if cleanup_chunks and missing == 0:
            for path in chunk_paths:
                path.unlink(missing_ok=True)

        summary_rows.append(
            {
                "month": month,
                "rows": int(len(df)),
                "symbol_days": int(len(group)),
                "missing_chunks": int(missing),
                "bytes": out_path.stat().st_size,
                "path": str(out_path),
            }
        )

    return pd.DataFrame(summary_rows).sort_values("month").reset_index(drop=True)


def summarize_monthly_outputs(daily_activity: pd.DataFrame, monthly_dir: Path) -> pd.DataFrame:
    """Summarize existing monthly parquet outputs without rewriting them."""
    activity = _activity_with_month(daily_activity)
    summary_rows: list[dict[str, Any]] = []
    try:
        import pyarrow.parquet as pq  # noqa: PLC0415
    except Exception:
        pq = None

    for month, group in activity.groupby("month", sort=True):
        path = monthly_dir / f"{month}.parquet"
        rows = 0
        bytes_size = path.stat().st_size if path.exists() else 0
        if path.exists():
            try:
                rows = (
                    int(pq.ParquetFile(path).metadata.num_rows)
                    if pq is not None
                    else int(len(pd.read_parquet(path)))
                )
            except Exception:
                rows = 0
        summary_rows.append(
            {
                "month": month,
                "rows": rows,
                "symbol_days": int(len(group)),
                "missing_chunks": 0,
                "bytes": bytes_size,
                "path": str(path) if path.exists() else "",
            }
        )
    return pd.DataFrame(summary_rows).sort_values("month").reset_index(drop=True)


def validate_monthly_output(
    daily_activity: pd.DataFrame,
    monthly_dir: Path,
    *,
    no_data_pairs: set[tuple[str, str]] | None = None,
    provider_timeout_pairs: set[tuple[str, str]] | None = None,
    allow_provider_timeout_gaps: bool = False,
) -> QualityReport:
    """Validate monthly parquet coverage and schema for one underlying."""
    activity = _activity_with_month(daily_activity)
    expected_pairs = {(str(row.symbol), str(row.date)) for row in activity.itertuples(index=False)}
    no_data_pairs = no_data_pairs or set()
    provider_timeout_pairs = provider_timeout_pairs or set()
    observed_pairs: set[tuple[str, str]] = set()
    invalid_files: list[dict[str, Any]] = []
    rows = 0
    monthly_files = 0

    for month, group in activity.groupby("month", sort=True):
        expected_month_pairs = {
            (str(row.symbol), str(row.date)) for row in group.itertuples(index=False)
        }
        path = monthly_dir / f"{month}.parquet"
        if not path.exists():
            invalid_files.append({"path": str(path), "reason": "missing_file"})
            continue
        monthly_files += 1
        try:
            df = pd.read_parquet(path)
        except Exception as exc:
            invalid_files.append(
                {"path": str(path), "reason": "unreadable", "error": f"{type(exc).__name__}: {exc}"}
            )
            continue

        rows += int(len(df))
        missing_columns = [column for column in EXPECTED_TICK_COLUMNS if column not in df.columns]
        if missing_columns:
            invalid_files.append(
                {
                    "path": str(path),
                    "reason": "missing_columns",
                    "columns": ",".join(missing_columns),
                }
            )
        if df.empty:
            timeout_covered = provider_timeout_pairs if allow_provider_timeout_gaps else set()
            unresolved = expected_month_pairs - no_data_pairs - timeout_covered
            if unresolved:
                invalid_files.append({"path": str(path), "reason": "empty_file"})
            continue

        for column in FIVE_LEVEL_COLUMNS:
            if column in df.columns:
                bad = df[column].map(lambda value: not is_five_level_sequence(value))
                if bool(bad.any()):
                    invalid_files.append({"path": str(path), "reason": f"bad_five_level_{column}"})
                    break

        if {"symbol", "timestamp"}.issubset(df.columns):
            for symbol, symbol_df in df.groupby("symbol", sort=False):
                timestamps = pd.to_numeric(symbol_df["timestamp"], errors="coerce")
                if not timestamps.is_monotonic_increasing:
                    invalid_files.append(
                        {
                            "path": str(path),
                            "reason": "timestamp_not_monotonic",
                            "symbol": str(symbol),
                        }
                    )
                    break

        coverage_date_column = "trading_date" if "trading_date" in df.columns else "date"
        if {"symbol", coverage_date_column}.issubset(df.columns):
            dates = df[coverage_date_column].map(_normalise_yyyymmdd)
            observed_pairs.update(zip(df["symbol"].astype(str), dates, strict=False))

    timeout_covered = provider_timeout_pairs if allow_provider_timeout_gaps else set()
    covered_pairs = observed_pairs | no_data_pairs | timeout_covered
    missing_pairs = sorted(expected_pairs - covered_pairs)
    status = "ok" if not invalid_files and not missing_pairs else "failed"
    return QualityReport(
        status=status,
        monthly_files=monthly_files,
        rows=rows,
        expected_symbol_days=len(expected_pairs),
        observed_symbol_days=len(observed_pairs),
        no_data_symbol_days=len(no_data_pairs & expected_pairs),
        provider_timeout_symbol_days=len(provider_timeout_pairs & expected_pairs),
        missing_symbol_days=missing_pairs,
        invalid_files=invalid_files,
    )


def build_month_retry_activity(daily_activity: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    """Return the active symbol-days that need another download attempt."""
    activity = daily_activity.copy()
    activity["date"] = activity["date"].map(_normalise_yyyymmdd)
    if report.missing_symbol_days:
        missing_pairs = set(report.missing_symbol_days)
        retry = activity[
            [
                (str(row.symbol), str(row.date)) in missing_pairs
                for row in activity.itertuples(index=False)
            ]
        ]
        return retry.reset_index(drop=True)
    if report.invalid_files:
        return activity.reset_index(drop=True)
    return activity.iloc[:0].reset_index(drop=True)


def write_quality_report(report: QualityReport, path: Path, *, underlying: str) -> None:
    """Write a markdown quality report for one underlying."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {underlying} Tick Data Quality Report",
        "",
        f"- status: `{report.status}`",
        f"- monthly_files: `{report.monthly_files}`",
        f"- rows: `{report.rows}`",
        f"- expected_symbol_days: `{report.expected_symbol_days}`",
        f"- observed_symbol_days: `{report.observed_symbol_days}`",
        f"- no_data_symbol_days: `{report.no_data_symbol_days}`",
        f"- provider_timeout_symbol_days: `{report.provider_timeout_symbol_days}`",
        f"- missing_symbol_days: `{len(report.missing_symbol_days)}`",
        f"- invalid_files: `{len(report.invalid_files)}`",
        "",
    ]
    if report.invalid_files:
        lines.extend(["## Invalid Files", ""])
        for item in report.invalid_files[:200]:
            lines.append(f"- `{item.get('path')}`: {item.get('reason')}")
        lines.append("")
    if report.missing_symbol_days:
        lines.extend(["## Missing Symbol Days", ""])
        for symbol, day in report.missing_symbol_days[:500]:
            lines.append(f"- `{symbol}` `{day}`")
        if len(report.missing_symbol_days) > 500:
            lines.append(f"- ... {len(report.missing_symbol_days) - 500} more")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def cleanup_chunks(daily_activity: pd.DataFrame, chunks_dir: Path) -> int:
    """Delete daily chunk files for completed activity rows."""
    removed = 0
    for row in _activity_with_month(daily_activity).itertuples(index=False):
        path = chunks_dir / safe_symbol_name(str(row.symbol)) / f"{row.date}.parquet"
        if path.exists():
            path.unlink()
            removed += 1
    for path in sorted(chunks_dir.glob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    return removed


def write_global_progress(rows: list[UnderlyingRunResult], path: Path) -> None:
    """Write global underlying progress as CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row.__dict__ for row in rows]).to_csv(path, index=False)


def write_global_report(
    rows: list[UnderlyingRunResult],
    path: Path,
    *,
    free_gb: float,
    min_free_gb: float,
    status: str,
) -> None:
    """Write global markdown report for all-underlying orchestration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    completed = sum(1 for row in rows if row.status == "ok")
    failed = sum(1 for row in rows if row.status == "failed")
    skipped = sum(1 for row in rows if row.status == "skipped")
    lines = [
        "# PandaAI Futures Tick Global Download Report",
        "",
        f"- status: `{status}`",
        f"- completed: `{completed}`",
        f"- failed: `{failed}`",
        f"- skipped: `{skipped}`",
        f"- free_disk_gib: `{free_gb:.2f}`",
        f"- min_free_disk_gb: `{min_free_gb}`",
        "",
        "## Underlyings",
        "",
    ]
    for row in rows:
        lines.append(
            f"- `{row.underlying}` status=`{row.status}` workers=`{row.workers}` "
            f"contracts=`{row.contracts}` active_symbol_days=`{row.active_symbol_days}` "
            f"failed_tasks=`{row.failed_tasks}`"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _read_completed_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return manifest if manifest.get("status") == "ok" else None


def _resolve_output_dir(args: argparse.Namespace, underlying: str) -> Path:
    if getattr(args, "output_root", None):
        return (ROOT / args.output_root / underlying).resolve()
    return (ROOT / args.output_dir).resolve()


def _latest_failed(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame(columns=["symbol", "date", "status"])
    results = mark_existing_path_failures_recovered(results)
    latest = results.groupby(["symbol", "date"], as_index=False).tail(1)
    return latest[latest["status"].eq("failed")]


def mark_existing_path_failures_recovered(results: pd.DataFrame) -> pd.DataFrame:
    """Treat failed rows with an existing chunk file as recovered by persisted data."""
    if results.empty or not {"status", "path"}.issubset(results.columns):
        return results
    recovered = results["status"].eq("failed") & results["path"].astype(str).map(
        lambda path: Path(path).exists()
    )
    if not bool(recovered.any()):
        return results
    results = results.copy()
    results.loc[recovered, "status"] = "skipped"
    return results


def numeric_sum(frame: pd.DataFrame, column: str) -> int:
    """Sum a possibly string/object numeric column from legacy CSV data."""
    if frame.empty or column not in frame.columns:
        return 0
    return int(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def download_activity_batches(
    activity: pd.DataFrame,
    chunks_dir: Path,
    config: WorkerConfig,
    args: argparse.Namespace,
    *,
    workers: int,
    results_path: Path,
    overwrite_existing_chunks: bool = False,
) -> tuple[list[TickBatchTask], pd.DataFrame, pd.DataFrame, set[tuple[str, str]]]:
    """Download one activity subset and return task/result/failure state."""
    pairs = activity_pairs(activity)
    task_overwrite = args.overwrite or overwrite_existing_chunks
    worker_config = replace(config, overwrite=True) if overwrite_existing_chunks else config
    tasks = build_tick_batch_tasks(
        activity,
        chunks_dir,
        overwrite=task_overwrite,
        symbol_batch_size=args.symbol_batch_size,
    )
    if args.limit_tasks:
        tasks = tasks[: args.limit_tasks]

    if args.overwrite and results_path.exists():
        results_path.unlink()

    all_results: list[pd.DataFrame] = []
    existing_results = read_download_results(results_path)
    if not existing_results.empty and not args.overwrite:
        all_results.append(existing_results)

    existing_subset = filter_results_to_pairs(existing_results, pairs)
    initial_provider_timeouts = (
        provider_timeout_symbol_days(
            existing_subset,
            threshold=args.provider_timeout_threshold,
        )
        if args.allow_provider_timeout_gaps
        else set()
    )
    pending = filter_batch_tasks_excluding_pairs(tasks, initial_provider_timeouts)
    if initial_provider_timeouts:
        print(
            f"provider-timeout skipped={len(initial_provider_timeouts)}",
            flush=True,
        )

    for round_idx in range(args.retry_failed_rounds + 1):
        if not pending:
            break
        if round_idx:
            print(f"retry round {round_idx}: tasks={len(pending)}", flush=True)
        result = run_tick_batch_tasks(
            pending,
            worker_config,
            workers=workers,
            progress_every=max(1, args.progress_every),
            result_sink=results_path,
            result_round=round_idx,
            stall_timeout=getattr(args, "stall_timeout", 300),
        )
        all_results.append(result)
        cumulative_results = filter_results_to_pairs(
            pd.concat(all_results, ignore_index=True),
            pairs,
        )
        exhausted_timeouts = (
            provider_timeout_symbol_days(
                cumulative_results,
                threshold=args.provider_timeout_threshold,
            )
            if args.allow_provider_timeout_gaps
            else set()
        )
        failed = result[result["status"].eq("failed")].copy()
        if exhausted_timeouts and not failed.empty:
            failed_pairs = list(
                zip(
                    failed["symbol"].astype(str),
                    failed["date"].map(_normalise_yyyymmdd),
                    strict=False,
                )
            )
            failed = failed[[pair not in exhausted_timeouts for pair in failed_pairs]]
        pending = build_tick_batch_tasks(
            failed[["symbol", "date"]].copy(),
            chunks_dir,
            overwrite=True,
            symbol_batch_size=args.symbol_batch_size,
        )
        pending = filter_batch_tasks_excluding_pairs(pending, exhausted_timeouts)

    results = pd.concat(all_results, ignore_index=True) if all_results else empty_results_frame()
    if "path" in results.columns and "status" in results.columns:
        recovered = results["status"].eq("failed") & results["path"].astype(str).map(
            lambda path: Path(path).exists()
        )
        results.loc[recovered, "status"] = "skipped"
    results.to_csv(results_path, index=False)

    subset_results = filter_results_to_pairs(results, pairs)
    provider_timeout_pairs = provider_timeout_symbol_days(
        subset_results,
        threshold=args.provider_timeout_threshold,
    )
    final_failed = _latest_failed(subset_results)
    if args.allow_provider_timeout_gaps and provider_timeout_pairs and not final_failed.empty:
        final_pairs = list(
            zip(
                final_failed["symbol"].astype(str),
                final_failed["date"].map(_normalise_yyyymmdd),
                strict=False,
            )
        )
        final_failed = final_failed[[pair not in provider_timeout_pairs for pair in final_pairs]]

    return tasks, results, final_failed, provider_timeout_pairs


def run_monthly_pipeline(
    args: argparse.Namespace,
    *,
    underlying: str,
    activity: pd.DataFrame,
    contracts: pd.DataFrame,
    symbols: list[str],
    chunks_dir: Path,
    monthly_dir: Path,
    output_dir: Path,
    manifest_path: Path,
    config: WorkerConfig,
    workers: int,
    tasks_requested: int,
    effective_start_date: str,
) -> UnderlyingRunResult:
    """Run one underlying month by month, finalizing monthly parquet incrementally."""
    results_path = output_dir / "download_results.csv"
    quality_report_path = output_dir / "quality_report.md"
    no_data_path = output_dir / "no_data_symbol_days.csv"
    provider_timeout_path = output_dir / "provider_timeout_symbol_days.csv"
    no_data_pairs = read_pair_csv(no_data_path)
    provider_timeout_pairs = read_pair_csv(provider_timeout_path)
    month_failures: list[dict[str, Any]] = []

    activity_months = _activity_with_month(activity)
    for month, month_activity in activity_months.groupby("month", sort=True):
        existing_report = validate_monthly_output(
            month_activity,
            monthly_dir,
            no_data_pairs=no_data_pairs,
            provider_timeout_pairs=provider_timeout_pairs,
            allow_provider_timeout_gaps=args.allow_provider_timeout_gaps,
        )
        month_path = monthly_dir / f"{month}.parquet"
        if month_path.exists() and existing_report.status == "ok" and not args.overwrite:
            print(f"underlying={underlying} month={month} skip completed", flush=True)
            continue

        download_activity = month_activity
        if month_path.exists() and not args.overwrite:
            retry_activity = build_month_retry_activity(month_activity, existing_report)
            if not retry_activity.empty:
                download_activity = retry_activity

        print(
            f"underlying={underlying} month={month} active_symbol_days={len(month_activity)} "
            f"download_symbol_days={len(download_activity)}",
            flush=True,
        )
        _month_tasks, _results, final_failed, month_provider_timeouts = download_activity_batches(
            download_activity,
            chunks_dir,
            config,
            args,
            workers=workers,
            results_path=results_path,
        )
        provider_timeout_pairs |= month_provider_timeouts
        no_data_pairs |= collect_no_data_symbol_days(month_activity, chunks_dir)
        write_pair_csv(no_data_path, no_data_pairs)
        write_pair_csv(provider_timeout_path, provider_timeout_pairs)

        month_summary = combine_monthly_chunks(
            month_activity,
            chunks_dir,
            monthly_dir,
            compression=args.compression,
            compression_level=args.compression_level,
            cleanup_chunks=False,
        )
        month_summary.to_csv(output_dir / f"combined_monthly_{month}.csv", index=False)
        month_report = validate_monthly_output(
            month_activity,
            monthly_dir,
            no_data_pairs=no_data_pairs,
            provider_timeout_pairs=provider_timeout_pairs,
            allow_provider_timeout_gaps=args.allow_provider_timeout_gaps,
        )
        for quality_round in range(1, args.retry_failed_rounds + 1):
            retry_activity = build_month_retry_activity(month_activity, month_report)
            if retry_activity.empty:
                break
            print(
                f"underlying={underlying} month={month} quality retry "
                f"{quality_round}: active_symbol_days={len(retry_activity)}",
                flush=True,
            )
            _retry_tasks, _retry_results, final_failed, retry_provider_timeouts = (
                download_activity_batches(
                    retry_activity,
                    chunks_dir,
                    config,
                    args,
                    workers=workers,
                    results_path=results_path,
                    overwrite_existing_chunks=True,
                )
            )
            provider_timeout_pairs |= retry_provider_timeouts
            no_data_pairs |= collect_no_data_symbol_days(month_activity, chunks_dir)
            write_pair_csv(no_data_path, no_data_pairs)
            write_pair_csv(provider_timeout_path, provider_timeout_pairs)
            month_summary = combine_monthly_chunks(
                month_activity,
                chunks_dir,
                monthly_dir,
                compression=args.compression,
                compression_level=args.compression_level,
                cleanup_chunks=False,
            )
            month_summary.to_csv(output_dir / f"combined_monthly_{month}.csv", index=False)
            month_report = validate_monthly_output(
                month_activity,
                monthly_dir,
                no_data_pairs=no_data_pairs,
                provider_timeout_pairs=provider_timeout_pairs,
                allow_provider_timeout_gaps=args.allow_provider_timeout_gaps,
            )
            if month_report.status == "ok" and final_failed.empty:
                break
        print(
            f"underlying={underlying} month={month} quality={month_report.status} "
            f"rows={month_report.rows} missing={len(month_report.missing_symbol_days)} "
            f"failed_tasks={len(final_failed)}",
            flush=True,
        )
        if month_report.status == "ok" and final_failed.empty and not args.limit_tasks:
            cleanup_chunks(month_activity, chunks_dir)
        else:
            month_failures.append(
                {
                    "month": month,
                    "quality_status": month_report.status,
                    "failed_tasks": int(len(final_failed)),
                    "missing_symbol_days": int(len(month_report.missing_symbol_days)),
                    "invalid_files": int(len(month_report.invalid_files)),
                }
            )

    combine_summary = summarize_monthly_outputs(activity, monthly_dir)
    combine_summary.to_csv(output_dir / "combined_monthly.csv", index=False)
    results = read_download_results(results_path)
    subset_results = filter_results_to_pairs(results, activity_pairs(activity))
    provider_timeout_pairs |= provider_timeout_symbol_days(
        subset_results,
        threshold=args.provider_timeout_threshold,
    )
    write_pair_csv(provider_timeout_path, provider_timeout_pairs)
    write_pair_csv(no_data_path, no_data_pairs)
    report = validate_monthly_output(
        activity,
        monthly_dir,
        no_data_pairs=no_data_pairs,
        provider_timeout_pairs=provider_timeout_pairs,
        allow_provider_timeout_gaps=args.allow_provider_timeout_gaps,
    )
    write_quality_report(report, quality_report_path, underlying=underlying)

    final_failed = _latest_failed(subset_results)
    if args.allow_provider_timeout_gaps and provider_timeout_pairs and not final_failed.empty:
        final_pairs = list(
            zip(
                final_failed["symbol"].astype(str),
                final_failed["date"].map(_normalise_yyyymmdd),
                strict=False,
            )
        )
        final_failed = final_failed[[pair not in provider_timeout_pairs for pair in final_pairs]]

    quality_status = report.status
    if quality_status == "ok" and not month_failures:
        final_failed = final_failed.iloc[0:0]
    failed_tasks = int(len(final_failed))
    rows_downloaded = int(report.rows)
    status = "ok" if quality_status == "ok" and not month_failures else "failed"
    manifest = {
        "status": status,
        "underlying": underlying,
        "start_date": args.start_date,
        "effective_start_date": effective_start_date,
        "end_date": args.end_date,
        "contracts": len(symbols),
        "active_symbol_days": int(len(activity)),
        "tasks_requested": int(tasks_requested),
        "failed_tasks": failed_tasks,
        "rows_downloaded": rows_downloaded,
        "chunk_bytes": numeric_sum(subset_results, "bytes"),
        "combined_bytes": numeric_sum(combine_summary, "bytes"),
        "quality_status": quality_status,
        "quality_report": str(quality_report_path),
        "no_data_symbol_days": str(no_data_path),
        "provider_timeout_symbol_days": str(provider_timeout_path),
        "month_failures": month_failures,
        "output_dir": str(output_dir),
        "results_path": str(results_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)

    return UnderlyingRunResult(
        underlying=underlying,
        status=status,
        workers=workers,
        contracts=len(contracts),
        active_symbol_days=int(len(activity)),
        failed_tasks=failed_tasks,
        rows_downloaded=rows_downloaded,
        output_dir=str(output_dir),
    )


def run_underlying(
    args: argparse.Namespace,
    *,
    username: str,
    password: str,
    underlying: str,
    workers: int,
    all_contracts: pd.DataFrame | None = None,
) -> UnderlyingRunResult:
    """Run one underlying through download, monthly combine, and validation."""
    output_dir = _resolve_output_dir(args, underlying)
    chunks_dir = output_dir / "chunks"
    monthly_dir = output_dir / "monthly"
    contracts_dir = output_dir / "contracts"
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "manifest.json"
    completed = _read_completed_manifest(manifest_path)
    if completed and not args.overwrite:
        print(f"skip completed underlying={underlying} output={output_dir}", flush=True)
        return UnderlyingRunResult(
            underlying=underlying,
            status="skipped",
            workers=workers,
            contracts=int(completed.get("contracts", 0)),
            active_symbol_days=int(completed.get("active_symbol_days", 0)),
            failed_tasks=0,
            rows_downloaded=int(completed.get("rows_downloaded", 0)),
            output_dir=str(output_dir),
        )

    contracts_path = output_dir / "contracts_meta.parquet"
    activity_path = output_dir / "daily_activity.parquet"

    if contracts_path.exists() and activity_path.exists() and not args.refresh_discovery:
        print(
            f"reuse discovery underlying={underlying} contracts={contracts_path} "
            f"activity={activity_path}",
            flush=True,
        )
        contracts = pd.read_parquet(contracts_path)
        activity = pd.read_parquet(activity_path)
    else:
        print(
            f"discover contracts underlying={underlying} range={args.start_date}-{args.end_date}",
            flush=True,
        )
        if all_contracts is not None:
            contracts = all_contracts[
                all_contracts["underlying_symbol"].astype(str).str.upper().eq(underlying.upper())
            ].copy()
            if not args.include_dominant:
                contracts = contracts[
                    ~contracts["symbol"].astype(str).str.contains("_DOMINANT", na=False)
                ]
            contracts = contracts.sort_values("symbol").reset_index(drop=True)
        else:
            contracts = discover_future_contracts(
                underlying,
                include_dominant=args.include_dominant,
            )
        effective_start = effective_underlying_start_date(contracts, args.start_date)
        contracts.to_parquet(
            contracts_path,
            index=False,
            **parquet_kwargs(args.compression, args.compression_level),
        )
        symbols_for_activity = contracts["symbol"].astype(str).tolist()
        activity = (
            fetch_daily_activity(symbols_for_activity, effective_start, args.end_date)
            if effective_start <= args.end_date
            else pd.DataFrame(columns=["symbol", "date"])
        )
        activity.to_parquet(
            activity_path,
            index=False,
            **parquet_kwargs(args.compression, args.compression_level),
        )

    if all_contracts is not None and "symbol" in contracts.columns:
        available_columns = [
            column
            for column in ["listed_date", "de_listed_date"]
            if column not in contracts.columns and column in all_contracts.columns
        ]
        if available_columns:
            contracts = contracts.merge(
                all_contracts[["symbol", *available_columns]].drop_duplicates("symbol"),
                on="symbol",
                how="left",
            )
            contracts.to_parquet(
                contracts_path,
                index=False,
                **parquet_kwargs(args.compression, args.compression_level),
            )

    effective_start = effective_underlying_start_date(contracts, args.start_date)
    if not activity.empty:
        activity = activity.copy()
        activity["date"] = activity["date"].map(_normalise_yyyymmdd)
        activity = activity[activity["date"].ge(effective_start)].copy()
    if effective_start != _normalise_yyyymmdd(args.start_date):
        print(
            f"underlying={underlying} listed-start={effective_start} "
            f"requested-start={args.start_date}",
            flush=True,
        )

    symbols = contracts["symbol"].astype(str).tolist()
    print(
        f"underlying={underlying} contracts={len(symbols)} "
        f"active_symbol_days={len(activity)} workers={workers}",
        flush=True,
    )

    tasks = build_tick_batch_tasks(
        activity,
        chunks_dir,
        overwrite=args.overwrite,
        symbol_batch_size=args.symbol_batch_size,
    )
    if args.limit_tasks:
        tasks = tasks[: args.limit_tasks]
    print(
        f"underlying={underlying} download batch-tasks={len(tasks)} "
        f"symbol_batch_size={args.symbol_batch_size}",
        flush=True,
    )

    config = WorkerConfig(
        username=username,
        password=password,
        max_retries=args.max_retries,
        retry_sleep=args.retry_sleep,
        compression=args.compression,
        compression_level=args.compression_level,
        overwrite=args.overwrite,
        http_timeout=args.http_timeout,
        fallback_on_batch_timeout=not args.no_fallback_on_batch_timeout,
    )

    if args.monthly_output and not args.no_month_by_month:
        return run_monthly_pipeline(
            args,
            underlying=underlying,
            activity=activity,
            contracts=contracts,
            symbols=symbols,
            chunks_dir=chunks_dir,
            monthly_dir=monthly_dir,
            output_dir=output_dir,
            manifest_path=manifest_path,
            config=config,
            workers=workers,
            tasks_requested=len(tasks),
            effective_start_date=effective_start,
        )

    results_path = output_dir / "download_results.csv"
    if args.overwrite and results_path.exists():
        results_path.unlink()
    all_results: list[pd.DataFrame] = []
    if results_path.exists() and not args.overwrite:
        all_results.append(pd.read_csv(results_path))
    initial_provider_timeouts = (
        provider_timeout_symbol_days(all_results[0], threshold=args.provider_timeout_threshold)
        if all_results and args.allow_provider_timeout_gaps
        else set()
    )
    pending = filter_batch_tasks_excluding_pairs(tasks, initial_provider_timeouts)
    if initial_provider_timeouts:
        print(
            f"underlying={underlying} provider-timeout skipped={len(initial_provider_timeouts)}",
            flush=True,
        )
    for round_idx in range(args.retry_failed_rounds + 1):
        if not pending:
            break
        if round_idx:
            print(f"underlying={underlying} retry round {round_idx}: tasks={len(pending)}")
        result = run_tick_batch_tasks(
            pending,
            config,
            workers=workers,
            progress_every=max(1, args.progress_every),
            result_sink=results_path,
            result_round=round_idx,
            stall_timeout=getattr(args, "stall_timeout", 300),
        )
        all_results.append(result)
        cumulative_results = pd.concat(all_results, ignore_index=True)
        exhausted_timeouts = (
            provider_timeout_symbol_days(
                cumulative_results,
                threshold=args.provider_timeout_threshold,
            )
            if args.allow_provider_timeout_gaps
            else set()
        )
        failed = result[result["status"].eq("failed")].copy()
        if exhausted_timeouts and not failed.empty:
            failed_pairs = list(
                zip(
                    failed["symbol"].astype(str),
                    failed["date"].map(_normalise_yyyymmdd),
                    strict=False,
                )
            )
            retry_mask = [pair not in exhausted_timeouts for pair in failed_pairs]
            failed = failed[retry_mask]
        pending = build_tick_batch_tasks(
            failed[["symbol", "date"]].copy(),
            chunks_dir,
            overwrite=True,
            symbol_batch_size=args.symbol_batch_size,
        )
        pending = filter_batch_tasks_excluding_pairs(pending, exhausted_timeouts)

    results = (
        pd.concat(all_results, ignore_index=True)
        if all_results
        else pd.DataFrame(columns=["symbol", "date", "status", "rows", "bytes", "path", "error"])
    )
    if "path" in results.columns and "status" in results.columns:
        recovered = results["status"].eq("failed") & results["path"].astype(str).map(
            lambda path: Path(path).exists()
        )
        results.loc[recovered, "status"] = "skipped"
    results.to_csv(results_path, index=False)
    final_failed = _latest_failed(results)
    provider_timeout_pairs = provider_timeout_symbol_days(
        results,
        threshold=args.provider_timeout_threshold,
    )
    if args.allow_provider_timeout_gaps and provider_timeout_pairs and not final_failed.empty:
        final_pairs = list(
            zip(
                final_failed["symbol"].astype(str),
                final_failed["date"].map(_normalise_yyyymmdd),
                strict=False,
            )
        )
        final_failed = final_failed[[pair not in provider_timeout_pairs for pair in final_pairs]]

    combine_summary = pd.DataFrame()
    quality_status = "not_run"
    quality_report_path = output_dir / "quality_report.md"
    no_data_path = output_dir / "no_data_symbol_days.csv"
    provider_timeout_path = output_dir / "provider_timeout_symbol_days.csv"
    if args.monthly_output:
        combine_summary = combine_monthly_chunks(
            activity,
            chunks_dir,
            monthly_dir,
            compression=args.compression,
            compression_level=args.compression_level,
            cleanup_chunks=False,
        )
        combine_summary.to_csv(output_dir / "combined_monthly.csv", index=False)
        no_data_pairs = collect_no_data_symbol_days(activity, chunks_dir)
        pd.DataFrame(
            [{"symbol": symbol, "date": day} for symbol, day in sorted(no_data_pairs)],
            columns=["symbol", "date"],
        ).to_csv(no_data_path, index=False)
        pd.DataFrame(
            [{"symbol": symbol, "date": day} for symbol, day in sorted(provider_timeout_pairs)],
            columns=["symbol", "date"],
        ).to_csv(provider_timeout_path, index=False)
        report = validate_monthly_output(
            activity,
            monthly_dir,
            no_data_pairs=no_data_pairs,
            provider_timeout_pairs=provider_timeout_pairs,
            allow_provider_timeout_gaps=args.allow_provider_timeout_gaps,
        )
        write_quality_report(report, quality_report_path, underlying=underlying)
        quality_status = report.status
        if report.status == "ok" and final_failed.empty and not args.limit_tasks:
            cleanup_chunks(activity, chunks_dir)
    elif not args.no_combine:
        combine_summary = combine_contract_chunks(
            symbols,
            chunks_dir,
            contracts_dir,
            compression=args.compression,
            compression_level=args.compression_level,
        )
        combine_summary.to_csv(output_dir / "combined_contracts.csv", index=False)

    failed_tasks = int(len(final_failed))
    rows_downloaded = numeric_sum(results, "rows")
    status = "ok" if failed_tasks == 0 and quality_status in {"ok", "not_run"} else "failed"
    manifest = {
        "status": status,
        "underlying": underlying,
        "start_date": args.start_date,
        "effective_start_date": effective_start,
        "end_date": args.end_date,
        "contracts": len(symbols),
        "active_symbol_days": int(len(activity)),
        "tasks_requested": int(len(tasks)),
        "failed_tasks": failed_tasks,
        "rows_downloaded": rows_downloaded,
        "chunk_bytes": numeric_sum(results, "bytes"),
        "combined_bytes": numeric_sum(combine_summary, "bytes"),
        "quality_status": quality_status,
        "quality_report": str(quality_report_path) if args.monthly_output else "",
        "no_data_symbol_days": str(no_data_path) if args.monthly_output else "",
        "provider_timeout_symbol_days": str(provider_timeout_path) if args.monthly_output else "",
        "output_dir": str(output_dir),
        "results_path": str(results_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)

    return UnderlyingRunResult(
        underlying=underlying,
        status=status,
        workers=workers,
        contracts=len(symbols),
        active_symbol_days=int(len(activity)),
        failed_tasks=failed_tasks,
        rows_downloaded=rows_downloaded,
        output_dir=str(output_dir),
    )


def run_underlying_with_adaptive_workers(
    args: argparse.Namespace,
    *,
    username: str,
    password: str,
    underlying: str,
    all_contracts: pd.DataFrame | None = None,
) -> UnderlyingRunResult:
    """Run one underlying and lower worker count if the final result fails."""
    worker_plan = [args.workers]
    for candidate in [4, 2]:
        if candidate < args.workers and candidate not in worker_plan:
            worker_plan.append(candidate)

    last_result: UnderlyingRunResult | None = None
    for workers in worker_plan:
        result = run_underlying(
            args,
            username=username,
            password=password,
            underlying=underlying,
            workers=workers,
            all_contracts=all_contracts,
        )
        last_result = result
        if result.status in {"ok", "skipped"}:
            return result
        print(
            f"underlying={underlying} status={result.status}; retry with lower workers if available",
            flush=True,
        )
    assert last_result is not None
    return last_result


def run_all_underlyings(args: argparse.Namespace, *, username: str, password: str) -> int:
    """Run all futures underlyings serially."""
    output_root = (ROOT / args.output_root).resolve()
    global_dir = output_root / "_global"
    progress_path = global_dir / "progress.csv"
    report_path = global_dir / "all_underlyings_report.md"
    global_dir.mkdir(parents=True, exist_ok=True)

    contracts = discover_all_future_contracts(include_dominant=args.include_dominant)
    underlyings = sorted_underlyings(contracts)
    if args.limit_underlyings:
        underlyings = underlyings[: args.limit_underlyings]
    underlyings = prioritize_underlyings(underlyings, args.priority_underlyings)

    rows: list[UnderlyingRunResult] = []
    if progress_path.exists() and not args.overwrite:
        previous = pd.read_csv(progress_path)
        for row in previous.itertuples(index=False):
            if str(row.status) in {"ok", "skipped"}:
                rows.append(
                    UnderlyingRunResult(
                        underlying=str(row.underlying),
                        status=str(row.status),
                        workers=int(row.workers),
                        contracts=int(row.contracts),
                        active_symbol_days=int(row.active_symbol_days),
                        failed_tasks=int(row.failed_tasks),
                        rows_downloaded=int(row.rows_downloaded),
                        output_dir=str(row.output_dir),
                        error=str(getattr(row, "error", "")),
                    )
                )
        completed = {row.underlying for row in rows if row.status in {"ok", "skipped"}}
        underlyings = [underlying for underlying in underlyings if underlying not in completed]

    status = "running"
    for underlying in underlyings:
        result = run_underlying_with_adaptive_workers(
            args,
            username=username,
            password=password,
            underlying=underlying,
            all_contracts=contracts,
        )
        rows = [row for row in rows if row.underlying != underlying] + [result]
        rows = sorted(rows, key=lambda row: row.underlying)
        write_global_progress(rows, progress_path)

        current_free_gb = free_disk_gb(output_root)
        if free_disk_below_threshold(
            free_bytes=int(current_free_gb * 1024**3),
            min_free_gb=args.min_free_disk_gb,
        ):
            status = "paused_low_disk_space"
            write_global_report(
                rows,
                report_path,
                free_gb=current_free_gb,
                min_free_gb=args.min_free_disk_gb,
                status=status,
            )
            print(
                f"pause: free disk {current_free_gb:.2f} GiB < {args.min_free_disk_gb} GB",
                flush=True,
            )
            return 0

    failed = [row for row in rows if row.status == "failed"]
    status = "failed" if failed else "ok"
    write_global_report(
        rows,
        report_path,
        free_gb=free_disk_gb(output_root),
        min_free_gb=args.min_free_disk_gb,
        status=status,
    )
    return 1 if failed else 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--underlying", default="SA", help="Futures underlying symbol.")
    parser.add_argument("--all-underlyings", action="store_true")
    parser.add_argument("--start-date", default=default_start_date(), help="YYYYMMDD.")
    parser.add_argument("--end-date", default=date.today().strftime("%Y%m%d"), help="YYYYMMDD.")
    parser.add_argument(
        "--output-dir",
        default="data/export/panda_future_ticks/SA",
        help="Directory for manifests, chunks, and combined contract files.",
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help="Root directory for underlying subdirectories.",
    )
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--symbol-batch-size", type=int, default=8)
    parser.add_argument("--progress-every", type=int, default=1)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=2.0)
    parser.add_argument("--retry-failed-rounds", type=int, default=2)
    parser.add_argument("--http-timeout", type=int, default=60)
    parser.add_argument(
        "--stall-timeout",
        type=int,
        default=300,
        help="Seconds without completed worker futures before terminating the pool.",
    )
    parser.add_argument("--provider-timeout-threshold", type=int, default=3)
    parser.add_argument(
        "--allow-provider-timeout-gaps",
        action="store_true",
        help="Treat repeatedly timed-out symbol-days as acceptable coverage gaps.",
    )
    parser.add_argument("--no-fallback-on-batch-timeout", action="store_true")
    parser.add_argument("--compression", default="zstd")
    parser.add_argument("--compression-level", type=int, default=9)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--include-dominant", action="store_true")
    parser.add_argument("--refresh-discovery", action="store_true")
    parser.add_argument("--no-combine", action="store_true")
    parser.add_argument("--monthly-output", action="store_true")
    parser.add_argument("--no-month-by-month", action="store_true")
    parser.add_argument("--min-free-disk-gb", type=float, default=100.0)
    parser.add_argument("--limit-tasks", type=int, default=0, help="Debug limit.")
    parser.add_argument("--limit-underlyings", type=int, default=0, help="Debug limit.")
    parser.add_argument(
        "--priority-underlyings",
        default="",
        help="Comma-separated underlyings to process before the remaining sorted list.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    load_dotenv()

    username = os.environ.get("PANDA_DATA_USERNAME", "")
    password = os.environ.get("PANDA_DATA_PASSWORD", "")
    if not username or not password:
        print("PANDA_DATA_USERNAME / PANDA_DATA_PASSWORD not set", file=sys.stderr)
        return 2

    _init_panda_data(username, password, http_timeout=args.http_timeout)
    if args.all_underlyings:
        if not args.output_root:
            args.output_root = "data/export/panda_future_ticks"
        return run_all_underlyings(args, username=username, password=password)

    result = run_underlying(
        args,
        username=username,
        password=password,
        underlying=args.underlying,
        workers=args.workers,
    )
    return 0 if result.status in {"ok", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
