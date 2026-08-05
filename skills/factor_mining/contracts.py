"""Versioned public contracts for AI factor-mining research.

Pure data objects only. No research algorithms, role enums, or platform SDKs.
"""

from __future__ import annotations

import hashlib
import json
import math
import types
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Union, get_args, get_origin, get_type_hints

SCHEMA_VERSION = "1.4.0"

class Severity(str, Enum):
    HARD_FAIL = "hard_fail"
    SOFT_FAIL = "soft_fail"
    WARNING = "warning"
    INFO = "info"

class SectionStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_RUN = "not_run"

class ReviewConclusion(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVISE = "revise"
    DEBATE = "debate"

class PoolDecisionKind(str, Enum):
    ACCEPT = "accept"
    WATCH = "watch"
    REJECT = "reject"

class ResearchDecisionKind(str, Enum):
    CONTINUE = "continue"
    REVISE = "revise"
    STOP = "stop"
    FREEZE = "freeze"
    REJECT = "reject"

class CandidateStatus(str, Enum):
    PROPOSED = "proposed"
    PREFLIGHT_PASSED = "preflight_passed"
    COMPUTED = "computed"
    EVALUATED = "evaluated"
    REVIEW_PENDING = "review_pending"
    DEBATING = "debating"
    SYNTHESIZING = "synthesizing"
    FREEZE_READY = "freeze_ready"
    REJECTED = "rejected"
    FROZEN = "frozen"
    OOS_TESTED = "oos_tested"
    PROMOTED = "promoted"

class ResearchRunStatus(str, Enum):
    """Research-run aggregate lifecycle (Phase 04 implements through FROZEN)."""

    BRIEFED = "briefed"
    ACTIVE = "active"
    FREEZE_PENDING = "freeze_pending"
    FROZEN = "frozen"
    OOS_AUTHORIZED = "oos_authorized"
    OOS_TESTED = "oos_tested"
    PROMOTED = "promoted"
    REJECTED = "rejected"

class TaskLifecycleStatus(str, Enum):
    """Task-lease aggregate lifecycle for Phase 04→05 handoff."""

    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

class TaskResultStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

class FormulaKind(str, Enum):
    FUNCTION_REF = "function_ref"
    EXPRESSION = "expression"

class FailureCode(str, Enum):
    INVALID_STATE = "INVALID_STATE"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    HASH_MISMATCH = "HASH_MISMATCH"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    FORBIDDEN_INPUT = "FORBIDDEN_INPUT"
    UNSUPPORTED_FORMULA = "UNSUPPORTED_FORMULA"
    FUNCTION_NOT_ALLOWED = "FUNCTION_NOT_ALLOWED"
    INVALID_PARAMETERS = "INVALID_PARAMETERS"
    INVALID_PANEL_TYPE = "INVALID_PANEL_TYPE"
    INVALID_INDEX_SCHEMA = "INVALID_INDEX_SCHEMA"
    TIME_CONVERSION_FAILED = "TIME_CONVERSION_FAILED"
    TIME_COLLISION = "TIME_COLLISION"
    DUPLICATE_LOGICAL_KEY = "DUPLICATE_LOGICAL_KEY"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    NON_NUMERIC_FIELD = "NON_NUMERIC_FIELD"
    FACTOR_RUNTIME_FAILED = "FACTOR_RUNTIME_FAILED"
    INVALID_OUTPUT_TYPE = "INVALID_OUTPUT_TYPE"
    OUTPUT_INDEX_MISMATCH = "OUTPUT_INDEX_MISMATCH"
    INVALID_OUTPUT_DTYPE = "INVALID_OUTPUT_DTYPE"
    ARTIFACT_PERSIST_FAILED = "ARTIFACT_PERSIST_FAILED"
    OOS_NOT_AUTHORIZED = "OOS_NOT_AUTHORIZED"
    OOS_ALREADY_CONSUMED = "OOS_ALREADY_CONSUMED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    UNKNOWN = "UNKNOWN"

EVALUATION_SECTIONS = (
    "data_quality",
    "formula_safety",
    "alignment",
    "predictive",
    "robustness",
    "trading",
    "pool_incremental",
)

def _require_non_empty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value

def _require_schema(schema_version: str) -> str:
    version = _require_non_empty("schema_version", schema_version)
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"schema_version must be {SCHEMA_VERSION!r}, got {version!r}"
        )
    return version

def _require_content_hash_hex(name: str, value: str) -> str:
    digest = _require_non_empty(name, value)
    if len(digest) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest):
        raise ValueError(f"{name} must be a 64-character hex digest")
    return digest

def _enum_or_value(enum_cls: type[Enum], value: Any) -> Any:
    if isinstance(value, enum_cls):
        return value
    return enum_cls(value)

def _freeze_value(value: Any) -> Any:
    """Deep-freeze mappings/lists for frozen dataclass fields."""
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

def _set_frozen_mapping(obj: Any, name: str, value: Mapping[Any, Any] | None) -> None:
    if value is None:
        object.__setattr__(obj, name, None)
        return
    object.__setattr__(obj, name, _freeze_mapping(value))

def canonical_value(value: Any) -> Any:
    """Normalize values for stable, strict-JSON serialization and hashing."""
    # Enum before str/int: str-Enum instances are also instances of str.
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
                raise TypeError(
                    f"canonical JSON requires str mapping keys, got {type(key)!r}"
                )
            normalized[key] = canonical_value(value[key])
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        # Avoid dataclasses.asdict: it deepcopies and cannot pickle MappingProxyType.
        return canonical_value(
            {item.name: getattr(value, item.name) for item in fields(value)}
        )
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"unsupported canonicalization type: {type(value)!r}")

def canonical_json(value: Any) -> str:
    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )

def content_hash(value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8"))
    return digest.hexdigest()

def to_plain_dict(value: Any) -> dict[str, Any]:
    plain = canonical_value(value)
    if not isinstance(plain, dict):
        raise TypeError("to_plain_dict expects a mapping-like dataclass")
    return plain

def _payload_without_hash(obj: Any) -> dict[str, Any]:
    payload = to_plain_dict(obj)
    payload.pop("content_hash", None)
    return payload

def _finalize_content_hash(obj: Any, label: str) -> None:
    """Compute hash when blank; reject a non-blank forged/mismatched hash."""
    expected = content_hash(_payload_without_hash(obj))
    current = obj.content_hash
    if not current:
        object.__setattr__(obj, "content_hash", expected)
        return
    if current != expected:
        raise ValueError(f"{label} content_hash mismatch: {current} != {expected}")

def _validate_content_hash(obj: Any, label: str) -> None:
    expected = content_hash(_payload_without_hash(obj))
    if obj.content_hash != expected:
        raise ValueError(f"{label} content_hash mismatch: {obj.content_hash} != {expected}")

def _require_ref_namespace(namespace: str, *refs: Any) -> None:
    """Require every provided ref to share the caller namespace."""
    _require_non_empty("namespace", namespace)
    for ref in refs:
        if ref is None:
            continue
        ref_ns = getattr(ref, "namespace", None)
        if ref_ns is None or ref_ns != namespace:
            raise ValueError(
                f"reference namespace mismatch: expected {namespace!r}, got {ref_ns!r}"
            )

def _require_provenance(provenance: Provenance, *, namespace: str | None = None) -> None:
    if provenance is None:  # type: ignore[comparison-overlap]
        raise ValueError("provenance is required")
    _require_non_empty("provenance.namespace", provenance.namespace)
    if namespace is not None and provenance.namespace != namespace:
        raise ValueError(
            f"provenance.namespace mismatch: expected {namespace!r}, "
            f"got {provenance.namespace!r}"
        )

@dataclass(frozen=True)
class ObjectRef:
    """Content-addressed reference to a versioned research object."""

    object_type: str
    object_id: str
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""
    namespace: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("object_type", self.object_type)
        _require_non_empty("object_id", self.object_id)
        _require_schema(self.schema_version)
        _require_content_hash_hex("content_hash", self.content_hash)
        _require_non_empty("namespace", self.namespace)

@dataclass(frozen=True)
class ArtifactRef:
    """Reference to a persisted artifact under an explicit namespace."""

    kind: str
    artifact_id: str
    namespace: str
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""
    uri: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("kind", self.kind)
        _require_non_empty("artifact_id", self.artifact_id)
        _require_non_empty("namespace", self.namespace)
        _require_schema(self.schema_version)
        _require_content_hash_hex("content_hash", self.content_hash)

@dataclass(frozen=True)
class EvidenceRef:
    """Reference to a deterministic fact or check outcome."""

    evidence_id: str
    source_report_id: str
    section: str
    namespace: str
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""
    artifact: ArtifactRef | None = None

    def __post_init__(self) -> None:
        _require_non_empty("evidence_id", self.evidence_id)
        _require_non_empty("source_report_id", self.source_report_id)
        _require_non_empty("section", self.section)
        _require_non_empty("namespace", self.namespace)
        _require_schema(self.schema_version)
        _require_content_hash_hex("content_hash", self.content_hash)
        if self.artifact is not None:
            _require_ref_namespace(self.namespace, self.artifact)

@dataclass(frozen=True)
class Provenance:
    """Traceability metadata shared by research objects."""

    producer: str
    data_version: str
    code_version: str
    experiment_version: str
    namespace: str
    input_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...] = ()
    created_at: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("producer", self.producer)
        _require_non_empty("data_version", self.data_version)
        _require_non_empty("code_version", self.code_version)
        _require_non_empty("experiment_version", self.experiment_version)
        _require_non_empty("namespace", self.namespace)
        object.__setattr__(self, "input_refs", tuple(self.input_refs))
        _require_ref_namespace(self.namespace, *self.input_refs)

