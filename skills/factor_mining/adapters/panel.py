"""Reversible two-level panel index normalization for factor execution."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from skills.factor_mining.contracts import FailureCode, IndexSchema

ADAPTER_SCHEMA_VERSION = "2.0.0"


class PanelAdapterError(Exception):
    """Structured panel validation/normalization failure."""

    def __init__(self, code: FailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class NormalizedPanel:
    """Working copy normalized to ``(symbol, eob)`` with a reversible row map."""

    frame: pd.DataFrame
    index_schema: IndexSchema
    original_positions: np.ndarray
    datetime_was_tz_aware: bool
    original_index: pd.MultiIndex


def _timezone_label(values: pd.DatetimeIndex) -> str:
    tz = values.tz
    if tz is None:
        return "naive"
    for attr in ("key", "zone"):
        name = getattr(tz, attr, None)
        if isinstance(name, str) and name:
            return name
    return str(tz)


def _find_symbol_level(index: pd.MultiIndex) -> int:
    matches = [i for i, name in enumerate(index.names) if name == "symbol"]
    if not matches:
        raise PanelAdapterError(
            FailureCode.INVALID_INDEX_SCHEMA,
            "index must contain exactly one level named 'symbol'",
        )
    if len(matches) > 1:
        raise PanelAdapterError(
            FailureCode.INVALID_INDEX_SCHEMA,
            "index must not contain duplicate 'symbol' levels",
        )
    return matches[0]


def _require_string_symbols(symbols: pd.Index) -> pd.Index:
    cleaned: list[str] = []
    for item in symbols:
        if not isinstance(item, str) or not item.strip():
            raise PanelAdapterError(
                FailureCode.INVALID_INDEX_SCHEMA,
                "symbol level values must be non-empty strings",
            )
        cleaned.append(item)
    return pd.Index(cleaned, dtype=object)


def _as_datetime_level(values: pd.Index, *, level_name: str | None) -> pd.DatetimeIndex:
    label = level_name if level_name is not None else "<unnamed>"
    try:
        converted = pd.to_datetime(pd.Index(values), errors="coerce")
    except Exception as exc:  # noqa: BLE001 - all conversion failures are hard fails
        raise PanelAdapterError(
            FailureCode.TIME_CONVERSION_FAILED,
            f"datetime level {label!r} could not be converted",
        ) from exc
    try:
        if not isinstance(converted, pd.DatetimeIndex):
            converted = pd.DatetimeIndex(converted)
    except Exception as exc:  # noqa: BLE001
        raise PanelAdapterError(
            FailureCode.TIME_CONVERSION_FAILED,
            f"datetime level {label!r} could not be converted",
        ) from exc
    if bool(converted.isna().any()):
        raise PanelAdapterError(
            FailureCode.TIME_CONVERSION_FAILED,
            f"datetime level {label!r} produced NaT values",
        )
    raw = pd.Index(values)
    if raw.nunique(dropna=False) != converted.nunique(dropna=False):
        raise PanelAdapterError(
            FailureCode.TIME_COLLISION,
            f"datetime level {label!r} collapsed distinct keys",
        )
    return converted


def inspect_panel(panel: object) -> IndexSchema:
    """Validate panel index lineage and return schema. Never mutates ``panel``."""
    if not isinstance(panel, pd.DataFrame):
        raise PanelAdapterError(
            FailureCode.INVALID_PANEL_TYPE,
            "panel must be a pandas DataFrame",
        )
    if not isinstance(panel.index, pd.MultiIndex):
        raise PanelAdapterError(
            FailureCode.INVALID_INDEX_SCHEMA,
            "panel index must be a MultiIndex",
        )
    if panel.index.nlevels != 2:
        raise PanelAdapterError(
            FailureCode.INVALID_INDEX_SCHEMA,
            "panel index must have exactly two levels",
        )
    symbol_pos = _find_symbol_level(panel.index)
    datetime_pos = 1 - symbol_pos
    names = tuple(panel.index.names)
    datetime_name = names[datetime_pos]
    _require_string_symbols(panel.index.get_level_values(symbol_pos))
    dt_values = _as_datetime_level(
        panel.index.get_level_values(datetime_pos),
        level_name=datetime_name,
    )
    return IndexSchema(
        names=names,
        symbol_level="symbol",
        datetime_level=datetime_name,
        level_order=(symbol_pos, datetime_pos),
        timezone=_timezone_label(dt_values),
        sorted=bool(panel.index.is_monotonic_increasing),
    )


def normalize_panel(
    panel: object,
    *,
    required_fields: tuple[str, ...] = (),
) -> NormalizedPanel:
    """Copy ``panel`` into a sorted ``(symbol, eob)`` working frame.

    The caller panel is never mutated. Row identity is preserved via
    ``original_positions`` for exact restoration.
    """
    schema = inspect_panel(panel)
    assert isinstance(panel, pd.DataFrame)
    if panel.columns.duplicated().any():
        raise PanelAdapterError(
            FailureCode.INVALID_PANEL_TYPE,
            "panel columns must be unique",
        )
    missing = [name for name in required_fields if name not in panel.columns]
    if missing:
        raise PanelAdapterError(
            FailureCode.MISSING_REQUIRED_FIELD,
            f"missing required fields: {sorted(missing)}",
        )
    for name in required_fields:
        series = panel[name]
        if not pd.api.types.is_numeric_dtype(series.dtype) or pd.api.types.is_bool_dtype(
            series.dtype
        ):
            raise PanelAdapterError(
                FailureCode.NON_NUMERIC_FIELD,
                f"required field {name!r} must be numeric",
            )

    symbol_pos, datetime_pos = schema.level_order
    symbols = _require_string_symbols(panel.index.get_level_values(symbol_pos))
    dt_values = _as_datetime_level(
        panel.index.get_level_values(datetime_pos),
        level_name=schema.datetime_level,
    )
    work_index = pd.MultiIndex.from_arrays(
        [symbols, dt_values],
        names=["symbol", "eob"],
    )
    if work_index.duplicated().any():
        raise PanelAdapterError(
            FailureCode.DUPLICATE_LOGICAL_KEY,
            "duplicate logical keys for (symbol, timestamp)",
        )

    work = panel.copy(deep=True)
    work.index = work_index
    original_positions = np.arange(len(work), dtype=np.int64)
    order = np.lexsort(
        (
            work.index.get_level_values("eob").view("i8"),
            work.index.get_level_values("symbol").to_numpy(),
        )
    )
    work = work.take(order)
    original_positions = original_positions[order]
    return NormalizedPanel(
        frame=work,
        index_schema=schema,
        original_positions=original_positions,
        datetime_was_tz_aware=bool(dt_values.tz is not None),
        original_index=panel.index.copy(),
    )


def restore_series(
    values: pd.Series,
    normalized: NormalizedPanel,
) -> pd.Series:
    """Restore computed ``(symbol, eob)`` values onto the original index semantics."""
    if not isinstance(values.index, pd.MultiIndex):
        raise PanelAdapterError(
            FailureCode.OUTPUT_INDEX_MISMATCH,
            "computed values must use a MultiIndex",
        )
    if list(values.index.names) != ["symbol", "eob"]:
        raise PanelAdapterError(
            FailureCode.OUTPUT_INDEX_MISMATCH,
            "computed values must be indexed by (symbol, eob)",
        )
    if len(values) != len(normalized.frame):
        raise PanelAdapterError(
            FailureCode.OUTPUT_INDEX_MISMATCH,
            "computed values length must match the working panel",
        )
    if not values.index.equals(normalized.frame.index):
        raise PanelAdapterError(
            FailureCode.OUTPUT_INDEX_MISMATCH,
            "computed values index must equal the working panel index",
        )

    ordered = np.empty(len(values), dtype="float64")
    ordered[normalized.original_positions] = values.to_numpy(dtype="float64", copy=True)
    return pd.Series(ordered, index=normalized.original_index.copy(), dtype="float64")


def valid_mask(values: pd.Series) -> pd.Series:
    """Boolean mask of finite numeric values (False for NaN/inf)."""
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64", copy=False)
    mask = np.isfinite(arr)
    return pd.Series(mask, index=values.index, dtype=bool)
