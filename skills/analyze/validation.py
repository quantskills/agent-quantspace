"""Panel / index / field preflight validation for analyze."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from skills.analyze.content_fingerprint import fingerprint_frame
from skills.analyze.contracts import (
    Finding,
    FindingSeverity,
    MetricResult,
    ProtocolSnapshot,
)


def _finding(
    name: str,
    *,
    passed: bool,
    message: str,
    severity: FindingSeverity = FindingSeverity.HARD_FAIL,
    details: Mapping[str, Any] | None = None,
) -> Finding:
    return Finding(
        name=name,
        severity=severity,
        passed=passed,
        message=message,
        details=dict(details or {}),
    )


def _timezone_label(values: pd.Index) -> str:
    if not isinstance(values, pd.DatetimeIndex):
        return "non_datetime"
    tz = values.tz
    if tz is None:
        return "naive"
    for attr in ("key", "zone"):
        name = getattr(tz, attr, None)
        if isinstance(name, str) and name:
            return name
    return str(tz)


def identify_levels(
    index: pd.MultiIndex, protocol: ProtocolSnapshot
) -> tuple[list[Finding], int | None, int | None]:
    findings: list[Finding] = []
    if not isinstance(index, pd.MultiIndex) or index.nlevels != 2:
        findings.append(
            _finding(
                "INPUT_INVALID_INDEX",
                passed=False,
                message="panel index must be a two-level MultiIndex",
            )
        )
        return findings, None, None

    symbol_matches = [
        i for i, name in enumerate(index.names) if name == protocol.symbol_level
    ]
    if len(symbol_matches) != 1:
        findings.append(
            _finding(
                "INPUT_INVALID_INDEX",
                passed=False,
                message=(
                    f"symbol level {protocol.symbol_level!r} must appear exactly once"
                ),
                details={"names": list(index.names)},
            )
        )
        return findings, None, None
    symbol_pos = symbol_matches[0]

    if protocol.datetime_level is None:
        datetime_matches = [i for i, name in enumerate(index.names) if name is None]
    else:
        datetime_matches = [
            i for i, name in enumerate(index.names) if name == protocol.datetime_level
        ]
    if len(datetime_matches) != 1:
        findings.append(
            _finding(
                "INPUT_INVALID_INDEX",
                passed=False,
                message="datetime level identification is ambiguous or missing",
                details={
                    "datetime_level": protocol.datetime_level,
                    "names": list(index.names),
                },
            )
        )
        return findings, None, None
    datetime_pos = datetime_matches[0]
    if datetime_pos == symbol_pos:
        findings.append(
            _finding(
                "INPUT_INVALID_INDEX",
                passed=False,
                message="symbol and datetime levels collide",
            )
        )
        return findings, None, None
    findings.append(
        _finding(
            "INPUT_INDEX_LEVELS",
            passed=True,
            severity=FindingSeverity.INFO,
            message="symbol/datetime levels identified",
            details={
                "symbol_pos": symbol_pos,
                "datetime_pos": datetime_pos,
                "names": list(index.names),
            },
        )
    )
    return findings, symbol_pos, datetime_pos


def validate_panel(
    panel: pd.DataFrame,
    protocol: ProtocolSnapshot,
    *,
    allowed_fields: Sequence[str] | None = None,
) -> tuple[list[Finding], list[MetricResult], dict[str, Any]]:
    """Validate panel without mutating the caller's frame."""
    findings: list[Finding] = []
    metrics: list[MetricResult] = []
    facts: dict[str, Any] = {}

    if not isinstance(panel, pd.DataFrame):
        findings.append(
            _finding(
                "INPUT_INVALID_PANEL",
                passed=False,
                message="panel must be a pandas DataFrame",
            )
        )
        return findings, metrics, facts

    level_findings, symbol_pos, datetime_pos = identify_levels(panel.index, protocol)
    findings.extend(level_findings)
    if symbol_pos is None or datetime_pos is None:
        return findings, metrics, facts

    symbols = panel.index.get_level_values(symbol_pos)
    times = panel.index.get_level_values(datetime_pos)
    facts["symbol_pos"] = symbol_pos
    facts["datetime_pos"] = datetime_pos
    facts["n_rows"] = int(len(panel))
    facts["n_symbols"] = int(pd.Index(symbols).nunique(dropna=False))

    bad_symbols = [
        item
        for item in symbols
        if not isinstance(item, str) or not str(item).strip()
    ]
    if bad_symbols:
        findings.append(
            _finding(
                "INPUT_INVALID_SYMBOL",
                passed=False,
                message="symbol values must be non-empty strings",
                details={"count": len(bad_symbols)},
            )
        )
    else:
        findings.append(
            _finding(
                "INPUT_SYMBOL_TYPE",
                passed=True,
                severity=FindingSeverity.INFO,
                message="symbol values are non-empty strings",
            )
        )

    try:
        as_dt = pd.DatetimeIndex(pd.to_datetime(pd.Index(times), errors="raise"))
    except Exception as exc:  # noqa: BLE001
        findings.append(
            _finding(
                "INPUT_TIME_CONVERSION",
                passed=False,
                message="datetime level could not be converted",
                details={"cause_type": type(exc).__name__},
            )
        )
        return findings, metrics, facts

    tz_label = _timezone_label(as_dt if isinstance(times, pd.DatetimeIndex) else as_dt)
    # Prefer original DatetimeIndex tz when already datetime-like.
    if isinstance(times, pd.DatetimeIndex):
        tz_label = _timezone_label(times)
        as_dt = times
    facts["timezone"] = tz_label
    if protocol.timezone == "naive":
        tz_ok = tz_label == "naive"
    else:
        tz_ok = tz_label == protocol.timezone
    findings.append(
        _finding(
            "INPUT_TIMEZONE",
            passed=tz_ok,
            severity=FindingSeverity.HARD_FAIL if not tz_ok else FindingSeverity.INFO,
            message=(
                "timezone matches protocol"
                if tz_ok
                else f"timezone {tz_label!r} != protocol {protocol.timezone!r}"
            ),
            details={"observed": tz_label, "expected": protocol.timezone},
        )
    )

    # Uniqueness of logical keys.
    key_frame = pd.DataFrame(
        {
            "symbol": list(symbols),
            "time": list(as_dt),
        }
    )
    dup_count = int(key_frame.duplicated().sum())
    findings.append(
        _finding(
            "INPUT_UNIQUE_KEYS",
            passed=dup_count == 0,
            message=(
                "logical keys are unique"
                if dup_count == 0
                else f"duplicate logical keys: {dup_count}"
            ),
            details={"duplicate_count": dup_count},
        )
    )

    # Per-symbol sortability (not requiring global sort).
    unsorted_symbols: list[str] = []
    for symbol, group in key_frame.groupby("symbol", sort=False):
        order = pd.Index(group["time"]).argsort()
        if not (order == np.arange(len(order))).all():
            # Still sortable if unique times; flag only non-unique times within symbol.
            if group["time"].duplicated().any():
                unsorted_symbols.append(str(symbol))
    findings.append(
        _finding(
            "INPUT_SYMBOL_TIME_UNIQUE",
            passed=not unsorted_symbols,
            message=(
                "per-symbol times are unique"
                if not unsorted_symbols
                else "duplicate times within symbol"
            ),
            details={"symbols": unsorted_symbols[:20]},
        )
    )

    required = tuple(protocol.required_fields)
    if allowed_fields is not None:
        allowed = set(allowed_fields)
        missing_allowed = [name for name in required if name not in allowed]
        if missing_allowed:
            findings.append(
                _finding(
                    "INPUT_FIELD_NOT_ALLOWED",
                    passed=False,
                    message="required fields are outside allowed field set",
                    details={"missing_allowed": missing_allowed},
                )
            )

    missing_cols = [name for name in required if name not in panel.columns]
    findings.append(
        _finding(
            "INPUT_REQUIRED_FIELDS",
            passed=not missing_cols,
            message=(
                "required fields present"
                if not missing_cols
                else f"missing required fields: {missing_cols}"
            ),
            details={"missing": missing_cols},
        )
    )

    coverage: dict[str, float] = {}
    for col in required:
        if col not in panel.columns:
            continue
        series = panel[col]
        if not pd.api.types.is_numeric_dtype(series):
            findings.append(
                _finding(
                    "INPUT_NON_NUMERIC_FIELD",
                    passed=False,
                    message=f"field {col!r} is not numeric",
                )
            )
            continue
        values = pd.to_numeric(series, errors="coerce")
        n = len(values)
        n_missing = int(values.isna().sum())
        n_inf = int(np.isinf(values.to_numpy(dtype=float, na_value=np.nan)).sum())
        finite = int(np.isfinite(values.to_numpy(dtype=float, na_value=np.nan)).sum())
        cov = float(finite / n) if n else 0.0
        coverage[col] = cov
        metrics.append(
            MetricResult(
                name=f"coverage_{col}",
                value=cov,
                unit="ratio",
                sample_range="panel",
            )
        )
        metrics.append(
            MetricResult(
                name=f"missing_{col}",
                value=n_missing,
                unit="count",
                sample_range="panel",
            )
        )
        metrics.append(
            MetricResult(
                name=f"inf_{col}",
                value=n_inf,
                unit="count",
                sample_range="panel",
            )
        )
        if n_inf:
            findings.append(
                _finding(
                    "INPUT_INF_VALUES",
                    passed=False,
                    severity=FindingSeverity.SOFT_FAIL,
                    message=f"field {col!r} contains Inf values",
                    details={"count": n_inf},
                )
            )

    facts["coverage"] = coverage
    if coverage:
        # Canonical OOS observation: the official minimum coverage across the
        # protocol-required fields.  Consumers must use this metric rather
        # than re-aggregating individual coverage_<field> facts.
        metrics.append(
            MetricResult(
                name="coverage_worst",
                value=float(min(coverage.values())),
                unit="ratio",
                sample_range="panel",
            )
        )

    # OHLC anomaly flags when columns are present.
    ohlc_cols = [c for c in ("open", "high", "low", "close") if c in panel.columns]
    if len(ohlc_cols) >= 2 and all(
        pd.api.types.is_numeric_dtype(panel[c]) for c in ohlc_cols
    ):
        anomalies = 0
        if {"high", "low"}.issubset(ohlc_cols):
            anomalies += int((panel["high"] < panel["low"]).fillna(False).sum())
        if {"high", "open", "close"}.issubset(ohlc_cols):
            anomalies += int(
                (
                    panel["high"] < panel[["open", "close"]].max(axis=1)
                )
                .fillna(False)
                .sum()
            )
        if {"low", "open", "close"}.issubset(ohlc_cols):
            anomalies += int(
                (
                    panel["low"] > panel[["open", "close"]].min(axis=1)
                )
                .fillna(False)
                .sum()
            )
        findings.append(
            _finding(
                "INPUT_OHLC_ANOMALY",
                passed=anomalies == 0,
                severity=FindingSeverity.SOFT_FAIL if anomalies else FindingSeverity.INFO,
                message=(
                    "no OHLC anomalies"
                    if anomalies == 0
                    else f"OHLC anomaly rows flagged: {anomalies}"
                ),
                details={"anomaly_count": anomalies},
            )
        )

    # Universe membership when protocol declares an explicit universe.
    if protocol.universe:
        observed = {str(s) for s in symbols}
        unexpected = sorted(observed - set(protocol.universe))
        findings.append(
            _finding(
                "INPUT_UNIVERSE",
                passed=not unexpected,
                severity=FindingSeverity.HARD_FAIL if unexpected else FindingSeverity.INFO,
                message=(
                    "panel symbols ⊆ protocol universe"
                    if not unexpected
                    else "panel contains symbols outside protocol universe"
                ),
                details={"unexpected": unexpected[:50]},
            )
        )

    facts["panel_hash"] = fingerprint_frame(panel)
    min_cov = protocol.thresholds.get("min_coverage")
    if isinstance(min_cov, (int, float)) and coverage:
        worst = min(coverage.values())
        findings.append(
            _finding(
                "INPUT_COVERAGE_THRESHOLD",
                passed=worst >= float(min_cov),
                severity=FindingSeverity.SOFT_FAIL,
                message=f"worst field coverage {worst:.4f} vs min {min_cov}",
                details={"worst": worst, "min_coverage": float(min_cov)},
            )
        )
    findings.append(
        _finding(
            "INPUT_PANEL_OK",
            passed=not any(
                (not f.passed) and f.severity is FindingSeverity.HARD_FAIL for f in findings
            ),
            severity=FindingSeverity.INFO,
            message="panel validation finished",
        )
    )
    return findings, metrics, facts


__all__ = ["identify_levels", "validate_panel"]
