"""Governed factor-mining workflow: screening, record, freeze, and final.

Every phase reads and writes formal objects through ``DataManagerArtifactStore``.
The sealed split is opened at most once per Brief: ``final`` first creates the
``unblind_started`` artifact with ``put_if_absent`` and refuses to continue when
that artifact already exists.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from skills.analyze import AnalyzeFacade, ProtocolSnapshot
from skills.analyze.content_fingerprint import fingerprint_frame
from skills.analyze.contracts import ENGINE_VERSION
from skills.factor_mining import (
    SCHEMA_VERSION,
    AnalyzeAdapter,
    ArtifactRef,
    DataManagerArtifactStore,
    EvaluationReport,
    EvaluationRequest,
    FactorComputeRequest,
    FactorExecutionAdapter,
    FactorExecutionResult,
    FactorSpec,
    FailureCode,
    FormulaKind,
    FreezeManifest,
    FunctionRef,
    ObjectRef,
    PoolDecision,
    PoolDecisionKind,
    Provenance,
    ResearchBrief,
    ReviewConclusion,
    ReviewReport,
    SectionStatus,
    Severity,
    SplitWindow,
    StructuredFormula,
    rebuild_dataclass,
    to_plain_dict,
)
from skills.factor_mining.adapters.analyze import oos_report_passes_frozen_thresholds
from skills.factor_mining.adapters.compute import CODE_VERSION, load_execution_series
from skills.factor_mining.adapters.execution_identity import execution_envelope_identity
from skills.factor_mining.adapters.formula import compile_formula
from skills.factor_mining.adapters.panel import ADAPTER_SCHEMA_VERSION
from skills.factor_mining.adapters.store import ArtifactStoreAdapterError
from skills.store.data_manager import DataManager
from skills.store.workspace import resolve_workspace_paths
from strategies.factor_mining.brief import (
    CODE_VERSION_WORKFLOW,
    PROTOCOL_ID_PREFIX,
    dump_brief,
    load_brief,
    make_example_brief,
    protocol_for,
    protocol_id_for,
)
from strategies.factor_mining.mined_factors import CANDIDATES as PACKAGE_CANDIDATES

PhaseName = Literal["screening", "record", "freeze", "final"]

MINED_MODULE_PREFIX = "strategies.factor_mining.mined_factors"
# Generated factor code lives in the mined_factors package of any strategy domain.
MINED_MODULE_PATTERN = re.compile(
    r"strategies\.[A-Za-z_][A-Za-z0-9_]*\.mined_factors(\.[A-Za-z_][A-Za-z0-9_]*)*"
)
REVIEW_ROLES = ("methodology_critic", "leakage_and_code_reviewer")
POOL_ROLE = "pool_synthesizer"
UNBLIND_STARTED = "unblind_started"
UNBLIND_COMPLETED = "unblind_completed"
UNBLIND_FAILED = "unblind_failed"
SCREENING_INDEX_NAME = "screening_index.json"
FREEZE_INDEX_NAME = "freeze_index.json"


@dataclass
class PhaseResult:
    """JSON-printable outcome of one workflow phase."""

    phase: str
    brief_id: str
    brief_hash: str
    data_version: str
    output_dir: str
    observed_panel_end: str | None
    contains_sealed_rows: bool
    factor_ids: tuple[str, ...] = ()
    manifest_hashes: tuple[str, ...] = ()
    once_key: str | None = None
    event_ids: tuple[str, ...] = ()


@dataclass
class _Runtime:
    brief: ResearchBrief
    specs: dict[str, FactorSpec]
    executions: dict[str, FactorExecutionResult] = field(default_factory=dict)
    reports: dict[str, EvaluationReport] = field(default_factory=dict)
    observed_panels: list[pd.DataFrame] = field(default_factory=list)
    allow_sealed: bool = False
    base_panel: pd.DataFrame | None = None
    artifacts: DataManagerArtifactStore | None = None
    dm: DataManager | None = None


def specs_from_candidates(
    brief: ResearchBrief,
    candidates: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[FactorSpec, ...]:
    rows = tuple(PACKAGE_CANDIDATES if candidates is None else candidates)
    if len(rows) > brief.budget.max_candidates:
        raise ValueError(
            f"candidate count exceeds budget: {len(rows)} > {brief.budget.max_candidates}"
        )
    brief_ref = _brief_ref(brief)
    specs: list[FactorSpec] = []
    for row in rows:
        module = str(row["module"])
        if MINED_MODULE_PATTERN.fullmatch(module) is None:
            raise ValueError(
                f"function_ref.module must be inside a strategies mined_factors package: {module}"
            )
        specs.append(
            FactorSpec(
                factor_id=str(row["factor_id"]),
                revision=int(row.get("revision", 1)),
                brief_ref=brief_ref,
                family=str(row["family"]),
                hypothesis=str(row["hypothesis"]),
                expected_direction=str(row["expected_direction"]),
                required_fields=tuple(row["required_fields"]),
                formula=StructuredFormula(
                    kind=FormulaKind.FUNCTION_REF,
                    function_ref=FunctionRef(module=module, name=str(row["name"])),
                    params=dict(row.get("params") or {}),
                ),
                window=int(row["window"]),
                lag=int(row["lag"]),
                warmup=int(row["warmup"]),
                missing_policy=str(row["missing_policy"]),
                availability_rule=str(row["availability_rule"]),
                output_dtype=str(row["output_dtype"]),
                index_restore_policy=str(row["index_restore_policy"]),
                applicable_regimes=tuple(row.get("applicable_regimes") or ()),
                known_relations=tuple(row.get("known_relations") or ()),
                falsification_tests=tuple(row.get("falsification_tests") or ()),
                provenance=Provenance(
                    producer="factor_mining.generator",
                    data_version=brief.data_version,
                    code_version=CODE_VERSION_WORKFLOW,
                    experiment_version=brief.brief_id,
                    namespace=brief.provenance.namespace,
                    input_refs=(brief_ref,),
                ),
            )
        )
    return tuple(specs)


def _eob(panel: pd.DataFrame, datetime_level: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(panel.index.get_level_values(datetime_level)))


def slice_research_panel(panel: pd.DataFrame, brief: ResearchBrief) -> pd.DataFrame:
    eob = _eob(panel, brief.datetime_level)
    end = pd.Timestamp(brief.validation.end)
    sealed_start = pd.Timestamp(brief.sealed.start)
    sliced = panel.loc[eob <= end]
    if sliced.empty:
        raise ValueError("research panel is empty")
    sliced_eob = _eob(sliced, brief.datetime_level)
    if sliced_eob.max() > end:
        raise ValueError("research panel exceeds validation.end")
    if (sliced_eob >= sealed_start).any():
        raise ValueError("research panel contains sealed rows")
    return sliced


def slice_split_panel(
    panel: pd.DataFrame,
    brief: ResearchBrief,
    split: SplitWindow,
    *,
    warmup_bars: int,
    allow_sealed: bool,
) -> pd.DataFrame:
    if split.sealed and not allow_sealed:
        raise ValueError("sealed split is not available before unblind")
    eob = _eob(panel, brief.datetime_level)
    end = pd.Timestamp(split.end)
    start = pd.Timestamp(split.start)
    unique = pd.DatetimeIndex(sorted(eob.unique()))
    prior = unique[unique < start]
    if warmup_bars > 0 and len(prior):
        warmup_start = prior[max(0, len(prior) - warmup_bars)]
    else:
        warmup_start = unique[0] if len(unique) else start
    sliced = panel.loc[(eob >= warmup_start) & (eob <= end)]
    if sliced.empty:
        raise ValueError(f"split panel is empty: {split.split_id}")
    if not allow_sealed:
        sealed_start = pd.Timestamp(brief.sealed.start)
        if (_eob(sliced, brief.datetime_level) >= sealed_start).any():
            raise ValueError("research panel contains sealed rows")
    return sliced


def research_data_version(panel: pd.DataFrame, brief: ResearchBrief) -> str:
    return fingerprint_frame(slice_research_panel(panel, brief))


def assert_data_version(panel: pd.DataFrame, brief: ResearchBrief) -> str:
    actual = research_data_version(panel, brief)
    if actual != brief.data_version:
        raise ValueError(f"data_version mismatch: brief={brief.data_version} panel={actual}")
    return actual


def write_example_brief(
    path: str | Path, *, data_root: str | Path | None = None, overwrite: bool = False
) -> ResearchBrief:
    """Write the example Brief with ``data_version`` taken from local research-window data."""
    target = Path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"Brief already exists: {target}")
    draft = make_example_brief(data_version="pending")
    panel = _load_market_panel(draft, _data_manager(data_root), research_only=True)
    brief = make_example_brief(data_version=research_data_version(panel, draft))
    dump_brief(brief, target)
    return brief


def _brief_ref(brief: ResearchBrief) -> ObjectRef:
    return ObjectRef(
        object_type="ResearchBrief",
        object_id=brief.brief_id,
        content_hash=brief.content_hash,
        namespace=brief.provenance.namespace,
    )


def _factor_ref(spec: FactorSpec) -> ObjectRef:
    return ObjectRef(
        object_type="FactorSpec",
        object_id=spec.factor_id,
        content_hash=spec.content_hash,
        namespace=spec.provenance.namespace,
    )


def _execution_ref(execution: FactorExecutionResult) -> ObjectRef:
    return ObjectRef(
        object_type="FactorExecutionResult",
        object_id=execution.execution_id,
        content_hash=execution.fingerprint,
        namespace=execution.provenance.namespace,
    )


def _report_ref(report: EvaluationReport) -> ObjectRef:
    return ObjectRef(
        object_type="EvaluationReport",
        object_id=report.report_id,
        content_hash=report.content_hash,
        namespace=report.provenance.namespace,
    )


def _split(brief: ResearchBrief, split_id: str) -> SplitWindow:
    for window in (brief.train, brief.validation, brief.sealed):
        if window.split_id == split_id:
            return window
    raise ValueError(f"unknown split_id: {split_id}")


def _put_payload(
    store: DataManagerArtifactStore,
    *,
    namespace: str,
    kind: str,
    artifact_id: str,
    payload: Mapping[str, Any],
    input_refs: tuple[ObjectRef | ArtifactRef, ...] = (),
    append_only: bool = False,
) -> ArtifactRef:
    if append_only:
        return store.put_if_absent(
            namespace=namespace,
            kind=kind,
            artifact_id=artifact_id,
            payload=dict(payload),
            input_refs=input_refs,
        ).ref
    return store.put(
        namespace=namespace,
        kind=kind,
        artifact_id=artifact_id,
        payload=dict(payload),
        input_refs=input_refs,
    )


def _put_object(
    store: DataManagerArtifactStore,
    obj: Any,
    *,
    kind: str,
    artifact_id: str,
    input_refs: tuple[ObjectRef | ArtifactRef, ...] = (),
    append_only: bool = False,
) -> ArtifactRef:
    namespace = obj.provenance.namespace
    return _put_payload(
        store,
        namespace=namespace,
        kind=kind,
        artifact_id=artifact_id,
        payload=to_plain_dict(obj),
        input_refs=input_refs,
        append_only=append_only,
    )


def _load_typed(
    store: DataManagerArtifactStore, cls: type, *, namespace: str, kind: str, artifact_id: str
) -> Any:
    payload = store.get_by_identity(namespace=namespace, kind=kind, artifact_id=artifact_id)
    obj = rebuild_dataclass(cls, payload)
    if hasattr(obj, "validate_hash"):
        obj.validate_hash()
    return obj


def _resolve_object_ref(store: DataManagerArtifactStore, ref: ObjectRef) -> Any:
    if ref.object_type == "ResearchBrief":
        cls, kind, artifact_id = ResearchBrief, "research_brief", ref.object_id
    elif ref.object_type == "FactorSpec":
        cls, kind, artifact_id = FactorSpec, "factor_spec", ref.object_id
    elif ref.object_type == "EvaluationReport":
        request_id = ref.object_id.removeprefix("eval-")
        if request_id.startswith("eval."):
            factor_id, split_id = request_id.removeprefix("eval.").rsplit("__", 1)
            artifact_id = f"eval.{factor_id}.{split_id}"
        else:
            artifact_id = request_id
        cls, kind = EvaluationReport, "evaluation_report"
    elif ref.object_type == "ReviewReport":
        cls, kind, artifact_id = ReviewReport, "review_report", ref.object_id.removeprefix("rev.")
    elif ref.object_type == "PoolDecision":
        cls, kind, artifact_id = (
            PoolDecision,
            "pool_decision",
            ref.object_id.removeprefix("pool.") + "." + POOL_ROLE,
        )
    elif ref.object_type == "FactorExecutionResult":
        cls, kind, artifact_id = FactorExecutionResult, "factor_execution_result", ref.object_id
    else:
        raise ValueError(f"unsupported object reference: {ref.object_type}")
    obj = _load_typed(store, cls, namespace=ref.namespace, kind=kind, artifact_id=artifact_id)
    digest = obj.fingerprint if isinstance(obj, FactorExecutionResult) else obj.content_hash
    if isinstance(obj, FactorExecutionResult) and execution_envelope_identity(obj) != digest:
        raise ValueError(f"execution fingerprint mismatch: {ref.object_id}")
    identity_field = {
        "ResearchBrief": "brief_id",
        "FactorSpec": "factor_id",
        "EvaluationReport": "report_id",
        "ReviewReport": "report_id",
        "PoolDecision": "decision_id",
        "FactorExecutionResult": "execution_id",
    }[ref.object_type]
    if digest != ref.content_hash or getattr(obj, identity_field) != ref.object_id:
        raise ValueError(f"object reference mismatch: {ref.object_type}/{ref.object_id}")
    return obj


def run_record(
    brief: ResearchBrief,
    *,
    data_root: str | Path | None = None,
    record_object: Mapping[str, Any],
    output_dir: str | Path | None = None,
) -> PhaseResult:
    object_type = record_object.get("object_type")
    if object_type not in {"ReviewReport", "PoolDecision"}:
        raise ValueError("record supports ReviewReport or PoolDecision")
    payload = record_object.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("record requires an object payload")
    if not payload.get("content_hash"):
        raise ValueError("record requires a supplied content_hash")
    cls = ReviewReport if object_type == "ReviewReport" else PoolDecision
    obj = rebuild_dataclass(cls, payload)
    obj.validate_hash()
    namespace = brief.provenance.namespace
    if obj.provenance.namespace != namespace or obj.provenance.data_version != brief.data_version:
        raise ValueError("record provenance mismatch")
    dm = _data_manager(data_root)
    store = DataManagerArtifactStore(dm)
    if obj.factor_ref.namespace != namespace:
        raise ValueError("record namespace mismatch")
    stored_brief = _resolve_object_ref(store, _brief_ref(brief))
    if stored_brief.content_hash != brief.content_hash:
        raise ValueError("record Brief mismatch")
    _resolve_object_ref(store, obj.factor_ref)
    if isinstance(obj, ReviewReport):
        if (
            obj.role_id not in REVIEW_ROLES
            or obj.report_id != f"rev.{obj.factor_ref.object_id}.{obj.role_id}"
        ):
            raise ValueError("record ReviewReport identity mismatch")
        report = _resolve_object_ref(store, obj.evaluation_ref)
        if (
            report.factor_ref != obj.factor_ref
            or report.brief_ref != _brief_ref(brief)
            or report.split_id != brief.validation.split_id
        ):
            raise ValueError("record evaluation reference mismatch")
        refs = [ref for issue in obj.issues for ref in issue.evidence_refs]
        kind, artifact_id = "review_report", f"{obj.factor_ref.object_id}.{obj.role_id}"
    else:
        if obj.role_id != POOL_ROLE or obj.decision_id != f"pool.{obj.factor_ref.object_id}":
            raise ValueError("record PoolDecision identity mismatch")
        refs = list(obj.incremental_evidence)
        kind, artifact_id = "pool_decision", f"{obj.factor_ref.object_id}.{POOL_ROLE}"
    for source_ref in obj.provenance.input_refs:
        if isinstance(source_ref, ObjectRef):
            _resolve_object_ref(store, source_ref)
        elif isinstance(source_ref, ArtifactRef):
            store.get(source_ref)
        else:
            refs.append(source_ref)
    for evidence in refs:
        request_id = evidence.source_report_id.removeprefix("eval-")
        if request_id.startswith("eval."):
            factor_id, split_id = request_id.removeprefix("eval.").rsplit("__", 1)
            source_artifact_id = f"eval.{factor_id}.{split_id}"
        else:
            source_artifact_id = request_id
        report = _load_typed(
            store,
            EvaluationReport,
            namespace=namespace,
            kind="evaluation_report",
            artifact_id=source_artifact_id,
        )
        if report.report_id != evidence.source_report_id or report.brief_ref != _brief_ref(brief):
            raise ValueError("record evidence report mismatch")
        found = [fact.evidence for section in report.sections for fact in section.facts] + [
            check.evidence
            for section in report.sections
            for check in section.checks
            if check.evidence is not None
        ]
        if evidence not in found or not any(
            section.name == evidence.section for section in report.sections
        ):
            raise ValueError(f"record evidence reference mismatch: {evidence.evidence_id}")
        if evidence.artifact is not None:
            store.get(evidence.artifact)
    _put_object(
        store,
        obj,
        kind=kind,
        artifact_id=artifact_id,
        input_refs=(obj.factor_ref,),
        append_only=True,
    )
    return PhaseResult(
        "record",
        brief.brief_id,
        brief.content_hash,
        brief.data_version,
        str(Path(output_dir) if output_dir is not None else _default_output_dir(brief.brief_id)),
        None,
        False,
        (obj.factor_ref.object_id,),
    )


def _hard_failed_report(report: EvaluationReport) -> bool:
    if report.failure is not None:
        return True
    for section in report.sections:
        for check in section.checks:
            if (not check.passed) and check.severity is Severity.HARD_FAIL:
                return True
    return False


def _hard_failed_review(review: ReviewReport) -> bool:
    if review.conclusion is ReviewConclusion.FAIL:
        return True
    return any(issue.severity is Severity.HARD_FAIL for issue in review.issues)


EMPTY_POOL_RISK = "POOL_INCREMENTAL_UNAVAILABLE"


def _validate_pool_acceptance(
    brief: ResearchBrief,
    compare: EvaluationReport,
    reviews: Sequence[ReviewReport],
    pool: PoolDecision,
) -> None:
    """An empty pool may bootstrap one candidate, never imply incremental value."""
    if pool.decision is not PoolDecisionKind.ACCEPT:
        raise ValueError("PoolDecision rejected")
    if compare.pool_refs:
        return
    section = next((item for item in compare.sections if item.name == "pool_incremental"), None)
    unavailable = (
        None
        if section is None
        else next((check for check in section.checks if check.name == "POOL_UNAVAILABLE"), None)
    )
    if (
        brief.freeze_criteria.require_pool_incremental
        or section is None
        or section.status is not SectionStatus.PARTIAL
        or len(section.checks) != 1
        or unavailable is None
        or unavailable.passed
        or unavailable.severity is not Severity.SOFT_FAIL
        or unavailable.evidence is None
        or any(fact.value is not None for fact in section.facts)
        or any(review.conclusion is not ReviewConclusion.PASS for review in reviews)
        or pool.incremental_evidence != (unavailable.evidence,)
        or EMPTY_POOL_RISK not in pool.residual_risks
    ):
        raise ValueError("empty-pool bootstrap evidence or Brief opt-in missing")


def _panel_end(panel: pd.DataFrame, datetime_level: str) -> str:
    return str(_eob(panel, datetime_level).max().date())


def _contains_sealed(panels: Sequence[pd.DataFrame], brief: ResearchBrief) -> bool:
    sealed_start = pd.Timestamp(brief.sealed.start)
    return any((_eob(panel, brief.datetime_level) >= sealed_start).any() for panel in panels)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _data_manager(data_root: str | Path | None) -> DataManager:
    return DataManager(data_root=None if data_root is None else str(data_root))


def _default_output_dir(brief_id: str) -> Path:
    return resolve_workspace_paths().reports_root / "factor_mining" / brief_id


def _load_market_panel(
    brief: ResearchBrief, dm: DataManager, *, research_only: bool
) -> pd.DataFrame:
    panel = dm.read_symbols(list(brief.universe), frequency=brief.frequency)
    if research_only:
        # Rows after validation.end are dropped here, before any caller sees the panel.
        panel = panel.loc[_eob(panel, brief.datetime_level) <= pd.Timestamp(brief.validation.end)]
    return panel


def _build_adapters(runtime: _Runtime) -> tuple[FactorExecutionAdapter, AnalyzeAdapter]:
    brief = runtime.brief
    artifacts = runtime.artifacts
    assert artifacts is not None
    assert runtime.base_panel is not None

    def resolve_brief(ref: ObjectRef) -> ResearchBrief:
        if ref.object_id != brief.brief_id or ref.content_hash != brief.content_hash:
            raise ValueError("brief ref mismatch")
        return brief

    def resolve_factor(ref: ObjectRef) -> FactorSpec:
        spec = runtime.specs[ref.object_id]
        if spec.content_hash != ref.content_hash:
            raise ValueError("factor ref mismatch")
        return spec

    def resolve_protocol(protocol_id: str) -> ProtocolSnapshot:
        prefix = PROTOCOL_ID_PREFIX + ":"
        if not protocol_id.startswith(prefix):
            raise ValueError(f"unknown protocol_id: {protocol_id}")
        return protocol_for(brief, runtime.specs[protocol_id[len(prefix) :]])

    def resolve_execution(ref: ObjectRef) -> FactorExecutionResult:
        execution = runtime.executions[ref.object_id]
        if execution.fingerprint != ref.content_hash:
            raise ValueError("execution ref mismatch")
        return execution

    def load_panel(request: EvaluationRequest | FactorComputeRequest) -> pd.DataFrame:
        spec = runtime.specs[request.factor_ref.object_id]
        split = _split(brief, request.split_id)
        panel = slice_split_panel(
            runtime.base_panel,
            brief,
            split,
            warmup_bars=spec.warmup,
            allow_sealed=runtime.allow_sealed,
        )
        runtime.observed_panels.append(panel)
        return panel

    execution_adapter = FactorExecutionAdapter(
        resolve_factor_spec=resolve_factor,
        resolve_panel=load_panel,
        artifact_store=artifacts,
    )
    analyze_adapter = AnalyzeAdapter(
        facade=AnalyzeFacade(),
        resolve_brief=resolve_brief,
        resolve_factor=resolve_factor,
        resolve_protocol=resolve_protocol,
        resolve_execution=resolve_execution,
        load_series=lambda ref: load_execution_series(artifacts, ref),
        load_panel=load_panel,
        load_pool=lambda request: None,
    )
    return execution_adapter, analyze_adapter


def _evaluate_split(
    runtime: _Runtime,
    spec: FactorSpec,
    split_id: str,
    *,
    execution_adapter: FactorExecutionAdapter,
    analyze_adapter: AnalyzeAdapter,
    sealed_execution: bool = False,
) -> tuple[FactorExecutionResult, EvaluationReport]:
    brief = runtime.brief
    namespace = brief.provenance.namespace
    execution_id = f"{spec.factor_id}__{split_id}"
    compute = FactorComputeRequest(
        request_id=f"compute.{execution_id}",
        namespace=namespace,
        experiment_id=brief.brief_id,
        execution_id=execution_id,
        brief_ref=_brief_ref(brief),
        factor_ref=_factor_ref(spec),
        data_version=brief.data_version,
        split_id=split_id,
        sealed_execution=sealed_execution,
    )
    execution = execution_adapter.execute(compute)
    runtime.executions[execution.execution_id] = execution
    _put_object(
        runtime.artifacts,
        execution,
        kind="factor_execution_result",
        artifact_id=execution.execution_id,
        input_refs=(_brief_ref(brief), _factor_ref(spec)),
    )
    eval_req = EvaluationRequest(
        request_id=f"eval.{execution_id}",
        namespace=namespace,
        brief_ref=_brief_ref(brief),
        factor_ref=_factor_ref(spec),
        execution_ref=None if execution.failure is not None else _execution_ref(execution),
        protocol_id=protocol_id_for(spec),
        data_version=brief.data_version,
        split_id=split_id,
    )
    report = analyze_adapter.evaluate(eval_req)
    runtime.reports[report.report_id] = report
    _put_object(
        runtime.artifacts,
        report,
        kind="evaluation_report",
        artifact_id=f"eval.{spec.factor_id}.{split_id}",
        input_refs=(_brief_ref(brief), _factor_ref(spec)),
    )
    return execution, report


def run_screening(
    brief: ResearchBrief,
    *,
    data_root: str | Path | None = None,
    output_dir: str | Path | None = None,
    candidates: Sequence[Mapping[str, Any]] | None = None,
    panel: pd.DataFrame | None = None,
) -> PhaseResult:
    specs = specs_from_candidates(brief, candidates)
    dm = _data_manager(data_root)
    artifacts = DataManagerArtifactStore(dm)
    try:
        artifacts.get_by_identity(
            namespace=brief.provenance.namespace,
            kind="freeze_batch",
            artifact_id=brief.brief_id,
        )
    except ArtifactStoreAdapterError as exc:
        if exc.code is not FailureCode.INVALID_REFERENCE:
            raise
    else:
        raise ValueError("screening is closed after this Brief was frozen")
    market = panel if panel is not None else _load_market_panel(brief, dm, research_only=True)
    assert_data_version(market, brief)
    research = slice_research_panel(market, brief)
    runtime = _Runtime(
        brief=brief,
        specs={spec.factor_id: spec for spec in specs},
        allow_sealed=False,
        base_panel=research,
        artifacts=artifacts,
        dm=dm,
    )
    execution_adapter, analyze_adapter = _build_adapters(runtime)
    namespace = brief.provenance.namespace
    _put_object(
        artifacts,
        brief,
        kind="research_brief",
        artifact_id=brief.brief_id,
    )
    candidate_rows: list[dict[str, Any]] = []
    for spec in specs:
        _put_object(
            artifacts,
            spec,
            kind="factor_spec",
            artifact_id=spec.factor_id,
            input_refs=(_brief_ref(brief),),
        )
        preflight_req = EvaluationRequest(
            request_id=f"preflight.{spec.factor_id}",
            namespace=namespace,
            brief_ref=_brief_ref(brief),
            factor_ref=_factor_ref(spec),
            execution_ref=None,
            protocol_id=protocol_id_for(spec),
            data_version=brief.data_version,
            split_id=brief.train.split_id,
        )
        preflight = analyze_adapter.preflight(preflight_req)
        runtime.reports[preflight.report_id] = preflight
        _put_object(
            artifacts,
            preflight,
            kind="evaluation_report",
            artifact_id=f"preflight.{spec.factor_id}",
            input_refs=(_brief_ref(brief), _factor_ref(spec)),
        )
        row: dict[str, Any] = {
            "factor_id": spec.factor_id,
            "spec": to_plain_dict(spec),
            "preflight_report_id": preflight.report_id,
            "preflight_hash": preflight.content_hash,
            "preflight_failed": _hard_failed_report(preflight),
            "splits": {},
        }
        if not _hard_failed_report(preflight):
            for split in (brief.train, brief.validation):
                execution, report = _evaluate_split(
                    runtime,
                    spec,
                    split.split_id,
                    execution_adapter=execution_adapter,
                    analyze_adapter=analyze_adapter,
                )
                row["splits"][split.split_id] = {
                    "execution_id": execution.execution_id,
                    "execution_fingerprint": execution.fingerprint,
                    "report_id": report.report_id,
                    "report_hash": report.content_hash,
                    "failed": execution.failure is not None or _hard_failed_report(report),
                    "rank_ic_ir": _metric(report, "rank_ic_ir"),
                }
            if (
                brief.validation.split_id in row["splits"]
                and not row["splits"][brief.validation.split_id]["failed"]
            ):
                compare_req = EvaluationRequest(
                    request_id=f"compare.{spec.factor_id}",
                    namespace=namespace,
                    brief_ref=_brief_ref(brief),
                    factor_ref=_factor_ref(spec),
                    execution_ref=_execution_ref(
                        runtime.executions[f"{spec.factor_id}__{brief.validation.split_id}"]
                    ),
                    protocol_id=protocol_id_for(spec),
                    data_version=brief.data_version,
                    split_id=brief.validation.split_id,
                )
                compare = analyze_adapter.compare_to_pool(compare_req)
                runtime.reports[compare.report_id] = compare
                _put_object(
                    artifacts,
                    compare,
                    kind="evaluation_report",
                    artifact_id=f"compare.{spec.factor_id}",
                    input_refs=(_brief_ref(brief), _factor_ref(spec)),
                )
                row["compare_report_id"] = compare.report_id
                row["compare_hash"] = compare.content_hash
        candidate_rows.append(row)

    out = Path(output_dir) if output_dir is not None else _default_output_dir(brief.brief_id)
    index = {
        "brief_id": brief.brief_id,
        "brief_hash": brief.content_hash,
        "namespace": namespace,
        "data_version": brief.data_version,
        "schema_version": SCHEMA_VERSION,
        "candidates": candidate_rows,
    }
    _write_json(out / SCREENING_INDEX_NAME, index)
    _write_json(
        out / "screening_summary.json",
        {
            "brief_id": brief.brief_id,
            "data_version": brief.data_version,
            "factor_ids": [row["factor_id"] for row in candidate_rows],
            "candidates": candidate_rows,
        },
    )
    observed_end = (
        max(_panel_end(item, brief.datetime_level) for item in runtime.observed_panels)
        if runtime.observed_panels
        else None
    )
    return PhaseResult(
        phase="screening",
        brief_id=brief.brief_id,
        brief_hash=brief.content_hash,
        data_version=brief.data_version,
        output_dir=str(out),
        observed_panel_end=observed_end,
        contains_sealed_rows=_contains_sealed(runtime.observed_panels, brief),
        factor_ids=tuple(spec.factor_id for spec in specs),
    )


def _oos_thresholds(brief: ResearchBrief) -> tuple[dict[str, float], dict[str, dict[str, str]]]:
    criteria = brief.oos_criteria
    thresholds: dict[str, float] = {}
    selectors: dict[str, dict[str, str]] = {}
    if criteria.min_rank_ic_ir is not None:
        thresholds["min_rank_ic_ir"] = float(criteria.min_rank_ic_ir)
        selectors["min_rank_ic_ir"] = {"fact_name": "rank_ic_ir", "operator": "gte"}
    if criteria.min_coverage is not None:
        thresholds["min_coverage"] = float(criteria.min_coverage)
        selectors["min_coverage"] = {"fact_name": "coverage_worst", "operator": "gte"}
    if criteria.max_turnover is not None:
        thresholds["max_turnover"] = float(criteria.max_turnover)
        selectors["max_turnover"] = {"fact_name": "group_turnover_mean", "operator": "lte"}
    if not thresholds:
        thresholds["min_rank_ic_ir"] = 0.0
        selectors["min_rank_ic_ir"] = {"fact_name": "rank_ic_ir", "operator": "gte"}
    return thresholds, selectors


def _metric(report: EvaluationReport, name: str) -> float | None:
    for section in report.sections:
        for fact in section.facts:
            if (
                fact.name == name
                and isinstance(fact.value, (int, float))
                and not isinstance(fact.value, bool)
            ):
                return float(fact.value)
    return None


def run_freeze(
    brief: ResearchBrief,
    *,
    data_root: str | Path | None = None,
    approve: Sequence[str],
    output_dir: str | Path | None = None,
) -> PhaseResult:
    if not approve:
        raise ValueError("freeze requires --approve factor_id list")
    if len(set(approve)) != len(approve):
        raise ValueError("freeze approval contains duplicate factor_id")
    dm = _data_manager(data_root)
    artifacts = DataManagerArtifactStore(dm)
    out = Path(output_dir) if output_dir is not None else _default_output_dir(brief.brief_id)
    index_path = out / SCREENING_INDEX_NAME
    if not index_path.is_file():
        raise FileNotFoundError(f"screening index not found: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("brief_hash") != brief.content_hash:
        raise ValueError("screening index brief_hash does not match the loaded Brief")
    by_id = {row["factor_id"]: row for row in index["candidates"]}
    namespace = brief.provenance.namespace
    manifests: list[FreezeManifest] = []
    for factor_id in approve:
        if factor_id not in by_id:
            raise ValueError(f"unknown factor_id in --approve: {factor_id}")
        row = by_id[factor_id]
        spec = rebuild_dataclass(FactorSpec, row["spec"])
        spec.validate_hash()
        if spec.brief_ref != _brief_ref(brief):
            raise ValueError(f"screening candidate Brief mismatch: {factor_id}")
        stored_spec = _resolve_object_ref(artifacts, _factor_ref(spec))
        if stored_spec != spec:
            raise ValueError(f"screening candidate mismatch: {factor_id}")
        if row.get("preflight_failed"):
            raise ValueError(f"cannot freeze hard-failed candidate: {factor_id}")
        for split_id in (brief.train.split_id, brief.validation.split_id):
            split_row = row.get("splits", {}).get(split_id)
            if split_row is None or split_row.get("failed"):
                raise ValueError(
                    f"cannot freeze candidate without a clean {split_id} evaluation: {factor_id}"
                )
        review_refs: list[ObjectRef] = []
        reviews: list[ReviewReport] = []
        for role_id in REVIEW_ROLES:
            try:
                review = _load_typed(
                    artifacts,
                    ReviewReport,
                    namespace=namespace,
                    kind="review_report",
                    artifact_id=f"{factor_id}.{role_id}",
                )
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"missing review {role_id} for {factor_id}") from exc
            if review.role_id != role_id:
                raise ValueError(f"review role mismatch for {factor_id}: {review.role_id}")
            if review.factor_ref != _factor_ref(spec):
                raise ValueError(f"review factor reference mismatch for {factor_id}")
            if _hard_failed_review(review):
                raise ValueError(f"hard fail review {role_id} for {factor_id}")
            reviews.append(review)
            review_refs.append(
                ObjectRef(
                    object_type="ReviewReport",
                    object_id=review.report_id,
                    content_hash=review.content_hash,
                    namespace=namespace,
                )
            )
        try:
            pool = _load_typed(
                artifacts,
                PoolDecision,
                namespace=namespace,
                kind="pool_decision",
                artifact_id=f"{factor_id}.{POOL_ROLE}",
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"missing PoolDecision for {factor_id}") from exc
        if pool.role_id != POOL_ROLE:
            raise ValueError(f"PoolDecision role mismatch for {factor_id}")
        if pool.factor_ref != _factor_ref(spec) or pool.decision is not PoolDecisionKind.ACCEPT:
            raise ValueError(f"PoolDecision rejected or factor reference mismatch for {factor_id}")
        preflight = _load_typed(
            artifacts,
            EvaluationReport,
            namespace=namespace,
            kind="evaluation_report",
            artifact_id=f"preflight.{factor_id}",
        )
        validation = _load_typed(
            artifacts,
            EvaluationReport,
            namespace=namespace,
            kind="evaluation_report",
            artifact_id=f"eval.{factor_id}.{brief.validation.split_id}",
        )
        compare = _load_typed(
            artifacts,
            EvaluationReport,
            namespace=namespace,
            kind="evaluation_report",
            artifact_id=f"compare.{factor_id}",
        )
        validation_execution_id = row["splits"][brief.validation.split_id]["execution_id"]
        execution_fp = row["splits"][brief.validation.split_id]["execution_fingerprint"]
        for label, report in (
            ("preflight", preflight),
            ("validation", validation),
            ("compare", compare),
        ):
            if report.brief_ref != _brief_ref(brief) or report.factor_ref != _factor_ref(spec):
                raise ValueError(f"{label} report reference mismatch for {factor_id}")
        if (
            validation.content_hash != row["splits"][brief.validation.split_id]["report_hash"]
            or preflight.content_hash != row["preflight_hash"]
            or compare.content_hash != row["compare_hash"]
        ):
            raise ValueError(f"screening report hash mismatch for {factor_id}")
        if not compare.pool_refs and len(approve) != 1:
            raise ValueError("empty-pool bootstrap requires exactly one approved factor")
        _validate_pool_acceptance(brief, compare, reviews, pool)
        for role_id, review_ref in zip(REVIEW_ROLES, review_refs, strict=True):
            review = _resolve_object_ref(artifacts, review_ref)
            if review.evaluation_ref != _report_ref(validation):
                raise ValueError(f"review evaluation reference mismatch for {factor_id}: {role_id}")
        _resolve_object_ref(
            artifacts,
            ObjectRef(
                "FactorExecutionResult",
                validation_execution_id,
                content_hash=execution_fp,
                namespace=namespace,
            ),
        )
        approval = _put_payload(
            artifacts,
            namespace=namespace,
            kind="human_gate_1",
            artifact_id=f"approve.{factor_id}",
            payload={
                "factor_id": factor_id,
                "brief_id": brief.brief_id,
                "approved": True,
            },
            input_refs=(_brief_ref(brief), _factor_ref(spec)),
            append_only=True,
        )
        thresholds, selectors = _oos_thresholds(brief)
        manifest = FreezeManifest(
            manifest_id=f"freeze.{factor_id}",
            run_id=brief.brief_id,
            brief_ref=_brief_ref(brief),
            factor_ref=_factor_ref(spec),
            universe=tuple(brief.universe),
            data_version=brief.data_version,
            split_refs={
                brief.train.split_id: brief.train.split_id,
                brief.validation.split_id: brief.validation.split_id,
                brief.sealed.split_id: brief.sealed.split_id,
            },
            compute_engine_version=CODE_VERSION,
            analyze_engine_version=ENGINE_VERSION,
            evaluation_protocol_id=protocol_id_for(spec),
            direction=spec.expected_direction,
            params=dict(spec.formula.params),
            missing_policy=spec.missing_policy,
            adjustment_policy=brief.adjustment,
            outlier_policy="none",
            neutralization_policy="none",
            holding_horizon_bars=brief.horizon_bars,
            rebalance=brief.rebalance,
            cost=brief.cost,
            pool_baseline_refs=(),
            preflight_ref=_report_ref(preflight),
            execution_ref=ObjectRef(
                object_type="FactorExecutionResult",
                object_id=validation_execution_id,
                content_hash=execution_fp,
                namespace=namespace,
            ),
            evaluation_ref=_report_ref(validation),
            compare_ref=_report_ref(compare),
            review_refs=tuple(review_refs),
            pool_decision_ref=ObjectRef(
                object_type="PoolDecision",
                object_id=pool.decision_id,
                content_hash=pool.content_hash,
                namespace=namespace,
            ),
            approval_ref=approval,
            oos_thresholds=thresholds,
            oos_metric_selectors=selectors,
            provenance=Provenance(
                producer="factor_mining.freeze",
                data_version=brief.data_version,
                code_version=CODE_VERSION_WORKFLOW,
                experiment_version=brief.brief_id,
                namespace=namespace,
                input_refs=(_brief_ref(brief), _factor_ref(spec)),
            ),
        )
        _put_object(
            artifacts,
            manifest,
            kind="freeze_manifest",
            artifact_id=factor_id,
            input_refs=(_brief_ref(brief), _factor_ref(spec)),
            append_only=True,
        )
        manifests.append(manifest)

    freeze_index = {
        "brief_id": brief.brief_id,
        "brief_hash": brief.content_hash,
        "data_version": brief.data_version,
        "approved": list(approve),
        "manifests": [
            {"factor_id": item.factor_ref.object_id, "content_hash": item.content_hash}
            for item in manifests
        ],
    }
    _put_payload(
        artifacts,
        namespace=namespace,
        kind="freeze_batch",
        artifact_id=brief.brief_id,
        payload=freeze_index,
        input_refs=(_brief_ref(brief),),
        append_only=True,
    )
    _write_json(out / FREEZE_INDEX_NAME, freeze_index)
    return PhaseResult(
        phase="freeze",
        brief_id=brief.brief_id,
        brief_hash=brief.content_hash,
        data_version=brief.data_version,
        output_dir=str(out),
        observed_panel_end=None,
        contains_sealed_rows=False,
        factor_ids=tuple(approve),
        manifest_hashes=tuple(item.content_hash for item in manifests),
    )


def _frozen_batch(
    brief: ResearchBrief, artifacts: DataManagerArtifactStore, out: Path
) -> list[tuple[FactorSpec, FreezeManifest]]:
    namespace = brief.provenance.namespace
    batch = artifacts.get_by_identity(
        namespace=namespace, kind="freeze_batch", artifact_id=brief.brief_id
    )
    if (
        batch.get("brief_hash") != brief.content_hash
        or batch.get("data_version") != brief.data_version
    ):
        raise ValueError("freeze batch Brief mismatch")
    entries = batch.get("manifests")
    if (
        not isinstance(entries, list)
        or not entries
        or len(entries) != len({item["factor_id"] for item in entries})
    ):
        raise ValueError("freeze batch must contain the complete unique manifest list")
    if batch.get("approved") != [item["factor_id"] for item in entries]:
        raise ValueError("freeze batch approval mismatch")
    index_path = out / FREEZE_INDEX_NAME
    if index_path.is_file() and json.loads(index_path.read_text(encoding="utf-8")) != batch:
        raise ValueError("local freeze index differs from immutable freeze batch")
    result: list[tuple[FactorSpec, FreezeManifest]] = []
    for entry in entries:
        factor_id = str(entry["factor_id"])
        manifest = _load_typed(
            artifacts,
            FreezeManifest,
            namespace=namespace,
            kind="freeze_manifest",
            artifact_id=factor_id,
        )
        if (
            manifest.content_hash != entry["content_hash"]
            or manifest.manifest_id != f"freeze.{factor_id}"
        ):
            raise ValueError(f"FreezeManifest hash or identity mismatch: {factor_id}")
        if manifest.brief_ref != _brief_ref(brief) or manifest.run_id != brief.brief_id:
            raise ValueError(f"FreezeManifest Brief mismatch: {factor_id}")
        spec = _resolve_object_ref(artifacts, manifest.factor_ref)
        if (
            not isinstance(spec, FactorSpec)
            or spec.factor_id != factor_id
            or spec.brief_ref != _brief_ref(brief)
        ):
            raise ValueError(f"FreezeManifest factor mismatch: {factor_id}")
        if (
            manifest.universe != brief.universe
            or manifest.data_version != brief.data_version
            or manifest.split_refs
            != {
                brief.train.split_id: brief.train.split_id,
                brief.validation.split_id: brief.validation.split_id,
                brief.sealed.split_id: brief.sealed.split_id,
            }
            or manifest.compute_engine_version != CODE_VERSION
            or manifest.analyze_engine_version != ENGINE_VERSION
            or manifest.evaluation_protocol_id != protocol_id_for(spec)
            or manifest.direction != spec.expected_direction
            or manifest.params != spec.formula.params
            or manifest.missing_policy != spec.missing_policy
            or manifest.adjustment_policy != brief.adjustment
            or manifest.holding_horizon_bars != brief.horizon_bars
            or manifest.rebalance != brief.rebalance
            or manifest.cost != brief.cost
        ):
            raise ValueError(f"FreezeManifest protocol mismatch: {factor_id}")
        for ref in (
            manifest.preflight_ref,
            manifest.execution_ref,
            manifest.evaluation_ref,
            manifest.compare_ref,
            *manifest.review_refs,
            manifest.pool_decision_ref,
        ):
            _resolve_object_ref(artifacts, ref)
        if len(manifest.review_refs) != len(REVIEW_ROLES):
            raise ValueError(f"FreezeManifest review set mismatch: {factor_id}")
        preflight = _resolve_object_ref(artifacts, manifest.preflight_ref)
        execution = _resolve_object_ref(artifacts, manifest.execution_ref)
        validation = _resolve_object_ref(artifacts, manifest.evaluation_ref)
        compare = _resolve_object_ref(artifacts, manifest.compare_ref)
        if (
            preflight.brief_ref != manifest.brief_ref
            or preflight.factor_ref != manifest.factor_ref
            or preflight.split_id != brief.train.split_id
            or _hard_failed_report(preflight)
            or execution.brief_ref != manifest.brief_ref
            or execution.factor_ref != manifest.factor_ref
            or execution.split_id != brief.validation.split_id
            or execution.data_version != brief.data_version
            or execution.failure is not None
            or validation.factor_ref != manifest.factor_ref
            or validation.brief_ref != manifest.brief_ref
            or validation.split_id != brief.validation.split_id
            or validation.execution_ref != manifest.execution_ref
            or _hard_failed_report(validation)
            or compare.brief_ref != manifest.brief_ref
            or compare.factor_ref != manifest.factor_ref
            or compare.split_id != brief.validation.split_id
            or _hard_failed_report(compare)
        ):
            raise ValueError(f"FreezeManifest evaluation mismatch: {factor_id}")
        reviews: list[ReviewReport] = []
        for role, ref in zip(REVIEW_ROLES, manifest.review_refs, strict=True):
            review = _resolve_object_ref(artifacts, ref)
            if (
                review.role_id != role
                or review.factor_ref != manifest.factor_ref
                or review.evaluation_ref != manifest.evaluation_ref
                or _hard_failed_review(review)
            ):
                raise ValueError(f"FreezeManifest review mismatch: {factor_id}")
            reviews.append(review)
        pool = _resolve_object_ref(artifacts, manifest.pool_decision_ref)
        if pool.factor_ref != manifest.factor_ref or pool.decision is not PoolDecisionKind.ACCEPT:
            raise ValueError(f"FreezeManifest PoolDecision mismatch: {factor_id}")
        _validate_pool_acceptance(brief, compare, reviews, pool)
        approval = artifacts.get(manifest.approval_ref)
        if (
            approval.get("factor_id") != factor_id
            or approval.get("brief_id") != brief.brief_id
            or approval.get("approved") is not True
        ):
            raise ValueError(f"FreezeManifest approval mismatch: {factor_id}")
        if (
            manifest.oos_thresholds != _oos_thresholds(brief)[0]
            or manifest.oos_metric_selectors != _oos_thresholds(brief)[1]
        ):
            raise ValueError(f"FreezeManifest OOS gates mismatch: {factor_id}")
        result.append((spec, manifest))
    return result


def run_final(
    brief: ResearchBrief,
    *,
    data_root: str | Path | None = None,
    write: bool,
    output_dir: str | Path | None = None,
    panel: pd.DataFrame | None = None,
    candidates: Sequence[Mapping[str, Any]] | None = None,
) -> PhaseResult:
    if not write:
        raise ValueError("final requires --write")
    dm = _data_manager(data_root)
    artifacts = DataManagerArtifactStore(dm)
    out = Path(output_dir) if output_dir is not None else _default_output_dir(brief.brief_id)
    frozen = _frozen_batch(brief, artifacts, out)
    manifest_hashes = [manifest.content_hash for _, manifest in frozen]
    once_key = brief.content_hash
    current_specs = {spec.factor_id: spec for spec in specs_from_candidates(brief, candidates)}
    for spec, manifest in frozen:
        if current_specs.get(spec.factor_id) != spec:
            raise ValueError(f"frozen candidate implementation changed: {spec.factor_id}")
        execution = _resolve_object_ref(artifacts, manifest.execution_ref)
        _, callable_fp, _ = compile_formula(
            spec.formula,
            required_fields=spec.required_fields,
            adapter_schema_version=ADAPTER_SCHEMA_VERSION,
        )
        if callable_fp != execution.callable_fingerprint:
            raise ValueError(f"frozen callable fingerprint changed: {spec.factor_id}")

    # The rehearsal reads only the research window and runs the same adapter path.
    research_market = (
        slice_research_panel(panel, brief)
        if panel is not None
        else _load_market_panel(brief, dm, research_only=True)
    )
    assert_data_version(research_market, brief)
    with tempfile.TemporaryDirectory(prefix="factor-mining-rehearsal-") as scratch:
        scratch_dm = DataManager(data_root=scratch)
        rehearsal = _Runtime(
            brief=brief,
            specs={spec.factor_id: spec for spec, _ in frozen},
            allow_sealed=False,
            base_panel=research_market,
            artifacts=DataManagerArtifactStore(scratch_dm),
            dm=scratch_dm,
        )
        rehearsal_execution, rehearsal_analyze = _build_adapters(rehearsal)
        for spec, manifest in frozen:
            execution, report = _evaluate_split(
                rehearsal,
                spec,
                brief.validation.split_id,
                execution_adapter=rehearsal_execution,
                analyze_adapter=rehearsal_analyze,
            )
            if execution.failure is not None or _hard_failed_report(report):
                raise ValueError(f"final rehearsal failed: {spec.factor_id}")
            frozen_execution = _resolve_object_ref(artifacts, manifest.execution_ref)
            if (
                execution.callable_fingerprint != frozen_execution.callable_fingerprint
                or execution.values_content_hash != frozen_execution.values_content_hash
                or execution.valid_mask_content_hash != frozen_execution.valid_mask_content_hash
            ):
                raise ValueError(f"final rehearsal changed frozen values: {spec.factor_id}")

    payload = {
        "brief_id": brief.brief_id,
        "brief_hash": brief.content_hash,
        "manifest_hashes": manifest_hashes,
        "data_version": brief.data_version,
        "once_key": once_key,
    }
    namespace = brief.provenance.namespace
    # put_if_absent is atomic across processes: only the first final run creates this
    # artifact, and every later run stops here before any sealed row is read.
    try:
        started = artifacts.put_if_absent(
            namespace=namespace,
            kind=UNBLIND_STARTED,
            artifact_id=brief.brief_id,
            payload=payload,
            input_refs=(_brief_ref(brief),),
        )
    except ArtifactStoreAdapterError as exc:
        if exc.code is not FailureCode.DUPLICATE_LOGICAL_KEY:
            raise
        raise ValueError("sealed OOS already started for this Brief") from exc
    if not started.created:
        raise ValueError("sealed OOS already started for this Brief")
    runtime = _Runtime(
        brief=brief,
        specs={spec.factor_id: spec for spec, _ in frozen},
        allow_sealed=True,
        artifacts=artifacts,
        dm=dm,
    )
    try:
        market = panel if panel is not None else _load_market_panel(brief, dm, research_only=False)
        assert_data_version(market, brief)
        runtime.base_panel = market
        execution_adapter, analyze_adapter = _build_adapters(runtime)
        sealed_rows: list[dict[str, Any]] = []
        for spec, manifest in frozen:
            factor_id = spec.factor_id
            execution, report = _evaluate_split(
                runtime,
                spec,
                brief.sealed.split_id,
                execution_adapter=execution_adapter,
                analyze_adapter=analyze_adapter,
                sealed_execution=True,
            )
            sealed_rows.append(
                {
                    "factor_id": factor_id,
                    "execution_id": execution.execution_id,
                    "failed": execution.failure is not None or _hard_failed_report(report),
                    "rank_ic_ir": _metric(report, "rank_ic_ir"),
                    "report_hash": report.content_hash,
                    "oos_thresholds": dict(manifest.oos_thresholds),
                    "oos_metrics": {
                        key: _metric(report, selector["fact_name"])
                        for key, selector in manifest.oos_metric_selectors.items()
                    },
                    "oos_passed": oos_report_passes_frozen_thresholds(
                        report,
                        thresholds=manifest.oos_thresholds,
                        selectors=manifest.oos_metric_selectors,
                    ),
                }
            )
        completed = _put_payload(
            artifacts,
            namespace=namespace,
            kind=UNBLIND_COMPLETED,
            artifact_id=brief.brief_id,
            payload={**payload, "sealed": sealed_rows},
            input_refs=(_brief_ref(brief),),
            append_only=True,
        )
        _write_json(out / "final_summary.json", {"once_key": once_key, "sealed": sealed_rows})
        observed_end = (
            max(_panel_end(item, brief.datetime_level) for item in runtime.observed_panels)
            if runtime.observed_panels
            else None
        )
        return PhaseResult(
            phase="final",
            brief_id=brief.brief_id,
            brief_hash=brief.content_hash,
            data_version=brief.data_version,
            output_dir=str(out),
            observed_panel_end=observed_end,
            contains_sealed_rows=_contains_sealed(runtime.observed_panels, brief),
            factor_ids=tuple(spec.factor_id for spec, _ in frozen),
            manifest_hashes=tuple(manifest_hashes),
            once_key=once_key,
            event_ids=(
                f"{UNBLIND_STARTED}/{started.ref.artifact_id}",
                f"{UNBLIND_COMPLETED}/{completed.artifact_id}",
            ),
        )
    except Exception as error:
        _put_payload(
            artifacts,
            namespace=namespace,
            kind=UNBLIND_FAILED,
            artifact_id=brief.brief_id,
            payload={**payload, "error_type": type(error).__name__, "error": str(error)},
            input_refs=(_brief_ref(brief),),
            append_only=True,
        )
        raise


def run_factor_mining(
    *,
    brief: str | Path | ResearchBrief,
    phase: PhaseName,
    data_root: str | Path | None = None,
    output_dir: str | Path | None = None,
    approve: Sequence[str] = (),
    record_object: Mapping[str, Any] | None = None,
    write: bool = False,
    candidates: Sequence[Mapping[str, Any]] | None = None,
    panel: pd.DataFrame | None = None,
) -> PhaseResult:
    loaded = brief if isinstance(brief, ResearchBrief) else load_brief(brief)
    if phase == "screening":
        return run_screening(
            loaded,
            data_root=data_root,
            output_dir=output_dir,
            candidates=candidates,
            panel=panel,
        )
    if phase == "record":
        if record_object is None:
            raise ValueError("record requires --object")
        return run_record(
            loaded, data_root=data_root, record_object=record_object, output_dir=output_dir
        )
    if phase == "freeze":
        return run_freeze(
            loaded,
            data_root=data_root,
            approve=approve,
            output_dir=output_dir,
        )
    if phase == "final":
        return run_final(
            loaded,
            data_root=data_root,
            write=write,
            output_dir=output_dir,
            panel=panel,
            candidates=candidates,
        )
    raise ValueError(f"unknown phase: {phase}")


def result_to_json(result: PhaseResult) -> str:
    payload = asdict(result)
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
