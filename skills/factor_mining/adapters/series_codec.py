"""JSON-safe MultiIndex Series codec with explicit per-level descriptors."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

import pandas as pd

from skills.factor_mining.contracts import FailureCode


class SeriesCodecError(Exception):
    def __init__(self, code: FailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_LEVEL_KINDS = frozenset({"object", "datetime", "date", "bool", "int", "float"})
_LEVEL_KEYS = frozenset({"kind", "name", "tz", "encoding", "values"})
_DATETIME_ENCODINGS = frozenset({"utc_ns", "naive_iso"})


def _encode_number(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return {"inf": 1 if value > 0 else -1}
        return float(value)
    if pd.isna(value):
        return None
    raise SeriesCodecError(
        FailureCode.INVALID_OUTPUT_TYPE,
        "unsupported series value type for artifact encoding",
    )


def _decode_inf_marker(value: Mapping[str, Any]) -> float:
    if set(value.keys()) != {"inf"}:
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "invalid numeric series payload value",
        )
    marker = value["inf"]
    # Exact +1 / -1 only; reject bool, 0, 2, and string coercion.
    if isinstance(marker, bool) or not isinstance(marker, int) or marker not in (1, -1):
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "inf marker must be exactly +1 or -1",
        )
    return math.inf if marker == 1 else -math.inf


def _decode_number(value: Any, *, as_bool: bool = False) -> Any:
    if as_bool:
        if isinstance(value, bool):
            return value
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "bool series payload values must be boolean",
        )
    if value is None:
        return float("nan")
    if isinstance(value, Mapping):
        return _decode_inf_marker(value)
    if isinstance(value, bool):
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "numeric series payload rejected boolean value",
        )
    if isinstance(value, (int, float)):
        return float(value)
    raise SeriesCodecError(
        FailureCode.ARTIFACT_PERSIST_FAILED,
        "invalid numeric series payload value",
    )


def _timezone_name(tz: Any) -> str | None:
    if tz is None:
        return None
    for attr in ("key", "zone"):
        name = getattr(tz, attr, None)
        if isinstance(name, str) and name:
            return name
    text = str(tz)
    return text or None


def _is_python_date_level(values: pd.Index) -> bool:
    non_null = [item for item in values if item is not None and not pd.isna(item)]
    if not non_null:
        return False
    return all(
        isinstance(item, date) and not isinstance(item, datetime) for item in non_null
    )


def _encode_level(values: pd.Index, *, name: str | None) -> dict[str, Any]:
    if isinstance(values, pd.DatetimeIndex):
        tz_name = _timezone_name(values.tz)
        if values.tz is not None:
            # Unambiguous UTC instants + IANA zone (handles DST fold hours).
            encoded: list[Any] = []
            for ts in values:
                if pd.isna(ts):
                    encoded.append(None)
                    continue
                stamp = pd.Timestamp(ts)
                encoded.append(int(stamp.tz_convert("UTC").value))
            return {
                "kind": "datetime",
                "name": name,
                "tz": tz_name,
                "encoding": "utc_ns",
                "values": encoded,
            }
        encoded_naive: list[Any] = []
        for ts in values:
            if pd.isna(ts):
                encoded_naive.append(None)
            else:
                encoded_naive.append(pd.Timestamp(ts).isoformat())
        return {
            "kind": "datetime",
            "name": name,
            "tz": None,
            "encoding": "naive_iso",
            "values": encoded_naive,
        }
    if _is_python_date_level(values):
        encoded_dates: list[Any] = []
        for item in values:
            if item is None or pd.isna(item):
                encoded_dates.append(None)
            elif isinstance(item, date) and not isinstance(item, datetime):
                encoded_dates.append(item.isoformat())
            else:
                raise SeriesCodecError(
                    FailureCode.INVALID_OUTPUT_TYPE,
                    "date level values must be homogeneous Python date objects",
                )
        return {
            "kind": "date",
            "name": name,
            "tz": None,
            "values": encoded_dates,
        }
    if pd.api.types.is_bool_dtype(values.dtype):
        return {
            "kind": "bool",
            "name": name,
            "tz": None,
            "values": [None if pd.isna(v) else bool(v) for v in values],
        }
    if pd.api.types.is_integer_dtype(values.dtype):
        return {
            "kind": "int",
            "name": name,
            "tz": None,
            "values": [None if pd.isna(v) else int(v) for v in values],
        }
    if pd.api.types.is_float_dtype(values.dtype):
        return {
            "kind": "float",
            "name": name,
            "tz": None,
            "values": [_encode_number(v) for v in values],
        }
    # Object / string levels stay literal; never coerce date-like strings.
    out: list[Any] = []
    for item in values:
        if item is None or (not isinstance(item, (bytes, bytearray)) and pd.isna(item)):
            out.append(None)
        elif isinstance(item, (str, bool)):
            out.append(item)
        elif isinstance(item, int) and not isinstance(item, bool):
            out.append(int(item))
        elif isinstance(item, float):
            out.append(_encode_number(item))
        else:
            raise SeriesCodecError(
                FailureCode.INVALID_OUTPUT_TYPE,
                "unsupported object level value type",
            )
    return {
        "kind": "object",
        "name": name,
        "tz": None,
        "values": out,
    }


def _validate_level_descriptor(level: Mapping[str, Any]) -> None:
    unknown = set(level.keys()) - _LEVEL_KEYS
    if unknown:
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series level descriptor has unknown keys",
        )
    kind = level.get("kind")
    if kind not in _LEVEL_KINDS:
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series level kind is invalid",
        )
    name = level.get("name")
    if name is not None and not isinstance(name, str):
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series level name must be str or null",
        )
    tz_name = level.get("tz")
    if tz_name is not None and not isinstance(tz_name, str):
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "datetime level tz must be str or null",
        )
    values = level.get("values")
    if not isinstance(values, list):
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series level values must be a list",
        )
    if kind == "datetime":
        encoding = level.get("encoding")
        if encoding not in _DATETIME_ENCODINGS:
            raise SeriesCodecError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "datetime level encoding is invalid",
            )
        if encoding == "utc_ns" and not tz_name:
            raise SeriesCodecError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "utc_ns datetime levels require an IANA timezone",
            )
        if encoding == "naive_iso" and tz_name is not None:
            raise SeriesCodecError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "naive_iso datetime levels must not set tz",
            )
    else:
        if tz_name is not None:
            raise SeriesCodecError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "non-datetime levels must set tz to null",
            )
        if "encoding" in level and level.get("encoding") is not None:
            raise SeriesCodecError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "only datetime levels may set encoding",
            )


def _decode_level(level: Mapping[str, Any], *, expected_len: int) -> pd.Index:
    _validate_level_descriptor(level)
    kind = level["kind"]
    name = level.get("name")
    values = level["values"]
    if len(values) != expected_len:
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series level length mismatch",
        )
    try:
        if kind == "datetime":
            encoding = level["encoding"]
            tz_name = level.get("tz")
            if encoding == "utc_ns":
                instants: list[Any] = []
                for item in values:
                    if item is None:
                        instants.append(pd.NaT)
                    elif isinstance(item, int) and not isinstance(item, bool):
                        instants.append(item)
                    else:
                        raise SeriesCodecError(
                            FailureCode.ARTIFACT_PERSIST_FAILED,
                            "utc_ns values must be int nanoseconds or null",
                        )
                parsed = pd.to_datetime(instants, unit="ns", utc=True)
                return parsed.tz_convert(tz_name).rename(name)
            decoded_naive: list[Any] = []
            for item in values:
                if item is None:
                    decoded_naive.append(pd.NaT)
                elif isinstance(item, str):
                    decoded_naive.append(item)
                else:
                    raise SeriesCodecError(
                        FailureCode.ARTIFACT_PERSIST_FAILED,
                        "naive_iso values must be strings or null",
                    )
            naive_index = pd.DatetimeIndex(
                pd.to_datetime(decoded_naive, errors="raise")
            ).rename(name)
            if naive_index.tz is not None:
                raise SeriesCodecError(
                    FailureCode.ARTIFACT_PERSIST_FAILED,
                    "naive_iso datetime levels must decode to tz-naive values",
                )
            return naive_index
        if kind == "date":
            decoded_dates: list[Any] = []
            for item in values:
                if item is None:
                    decoded_dates.append(None)
                elif isinstance(item, str):
                    decoded_dates.append(date.fromisoformat(item))
                else:
                    raise SeriesCodecError(
                        FailureCode.ARTIFACT_PERSIST_FAILED,
                        "date level values must be ISO date strings or null",
                    )
            return pd.Index(decoded_dates, dtype=object, name=name)
        if kind == "bool":
            decoded_bool: list[Any] = []
            for item in values:
                if item is None:
                    decoded_bool.append(None)
                elif isinstance(item, bool):
                    decoded_bool.append(item)
                else:
                    raise SeriesCodecError(
                        FailureCode.ARTIFACT_PERSIST_FAILED,
                        "bool level values must be boolean or null",
                    )
            return pd.Index(decoded_bool, name=name, dtype=object).astype("boolean")
        if kind == "int":
            decoded_int: list[Any] = []
            for item in values:
                if item is None:
                    decoded_int.append(pd.NA)
                elif isinstance(item, int) and not isinstance(item, bool):
                    decoded_int.append(item)
                else:
                    raise SeriesCodecError(
                        FailureCode.ARTIFACT_PERSIST_FAILED,
                        "int level values must be non-bool int or null",
                    )
            return pd.Index(decoded_int, name=name, dtype="Int64")
        if kind == "float":
            return pd.Index(
                [_decode_number(v) for v in values], name=name, dtype="float64"
            )
        # object
        for item in values:
            if item is None or isinstance(item, (str, bool, int, float)):
                continue
            if isinstance(item, Mapping):
                _decode_inf_marker(item)
                continue
            raise SeriesCodecError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "object level contains an unsupported value type",
            )
        return pd.Index(
            [_decode_number(v) if isinstance(v, Mapping) else v for v in values],
            name=name,
            dtype=object,
        )
    except SeriesCodecError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series level values could not be decoded",
        ) from exc


def series_to_payload(series: pd.Series) -> dict[str, Any]:
    """Encode a MultiIndex Series using explicit per-level descriptors."""
    if not isinstance(series.index, pd.MultiIndex):
        raise SeriesCodecError(
            FailureCode.INVALID_OUTPUT_TYPE,
            "only MultiIndex Series payloads are supported",
        )
    if series.index.nlevels != 2:
        raise SeriesCodecError(
            FailureCode.INVALID_OUTPUT_TYPE,
            "series payload requires a two-level MultiIndex",
        )
    names = list(series.index.names)
    levels = [
        _encode_level(series.index.get_level_values(i), name=names[i])
        for i in range(2)
    ]
    if pd.api.types.is_bool_dtype(series.dtype):
        data = [bool(v) for v in series.to_numpy(copy=False)]
        dtype = "bool"
    else:
        data = [_encode_number(v) for v in series.to_numpy(copy=False)]
        dtype = "float64"
    return {
        "index_names": names,
        "levels": levels,
        "data": data,
        "dtype": dtype,
    }


def series_content_hash(series: pd.Series) -> str:
    """Immutable content identity of a Series via canonical ``series_to_payload``."""
    from skills.factor_mining.contracts import content_hash

    return content_hash(series_to_payload(series))


def series_from_payload(payload: Mapping[str, Any]) -> pd.Series:
    """Decode a payload produced by ``series_to_payload``."""
    if not isinstance(payload, Mapping):
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series payload must be a mapping",
        )
    unknown = set(payload.keys()) - {"index_names", "levels", "data", "dtype"}
    if unknown:
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series payload has unknown keys",
        )
    try:
        names = list(payload["index_names"])
        levels_raw = list(payload["levels"])
        data_raw = list(payload["data"])
        dtype = payload.get("dtype", "float64")
    except Exception as exc:  # noqa: BLE001
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "invalid series payload shape",
        ) from exc
    if len(names) != 2 or len(levels_raw) != 2:
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series payload must describe a two-level MultiIndex",
        )
    if not isinstance(dtype, str):
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series dtype must be a string",
        )
    expected_len = len(data_raw)
    arrays = [
        _decode_level(_require_level(level), expected_len=expected_len)
        for level in levels_raw
    ]
    for i, level in enumerate(levels_raw):
        declared = level.get("name")
        if declared != names[i]:
            raise SeriesCodecError(
                FailureCode.ARTIFACT_PERSIST_FAILED,
                "series level name does not match index_names",
            )
    try:
        index = pd.MultiIndex.from_arrays(arrays, names=names)
    except Exception as exc:  # noqa: BLE001
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series index could not be rebuilt",
        ) from exc
    if dtype == "bool":
        data = [_decode_number(item, as_bool=True) for item in data_raw]
        return pd.Series(data, index=index, dtype=bool)
    if dtype != "float64":
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "unsupported series dtype in payload",
        )
    data = [_decode_number(item) for item in data_raw]
    return pd.Series(data, index=index, dtype="float64")


def _require_level(level: Any) -> Mapping[str, Any]:
    if not isinstance(level, Mapping):
        raise SeriesCodecError(
            FailureCode.ARTIFACT_PERSIST_FAILED,
            "series level descriptor must be a mapping",
        )
    return level