@dataclass(frozen=True)
class FailureDetail:
    """Structured failure envelope used across ports and controllers."""

    code: FailureCode
    message: str
    severity: Severity = Severity.HARD_FAIL
    retryable: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _enum_or_value(FailureCode, self.code))
        object.__setattr__(self, "severity", _enum_or_value(Severity, self.severity))
        _require_non_empty("message", self.message)
        _set_frozen_mapping(self, "details", self.details)

@dataclass(frozen=True)
class SplitWindow:
    split_id: str
    start: str
    end: str
    sealed: bool = False

    def __post_init__(self) -> None:
        _require_non_empty("split_id", self.split_id)
        _require_non_empty("start", self.start)
        _require_non_empty("end", self.end)

@dataclass(frozen=True)
class CostConstraints:
    commission: float = 0.0
    slippage: float = 0.0
    borrow_cost: float = 0.0
    notes: str = ""

@dataclass(frozen=True)
class RiskConstraints:
    max_gross_exposure: float | None = None
    max_net_exposure: float | None = None
    max_weight: float | None = None
    max_turnover: float | None = None
    notes: str = ""

@dataclass(frozen=True)
class TradingConstraints:
    long_only: bool = True
    allow_short: bool = False
    min_history_bars: int = 0
    rebalance: str = "daily"
    execution_delay_bars: int = 1
    notes: str = ""

    def __post_init__(self) -> None:
        if self.min_history_bars < 0 or self.execution_delay_bars < 0:
            raise ValueError("history/delay bars must be non-negative")
        _require_non_empty("rebalance", self.rebalance)

@dataclass(frozen=True)
class RobustnessGrid:
    parameter_neighborhood: Mapping[str, tuple[Any, ...]] = field(
        default_factory=dict
    )
    time_subsamples: tuple[str, ...] = ()
    regime_slices: tuple[str, ...] = ()
    random_seed: int = 0

    def __post_init__(self) -> None:
        neighborhood = {
            key: tuple(value) if not isinstance(value, tuple) else value
            for key, value in dict(self.parameter_neighborhood).items()
        }
        _set_frozen_mapping(self, "parameter_neighborhood", neighborhood)
        object.__setattr__(self, "time_subsamples", tuple(self.time_subsamples))
        object.__setattr__(self, "regime_slices", tuple(self.regime_slices))

@dataclass(frozen=True)
class ResearchBudget:
    max_candidates: int
    max_experiments: int
    max_revisions: int
    max_debate_rounds: int

    def __post_init__(self) -> None:
        for name in (
            "max_candidates",
            "max_experiments",
            "max_revisions",
            "max_debate_rounds",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative int")

@dataclass(frozen=True)
class AcceptanceCriteria:
    min_rank_ic_ir: float | None = None
    min_coverage: float | None = None
    max_turnover: float | None = None
    require_pool_incremental: bool = True
    notes: str = ""

@dataclass(frozen=True)
class ResearchBrief:
    """Immutable research boundary for one mining run."""

    brief_id: str
    market: str
    asset_class: str
    universe: tuple[str, ...]
    frequency: str
    allowed_fields: tuple[str, ...]
    symbol_level: str
    datetime_level: str | None
    timezone: str
    adjustment: str
    data_version: str
    train: SplitWindow
    validation: SplitWindow
    sealed: SplitWindow
    horizon_bars: int
    rebalance: str
    cost: CostConstraints
    risk: RiskConstraints
    trading: TradingConstraints
    robustness: RobustnessGrid
    multiple_testing_budget: int
    budget: ResearchBudget
    acceptance: AcceptanceCriteria
    freeze_criteria: AcceptanceCriteria
    oos_criteria: AcceptanceCriteria
    provenance: Provenance
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("brief_id", self.brief_id)
        _require_non_empty("market", self.market)
        _require_non_empty("asset_class", self.asset_class)
        _require_non_empty("data_version", self.data_version)
        _require_schema(self.schema_version)
        _require_provenance(self.provenance)
        if self.data_version != self.provenance.data_version:
            raise ValueError("ResearchBrief.data_version must match provenance.data_version")
        if self.datetime_level is not None:
            _require_non_empty("datetime_level", self.datetime_level)
        if not self.universe:
            raise ValueError("universe must be an explicit non-empty snapshot")
        if len(set(self.universe)) != len(self.universe):
            raise ValueError("universe symbols must be unique")
        if not self.allowed_fields:
            raise ValueError("allowed_fields must be non-empty")
        if self.horizon_bars <= 0:
            raise ValueError("horizon_bars must be positive")
        _require_non_empty("rebalance", self.rebalance)
        if self.rebalance != self.trading.rebalance:
            raise ValueError(
                "ResearchBrief.rebalance must equal ResearchBrief.trading.rebalance"
            )
        if self.multiple_testing_budget < 0:
            raise ValueError("multiple_testing_budget must be non-negative")
        if not self.sealed.sealed:
            raise ValueError("sealed split must have sealed=True")
        if self.train.sealed or self.validation.sealed:
            raise ValueError("train/validation splits must not be sealed")
        object.__setattr__(self, "universe", tuple(self.universe))
        object.__setattr__(self, "allowed_fields", tuple(self.allowed_fields))
        _finalize_content_hash(self, "ResearchBrief")

    def payload_for_hash(self) -> dict[str, Any]:
        return _payload_without_hash(self)

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

    def validate_hash(self) -> None:
        _validate_content_hash(self, "ResearchBrief")

@dataclass(frozen=True)
class FunctionRef:
    """Versioned reference to an allowlisted compute function."""

    module: str
    name: str

    def __post_init__(self) -> None:
        _require_non_empty("module", self.module)
        _require_non_empty("name", self.name)
        if self.module.startswith("strategies"):
            raise ValueError("function refs must not point into strategies/")

@dataclass(frozen=True)
class StructuredFormula:
    """Constrained formula representation. Free-text and callables are forbidden."""

    kind: FormulaKind
    function_ref: FunctionRef | None = None
    expression: Mapping[str, Any] | None = None
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _enum_or_value(FormulaKind, self.kind))
        _set_frozen_mapping(self, "params", self.params)
        if self.expression is not None:
            _set_frozen_mapping(self, "expression", self.expression)
        try:
            canonical_json(self.params)
            if self.expression is not None:
                canonical_json(self.expression)
        except (TypeError, ValueError) as exc:
            raise ValueError("formula params/expression must be strict-JSON") from exc
        if self.kind is FormulaKind.FUNCTION_REF:
            if self.function_ref is None:
                raise ValueError("function_ref formula requires function_ref")
            if self.expression is not None:
                raise ValueError("function_ref formula must not set expression")
        elif self.kind is FormulaKind.EXPRESSION:
            if self.expression is None or not self.expression:
                raise ValueError("expression formula requires a non-empty mapping")
            if self.function_ref is not None:
                raise ValueError("expression formula must not set function_ref")
        else:  # pragma: no cover
            raise ValueError(f"unsupported formula kind: {self.kind}")

