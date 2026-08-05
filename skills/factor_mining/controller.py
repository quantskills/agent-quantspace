"""Deterministic Research Controller: orchestration only, no research math."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

from skills.factor_mining.adapters.analyze import (
    frozen_oos_metric_selectors,
    oos_report_passes_frozen_thresholds,
)
from skills.factor_mining.budget import (
    BudgetView,
    exhausted_keys,
    initial_budget_from_limits,
    release,
    reserve,
    settle,
)
from skills.factor_mining.contracts import (
    ArtifactRef,
    CandidateStatus,
    ControllerEvent,
    EvaluationReport,
    EvaluationRequest,
    EvidenceRef,
    FactorComputeRequest,
    FactorExecutionResult,
    FailureCode,
    FailureDetail,
    FailureKnowledgeEntry,
    FreezeManifest,
    ObjectRef,
    OOSAttempt,
    OOSAuthorization,
    OOSResult,
    Provenance,
    ReportRequest,
    ResearchBrief,
    ResearchBudget,
    ResearchRunStatus,
    ReviewConclusion,
    Severity,
    TaskLifecycleStatus,
    TaskResultStatus,
    content_hash,
    to_plain_dict,
)
from skills.factor_mining.event_chain import (
    EventChainError,
    load_run_event_payloads,
    state_after_digest_from_run_payload,
    verify_event_chain,
)
from skills.factor_mining.events import (
    build_event_body,
    event_from_body,
    hash_event_body,
)
from skills.factor_mining.identity import command_identity_key
from skills.factor_mining.isolation import (
    DEFAULT_RESEARCH_VISIBILITY,
    VIS_SEALED,
    IsolationDenied,
    assert_refs_authorized,
    assert_same_namespace,
    build_agent_task_view,
    is_sealed_marker,
)
from skills.factor_mining.objects import (
    EVENT_GATED_TYPES,
    ObjectStoreError,
    load_formal_payload,
    load_staging_payload,
    put_formal_object,
    put_staging_object,
    resolve_typed_object,
)
from skills.factor_mining.policies import evaluate_stop_reason, stop_event_details
from skills.factor_mining.ports import AnalyzePort, ArtifactStorePort, FactorExecutionPort
from skills.factor_mining.replay_semantics import (
    ReplaySemanticsError,
    replay_with_semantics,
)
from skills.factor_mining.snapshots import (
    FreezeGateError,
    build_freeze_manifest,
    require_complete_refs,
    require_gate1_approval,
    require_pool_accept,
    validate_freeze_evidence_refs,
)
from skills.factor_mining.state import (
    PHASE04_RUN_TERMINAL,
    CandidateAggregate,
    IllegalTransitionError,
    RunAggregate,
    TaskAggregate,
    transition_candidate,
    transition_run,
    transition_task,
)

KIND_SNAPSHOT = "controller_snapshot"
KIND_EVENT = "controller_event"
KIND_GATE1 = "gate1_approval"
KIND_FAILURE_KNOWLEDGE = "failure_knowledge"
KIND_OBJECT = "controller_object"
KIND_STAGING = "controller_staging"
KIND_COMMAND_RESULT = "controller_command_result"
KIND_OOS_ATTEMPT = "oos_attempt_ledger"
KIND_GATE2 = "gate2_approval"
KIND_RELEASE_KNOWLEDGE = "release_knowledge"

PORT_BEARING_COMMANDS = frozenset({"run_candidate_pipeline"})

# Capability names required per command (not role whitelist — grants injected).
COMMAND_CAPABILITIES: dict[str, frozenset[str]] = {
    "create_run": frozenset({"run.write"}),
    "activate": frozenset({"run.write"}),
    "propose_candidate": frozenset({"candidate.write"}),
    "run_candidate_pipeline": frozenset({"candidate.pipeline"}),
    "revise_candidate": frozenset({"candidate.write"}),
    "submit_review": frozenset({"review.write"}),
    "submit_pool_decision": frozenset({"pool.write"}),
    "record_gate1_approval": frozenset({"gate1.record"}),
    "authorize_oos": frozenset({"oos.authorize"}),
    "complete_oos": frozenset({"oos.execute"}),
    "record_gate2_approval": frozenset({"gate2.record"}),
    "promote": frozenset({"release.promote"}),
    "request_freeze": frozenset({"freeze.request"}),
    "freeze": frozenset({"freeze.commit"}),
    "reject_candidate": frozenset({"candidate.write"}),
    "reject_run": frozenset({"run.write"}),
    "stop": frozenset({"run.write"}),
    "claim_task": frozenset({"task.write"}),
    "start_task": frozenset({"task.write"}),
    "submit_task": frozenset({"task.write"}),
    "fail_task": frozenset({"task.write"}),
    "cancel_task": frozenset({"task.write"}),
    "timeout_task": frozenset({"task.write"}),
    "create_task": frozenset({"task.write"}),
    "build_task_view": frozenset({"task.read"}),
}


@dataclass(frozen=True)
class CommandRequest:
    command: str
    run_id: str
    aggregate_id: str
    idempotency_key: str
    actor_id: str
    role_id: str
    expected_version: int | None = None
    parent_task_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    run: RunAggregate | None = None
    failure: FailureDetail | None = None
    event: ControllerEvent | None = None
    replayed: bool = False
    outputs: Mapping[str, Any] = field(default_factory=dict)


class _OOSExecutionFailure(Exception):
    """Internal typed boundary for a post-claim sealed execution failure."""

    def __init__(self, failure: FailureDetail) -> None:
        super().__init__(failure.message)
        self.failure = failure


def _default_capability_check(role_id: str, capability: str) -> bool:
    """Fail-closed default — callers must inject SKILL-backed grants."""
    _ = (role_id, capability)
    return False


def _default_gate1_verifier(
    payload: Mapping[str, Any], request: CommandRequest
) -> None:
    """Reject agent self-approval unless a trusted verifier is injected."""
    _ = payload
    raise IsolationDenied(
        FailureDetail(
            code=FailureCode.FORBIDDEN_INPUT,
            message="Gate-1 requires injected trusted human approval verifier",
            details={"role_id": request.role_id, "actor_id": request.actor_id},
        )
    )


def _default_gate2_verifier(
    payload: Mapping[str, Any], request: CommandRequest
) -> None:
    """Reject agent self-approval unless a trusted verifier is injected."""
    _ = payload
    raise IsolationDenied(
        FailureDetail(
            code=FailureCode.FORBIDDEN_INPUT,
            message="Gate-2 requires injected trusted human approval verifier",
            details={"role_id": request.role_id, "actor_id": request.actor_id},
        )
    )


class ResearchController:
    """Orchestrates Phase 02/03 ports with fail-fast state control."""

    def __init__(
        self,
        *,
        store: ArtifactStorePort,
        analyze: AnalyzePort,
        execution: FactorExecutionPort,
        resolve_brief: Callable[[ObjectRef], ResearchBrief] | None = None,
        resolve_object: Callable[[ObjectRef], Mapping[str, Any]] | None = None,
        capability_check: Callable[[str, str], bool] | None = None,
        gate1_verifier: Callable[[Mapping[str, Any], CommandRequest], None] | None = None,
        gate2_verifier: Callable[[Mapping[str, Any], CommandRequest], None] | None = None,
        oos_request_factory: Callable[
            [FreezeManifest, OOSAuthorization],
            tuple[FactorComputeRequest, EvaluationRequest],
        ]
        | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self._store = store
        self._analyze = analyze
        self._execution = execution
        self._resolve_brief = resolve_brief
        self._resolve_object = resolve_object
        self._capability_check = capability_check or _default_capability_check
        self._gate1_verifier = gate1_verifier or _default_gate1_verifier
        self._gate2_verifier = gate2_verifier or _default_gate2_verifier
        self._oos_request_factory = oos_request_factory
        self._now = now or (lambda: datetime.now(timezone.utc).isoformat())

    # ------------------------------------------------------------------ public
    def handle(self, request: CommandRequest) -> CommandResult:
        try:
            return self._handle(request)
        except IsolationDenied as exc:
            return CommandResult(ok=False, failure=exc.failure)
        except FreezeGateError as exc:
            return CommandResult(ok=False, failure=exc.failure)
        except IllegalTransitionError as exc:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.INVALID_STATE,
                    message=str(exc),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="indeterminate controller failure; manual recovery required",
                    retryable=False,
                    details={"cause_type": type(exc).__name__, "cause": str(exc)},
                ),
            )

    def load_run(self, *, namespace: str, run_id: str) -> RunAggregate | None:
        """Load run from authoritative event chain only.

        Snapshots are cache; a snapshot-only run is never valid.
        """
        events = self._load_event_chain(namespace=namespace, run_id=run_id)
        if not events:
            return None
        return self.replay_events(namespace=namespace, run_id=run_id, events=events)

    def build_release_report_request(
        self, *, namespace: str, run_id: str, title: str
    ) -> ReportRequest:
        """Return the complete trusted ReportPort closure for a sealed release.

        This is intentionally not an AgentTaskView.  Callers hand it only to a
        trusted ReportPort after OOS testing/final decision; the request carries
        refs and formal facts, never panel values or derived OOS summaries.
        """
        run = self.load_run(namespace=namespace, run_id=run_id)
        if run is None:
            raise ValueError(f"run not found: {run_id}")
        if run.status not in {
            ResearchRunStatus.OOS_TESTED,
            ResearchRunStatus.PROMOTED,
            ResearchRunStatus.REJECTED,
        }:
            raise ValueError("release report requires OOS-tested or terminal run")
        if run.oos_authorization_ref is None or run.freeze_manifest_ref is None:
            raise ValueError("release report requires manifest and OOS authorization")
        auth = resolve_typed_object(
            self._store, run.oos_authorization_ref, allow_staging=False
        )
        if not isinstance(auth, OOSAuthorization):
            raise ValueError("release report authorization type mismatch")
        cand = run.candidates.get(auth.candidate_id)
        if cand is None:
            raise ValueError("release report authorized candidate missing")
        object_refs = [
            run.brief_ref,
            cand.factor_ref,
            run.freeze_manifest_ref,
            run.oos_authorization_ref,
        ]
        evidence_refs: list[EvidenceRef] = []
        if run.oos_result_ref is not None:
            result = resolve_typed_object(
                self._store, run.oos_result_ref, allow_staging=False
            )
            if not isinstance(result, OOSResult):
                raise ValueError("release report OOS result type mismatch")
            object_refs.append(run.oos_result_ref)
            evidence_refs.extend(result.evidence_refs)
            oos_artifacts = list(result.artifact_refs)
        else:
            oos_artifacts = []
        artifact_refs = [run.gate1_approval_ref, *run.oos_attempt_refs, *oos_artifacts]
        if run.gate2_approval_ref is not None:
            artifact_refs.append(run.gate2_approval_ref)
        if run.release_knowledge_ref is not None:
            artifact_refs.append(run.release_knowledge_ref)
        if any(ref is None for ref in artifact_refs):
            raise ValueError("release report missing Gate-1 approval")
        artifacts = tuple(ref for ref in artifact_refs if ref is not None)
        report_identity = {
            "run_id": run.run_id,
            "title": title,
            "object_refs": [to_plain_dict(ref) for ref in object_refs],
            "artifact_refs": [to_plain_dict(ref) for ref in artifacts],
        }
        request_id = f"release-report-{content_hash(report_identity)}"
        return ReportRequest(
            request_id=request_id,
            namespace=namespace,
            run_id=run.run_id,
            title=title,
            object_refs=tuple(object_refs),
            evidence_refs=tuple(evidence_refs),
            artifact_refs=artifacts,
        )

    def replay_events(
        self, *, namespace: str, run_id: str, events: Sequence[Mapping[str, Any]]
    ) -> RunAggregate:
        """Rebuild aggregate from an ordered event chain with full validation."""
        if not events:
            raise ValueError("events required")
        try:
            verified = verify_event_chain(
                events, namespace=namespace, run_id=run_id
            )
        except EventChainError as exc:
            # Preserve historical ValueError messages expected by Phase04 tests.
            msg = exc.failure.message
            if "namespace" in msg:
                raise ValueError("event namespace mismatch") from exc
            if "run_id" in msg:
                raise ValueError("event run_id mismatch") from exc
            if "sequence" in msg:
                raise ValueError(f"event sequence gap at {exc.failure.details.get('expected', '?')}") from exc
            if "prev_hash" in msg:
                raise ValueError("event chain prev_hash mismatch") from exc
            if "event hash" in msg or "HASH_MISMATCH" in str(exc.failure.code):
                raise ValueError("event hash mismatch") from exc
            raise ValueError(msg) from exc
        try:
            return replay_with_semantics(
                verified,
                namespace=namespace,
                run_id=run_id,
                external_validator=self._validate_replay_external_bindings,
            )
        except ReplaySemanticsError as exc:
            raise ValueError(exc.failure.message) from exc

    # --------------------------------------------------------------- dispatch
    def _handle(self, request: CommandRequest) -> CommandResult:
        self._assert_capabilities(request)

        if request.command == "create_run":
            return self._cmd_create_run(request)

        # Prefer command-result artifact for exactly-once before loading ports.
        prior = self._read_command_result(request)
        if prior is not None:
            return prior

        run = self._require_run(request)
        idem_key = self._idempotency_index_key(request)
        if idem_key in run.idempotency:
            # Reconstruct original CommandResult from verified event prefix.
            # pipeline_started-only ledger yields exact RECOVERY_REQUIRED (ok=False).
            return self._result_from_idem_entry(run, run.idempotency[idem_key])

        if (
            request.expected_version is not None
            and request.expected_version != run.version
        ):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_STATE,
                    message="expected_version conflict",
                    details={
                        "expected": request.expected_version,
                        "actual": run.version,
                    },
                ),
            )

        handlers = {
            "activate": self._cmd_activate,
            "propose_candidate": self._cmd_propose_candidate,
            "run_candidate_pipeline": self._cmd_run_candidate_pipeline,
            "revise_candidate": self._cmd_revise_candidate,
            "submit_review": self._cmd_submit_review,
            "submit_pool_decision": self._cmd_submit_pool_decision,
            "record_gate1_approval": self._cmd_record_gate1,
            "authorize_oos": self._cmd_authorize_oos,
            "complete_oos": self._cmd_complete_oos,
            "record_gate2_approval": self._cmd_record_gate2,
            "promote": self._cmd_promote,
            "request_freeze": self._cmd_request_freeze,
            "freeze": self._cmd_freeze,
            "reject_candidate": self._cmd_reject_candidate,
            "reject_run": self._cmd_reject_run,
            "stop": self._cmd_stop,
            "claim_task": self._cmd_claim_task,
            "start_task": self._cmd_start_task,
            "submit_task": self._cmd_submit_task,
            "fail_task": self._cmd_fail_task,
            "cancel_task": self._cmd_cancel_task,
            "timeout_task": self._cmd_timeout_task,
            "create_task": self._cmd_create_task,
            "build_task_view": self._cmd_build_task_view,
        }
        handler = handlers.get(request.command)
        if handler is None:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message=f"unknown command {request.command!r}",
                ),
            )
        return handler(request, run)

    def _assert_capabilities(self, request: CommandRequest) -> None:
        required = COMMAND_CAPABILITIES.get(request.command, frozenset())
        for cap in required:
            if not self._capability_check(request.role_id, cap):
                raise IsolationDenied(
                    FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message="role lacks required capability for command",
                        details={
                            "role_id": request.role_id,
                            "command": request.command,
                            "capability": cap,
                        },
                    )
                )

    # --------------------------------------------------------------- commands
    def _cmd_create_run(self, request: CommandRequest) -> CommandResult:
        payload = dict(request.payload)
        namespace = str(payload["namespace"])
        brief_ref = ObjectRef(**dict(payload["brief_ref"]))
        assert_same_namespace(namespace, [brief_ref])
        try:
            self._load_brief(brief_ref)
            assert_refs_authorized(
                self._store,
                namespace=namespace,
                refs=[brief_ref],
                allow_sealed=False,
            )
        except (FreezeGateError, IsolationDenied) as exc:
            failure = getattr(exc, "failure", None)
            return CommandResult(
                ok=False,
                failure=(
                    failure
                    if isinstance(failure, FailureDetail)
                    else FailureDetail(
                        code=FailureCode.INVALID_REFERENCE,
                        message="create_run brief_ref is not authorized",
                    )
                ),
            )

        existing = self.load_run(namespace=namespace, run_id=request.run_id)
        if existing is not None:
            idem_key = self._idempotency_index_key(request)
            if idem_key in existing.idempotency:
                return self._result_from_idem_entry(existing, existing.idempotency[idem_key])
            prior = self._read_command_result(request)
            if prior is not None:
                return prior
            return CommandResult(
                ok=False,
                run=existing,
                failure=FailureDetail(
                    code=FailureCode.DUPLICATE_LOGICAL_KEY,
                    message="run already exists",
                ),
            )

        prior = self._read_command_result(request)
        if prior is not None:
            return prior

        budget_limits = dict(payload.get("budget_limits") or {})
        if not budget_limits:
            brief = self._load_brief(brief_ref)
            budget_limits = {
                "candidates": brief.budget.max_candidates,
                "experiments": brief.budget.max_experiments,
                "revisions": brief.budget.max_revisions,
                "debate_rounds": brief.budget.max_debate_rounds,
            }
        view = initial_budget_from_limits(budget_limits)
        run = RunAggregate(
            run_id=request.run_id,
            namespace=namespace,
            brief_ref=brief_ref,
            status=ResearchRunStatus.BRIEFED,
            version=1,
            budget_limits=view.limits,
            budget_remaining=view.remaining,
        )
        # Event sequence artifact is the create CAS (no side version claim).
        return self._commit(
            request,
            run,
            from_status="none",
            to_status=run.status.value,
        )

    def _cmd_activate(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        new_status = transition_run(run.status, "activate")
        updated = replace(run, status=new_status)
        return self._commit(
            request,
            updated,
            from_status=run.status.value,
            to_status=new_status.value,
        )

    def _cmd_propose_candidate(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        if run.status is not ResearchRunStatus.ACTIVE:
            return self._invalid_state(run, "run must be active to propose")
        stop = evaluate_stop_reason(run, action="propose_candidate")
        if stop:
            return self._stop_blocked(run, stop)
        factor_ref = ObjectRef(**dict(request.payload["factor_ref"]))
        # FactorSpec must exist as a formal object (fail closed on missing refs).
        try:
            load_formal_payload(self._store, factor_ref, allow_staging=False)
        except ObjectStoreError as exc:
            return CommandResult(ok=False, failure=exc.failure)
        assert_refs_authorized(
            self._store, namespace=run.namespace, refs=[factor_ref], allow_sealed=False
        )
        candidate_id = request.aggregate_id
        if candidate_id in run.candidates:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.DUPLICATE_LOGICAL_KEY,
                    message="candidate already exists",
                ),
            )
        reservation_id = f"cand:{candidate_id}:{request.idempotency_key}"
        budget = BudgetView.from_run(run)
        reserved = reserve(
            budget, reservation_id=reservation_id, amounts={"candidates": 1}
        )
        if isinstance(reserved, FailureDetail):
            return CommandResult(ok=False, run=run, failure=reserved)
        settled = settle(reserved, reservation_id=reservation_id)
        if isinstance(settled, FailureDetail):
            return CommandResult(ok=False, run=run, failure=settled)
        cand = CandidateAggregate(
            candidate_id=candidate_id,
            factor_ref=factor_ref,
            status=CandidateStatus.PROPOSED,
            revision=int(request.payload.get("revision", 1)),
            parent_ref=(
                ObjectRef(**dict(request.payload["parent_ref"]))
                if request.payload.get("parent_ref")
                else None
            ),
        )
        updated = settled.apply_to_run(run)
        candidates = dict(updated.candidates)
        candidates[candidate_id] = cand
        updated = replace(updated, candidates=candidates)
        return self._commit(
            request,
            updated,
            from_status="none",
            to_status=cand.status.value,
            budget_delta={"candidates": -1},
            input_refs=(run.brief_ref, factor_ref),
            outputs={"candidate_id": candidate_id},
        )

    def _cmd_run_candidate_pipeline(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        """preflight → execute → evaluate → compare_to_pool; hard-fail short-circuits."""
        if run.status is not ResearchRunStatus.ACTIVE:
            return self._invalid_state(run, "run must be active")
        cand = self._require_candidate(run, request.aggregate_id)
        if cand.status is not CandidateStatus.PROPOSED:
            return self._invalid_state(run, "pipeline requires Proposed candidate")

        eval_raw = request.payload["evaluation_request"]
        compute_raw = request.payload["compute_request"]
        eval_req = (
            eval_raw
            if isinstance(eval_raw, EvaluationRequest)
            else EvaluationRequest(**dict(eval_raw))
        )
        compute_req = (
            compute_raw
            if isinstance(compute_raw, FactorComputeRequest)
            else FactorComputeRequest(**dict(compute_raw))
        )

        # Lineage bind BEFORE any event or port call.
        lineage_fail = self._validate_pipeline_lineage(run, cand, eval_req, compute_req)
        if lineage_fail is not None:
            return lineage_fail

        reservation_id = f"exp:{cand.candidate_id}:{request.idempotency_key}"
        budget = BudgetView.from_run(run)
        reserved = reserve(
            budget, reservation_id=reservation_id, amounts={"experiments": 1}
        )
        if isinstance(reserved, FailureDetail):
            return CommandResult(ok=False, run=run, failure=reserved)
        # Consume budget at started boundary (external work begins after this event).
        settled = settle(reserved, reservation_id=reservation_id)
        if isinstance(settled, FailureDetail):
            return CommandResult(ok=False, run=run, failure=settled)
        run = settled.apply_to_run(run)

        # pipeline_started event: CAS via event sequence, advances version/budget.
        # No side version-claim artifacts. If terminal later fails, started remains
        # authoritative; same key returns RecoveryRequired without re-calling ports.
        started = self._commit(
            request,
            run,
            from_status=cand.status.value,
            to_status=cand.status.value,
            budget_delta={"experiments": -1},
            result_status="started",
            ok=False,
            failure=FailureDetail(
                code=FailureCode.RECOVERY_REQUIRED,
                message="pipeline_started; terminal outcome required (no automatic recompute)",
                retryable=False,
                details={
                    "pipeline_phase": "started",
                    "reservation_id": reservation_id,
                    "idempotency_key": request.idempotency_key,
                },
            ),
            input_refs=(run.brief_ref, cand.factor_ref),
            outputs={
                "pipeline_phase": "started",
                "reservation_id": reservation_id,
                "amounts": {"experiments": 1},
                "calls": [],
            },
        )
        # started commits with ok=False by design (ledger until terminal).
        # Only abort when the started event itself did not persist.
        if started.event is None or started.run is None:
            if (
                started.failure is not None
                and started.failure.code is FailureCode.DUPLICATE_LOGICAL_KEY
            ):
                return CommandResult(
                    ok=False,
                    run=run,
                    failure=FailureDetail(
                        code=FailureCode.INVALID_STATE,
                        message="pipeline_started event CAS lost",
                    ),
                )
            return started
        run = started.run
        cand = self._require_candidate(run, request.aggregate_id)

        calls: list[str] = []
        try:
            preflight = self._analyze.preflight(eval_req)
            calls.append("preflight")
            lineage = self._assert_port_output_lineage(
                run=run,
                cand=cand,
                request_obj=eval_req,
                report=preflight,
                stage="preflight",
            )
            if lineage is not None:
                return self._pipeline_reject(
                    request,
                    run,
                    cand,
                    reservation_id=reservation_id,
                    stage="preflight",
                    calls=calls,
                    forced_failure=lineage,
                )
            if preflight.failure is not None or _report_hard_failed(preflight):
                return self._pipeline_reject(
                    request,
                    run,
                    cand,
                    reservation_id=reservation_id,
                    stage="preflight",
                    report=preflight,
                    calls=calls,
                    )

            cand = replace(
                cand,
                status=transition_candidate(cand.status, "preflight_pass"),
                preflight_ref=self._persist_report_object(run, preflight),
                version=cand.version + 1,
            )

            execution = self._execution.execute(compute_req)
            calls.append("execute")
            lineage = self._assert_port_output_lineage(
                run=run,
                cand=cand,
                request_obj=compute_req,
                report=execution,
                stage="execute",
            )
            if lineage is not None:
                return self._pipeline_reject(
                    request,
                    run,
                    cand,
                    reservation_id=reservation_id,
                    stage="execute",
                    calls=calls,
                    forced_failure=lineage,
                )
            if execution.failure is not None:
                return self._pipeline_reject(
                    request,
                    run,
                    cand,
                    reservation_id=reservation_id,
                    stage="execute",
                    execution=execution,
                    calls=calls,
                )
            cand = replace(
                cand,
                status=transition_candidate(cand.status, "compute"),
                execution_ref=self._persist_execution_object(run, execution),
                version=cand.version + 1,
            )

            if isinstance(eval_raw, EvaluationRequest):
                eval_req2 = eval_req
                if eval_req2.execution_ref is None and cand.execution_ref is not None:
                    eval_req2 = replace(eval_req2, execution_ref=cand.execution_ref)
            else:
                eval_payload = dict(request.payload["evaluation_request"])
                if (
                    eval_payload.get("execution_ref") is None
                    and cand.execution_ref is not None
                ):
                    eval_payload["execution_ref"] = to_plain_dict(cand.execution_ref)
                eval_req2 = EvaluationRequest(**eval_payload)
            evaluated = self._analyze.evaluate(eval_req2)
            calls.append("evaluate")
            lineage = self._assert_port_output_lineage(
                run=run,
                cand=cand,
                request_obj=eval_req2,
                report=evaluated,
                stage="evaluate",
            )
            if lineage is not None:
                return self._pipeline_reject(
                    request,
                    run,
                    cand,
                    reservation_id=reservation_id,
                    stage="evaluate",
                    calls=calls,
                    forced_failure=lineage,
                )
            if evaluated.failure is not None or _report_hard_failed(evaluated):
                return self._pipeline_reject(
                    request,
                    run,
                    cand,
                    reservation_id=reservation_id,
                    stage="evaluate",
                    report=evaluated,
                    calls=calls,
                )
            cand = replace(
                cand,
                status=transition_candidate(cand.status, "evaluate"),
                evaluation_ref=self._persist_report_object(run, evaluated),
                version=cand.version + 1,
            )

            compared = self._analyze.compare_to_pool(eval_req2)
            calls.append("compare_to_pool")
            lineage = self._assert_port_output_lineage(
                run=run,
                cand=cand,
                request_obj=eval_req2,
                report=compared,
                stage="compare_to_pool",
            )
            if lineage is not None:
                return self._pipeline_reject(
                    request,
                    run,
                    cand,
                    reservation_id=reservation_id,
                    stage="compare_to_pool",
                    calls=calls,
                    forced_failure=lineage,
                )
            if compared.failure is not None or _report_hard_failed(compared):
                return self._pipeline_reject(
                    request,
                    run,
                    cand,
                    reservation_id=reservation_id,
                    stage="compare_to_pool",
                    report=compared,
                    calls=calls,
                )
            cand = replace(
                cand,
                status=transition_candidate(cand.status, "compare_pool"),
                compare_ref=self._persist_report_object(run, compared),
                version=cand.version + 1,
            )
        except Exception as exc:  # noqa: BLE001
            failure = FailureDetail(
                code=FailureCode.RECOVERY_REQUIRED,
                message="port call indeterminate; recovery required",
                retryable=False,
                details={
                    "cause_type": type(exc).__name__,
                    "calls": tuple(calls),
                    "reservation_id": reservation_id,
                    "pipeline_phase": "terminal",
                },
            )
            # Budget already settled at pipeline_started. Terminal event overwrites
            # idempotency; if append fails, started ledger remains authoritative.
            # from/to must describe the committed candidate, not uncommitted locals.
            committed = run.candidates[request.aggregate_id]
            return self._commit_pipeline_terminal(
                request,
                run,
                from_status=committed.status.value,
                to_status=committed.status.value,
                result_status="failed",
                failure=failure,
                input_refs=(run.brief_ref, committed.factor_ref),
                outputs={
                    "calls": calls,
                    "recovery": True,
                    "pipeline_phase": "terminal",
                },
                ok=False,
            )

        candidates = dict(run.candidates)
        candidates[cand.candidate_id] = cand
        updated = replace(run, candidates=candidates)
        stage_refs = tuple(
            ref
            for ref in (
                cand.preflight_ref,
                cand.execution_ref,
                cand.evaluation_ref,
                cand.compare_ref,
            )
            if ref is not None
        )
        return self._commit_pipeline_terminal(
            request,
            updated,
            from_status=CandidateStatus.PROPOSED.value,
            to_status=cand.status.value,
            input_refs=(run.brief_ref, cand.factor_ref),
            output_refs=stage_refs,
            outputs={
                "calls": calls,
                "candidate": cand.to_payload(),
                "evaluation_ref": to_plain_dict(cand.evaluation_ref)
                if cand.evaluation_ref
                else None,
                "pipeline_phase": "terminal",
            },
        )

    def _validate_pipeline_lineage(
        self,
        run: RunAggregate,
        cand: CandidateAggregate,
        eval_req: EvaluationRequest,
        compute_req: FactorComputeRequest,
    ) -> CommandResult | None:
        try:
            assert_same_namespace(
                run.namespace,
                [
                    cand.factor_ref,
                    eval_req.factor_ref,
                    eval_req.brief_ref,
                    compute_req.factor_ref,
                    compute_req.brief_ref,
                ],
            )
        except IsolationDenied as exc:
            return CommandResult(ok=False, run=run, failure=exc.failure)

        if eval_req.namespace != run.namespace or compute_req.namespace != run.namespace:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_REFERENCE,
                    message="request namespace mismatch",
                ),
            )
        if to_plain_dict(eval_req.brief_ref) != to_plain_dict(run.brief_ref):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="evaluation brief_ref does not exact-bind run brief",
                ),
            )
        if to_plain_dict(compute_req.brief_ref) != to_plain_dict(run.brief_ref):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="compute brief_ref does not exact-bind run brief",
                ),
            )
        if to_plain_dict(eval_req.factor_ref) != to_plain_dict(cand.factor_ref):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="evaluation factor_ref does not exact-bind candidate",
                ),
            )
        if to_plain_dict(compute_req.factor_ref) != to_plain_dict(cand.factor_ref):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="compute factor_ref does not exact-bind candidate",
                ),
            )
        brief = self._load_brief(run.brief_ref)
        if compute_req.data_version != brief.data_version:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="compute data_version mismatch vs brief",
                ),
            )
        if eval_req.data_version != brief.data_version:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="evaluation data_version mismatch vs brief",
                ),
            )
        if compute_req.split_id not in {brief.train.split_id, brief.validation.split_id}:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="compute split_id not in authorized brief splits",
                ),
            )
        if eval_req.split_id != compute_req.split_id:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="evaluation/compute split_id mismatch",
                ),
            )
        return None

    def _cmd_revise_candidate(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        parent = self._require_candidate(run, str(request.payload["parent_candidate_id"]))
        if parent.status in {
            CandidateStatus.FROZEN,
            CandidateStatus.PROMOTED,
        }:
            return self._invalid_state(run, "cannot revise frozen/promoted candidate")
        reservation_id = f"rev:{request.aggregate_id}:{request.idempotency_key}"
        budget = BudgetView.from_run(run)
        reserved = reserve(
            budget, reservation_id=reservation_id, amounts={"revisions": 1}
        )
        if isinstance(reserved, FailureDetail):
            return CommandResult(ok=False, run=run, failure=reserved)
        settled = settle(reserved, reservation_id=reservation_id)
        if isinstance(settled, FailureDetail):
            return CommandResult(ok=False, run=run, failure=settled)
        factor_ref = ObjectRef(**dict(request.payload["factor_ref"]))
        assert_refs_authorized(
            self._store,
            namespace=run.namespace,
            refs=[factor_ref, parent.factor_ref],
            allow_sealed=False,
        )
        new_cand = CandidateAggregate(
            candidate_id=request.aggregate_id,
            factor_ref=factor_ref,
            status=CandidateStatus.PROPOSED,
            parent_ref=parent.factor_ref,
            revision=parent.revision + 1,
        )
        updated = settled.apply_to_run(run)
        candidates = dict(updated.candidates)
        candidates[new_cand.candidate_id] = new_cand
        updated = replace(updated, candidates=candidates)
        return self._commit(
            request,
            updated,
            from_status=parent.status.value,
            to_status=new_cand.status.value,
            budget_delta={"revisions": -1},
            input_refs=(parent.factor_ref, new_cand.factor_ref),
            outputs={
                "candidate_id": new_cand.candidate_id,
                "revision": new_cand.revision,
                "parent_candidate_id": parent.candidate_id,
            },
        )

    def _cmd_submit_review(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        cand = self._require_candidate(run, request.aggregate_id)
        if cand.status not in {
            CandidateStatus.REVIEW_PENDING,
            CandidateStatus.DEBATING,
            CandidateStatus.SYNTHESIZING,
        }:
            return self._invalid_state(run, "candidate not ready for review")
        if cand.evaluation_ref is None:
            return self._invalid_state(run, "evaluation_ref required before review")
        review_ref = ObjectRef(**dict(request.payload["review_ref"]))
        try:
            review = resolve_typed_object(self._store, review_ref, allow_staging=False)
        except ObjectStoreError as exc:
            return CommandResult(ok=False, failure=exc.failure)
        from skills.factor_mining.contracts import ReviewReport

        if not isinstance(review, ReviewReport):
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.SCHEMA_MISMATCH,
                    message="review_ref must resolve to ReviewReport",
                ),
            )
        if to_plain_dict(review.factor_ref) != to_plain_dict(cand.factor_ref):
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="ReviewReport.factor_ref must exact-bind candidate",
                ),
            )
        if to_plain_dict(review.evaluation_ref) != to_plain_dict(cand.evaluation_ref):
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="ReviewReport.evaluation_ref must exact-bind candidate evaluation",
                ),
            )
        # Reject duplicate role or duplicate ref.
        existing_roles: set[str] = set()
        for prev in cand.review_refs:
            try:
                prev_obj = resolve_typed_object(self._store, prev, allow_staging=False)
                existing_roles.add(str(getattr(prev_obj, "role_id", "")))
            except ObjectStoreError as exc:
                return CommandResult(ok=False, failure=exc.failure)
            if to_plain_dict(prev) == to_plain_dict(review_ref):
                return CommandResult(
                    ok=False,
                    failure=FailureDetail(
                        code=FailureCode.DUPLICATE_LOGICAL_KEY,
                        message="duplicate review_ref",
                    ),
                )
        if review.role_id in existing_roles:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.DUPLICATE_LOGICAL_KEY,
                    message="duplicate review role_id for candidate",
                    details={"role_id": review.role_id},
                ),
            )
        assert_refs_authorized(
            self._store, namespace=run.namespace, refs=[review_ref], allow_sealed=False
        )
        reviews = tuple(cand.review_refs) + (review_ref,)
        # Authority is persisted ReviewReport.conclusion — never caller hard_reject.
        # Never bypass transition tables with IllegalTransitionError fallbacks.
        conclusion = review.conclusion
        if isinstance(conclusion, str):
            conclusion = ReviewConclusion(conclusion)
        try:
            if conclusion is ReviewConclusion.FAIL:
                new_status = transition_candidate(cand.status, "reject")
                cand2 = replace(
                    cand,
                    review_refs=reviews,
                    status=new_status,
                    version=cand.version + 1,
                )
            elif conclusion is ReviewConclusion.DEBATE:
                new_status = transition_candidate(cand.status, "mark_debating")
                cand2 = replace(
                    cand,
                    review_refs=reviews,
                    status=new_status,
                    version=cand.version + 1,
                )
            elif conclusion is ReviewConclusion.REVISE:
                new_status = transition_candidate(cand.status, "mark_synthesizing")
                cand2 = replace(
                    cand,
                    review_refs=reviews,
                    status=new_status,
                    version=cand.version + 1,
                )
            elif conclusion is ReviewConclusion.PASS:
                # PASS leaves lifecycle status unchanged.
                cand2 = replace(cand, review_refs=reviews, version=cand.version + 1)
            else:
                return CommandResult(
                    ok=False,
                    failure=FailureDetail(
                        code=FailureCode.INVALID_PARAMETERS,
                        message="unsupported ReviewReport.conclusion",
                        details={"conclusion": str(conclusion)},
                    ),
                )
        except IllegalTransitionError as exc:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_STATE,
                    message=str(exc),
                    details={
                        "conclusion": conclusion.value,
                        "from_status": cand.status.value,
                    },
                ),
            )
        candidates = dict(run.candidates)
        candidates[cand2.candidate_id] = cand2
        updated = replace(run, candidates=candidates)
        return self._commit(
            request,
            updated,
            from_status=cand.status.value,
            to_status=cand2.status.value,
            input_refs=(cand.evaluation_ref, review_ref),
            output_refs=(review_ref,),
            outputs={
                "review_ref": to_plain_dict(review_ref),
                "role_id": review.role_id,
                "conclusion": conclusion.value,
            },
        )

    def _cmd_submit_pool_decision(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        cand = self._require_candidate(run, request.aggregate_id)
        # Full evidence required before pool (SKILL: Pool Steward after two reviews).
        missing = []
        if cand.preflight_ref is None:
            missing.append("preflight_ref")
        if cand.execution_ref is None:
            missing.append("execution_ref")
        if cand.evaluation_ref is None:
            missing.append("evaluation_ref")
        if cand.compare_ref is None:
            missing.append("compare_ref")
        if missing:
            return self._invalid_state(
                run, f"complete evidence required before pool: {missing}"
            )
        roles_present: set[str] = set()
        for review_ref in cand.review_refs:
            try:
                review = resolve_typed_object(
                    self._store, review_ref, allow_staging=False
                )
            except ObjectStoreError as exc:
                return CommandResult(ok=False, failure=exc.failure)
            roles_present.add(str(getattr(review, "role_id", "")))
        if len(roles_present) < 2:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.INVALID_STATE,
                    message="two independent reviews required before pool",
                    details={
                        "required_distinct_roles": 2,
                        "present": sorted(roles_present),
                    },
                ),
            )
        decision_ref = ObjectRef(**dict(request.payload["pool_decision_ref"]))
        try:
            decision = resolve_typed_object(
                self._store, decision_ref, allow_staging=False
            )
        except ObjectStoreError as exc:
            return CommandResult(ok=False, failure=exc.failure)
        from skills.factor_mining.contracts import PoolDecision

        if not isinstance(decision, PoolDecision):
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.SCHEMA_MISMATCH,
                    message="pool_decision_ref must resolve to PoolDecision",
                ),
            )
        assert_refs_authorized(
            self._store, namespace=run.namespace, refs=[decision_ref], allow_sealed=False
        )
        cand_for_check = replace(cand, pool_decision_ref=decision_ref)
        # Decision kind comes from the persisted object, never caller accept bool.
        decision_payload = require_pool_accept(
            candidate=cand_for_check,
            store_get=self._store_get_object,
            require_accept=False,
        )
        decision_kind = str(decision_payload.get("decision", ""))
        if decision_kind == "accept":
            require_pool_accept(
                candidate=cand_for_check, store_get=self._store_get_object
            )
            new_status = transition_candidate(cand.status, "mark_freeze_ready")
        else:
            new_status = transition_candidate(cand.status, "reject")
        cand2 = replace(
            cand,
            pool_decision_ref=decision_ref,
            status=new_status,
            version=cand.version + 1,
        )
        candidates = dict(run.candidates)
        candidates[cand2.candidate_id] = cand2
        updated = replace(run, candidates=candidates)
        return self._commit(
            request,
            updated,
            from_status=cand.status.value,
            to_status=cand2.status.value,
            input_refs=(
                cand.evaluation_ref,
                cand.compare_ref,
                *cand.review_refs,
                decision_ref,
            ),
            output_refs=(decision_ref,),
            outputs={"pool_decision_ref": to_plain_dict(decision_ref)},
        )

    def _cmd_record_gate1(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        approval = dict(request.payload)
        approval["run_id"] = run.run_id
        candidate_id = approval.get("candidate_id")
        if not candidate_id or not isinstance(candidate_id, str):
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message="Gate-1 requires exact candidate_id",
                ),
            )
        cand = self._require_candidate(run, candidate_id)
        if cand.status is not CandidateStatus.FREEZE_READY:
            return self._invalid_state(
                run, "Gate-1 requires freeze_ready candidate with full evidence"
            )
        require_complete_refs(cand)
        if cand.preflight_ref is None or cand.execution_ref is None or cand.compare_ref is None:
            return self._invalid_state(run, "Gate-1 requires full pipeline evidence refs")
        raw_intent = approval.get("freeze_intent")
        if not isinstance(raw_intent, Mapping):
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message="Gate-1 requires complete freeze_intent mapping",
                ),
            )
        try:
            canonical_intent, fingerprint = self._validate_and_canonicalize_freeze_intent(
                run=run,
                cand=cand,
                intent_payload=dict(raw_intent),
            )
        except FreezeGateError as exc:
            return CommandResult(ok=False, failure=exc.failure)
        except ObjectStoreError as exc:
            return CommandResult(ok=False, failure=exc.failure)
        approval["candidate_id"] = candidate_id
        approval["freeze_intent"] = canonical_intent
        approval["freeze_intent_fingerprint"] = fingerprint
        if is_sealed_marker(approval):
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="Gate-1 approval must not carry sealed markers",
                ),
            )
        self._gate1_verifier(approval, request)
        if approval.get("approved") is not True:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.INVALID_STATE,
                    message="Gate-1 approval must set approved=true",
                ),
            )
        put = self._put_if_absent(
            namespace=run.namespace,
            kind=KIND_GATE1,
            artifact_id=f"{run.run_id}-{candidate_id}-{request.idempotency_key}",
            payload=approval,
            input_refs=(
                run.brief_ref,
                cand.factor_ref,
                cand.evaluation_ref,
                cand.pool_decision_ref,
                *cand.review_refs,
            ),
            meta={"human_gate": True, "sealed": False},
        )
        ref = put.ref if hasattr(put, "ref") else put
        updated = replace(run, gate1_approval_ref=ref)
        return self._commit(
            request,
            updated,
            from_status=run.status.value,
            to_status=run.status.value,
            input_refs=(run.brief_ref, cand.factor_ref),
            output_refs=(ref,),
            outputs={
                "gate1_approval_ref": to_plain_dict(ref),
                "freeze_intent_fingerprint": fingerprint,
                "candidate_id": candidate_id,
            },
        )

    def _cmd_request_freeze(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        cand = self._require_candidate(run, request.aggregate_id)
        if cand.status is not CandidateStatus.FREEZE_READY:
            return self._invalid_state(run, "candidate must be freeze_ready")
        new_status = transition_run(run.status, "request_freeze")
        updated = replace(run, status=new_status)
        return self._commit(
            request,
            updated,
            from_status=run.status.value,
            to_status=new_status.value,
            input_refs=(run.brief_ref, cand.factor_ref),
        )

    def _cmd_freeze(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        if run.status is not ResearchRunStatus.FREEZE_PENDING:
            return self._invalid_state(run, "run must be freeze_pending")
        cand = self._require_candidate(run, request.aggregate_id)
        if cand.status is not CandidateStatus.FREEZE_READY:
            return self._invalid_state(run, "candidate must be freeze_ready")
        approval = require_gate1_approval(
            run, store_get=self._store.get, candidate_id=cand.candidate_id
        )
        approval_payload = self._store.get(approval)
        if approval_payload.get("candidate_id") != cand.candidate_id:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="Gate-1 candidate_id mismatch",
                ),
            )
        stored_intent = approval_payload.get("freeze_intent")
        if not isinstance(stored_intent, Mapping):
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.INVALID_REFERENCE,
                    message="Gate-1 approval missing freeze_intent",
                ),
            )
        # Freeze may not introduce or change any freeze-critical field after Gate-1.
        for forbidden in (
            "manifest_id",
            "compute_engine_version",
            "analyze_engine_version",
            "evaluation_protocol_id",
            "outlier_policy",
            "neutralization_policy",
            "rebalance",
            "pool_baseline_refs",
            "oos_thresholds",
            "oos_metric_selectors",
            "direction",
            "params",
            "missing_policy",
            "adjustment_policy",
            "holding_horizon_bars",
            "freeze_intent",
        ):
            if forbidden in request.payload:
                return CommandResult(
                    ok=False,
                    failure=FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message="freeze must not mutate Gate-1 approved intent fields",
                        details={"field": forbidden},
                    ),
                )
        try:
            canonical_intent, fingerprint = self._validate_and_canonicalize_freeze_intent(
                run=run,
                cand=cand,
                intent_payload=dict(stored_intent),
            )
        except FreezeGateError as exc:
            return CommandResult(ok=False, failure=exc.failure)
        except ObjectStoreError as exc:
            return CommandResult(ok=False, failure=exc.failure)
        if str(approval_payload.get("freeze_intent_fingerprint") or "") != fingerprint:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="Gate-1 freeze intent fingerprint mismatch",
                ),
            )
        if to_plain_dict(stored_intent) != canonical_intent:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="Gate-1 freeze_intent body mismatch vs canonical rebuild",
                ),
            )
        require_pool_accept(candidate=cand, store_get=self._store_get_object)
        require_complete_refs(cand)
        validate_freeze_evidence_refs(
            run=run,
            candidate=cand,
            store_get_object=self._store_get_object,
            store=self._store,
        )
        brief = self._load_brief(run.brief_ref)
        manifest = build_freeze_manifest(
            manifest_id=str(canonical_intent["manifest_id"]),
            run=run,
            candidate=cand,
            brief=brief,
            approval_ref=approval,
            compute_engine_version=str(canonical_intent["compute_engine_version"]),
            analyze_engine_version=str(canonical_intent["analyze_engine_version"]),
            evaluation_protocol_id=str(canonical_intent["evaluation_protocol_id"]),
            direction=str(canonical_intent["direction"]),
            params=dict(canonical_intent["params"]),
            missing_policy=str(canonical_intent["missing_policy"]),
            adjustment_policy=str(canonical_intent["adjustment_policy"]),
            outlier_policy=str(canonical_intent["outlier_policy"]),
            neutralization_policy=str(canonical_intent["neutralization_policy"]),
            holding_horizon_bars=int(canonical_intent["holding_horizon_bars"]),
            rebalance=str(canonical_intent["rebalance"]),
            cost=brief.cost,
            pool_baseline_refs=tuple(
                ObjectRef(**dict(item))
                for item in canonical_intent["pool_baseline_refs"]
            ),
            oos_thresholds=dict(canonical_intent["oos_thresholds"]),
            oos_metric_selectors=dict(canonical_intent["oos_metric_selectors"]),
            provenance=brief.provenance,
            split_refs=dict(canonical_intent["split_refs"]),
        )
        closed_inputs: list = [
            run.brief_ref,
            cand.factor_ref,
            approval,
        ]
        for ref in (
            cand.preflight_ref,
            cand.execution_ref,
            cand.evaluation_ref,
            cand.compare_ref,
            cand.pool_decision_ref,
            *cand.review_refs,
        ):
            if ref is not None:
                closed_inputs.append(ref)
        for item in canonical_intent["pool_baseline_refs"]:
            closed_inputs.append(ObjectRef(**dict(item)))
        try:
            manifest_ref = put_staging_object(
                self._store,
                namespace=run.namespace,
                object_type="FreezeManifest",
                object_id=manifest.manifest_id,
                body=to_plain_dict(manifest),
                input_refs=tuple(closed_inputs),
            )
        except ObjectStoreError as exc:
            return CommandResult(ok=False, failure=exc.failure)
        except Exception as exc:  # noqa: BLE001
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="freeze staging failed",
                    details={"cause_type": type(exc).__name__},
                ),
            )

        cand2 = replace(
            cand,
            status=transition_candidate(cand.status, "freeze"),
            freeze_manifest_ref=manifest_ref,
            version=cand.version + 1,
        )
        run_status = transition_run(run.status, "freeze")
        candidates = dict(run.candidates)
        candidates[cand2.candidate_id] = cand2
        updated = replace(
            run,
            status=run_status,
            candidates=candidates,
            freeze_manifest_ref=manifest_ref,
        )
        return self._commit(
            request,
            updated,
            from_status=run.status.value,
            to_status=run_status.value,
            input_refs=tuple(closed_inputs),
            output_refs=(manifest_ref,),
            outputs={
                "manifest_ref": to_plain_dict(manifest_ref),
                "manifest_hash": manifest.content_hash,
                "staging_content_hash": manifest_ref.content_hash,
                "staging_kind": KIND_STAGING,
                "staging_artifact_id": f"FreezeManifest-{manifest.manifest_id}",
                "freeze_intent_fingerprint": fingerprint,
                "manifest": to_plain_dict(manifest),
            },
        )

    # --------------------------------------------------------- sealed OOS
    def _cmd_authorize_oos(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        """Create the one sealed execution authorization from frozen lineage only."""
        forbidden = set(request.payload) - {"namespace"}
        if forbidden:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="authorize_oos accepts no caller-selected OOS inputs",
                    details={"fields": sorted(forbidden)},
                ),
            )
        context = self._oos_context(run, request.aggregate_id)
        if isinstance(context, CommandResult):
            return context
        cand, manifest_ref, manifest, gate1_ref = context
        if run.oos_authorization_ref is not None:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.OOS_ALREADY_CONSUMED,
                    message="sealed OOS authorization already exists for frozen run",
                ),
            )
        sealed_split_id = str(manifest.split_refs["sealed"])
        one_shot_key = self._oos_one_shot_key(
            run=run,
            candidate=cand,
            manifest_ref=manifest_ref,
            sealed_split_id=sealed_split_id,
        )
        authorization = OOSAuthorization(
            authorization_id=f"oos-auth-{one_shot_key}",
            run_id=run.run_id,
            candidate_id=cand.candidate_id,
            manifest_ref=manifest_ref,
            sealed_split_id=sealed_split_id,
            one_shot_key=one_shot_key,
            issued_at=self._now(),
        )
        try:
            auth_ref = put_formal_object(
                self._store,
                namespace=run.namespace,
                object_type="OOSAuthorization",
                object_id=authorization.authorization_id,
                body=to_plain_dict(authorization),
                input_refs=(run.brief_ref, cand.factor_ref, manifest_ref, gate1_ref),
                meta={"sealed": True, "append_only": True},
            )
        except ObjectStoreError as exc:
            return CommandResult(ok=False, run=run, failure=exc.failure)
        updated = replace(run, oos_authorization_ref=auth_ref)
        return self._commit(
            request,
            updated,
            from_status=run.status.value,
            to_status=run.status.value,
            input_refs=(run.brief_ref, cand.factor_ref, manifest_ref, gate1_ref),
            output_refs=(auth_ref,),
            outputs={
                "candidate_id": cand.candidate_id,
                "authorization_ref": to_plain_dict(auth_ref),
            },
        )

    def _cmd_complete_oos(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        """Claim once, then run the sealed execution/evaluation exactly once.

        The first append-only ``started`` ledger write consumes the OOS interval.
        A process crash after that write is intentionally unrecoverable by retry:
        a human must stop the run and create a new independent brief/interval.
        """
        if run.status is ResearchRunStatus.OOS_TESTED:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.OOS_ALREADY_CONSUMED,
                    message="sealed OOS attempt is already terminal; refusing recompute",
                ),
            )
        forbidden = set(request.payload) - {"namespace"}
        if forbidden:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="complete_oos accepts no caller-selected OOS inputs",
                    details={"fields": sorted(forbidden)},
                ),
            )
        context = self._oos_context(run, request.aggregate_id)
        if isinstance(context, CommandResult):
            return context
        cand, manifest_ref, manifest, gate1_ref = context
        auth = self._load_oos_authorization(run, cand, manifest_ref, manifest)
        if isinstance(auth, CommandResult):
            return auth
        auth_ref, authorization = auth
        attempt_started = OOSAttempt(
            attempt_id=f"oos-attempt-{authorization.one_shot_key}",
            authorization_id=authorization.authorization_id,
            run_id=run.run_id,
            candidate_id=cand.candidate_id,
            manifest_ref=manifest_ref,
            sealed_split_id=authorization.sealed_split_id,
            one_shot_key=authorization.one_shot_key,
            started_at=self._now(),
        )
        start_id = f"oos-start-{authorization.one_shot_key}"
        try:
            started_put = self._put_if_absent(
                namespace=run.namespace,
                kind=KIND_OOS_ATTEMPT,
                artifact_id=start_id,
                payload=to_plain_dict(attempt_started),
                input_refs=(run.brief_ref, cand.factor_ref, manifest_ref, auth_ref),
                meta={"sealed": True, "append_only": True, "phase": "started"},
            )
        except Exception as exc:  # noqa: BLE001
            # A restarted worker may rebuild the same one-shot identity with a
            # different wall-clock timestamp.  Identity existence still means
            # consumed; never downgrade that fact to a retryable recovery.
            getter = getattr(self._store, "get_by_identity", None)
            if callable(getter):
                try:
                    getter(
                        namespace=run.namespace,
                        kind=KIND_OOS_ATTEMPT,
                        artifact_id=start_id,
                    )
                except Exception:  # noqa: BLE001
                    pass
                else:
                    return CommandResult(
                        ok=False,
                        run=run,
                        failure=FailureDetail(
                            code=FailureCode.OOS_ALREADY_CONSUMED,
                            message="sealed OOS interval was already claimed; refusing recompute",
                        ),
                    )
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="sealed OOS claim could not be persisted",
                    details={"cause_type": type(exc).__name__},
                ),
            )
        if not bool(getattr(started_put, "created", True)):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.OOS_ALREADY_CONSUMED,
                    message="sealed OOS interval was already claimed; refusing recompute",
                ),
            )
        started_ref = started_put.ref if hasattr(started_put, "ref") else started_put

        try:
            compute_req, eval_req = self._build_oos_requests(manifest, authorization)
            execution = self._execution.execute(compute_req)
            execution_failure = self._assert_port_output_lineage(
                run=run,
                cand=cand,
                request_obj=compute_req,
                report=execution,
                stage="sealed_oos_execute",
            )
            if execution_failure is not None:
                raise _OOSExecutionFailure(execution_failure)
            if execution.failure is not None:
                raise _OOSExecutionFailure(execution.failure)
            if execution.provenance.code_version != manifest.compute_engine_version:
                raise _OOSExecutionFailure(
                    FailureDetail(
                        code=FailureCode.HASH_MISMATCH,
                        message=(
                            "sealed OOS execution code_version drifted from "
                            "frozen manifest"
                        ),
                    )
                )
            execution_ref = self._persist_execution_object(
                run, execution, sealed=True
            )
            eval_req = replace(eval_req, execution_ref=execution_ref)
            evaluated = self._analyze.evaluate(eval_req)
            evaluation_failure = self._assert_port_output_lineage(
                run=run,
                cand=cand,
                request_obj=eval_req,
                report=evaluated,
                stage="sealed_oos_evaluate",
            )
            if evaluation_failure is not None:
                raise _OOSExecutionFailure(evaluation_failure)
            if evaluated.engine_version != manifest.analyze_engine_version:
                raise _OOSExecutionFailure(
                    FailureDetail(
                        code=FailureCode.HASH_MISMATCH,
                        message="sealed OOS evaluation engine_version drifted from frozen manifest",
                    )
                )
            evaluation_ref = self._persist_report_object(run, evaluated, sealed=True)
            passed = self._oos_thresholds_passed(evaluated, manifest)
            evidence_refs = tuple(
                ref
                for section in evaluated.sections
                for fact in section.facts
                for ref in (fact.evidence,)
                if ref is not None
            )
            artifact_refs = tuple(
                ref
                for section in evaluated.sections
                for fact in section.facts
                for ref in (fact.artifact,)
                if ref is not None
            )
            oos_result = OOSResult(
                result_id=f"oos-result-{authorization.one_shot_key}",
                attempt_id=attempt_started.attempt_id,
                authorization_id=authorization.authorization_id,
                run_id=run.run_id,
                candidate_id=cand.candidate_id,
                manifest_ref=manifest_ref,
                sealed_split_id=authorization.sealed_split_id,
                evaluation_ref=evaluation_ref,
                passed=passed,
                evidence_refs=evidence_refs,
                provenance=Provenance(
                    producer="factor_mining.controller.sealed_oos",
                    data_version=manifest.data_version,
                    code_version=manifest.analyze_engine_version,
                    experiment_version=authorization.one_shot_key,
                    namespace=run.namespace,
                    input_refs=(run.brief_ref, cand.factor_ref, manifest_ref, auth_ref),
                ),
                artifact_refs=artifact_refs,
            )
            oos_result_ref = put_formal_object(
                self._store,
                namespace=run.namespace,
                object_type="OOSResult",
                object_id=oos_result.result_id,
                body=to_plain_dict(oos_result),
                input_refs=(manifest_ref, auth_ref, evaluation_ref),
                meta={"sealed": True, "append_only": True},
            )
            terminal = replace(
                attempt_started,
                finished_at=self._now(),
                status=TaskResultStatus.SUCCEEDED,
                content_hash="",
            )
            return self._commit_oos_terminal(
                request=request,
                run=run,
                cand=cand,
                manifest_ref=manifest_ref,
                auth_ref=auth_ref,
                started_ref=started_ref,
                terminal=terminal,
                oos_result_ref=oos_result_ref,
                passed=passed,
            )
        except _OOSExecutionFailure as exc:
            failure = exc.failure
        except Exception as exc:  # noqa: BLE001
            failure = FailureDetail(
                code=FailureCode.RECOVERY_REQUIRED,
                message="sealed OOS execution failed after claim; retry is forbidden",
                retryable=False,
                details={"cause_type": type(exc).__name__},
            )
        terminal = replace(
            attempt_started,
            finished_at=self._now(),
            status=TaskResultStatus.FAILED,
            failure=failure,
            content_hash="",
        )
        return self._commit_oos_terminal(
            request=request,
            run=run,
            cand=cand,
            manifest_ref=manifest_ref,
            auth_ref=auth_ref,
            started_ref=started_ref,
            terminal=terminal,
            failure=failure,
        )

    def _cmd_record_gate2(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        if run.status is not ResearchRunStatus.OOS_TESTED:
            return self._invalid_state(run, "Gate-2 requires OOS-tested run")
        if run.gate2_approval_ref is not None:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.DUPLICATE_LOGICAL_KEY,
                    message="Gate-2 approval already recorded",
                ),
            )
        allowed = {"namespace", "candidate_id", "approved", "approver_id", "signed_at", "reason"}
        if set(request.payload) != allowed:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="Gate-2 payload must contain exactly the audited approval schema",
                    details={"fields": sorted(request.payload)},
                ),
            )
        candidate_id = str(request.payload.get("candidate_id") or "")
        if candidate_id != request.aggregate_id:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message="Gate-2 candidate_id must exact-bind aggregate_id",
                ),
            )
        cand = self._require_candidate(run, candidate_id)
        if cand.status is not CandidateStatus.OOS_TESTED:
            return self._invalid_state(run, "Gate-2 target candidate must be OOS-tested")
        approval = {
            "run_id": run.run_id,
            "candidate_id": candidate_id,
            "manifest_ref": to_plain_dict(run.freeze_manifest_ref),
            "oos_result_ref": to_plain_dict(run.oos_result_ref)
            if run.oos_result_ref is not None
            else None,
            "approved": request.payload.get("approved"),
            "approver_id": request.payload.get("approver_id"),
            "signed_at": request.payload.get("signed_at"),
            "reason": request.payload.get("reason"),
        }
        if (
            not isinstance(approval["approved"], bool)
            or not all(isinstance(approval[name], str) and approval[name] for name in ("approver_id", "signed_at", "reason"))
        ):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message="Gate-2 requires approved, approver_id, signed_at, and reason",
                ),
            )
        if approval["approved"] is True:
            if run.oos_result_ref is None:
                return self._invalid_state(
                    run, "Gate-2 cannot approve failed OOS execution"
                )
            result = resolve_typed_object(
                self._store, run.oos_result_ref, allow_staging=False
            )
            if not isinstance(result, OOSResult) or result.passed is not True:
                return self._invalid_state(
                    run, "Gate-2 cannot approve OOS result below frozen thresholds"
                )
        self._gate2_verifier(approval, request)
        put = self._put_if_absent(
            namespace=run.namespace,
            kind=KIND_GATE2,
            artifact_id=f"{run.run_id}-{candidate_id}-{request.idempotency_key}",
            payload=approval,
            input_refs=tuple(
                ref
                for ref in (run.freeze_manifest_ref, run.oos_result_ref)
                if ref is not None
            ),
            meta={"human_gate": True, "sealed": True, "append_only": True},
        )
        gate2_ref = put.ref if hasattr(put, "ref") else put
        updated = replace(run, gate2_approval_ref=gate2_ref)
        return self._commit(
            request,
            updated,
            from_status=run.status.value,
            to_status=run.status.value,
            input_refs=tuple(
                ref
                for ref in (run.brief_ref, run.freeze_manifest_ref, run.oos_result_ref)
                if ref is not None
            ),
            output_refs=(gate2_ref,),
            outputs={
                "candidate_id": candidate_id,
                "gate2_approval_ref": to_plain_dict(gate2_ref),
                "approved": approval["approved"],
            },
        )

    def _cmd_promote(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        if run.status is not ResearchRunStatus.OOS_TESTED:
            return self._invalid_state(run, "promotion requires OOS-tested run")
        if set(request.payload) != {"namespace"}:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="promotion accepts no unaudited caller inputs",
                    details={"fields": sorted(request.payload)},
                ),
            )
        cand = self._require_candidate(run, request.aggregate_id)
        if cand.status is not CandidateStatus.OOS_TESTED:
            return self._invalid_state(run, "promotion requires OOS-tested candidate")
        gate2 = self._require_gate2(run, cand, approved=True)
        if isinstance(gate2, CommandResult):
            return gate2
        if run.oos_result_ref is None:
            return self._invalid_state(run, "promotion requires successful OOS result")
        result = resolve_typed_object(self._store, run.oos_result_ref, allow_staging=False)
        if not isinstance(result, OOSResult) or result.passed is not True:
            return self._invalid_state(run, "promotion requires OOS result passing frozen thresholds")
        knowledge_ref = self._put_release_knowledge(
            run=run, cand=cand, disposition="promoted", request=request
        )
        cand2 = replace(
            cand,
            status=transition_candidate(cand.status, "promote"),
            version=cand.version + 1,
        )
        candidates = dict(run.candidates)
        candidates[cand2.candidate_id] = cand2
        updated = replace(
            run,
            status=transition_run(run.status, "promote"),
            candidates=candidates,
            release_knowledge_ref=knowledge_ref,
        )
        return self._commit(
            request,
            updated,
            from_status=run.status.value,
            to_status=updated.status.value,
            input_refs=(
                run.brief_ref,
                cand.factor_ref,
                run.freeze_manifest_ref,
                run.oos_result_ref,
                gate2,
            ),
            output_refs=(knowledge_ref,),
            outputs={"release_knowledge_ref": to_plain_dict(knowledge_ref)},
        )

    def _oos_context(
        self, run: RunAggregate, candidate_id: str
    ) -> tuple[CandidateAggregate, ObjectRef, FreezeManifest, ArtifactRef] | CommandResult:
        """Load the immutable Frozen/Gate-1/manifest closure for sealed OOS."""
        if run.status is not ResearchRunStatus.FROZEN:
            return self._invalid_state(run, "sealed OOS requires frozen run")
        cand = self._require_candidate(run, candidate_id)
        if cand.status is not CandidateStatus.FROZEN:
            return self._invalid_state(run, "sealed OOS requires frozen candidate")
        manifest_ref = run.freeze_manifest_ref
        if manifest_ref is None or cand.freeze_manifest_ref is None:
            return self._invalid_state(run, "sealed OOS requires frozen manifest")
        if to_plain_dict(manifest_ref) != to_plain_dict(cand.freeze_manifest_ref):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="run/candidate frozen manifest refs disagree",
                ),
            )
        try:
            gate1_ref = require_gate1_approval(
                run, store_get=self._store.get, candidate_id=cand.candidate_id
            )
            manifest = resolve_typed_object(
                self._store, manifest_ref, allow_staging=False
            )
        except (FreezeGateError, ObjectStoreError) as exc:
            return CommandResult(ok=False, run=run, failure=exc.failure)
        if not isinstance(manifest, FreezeManifest):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.SCHEMA_MISMATCH,
                    message="frozen manifest_ref must resolve to FreezeManifest",
                ),
            )
        if (
            manifest.run_id != run.run_id
            or to_plain_dict(manifest.brief_ref) != to_plain_dict(run.brief_ref)
            or to_plain_dict(manifest.factor_ref) != to_plain_dict(cand.factor_ref)
            or to_plain_dict(manifest.approval_ref) != to_plain_dict(gate1_ref)
        ):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="frozen manifest does not exact-bind run/candidate/Gate-1",
                ),
            )
        sealed_split = manifest.split_refs.get("sealed")
        if not isinstance(sealed_split, str) or not sealed_split:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_REFERENCE,
                    message="frozen manifest missing sealed split identifier",
                ),
            )
        return cand, manifest_ref, manifest, gate1_ref

    def _oos_one_shot_key(
        self,
        *,
        run: RunAggregate,
        candidate: CandidateAggregate,
        manifest_ref: ObjectRef,
        sealed_split_id: str,
    ) -> str:
        """Controller-only canonical identity; caller payload never contributes."""
        return content_hash(
            {
                "namespace": run.namespace,
                "run_id": run.run_id,
                "candidate_id": candidate.candidate_id,
                "manifest_ref": to_plain_dict(manifest_ref),
                "sealed_split_id": sealed_split_id,
            }
        )

    def _load_oos_authorization(
        self,
        run: RunAggregate,
        cand: CandidateAggregate,
        manifest_ref: ObjectRef,
        manifest: FreezeManifest,
    ) -> tuple[ObjectRef, OOSAuthorization] | CommandResult:
        auth_ref = run.oos_authorization_ref
        if auth_ref is None:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.OOS_NOT_AUTHORIZED,
                    message="sealed OOS requires a prior controller authorization",
                ),
            )
        try:
            authorization = resolve_typed_object(
                self._store, auth_ref, allow_staging=False
            )
        except ObjectStoreError as exc:
            return CommandResult(ok=False, run=run, failure=exc.failure)
        if not isinstance(authorization, OOSAuthorization):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.SCHEMA_MISMATCH,
                    message="oos_authorization_ref must resolve to OOSAuthorization",
                ),
            )
        split_id = str(manifest.split_refs["sealed"])
        expected_key = self._oos_one_shot_key(
            run=run,
            candidate=cand,
            manifest_ref=manifest_ref,
            sealed_split_id=split_id,
        )
        if (
            authorization.run_id != run.run_id
            or authorization.candidate_id != cand.candidate_id
            or to_plain_dict(authorization.manifest_ref) != to_plain_dict(manifest_ref)
            or authorization.sealed_split_id != split_id
            or authorization.one_shot_key != expected_key
        ):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="sealed OOS authorization does not exact-bind frozen closure",
                ),
            )
        return auth_ref, authorization

    def _build_oos_requests(
        self, manifest: FreezeManifest, authorization: OOSAuthorization
    ) -> tuple[FactorComputeRequest, EvaluationRequest]:
        if self._oos_request_factory is None:
            raise _OOSExecutionFailure(
                FailureDetail(
                    code=FailureCode.OOS_NOT_AUTHORIZED,
                    message="sealed OOS request factory is not injected",
                )
            )
        compute_req, eval_req = self._oos_request_factory(manifest, authorization)
        expected_request_id = f"oos-compute-{authorization.one_shot_key}"
        expected_execution_id = f"oos-execution-{authorization.one_shot_key}"
        expected_eval_id = f"oos-evaluate-{authorization.one_shot_key}"
        if (
            compute_req.request_id != expected_request_id
            or compute_req.experiment_id != authorization.one_shot_key
            or compute_req.execution_id != expected_execution_id
            or compute_req.namespace != manifest.provenance.namespace
            or to_plain_dict(compute_req.brief_ref) != to_plain_dict(manifest.brief_ref)
            or to_plain_dict(compute_req.factor_ref) != to_plain_dict(manifest.factor_ref)
            or compute_req.data_version != manifest.data_version
            or compute_req.split_id != authorization.sealed_split_id
            or compute_req.sealed_execution is not True
        ):
            raise _OOSExecutionFailure(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="sealed compute request drifted from frozen manifest",
                )
            )
        if (
            eval_req.request_id != expected_eval_id
            or eval_req.namespace != manifest.provenance.namespace
            or to_plain_dict(eval_req.brief_ref) != to_plain_dict(manifest.brief_ref)
            or to_plain_dict(eval_req.factor_ref) != to_plain_dict(manifest.factor_ref)
            or eval_req.data_version != manifest.data_version
            or eval_req.split_id != authorization.sealed_split_id
            or eval_req.protocol_id != manifest.evaluation_protocol_id
            or eval_req.execution_ref is not None
            or tuple(eval_req.pool_refs) != tuple(manifest.pool_baseline_refs)
        ):
            raise _OOSExecutionFailure(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="sealed evaluation request drifted from frozen manifest",
                )
            )
        return compute_req, eval_req

    def _oos_thresholds_passed(
        self, report: EvaluationReport, manifest: FreezeManifest
    ) -> bool:
        """Delegate frozen official fact selection to the Analyze boundary."""
        return oos_report_passes_frozen_thresholds(
            report,
            thresholds=manifest.oos_thresholds,
            selectors=manifest.oos_metric_selectors,
        )

    def _commit_oos_terminal(
        self,
        *,
        request: CommandRequest,
        run: RunAggregate,
        cand: CandidateAggregate,
        manifest_ref: ObjectRef,
        auth_ref: ObjectRef,
        started_ref: ArtifactRef,
        terminal: OOSAttempt,
        oos_result_ref: ObjectRef | None = None,
        passed: bool = False,
        failure: FailureDetail | None = None,
    ) -> CommandResult:
        terminal_id = f"oos-terminal-{terminal.one_shot_key}"
        try:
            put = self._put_if_absent(
                namespace=run.namespace,
                kind=KIND_OOS_ATTEMPT,
                artifact_id=terminal_id,
                payload=to_plain_dict(terminal),
                input_refs=(run.brief_ref, cand.factor_ref, manifest_ref, auth_ref, started_ref),
                meta={"sealed": True, "append_only": True, "phase": "terminal"},
            )
        except Exception as exc:  # noqa: BLE001
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="sealed OOS terminal ledger could not be persisted",
                    details={"cause_type": type(exc).__name__},
                ),
            )
        terminal_ref = put.ref if hasattr(put, "ref") else put
        if not bool(getattr(put, "created", True)):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.OOS_ALREADY_CONSUMED,
                    message="sealed OOS terminal already exists; refusing overwrite",
                ),
            )
        cand2 = replace(
            cand,
            status=transition_candidate(cand.status, "complete_oos"),
            version=cand.version + 1,
        )
        candidates = dict(run.candidates)
        candidates[cand2.candidate_id] = cand2
        updated = replace(
            run,
            status=transition_run(run.status, "complete_oos"),
            candidates=candidates,
            oos_attempt_refs=(started_ref, terminal_ref),
            oos_result_ref=oos_result_ref,
        )
        output_refs = (terminal_ref,) + ((oos_result_ref,) if oos_result_ref else ())
        return self._commit(
            request,
            updated,
            from_status=run.status.value,
            to_status=updated.status.value,
            result_status="ok" if failure is None else "failed",
            ok=failure is None,
            failure=failure,
            input_refs=(run.brief_ref, cand.factor_ref, manifest_ref, auth_ref, started_ref),
            output_refs=output_refs,
            outputs={
                "candidate_id": cand.candidate_id,
                "authorization_ref": to_plain_dict(auth_ref),
                "attempt_started_ref": to_plain_dict(started_ref),
                "attempt_terminal_ref": to_plain_dict(terminal_ref),
                "oos_result_ref": to_plain_dict(oos_result_ref)
                if oos_result_ref is not None
                else None,
                "passed": bool(passed),
            },
        )

    def _require_gate2(
        self, run: RunAggregate, cand: CandidateAggregate, *, approved: bool
    ) -> ArtifactRef | CommandResult:
        ref = run.gate2_approval_ref
        if ref is None:
            return self._invalid_state(run, "Human Gate-2 approval record required")
        try:
            payload = self._store.get(ref)
        except Exception as exc:  # noqa: BLE001
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_REFERENCE,
                    message="Gate-2 approval artifact unavailable",
                    details={"cause_type": type(exc).__name__},
                ),
            )
        expected_fields = {
            "run_id",
            "candidate_id",
            "manifest_ref",
            "oos_result_ref",
            "approved",
            "approver_id",
            "signed_at",
            "reason",
        }
        if (
            set(payload) != expected_fields
            or to_plain_dict(payload.get("manifest_ref"))
            != to_plain_dict(run.freeze_manifest_ref)
            or to_plain_dict(payload.get("oos_result_ref"))
            != to_plain_dict(run.oos_result_ref)
            or payload.get("run_id") != run.run_id
            or payload.get("candidate_id") != cand.candidate_id
            or payload.get("approved") is not approved
        ):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="Gate-2 approval does not bind final release decision",
                ),
            )
        return ref

    def _put_release_knowledge(
        self,
        *,
        run: RunAggregate,
        cand: CandidateAggregate,
        disposition: str,
        request: CommandRequest,
    ) -> ArtifactRef:
        """Append an opaque reference closure, never OOS facts or values."""
        identity = content_hash(
            {
                "run_id": run.run_id,
                "candidate_id": cand.candidate_id,
                "disposition": disposition,
                "manifest_ref": to_plain_dict(run.freeze_manifest_ref),
                "oos_result_ref": to_plain_dict(run.oos_result_ref),
                "gate2_ref": to_plain_dict(run.gate2_approval_ref),
                "idempotency_key": request.idempotency_key,
            }
        )
        payload = {
            "knowledge_id": f"release-{identity}",
            "run_id": run.run_id,
            "candidate_id": cand.candidate_id,
            "disposition": disposition,
            "factor_ref": to_plain_dict(cand.factor_ref),
            "manifest_ref": to_plain_dict(run.freeze_manifest_ref),
            "oos_result_ref": to_plain_dict(run.oos_result_ref)
            if run.oos_result_ref is not None
            else None,
            "gate1_approval_ref": to_plain_dict(run.gate1_approval_ref),
            "gate2_approval_ref": to_plain_dict(run.gate2_approval_ref),
            "oos_attempt_refs": [to_plain_dict(ref) for ref in run.oos_attempt_refs],
        }
        put = self._put_if_absent(
            namespace=run.namespace,
            kind=KIND_RELEASE_KNOWLEDGE,
            artifact_id=payload["knowledge_id"],
            payload=payload,
            input_refs=tuple(
                ref
                for ref in (
                    cand.factor_ref,
                    run.freeze_manifest_ref,
                    run.gate1_approval_ref,
                    run.oos_result_ref,
                    run.gate2_approval_ref,
                    *run.oos_attempt_refs,
                )
                if ref is not None
            ),
            meta={"sealed": True, "append_only": True},
        )
        return put.ref if hasattr(put, "ref") else put

    def _cmd_reject_candidate(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        cand = self._require_candidate(run, request.aggregate_id)
        new_status = transition_candidate(cand.status, "reject")
        cand2 = replace(cand, status=new_status, version=cand.version + 1)
        candidates = dict(run.candidates)
        candidates[cand2.candidate_id] = cand2
        knowledge = None
        knowledge_ref = None
        if request.payload.get("record_failure_knowledge"):
            knowledge, knowledge_ref = self._record_failure_knowledge(
                run, cand2, request.payload, request=request
            )
        updated = replace(run, candidates=candidates)
        if knowledge is not None and knowledge_ref is not None:
            updated = replace(
                updated,
                failure_knowledge_ids=tuple(updated.failure_knowledge_ids)
                + (knowledge.knowledge_id,),
            )
            return self._commit(
                request,
                updated,
                from_status=cand.status.value,
                to_status=new_status.value,
                input_refs=(run.brief_ref, cand2.factor_ref, knowledge_ref),
                output_refs=(knowledge_ref,),
                outputs={
                    "knowledge_id": knowledge.knowledge_id,
                    "failure_knowledge_ref": to_plain_dict(knowledge_ref),
                    "staging_content_hash": knowledge_ref.content_hash,
                    "staging_kind": KIND_STAGING,
                    "staging_artifact_id": (
                        f"FailureKnowledgeEntry-{knowledge.knowledge_id}"
                    ),
                },
            )
        return self._commit(
            request,
            updated,
            from_status=cand.status.value,
            to_status=new_status.value,
            input_refs=(run.brief_ref, cand.factor_ref),
            outputs={"knowledge_id": None},
        )

    def _cmd_reject_run(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        if run.status is ResearchRunStatus.OOS_TESTED:
            if set(request.payload) != {"namespace"}:
                return CommandResult(
                    ok=False,
                    run=run,
                    failure=FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message="OOS rejection accepts no unaudited caller inputs",
                        details={"fields": sorted(request.payload)},
                    ),
                )
            cand = self._require_candidate(run, request.aggregate_id)
            if cand.status is not CandidateStatus.OOS_TESTED:
                return self._invalid_state(
                    run, "OOS rejection requires OOS-tested candidate"
                )
            gate2 = self._require_gate2(run, cand, approved=False)
            if isinstance(gate2, CommandResult):
                return gate2
            knowledge_ref = self._put_release_knowledge(
                run=run, cand=cand, disposition="rejected", request=request
            )
            cand2 = replace(
                cand,
                status=transition_candidate(cand.status, "reject"),
                version=cand.version + 1,
            )
            candidates = dict(run.candidates)
            candidates[cand2.candidate_id] = cand2
            updated = replace(
                run,
                status=transition_run(run.status, "reject_run"),
                candidates=candidates,
                release_knowledge_ref=knowledge_ref,
            )
            return self._commit(
                request,
                updated,
                from_status=run.status.value,
                to_status=updated.status.value,
                input_refs=tuple(
                    ref
                    for ref in (
                        run.brief_ref,
                        cand.factor_ref,
                        run.freeze_manifest_ref,
                        run.oos_result_ref,
                        gate2,
                    )
                    if ref is not None
                ),
                output_refs=(knowledge_ref,),
                outputs={"release_knowledge_ref": to_plain_dict(knowledge_ref)},
            )
        new_status = transition_run(run.status, "reject_run")
        updated = replace(run, status=new_status)
        return self._commit(
            request,
            updated,
            from_status=run.status.value,
            to_status=new_status.value,
        )

    def _cmd_stop(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        reason = str(request.payload.get("reason") or "human_terminated")
        new_status = transition_run(run.status, "stop")
        updated = replace(run, status=new_status, stop_reason=reason)
        return self._commit(
            request,
            updated,
            from_status=run.status.value,
            to_status=new_status.value,
            outputs=stop_event_details(reason),
        )

    def _cmd_create_task(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        payload = dict(request.payload)
        raw_visibility = tuple(payload.get("visibility") or ())
        effective_visibility = raw_visibility or DEFAULT_RESEARCH_VISIBILITY
        if VIS_SEALED in raw_visibility:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="sealed visibility cannot be assigned to research tasks",
                ),
            )
        if (
            len(set(raw_visibility)) != len(raw_visibility)
            or any(token not in DEFAULT_RESEARCH_VISIBILITY for token in raw_visibility)
        ):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message="task visibility must be a unique subset of research visibility",
                ),
            )
        candidate_id = payload.get("candidate_id")
        if candidate_id is not None:
            if not isinstance(candidate_id, str) or candidate_id not in run.candidates:
                return CommandResult(
                    ok=False,
                    run=run,
                    failure=FailureDetail(
                        code=FailureCode.INVALID_REFERENCE,
                        message="task candidate_id must name an existing candidate",
                    ),
                )
        if request.parent_task_id is not None and request.parent_task_id not in run.tasks:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_REFERENCE,
                    message="task parent_task_id must name an existing task",
                ),
            )
        if payload.get("attempt", 1) != 1 or payload.get("debate_round", 0) != 0:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message="Phase 04 task creation requires attempt=1 and debate_round=0",
                ),
            )
        expected_output_type = payload.get("expected_output_type", "ResearchDecision")
        if not isinstance(expected_output_type, str) or not expected_output_type:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message="task expected_output_type must be non-empty str",
                ),
            )
        try:
            input_refs = tuple(
                _coerce_ref(item) for item in payload.get("input_refs", ())
            )
            assert_refs_authorized(
                self._store,
                namespace=run.namespace,
                refs=input_refs,
                allow_sealed=False,
                visibility=effective_visibility,
            )
            authorized_inputs = [
                to_plain_dict(ref) for ref in _controller_task_authorized_refs(run)
            ]
            if any(to_plain_dict(ref) not in authorized_inputs for ref in input_refs):
                raise IsolationDenied(
                    FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message=(
                            "task input_refs must be drawn from controller-authorized "
                            "run lineage"
                        ),
                    )
                )
        except (IsolationDenied, TypeError, ValueError) as exc:
            failure = getattr(exc, "failure", None)
            return CommandResult(
                ok=False,
                run=run,
                failure=(
                    failure
                    if isinstance(failure, FailureDetail)
                    else FailureDetail(
                        code=FailureCode.INVALID_REFERENCE,
                        message="task input_refs are not authorized",
                        details={"cause_type": type(exc).__name__},
                    )
                ),
            )
        task = TaskAggregate(
            task_id=request.aggregate_id,
            run_id=run.run_id,
            role_id=request.role_id,
            status=TaskLifecycleStatus.PENDING,
            parent_task_id=request.parent_task_id,
            candidate_id=candidate_id,
            visibility=raw_visibility,
            input_refs=input_refs,
            expected_output_type=expected_output_type,
        )
        if VIS_SEALED in task.visibility:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="sealed visibility cannot be assigned to research tasks",
                ),
            )
        tasks = dict(run.tasks)
        if task.task_id in tasks:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.DUPLICATE_LOGICAL_KEY,
                    message="task already exists",
                ),
            )
        tasks[task.task_id] = task
        updated = replace(run, tasks=tasks)
        return self._commit(
            request,
            updated,
            from_status="none",
            to_status=task.status.value,
            input_refs=(
                run.brief_ref,
                *task.input_refs,
                *(
                    (run.candidates[task.candidate_id].factor_ref,)
                    if task.candidate_id is not None
                    else ()
                ),
            ),
        )

    def _cmd_claim_task(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        task = self._require_task(run, request.aggregate_id)
        raw_amounts = request.payload.get("amounts", {})
        if not isinstance(raw_amounts, Mapping):
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message="claim_task amounts must be a mapping",
                ),
            )
        reservation_id = f"task:{task.task_id}:{request.idempotency_key}"
        budget = BudgetView.from_run(run)
        reserved = reserve(
            budget, reservation_id=reservation_id, amounts=dict(raw_amounts)
        )
        if isinstance(reserved, FailureDetail):
            return CommandResult(ok=False, run=run, failure=reserved)
        amounts = dict(reserved.reservations[reservation_id])
        new_status = transition_task(task.status, "claim")
        task2 = replace(
            task,
            status=new_status,
            reservation_id=reservation_id,
            lease_id=reservation_id,
            version=task.version + 1,
        )
        updated = reserved.apply_to_run(run)
        tasks = dict(updated.tasks)
        tasks[task2.task_id] = task2
        updated = replace(updated, tasks=tasks)
        return self._commit(
            request,
            updated,
            from_status=task.status.value,
            to_status=new_status.value,
            budget_delta={k: -v for k, v in amounts.items() if v},
            outputs={
                "reservation_id": reservation_id,
                "lease_id": task2.lease_id,
                "amounts": amounts,
            },
        )

    def _cmd_start_task(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        task = self._require_task(run, request.aggregate_id)
        new_status = transition_task(task.status, "start")
        task2 = replace(task, status=new_status, version=task.version + 1)
        tasks = dict(run.tasks)
        tasks[task2.task_id] = task2
        updated = replace(run, tasks=tasks)
        return self._commit(
            request,
            updated,
            from_status=task.status.value,
            to_status=new_status.value,
        )

    def _cmd_submit_task(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        task = self._require_task(run, request.aggregate_id)
        new_status = transition_task(task.status, "submit")
        output_ref = ObjectRef(**dict(request.payload["output_ref"]))
        if output_ref.object_type != task.expected_output_type:
            return CommandResult(
                ok=False,
                run=run,
                failure=FailureDetail(
                    code=FailureCode.SCHEMA_MISMATCH,
                    message="task output_ref.object_type must exact-match task expected_output_type",
                ),
            )
        assert_refs_authorized(
            self._store, namespace=run.namespace, refs=[output_ref], allow_sealed=False
        )
        budget = BudgetView.from_run(run)
        if task.reservation_id:
            settled = settle(budget, reservation_id=task.reservation_id)
            if isinstance(settled, FailureDetail):
                return CommandResult(ok=False, run=run, failure=settled)
            budget = settled
        task2 = replace(
            task,
            status=new_status,
            output_ref=output_ref,
            version=task.version + 1,
            reservation_id=None,
        )
        updated = budget.apply_to_run(run)
        tasks = dict(updated.tasks)
        tasks[task2.task_id] = task2
        updated = replace(updated, tasks=tasks)
        return self._commit(
            request,
            updated,
            from_status=task.status.value,
            to_status=new_status.value,
            output_refs=(output_ref,),
            outputs={"output_ref": to_plain_dict(output_ref)},
        )

    def _cmd_fail_task(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        return self._end_task(request, run, command="fail", settle_budget=True)

    def _cmd_cancel_task(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        task = self._require_task(run, request.aggregate_id)
        release_budget = task.status is TaskLifecycleStatus.CLAIMED
        return self._end_task(
            request,
            run,
            command="cancel",
            settle_budget=not release_budget,
            release_budget=release_budget,
        )

    def _cmd_timeout_task(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        return self._end_task(request, run, command="timeout", settle_budget=True)

    def _cmd_build_task_view(
        self, request: CommandRequest, run: RunAggregate
    ) -> CommandResult:
        task = self._require_task(run, request.aggregate_id)
        refs = tuple(
            _coerce_ref(item) for item in request.payload.get("input_refs", ())
        )
        requested_candidate_ref = None
        if request.payload.get("candidate_ref"):
            requested_candidate_ref = ObjectRef(**dict(request.payload["candidate_ref"]))
        # Brief lineage plus every inspected ref (including candidate_ref when used).
        inspected: list = [run.brief_ref, *refs]
        if requested_candidate_ref is not None:
            inspected.append(requested_candidate_ref)
        inspected_refs = tuple(inspected)
        try:
            if requested_candidate_ref is not None:
                # Validate the attempted ref first so denial keeps the precise
                # cross-namespace/sealed audit reason rather than masking it as
                # a task-shape violation below.
                assert_refs_authorized(
                    self._store,
                    namespace=run.namespace,
                    refs=[requested_candidate_ref],
                    allow_sealed=False,
                )
            if [to_plain_dict(ref) for ref in refs] != [
                to_plain_dict(ref) for ref in task.input_refs
            ]:
                raise IsolationDenied(
                    FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message="task view input_refs must exact-match task authorization",
                    )
                )
            requested_output = request.payload.get(
                "expected_output_type", task.expected_output_type
            )
            if requested_output != task.expected_output_type:
                raise IsolationDenied(
                    FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message="task view expected_output_type must exact-match task",
                    )
                )
            candidate_ref = None
            if task.candidate_id is not None:
                candidate_ref = run.candidates[task.candidate_id].factor_ref
                if (
                    requested_candidate_ref is not None
                    and to_plain_dict(requested_candidate_ref)
                    != to_plain_dict(candidate_ref)
                ):
                    raise IsolationDenied(
                        FailureDetail(
                            code=FailureCode.FORBIDDEN_INPUT,
                            message="task view candidate_ref must exact-match task candidate",
                        )
                    )
            elif requested_candidate_ref is not None:
                raise IsolationDenied(
                    FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message="run-level task cannot introduce candidate_ref",
                    )
                )
            assert_refs_authorized(
                self._store,
                namespace=run.namespace,
                refs=list(task.input_refs)
                + ([candidate_ref] if candidate_ref else []),
                allow_sealed=False,
            )
            view = build_agent_task_view(
                run=run,
                task=task,
                goal=str(request.payload.get("goal", "task")),
                input_refs=task.input_refs,
                expected_output_type=task.expected_output_type,
                lease_id=str(task.lease_id or f"lease-{task.task_id}"),
                visibility=task.visibility or None,
                candidate_ref=candidate_ref,
                store=self._store,
            )
        except IsolationDenied as exc:
            return self._commit(
                request,
                run,
                from_status=task.status.value,
                to_status=task.status.value,
                result_status="denied",
                failure=exc.failure,
                ok=False,
                input_refs=inspected_refs,
            )
        return self._commit(
            request,
            run,
            from_status=task.status.value,
            to_status=task.status.value,
            input_refs=inspected_refs,
            outputs={"task_view": to_plain_dict(view)},
        )

    # ------------------------------------------------------------- helpers
    def _end_task(
        self,
        request: CommandRequest,
        run: RunAggregate,
        *,
        command: str,
        settle_budget: bool,
        release_budget: bool = False,
    ) -> CommandResult:
        task = self._require_task(run, request.aggregate_id)
        new_status = transition_task(task.status, command)
        budget = BudgetView.from_run(run)
        budget_delta: dict[str, int] = {}
        if task.reservation_id:
            prior_amounts = {
                key: int(value)
                for key, value in dict(
                    budget.reservations.get(task.reservation_id) or {}
                ).items()
                if int(value)
            }
            if release_budget:
                outcome = release(budget, reservation_id=task.reservation_id)
                budget_delta = dict(prior_amounts)
            elif settle_budget:
                outcome = settle(budget, reservation_id=task.reservation_id)
            else:
                outcome = budget
            if isinstance(outcome, FailureDetail):
                return CommandResult(ok=False, run=run, failure=outcome)
            budget = outcome
        task2 = replace(
            task,
            status=new_status,
            version=task.version + 1,
            reservation_id=None,
        )
        updated = budget.apply_to_run(run)
        tasks = dict(updated.tasks)
        tasks[task2.task_id] = task2
        updated = replace(updated, tasks=tasks)
        return self._commit(
            request,
            updated,
            from_status=task.status.value,
            to_status=new_status.value,
            budget_delta=budget_delta,
        )

    def _pipeline_reject(
        self,
        request: CommandRequest,
        run: RunAggregate,
        cand: CandidateAggregate,
        *,
        reservation_id: str,
        stage: str,
        calls: list[str],
        report: EvaluationReport | None = None,
        execution: FactorExecutionResult | None = None,
        forced_failure: FailureDetail | None = None,
    ) -> CommandResult:
        _ = reservation_id  # settled at pipeline_started
        try:
            new_status = transition_candidate(cand.status, "reject")
        except IllegalTransitionError:
            new_status = CandidateStatus.REJECTED
        failure = forced_failure
        if failure is None and report is not None and report.failure is not None:
            failure = report.failure
        elif failure is None and execution is not None and execution.failure is not None:
            failure = execution.failure
        elif failure is None:
            failure = FailureDetail(
                code=FailureCode.INVALID_STATE,
                message=f"hard fail at {stage}",
                severity=Severity.HARD_FAIL,
            )
        cand2 = replace(cand, status=new_status, version=cand.version + 1)
        candidates = dict(run.candidates)
        candidates[cand2.candidate_id] = cand2
        knowledge, knowledge_ref = self._record_failure_knowledge(
            run,
            cand2,
            {
                "family_fingerprint": request.payload.get(
                    "family_fingerprint", cand2.factor_ref.content_hash[:16]
                ),
                "formula_fingerprint": request.payload.get(
                    "formula_fingerprint", cand2.factor_ref.content_hash[16:32]
                ),
                "failure_type": stage,
                "disposition": "rejected",
                "split_id": str(request.payload.get("split_id", "train")),
            },
            request=request,
        )
        updated = replace(
            run,
            candidates=candidates,
            failure_knowledge_ids=tuple(run.failure_knowledge_ids)
            + (knowledge.knowledge_id,),
        )
        return self._commit_pipeline_terminal(
            request,
            updated,
            from_status=cand.status.value,
            to_status=new_status.value,
            result_status="failed",
            failure=failure,
            input_refs=(run.brief_ref, cand2.factor_ref, knowledge_ref),
            output_refs=(knowledge_ref,),
            outputs={
                "calls": calls,
                "stage": stage,
                "pipeline_phase": "terminal",
                "knowledge_id": knowledge.knowledge_id,
                "failure_knowledge_ref": to_plain_dict(knowledge_ref),
                "staging_content_hash": knowledge_ref.content_hash,
                "staging_kind": KIND_STAGING,
                "staging_artifact_id": f"FailureKnowledgeEntry-{knowledge.knowledge_id}",
            },
            ok=False,
        )

    def _persist_report_object(
        self, run: RunAggregate, report: EvaluationReport, *, sealed: bool = False
    ) -> ObjectRef:
        body = to_plain_dict(report)
        return put_formal_object(
            self._store,
            namespace=run.namespace,
            object_type="EvaluationReport",
            object_id=report.report_id,
            body=body,
            input_refs=(run.brief_ref, report.factor_ref),
            meta={"sealed": sealed, "append_only": sealed},
        )

    def _persist_execution_object(
        self, run: RunAggregate, result: FactorExecutionResult, *, sealed: bool = False
    ) -> ObjectRef:
        body = to_plain_dict(result)
        # ObjectRef.content_hash binds the envelope fingerprint; stored as body
        # content_hash alias for formal put, stripped on typed resolve.
        digest = result.fingerprint
        if len(digest) != 64:
            raise ObjectStoreError(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="FactorExecutionResult fingerprint must be 64-hex content hash",
                )
            )
        body = {**body, "content_hash": digest}
        return put_formal_object(
            self._store,
            namespace=run.namespace,
            object_type="FactorExecutionResult",
            object_id=result.execution_id,
            body=body,
            input_refs=(run.brief_ref, result.factor_ref),
            meta={"sealed": sealed, "append_only": sealed},
        )

    def _record_failure_knowledge(
        self,
        run: RunAggregate,
        cand: CandidateAggregate,
        payload: Mapping[str, Any],
        *,
        request: CommandRequest,
    ) -> tuple[FailureKnowledgeEntry, ObjectRef]:
        """Stage immutable FailureKnowledge; visible only after terminal event binds it.

        Staging identity is content-addressed from command/logical-key/payload body so
        same logical retry is idempotent and a different knowledge payload cannot collide
        at a sequence-derived or candidate-only id.
        """
        fingerprint = {
            "run_id": run.run_id,
            "command": request.command,
            "logical_key": command_identity_key(
                run_id=request.run_id,
                aggregate_id=request.aggregate_id,
                idempotency_key=request.idempotency_key,
            ),
            "idempotency_key": request.idempotency_key,
            "aggregate_id": request.aggregate_id,
            "payload": to_plain_dict(dict(payload)),
            "factor_ref": to_plain_dict(cand.factor_ref),
            "family_fingerprint": str(payload["family_fingerprint"]),
            "formula_fingerprint": str(payload["formula_fingerprint"]),
            "failure_type": str(payload["failure_type"]),
            "disposition": str(payload.get("disposition", "rejected")),
            "split_id": str(payload.get("split_id", "train")),
            "repairable": bool(payload.get("repairable", False)),
        }
        knowledge_id = f"fk-{content_hash(fingerprint)}"
        entry = FailureKnowledgeEntry(
            knowledge_id=knowledge_id,
            run_id=run.run_id,
            family_fingerprint=str(payload["family_fingerprint"]),
            formula_fingerprint=str(payload["formula_fingerprint"]),
            failure_type=str(payload["failure_type"]),
            disposition=str(payload.get("disposition", "rejected")),
            split_id=str(payload.get("split_id", "train")),
            repairable=bool(payload.get("repairable", False)),
            factor_ref=cand.factor_ref,
            sealed=False,
        )
        knowledge_ref = put_staging_object(
            self._store,
            namespace=run.namespace,
            object_type="FailureKnowledgeEntry",
            object_id=entry.knowledge_id,
            body=to_plain_dict(entry),
            input_refs=(cand.factor_ref,),
        )
        return entry, knowledge_ref

    def _commit_pipeline_terminal(
        self,
        request: CommandRequest,
        run: RunAggregate,
        **kwargs: Any,
    ) -> CommandResult:
        """Append pipeline terminal event; on append failure keep started ledger."""
        result = self._commit(request, run, **kwargs)
        if result.event is not None:
            return result
        loaded = self.load_run(namespace=run.namespace, run_id=run.run_id)
        if loaded is None:
            return result
        entry = loaded.idempotency.get(self._idempotency_index_key(request))
        if isinstance(entry, Mapping) and entry.get("pipeline_phase") == "started":
            return self._result_from_idem_entry(loaded, entry)
        return result

    def _commit(
        self,
        request: CommandRequest,
        run: RunAggregate,
        *,
        from_status: str,
        to_status: str,
        outputs: Mapping[str, Any] | None = None,
        budget_delta: Mapping[str, int] | None = None,
        failure: FailureDetail | None = None,
        result_status: str = "ok",
        ok: bool = True,
        input_refs: tuple = (),
        output_refs: tuple = (),
    ) -> CommandResult:
        outputs = dict(outputs or {})
        # Event sequence put_if_absent is the only concurrency CAS.
        bumped = replace(run, version=run.version + 1)
        seq = bumped.event_head_seq + 1
        prev_hash = bumped.event_head_hash

        # Run payload in event outputs omits authoritative head hash (set after).
        # Idempotency index is rebuilt from the verified prefix after append.
        run_for_event = bumped.to_payload()
        run_for_event["event_head_seq"] = seq
        run_for_event["event_head_hash"] = None
        state_digest = content_hash(
            {k: v for k, v in run_for_event.items() if k != "event_head_hash"}
        )
        # Normalized CommandResult embed: no self-referential event_head_hash and
        # no idempotency map. Exact returned run is reconstructed from the verified
        # event prefix after the hash is known.
        normalized_run = {
            **run_for_event,
            "event_head_hash": None,
            "idempotency": {},
        }
        result_snapshot = {
            "ok": ok,
            "failure": to_plain_dict(failure) if failure else None,
            "outputs": dict(outputs),
            "run": normalized_run,
            "replayed": False,
        }
        event_outputs = {
            **outputs,
            "run": run_for_event,
            "command_result": result_snapshot,
        }
        refs_in = tuple(input_refs) if input_refs else (bumped.brief_ref,)
        refs_out = tuple(output_refs)
        body = build_event_body(
            sequence=seq,
            prev_hash=prev_hash,
            run_id=bumped.run_id,
            aggregate_kind=_aggregate_kind(request),
            aggregate_id=request.aggregate_id,
            command=request.command,
            idempotency_key=request.idempotency_key,
            actor_id=request.actor_id,
            role_id=request.role_id,
            from_status=from_status,
            to_status=to_status,
            input_refs=refs_in,
            output_refs=refs_out,
            budget_delta=dict(budget_delta or {}),
            parent_task_id=request.parent_task_id,
            result_status=result_status if ok else (result_status or "failed"),
            failure=failure,
            state_after_digest=state_digest,
            outputs=event_outputs,
        )
        event_hash = hash_event_body(body)
        event = event_from_body(body, event_hash=event_hash)
        if event.compute_hash() != event_hash:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="event compute_hash diverged from canonical body",
                ),
            )

        try:
            put_result = self._put_if_absent(
                namespace=bumped.namespace,
                kind=KIND_EVENT,
                artifact_id=f"{bumped.run_id}-{seq:08d}",
                payload={**body, "event_hash": event_hash},
                input_refs=refs_in if refs_in else (bumped.brief_ref,),
                meta={"append_only": True},
            )
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", None)
            if code is FailureCode.DUPLICATE_LOGICAL_KEY:
                return CommandResult(
                    ok=False,
                    failure=FailureDetail(
                        code=FailureCode.DUPLICATE_LOGICAL_KEY,
                        message="event append-only conflict",
                    ),
                )
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="event append failed; no state migration committed",
                    details={"cause_type": type(exc).__name__},
                ),
            )

        created = bool(getattr(put_result, "created", True))
        if not created:
            # Concurrent winner wrote identical content — return canonical replay.
            try:
                return self._result_from_verified_prefix(
                    namespace=bumped.namespace,
                    run_id=bumped.run_id,
                    sequence=seq,
                    event_hash=event_hash,
                    replayed=True,
                )
            except Exception as exc:  # noqa: BLE001
                return CommandResult(
                    ok=False,
                    failure=FailureDetail(
                        code=FailureCode.RECOVERY_REQUIRED,
                        message="concurrent event present but could not reconstruct",
                        details={
                            "cause_type": type(exc).__name__,
                            "cause": str(exc),
                        },
                    ),
                )

        try:
            result = self._result_from_verified_prefix(
                namespace=bumped.namespace,
                run_id=bumped.run_id,
                sequence=seq,
                event_hash=event_hash,
                replayed=False,
            )
        except Exception as exc:  # noqa: BLE001
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="event written but prefix reconstruction failed",
                    details={"cause_type": type(exc).__name__, "cause": str(exc)},
                ),
            )

        if result.run is not None:
            try:
                self._put_snapshot(result.run)
            except Exception:  # noqa: BLE001
                # Event is authoritative; snapshot is cache only.
                pass

        self._persist_command_result(
            request,
            ok=result.ok,
            failure=result.failure,
            outputs={
                **dict(result.outputs),
                "run": result.run.to_payload() if result.run is not None else {},
            },
            event_hash=event_hash,
            sequence=seq,
        )
        return result

    def _put_snapshot(self, run: RunAggregate) -> ArtifactRef:
        # Snapshot is a cache — overwrite allowed; events remain authority.
        return self._store.put(
            namespace=run.namespace,
            kind=KIND_SNAPSHOT,
            artifact_id=run.run_id,
            payload=run.to_payload(),
            input_refs=(run.brief_ref,),
        )

    def _put_if_absent(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        input_refs: tuple = (),
        meta: Mapping[str, Any] | None = None,
    ) -> Any:
        putter = getattr(self._store, "put_if_absent", None)
        if not callable(putter):
            raise RuntimeError("store must implement put_if_absent for Phase 04")
        return putter(
            namespace=namespace,
            kind=kind,
            artifact_id=artifact_id,
            payload=payload,
            input_refs=input_refs,
            meta=meta,
        )

    def _persist_command_result(
        self,
        request: CommandRequest,
        *,
        ok: bool,
        failure: FailureDetail | None,
        outputs: Mapping[str, Any],
        event_hash: str | None = None,
        sequence: int | None = None,
    ) -> None:
        namespace = str(request.payload.get("namespace") or "")
        if not namespace:
            return
        payload = {
            "ok": ok,
            "failure": to_plain_dict(failure) if failure else None,
            "outputs": dict(outputs),
            "event_hash": event_hash,
            "sequence": sequence,
            "command": request.command,
            "idempotency_key": request.idempotency_key,
        }
        try:
            self._put_if_absent(
                namespace=namespace,
                kind=KIND_COMMAND_RESULT,
                artifact_id=self._command_result_id(request),
                payload=payload,
                meta={"terminal": True},
            )
        except Exception:  # noqa: BLE001
            # Best-effort; event log remains authority when present.
            pass

    def _read_command_result(self, request: CommandRequest) -> CommandResult | None:
        """Optional pointer cache: sequence/hash must exact-bind the event ledger.

        Missing cache → None (caller uses event-prefix idempotency).
        Present but unbound/mismatched → fail closed with RECOVERY_REQUIRED.
        """
        namespace = str(request.payload.get("namespace") or "")
        if not namespace:
            return None
        getter = getattr(self._store, "get_by_identity", None)
        if not callable(getter):
            return None
        try:
            payload = getter(
                namespace=namespace,
                kind=KIND_COMMAND_RESULT,
                artifact_id=self._command_result_id(request),
            )
        except Exception:  # noqa: BLE001
            return None
        seq = payload.get("sequence")
        event_hash = payload.get("event_hash")
        if seq is None or not event_hash:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="command-result cache missing sequence/event_hash binding",
                ),
                replayed=True,
            )
        try:
            return self._result_from_verified_prefix(
                namespace=namespace,
                run_id=request.run_id,
                sequence=int(seq),
                event_hash=str(event_hash),
                replayed=True,
            )
        except Exception as exc:  # noqa: BLE001
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="command-result cache does not exact-bind verified event ledger",
                    details={"cause_type": type(exc).__name__, "cause": str(exc)},
                ),
                replayed=True,
            )

    def _command_result_id(self, request: CommandRequest) -> str:
        return command_identity_key(
            run_id=request.run_id,
            aggregate_id=request.aggregate_id,
            idempotency_key=request.idempotency_key,
        )

    def _failure_from_mapping(
        self, raw: Mapping[str, Any] | None
    ) -> FailureDetail | None:
        if not raw:
            return None
        return FailureDetail(
            code=raw["code"],
            message=str(raw["message"]),
            severity=raw.get("severity", "hard_fail"),
            retryable=bool(raw.get("retryable", False)),
            details=dict(raw.get("details") or {}),
        )

    def _reconstruct_run_at(
        self,
        *,
        namespace: str,
        run_id: str,
        sequence: int,
        event_hash: str,
    ) -> RunAggregate:
        """Rebuild aggregate from verified event prefix through ``sequence``."""
        events = self._load_event_chain(namespace=namespace, run_id=run_id)
        if len(events) < sequence:
            raise ValueError(
                f"incomplete event prefix: have {len(events)}, need {sequence}"
            )
        prefix = events[:sequence]
        raw = prefix[-1]
        if int(raw.get("sequence", 0)) != sequence:
            raise ValueError(
                f"event sequence mismatch at prefix end: "
                f"{raw.get('sequence')} != {sequence}"
            )
        if str(raw.get("event_hash")) != str(event_hash):
            raise ValueError("event_hash mismatch at requested sequence")
        return self.replay_events(namespace=namespace, run_id=run_id, events=prefix)

    def _result_from_verified_prefix(
        self,
        *,
        namespace: str,
        run_id: str,
        sequence: int,
        event_hash: str,
        replayed: bool,
    ) -> CommandResult:
        """Materialize the original CommandResult from a verified event prefix."""
        reconstructed = self._reconstruct_run_at(
            namespace=namespace,
            run_id=run_id,
            sequence=sequence,
            event_hash=event_hash,
        )
        events = self._load_event_chain(namespace=namespace, run_id=run_id)
        raw = events[sequence - 1]
        body = {k: v for k, v in dict(raw).items() if k != "event_hash"}
        outs = dict(body.get("outputs") or {})
        cmd = outs.get("command_result")
        if not isinstance(cmd, Mapping):
            raise ValueError("verified event missing command_result")
        failure = self._failure_from_mapping(
            dict(cmd["failure"]) if cmd.get("failure") else None
        )
        event = event_from_body(body, event_hash=event_hash)
        return CommandResult(
            ok=bool(cmd.get("ok", False)),
            run=reconstructed,
            failure=failure,
            event=event,
            replayed=replayed,
            outputs=dict(cmd.get("outputs") or {}),
        )

    def _result_from_idem_entry(
        self, run: RunAggregate, prior: Mapping[str, Any]
    ) -> CommandResult:
        seq = prior.get("sequence")
        event_hash = prior.get("event_hash")
        if seq is None or event_hash is None:
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="idempotency entry missing sequence/event_hash",
                ),
                replayed=True,
            )
        try:
            return self._result_from_verified_prefix(
                namespace=run.namespace,
                run_id=run.run_id,
                sequence=int(seq),
                event_hash=str(event_hash),
                replayed=True,
            )
        except Exception as exc:  # noqa: BLE001
            return CommandResult(
                ok=False,
                failure=FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="could not reconstruct command result from event prefix",
                    details={"cause_type": type(exc).__name__, "cause": str(exc)},
                ),
                replayed=True,
            )

    def _store_get_object(self, ref: ObjectRef | ArtifactRef) -> Mapping[str, Any]:
        if isinstance(ref, ArtifactRef):
            return self._store.get(ref)
        # Event-gated types: Frozen event is the sole publish marker.
        if ref.object_type in EVENT_GATED_TYPES:
            try:
                return load_formal_payload(self._store, ref, allow_staging=False)
            except ObjectStoreError as exc:
                raise FreezeGateError(exc.failure) from exc
        if self._resolve_object is not None:
            body = self._resolve_object(ref)
            if isinstance(body, Mapping) and "body" in body and isinstance(body["body"], Mapping):
                body = body["body"]
            return body
        try:
            return load_formal_payload(self._store, ref, allow_staging=False)
        except ObjectStoreError as exc:
            raise FreezeGateError(exc.failure) from exc

    def _validate_replay_external_bindings(
        self,
        event: ControllerEvent,
        prior: RunAggregate | None,
        _out_run: Mapping[str, Any],
        outputs: Mapping[str, Any],
    ) -> None:
        """Re-check store-backed authority that cannot be inferred from a hash chain.

        Semantic replay owns transition math.  Gate-1 approvals and frozen
        manifests additionally depend on immutable objects in the trusted store;
        allowing their event copies to self-attest would permit a full rehash
        rewrite of caller choices and derived evidence.
        """
        if prior is None:
            return
        if event.command == "create_task":
            rebuilt = RunAggregate.from_payload(_out_run)
            task = rebuilt.tasks[event.aggregate_id]
            visibility = task.visibility or DEFAULT_RESEARCH_VISIBILITY
            authorized_inputs = [
                to_plain_dict(ref) for ref in _controller_task_authorized_refs(prior)
            ]
            if any(
                to_plain_dict(ref) not in authorized_inputs
                for ref in task.input_refs
            ):
                raise ValueError(
                    "task input_refs must be drawn from controller-authorized run lineage"
                )
            assert_refs_authorized(
                self._store,
                namespace=prior.namespace,
                refs=list(task.input_refs),
                allow_sealed=False,
                visibility=visibility,
            )
            if task.candidate_id is not None:
                candidate = prior.candidates[task.candidate_id]
                assert_refs_authorized(
                    self._store,
                    namespace=prior.namespace,
                    refs=[candidate.factor_ref],
                    allow_sealed=False,
                    visibility=visibility,
                )
            return
        if event.command == "build_task_view" and event.result_status == "ok":
            task = prior.tasks[event.aggregate_id]
            visibility = task.visibility or DEFAULT_RESEARCH_VISIBILITY
            refs: list[ObjectRef | ArtifactRef | EvidenceRef] = list(task.input_refs)
            if task.candidate_id is not None:
                refs.append(prior.candidates[task.candidate_id].factor_ref)
            assert_refs_authorized(
                self._store,
                namespace=prior.namespace,
                refs=refs,
                allow_sealed=False,
                visibility=visibility,
            )
            return
        if event.command == "record_gate1_approval":
            ordinary = {
                key: value
                for key, value in outputs.items()
                if key not in {"run", "command_result"}
            }
            candidate_id = str(ordinary["candidate_id"])
            candidate = prior.candidates[candidate_id]
            approval_ref = ArtifactRef(**dict(ordinary["gate1_approval_ref"]))
            approval = self._store.get(approval_ref)
            if approval.get("run_id") != prior.run_id:
                raise ValueError("Gate-1 approval run_id mismatch")
            if approval.get("candidate_id") != candidate_id:
                raise ValueError("Gate-1 approval candidate_id mismatch")
            stored_intent = approval.get("freeze_intent")
            if not isinstance(stored_intent, Mapping):
                raise ValueError("Gate-1 approval missing freeze_intent")
            canonical, fingerprint = self._validate_and_canonicalize_freeze_intent(
                run=prior,
                cand=candidate,
                intent_payload=dict(stored_intent),
            )
            if to_plain_dict(stored_intent) != canonical:
                raise ValueError("Gate-1 freeze_intent body mismatch vs canonical rebuild")
            if approval.get("freeze_intent_fingerprint") != fingerprint:
                raise ValueError("Gate-1 approval freeze intent fingerprint mismatch")
            if ordinary.get("freeze_intent_fingerprint") != fingerprint:
                raise ValueError("Gate-1 event freeze intent fingerprint mismatch")
            return
        if event.command == "authorize_oos":
            ordinary = _ordinary_event_outputs(outputs)
            context = self._oos_context(prior, event.aggregate_id)
            if isinstance(context, CommandResult):
                raise ValueError("authorize_oos frozen context invalid")
            cand, manifest_ref, manifest, _gate1_ref = context
            auth_ref = ObjectRef(**dict(ordinary["authorization_ref"]))
            authorization = resolve_typed_object(
                self._store, auth_ref, allow_staging=False
            )
            if not isinstance(authorization, OOSAuthorization):
                raise ValueError("authorize_oos object type mismatch")
            expected_key = self._oos_one_shot_key(
                run=prior,
                candidate=cand,
                manifest_ref=manifest_ref,
                sealed_split_id=str(manifest.split_refs["sealed"]),
            )
            if (
                authorization.run_id != prior.run_id
                or authorization.candidate_id != cand.candidate_id
                or to_plain_dict(authorization.manifest_ref) != to_plain_dict(manifest_ref)
                or authorization.sealed_split_id != manifest.split_refs["sealed"]
                or authorization.one_shot_key != expected_key
                or authorization.authorization_id
                != f"oos-auth-{expected_key}"
            ):
                raise ValueError("authorize_oos authorization binding mismatch")
            return
        if event.command == "complete_oos":
            ordinary = _ordinary_event_outputs(outputs)
            context = self._oos_context(prior, event.aggregate_id)
            if isinstance(context, CommandResult):
                raise ValueError("complete_oos frozen context invalid")
            cand, manifest_ref, manifest, _gate1_ref = context
            auth = self._load_oos_authorization(prior, cand, manifest_ref, manifest)
            if isinstance(auth, CommandResult):
                raise ValueError("complete_oos authorization invalid")
            auth_ref, authorization = auth
            from skills.factor_mining.contracts import rebuild_dataclass

            start_ref = ArtifactRef(**dict(ordinary["attempt_started_ref"]))
            terminal_ref = ArtifactRef(**dict(ordinary["attempt_terminal_ref"]))
            started = rebuild_dataclass(OOSAttempt, self._store.get(start_ref))
            terminal = rebuild_dataclass(OOSAttempt, self._store.get(terminal_ref))
            sealed_split_id = str(manifest.split_refs["sealed"])
            expected_attempt_id = f"oos-attempt-{authorization.one_shot_key}"
            if (
                started.status is not TaskResultStatus.RUNNING
                or terminal.status is TaskResultStatus.RUNNING
                or started.attempt_id != terminal.attempt_id
                or started.attempt_id != expected_attempt_id
                or started.authorization_id != authorization.authorization_id
                or terminal.authorization_id != authorization.authorization_id
                or started.run_id != prior.run_id
                or terminal.run_id != prior.run_id
                or started.candidate_id != cand.candidate_id
                or terminal.candidate_id != cand.candidate_id
                or to_plain_dict(started.manifest_ref) != to_plain_dict(manifest_ref)
                or to_plain_dict(terminal.manifest_ref) != to_plain_dict(manifest_ref)
                or started.sealed_split_id != sealed_split_id
                or terminal.sealed_split_id != sealed_split_id
                or started.one_shot_key != authorization.one_shot_key
                or terminal.one_shot_key != authorization.one_shot_key
            ):
                raise ValueError("complete_oos attempt ledger binding mismatch")
            raw_result = ordinary.get("oos_result_ref")
            if raw_result is not None:
                result_ref = ObjectRef(**dict(raw_result))
                result = resolve_typed_object(
                    self._store, result_ref, allow_staging=False
                )
                if (
                    not isinstance(result, OOSResult)
                    or result.result_id
                    != f"oos-result-{authorization.one_shot_key}"
                    or result.attempt_id != started.attempt_id
                    or result.authorization_id != authorization.authorization_id
                    or result.run_id != prior.run_id
                    or result.candidate_id != cand.candidate_id
                    or to_plain_dict(result.manifest_ref) != to_plain_dict(manifest_ref)
                    or result.sealed_split_id != sealed_split_id
                    or result.passed is not ordinary.get("passed")
                    or result.provenance.producer
                    != "factor_mining.controller.sealed_oos"
                    or result.provenance.namespace != prior.namespace
                    or result.provenance.data_version != manifest.data_version
                    or result.provenance.code_version
                    != manifest.analyze_engine_version
                    or result.provenance.experiment_version
                    != authorization.one_shot_key
                    or [to_plain_dict(ref) for ref in result.provenance.input_refs]
                    != [
                        to_plain_dict(prior.brief_ref),
                        to_plain_dict(cand.factor_ref),
                        to_plain_dict(manifest_ref),
                        to_plain_dict(auth_ref),
                    ]
                ):
                    raise ValueError("complete_oos result binding mismatch")
                evaluation = resolve_typed_object(
                    self._store, result.evaluation_ref, allow_staging=False
                )
                if (
                    not isinstance(evaluation, EvaluationReport)
                    or evaluation.request_id
                    != f"oos-evaluate-{authorization.one_shot_key}"
                    or to_plain_dict(evaluation.brief_ref)
                    != to_plain_dict(prior.brief_ref)
                    or to_plain_dict(evaluation.factor_ref)
                    != to_plain_dict(cand.factor_ref)
                    or evaluation.split_id != sealed_split_id
                    or evaluation.protocol_id != manifest.evaluation_protocol_id
                    or evaluation.engine_version != manifest.analyze_engine_version
                    or evaluation.data_version != manifest.data_version
                    or [to_plain_dict(ref) for ref in evaluation.pool_refs]
                    != [to_plain_dict(ref) for ref in manifest.pool_baseline_refs]
                ):
                    raise ValueError("complete_oos evaluation report binding mismatch")
                if evaluation.execution_ref is None:
                    raise ValueError("complete_oos evaluation missing execution_ref")
                execution = resolve_typed_object(
                    self._store, evaluation.execution_ref, allow_staging=False
                )
                if (
                    not isinstance(execution, FactorExecutionResult)
                    or execution.request_id
                    != f"oos-compute-{authorization.one_shot_key}"
                    or execution.experiment_id != authorization.one_shot_key
                    or execution.execution_id
                    != f"oos-execution-{authorization.one_shot_key}"
                    or to_plain_dict(execution.brief_ref)
                    != to_plain_dict(prior.brief_ref)
                    or to_plain_dict(execution.factor_ref)
                    != to_plain_dict(cand.factor_ref)
                    or execution.data_version != manifest.data_version
                    or execution.split_id != sealed_split_id
                    or execution.provenance.namespace != prior.namespace
                    or execution.provenance.data_version != manifest.data_version
                    or execution.provenance.code_version
                    != manifest.compute_engine_version
                    or execution.failure is not None
                ):
                    raise ValueError("complete_oos execution result binding mismatch")
                expected_evidence_refs = tuple(
                    fact.evidence
                    for section in evaluation.sections
                    for fact in section.facts
                )
                expected_artifact_refs = tuple(
                    fact.artifact
                    for section in evaluation.sections
                    for fact in section.facts
                    if fact.artifact is not None
                )
                if (
                    result.evidence_refs != expected_evidence_refs
                    or result.artifact_refs != expected_artifact_refs
                    or result.passed
                    is not self._oos_thresholds_passed(evaluation, manifest)
                ):
                    raise ValueError("complete_oos OOS result closure mismatch")
                if terminal.status is not TaskResultStatus.SUCCEEDED:
                    raise ValueError("complete_oos result requires successful terminal attempt")
            elif ordinary.get("passed") is not False:
                raise ValueError("complete_oos no-result terminal must set passed=false")
            return
        if event.command == "record_gate2_approval":
            ordinary = _ordinary_event_outputs(outputs)
            gate2_ref = ArtifactRef(**dict(ordinary["gate2_approval_ref"]))
            approval = self._store.get(gate2_ref)
            expected_approval_fields = {
                "run_id",
                "candidate_id",
                "manifest_ref",
                "oos_result_ref",
                "approved",
                "approver_id",
                "signed_at",
                "reason",
            }
            if (
                set(approval) != expected_approval_fields
                or approval.get("run_id") != prior.run_id
                or approval.get("candidate_id") != event.aggregate_id
                or approval.get("approved") is not ordinary.get("approved")
                or to_plain_dict(approval.get("manifest_ref"))
                != to_plain_dict(prior.freeze_manifest_ref)
                or to_plain_dict(approval.get("oos_result_ref"))
                != to_plain_dict(prior.oos_result_ref)
            ):
                raise ValueError("Gate-2 approval binding mismatch")
            if approval.get("approved") is True:
                if prior.oos_result_ref is None:
                    raise ValueError("Gate-2 approved without OOS result")
                result = resolve_typed_object(
                    self._store, prior.oos_result_ref, allow_staging=False
                )
                if not isinstance(result, OOSResult) or result.passed is not True:
                    raise ValueError("Gate-2 approved OOS result below threshold")
            return
        if event.command in {"promote", "reject_run"} and prior.status is ResearchRunStatus.OOS_TESTED:
            ordinary = _ordinary_event_outputs(outputs)
            knowledge_ref = ArtifactRef(**dict(ordinary["release_knowledge_ref"]))
            knowledge = self._store.get(knowledge_ref)
            expected_disposition = "promoted" if event.command == "promote" else "rejected"
            expected_knowledge_fields = {
                "knowledge_id",
                "run_id",
                "candidate_id",
                "disposition",
                "factor_ref",
                "manifest_ref",
                "oos_result_ref",
                "gate1_approval_ref",
                "gate2_approval_ref",
                "oos_attempt_refs",
            }
            candidate = prior.candidates[event.aggregate_id]
            if (
                set(knowledge) != expected_knowledge_fields
                or knowledge.get("run_id") != prior.run_id
                or knowledge.get("candidate_id") != event.aggregate_id
                or knowledge.get("disposition") != expected_disposition
                or to_plain_dict(knowledge.get("factor_ref"))
                != to_plain_dict(candidate.factor_ref)
                or to_plain_dict(knowledge.get("manifest_ref"))
                != to_plain_dict(prior.freeze_manifest_ref)
                or to_plain_dict(knowledge.get("oos_result_ref"))
                != to_plain_dict(prior.oos_result_ref)
                or to_plain_dict(knowledge.get("gate1_approval_ref"))
                != to_plain_dict(prior.gate1_approval_ref)
                or to_plain_dict(knowledge.get("gate2_approval_ref"))
                != to_plain_dict(prior.gate2_approval_ref)
                or list(knowledge.get("oos_attempt_refs") or [])
                != [to_plain_dict(ref) for ref in prior.oos_attempt_refs]
            ):
                raise ValueError("release knowledge binding mismatch")
            return
        if event.command != "freeze":
            return

        ordinary = {
            key: value
            for key, value in outputs.items()
            if key not in {"run", "command_result"}
        }
        candidate = prior.candidates[event.aggregate_id]
        approval = require_gate1_approval(
            prior, store_get=self._store.get, candidate_id=candidate.candidate_id
        )
        approval_payload = self._store.get(approval)
        stored_intent = approval_payload.get("freeze_intent")
        if not isinstance(stored_intent, Mapping):
            raise ValueError("Gate-1 approval missing freeze_intent")
        canonical, fingerprint = self._validate_and_canonicalize_freeze_intent(
            run=prior,
            cand=candidate,
            intent_payload=dict(stored_intent),
        )
        if to_plain_dict(stored_intent) != canonical:
            raise ValueError("Gate-1 freeze_intent body mismatch vs canonical rebuild")
        if approval_payload.get("freeze_intent_fingerprint") != fingerprint:
            raise ValueError("Gate-1 approval freeze intent fingerprint mismatch")
        if ordinary.get("freeze_intent_fingerprint") != fingerprint:
            raise ValueError("freeze event freeze intent fingerprint mismatch")
        validate_freeze_evidence_refs(
            run=prior,
            candidate=candidate,
            store_get_object=self._store_get_object,
            store=self._store,
        )
        brief = self._load_brief(prior.brief_ref)
        expected = build_freeze_manifest(
            manifest_id=str(canonical["manifest_id"]),
            run=prior,
            candidate=candidate,
            brief=brief,
            approval_ref=approval,
            compute_engine_version=str(canonical["compute_engine_version"]),
            analyze_engine_version=str(canonical["analyze_engine_version"]),
            evaluation_protocol_id=str(canonical["evaluation_protocol_id"]),
            direction=str(canonical["direction"]),
            params=dict(canonical["params"]),
            missing_policy=str(canonical["missing_policy"]),
            adjustment_policy=str(canonical["adjustment_policy"]),
            outlier_policy=str(canonical["outlier_policy"]),
            neutralization_policy=str(canonical["neutralization_policy"]),
            holding_horizon_bars=int(canonical["holding_horizon_bars"]),
            rebalance=str(canonical["rebalance"]),
            cost=brief.cost,
            pool_baseline_refs=tuple(
                ObjectRef(**dict(item)) for item in canonical["pool_baseline_refs"]
            ),
            oos_thresholds=dict(canonical["oos_thresholds"]),
            oos_metric_selectors=dict(canonical["oos_metric_selectors"]),
            provenance=brief.provenance,
            split_refs=dict(canonical["split_refs"]),
        )
        manifest_ref = ObjectRef(**dict(ordinary["manifest_ref"]))
        if (
            manifest_ref.object_type != "FreezeManifest"
            or manifest_ref.object_id != expected.manifest_id
            or manifest_ref.content_hash != expected.content_hash
            or manifest_ref.namespace != prior.namespace
        ):
            raise ValueError("freeze manifest_ref must exact-bind canonical manifest")
        staged = load_staging_payload(
            self._store,
            namespace=prior.namespace,
            object_type="FreezeManifest",
            object_id=expected.manifest_id,
        )
        if to_plain_dict(staged) != to_plain_dict(expected):
            raise ValueError("freeze staging manifest mismatch vs canonical manifest")
        if to_plain_dict(ordinary.get("manifest")) != to_plain_dict(expected):
            raise ValueError("freeze event manifest mismatch vs canonical manifest")

    def _load_event_chain(
        self, *, namespace: str, run_id: str
    ) -> list[dict[str, Any]]:
        """Load verified event payloads; listed-but-unreadable is corruption."""
        try:
            return load_run_event_payloads(
                self._store, namespace=namespace, run_id=run_id
            )
        except EventChainError as exc:
            raise ValueError(exc.failure.message) from exc

    def _load_snapshot_cache(
        self, *, namespace: str, run_id: str
    ) -> RunAggregate | None:
        getter = getattr(self._store, "get_by_identity", None)
        if not callable(getter):
            return None
        try:
            payload = getter(
                namespace=namespace, kind=KIND_SNAPSHOT, artifact_id=run_id
            )
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(payload, Mapping):
            return None
        run = RunAggregate.from_payload(payload)
        # Fail closed if snapshot head does not match event chain when events exist.
        events = self._load_event_chain(namespace=namespace, run_id=run_id)
        if events:
            head = events[-1]
            if (
                int(head.get("sequence", -1)) != run.event_head_seq
                or str(head.get("event_hash")) != run.event_head_hash
            ):
                return self.replay_events(
                    namespace=namespace, run_id=run_id, events=events
                )
        return run

    def _require_run(self, request: CommandRequest) -> RunAggregate:
        namespace = str(request.payload.get("namespace") or "")
        if not namespace:
            raise ValueError("payload.namespace required")
        run = self.load_run(namespace=namespace, run_id=request.run_id)
        if run is None:
            raise ValueError(f"run not found: {request.run_id}")
        read_only = {"build_task_view"}
        frozen_allowed = {"authorize_oos", "complete_oos"}
        oos_tested_allowed = {
            "complete_oos",
            "record_gate2_approval",
            "promote",
            "reject_run",
        }
        if run.status is ResearchRunStatus.FROZEN and request.command not in (
            read_only | frozen_allowed
        ):
            raise IllegalTransitionError(
                f"run is frozen; refusing {request.command} outside sealed OOS"
            )
        if run.status is ResearchRunStatus.OOS_TESTED and request.command not in (
            read_only | oos_tested_allowed
        ):
            raise IllegalTransitionError(
                f"run is OOS-tested; refusing {request.command} outside release"
            )
        if (
            run.status in PHASE04_RUN_TERMINAL
            and run.status is not ResearchRunStatus.FROZEN
            and request.command not in read_only
        ):
            raise IllegalTransitionError(
                f"run is terminal ({run.status.value}); refusing {request.command}"
            )
        return run

    def _require_candidate(self, run: RunAggregate, candidate_id: str) -> CandidateAggregate:
        cand = run.candidates.get(candidate_id)
        if cand is None:
            raise IllegalTransitionError(f"unknown candidate {candidate_id}")
        return cand

    def _require_task(self, run: RunAggregate, task_id: str) -> TaskAggregate:
        task = run.tasks.get(task_id)
        if task is None:
            raise IllegalTransitionError(f"unknown task {task_id}")
        return task

    def _load_brief(self, brief_ref: ObjectRef) -> ResearchBrief:
        if self._resolve_brief is not None:
            return self._resolve_brief(brief_ref)
        raw = self._store_get_object(brief_ref)
        body = raw.get("body", raw) if isinstance(raw, Mapping) else raw
        from skills.factor_mining.contracts import rebuild_dataclass

        return rebuild_dataclass(ResearchBrief, body)

    def _idempotency_index_key(self, request: CommandRequest) -> str:
        return command_identity_key(
            run_id=request.run_id,
            aggregate_id=request.aggregate_id,
            idempotency_key=request.idempotency_key,
        )


    def _oos_thresholds_from_brief(self, brief: ResearchBrief) -> dict[str, float]:
        """Canonicalize non-None numeric oos_criteria fields into float thresholds."""
        criteria = brief.oos_criteria
        out: dict[str, float] = {}
        for key in ("min_rank_ic_ir", "min_coverage", "max_turnover"):
            value = getattr(criteria, key)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise FreezeGateError(
                    FailureDetail(
                        code=FailureCode.INVALID_PARAMETERS,
                        message=f"oos_criteria.{key} must be numeric float threshold",
                    )
                )
            out[key] = float(value)
        if not out:
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message="ResearchBrief.oos_criteria must yield at least one float threshold",
                )
            )
        return out

    def _derive_analyze_engine_version(
        self, run: RunAggregate, cand: CandidateAggregate
    ) -> str:
        versions: list[str] = []
        for label, ref in (
            ("preflight", cand.preflight_ref),
            ("evaluation", cand.evaluation_ref),
            ("compare", cand.compare_ref),
        ):
            if ref is None:
                raise FreezeGateError(
                    FailureDetail(
                        code=FailureCode.INVALID_STATE,
                        message=f"missing {label}_ref for analyze engine derivation",
                    )
                )
            report = resolve_typed_object(self._store, ref, allow_staging=False)
            if not isinstance(report, EvaluationReport):
                raise FreezeGateError(
                    FailureDetail(
                        code=FailureCode.SCHEMA_MISMATCH,
                        message=f"{label}_ref must resolve to EvaluationReport",
                    )
                )
            report.validate_hash()
            if to_plain_dict(report.factor_ref) != to_plain_dict(cand.factor_ref):
                raise FreezeGateError(
                    FailureDetail(
                        code=FailureCode.HASH_MISMATCH,
                        message=f"{label} factor_ref does not bind candidate",
                    )
                )
            if to_plain_dict(report.brief_ref) != to_plain_dict(run.brief_ref):
                raise FreezeGateError(
                    FailureDetail(
                        code=FailureCode.HASH_MISMATCH,
                        message=f"{label} brief_ref does not bind run",
                    )
                )
            versions.append(str(report.engine_version))
        if len(set(versions)) != 1:
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="preflight/evaluation/compare engine_version disagree",
                    details={"versions": versions},
                )
            )
        return versions[0]

    def _derive_evaluation_protocol_id(
        self, run: RunAggregate, cand: CandidateAggregate
    ) -> str:
        """Freeze the trusted protocol identity from the prior evaluation report."""
        if cand.evaluation_ref is None:
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.INVALID_STATE,
                    message="evaluation_ref required for protocol derivation",
                )
            )
        report = resolve_typed_object(
            self._store, cand.evaluation_ref, allow_staging=False
        )
        if not isinstance(report, EvaluationReport):
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.SCHEMA_MISMATCH,
                    message="evaluation_ref must resolve to EvaluationReport",
                )
            )
        report.validate_hash()
        if (
            to_plain_dict(report.brief_ref) != to_plain_dict(run.brief_ref)
            or to_plain_dict(report.factor_ref) != to_plain_dict(cand.factor_ref)
        ):
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="evaluation report does not exact-bind run/candidate",
                )
            )
        if not report.protocol_id:
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.INVALID_REFERENCE,
                    message="evaluation report protocol_id missing",
                )
            )
        return report.protocol_id

    def _derive_compute_engine_version(
        self, run: RunAggregate, cand: CandidateAggregate
    ) -> str:
        if cand.execution_ref is None:
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.INVALID_STATE,
                    message="execution_ref required for compute engine derivation",
                )
            )
        execution = resolve_typed_object(
            self._store, cand.execution_ref, allow_staging=False
        )
        if not isinstance(execution, FactorExecutionResult):
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.SCHEMA_MISMATCH,
                    message="execution_ref must resolve to FactorExecutionResult",
                )
            )
        from skills.factor_mining.adapters.execution_identity import (
            execution_envelope_identity,
        )

        recomputed = execution_envelope_identity(execution)
        if recomputed != execution.fingerprint:
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="execution fingerprint recomputation mismatch",
                )
            )
        if to_plain_dict(execution.factor_ref) != to_plain_dict(cand.factor_ref):
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="execution factor_ref does not bind candidate",
                )
            )
        if to_plain_dict(execution.brief_ref) != to_plain_dict(run.brief_ref):
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="execution brief_ref does not bind run",
                )
            )
        code_version = str(execution.provenance.code_version)
        if not code_version:
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.INVALID_REFERENCE,
                    message="execution provenance.code_version missing",
                )
            )
        return code_version

    def _validate_and_canonicalize_freeze_intent(
        self,
        *,
        run: RunAggregate,
        cand: CandidateAggregate,
        intent_payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], str]:
        """Validate Gate-1 freeze intent; derive all Brief/Factor/evidence fields."""
        from skills.factor_mining.contracts import FactorSpec

        require_complete_refs(cand)
        brief = self._load_brief(run.brief_ref)
        factor = resolve_typed_object(self._store, cand.factor_ref, allow_staging=False)
        if not isinstance(factor, FactorSpec):
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.SCHEMA_MISMATCH,
                    message="candidate factor_ref must resolve to FactorSpec",
                )
            )
        # Caller-only choices that cannot be derived.
        required_choices = (
            "manifest_id",
            "outlier_policy",
            "neutralization_policy",
            "pool_baseline_refs",
        )
        missing = [k for k in required_choices if k not in intent_payload]
        if missing:
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message="freeze_intent missing required caller fields",
                    details={"missing": missing},
                )
            )
        for key in ("manifest_id", "outlier_policy", "neutralization_policy"):
            value = intent_payload.get(key)
            if not isinstance(value, str) or not value or value.strip() != value:
                raise FreezeGateError(
                    FailureDetail(
                        code=FailureCode.INVALID_PARAMETERS,
                        message=f"freeze_intent.{key} must be a non-empty str",
                        details={"field": key},
                    )
                )
        # Derived fields below may appear in intent only when exact-matching evidence.

        direction = factor.expected_direction
        params = dict(factor.formula.params)
        missing_policy = factor.missing_policy
        adjustment_policy = brief.adjustment
        holding_horizon_bars = int(brief.horizon_bars)
        rebalance = str(brief.rebalance)
        split_refs = {
            "train": brief.train.split_id,
            "validation": brief.validation.split_id,
            "sealed": brief.sealed.split_id,
        }
        oos_thresholds = self._oos_thresholds_from_brief(brief)
        analyze_engine_version = self._derive_analyze_engine_version(run, cand)
        evaluation_protocol_id = self._derive_evaluation_protocol_id(run, cand)
        compute_engine_version = self._derive_compute_engine_version(run, cand)
        try:
            oos_metric_selectors = frozen_oos_metric_selectors(oos_thresholds)
        except ValueError as exc:
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.INVALID_PARAMETERS,
                    message=str(exc),
                )
            ) from exc

        derived = {
            "run_id": run.run_id,
            "candidate_id": cand.candidate_id,
            "brief_ref": to_plain_dict(run.brief_ref),
            "factor_ref": to_plain_dict(cand.factor_ref),
            "preflight_ref": to_plain_dict(cand.preflight_ref),
            "execution_ref": to_plain_dict(cand.execution_ref),
            "evaluation_ref": to_plain_dict(cand.evaluation_ref),
            "compare_ref": to_plain_dict(cand.compare_ref),
            "review_refs": [to_plain_dict(r) for r in cand.review_refs],
            "pool_decision_ref": to_plain_dict(cand.pool_decision_ref),
            "universe": list(brief.universe),
            "data_version": brief.data_version,
            "split_refs": split_refs,
            "compute_engine_version": compute_engine_version,
            "analyze_engine_version": analyze_engine_version,
            "evaluation_protocol_id": evaluation_protocol_id,
            "direction": direction,
            "params": params,
            "missing_policy": missing_policy,
            "adjustment_policy": adjustment_policy,
            "holding_horizon_bars": holding_horizon_bars,
            "rebalance": rebalance,
            "cost": to_plain_dict(brief.cost),
            "oos_thresholds": oos_thresholds,
            "oos_metric_selectors": oos_metric_selectors,
            "provenance": to_plain_dict(brief.provenance),
        }
        for key, expected in derived.items():
            if key not in intent_payload:
                continue
            got = intent_payload[key]
            if key in {
                "params",
                "split_refs",
                "oos_thresholds",
                "oos_metric_selectors",
                "cost",
                "provenance",
            }:
                comparable_got = dict(got) if isinstance(got, Mapping) else got
                comparable_exp = dict(expected) if isinstance(expected, Mapping) else expected
            elif key in {
                "brief_ref",
                "factor_ref",
                "preflight_ref",
                "execution_ref",
                "evaluation_ref",
                "compare_ref",
                "pool_decision_ref",
            }:
                comparable_got = dict(got)
                comparable_exp = dict(expected)
            elif key == "review_refs":
                comparable_got = [dict(item) for item in got]
                comparable_exp = list(expected)
            elif key == "universe":
                comparable_got = list(got)
                comparable_exp = list(expected)
            else:
                comparable_got = got
                comparable_exp = expected
            if comparable_got != comparable_exp:
                raise FreezeGateError(
                    FailureDetail(
                        code=FailureCode.HASH_MISMATCH,
                        message=f"freeze_intent.{key} must exact-match derived evidence",
                        details={"expected": comparable_exp, "got": comparable_got},
                    )
                )

        baselines = tuple(
            ObjectRef(**dict(item)) for item in intent_payload["pool_baseline_refs"]
        )
        for base_ref in baselines:
            if base_ref.namespace != run.namespace:
                raise FreezeGateError(
                    FailureDetail(
                        code=FailureCode.INVALID_REFERENCE,
                        message="pool baseline namespace mismatch",
                    )
                )
            try:
                load_formal_payload(self._store, base_ref, allow_staging=False)
            except ObjectStoreError as exc:
                raise FreezeGateError(exc.failure) from exc

        canonical = {
            "manifest_id": str(intent_payload["manifest_id"]),
            **derived,
            "outlier_policy": str(intent_payload["outlier_policy"]),
            "neutralization_policy": str(intent_payload["neutralization_policy"]),
            "pool_baseline_refs": [to_plain_dict(r) for r in baselines],
        }
        return to_plain_dict(canonical), content_hash(canonical)

    def _assert_port_output_lineage(
        self,
        *,
        run: RunAggregate,
        cand: CandidateAggregate,
        request_obj: EvaluationRequest | FactorComputeRequest,
        report: EvaluationReport | FactorExecutionResult | None = None,
        stage: str,
    ) -> FailureDetail | None:
        """Fail closed when port outputs do not exact-bind all contract lineage."""
        if report is None:
            return FailureDetail(
                code=FailureCode.INVALID_OUTPUT_TYPE,
                message=f"{stage} produced no output",
            )
        if report.request_id != request_obj.request_id:
            return FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message=f"{stage} request_id mismatch",
            )
        if to_plain_dict(report.factor_ref) != to_plain_dict(cand.factor_ref):
            return FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message=f"{stage} factor_ref does not exact-bind candidate",
            )
        if to_plain_dict(report.factor_ref) != to_plain_dict(request_obj.factor_ref):
            return FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message=f"{stage} factor_ref does not exact-bind request",
            )
        if to_plain_dict(report.brief_ref) != to_plain_dict(run.brief_ref):
            return FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message=f"{stage} brief_ref does not exact-bind run",
            )
        if to_plain_dict(report.brief_ref) != to_plain_dict(request_obj.brief_ref):
            return FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message=f"{stage} brief_ref does not exact-bind request",
            )
        if report.data_version != request_obj.data_version:
            return FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message=f"{stage} data_version mismatch",
            )
        if report.split_id != request_obj.split_id:
            return FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message=f"{stage} split_id mismatch",
            )
        if report.provenance.namespace != run.namespace:
            return FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message=f"{stage} provenance.namespace mismatch",
            )
        if report.provenance.data_version != request_obj.data_version:
            return FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message=f"{stage} provenance.data_version mismatch",
            )
        if isinstance(report, EvaluationReport):
            if not isinstance(request_obj, EvaluationRequest):
                return FailureDetail(
                    code=FailureCode.INVALID_OUTPUT_TYPE,
                    message=f"{stage} EvaluationReport requires EvaluationRequest",
                )
            report.validate_hash()
            if report.protocol_id != request_obj.protocol_id:
                return FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message=f"{stage} protocol_id mismatch",
                )
            got_pool = [to_plain_dict(r) for r in report.pool_refs]
            exp_pool = [to_plain_dict(r) for r in request_obj.pool_refs]
            if got_pool != exp_pool:
                return FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message=f"{stage} pool_refs mismatch",
                )
            req_exec = request_obj.execution_ref
            if req_exec is None:
                if report.execution_ref is not None:
                    return FailureDetail(
                        code=FailureCode.HASH_MISMATCH,
                        message=f"{stage} execution_ref must be None when request has none",
                    )
            elif report.execution_ref is None or to_plain_dict(
                report.execution_ref
            ) != to_plain_dict(req_exec):
                return FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message=f"{stage} execution_ref mismatch",
                )
        if isinstance(report, FactorExecutionResult):
            if not isinstance(request_obj, FactorComputeRequest):
                return FailureDetail(
                    code=FailureCode.INVALID_OUTPUT_TYPE,
                    message=f"{stage} FactorExecutionResult requires FactorComputeRequest",
                )
            from skills.factor_mining.adapters.execution_identity import (
                execution_envelope_identity,
            )

            if report.experiment_id != request_obj.experiment_id:
                return FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message=f"{stage} experiment_id mismatch",
                )
            if report.execution_id != request_obj.execution_id:
                return FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message=f"{stage} execution_id mismatch",
                )
            recomputed = execution_envelope_identity(report)
            if recomputed != report.fingerprint:
                return FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message=f"{stage} fingerprint recomputation mismatch",
                    details={"expected": report.fingerprint, "got": recomputed},
                )
            if report.failure is None:
                if report.values_ref is None or report.valid_mask_ref is None:
                    return FailureDetail(
                        code=FailureCode.INVALID_OUTPUT_TYPE,
                        message=f"{stage} successful execution missing values/mask refs",
                    )
                if (
                    report.values_content_hash is None
                    or report.valid_mask_content_hash is None
                ):
                    return FailureDetail(
                        code=FailureCode.HASH_MISMATCH,
                        message=f"{stage} successful execution missing content hashes",
                    )
        return None

    def _invalid_state(self, run: RunAggregate, message: str) -> CommandResult:
        return CommandResult(
            ok=False,
            run=run,
            failure=FailureDetail(code=FailureCode.INVALID_STATE, message=message),
        )

    def _stop_blocked(self, run: RunAggregate, reason: str) -> CommandResult:
        return CommandResult(
            ok=False,
            run=run,
            failure=FailureDetail(
                code=FailureCode.BUDGET_EXCEEDED
                if reason.startswith("budget")
                else FailureCode.INVALID_STATE,
                message=f"stop policy blocked command: {reason}",
                details=stop_event_details(reason),
            ),
        )


def _state_after_digest(run: RunAggregate) -> str:
    return state_after_digest_from_run_payload(run.to_payload())


def _ordinary_event_outputs(outputs: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in outputs.items()
        if key not in {"run", "command_result"}
    }


def _aggregate_kind(request: CommandRequest) -> str:
    if request.command in {
        "create_run",
        "activate",
        "reject_run",
        "stop",
        "request_freeze",
        "freeze",
        "record_gate1_approval",
        "authorize_oos",
        "complete_oos",
        "record_gate2_approval",
        "promote",
    }:
        return "run"
    if request.command in {
        "claim_task",
        "start_task",
        "submit_task",
        "fail_task",
        "cancel_task",
        "timeout_task",
        "create_task",
        "build_task_view",
    }:
        return "task"
    return "candidate"


def _report_hard_failed(report: EvaluationReport) -> bool:
    if report.failure is not None and report.failure.severity is Severity.HARD_FAIL:
        return True
    for section in report.sections:
        for check in section.checks:
            if (not check.passed) and check.severity is Severity.HARD_FAIL:
                return True
    return False


def _report_as_object_ref(report: EvaluationReport, namespace: str) -> ObjectRef:
    return ObjectRef(
        object_type="EvaluationReport",
        object_id=report.report_id,
        content_hash=report.content_hash,
        namespace=namespace,
    )


def _execution_as_object_ref(
    result: FactorExecutionResult, namespace: str
) -> ObjectRef:
    digest = result.fingerprint
    if len(digest) != 64:
        digest = content_hash(
            {
                "execution_id": result.execution_id,
                "fingerprint": result.fingerprint,
            }
        )
    return ObjectRef(
        object_type="FactorExecutionResult",
        object_id=result.execution_id,
        content_hash=digest,
        namespace=namespace,
    )


def _coerce_ref(
    raw: Mapping[str, Any] | ObjectRef | ArtifactRef | EvidenceRef,
) -> ObjectRef | ArtifactRef | EvidenceRef:
    if isinstance(raw, (ObjectRef, ArtifactRef, EvidenceRef)):
        return raw
    if "object_type" in raw:
        return ObjectRef(**dict(raw))
    if "evidence_id" in raw:
        value = dict(raw)
        artifact = value.get("artifact")
        if isinstance(artifact, Mapping):
            value["artifact"] = ArtifactRef(**dict(artifact))
        return EvidenceRef(**value)
    return ArtifactRef(**dict(raw))


def _controller_task_authorized_refs(
    run: RunAggregate,
) -> tuple[ObjectRef, ...]:
    """Return only refs already published by Controller-owned run state.

    A task command may select a minimal subset of these refs, but cannot turn an
    unrelated object merely present in the namespace into a task authorization.
    """
    refs: list[ObjectRef] = [run.brief_ref]
    for candidate in run.candidates.values():
        refs.append(candidate.factor_ref)
        for ref in (
            candidate.parent_ref,
            candidate.preflight_ref,
            candidate.execution_ref,
            candidate.evaluation_ref,
            candidate.compare_ref,
            candidate.pool_decision_ref,
            candidate.freeze_manifest_ref,
        ):
            if ref is not None:
                refs.append(ref)
        refs.extend(candidate.review_refs)
    return tuple(refs)


_ = (ResearchBudget, exhausted_keys)


__all__ = [
    "CommandRequest",
    "CommandResult",
    "ResearchController",
    "KIND_SNAPSHOT",
    "KIND_EVENT",
    "KIND_GATE1",
    "KIND_FAILURE_KNOWLEDGE",
    "KIND_STAGING",
    "KIND_COMMAND_RESULT",
    "COMMAND_CAPABILITIES",
]
