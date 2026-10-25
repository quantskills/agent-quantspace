"""File transport: explicit outputs, safe publication, and standard table layouts."""

from __future__ import annotations

import dataclasses
import functools
import importlib
import json
import math
import os
import sys
import tempfile
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from .models import Artifact, CLIError

# DataManager namespaces below the data root; only store commands with --write change them.
MANAGED = ("market", "adj_factor", "factors", "correlation", "backtest", "models")


@functools.cache
def _store_class():
    from skills.store.data_manager import DataManager

    class CommandStore(DataManager):
        """DataManager for command adapters.

        ``DataManager()`` creates its top-level store folders when constructed. Read-only
        commands must not create a store, and the save methods behind --write create their
        own target folders, so command adapters skip that step.
        """

        def _ensure_dirs(self):
            return None

    return CommandStore


def data_manager(data_root=None):
    root = str(Path(data_root).expanduser()) if data_root else None
    return _store_class()(data_root=root)


def read_json(path):
    if str(path) == "-":
        return json.load(sys.stdin)
    with Path(path).expanduser().open(encoding="utf-8") as stream:
        return json.load(stream)


def validate_symbol(symbol):
    """Symbols name single files under data/market/<frequency>/, never paths."""
    if (
        not isinstance(symbol, str)
        or not symbol
        or symbol in (".", "..")
        or any(char in symbol for char in "/\\\x00")
    ):
        raise ValueError(f"Invalid symbol: {symbol!r}")
    return symbol


def resolve_symbols(symbols, symbols_file=None):
    if symbols and symbols_file:
        raise ValueError("Use symbols or symbols-file, not both")
    values = list(symbols or [])
    if symbols_file:
        text = Path(symbols_file).expanduser().read_text(encoding="utf-8")
        values = json.loads(text) if text.lstrip().startswith("[") else text.splitlines()
    if not isinstance(values, list) or any(not isinstance(s, str) for s in values):
        raise ValueError("Symbols file must contain a list of strings")
    result = list(
        dict.fromkeys(s.strip() for value in values for s in value.split(",") if s.strip())
    )
    for symbol in result:
        validate_symbol(symbol)
    return result


def parse_times(values):
    """Parse calendar timestamps without guessing an epoch unit or changing timezone."""
    import pandas as pd

    index = pd.Index(values)
    if pd.api.types.is_numeric_dtype(index.dtype):
        strings = index.astype(str)
        if not strings.str.fullmatch(r"[0-9]{8}").all():
            raise ValueError("Numeric time values must be calendar dates in YYYYMMDD format")
        result = pd.DatetimeIndex(pd.to_datetime(strings, format="%Y%m%d"))
    else:
        result = pd.DatetimeIndex(pd.to_datetime(values))
    if result.hasnans:
        raise ValueError("Time index contains missing timestamps")
    return result.rename("eob")


def _times(values):
    result = parse_times(values)
    return result.tz_localize(None) if result.tz is not None else result


def read_frame(path):
    import pandas as pd

    path = Path(path).expanduser()
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    elif path.suffix.lower() in (".parquet", ".pq"):
        frame = pd.read_parquet(path)
    else:
        raise ValueError("Table files must be Parquet or CSV")
    if "eob" in frame.columns:
        frame = frame.set_index("eob")
    if frame.index.name == "eob" or isinstance(frame.index, pd.DatetimeIndex):
        frame.index = _times(frame.index)
    return frame


def read_panel(path):
    import pandas as pd

    frame = read_frame(path)
    if isinstance(frame.index, pd.MultiIndex):
        if set(frame.index.names) != {"symbol", "eob"}:
            raise ValueError("Panel index must contain symbol and eob")
        frame = frame.reset_index()
    elif frame.index.name == "eob":
        frame = frame.reset_index()
    if not {"symbol", "eob"}.issubset(frame.columns):
        raise ValueError("Panel needs symbol and eob columns or MultiIndex")
    if (
        frame["symbol"].isna().any()
        or not frame["symbol"].map(lambda x: isinstance(x, str) and bool(x.strip())).all()
    ):
        raise ValueError("Panel symbols must be nonempty strings")
    frame["eob"] = _times(frame["eob"])
    frame = frame.set_index(["symbol", "eob"]).sort_index()
    if frame.index.has_duplicates:
        raise ValueError("Panel contains duplicate (symbol, eob) rows")
    return frame