@dataclass(frozen=True)
class FactorSpec:
    """Structured, executable factor candidate definition."""

    factor_id: str
    revision: int
    brief_ref: ObjectRef
    family: str
    hypothesis: str
    expected_direction: str
    required_fields: tuple[str, ...]
    formula: StructuredFormula
    window: int
    lag: int
    warmup: int
    missing_policy: str
    availability_rule: str
    output_dtype: str
    index_restore_policy: str
    provenance: Provenance
    applicable_regimes: tuple[str, ...] = ()
    known_relations: tuple[str, ...] = ()
    falsification_tests: tuple[str, ...] = ()
    parent_ref: ObjectRef | None = None
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""
    status: CandidateStatus = CandidateStatus.PROPOSED

    def __post_init__(self) -> None:
        _require_non_empty("factor_id", self.factor_id)
        _require_non_empty("family", self.family)
        _require_non_empty("hypothesis", self.hypothesis)
        _require_non_empty("expected_direction", self.expected_direction)
        _require_schema(self.schema_version)
        _require_provenance(self.provenance, namespace=self.brief_ref.namespace)
        _require_ref_namespace(
            self.provenance.namespace,
            self.brief_ref,
            self.parent_ref,
        )
        if self.revision < 1:
            raise ValueError("revision must be >= 1")
        if not self.required_fields:
            raise ValueError("required_fields must be non-empty")
        for name in ("window", "lag", "warmup"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        object.__setattr__(self, "status", _enum_or_value(CandidateStatus, self.status))
        object.__setattr__(self, "required_fields", tuple(self.required_fields))
        object.__setattr__(self, "applicable_regimes", tuple(self.applicable_regimes))
        object.__setattr__(self, "known_relations", tuple(self.known_relations))
        object.__setattr__(
            self, "falsification_tests", tuple(self.falsification_tests)
        )
        _finalize_content_hash(self, "FactorSpec")

    def payload_for_hash(self) -> dict[str, Any]:
        return _payload_without_hash(self)

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

    def validate_hash(self) -> None:
        _validate_content_hash(self, "FactorSpec")

@dataclass(frozen=True)
class IndexSchema:
    """Index lineage describing original and working MultiIndex semantics."""

    names: tuple[str | None, ...]
    symbol_level: str
    datetime_level: str | None
    level_order: tuple[int, ...]
    timezone: str
    sorted: bool = False

    def __post_init__(self) -> None:
        _require_non_empty("timezone", self.timezone)
        names = tuple(self.names)
        order = tuple(self.level_order)
        object.__setattr__(self, "names", names)
        object.__setattr__(self, "level_order", order)
        if self.symbol_level != "symbol":
            raise ValueError("symbol_level must be 'symbol'")
        if len(names) != 2:
            raise ValueError("index schema must describe exactly two levels")
        if len(order) != 2 or tuple(sorted(order)) != (0, 1):
            raise ValueError("level_order must be a permutation of (0, 1)")
        symbol_pos, datetime_pos = order
        if names[symbol_pos] != "symbol":
            raise ValueError("level_order[0] must point to the symbol name 'symbol'")
        if self.datetime_level is None:
            if names[datetime_pos] is not None:
                raise ValueError(
                    "datetime_level None requires the datetime name slot to be None"
                )
        else:
            _require_non_empty("datetime_level", self.datetime_level)
            if names[datetime_pos] != self.datetime_level:
                raise ValueError(
                    "level_order[1] must point to the datetime_level name"
                )

@dataclass(frozen=True)
class FactorComputeRequest:
    """Execution request envelope. Phase 01 does not execute it."""

    request_id: str
    namespace: str
    experiment_id: str
    execution_id: str
    brief_ref: ObjectRef
    factor_ref: ObjectRef
    data_version: str
    split_id: str
    panel_artifact: ArtifactRef | None = None
    # Set only by the trusted sealed-OOS request factory.  It tells the
    # execution adapter to persist derived values under sealed metadata; it is
    # not a caller-selectable research workflow option.
    sealed_execution: bool = False
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "request_id",
            "namespace",
            "experiment_id",
            "execution_id",
            "data_version",
            "split_id",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.schema_version)
        _require_ref_namespace(
            self.namespace, self.brief_ref, self.factor_ref, self.panel_artifact
        )


@dataclass(frozen=True)
class FactorExecutionResult:
    """Execution result envelope with refs and lineage, without computed values.

    ``fingerprint`` is the envelope identity including brief/factor refs, artifact
    refs, ``data_version``, ``split_id``, ``callable_fingerprint``, and immutable
    ``values_content_hash`` / ``valid_mask_content_hash`` (canonical series payload
    digests). Failed executions set content hashes to ``None`` and must not carry
    values/mask refs.
    """

    request_id: str
    experiment_id: str
    execution_id: str
    brief_ref: ObjectRef
    factor_ref: ObjectRef
    values_ref: ArtifactRef | None
    valid_mask_ref: ArtifactRef | None
    index_schema: IndexSchema
    provenance: Provenance
    fingerprint: str
    callable_fingerprint: str
    data_version: str
    split_id: str
    values_content_hash: str | None
    valid_mask_content_hash: str | None
    warnings: tuple[str, ...] = ()
    failure: FailureDetail | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "request_id",
            "experiment_id",
            "execution_id",
            "fingerprint",
            "callable_fingerprint",
            "data_version",
            "split_id",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.schema_version)
        _require_provenance(self.provenance, namespace=self.factor_ref.namespace)
        if self.provenance.data_version != self.data_version:
            raise ValueError("data_version must equal provenance.data_version")
        if self.brief_ref.object_type != "ResearchBrief":
            raise ValueError("brief_ref.object_type must be ResearchBrief")
        if self.factor_ref.object_type != "FactorSpec":
            raise ValueError("factor_ref.object_type must be FactorSpec")
        _require_ref_namespace(
            self.provenance.namespace,
            self.brief_ref,
            self.factor_ref,
            self.values_ref,
            self.valid_mask_ref,
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))
        for warning in self.warnings:
            if str(warning).startswith("callable_fingerprint:"):
                raise ValueError(
                    "callable_fingerprint must be a first-class field, not a warning"
                )
        if self.failure is None:
            if self.values_ref is None or self.valid_mask_ref is None:
                raise ValueError("successful execution requires values and mask refs")
            if not self.values_content_hash or not self.valid_mask_content_hash:
                raise ValueError(
                    "successful execution requires values_content_hash and "
                    "valid_mask_content_hash"
                )
            _require_content_hash_hex("values_content_hash", self.values_content_hash)
            _require_content_hash_hex(
                "valid_mask_content_hash", self.valid_mask_content_hash
            )
        else:
            if self.values_ref is not None or self.valid_mask_ref is not None:
                raise ValueError("failed execution must not carry values/mask refs")
            if self.values_content_hash is not None or self.valid_mask_content_hash is not None:
                raise ValueError(
                    "failed execution must set values/mask content hashes to None"
                )

    @property
    def execution_content_hash(self) -> str:
        """Alias for the envelope identity hash stored in ``fingerprint``."""
        return self.fingerprint


