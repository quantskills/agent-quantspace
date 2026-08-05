"""Analyze-native immutable contracts for deterministic evaluation.

These types are internal to ``skills.analyze`` and deliberately do **not** copy
Phase 01 ``factor_mining`` business objects. Orchestration adapters map results
outward into EvaluationReport envelopes.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

import numpy as np

ENGINE_VERSION = "3.0.0"
ANALYZE_SCHEMA_VERSION = "3.0.0"

SECTION_NAMES = (
    "data_quality",
    "formula_safety",
    "causality",
    "alignment",
    "predictive",
    "robustness",
    "trading",
    "pool_incremental",
)


class FindingSeverity(str, Enum):
    HARD_FAIL = "hard_fail"
    SOFT_FAIL = "soft_fail"
    WARNING = "warning"
    INFO = "info"


class SectionStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_RUN = "not_run"
    UNAVAILABLE = "unavailable"


class CompletionStatus(str, Enum):
    COMPLETE = "complete"
    HARD_FAILED = "hard_failed"
    PARTIAL = "partial"


def _require_non_empty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValueError("NaN and Infinity are not allowed in contract values")
    return value


def _freeze_mapping(value: Mapping[Any, Any]) -> Mapping[str, Any]:
    frozen: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"mapping keys must be str, got {type(key)!r}")
        frozen[key] = _freeze_value(item)
    return MappingProxyType(frozen)


def canonical_value(value: Any) -> Any:
    """Normalize values for stable strict-JSON serialization and hashing."""
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("canonical JSON rejects NaN and Infinity")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key in value:
            if not isinstance(key, str):
                raise TypeError("canonical JSON requires str keys")
            normalized[key] = canonical_value(value[key])
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return canonical_value(
            {item.name: getattr(value, item.name) for item in fields(value)}
        )
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"unsupported canonical value type: {type(value)!r}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonical_value(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def json_safe(value: Any) -> Any:
    """Convert values to strict-JSON types; encode non-finite floats explicitly."""
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return {"inf": 1 if value > 0 else -1}
        return value
    if isinstance(value, Mapping):
        return {str(k): json_safe(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return json_safe({item.name: getattr(value, item.name) for item in fields(value)})
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"value is not JSON-serializable: {type(value)!r}")


ALLOWED_DIRECTIONS = frozenset({"long_high", "long_low"})
ALLOWED_TIE_RULES = frozenset({"average", "first", "dense", "min", "max"})
ALLOWED_REBALANCES = frozenset({"daily", "weekly", "monthly"})
ALLOWED_TRADE_AT = frozenset({"open", "close"})
ALLOWED_RETURN_MODES = frozenset({"forward", "backward"})


def protocol_content_hash(protocol: ProtocolSnapshot) -> str:
    """Deterministic content hash of a fully frozen ProtocolSnapshot."""
    return content_hash(protocol)


@dataclass(frozen=True)
class ProtocolSnapshot:
    """Fully frozen evaluation protocol; facade must not fill missing fields."""

    horizon_bars: int
    direction: str
    n_groups: int
    tie_rule: str
    rebalance: str
    commission: float
    slippage: float
    parameter_neighborhood: Mapping[str, tuple[Any, ...]]
    regimes: tuple[str, ...]
    time_subsamples: tuple[str, ...]
    random_seed: int
    multiple_testing_budget: int
    thresholds: Mapping[str, Any]
    symbol_level: str
    datetime_level: str | None
    timezone: str
    required_fields: tuple[str, ...]
    min_cross_section: int
    min_ic_samples: int
    bootstrap_samples: int
    bootstrap_block_size: int
    ic_decay_horizons: tuple[int, ...]
    trade_at: str
    signal_lag: int
    return_mode: str
    allow_short: bool
    require_prefix_recompute: bool
    universe: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.horizon_bars, int) or isinstance(self.horizon_bars, bool):
            raise ValueError("horizon_bars must be a Python int")
        if self.horizon_bars <= 0:
            raise ValueError("horizon_bars must be positive")
        if not isinstance(self.n_groups, int) or isinstance(self.n_groups, bool):
            raise ValueError("n_groups must be a Python int")
        if self.n_groups < 2:
            raise ValueError("n_groups must be >= 2")
        if self.direction not in ALLOWED_DIRECTIONS:
            raise ValueError(f"direction must be one of {sorted(ALLOWED_DIRECTIONS)}")
        if self.tie_rule not in ALLOWED_TIE_RULES:
            raise ValueError(f"tie_rule must be one of {sorted(ALLOWED_TIE_RULES)}")
        if self.rebalance not in ALLOWED_REBALANCES:
            raise ValueError(f"rebalance must be one of {sorted(ALLOWED_REBALANCES)}")
        _require_non_empty("symbol_level", self.symbol_level)
        _require_non_empty("timezone", self.timezone)
        if self.datetime_level is not None:
            _require_non_empty("datetime_level", self.datetime_level)
        for name in ("commission", "slippage"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a real number")
            if not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        for name in (
            "random_seed",
            "multiple_testing_budget",
            "min_cross_section",
            "min_ic_samples",
            "bootstrap_samples",
            "bootstrap_block_size",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be a Python int")
        if self.min_cross_section < 2:
            raise ValueError("min_cross_section must be >= 2")
        if self.min_ic_samples < 1:
            raise ValueError("min_ic_samples must be >= 1")
        if self.bootstrap_samples < 1 or self.bootstrap_block_size < 1:
            raise ValueError("bootstrap knobs must be positive")
        if self.multiple_testing_budget < 0 or self.random_seed < 0:
            raise ValueError("seed/budget must be non-negative")
        if self.trade_at not in ALLOWED_TRADE_AT:
            raise ValueError(f"trade_at must be one of {sorted(ALLOWED_TRADE_AT)}")
        if self.return_mode not in ALLOWED_RETURN_MODES:
            raise ValueError(f"return_mode must be one of {sorted(ALLOWED_RETURN_MODES)}")
        if not isinstance(self.signal_lag, int) or isinstance(self.signal_lag, bool) or self.signal_lag < 0:
            raise ValueError("signal_lag must be a non-negative Python int")
        if not isinstance(self.allow_short, bool):
            raise ValueError("allow_short must be a Python bool")
        if not isinstance(self.require_prefix_recompute, bool):
            raise ValueError("require_prefix_recompute must be a Python bool")
        horizons = tuple(self.ic_decay_horizons)
        if not horizons:
            raise ValueError("ic_decay_horizons must be non-empty")
        if any((not isinstance(h, int)) or isinstance(h, bool) or h <= 0 for h in horizons):
            raise ValueError("ic_decay_horizons must be positive Python ints")
        if len(set(horizons)) != len(horizons):
            raise ValueError("ic_decay_horizons must be unique")
        object.__setattr__(self, "ic_decay_horizons", horizons)
        neighborhood = {
            key: tuple(value) if not isinstance(value, tuple) else value
            for key, value in dict(self.parameter_neighborhood).items()
        }
        object.__setattr__(self, "parameter_neighborhood", _freeze_mapping(neighborhood))
        object.__setattr__(self, "thresholds", _freeze_mapping(dict(self.thresholds)))
        canonical_json(dict(self.parameter_neighborhood))
        canonical_json(dict(self.thresholds))
        regimes = tuple(self.regimes)
        if len(set(regimes)) != len(regimes):
            raise ValueError("regimes must be unique")
        object.__setattr__(self, "regimes", regimes)
        time_subsamples = tuple(self.time_subsamples)
        if len(set(time_subsamples)) != len(time_subsamples):
            raise ValueError("time_subsamples must be unique")
        if any((not isinstance(s, str)) or not s.strip() for s in time_subsamples):
            raise ValueError("time_subsamples must be non-empty strings")
        object.__setattr__(self, "time_subsamples", time_subsamples)
        fields_t = tuple(self.required_fields)
        if not fields_t:
            raise ValueError("required_fields must be non-empty")
        if len(set(fields_t)) != len(fields_t):
            raise ValueError("required_fields must be unique")
        object.__setattr__(self, "required_fields", fields_t)
        universe = tuple(self.universe)
        if len(set(universe)) != len(universe):
            raise ValueError("universe must be unique")
        if any((not isinstance(s, str)) or not s.strip() for s in universe):
            raise ValueError("universe members must be non-empty strings")
        object.__setattr__(self, "universe", universe)

    @property
    def content_hash(self) -> str:
        return protocol_content_hash(self)


@dataclass(frozen=True)
class SpecSnapshot:
    """Analyze-native FactorSpec view (no Phase 01 object dependency)."""

    factor_id: str
    formula_kind: str
    function_module: str | None
    function_name: str | None
    expression: Mapping[str, Any] | None
    params: Mapping[str, Any]
    required_fields: tuple[str, ...]
    window: int
    lag: int
    warmup: int
    missing_policy: str
    output_dtype: str
    expected_direction: str
    content_hash: str
    formula_fingerprint: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("factor_id", self.factor_id)
        _require_non_empty("formula_kind", self.formula_kind)
        _require_non_empty("missing_policy", self.missing_policy)
        _require_non_empty("output_dtype", self.output_dtype)
        _require_non_empty("expected_direction", self.expected_direction)
        _require_non_empty("content_hash", self.content_hash)
        if self.expected_direction not in ALLOWED_DIRECTIONS:
            raise ValueError("expected_direction must be long_high or long_low")
        for name in ("window", "lag", "warmup"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative Python int")
        if self.missing_policy not in {"keep_nan", "drop_nan"}:
            raise ValueError("missing_policy must be keep_nan or drop_nan")
        if self.output_dtype not in {"float64"}:
            raise ValueError("output_dtype must be float64")
        object.__setattr__(self, "required_fields", tuple(self.required_fields))
        object.__setattr__(self, "params", _freeze_mapping(dict(self.params)))
        canonical_json(dict(self.params))
        if self.expression is not None:
            object.__setattr__(
                self, "expression", _freeze_mapping(dict(self.expression))
            )
            canonical_json(dict(self.expression))
        object.__setattr__(self, "formula_fingerprint", str(self.formula_fingerprint))


# Issued FormalBacktestPair digests. Only the official runner may register.
_FORMAL_PAIR_DIGESTS: set[str] = set()


def _register_formal_pair_digest(digest: str) -> None:
    """Register a canonical issuance digest (digest string only — no results)."""
    if not isinstance(digest, str) or not digest:
        raise ValueError("formal-pair digest must be a non-empty string")
    _FORMAL_PAIR_DIGESTS.add(digest)


def _backtest_result_digest_payload(result: Any) -> Mapping[str, str]:
    from skills.analyze.content_fingerprint import fingerprint_frame

    return {
        "result_df": fingerprint_frame(result.result_df),
        "executed_weights": fingerprint_frame(result.executed_weights),
    }


def formal_pair_issuance_digest(pair: FormalBacktestPair) -> str:
    """Canonical digest over results + frozen provenance fields."""
    payload = {
        "before": _backtest_result_digest_payload(pair.before),
        "after": _backtest_result_digest_payload(pair.after),
        "protocol_content_hash": pair.protocol_content_hash,
        "panel_hash": pair.panel_hash,
        "candidate_hash": pair.candidate_hash,
        "ordered_pool_hash": pair.ordered_pool_hash,
        "shared_sample_hash": pair.shared_sample_hash,
        "before_weights_hash": pair.before_weights_hash,
        "after_weights_hash": pair.after_weights_hash,
        "engine_name": pair.engine_name,
        "engine_version": pair.engine_version,
    }
    return content_hash(payload)


class FormalBacktestPair:
    """Issued before/after formal ``BacktestResult`` pair for pool portfolio deltas.

    Public construction is forbidden. Production pairs come only from
    ``run_official_formal_backtest_pair``, which calls ``VectorBacktester``
    twice internally on explicit before/after target weights and registers a
    canonical issuance digest over results + provenance. Ordinary attribute
    assignment is rejected; ``is_issued`` recomputes the digest every time so
    ``object.__setattr__`` tampering invalidates issuance. There is no helper
    that accepts caller-supplied ``BacktestResult`` objects as verified.
    """

    __slots__ = (
        "before",
        "after",
        "protocol_content_hash",
        "panel_hash",
        "candidate_hash",
        "ordered_pool_hash",
        "shared_sample_hash",
        "before_weights_hash",
        "after_weights_hash",
        "engine_version",
        "engine_name",
        "_frozen",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "FormalBacktestPair cannot be constructed directly; use "
            "skills.analyze.factor_incremental.run_official_formal_backtest_pair"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError(
                f"FormalBacktestPair is immutable; cannot set {name!r}"
            )
        object.__setattr__(self, name, value)

    def is_issued(self) -> bool:
        if self.engine_name != "VectorBacktester":
            return False
        try:
            digest = formal_pair_issuance_digest(self)
        except Exception:  # noqa: BLE001
            return False
        return digest in _FORMAL_PAIR_DIGESTS


def verified_backtest_metrics(
    result: Any, *, rtol: float = 0.0, atol: float = 1e-12
) -> dict[str, float]:
    """Recompute canonical portfolio metrics; never trust forged frame columns.

    Authority:
    - ``total_return`` / equity path from ``result_df["return"]`` via cumprod
    - ``max_drawdown`` from that recomputed equity
    - ``avg_daily_turnover`` from ``executed_weights.diff().fillna(weights).abs()``
      summed per row, then aligned to ``result_df.index`` (preserves VectorBacktester
      semantics after date-range / forward-drop)

    ``result_df`` equity/drawdown/turnover columns must match the recomputation
    within tolerance; otherwise raises ``ValueError`` (formal_result_unverified).
    ``result.metrics`` is never read.
    """
    from skills.backtest.vector import BacktestResult

    if not isinstance(result, BacktestResult):
        raise TypeError("verified_backtest_metrics requires BacktestResult")
    weights = result.executed_weights
    df = result.result_df
    if weights is None or getattr(weights, "empty", True):
        raise ValueError("executed_weights must be a non-empty DataFrame")
    if df is None or getattr(df, "empty", True):
        raise ValueError("result_df must be a non-empty DataFrame")
    cols = set(getattr(df, "columns", ()))
    required_cols = {"equity", "drawdown", "turnover", "return"}
    missing = sorted(required_cols - cols)
    if missing:
        raise ValueError(f"result_df missing required columns: {missing}")

    rets = np.asarray(df["return"], dtype=float)
    if not np.isfinite(rets).all():
        raise ValueError("return contains non-finite values")
    equity = np.cumprod(1.0 + rets)
    peak = np.maximum.accumulate(equity)
    drawdown = equity / peak - 1.0

    turnover_full = weights.diff().fillna(weights).abs().sum(axis=1)
    turnover = turnover_full.reindex(df.index)
    if turnover.isna().any():
        raise ValueError("executed_weights turnover cannot align to result_df.index")
    turnover_arr = np.asarray(turnover, dtype=float)
    if not np.isfinite(turnover_arr).all():
        raise ValueError("recomputed turnover non-finite")

    def _check(name: str, reported: Any, expected: np.ndarray) -> None:
        got = np.asarray(reported, dtype=float)
        if got.shape != expected.shape or not np.allclose(
            got, expected, rtol=rtol, atol=atol, equal_nan=False
        ):
            raise ValueError(f"{name} inconsistent with recomputation from returns/weights")

    _check("equity", df["equity"], equity)
    _check("drawdown", df["drawdown"], drawdown)
    _check("turnover", df["turnover"], turnover_arr)

    total_return = float(equity[-1] - 1.0)
    max_drawdown = float(abs(drawdown.min()))
    avg_daily_turnover = float(turnover_arr.mean())
    for name, value in (
        ("total_return", total_return),
        ("max_drawdown", max_drawdown),
        ("avg_daily_turnover", avg_daily_turnover),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} recomputed non-finite")
    return {
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "avg_daily_turnover": avg_daily_turnover,
    }


@dataclass(frozen=True)
class PoolMemberSeries:
    """Verified pool member Series for AnalyzeFacade (adapter-filled only).

    All identity/lineage fields must be copied from a validated
    ``FactorExecutionResult`` — never from caller-declared pool_refs alone.
    """

    ref_object_type: str
    ref_object_id: str
    ref_content_hash: str
    ref_namespace: str
    ref_schema_version: str
    values: Any  # pd.Series
    data_version: str
    split_id: str
    execution_id: str
    experiment_id: str
    callable_fingerprint: str
    values_artifact_kind: str
    values_artifact_id: str
    values_artifact_hash: str
    values_artifact_namespace: str
    values_artifact_schema: str

    def __post_init__(self) -> None:
        for name in (
            "ref_object_type",
            "ref_object_id",
            "ref_content_hash",
            "ref_namespace",
            "ref_schema_version",
            "data_version",
            "split_id",
            "execution_id",
            "experiment_id",
            "callable_fingerprint",
            "values_artifact_kind",
            "values_artifact_id",
            "values_artifact_hash",
            "values_artifact_namespace",
            "values_artifact_schema",
        ):
            _require_non_empty(name, getattr(self, name))


@dataclass(frozen=True)
class Finding:
    name: str
    severity: FindingSeverity
    passed: bool
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty("name", self.name)
        _require_non_empty("message", self.message)
        object.__setattr__(self, "severity", FindingSeverity(self.severity))
        object.__setattr__(self, "details", _freeze_mapping(dict(self.details)))


@dataclass(frozen=True)
class MetricResult:
    name: str
    value: float | int | str | bool | None
    unit: str
    sample_range: str
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("name", self.name)
        _require_non_empty("unit", self.unit)
        _require_non_empty("sample_range", self.sample_range)
        if self.unavailable_reason is not None:
            if self.value is not None:
                raise ValueError("unavailable metrics must set value=None")
            _require_non_empty("unavailable_reason", self.unavailable_reason)
            return
        if self.value is None:
            raise ValueError("available metrics require a value")
        if isinstance(self.value, float):
            if math.isnan(self.value) or math.isinf(self.value):
                raise ValueError("metric value must not be NaN/Inf; use unavailable")
            return
        if isinstance(self.value, bool):
            return
        if isinstance(self.value, int):
            return
        if isinstance(self.value, str):
            return
        raise TypeError(f"metric value must be a Python scalar, got {type(self.value)!r}")


@dataclass(frozen=True)
class UncertaintyResult:
    name: str
    method: str
    estimates: Mapping[str, Any]
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("name", self.name)
        _require_non_empty("method", self.method)
        object.__setattr__(self, "estimates", _freeze_mapping(dict(self.estimates)))


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    section: str
    summary: str
    content_hash: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty("evidence_id", self.evidence_id)
        _require_non_empty("section", self.section)
        _require_non_empty("summary", self.summary)
        _require_non_empty("content_hash", self.content_hash)
        object.__setattr__(self, "details", _freeze_mapping(dict(self.details)))


@dataclass(frozen=True)
class SectionResult:
    name: str
    status: SectionStatus
    findings: tuple[Finding, ...] = ()
    metrics: tuple[MetricResult, ...] = ()
    uncertainty: tuple[UncertaintyResult, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("name", self.name)
        if self.name not in SECTION_NAMES:
            raise ValueError(f"unknown analyze section: {self.name}")
        object.__setattr__(self, "status", SectionStatus(self.status))
        object.__setattr__(
            self,
            "findings",
            tuple(sorted(self.findings, key=lambda item: item.name)),
        )
        object.__setattr__(
            self,
            "metrics",
            tuple(sorted(self.metrics, key=lambda item: item.name)),
        )
        object.__setattr__(
            self,
            "uncertainty",
            tuple(sorted(self.uncertainty, key=lambda item: item.name)),
        )


@dataclass(frozen=True)
class ArtifactBundle:
    """In-memory detailed tables; callers persist via store namespaces."""

    tables: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        safe = {str(key): json_safe(value) for key, value in dict(self.tables).items()}
        object.__setattr__(self, "tables", _freeze_mapping(safe))


@dataclass(frozen=True)
class AnalyzeResult:
    operation: str
    engine_version: str
    schema_version: str
    input_hashes: Mapping[str, str]
    protocol: ProtocolSnapshot
    completion_status: CompletionStatus
    sections: tuple[SectionResult, ...]
    findings: tuple[Finding, ...]
    metrics: tuple[MetricResult, ...]
    uncertainty: tuple[UncertaintyResult, ...]
    evidence: tuple[EvidenceItem, ...]
    artifacts: ArtifactBundle
    hard_failed: bool

    def __post_init__(self) -> None:
        _require_non_empty("operation", self.operation)
        _require_non_empty("engine_version", self.engine_version)
        _require_non_empty("schema_version", self.schema_version)
        object.__setattr__(
            self, "completion_status", CompletionStatus(self.completion_status)
        )
        object.__setattr__(self, "input_hashes", _freeze_mapping(dict(self.input_hashes)))
        object.__setattr__(
            self,
            "sections",
            tuple(sorted(self.sections, key=lambda item: item.name)),
        )
        object.__setattr__(
            self,
            "findings",
            tuple(sorted(self.findings, key=lambda item: (item.name, item.message))),
        )
        object.__setattr__(
            self,
            "metrics",
            tuple(sorted(self.metrics, key=lambda item: item.name)),
        )
        object.__setattr__(
            self,
            "uncertainty",
            tuple(sorted(self.uncertainty, key=lambda item: item.name)),
        )
        object.__setattr__(
            self,
            "evidence",
            tuple(sorted(self.evidence, key=lambda item: item.evidence_id)),
        )
        # Strict JSON round-trip of public payload.
        canonical_json(self.to_public_dict())

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "engine_version": self.engine_version,
            "schema_version": self.schema_version,
            "input_hashes": dict(self.input_hashes),
            "protocol": canonical_value(self.protocol),
            "completion_status": self.completion_status.value,
            "hard_failed": self.hard_failed,
            "sections": [canonical_value(section) for section in self.sections],
            "findings": [canonical_value(item) for item in self.findings],
            "metrics": [canonical_value(item) for item in self.metrics],
            "uncertainty": [canonical_value(item) for item in self.uncertainty],
            "evidence": [canonical_value(item) for item in self.evidence],
            "artifacts": canonical_value(self.artifacts),
        }


def sorted_findings(items: Sequence[Finding]) -> tuple[Finding, ...]:
    return tuple(sorted(items, key=lambda item: (item.name, item.message)))


def has_hard_fail(findings: Sequence[Finding]) -> bool:
    return any(
        (not item.passed) and item.severity is FindingSeverity.HARD_FAIL for item in findings
    )


__all__ = [
    "ANALYZE_SCHEMA_VERSION",
    "ENGINE_VERSION",
    "SECTION_NAMES",
    "ALLOWED_DIRECTIONS",
    "ALLOWED_TIE_RULES",
    "ALLOWED_REBALANCES",
    "ALLOWED_RETURN_MODES",
    "ALLOWED_TRADE_AT",
    "AnalyzeResult",
    "ArtifactBundle",
    "CompletionStatus",
    "EvidenceItem",
    "Finding",
    "FindingSeverity",
    "FormalBacktestPair",
    "formal_pair_issuance_digest",
    "verified_backtest_metrics",
    "MetricResult",
    "PoolMemberSeries",
    "ProtocolSnapshot",
    "SectionResult",
    "SectionStatus",
    "SpecSnapshot",
    "UncertaintyResult",
    "canonical_json",
    "canonical_value",
    "content_hash",
    "has_hard_fail",
    "json_safe",
    "protocol_content_hash",
    "sorted_findings",
]