def load_panel(args):
    """Load a PanelSource as a sorted (symbol, eob) panel."""
    import pandas as pd

    symbols = resolve_symbols(args.symbols, args.symbols_file)
    if bool(args.panel) == bool(symbols):
        raise ValueError("Provide exactly one of --panel or --symbols/--symbols-file")
    if args.panel:
        frame = read_panel(args.panel)
    else:
        frame = data_manager(args.data_root).read_symbols(symbols, frequency=args.frequency)
    dates = _times(frame.index.get_level_values("eob"))
    start = pd.Timestamp(args.start) if args.start else None
    end = pd.Timestamp(args.end) if args.end else None
    if start is not None and end is not None and start > end:
        raise ValueError("start must not be after end")
    if start is not None:
        frame = frame.loc[dates >= start]
        dates = _times(frame.index.get_level_values("eob"))
    if end is not None:
        frame = frame.loc[dates < end + pd.Timedelta(days=1)]
    if args.fields:
        missing = sorted(set(args.fields) - set(frame.columns))
        if missing:
            raise ValueError(f"Missing panel fields: {missing}")
        frame = frame.loc[:, args.fields]
    if frame.empty:
        raise ValueError("Panel is empty for the requested symbols and dates")
    return frame


def check_output(path, *, overwrite=False, data_root=None):
    path = Path(path).expanduser().resolve()
    roots = {
        data_manager(data_root).root.resolve(),
        data_manager().root.resolve(),
        Path(__file__).resolve().parents[2] / "data",
    }
    for root in roots:
        for namespace in MANAGED:
            managed = (root / namespace).resolve()
            if path == managed or managed in path.parents:
                raise CLIError(
                    "INVALID_INPUT",
                    f"Output targets a managed store namespace: {path}; use a store command with --write",
                )
    if path.exists() and not overwrite:
        raise CLIError("CONFLICT", f"Output already exists: {path}; use --overwrite", 2)
    if path.exists() and not path.is_file():
        raise ValueError(f"Output is not a file: {path}")
    return path


def _publish(path, writer, *, overwrite=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=path.suffix, dir=path.parent)
    os.close(fd)
    temp = Path(temporary)
    try:
        writer(temp)
        if overwrite:
            os.replace(temp, path)
        else:
            try:
                os.link(temp, path)
            except FileExistsError as exc:
                raise CLIError("CONFLICT", f"Output already exists: {path}", 2) from exc
    finally:
        temp.unlink(missing_ok=True)


def _plain_labels(labels):
    """Column labels without categorical dtype, or ``labels`` itself when there is none."""
    import pandas as pd

    if isinstance(labels, pd.CategoricalIndex):
        return labels.astype(labels.categories.dtype)
    if isinstance(labels, pd.MultiIndex) and any(
        isinstance(level, pd.CategoricalIndex) for level in labels.levels
    ):
        return labels.set_levels(
            [
                level.astype(level.categories.dtype)
                if isinstance(level, pd.CategoricalIndex)
                else level
                for level in labels.levels
            ]
        )
    return labels


def _without_categorical_columns(frame):
    """Parquet written with categorical column labels cannot be read back by pandas.

    Row labels and category-dtype data columns round-trip, so only column labels are
    replaced. The caller's frame is never modified.
    """
    labels = _plain_labels(frame.columns)
    if labels is frame.columns:
        return frame
    frame = frame.copy(deep=False)
    frame.columns = labels
    return frame