@dataclass(frozen=True)
class TypedPoolMember:
    """Loader-returned pool member: real execution envelope + loaded values.

    Adapter validates ``execution`` against ``request.pool_refs`` (exact
    id/hash/namespace/schema) and lineage fields; Mapping[str, Series]
    self-attestation is not accepted.
    """

    execution: FactorExecutionResult
    values: Any  # pd.Series

    def __post_init__(self) -> None:
        if not isinstance(self.execution, FactorExecutionResult):
            raise TypeError("execution must be FactorExecutionResult")
        if self.execution.failure is not None:
            raise ValueError("pool member execution must be successful")
        if self.execution.values_ref is None:
            raise ValueError("pool member requires values_ref")


@dataclass(frozen=True)
class MetricFact:
    """Deterministic metric fact. Agent narrative belongs in review/decision objects."""

    name: str
    value: float | int | str | bool | None
    unit: str
    sample_range: str
    engine_version: str
    data_version: str
    evidence: EvidenceRef
    artifact: ArtifactRef | None = None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("name", self.name)
        _require_non_empty("unit", self.unit)
        _require_non_empty("sample_range", self.sample_range)
        _require_non_empty("engine_version", self.engine_version)
        _require_non_empty("data_version", self.data_version)
        _require_ref_namespace(self.evidence.namespace, self.evidence, self.artifact)

@dataclass(frozen=True)
class RuleCheck:
    """Deterministic rule outcome with severity and stable failure code."""

    name: str
    passed: bool
    severity: Severity
    code: FailureCode | None
    message: str
    evidence: EvidenceRef | None = None

    def __post_init__(self) -> None:
        _require_non_empty("name", self.name)
        _require_non_empty("message", self.message)
        object.__setattr__(self, "severity", _enum_or_value(Severity, self.severity))
        if self.code is not None:
            object.__setattr__(self, "code", _enum_or_value(FailureCode, self.code))
        if not self.passed and self.severity is Severity.HARD_FAIL and self.code is None:
            raise ValueError("hard-fail rule checks require a failure code")
        if self.evidence is not None:
            _require_ref_namespace(self.evidence.namespace, self.evidence)

@dataclass(frozen=True)
class EvaluationSection:
    name: str
    status: SectionStatus
    facts: tuple[MetricFact, ...] = ()
    checks: tuple[RuleCheck, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("name", self.name)
        if self.name not in EVALUATION_SECTIONS:
            raise ValueError(f"unknown evaluation section: {self.name}")
        object.__setattr__(self, "status", _enum_or_value(SectionStatus, self.status))
        object.__setattr__(self, "facts", tuple(self.facts))
        object.__setattr__(self, "checks", tuple(self.checks))

@dataclass(frozen=True)
class EvaluationRequest:
    request_id: str
    namespace: str
    brief_ref: ObjectRef
    factor_ref: ObjectRef
    execution_ref: ObjectRef | None
    protocol_id: str
    data_version: str
    split_id: str
    pool_refs: tuple[ObjectRef, ...] = ()
    include_sections: tuple[str, ...] = EVALUATION_SECTIONS
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "request_id",
            "namespace",
            "protocol_id",
            "data_version",
            "split_id",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.schema_version)
        object.__setattr__(self, "pool_refs", tuple(self.pool_refs))
        object.__setattr__(self, "include_sections", tuple(self.include_sections))
        unknown = set(self.include_sections) - set(EVALUATION_SECTIONS)
        if unknown:
            raise ValueError(f"unknown evaluation sections: {sorted(unknown)}")
        _require_ref_namespace(
            self.namespace,
            self.brief_ref,
            self.factor_ref,
            self.execution_ref,
            *self.pool_refs,
        )

@dataclass(frozen=True)
class EvaluationReport:
    """Deterministic facts/checks/failure only. Agent decisions live elsewhere.

    Schema 1.4.0 requires exact request lineage fields so controllers can
    fail-closed on port-output binding without permissive getattr checks.
    """

    report_id: str
    request_id: str
    brief_ref: ObjectRef
    factor_ref: ObjectRef
    execution_ref: ObjectRef | None
    protocol_id: str
    data_version: str
    split_id: str
    pool_refs: tuple[ObjectRef, ...]
    sections: tuple[EvaluationSection, ...]
    provenance: Provenance
    engine_version: str
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""
    failure: FailureDetail | None = None

    def __post_init__(self) -> None:
        _require_non_empty("report_id", self.report_id)
        _require_non_empty("request_id", self.request_id)
        _require_non_empty("protocol_id", self.protocol_id)
        _require_non_empty("data_version", self.data_version)
        _require_non_empty("split_id", self.split_id)
        _require_non_empty("engine_version", self.engine_version)
        _require_schema(self.schema_version)
        _require_provenance(self.provenance, namespace=self.factor_ref.namespace)
        if self.brief_ref.object_type != "ResearchBrief":
            raise ValueError("brief_ref.object_type must be ResearchBrief")
        if self.factor_ref.object_type != "FactorSpec":
            raise ValueError("factor_ref.object_type must be FactorSpec")
        if self.provenance.data_version != self.data_version:
            raise ValueError("data_version must equal provenance.data_version")
        object.__setattr__(self, "pool_refs", tuple(self.pool_refs))
        evidence_refs = []
        for section in self.sections:
            for fact in section.facts:
                evidence_refs.append(fact.evidence)
                if fact.artifact is not None:
                    evidence_refs.append(fact.artifact)
            for check in section.checks:
                if check.evidence is not None:
                    evidence_refs.append(check.evidence)
        _require_ref_namespace(
            self.provenance.namespace,
            self.brief_ref,
            self.factor_ref,
            self.execution_ref,
            *self.pool_refs,
            *evidence_refs,
        )
        object.__setattr__(self, "sections", tuple(self.sections))
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise ValueError("evaluation sections must be unique")
        _finalize_content_hash(self, "EvaluationReport")

    def payload_for_hash(self) -> dict[str, Any]:
        return _payload_without_hash(self)

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

    def validate_hash(self) -> None:
        _validate_content_hash(self, "EvaluationReport")

@dataclass(frozen=True)
class ReviewIssue:
    code: str
    severity: Severity
    message: str
    evidence_refs: tuple[EvidenceRef, ...] = ()
    falsification_test: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("code", self.code)
        _require_non_empty("message", self.message)
        object.__setattr__(self, "severity", _enum_or_value(Severity, self.severity))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if self.evidence_refs:
            _require_ref_namespace(self.evidence_refs[0].namespace, *self.evidence_refs)

@dataclass(frozen=True)
class ReviewReport:
    report_id: str
    role_id: str
    factor_ref: ObjectRef
    evaluation_ref: ObjectRef
    conclusion: ReviewConclusion
    issues: tuple[ReviewIssue, ...]
    allow_revision: bool
    requires_full_rerun: bool
    provenance: Provenance
    rationale: str = ""
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("report_id", self.report_id)
        _require_non_empty("role_id", self.role_id)
        _require_schema(self.schema_version)
        _require_provenance(self.provenance, namespace=self.factor_ref.namespace)
        issue_evidence = tuple(
            ref for issue in self.issues for ref in issue.evidence_refs
        )
        _require_ref_namespace(
            self.provenance.namespace,
            self.factor_ref,
            self.evaluation_ref,
            *issue_evidence,
        )
        object.__setattr__(
            self, "conclusion", _enum_or_value(ReviewConclusion, self.conclusion)
        )
        object.__setattr__(self, "issues", tuple(self.issues))
        _finalize_content_hash(self, "ReviewReport")

    def payload_for_hash(self) -> dict[str, Any]:
        return _payload_without_hash(self)

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

    def validate_hash(self) -> None:
        _validate_content_hash(self, "ReviewReport")

