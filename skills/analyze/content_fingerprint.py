"""Analyze-native content fingerprints for panels/series (no factor_mining import)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from skills.analyze.contracts import content_hash, json_safe


def _encode_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        if np.isnan(f):
            return None
        if np.isinf(f):
            return {"inf": 1 if f > 0 else -1}
        return f
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        payload: dict[str, Any] = {"ts": int(value.value)}
        if value.tz is not None:
            tz = getattr(value.tz, "key", None) or str(value.tz)
            payload["tz"] = tz
        return payload
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except (TypeError, ValueError, AttributeError) as exc:
            raise TypeError(
                f"unsupported fingerprint scalar: {type(value)!r}"
            ) from exc
    if pd.isna(value):
        return None
    raise TypeError(f"unsupported fingerprint scalar: {type(value)!r}")


def fingerprint_index(index: pd.Index) -> dict[str, Any]:
    if isinstance(index, pd.MultiIndex):
        levels = []
        for i in range(index.nlevels):
            values = [_encode_scalar(v) for v in index.get_level_values(i)]
            levels.append({"name": index.names[i], "values": values})
        return {"type": "multi", "levels": levels}
    return {
        "type": "single",
        "name": index.name,
        "values": [_encode_scalar(v) for v in index],
    }


def fingerprint_series(series: pd.Series) -> str:
    payload = {
        "index": fingerprint_index(series.index),
        "dtype": str(series.dtype),
        "values": [_encode_scalar(v) for v in series.to_numpy(copy=False)],
    }
    return content_hash(json_safe(payload))


def fingerprint_frame(frame: pd.DataFrame) -> str:
    cols = [str(c) for c in frame.columns]
    payload = {
        "index": fingerprint_index(frame.index),
        "columns": cols,
        "blocks": {
            col: [_encode_scalar(v) for v in frame[col].to_numpy(copy=False)]
            for col in sorted(cols)
        },
    }
    return content_hash(json_safe(payload))


__all__ = ["fingerprint_frame", "fingerprint_index", "fingerprint_series"]