def write_frame(frame, path, *, overwrite=False, data_root=None, name=None):
    import pandas as pd

    path = check_output(path, overwrite=overwrite, data_root=data_root)
    if isinstance(frame, pd.Series):
        frame = frame.to_frame(name=frame.name or "value")
    frame = _without_categorical_columns(frame)
    if path.suffix.lower() not in (".csv", ".parquet", ".pq"):
        raise ValueError("Table output must end in .parquet or .csv")

    def writer(temp):
        if path.suffix.lower() == ".csv":
            frame.to_csv(temp, index=not isinstance(frame.index, pd.RangeIndex))
        else:
            frame.to_parquet(temp)

    _publish(path, writer, overwrite=overwrite)
    return Artifact(
        name=name or path.stem,
        path=str(path),
        format="csv" if path.suffix.lower() == ".csv" else "parquet",
        rows=len(frame),
        columns=list(map(str, frame.columns)),
    )


def write_bytes(payload, path, *, overwrite=False, data_root=None, name=None, format=None):
    """Publish a binary file such as a PNG chart."""
    path = check_output(path, overwrite=overwrite, data_root=data_root)
    _publish(path, lambda temp: temp.write_bytes(payload), overwrite=overwrite)
    return Artifact(
        name=name or path.stem, path=str(path), format=format or path.suffix.lstrip(".")
    )


def write_json(value, path, *, overwrite=False, data_root=None, name=None):
    path = check_output(path, overwrite=overwrite, data_root=data_root)
    payload = json.dumps(json_safe(value), ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    _publish(path, lambda temp: temp.write_text(payload, encoding="utf-8"), overwrite=overwrite)
    return Artifact(name=name or path.stem, path=str(path), format="json")


def write_lines(lines, path, *, overwrite=False, data_root=None, name=None):
    path = check_output(path, overwrite=overwrite, data_root=data_root)
    payload = "".join(f"{line}\n" for line in lines)
    _publish(path, lambda temp: temp.write_text(payload, encoding="utf-8"), overwrite=overwrite)
    return Artifact(name=name or path.stem, path=str(path), format="text", rows=len(lines))


def json_safe(value):
    import numpy as np
    import pandas as pd
    from pydantic import BaseModel

    if isinstance(value, BaseModel):
        return json_safe(value.model_dump())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: json_safe(getattr(value, field.name)) for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return json_safe(value.value)
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset, np.ndarray, pd.Index)):
        return [json_safe(v) for v in value]
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (Path, date, datetime)):
        return str(value)
    if isinstance(value, (pd.DataFrame, pd.Series)):
        raise TypeError("Tables must be saved as artifacts, not returned in JSON")
    return value


def frame_summary(frame, preview=5):
    import pandas as pd

    index = frame.index
    dates = index.get_level_values("eob") if "eob" in index.names else index
    dated = isinstance(dates, pd.DatetimeIndex) and len(dates) > 0
    return {
        "rows": len(frame),
        "columns": list(map(str, frame.columns)),
        "start": str(dates.min()) if dated else None,
        "end": str(dates.max()) if dated else None,
        "preview": json_safe(frame.head(preview).reset_index().to_dict("records")),
    }


def import_function(reference):
    module, separator, name = reference.partition(":")
    if not separator or not module or not name:
        raise ValueError("Function reference must be module:name")
    imported = importlib.import_module(module)
    if not hasattr(imported, name):
        raise CLIError(
            "INVALID_INPUT",
            f"Module {module} has no attribute {name}",
            hint="Check the module:name reference.",
        )
    function = getattr(imported, name)
    if not callable(function):
        raise ValueError(f"Not a callable: {reference}")
    return function


def factor_function(indicator=None, function=None):
    """Resolve a public skills.compute indicator name or a module:name callable."""
    if function:
        return import_function(function)
    from skills.compute.indicators import discover_indicators

    func = discover_indicators().get(indicator)
    if func is None:
        raise CLIError(
            "INVALID_INPUT",
            f"Unknown indicator: {indicator}",
            hint="Run `uv run qs compute indicators list` for available names.",
        )
    return func