@dataclass(frozen=True)
class PoolDecision:
    decision_id: str
    factor_ref: ObjectRef
    decision: PoolDecisionKind
    incremental_evidence: tuple[EvidenceRef, ...]
    residual_risks: tuple[str, ...]
    role_id: str
    provenance: Provenance
    rationale: str = ""
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("decision_id", self.decision_id)
        _require_non_empty("role_id", self.role_id)
        _require_schema(self.schema_version)
        _require_provenance(self.provenance, namespace=self.factor_ref.namespace)
        _require_ref_namespace(
            self.provenance.namespace,
            self.factor_ref,
            *self.incremental_evidence,
        )
        object.__setattr__(
            self, "decision", _enum_or_value(PoolDecisionKind, self.decision)
        )
        object.__setattr__(
            self, "incremental_evidence", tuple(self.incremental_evidence)
        )
        object.__setattr__(self, "residual_risks", tuple(self.residual_risks))
        _finalize_content_hash(self, "PoolDecision")

    def payload_for_hash(self) -> dict[str, Any]:
        return _payload_without_hash(self)

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

    def validate_hash(self) -> None:
        _validate_content_hash(self, "PoolDecision")

@dataclass(frozen=True)
class ControllerEvent:
    """Append-only audit event; hash-chained by sequence + prev_hash."""

    sequence: int
    prev_hash: str
    event_hash: str
    run_id: str
    aggregate_kind: str
    aggregate_id: str
    command: str
    idempotency_key: str
    actor_id: str
    role_id: str
    from_status: str
    to_status: str
    input_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...] = ()
    output_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...] = ()
    budget_delta: Mapping[str, int] = field(default_factory=dict)
    parent_task_id: str | None = None
    result_status: str = "ok"
    failure: FailureDetail | None = None
    state_after_digest: str = ""
    outputs: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "aggregate_kind",
            "aggregate_id",
            "command",
            "idempotency_key",
            "actor_id",
            "role_id",
            "from_status",
            "to_status",
            "result_status",
            "state_after_digest",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.schema_version)
        if self.sequence < 1:
            raise ValueError("sequence must be >= 1")
        if self.prev_hash != "0" * 64:
            _require_content_hash_hex("prev_hash", self.prev_hash)
        _require_content_hash_hex("event_hash", self.event_hash)
        _require_content_hash_hex("state_after_digest", self.state_after_digest)
        object.__setattr__(self, "input_refs", tuple(self.input_refs))
        object.__setattr__(self, "output_refs", tuple(self.output_refs))
        _set_frozen_mapping(self, "budget_delta", self.budget_delta)
        _set_frozen_mapping(self, "outputs", self.outputs)

    def payload_for_hash(self) -> dict[str, Any]:
        """Canonical hash payload — matches persisted event body (no event_hash)."""
        failure_plain = to_plain_dict(self.failure) if self.failure is not None else None
        return {
            "sequence": int(self.sequence),
            "prev_hash": self.prev_hash,
            "run_id": self.run_id,
            "aggregate_kind": self.aggregate_kind,
            "aggregate_id": self.aggregate_id,
            "command": self.command,
            "idempotency_key": self.idempotency_key,
            "actor_id": self.actor_id,
            "role_id": self.role_id,
            "parent_task_id": self.parent_task_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "input_refs": [to_plain_dict(ref) for ref in self.input_refs],
            "output_refs": [to_plain_dict(ref) for ref in self.output_refs],
            "budget_delta": dict(self.budget_delta),
            "result_status": self.result_status,
            "failure": failure_plain,
            "state_after_digest": self.state_after_digest,
            "outputs": dict(self.outputs),
            "schema_version": self.schema_version,
        }

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

@dataclass(frozen=True)
class FailureKnowledgeEntry:
    """Append-only failure knowledge for authorized non-sealed splits only."""

    knowledge_id: str
    run_id: str
    family_fingerprint: str
    formula_fingerprint: str
    failure_type: str
    disposition: str
    split_id: str
    repairable: bool
    evidence_refs: tuple[EvidenceRef, ...] = ()
    factor_ref: ObjectRef | None = None
    sealed: bool = False
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""

    def __post_init__(self) -> None:
        for name in (
            "knowledge_id",
            "run_id",
            "family_fingerprint",
            "formula_fingerprint",
            "failure_type",
            "disposition",
            "split_id",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.schema_version)
        if self.sealed:
            raise ValueError("failure knowledge must not record sealed facts")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if self.factor_ref is not None:
            _require_ref_namespace(self.factor_ref.namespace, self.factor_ref, *self.evidence_refs)
        _finalize_content_hash(self, "FailureKnowledgeEntry")

    def payload_for_hash(self) -> dict[str, Any]:
        return _payload_without_hash(self)

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

    def validate_hash(self) -> None:
        _validate_content_hash(self, "FailureKnowledgeEntry")

@dataclass(frozen=True)
class TaskLease:
    """Budget lease granting a role a finite amount of work."""

    lease_id: str
    run_id: str
    task_id: str
    role_id: str
    candidates_remaining: int
    experiments_remaining: int
    revisions_remaining: int
    debate_rounds_remaining: int
    expires_at: str = ""

    def __post_init__(self) -> None:
        for name in ("lease_id", "run_id", "task_id", "role_id"):
            _require_non_empty(name, getattr(self, name))
        for name in (
            "candidates_remaining",
            "experiments_remaining",
            "revisions_remaining",
            "debate_rounds_remaining",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")

@dataclass(frozen=True)
class AgentTaskView:
    """Minimal immutable context for one role task.

    ``role_id`` is a plain string. ``candidate_ref`` is optional for run-level
    tasks; role/task-specific requiredness is validated later by the Controller
    against ``SKILL.md``, not in this Phase 01 contract module.
    """

    task_id: str
    run_id: str
    parent_task_id: str | None
    role_id: str
    goal: str
    input_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...]
    input_hashes: Mapping[str, str]
    visibility: tuple[str, ...]
    lease: TaskLease
    attempt: int
    debate_round: int
    expected_output_type: str
    candidate_ref: ObjectRef | None = None
    expected_schema_version: str = SCHEMA_VERSION
    forbidden_actions: tuple[str, ...] = ()
    must_check: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("task_id", "run_id", "role_id", "goal", "expected_output_type"):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.expected_schema_version)
        if self.attempt < 1:
            raise ValueError("attempt must be >= 1")
        if self.debate_round < 0:
            raise ValueError("debate_round must be non-negative")
        if self.lease.run_id != self.run_id:
            raise ValueError("task lease run_id must match task run_id")
        if self.lease.task_id != self.task_id:
            raise ValueError("task lease task_id must match task_id")
        if self.lease.role_id != self.role_id:
            raise ValueError("task lease role_id must match task role_id")
        object.__setattr__(self, "input_refs", tuple(self.input_refs))
        expected_hashes = {
            f"ref:{index}": getattr(ref, "content_hash", "")
            or content_hash(to_plain_dict(ref))
            for index, ref in enumerate(self.input_refs)
        }
        if dict(self.input_hashes) != expected_hashes:
            raise ValueError("input_hashes must exact-match input_refs")
        if self.candidate_ref is not None:
            _require_ref_namespace(
                self.candidate_ref.namespace,
                self.candidate_ref,
                *self.input_refs,
            )
        elif self.input_refs:
            _require_ref_namespace(self.input_refs[0].namespace, *self.input_refs)
        _set_frozen_mapping(self, "input_hashes", self.input_hashes)
        object.__setattr__(self, "visibility", tuple(self.visibility))
        object.__setattr__(self, "forbidden_actions", tuple(self.forbidden_actions))
        object.__setattr__(self, "must_check", tuple(self.must_check))
        object.__setattr__(self, "stop_conditions", tuple(self.stop_conditions))

@dataclass(frozen=True)
class AgentTaskResult:
    task_id: str
    run_id: str
    role_id: str
    status: TaskResultStatus
    output_type: str
    output_ref: ObjectRef | None
    handoff_to: str
    evidence_refs: tuple[EvidenceRef, ...] = ()
    artifact_refs: tuple[ArtifactRef, ...] = ()
    budget_consumed: Mapping[str, int] = field(default_factory=dict)
    failure: FailureDetail | None = None
    parent_task_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("task_id", "run_id", "role_id", "output_type", "handoff_to"):
            _require_non_empty(name, getattr(self, name))
        object.__setattr__(self, "status", _enum_or_value(TaskResultStatus, self.status))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "artifact_refs", tuple(self.artifact_refs))
        _set_frozen_mapping(self, "budget_consumed", self.budget_consumed)
        if self.parent_task_id is not None:
            _require_non_empty("parent_task_id", self.parent_task_id)
        for key, value in self.budget_consumed.items():
            _require_non_empty("budget_consumed key", key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("budget_consumed values must be nonnegative ints")
        if self.status is TaskResultStatus.RUNNING:
            raise ValueError("AgentTaskResult rejects RUNNING; it is a result envelope")
        if self.status is TaskResultStatus.SUCCEEDED:
            if self.output_ref is None:
                raise ValueError("successful task results require output_ref")
            if not isinstance(self.output_ref, ObjectRef):
                raise ValueError("successful task results require one ObjectRef output_ref")
            if self.failure is not None:
                raise ValueError("successful task results must not include failure")
            _require_ref_namespace(
                self.output_ref.namespace,
                self.output_ref,
                *self.evidence_refs,
                *self.artifact_refs,
            )
        else:
            if self.failure is None:
                raise ValueError("non-success task results require failure detail")
            if self.output_ref is not None:
                raise ValueError("non-success task results must not include output_ref")


def _agent_task_view_authorized_namespace(view: AgentTaskView) -> str:
    refs = tuple(ref for ref in (view.candidate_ref, *view.input_refs) if ref is not None)
    namespaces = {getattr(ref, "namespace", None) for ref in refs}
    if len(namespaces) != 1 or None in namespaces:
        raise ValueError("task view has no unique authorized namespace")
    return next(iter(namespaces))


def validate_agent_task_handoff(
    view: AgentTaskView, result: AgentTaskResult
) -> None:
    """Bind one returned result to the immutable Controller-issued task view.

    This function intentionally does not select roles or invoke an agent runtime.
    It checks only platform-neutral envelope identity and lease limits; trusted
    object existence/content verification remains the Controller/store boundary.
    """
    for identity_field in ("task_id", "run_id", "role_id", "parent_task_id"):
        if getattr(result, identity_field) != getattr(view, identity_field):
            raise ValueError(f"task result {identity_field} must match task view")
    if result.output_type != view.expected_output_type:
        raise ValueError("task result output_type must match task expected_output_type")
    if (
        result.status is TaskResultStatus.SUCCEEDED
        and result.output_ref is not None
        and result.output_ref.object_type != view.expected_output_type
    ):
        raise ValueError("task result output_ref.object_type must match expected_output_type")
    authorized_namespace = _agent_task_view_authorized_namespace(view)
    returned_refs = (*result.evidence_refs, *result.artifact_refs)
    if result.status is TaskResultStatus.SUCCEEDED and result.output_ref is not None:
        returned_refs = (result.output_ref, *returned_refs)
    if any(getattr(ref, "namespace", None) != authorized_namespace for ref in returned_refs):
        raise ValueError("task result refs must match task view authorized namespace")
    remaining = {
        "candidates": view.lease.candidates_remaining,
        "experiments": view.lease.experiments_remaining,
        "revisions": view.lease.revisions_remaining,
        "debate_rounds": view.lease.debate_rounds_remaining,
    }
    for key, consumed in result.budget_consumed.items():
        if key not in remaining:
            raise ValueError("task result budget_consumed has unknown budget key")
        if consumed > remaining[key]:
            raise ValueError("task result budget_consumed exceeds task lease")

@dataclass(frozen=True)
class ResearchDecision:
    decision_id: str
    run_id: str
    role_id: str
    kind: ResearchDecisionKind
    candidate_refs: tuple[ObjectRef, ...]
    task_ids: tuple[str, ...]
    rationale: str
    provenance: Provenance
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""

    def __post_init__(self) -> None:
        for name in ("decision_id", "run_id", "role_id", "rationale"):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.schema_version)
        object.__setattr__(
            self, "kind", _enum_or_value(ResearchDecisionKind, self.kind)
        )
        object.__setattr__(self, "candidate_refs", tuple(self.candidate_refs))
        object.__setattr__(self, "task_ids", tuple(self.task_ids))
        _require_provenance(self.provenance)
        _require_ref_namespace(self.provenance.namespace, *self.candidate_refs)
        _finalize_content_hash(self, "ResearchDecision")

    def payload_for_hash(self) -> dict[str, Any]:
        return _payload_without_hash(self)

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

    def validate_hash(self) -> None:
        _validate_content_hash(self, "ResearchDecision")

@dataclass(frozen=True)
class FreezeManifest:
    """Frozen candidate package ready for one-shot sealed OOS.

    ``oos_thresholds`` maps frozen OOS metric names to float pass thresholds
    (not content-addressed refs).
    """

    manifest_id: str
    run_id: str
    brief_ref: ObjectRef
    factor_ref: ObjectRef
    universe: tuple[str, ...]
    data_version: str
    split_refs: Mapping[str, str]
    compute_engine_version: str
    analyze_engine_version: str
    evaluation_protocol_id: str
    direction: str
    params: Mapping[str, Any]
    missing_policy: str
    adjustment_policy: str
    outlier_policy: str
    neutralization_policy: str
    holding_horizon_bars: int
    rebalance: str
    cost: CostConstraints
    pool_baseline_refs: tuple[ObjectRef, ...]
    preflight_ref: ObjectRef
    execution_ref: ObjectRef
    evaluation_ref: ObjectRef
    compare_ref: ObjectRef
    review_refs: tuple[ObjectRef, ...]
    pool_decision_ref: ObjectRef
    approval_ref: ArtifactRef
    oos_thresholds: Mapping[str, float]
    oos_metric_selectors: Mapping[str, Mapping[str, str]]
    provenance: Provenance
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""

    def __post_init__(self) -> None:
        for name in (
            "manifest_id",
            "run_id",
            "data_version",
            "compute_engine_version",
            "analyze_engine_version",
            "evaluation_protocol_id",
            "direction",
            "missing_policy",
            "adjustment_policy",
            "outlier_policy",
            "neutralization_policy",
            "rebalance",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.schema_version)
        _require_provenance(self.provenance, namespace=self.brief_ref.namespace)
        if not self.universe:
            raise ValueError("freeze manifest universe must be non-empty")
        if self.holding_horizon_bars <= 0:
            raise ValueError("holding_horizon_bars must be positive")
        if not self.oos_thresholds:
            raise ValueError("oos_thresholds must be a non-empty mapping")
        if not self.review_refs:
            raise ValueError("review_refs must be non-empty")
        normalized_thresholds: dict[str, float] = {}
        for key, value in dict(self.oos_thresholds).items():
            if not isinstance(key, str) or not key:
                raise ValueError("oos_thresholds keys must be non-empty str")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    "oos_thresholds values must be float (int coerced); "
                    "bool/str/ref rejected"
                )
            normalized_thresholds[key] = float(value)
        raw_selectors = dict(self.oos_metric_selectors)
        if set(raw_selectors) != set(normalized_thresholds):
            raise ValueError(
                "oos_metric_selectors keys must exact-match oos_thresholds keys"
            )
        normalized_selectors: dict[str, dict[str, str]] = {}
        for key, selector in raw_selectors.items():
            if not isinstance(selector, Mapping):
                raise TypeError("oos_metric_selectors values must be mappings")
            normalized = dict(selector)
            if set(normalized) != {"fact_name", "operator"}:
                raise ValueError(
                    "each oos_metric_selector requires only fact_name and operator"
                )
            fact_name = normalized["fact_name"]
            operator = normalized["operator"]
            if not isinstance(fact_name, str) or not fact_name:
                raise ValueError("oos_metric_selector.fact_name must be non-empty str")
            if operator not in {"gte", "lte"}:
                raise ValueError("oos_metric_selector.operator must be gte or lte")
            normalized_selectors[key] = {
                "fact_name": fact_name,
                "operator": operator,
            }
        for label, ref in (
            ("brief_ref", self.brief_ref),
            ("factor_ref", self.factor_ref),
            ("preflight_ref", self.preflight_ref),
            ("execution_ref", self.execution_ref),
            ("evaluation_ref", self.evaluation_ref),
            ("compare_ref", self.compare_ref),
            ("pool_decision_ref", self.pool_decision_ref),
        ):
            if not isinstance(ref, ObjectRef):
                raise TypeError(f"{label} must be ObjectRef")
        if self.preflight_ref.object_type != "EvaluationReport":
            raise ValueError("preflight_ref.object_type must be EvaluationReport")
        if self.execution_ref.object_type != "FactorExecutionResult":
            raise ValueError("execution_ref.object_type must be FactorExecutionResult")
        if self.evaluation_ref.object_type != "EvaluationReport":
            raise ValueError("evaluation_ref.object_type must be EvaluationReport")
        if self.compare_ref.object_type != "EvaluationReport":
            raise ValueError("compare_ref.object_type must be EvaluationReport")
        if self.pool_decision_ref.object_type != "PoolDecision":
            raise ValueError("pool_decision_ref.object_type must be PoolDecision")
        for review in self.review_refs:
            if review.object_type != "ReviewReport":
                raise ValueError("review_refs must be ReviewReport ObjectRefs")
        _require_ref_namespace(
            self.provenance.namespace,
            self.brief_ref,
            self.factor_ref,
            self.preflight_ref,
            self.execution_ref,
            self.evaluation_ref,
            self.compare_ref,
            self.pool_decision_ref,
            self.approval_ref,
            *self.pool_baseline_refs,
            *self.review_refs,
        )
        object.__setattr__(self, "universe", tuple(self.universe))
        _set_frozen_mapping(self, "split_refs", self.split_refs)
        _set_frozen_mapping(self, "params", self.params)
        object.__setattr__(self, "pool_baseline_refs", tuple(self.pool_baseline_refs))
        object.__setattr__(self, "review_refs", tuple(self.review_refs))
        _set_frozen_mapping(self, "oos_thresholds", normalized_thresholds)
        _set_frozen_mapping(self, "oos_metric_selectors", normalized_selectors)
        _finalize_content_hash(self, "FreezeManifest")

    def payload_for_hash(self) -> dict[str, Any]:
        return _payload_without_hash(self)

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

    def validate_hash(self) -> None:
        _validate_content_hash(self, "FreezeManifest")

@dataclass(frozen=True)
class OOSAuthorization:
    authorization_id: str
    run_id: str
    candidate_id: str
    manifest_ref: ObjectRef
    sealed_split_id: str
    one_shot_key: str
    issued_at: str
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""

    def __post_init__(self) -> None:
        for name in (
            "authorization_id",
            "run_id",
            "candidate_id",
            "sealed_split_id",
            "one_shot_key",
            "issued_at",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.schema_version)
        if self.manifest_ref.object_type != "FreezeManifest":
            raise ValueError("manifest_ref.object_type must be FreezeManifest")
        _finalize_content_hash(self, "OOSAuthorization")

    def payload_for_hash(self) -> dict[str, Any]:
        return _payload_without_hash(self)

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

    def validate_hash(self) -> None:
        _validate_content_hash(self, "OOSAuthorization")

@dataclass(frozen=True)
class OOSAttempt:
    """One-shot sealed OOS claim ledger entry.

    Defaults to RUNNING after claim/start. Terminal statuses require finished_at.
    """

    attempt_id: str
    authorization_id: str
    run_id: str
    candidate_id: str
    manifest_ref: ObjectRef
    sealed_split_id: str
    one_shot_key: str
    started_at: str
    finished_at: str = ""
    status: TaskResultStatus = TaskResultStatus.RUNNING
    failure: FailureDetail | None = None
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""

    def __post_init__(self) -> None:
        for name in (
            "attempt_id",
            "authorization_id",
            "run_id",
            "candidate_id",
            "sealed_split_id",
            "one_shot_key",
            "started_at",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.schema_version)
        if self.manifest_ref.object_type != "FreezeManifest":
            raise ValueError("manifest_ref.object_type must be FreezeManifest")
        object.__setattr__(self, "status", _enum_or_value(TaskResultStatus, self.status))
        if self.status is TaskResultStatus.RUNNING:
            if self.finished_at:
                raise ValueError("RUNNING OOSAttempt must have empty finished_at")
            if self.failure is not None:
                raise ValueError("RUNNING OOSAttempt must not include failure")
        elif self.status is TaskResultStatus.SUCCEEDED:
            _require_non_empty("finished_at", self.finished_at)
            if self.failure is not None:
                raise ValueError("successful OOSAttempt must not include failure")
        else:
            _require_non_empty("finished_at", self.finished_at)
            if self.failure is None:
                raise ValueError("non-success OOSAttempt requires failure detail")
        _finalize_content_hash(self, "OOSAttempt")

    def payload_for_hash(self) -> dict[str, Any]:
        return _payload_without_hash(self)

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

    def validate_hash(self) -> None:
        _validate_content_hash(self, "OOSAttempt")

@dataclass(frozen=True)
class OOSResult:
    result_id: str
    attempt_id: str
    authorization_id: str
    run_id: str
    candidate_id: str
    manifest_ref: ObjectRef
    sealed_split_id: str
    evaluation_ref: ObjectRef
    passed: bool
    evidence_refs: tuple[EvidenceRef, ...]
    provenance: Provenance
    artifact_refs: tuple[ArtifactRef, ...] = ()
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""

    def __post_init__(self) -> None:
        for name in (
            "result_id",
            "attempt_id",
            "authorization_id",
            "run_id",
            "candidate_id",
            "sealed_split_id",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.schema_version)
        if self.manifest_ref.object_type != "FreezeManifest":
            raise ValueError("manifest_ref.object_type must be FreezeManifest")
        if self.evaluation_ref.object_type != "EvaluationReport":
            raise ValueError("evaluation_ref.object_type must be EvaluationReport")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "artifact_refs", tuple(self.artifact_refs))
        _require_provenance(self.provenance, namespace=self.manifest_ref.namespace)
        _require_ref_namespace(
            self.provenance.namespace,
            self.manifest_ref,
            self.evaluation_ref,
            *self.evidence_refs,
            *self.artifact_refs,
        )
        _finalize_content_hash(self, "OOSResult")

    def payload_for_hash(self) -> dict[str, Any]:
        return _payload_without_hash(self)

    def compute_hash(self) -> str:
        return content_hash(self.payload_for_hash())

    def validate_hash(self) -> None:
        _validate_content_hash(self, "OOSResult")

@dataclass(frozen=True)
class ReportRequest:
    request_id: str
    namespace: str
    run_id: str
    title: str
    object_refs: tuple[ObjectRef, ...]
    evidence_refs: tuple[EvidenceRef, ...] = ()
    artifact_refs: tuple[ArtifactRef, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("request_id", "namespace", "run_id", "title"):
            _require_non_empty(name, getattr(self, name))
        _require_schema(self.schema_version)
        object.__setattr__(self, "object_refs", tuple(self.object_refs))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "artifact_refs", tuple(self.artifact_refs))
        _require_ref_namespace(
            self.namespace,
            *self.object_refs,
            *self.evidence_refs,
            *self.artifact_refs,
        )

def _is_union(annotation: Any) -> bool:
    origin = get_origin(annotation)
    return origin is Union or isinstance(annotation, types.UnionType)

def _union_args(annotation: Any) -> tuple[Any, ...]:
    return get_args(annotation)

def _is_none_type(annotation: Any) -> bool:
    return annotation is type(None)

def _discriminate_ref(raw: Mapping[str, Any]) -> type[Any]:
    if "evidence_id" in raw:
        return EvidenceRef
    if "artifact_id" in raw and "kind" in raw:
        return ArtifactRef
    if "object_type" in raw and "object_id" in raw:
        return ObjectRef
    raise TypeError(f"cannot discriminate ref mapping keys={sorted(raw)}")

def _coerce(annotation: Any, raw: Any) -> Any:
    if raw is None:
        if _is_union(annotation) and any(_is_none_type(arg) for arg in _union_args(annotation)):
            return None
        if annotation is type(None):
            return None
        raise TypeError(f"unexpected None for annotation {annotation!r}")

    origin = get_origin(annotation)
    if _is_union(annotation):
        args = [arg for arg in _union_args(annotation) if not _is_none_type(arg)]
        if len(args) == 1:
            return _coerce(args[0], raw)
        # Exact primitive matches before lossy casts (bool is a subclass of int).
        primitive_args = [arg for arg in args if arg in {str, int, float, bool}]
        if primitive_args and not any(
            isinstance(arg, type) and is_dataclass(arg) for arg in args
        ):
            if type(raw) is bool and bool in primitive_args:
                return raw
            if type(raw) is int and int in primitive_args:
                return raw
            if type(raw) is float and float in primitive_args:
                return raw
            if type(raw) is int and float in primitive_args:
                return float(raw)
            if type(raw) is str and str in primitive_args:
                return raw
            raise TypeError(
                f"cannot coerce {type(raw)!r} value {raw!r} to {annotation!r}"
            )
        if isinstance(raw, Mapping):
            preferred = {
                ObjectRef,
                ArtifactRef,
                EvidenceRef,
            }.intersection(args)
            if preferred:
                return rebuild_dataclass(_discriminate_ref(raw), raw)
        errors: list[str] = []
        for arg in args:
            try:
                return _coerce(arg, raw)
            except (TypeError, ValueError, KeyError) as exc:
                errors.append(f"{arg}: {exc}")
        raise TypeError("union coerce failed: " + "; ".join(errors))

    if annotation is Any:
        return raw
    if annotation is str:
        if type(raw) is not str:
            raise TypeError(f"expected str, got {type(raw)!r}")
        return raw
    if annotation is bool:
        if type(raw) is not bool:
            raise TypeError(f"expected bool, got {type(raw)!r}")
        return raw
    if annotation is int:
        if type(raw) is bool or type(raw) is not int:
            raise TypeError(f"expected int (not bool), got {type(raw)!r}")
        return raw
    if annotation is float:
        if type(raw) is bool:
            raise TypeError("bool is not accepted as float")
        if type(raw) is int:
            return float(raw)
        if type(raw) is float:
            return raw
        raise TypeError(f"expected float or int, got {type(raw)!r}")
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(raw)
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(raw, Mapping):
            raise TypeError(f"expected mapping for {annotation.__name__}")
        return rebuild_dataclass(annotation, raw)

    if origin in {tuple, list}:
        args = get_args(annotation) or (Any,)
        inner = args[0]
        if not isinstance(raw, (list, tuple)):
            raise TypeError(f"expected sequence for {annotation!r}")
        return tuple(_coerce(inner, item) for item in raw)

    if origin in {dict, Mapping} or annotation in {dict, Mapping}:
        args = get_args(annotation)
        key_type = args[0] if args else str
        val_type = args[1] if len(args) > 1 else Any
        if key_type not in {str, Any}:
            raise TypeError("only Mapping[str, ...] is supported")
        if not isinstance(raw, Mapping):
            raise TypeError("expected mapping")
        coerced: dict[str, Any] = {}
        for key in raw:
            if not isinstance(key, str):
                raise TypeError(f"mapping keys must be str, got {type(key)!r}")
            coerced[key] = _coerce(val_type, raw[key])
        return _freeze_mapping(coerced)

    if isinstance(raw, Mapping) and (
        "object_type" in raw or "artifact_id" in raw or "evidence_id" in raw
    ):
        return rebuild_dataclass(_discriminate_ref(raw), raw)
    return raw

def rebuild_dataclass(cls: type[Any], payload: Mapping[str, Any]) -> Any:
    """Rebuild a frozen dataclass tree from a plain mapping using resolved hints."""
    if not isinstance(payload, Mapping):
        raise TypeError(f"rebuild_dataclass expects a mapping, got {type(payload)!r}")
    hints = get_type_hints(cls)
    field_names = {item.name for item in fields(cls)}
    unknown = set(payload) - field_names
    if unknown:
        raise ValueError(
            f"unknown fields for {cls.__name__}: {sorted(unknown)}"
        )
    kwargs: dict[str, Any] = {}
    for item in fields(cls):
        if item.name not in payload:
            continue
        annotation = hints.get(item.name, Any)
        kwargs[item.name] = _coerce(annotation, payload[item.name])
    return cls(**kwargs)


__all__ = [
    "SCHEMA_VERSION",
    "EVALUATION_SECTIONS",
    "Severity",
    "SectionStatus",
    "ReviewConclusion",
    "PoolDecisionKind",
    "ResearchDecisionKind",
    "CandidateStatus",
    "ResearchRunStatus",
    "TaskLifecycleStatus",
    "TaskResultStatus",
    "FormulaKind",
    "FailureCode",
    "canonical_value",
    "canonical_json",
    "content_hash",
    "to_plain_dict",
    "rebuild_dataclass",
    "ObjectRef",
    "ArtifactRef",
    "EvidenceRef",
    "Provenance",
    "FailureDetail",
    "SplitWindow",
    "CostConstraints",
    "RiskConstraints",
    "TradingConstraints",
    "RobustnessGrid",
    "ResearchBudget",
    "AcceptanceCriteria",
    "ResearchBrief",
    "FunctionRef",
    "StructuredFormula",
    "FactorSpec",
    "IndexSchema",
    "FactorComputeRequest",
    "FactorExecutionResult",
    "TypedPoolMember",
    "MetricFact",
    "RuleCheck",
    "EvaluationSection",
    "EvaluationRequest",
    "EvaluationReport",
    "ReviewIssue",
    "ReviewReport",
    "PoolDecision",
    "ControllerEvent",
    "FailureKnowledgeEntry",
    "TaskLease",
    "AgentTaskView",
    "AgentTaskResult",
    "validate_agent_task_handoff",
    "ResearchDecision",
    "FreezeManifest",
    "OOSAuthorization",
    "OOSAttempt",
    "OOSResult",
    "ReportRequest",
]
