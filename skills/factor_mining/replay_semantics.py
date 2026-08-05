"""Deterministic semantic validation over a hash-verified event prefix.

Hash-chain verification alone is insufficient: each event's ``outputs.run``
must also be a coherent successor of the previously reconstructed aggregate.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from skills.factor_mining.budget import BUDGET_KEYS
from skills.factor_mining.contracts import (
    SCHEMA_VERSION,
    CandidateStatus,
    FailureCode,
    FailureDetail,
    ObjectRef,
    ResearchRunStatus,
    ReviewConclusion,
    TaskLifecycleStatus,
    canonical_value,
    content_hash,
    to_plain_dict,
)
from skills.factor_mining.events import event_from_body
from skills.factor_mining.identity import command_identity_key
from skills.factor_mining.isolation import (
    DEFAULT_RESEARCH_VISIBILITY,
    VIS_SEALED,
    is_sealed_marker,
)
from skills.factor_mining.state import (
    CANDIDATE_TRANSITIONS,
    RUN_TRANSITIONS,
    TASK_TRANSITIONS,
    RunAggregate,
)


class ReplaySemanticsError(Exception):
    """Fail-closed semantic replay corruption."""

    def __init__(self, failure: FailureDetail) -> None:
        super().__init__(failure.message)
        self.failure = failure


def _fail(message: str, **details: Any) -> ReplaySemanticsError:
    return ReplaySemanticsError(
        FailureDetail(
            code=FailureCode.HASH_MISMATCH,
            message=message,
            details=details or None,
        )
    )


def _require_budget_map(
    values: Mapping[str, Any], *, label: str
) -> dict[str, int]:
    if not isinstance(values, Mapping):
        raise _fail(f"{label} must be a mapping")
    if set(values) != set(BUDGET_KEYS):
        raise _fail(
            f"{label} must contain exact known budget keys",
            expected=list(BUDGET_KEYS),
            got=sorted(values),
        )
    out: dict[str, int] = {}
    for key in BUDGET_KEYS:
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise _fail(f"{label}.{key} must be a non-bool nonnegative int")
        if value < 0:
            raise _fail(f"{label}.{key} must be nonnegative")
        out[key] = value
    return out


def _require_reservations(
    values: Mapping[str, Any], *, limits: Mapping[str, int]
) -> dict[str, dict[str, int]]:
    if not isinstance(values, Mapping):
        raise _fail("budget_reservations must be a mapping")
    out: dict[str, dict[str, int]] = {}
    for res_id, amounts in values.items():
        if not isinstance(res_id, str) or not res_id:
            raise _fail("reservation_id must be a non-empty str")
        if not isinstance(amounts, Mapping):
            raise _fail("reservation amounts must be a mapping")
        cleaned: dict[str, int] = {}
        for key, value in amounts.items():
            if key not in BUDGET_KEYS:
                raise _fail("reservation has unknown budget key", key=key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise _fail("reservation amounts must be non-bool nonnegative ints")
            if value > int(limits.get(key, 0)):
                raise _fail(
                    "reservation amount exceeds budget limit",
                    key=key,
                    amount=value,
                    limit=limits.get(key),
                )
            if value:
                cleaned[key] = value
        out[str(res_id)] = cleaned
    return out


def _pipeline_terminal_legal(from_status: str, to_status: str) -> bool:
    """Composite legality for run_candidate_pipeline terminal outcomes."""
    if from_status == to_status:
        return True
    if to_status == CandidateStatus.REJECTED.value:
        allowed_from = {
            CandidateStatus.PROPOSED.value,
            CandidateStatus.PREFLIGHT_PASSED.value,
            CandidateStatus.COMPUTED.value,
            CandidateStatus.EVALUATED.value,
            CandidateStatus.REVIEW_PENDING.value,
        }
        return from_status in allowed_from
    return (
        from_status == CandidateStatus.PROPOSED.value
        and to_status == CandidateStatus.REVIEW_PENDING.value
    )


def _transition_legal(
    *,
    aggregate_kind: str,
    command: str,
    from_status: str,
    to_status: str,
    result_status: str,
) -> bool:
    if command == "create_run":
        return from_status == "none" and to_status == ResearchRunStatus.BRIEFED.value
    if command == "run_candidate_pipeline":
        if result_status == "started":
            return from_status == to_status
        return _pipeline_terminal_legal(from_status, to_status)
    if aggregate_kind == "run":
        if command == "record_gate1_approval":
            return from_status == to_status
        try:
            current = ResearchRunStatus(from_status)
        except ValueError:
            return False
        expected = RUN_TRANSITIONS.get((current, command))
        return expected is not None and expected.value == to_status
    if aggregate_kind == "candidate":
        if command == "propose_candidate":
            return (
                from_status == "none"
                and to_status == CandidateStatus.PROPOSED.value
            )
        if command == "submit_review":
            if from_status == to_status:
                return from_status in {
                    CandidateStatus.REVIEW_PENDING.value,
                    CandidateStatus.DEBATING.value,
                    CandidateStatus.SYNTHESIZING.value,
                }
            for (cur, action), nxt in CANDIDATE_TRANSITIONS.items():
                if cur.value == from_status and nxt.value == to_status:
                    if action in {"reject", "mark_debating", "mark_synthesizing"}:
                        return True
            return False
        if command == "submit_pool_decision":
            if to_status == CandidateStatus.FREEZE_READY.value:
                return from_status == CandidateStatus.REVIEW_PENDING.value
            if to_status == CandidateStatus.REJECTED.value:
                return from_status in {
                    CandidateStatus.REVIEW_PENDING.value,
                    CandidateStatus.DEBATING.value,
                    CandidateStatus.SYNTHESIZING.value,
                    CandidateStatus.FREEZE_READY.value,
                }
            return False
        if command == "revise_candidate":
            # New child candidate is always proposed; from_status is parent status.
            return to_status == CandidateStatus.PROPOSED.value
        if command == "reject_candidate":
            try:
                current = CandidateStatus(from_status)
            except ValueError:
                return False
            expected = CANDIDATE_TRANSITIONS.get((current, "reject"))
            return expected is not None and expected.value == to_status
        return False
    if aggregate_kind == "task":
        token = {
            "claim_task": "claim",
            "start_task": "start",
            "submit_task": "submit",
            "fail_task": "fail",
            "cancel_task": "cancel",
            "timeout_task": "timeout",
        }.get(command)
        if command == "create_task":
            return from_status == "none" and to_status == TaskLifecycleStatus.PENDING.value
        if command == "build_task_view":
            return from_status == to_status
        if token is None:
            return False
        try:
            current = TaskLifecycleStatus(from_status)
        except ValueError:
            return False
        expected = TASK_TRANSITIONS.get((current, token))
        return expected is not None and expected.value == to_status
    return False


def _phase_of(event: Any, outputs: Mapping[str, Any]) -> str | None:
    phase = outputs.get("pipeline_phase")
    if isinstance(phase, str) and phase:
        return phase
    if event.result_status == "started":
        return "started"
    if event.command == "run_candidate_pipeline" and event.result_status in {
        "ok",
        "failed",
    }:
        return "terminal"
    return None


# Commands with exact RunAggregate delta rules implemented in this module.
# Remaining commands stay on legacy transition/idempotency checks until Step B.
_DELTA_IMPLEMENTED = frozenset(
    {
        "create_run",
        "activate",
        "request_freeze",
        "stop",
        "reject_run",
        "record_gate1_approval",
        "authorize_oos",
        "complete_oos",
        "record_gate2_approval",
        "promote",
        "propose_candidate",
        "revise_candidate",
        "submit_review",
        "submit_pool_decision",
        "reject_candidate",
        "run_candidate_pipeline",
        "freeze",
        "create_task",
        "claim_task",
        "start_task",
        "submit_task",
        "fail_task",
        "cancel_task",
        "timeout_task",
        "build_task_view",
    }
)

_PIPELINE_CALLS = ("preflight", "execute", "evaluate", "compare_to_pool")
_PIPELINE_REF_FIELDS = (
    "preflight_ref",
    "execution_ref",
    "evaluation_ref",
    "compare_ref",
)
_PIPELINE_STATUS_AFTER_STAGES = (
    CandidateStatus.PROPOSED,
    CandidateStatus.PREFLIGHT_PASSED,
    CandidateStatus.COMPUTED,
    CandidateStatus.EVALUATED,
)

_RUN_BUSINESS_KEYS = (
    "status",
    "stop_reason",
    "gate1_approval_ref",
    "freeze_manifest_ref",
    "oos_authorization_ref",
    "oos_attempt_refs",
    "oos_result_ref",
    "gate2_approval_ref",
    "release_knowledge_ref",
    "budget_limits",
    "budget_remaining",
    "budget_reservations",
    "candidates",
    "tasks",
    "failure_knowledge_ids",
    "brief_ref",
    "run_id",
    "namespace",
)


def _plain(value: Any) -> Any:
    return canonical_value(value)


def _require_equal(label: str, left: Any, right: Any, **details: Any) -> None:
    if _plain(left) != _plain(right):
        raise _fail(f"unauthorized run delta: {label}", **details)


def _normalized_run_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical compare form: drop bookkeeping that always advances per event."""
    out = dict(payload)
    out.pop("version", None)
    out.pop("event_head_seq", None)
    out.pop("event_head_hash", None)
    out.pop("idempotency", None)
    return out


def _require_only_business_changes(
    prior_payload: Mapping[str, Any],
    current_payload: Mapping[str, Any],
    *,
    allowed: frozenset[str],
) -> None:
    prior_n = _normalized_run_payload(prior_payload)
    current_n = _normalized_run_payload(current_payload)
    for key in _RUN_BUSINESS_KEYS:
        if key in allowed:
            continue
        _require_equal(
            key,
            prior_n.get(key),
            current_n.get(key),
            field=key,
        )
    extra_prior = set(prior_n) - set(_RUN_BUSINESS_KEYS)
    extra_current = set(current_n) - set(_RUN_BUSINESS_KEYS)
    if extra_prior or extra_current:
        raise _fail(
            "outputs.run has unexpected fields",
            prior_extra=sorted(extra_prior),
            current_extra=sorted(extra_current),
        )


def _validate_command_result(
    event: Any, outputs: Mapping[str, Any], out_run: Mapping[str, Any]
) -> None:
    """command_result must mirror event semantics; never an independent authority."""
    cr = outputs.get("command_result")
    if not isinstance(cr, Mapping):
        raise _fail("outputs.command_result required")
    expected_ok = event.result_status == "ok"
    if bool(cr.get("ok")) is not expected_ok:
        raise _fail(
            "command_result.ok mismatch vs result_status",
            result_status=event.result_status,
            command_result_ok=cr.get("ok"),
        )
    expected_failure = _plain(event.failure) if event.failure is not None else None
    if _plain(cr.get("failure")) != expected_failure:
        raise _fail("command_result.failure mismatch vs event.failure")
    normal = {
        key: value
        for key, value in outputs.items()
        if key not in {"run", "command_result"}
    }
    if _plain(cr.get("outputs") or {}) != _plain(normal):
        raise _fail("command_result.outputs mismatch vs event ordinary outputs")
    expected_run = {
        **dict(out_run),
        "event_head_hash": None,
        "idempotency": {},
    }
    if _plain(cr.get("run")) != _plain(expected_run):
        raise _fail("command_result.run mismatch vs normalized outputs.run")
    if cr.get("replayed") is not False:
        raise _fail("command_result.replayed must be False")


_KIND_STAGING = "controller_staging"

_AGENT_TASK_VIEW_KEYS = frozenset(
    {
        "task_id",
        "run_id",
        "parent_task_id",
        "role_id",
        "goal",
        "input_refs",
        "input_hashes",
        "visibility",
        "lease",
        "attempt",
        "debate_round",
        "expected_output_type",
        "candidate_ref",
        "expected_schema_version",
        "forbidden_actions",
        "must_check",
        "stop_conditions",
    }
)

_TASK_LEASE_KEYS = frozenset(
    {
        "lease_id",
        "run_id",
        "task_id",
        "role_id",
        "candidates_remaining",
        "experiments_remaining",
        "revisions_remaining",
        "debate_rounds_remaining",
        "expires_at",
    }
)

def _validate_create_run_delta(
    event: Any, out_run: Mapping[str, Any], *, run_id: str, namespace: str
) -> None:
    if event.aggregate_kind != "run" or event.aggregate_id != run_id:
        raise _fail("create_run aggregate_kind/id must target the run")
    if out_run.get("status") != ResearchRunStatus.BRIEFED.value:
        raise _fail("create_run must yield briefed status")
    if out_run.get("stop_reason") is not None:
        raise _fail("create_run stop_reason must be None")
    if out_run.get("gate1_approval_ref") is not None:
        raise _fail("create_run gate1_approval_ref must be None")
    if out_run.get("freeze_manifest_ref") is not None:
        raise _fail("create_run freeze_manifest_ref must be None")
    for field in (
        "oos_authorization_ref",
        "oos_result_ref",
        "gate2_approval_ref",
        "release_knowledge_ref",
    ):
        if out_run.get(field) is not None:
            raise _fail(f"create_run {field} must be None")
    if _plain(out_run.get("oos_attempt_refs") or []) != []:
        raise _fail("create_run oos_attempt_refs must be empty")
    if _plain(out_run.get("candidates") or {}) != {}:
        raise _fail("create_run candidates must be empty")
    if _plain(out_run.get("tasks") or {}) != {}:
        raise _fail("create_run tasks must be empty")
    if _plain(out_run.get("failure_knowledge_ids") or []) != []:
        raise _fail("create_run failure_knowledge_ids must be empty")
    if str(out_run.get("run_id")) != run_id or str(out_run.get("namespace")) != namespace:
        raise _fail("create_run run_id/namespace mismatch")
    brief_ref = out_run.get("brief_ref")
    if not isinstance(brief_ref, Mapping):
        raise _fail("create_run brief_ref required")
    _require_event_refs(event, label="create_run", input_refs=[brief_ref])


def _validate_activate_delta(
    prior: RunAggregate, event: Any, out_run: Mapping[str, Any]
) -> None:
    if event.aggregate_kind != "run" or event.aggregate_id != prior.run_id:
        raise _fail("activate aggregate_kind/id must target the run")
    if prior.status is not ResearchRunStatus.BRIEFED:
        raise _fail("activate requires prior briefed status")
    if out_run.get("status") != ResearchRunStatus.ACTIVE.value:
        raise _fail("activate must set status to active")
    if event.from_status != ResearchRunStatus.BRIEFED.value:
        raise _fail("activate from_status must be briefed")
    if event.to_status != ResearchRunStatus.ACTIVE.value:
        raise _fail("activate to_status must be active")
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"status"}),
    )
    _require_event_refs(event, label="activate", input_refs=[_plain(prior.brief_ref)])


def _validate_request_freeze_delta(
    prior: RunAggregate, event: Any, out_run: Mapping[str, Any]
) -> None:
    if event.aggregate_kind != "run":
        raise _fail("request_freeze aggregate_kind must be run")
    if event.aggregate_id not in prior.candidates:
        raise _fail(
            "request_freeze aggregate_id must be an existing candidate",
            aggregate_id=event.aggregate_id,
        )
    cand = prior.candidates[event.aggregate_id]
    if cand.status is not CandidateStatus.FREEZE_READY:
        raise _fail("request_freeze requires freeze_ready candidate")
    if prior.status is not ResearchRunStatus.ACTIVE:
        raise _fail("request_freeze requires prior active run")
    if out_run.get("status") != ResearchRunStatus.FREEZE_PENDING.value:
        raise _fail("request_freeze must set status to freeze_pending")
    if event.from_status != ResearchRunStatus.ACTIVE.value:
        raise _fail("request_freeze from_status must be active")
    if event.to_status != ResearchRunStatus.FREEZE_PENDING.value:
        raise _fail("request_freeze to_status must be freeze_pending")
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"status"}),
    )
    _require_event_refs(
        event,
        label="request_freeze",
        input_refs=[_plain(prior.brief_ref), _plain(cand.factor_ref)],
    )


def _validate_stop_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any] | None = None,
) -> None:
    if event.aggregate_kind != "run" or event.aggregate_id != prior.run_id:
        raise _fail("stop aggregate_kind/id must target the run")
    if prior.status is not ResearchRunStatus.ACTIVE:
        raise _fail("stop requires prior active run")
    if out_run.get("status") != ResearchRunStatus.REJECTED.value:
        raise _fail("stop must set status to rejected")
    reason = out_run.get("stop_reason")
    if not isinstance(reason, str) or not reason:
        raise _fail("stop must set non-empty stop_reason")
    if prior.stop_reason is not None:
        raise _fail("stop requires prior stop_reason to be None")
    if outputs is not None:
        ordinary = _ordinary_outputs(outputs)
        if ordinary.get("stop_reason") != reason:
            raise _fail("stop ordinary stop_reason must equal run.stop_reason")
    if event.from_status != ResearchRunStatus.ACTIVE.value:
        raise _fail("stop from_status must be active")
    if event.to_status != ResearchRunStatus.REJECTED.value:
        raise _fail("stop to_status must be rejected")
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"status", "stop_reason"}),
    )
    _require_event_refs(event, label="stop", input_refs=[_plain(prior.brief_ref)])


def _validate_reject_run_delta(
    prior: RunAggregate, event: Any, out_run: Mapping[str, Any]
) -> None:
    if event.aggregate_kind != "run" or event.aggregate_id != prior.run_id:
        raise _fail("reject_run aggregate_kind/id must target the run")
    expected = RUN_TRANSITIONS.get((prior.status, "reject_run"))
    if expected is None:
        raise _fail("reject_run illegal from prior status", status=prior.status.value)
    if out_run.get("status") != expected.value:
        raise _fail("reject_run status mismatch vs transition table")
    if event.from_status != prior.status.value:
        raise _fail("reject_run from_status mismatch vs prior")
    if event.to_status != expected.value:
        raise _fail("reject_run to_status mismatch")
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"status"}),
    )
    _require_event_refs(event, label="reject_run", input_refs=[_plain(prior.brief_ref)])


def _validate_record_gate1_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "run":
        raise _fail("record_gate1_approval aggregate_kind must be run")
    if event.aggregate_id != prior.run_id:
        raise _fail("record_gate1_approval aggregate_id must be the run_id")
    if event.from_status != prior.status.value or event.to_status != prior.status.value:
        raise _fail("record_gate1_approval must be a run status self-loop")
    if out_run.get("status") != prior.status.value:
        raise _fail("record_gate1_approval must not change run status")
    if prior.gate1_approval_ref is not None:
        raise _fail("record_gate1_approval requires prior gate1_approval_ref None")
    new_ref = out_run.get("gate1_approval_ref")
    if not isinstance(new_ref, Mapping) or not new_ref:
        raise _fail("record_gate1_approval must set gate1_approval_ref")
    ordinary = _ordinary_outputs(outputs)
    candidate_id = ordinary.get("candidate_id")
    if not isinstance(candidate_id, str) or candidate_id not in prior.candidates:
        raise _fail("record_gate1_approval outputs.candidate_id must target candidate")
    candidate = prior.candidates[candidate_id]
    if _plain(ordinary.get("gate1_approval_ref")) != _plain(new_ref):
        raise _fail("record_gate1_approval output ref mismatch")
    fingerprint = ordinary.get("freeze_intent_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise _fail("record_gate1_approval freeze intent fingerprint required")
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"gate1_approval_ref"}),
    )
    _require_event_refs(
        event,
        label="record_gate1_approval",
        input_refs=[_plain(prior.brief_ref), _plain(candidate.factor_ref)],
        output_refs=[new_ref],
    )


def _validate_authorize_oos_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "run" or prior.status is not ResearchRunStatus.FROZEN:
        raise _fail("authorize_oos requires frozen run aggregate")
    target_id = event.aggregate_id
    candidate = prior.candidates.get(target_id)
    if candidate is None or candidate.status is not CandidateStatus.FROZEN:
        raise _fail("authorize_oos requires frozen target candidate")
    if event.from_status != ResearchRunStatus.FROZEN.value or event.to_status != ResearchRunStatus.FROZEN.value:
        raise _fail("authorize_oos must be a Frozen status self-loop")
    if out_run.get("status") != ResearchRunStatus.FROZEN.value:
        raise _fail("authorize_oos must retain frozen run status")
    if prior.oos_authorization_ref is not None:
        raise _fail("authorize_oos requires no prior authorization")
    ordinary = _ordinary_outputs(outputs)
    if set(ordinary) != {"candidate_id", "authorization_ref"}:
        raise _fail("authorize_oos outputs must use exact audited schema")
    auth_ref = ordinary.get("authorization_ref")
    if not isinstance(auth_ref, Mapping) or _plain(auth_ref) != _plain(out_run.get("oos_authorization_ref")):
        raise _fail("authorize_oos authorization ref mismatch")
    if ordinary.get("candidate_id") != target_id:
        raise _fail("authorize_oos candidate_id mismatch")
    if prior.freeze_manifest_ref is None or prior.gate1_approval_ref is None:
        raise _fail("authorize_oos requires frozen manifest and Gate-1 ref")
    _require_only_business_changes(
        prior.to_payload(), out_run, allowed=frozenset({"oos_authorization_ref"})
    )
    _require_event_refs(
        event,
        label="authorize_oos",
        input_refs=[
            _plain(prior.brief_ref),
            _plain(candidate.factor_ref),
            _plain(prior.freeze_manifest_ref),
            _plain(prior.gate1_approval_ref),
        ],
        output_refs=[auth_ref],
    )


def _validate_complete_oos_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "run" or prior.status is not ResearchRunStatus.FROZEN:
        raise _fail("complete_oos requires frozen run aggregate")
    target_id = event.aggregate_id
    prior_candidate = prior.candidates.get(target_id)
    if prior_candidate is None or prior_candidate.status is not CandidateStatus.FROZEN:
        raise _fail("complete_oos requires frozen target candidate")
    if (
        event.from_status != ResearchRunStatus.FROZEN.value
        or event.to_status != ResearchRunStatus.OOS_TESTED.value
        or out_run.get("status") != ResearchRunStatus.OOS_TESTED.value
    ):
        raise _fail("complete_oos must transition Frozen to OOSTested")
    ordinary = _ordinary_outputs(outputs)
    if set(ordinary) != {
        "candidate_id",
        "authorization_ref",
        "attempt_started_ref",
        "attempt_terminal_ref",
        "oos_result_ref",
        "passed",
    }:
        raise _fail("complete_oos outputs must use exact audited schema")
    if ordinary.get("candidate_id") != target_id:
        raise _fail("complete_oos candidate_id mismatch")
    auth_ref = ordinary.get("authorization_ref")
    start_ref = ordinary.get("attempt_started_ref")
    terminal_ref = ordinary.get("attempt_terminal_ref")
    result_ref = ordinary.get("oos_result_ref")
    if any(not isinstance(ref, Mapping) for ref in (auth_ref, start_ref, terminal_ref)):
        raise _fail("complete_oos auth/start/terminal refs required")
    if _plain(auth_ref) != _plain(prior.oos_authorization_ref):
        raise _fail("complete_oos authorization ref mismatch")
    if _plain(out_run.get("oos_attempt_refs") or []) != _plain([start_ref, terminal_ref]):
        raise _fail("complete_oos attempt ledger refs mismatch")
    if _plain(out_run.get("oos_result_ref")) != _plain(result_ref):
        raise _fail("complete_oos result ref mismatch")
    if not isinstance(ordinary.get("passed"), bool):
        raise _fail("complete_oos passed must be bool")
    if event.result_status == "failed" and (result_ref is not None or ordinary.get("passed") is not False):
        raise _fail("failed complete_oos cannot publish result or pass")
    current = _cand_map(out_run).get(target_id)
    if current is None or current.get("status") != CandidateStatus.OOS_TESTED.value:
        raise _fail("complete_oos must set candidate OOSTested")
    if int(current.get("version", -1)) != prior_candidate.version + 1:
        raise _fail("complete_oos candidate version must advance one")
    _require_candidates_unchanged_except(prior, out_run, target_id)
    if prior.freeze_manifest_ref is None or prior.oos_authorization_ref is None:
        raise _fail("complete_oos requires frozen manifest and authorization")
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"status", "candidates", "oos_attempt_refs", "oos_result_ref"}),
    )
    out_refs = [terminal_ref] + ([result_ref] if result_ref is not None else [])
    _require_event_refs(
        event,
        label="complete_oos",
        input_refs=[
            _plain(prior.brief_ref),
            _plain(prior_candidate.factor_ref),
            _plain(prior.freeze_manifest_ref),
            _plain(prior.oos_authorization_ref),
            start_ref,
        ],
        output_refs=out_refs,
    )


def _validate_record_gate2_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "run" or prior.status is not ResearchRunStatus.OOS_TESTED:
        raise _fail("record_gate2_approval requires OOS-tested run")
    target_id = event.aggregate_id
    candidate = prior.candidates.get(target_id)
    if candidate is None or candidate.status is not CandidateStatus.OOS_TESTED:
        raise _fail("record_gate2_approval requires OOS-tested candidate")
    if event.from_status != prior.status.value or event.to_status != prior.status.value:
        raise _fail("record_gate2_approval must be a status self-loop")
    ordinary = _ordinary_outputs(outputs)
    if set(ordinary) != {"candidate_id", "gate2_approval_ref", "approved"}:
        raise _fail("record_gate2_approval outputs must use exact audited schema")
    gate2_ref = ordinary.get("gate2_approval_ref")
    if (
        prior.gate2_approval_ref is not None
        or not isinstance(gate2_ref, Mapping)
        or _plain(gate2_ref) != _plain(out_run.get("gate2_approval_ref"))
        or ordinary.get("candidate_id") != target_id
        or not isinstance(ordinary.get("approved"), bool)
    ):
        raise _fail("record_gate2_approval binding mismatch")
    _require_only_business_changes(
        prior.to_payload(), out_run, allowed=frozenset({"gate2_approval_ref"})
    )
    expected_inputs = [_plain(prior.brief_ref), _plain(prior.freeze_manifest_ref)]
    if prior.oos_result_ref is not None:
        expected_inputs.append(_plain(prior.oos_result_ref))
    _require_event_refs(
        event,
        label="record_gate2_approval",
        input_refs=expected_inputs,
        output_refs=[gate2_ref],
    )


def _validate_release_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
    *,
    disposition: str,
) -> None:
    if event.aggregate_kind != "run" or prior.status is not ResearchRunStatus.OOS_TESTED:
        raise _fail(f"{disposition} requires OOS-tested run")
    target_id = event.aggregate_id
    prior_candidate = prior.candidates.get(target_id)
    if prior_candidate is None or prior_candidate.status is not CandidateStatus.OOS_TESTED:
        raise _fail(f"{disposition} requires OOS-tested candidate")
    expected_status = (
        ResearchRunStatus.PROMOTED if disposition == "promoted" else ResearchRunStatus.REJECTED
    )
    expected_candidate = (
        CandidateStatus.PROMOTED if disposition == "promoted" else CandidateStatus.REJECTED
    )
    if event.from_status != prior.status.value or event.to_status != expected_status.value:
        raise _fail(f"{disposition} status transition mismatch")
    if out_run.get("status") != expected_status.value:
        raise _fail(f"{disposition} run status mismatch")
    ordinary = _ordinary_outputs(outputs)
    if set(ordinary) != {"release_knowledge_ref"}:
        raise _fail(f"{disposition} outputs must use exact audited schema")
    knowledge_ref = ordinary.get("release_knowledge_ref")
    if not isinstance(knowledge_ref, Mapping) or _plain(knowledge_ref) != _plain(out_run.get("release_knowledge_ref")):
        raise _fail(f"{disposition} release knowledge ref mismatch")
    current = _cand_map(out_run).get(target_id)
    if current is None or current.get("status") != expected_candidate.value:
        raise _fail(f"{disposition} candidate status mismatch")
    if int(current.get("version", -1)) != prior_candidate.version + 1:
        raise _fail(f"{disposition} candidate version must advance one")
    _require_candidates_unchanged_except(prior, out_run, target_id)
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"status", "candidates", "release_knowledge_ref"}),
    )
    if prior.freeze_manifest_ref is None or prior.gate2_approval_ref is None:
        raise _fail(f"{disposition} requires manifest and Gate-2")
    inputs = [
        _plain(prior.brief_ref),
        _plain(prior_candidate.factor_ref),
        _plain(prior.freeze_manifest_ref),
    ]
    if prior.oos_result_ref is not None:
        inputs.append(_plain(prior.oos_result_ref))
    inputs.append(_plain(prior.gate2_approval_ref))
    _require_event_refs(
        event, label=disposition, input_refs=inputs, output_refs=[knowledge_ref]
    )


def _ordinary_outputs(outputs: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in outputs.items()
        if key not in {"run", "command_result"}
    }


def _ref_plain_list(refs: Any) -> list[Any]:
    return [_plain(item) for item in (refs or ())]


def _require_exact_refs(
    label: str, got: Any, expected: Sequence[Any]
) -> None:
    if _plain(_ref_plain_list(got)) != _plain([_plain(item) for item in expected]):
        raise _fail(f"{label} refs mismatch", label=label)


def _require_event_refs(
    event: Any,
    *,
    label: str,
    input_refs: Sequence[Any],
    output_refs: Sequence[Any] = (),
) -> None:
    """Bind an event's complete ref lists to its Controller-derived lineage."""
    _require_exact_refs(f"{label} input_refs", event.input_refs, input_refs)
    _require_exact_refs(f"{label} output_refs", event.output_refs, output_refs)


def _ordinary_expected_keys(
    command: str, ordinary: Mapping[str, Any], event: Any
) -> frozenset[str]:
    """Exact ordinary-output key sets derived from controller commit sites."""
    empty = frozenset()
    if command in {
        "create_run",
        "activate",
        "request_freeze",
        "create_task",
        "start_task",
        "fail_task",
        "cancel_task",
        "timeout_task",
    }:
        return empty
    if command == "claim_task":
        return frozenset({"reservation_id", "lease_id", "amounts"})
    if command == "stop":
        return frozenset({"stop_reason"})
    if command == "propose_candidate":
        return frozenset({"candidate_id"})
    if command == "revise_candidate":
        return frozenset({"candidate_id", "revision", "parent_candidate_id"})
    if command == "submit_review":
        return frozenset({"review_ref", "role_id", "conclusion"})
    if command == "submit_pool_decision":
        return frozenset({"pool_decision_ref"})
    if command == "record_gate1_approval":
        return frozenset(
            {"gate1_approval_ref", "freeze_intent_fingerprint", "candidate_id"}
        )
    if command == "authorize_oos":
        return frozenset({"candidate_id", "authorization_ref"})
    if command == "complete_oos":
        return frozenset(
            {
                "candidate_id",
                "authorization_ref",
                "attempt_started_ref",
                "attempt_terminal_ref",
                "oos_result_ref",
                "passed",
            }
        )
    if command == "record_gate2_approval":
        return frozenset({"candidate_id", "gate2_approval_ref", "approved"})
    if command == "promote":
        return frozenset({"release_knowledge_ref"})
    if command == "reject_run":
        if event.from_status == ResearchRunStatus.OOS_TESTED.value:
            return frozenset({"release_knowledge_ref"})
        return empty
    if command == "freeze":
        return frozenset(
            {
                "manifest_ref",
                "manifest_hash",
                "staging_content_hash",
                "staging_kind",
                "staging_artifact_id",
                "freeze_intent_fingerprint",
                "manifest",
            }
        )
    if command == "reject_candidate":
        if ordinary.get("knowledge_id") is None:
            return frozenset({"knowledge_id"})
        return frozenset(
            {
                "knowledge_id",
                "failure_knowledge_ref",
                "staging_content_hash",
                "staging_kind",
                "staging_artifact_id",
            }
        )
    if command == "run_candidate_pipeline":
        phase = ordinary.get("pipeline_phase")
        if phase == "started" or event.result_status == "started":
            return frozenset(
                {"pipeline_phase", "reservation_id", "amounts", "calls"}
            )
        if ordinary.get("recovery") is True:
            return frozenset({"calls", "recovery", "pipeline_phase"})
        if event.result_status == "ok":
            return frozenset(
                {"calls", "candidate", "evaluation_ref", "pipeline_phase"}
            )
        return frozenset(
            {
                "calls",
                "stage",
                "pipeline_phase",
                "knowledge_id",
                "failure_knowledge_ref",
                "staging_content_hash",
                "staging_kind",
                "staging_artifact_id",
            }
        )
    if command == "submit_task":
        return frozenset({"output_ref"})
    if command == "build_task_view":
        if event.result_status == "denied":
            return empty
        return frozenset({"task_view"})
    raise _fail("ordinary schema unknown command", command=command)


def _validate_ordinary_schema(command: str, ordinary: Mapping[str, Any], event: Any) -> None:
    expected = _ordinary_expected_keys(command, ordinary, event)
    got = frozenset(ordinary)
    if got != expected:
        raise _fail(
            "ordinary outputs schema mismatch",
            command=command,
            expected=sorted(expected),
            got=sorted(got),
            missing=sorted(expected - got),
            unexpected=sorted(got - expected),
        )


def _cand_map(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = payload.get("candidates") or {}
    if not isinstance(raw, Mapping):
        raise _fail("candidates must be a mapping")
    return {str(key): dict(value) for key, value in raw.items()}


def _require_empty_evidence_refs(cand: Mapping[str, Any], *, label: str) -> None:
    for field in (
        "preflight_ref",
        "execution_ref",
        "evaluation_ref",
        "compare_ref",
        "pool_decision_ref",
        "freeze_manifest_ref",
    ):
        if cand.get(field) is not None:
            raise _fail(f"{label} {field} must be empty")
    if _plain(cand.get("review_refs") or []) != []:
        raise _fail(f"{label} review_refs must be empty")


def _require_budget_remaining_delta(
    prior: RunAggregate,
    out_run: Mapping[str, Any],
    *,
    key: str,
    delta: int,
) -> None:
    prior_rem = dict(prior.budget_remaining)
    current_rem = dict(out_run.get("budget_remaining") or {})
    for budget_key in prior_rem:
        expected = int(prior_rem[budget_key]) + (delta if budget_key == key else 0)
        got = int(current_rem.get(budget_key, -1))
        if got != expected:
            raise _fail(
                f"unauthorized budget_remaining.{budget_key} delta",
                expected=expected,
                got=got,
            )
    _require_equal(
        "budget_reservations",
        prior.budget_reservations,
        out_run.get("budget_reservations") or {},
    )
    _require_equal(
        "budget_limits",
        prior.budget_limits,
        out_run.get("budget_limits") or {},
    )


def _require_unrelated_candidates_equal(
    prior_cands: Mapping[str, Any],
    current_cands: Mapping[str, Any],
    *,
    target_id: str,
) -> None:
    for cand_id, prior_body in prior_cands.items():
        if cand_id == target_id:
            continue
        if cand_id not in current_cands:
            raise _fail("unrelated candidate removed", candidate_id=cand_id)
        _require_equal(
            f"unrelated candidate {cand_id}",
            prior_body,
            current_cands[cand_id],
            candidate_id=cand_id,
        )


def _validate_propose_candidate_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "candidate":
        raise _fail("propose_candidate aggregate_kind must be candidate")
    target_id = event.aggregate_id
    if not target_id:
        raise _fail("propose_candidate aggregate_id required")
    if target_id in prior.candidates:
        raise _fail("propose_candidate target already existed", candidate_id=target_id)
    prior_cands = _cand_map(prior.to_payload())
    current_cands = _cand_map(out_run)
    if set(current_cands) != set(prior_cands) | {target_id}:
        raise _fail(
            "propose_candidate must add exactly one candidate key",
            prior=sorted(prior_cands),
            current=sorted(current_cands),
        )
    new_cand = current_cands[target_id]
    if str(new_cand.get("candidate_id")) != target_id:
        raise _fail("propose_candidate candidate_id must equal map key")
    if new_cand.get("status") != CandidateStatus.PROPOSED.value:
        raise _fail("propose_candidate status must be proposed")
    if int(new_cand.get("version", -1)) != 1:
        raise _fail("propose_candidate version must be 1")
    if not isinstance(new_cand.get("factor_ref"), Mapping):
        raise _fail("propose_candidate factor_ref required")
    _require_empty_evidence_refs(new_cand, label="propose_candidate")
    ordinary = _ordinary_outputs(outputs)
    if ordinary.get("candidate_id") not in (None, target_id):
        raise _fail("propose_candidate outputs.candidate_id mismatch")
    if event.from_status != "none" or event.to_status != CandidateStatus.PROPOSED.value:
        raise _fail("propose_candidate must transition none→proposed")
    _require_unrelated_candidates_equal(
        prior_cands, current_cands, target_id=target_id
    )
    _require_budget_remaining_delta(prior, out_run, key="candidates", delta=-1)
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"candidates", "budget_remaining"}),
    )
    _require_event_refs(
        event,
        label="propose_candidate",
        input_refs=[_plain(prior.brief_ref), new_cand.get("factor_ref")],
    )


def _validate_revise_candidate_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "candidate":
        raise _fail("revise_candidate aggregate_kind must be candidate")
    ordinary = _ordinary_outputs(outputs)
    parent_id = ordinary.get("parent_candidate_id")
    if not isinstance(parent_id, str) or not parent_id:
        raise _fail("revise_candidate outputs.parent_candidate_id required")
    if parent_id not in prior.candidates:
        raise _fail("revise_candidate parent missing", parent_candidate_id=parent_id)
    child_id = event.aggregate_id
    if not child_id or child_id == parent_id:
        raise _fail("revise_candidate aggregate_id must be the new child")
    if child_id in prior.candidates:
        raise _fail("revise_candidate child already existed", candidate_id=child_id)
    prior_cands = _cand_map(prior.to_payload())
    current_cands = _cand_map(out_run)
    if set(current_cands) != set(prior_cands) | {child_id}:
        raise _fail("revise_candidate must add exactly one child key")
    _require_equal(
        "revise parent candidate",
        prior_cands[parent_id],
        current_cands[parent_id],
        candidate_id=parent_id,
    )
    parent = prior.candidates[parent_id]
    child = current_cands[child_id]
    if str(child.get("candidate_id")) != child_id:
        raise _fail("revise_candidate child candidate_id mismatch")
    if child.get("status") != CandidateStatus.PROPOSED.value:
        raise _fail("revise_candidate child status must be proposed")
    if int(child.get("version", -1)) != 1:
        raise _fail("revise_candidate child version must be 1")
    if int(child.get("revision", -1)) != parent.revision + 1:
        raise _fail("revise_candidate child revision must be parent.revision+1")
    if ordinary.get("revision") != parent.revision + 1:
        raise _fail("revise_candidate outputs.revision mismatch")
    if ordinary.get("candidate_id") != child_id:
        raise _fail("revise_candidate outputs.candidate_id mismatch")
    if _plain(child.get("parent_ref")) != _plain(parent.factor_ref):
        raise _fail("revise_candidate parent_ref must equal parent.factor_ref")
    if not isinstance(child.get("factor_ref"), Mapping):
        raise _fail("revise_candidate child factor_ref required")
    _require_empty_evidence_refs(child, label="revise_candidate child")
    if event.to_status != CandidateStatus.PROPOSED.value:
        raise _fail("revise_candidate to_status must be proposed")
    if event.from_status != parent.status.value:
        raise _fail("revise_candidate from_status must describe parent")
    _require_unrelated_candidates_equal(
        prior_cands, current_cands, target_id=child_id
    )
    # Parent already checked equal; unrelated excludes only child_id so parent covered.
    _require_budget_remaining_delta(prior, out_run, key="revisions", delta=-1)
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"candidates", "budget_remaining"}),
    )
    _require_event_refs(
        event,
        label="revise_candidate",
        input_refs=[parent.factor_ref, child.get("factor_ref")],
    )


def _expected_review_status(
    prior_status: CandidateStatus, conclusion: ReviewConclusion
) -> CandidateStatus:
    if conclusion is ReviewConclusion.PASS:
        return prior_status
    if conclusion is ReviewConclusion.FAIL:
        return CANDIDATE_TRANSITIONS[(prior_status, "reject")]
    if conclusion is ReviewConclusion.DEBATE:
        return CANDIDATE_TRANSITIONS[(prior_status, "mark_debating")]
    if conclusion is ReviewConclusion.REVISE:
        return CANDIDATE_TRANSITIONS[(prior_status, "mark_synthesizing")]
    raise _fail("unsupported review conclusion", conclusion=str(conclusion))


def _validate_submit_review_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "candidate":
        raise _fail("submit_review aggregate_kind must be candidate")
    target_id = event.aggregate_id
    if target_id not in prior.candidates:
        raise _fail("submit_review target missing", candidate_id=target_id)
    ordinary = _ordinary_outputs(outputs)
    review_ref = ordinary.get("review_ref")
    if not isinstance(review_ref, Mapping):
        raise _fail("submit_review outputs.review_ref required")
    raw_conclusion = ordinary.get("conclusion")
    try:
        conclusion = ReviewConclusion(str(raw_conclusion))
    except ValueError as exc:
        raise _fail("submit_review outputs.conclusion invalid") from exc
    prior_cands = _cand_map(prior.to_payload())
    current_cands = _cand_map(out_run)
    if set(current_cands) != set(prior_cands):
        raise _fail("submit_review must not add/remove candidates")
    _require_unrelated_candidates_equal(prior_cands, current_cands, target_id=target_id)
    prior_cand = prior_cands[target_id]
    current_cand = current_cands[target_id]
    prior_reviews = list(prior_cand.get("review_refs") or [])
    current_reviews = list(current_cand.get("review_refs") or [])
    if _plain(current_reviews) != _plain([*prior_reviews, review_ref]):
        raise _fail("submit_review must append exactly outputs.review_ref")
    if int(current_cand.get("version", -1)) != int(prior_cand.get("version", 0)) + 1:
        raise _fail("submit_review version must advance by exactly 1")
    expected_status = _expected_review_status(
        CandidateStatus(prior_cand["status"]), conclusion
    )
    if current_cand.get("status") != expected_status.value:
        raise _fail(
            "submit_review status mismatch vs conclusion",
            expected=expected_status.value,
            got=current_cand.get("status"),
        )
    if event.from_status != prior_cand["status"]:
        raise _fail("submit_review from_status mismatch")
    if event.to_status != expected_status.value:
        raise _fail("submit_review to_status mismatch")
    for field in (
        "candidate_id",
        "factor_ref",
        "parent_ref",
        "revision",
        "preflight_ref",
        "execution_ref",
        "evaluation_ref",
        "compare_ref",
        "pool_decision_ref",
        "freeze_manifest_ref",
    ):
        _require_equal(
            f"submit_review.{field}",
            prior_cand.get(field),
            current_cand.get(field),
            field=field,
        )
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"candidates"}),
    )
    _require_event_refs(
        event,
        label="submit_review",
        input_refs=[prior_cand.get("evaluation_ref"), review_ref],
        output_refs=[review_ref],
    )


def _validate_submit_pool_decision_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "candidate":
        raise _fail("submit_pool_decision aggregate_kind must be candidate")
    target_id = event.aggregate_id
    if target_id not in prior.candidates:
        raise _fail("submit_pool_decision target missing", candidate_id=target_id)
    ordinary = _ordinary_outputs(outputs)
    decision_ref = ordinary.get("pool_decision_ref")
    if not isinstance(decision_ref, Mapping):
        raise _fail("submit_pool_decision outputs.pool_decision_ref required")
    prior_cands = _cand_map(prior.to_payload())
    current_cands = _cand_map(out_run)
    if set(current_cands) != set(prior_cands):
        raise _fail("submit_pool_decision must not add/remove candidates")
    _require_unrelated_candidates_equal(prior_cands, current_cands, target_id=target_id)
    prior_cand = prior_cands[target_id]
    current_cand = current_cands[target_id]
    if prior_cand.get("pool_decision_ref") is not None:
        raise _fail("submit_pool_decision requires prior pool_decision_ref None")
    if _plain(current_cand.get("pool_decision_ref")) != _plain(decision_ref):
        raise _fail("submit_pool_decision pool_decision_ref mismatch vs outputs")
    if int(current_cand.get("version", -1)) != int(prior_cand.get("version", 0)) + 1:
        raise _fail("submit_pool_decision version must advance by exactly 1")
    prior_status = CandidateStatus(prior_cand["status"])
    to_status = current_cand.get("status")
    if to_status == CandidateStatus.FREEZE_READY.value:
        expected = CANDIDATE_TRANSITIONS.get((prior_status, "mark_freeze_ready"))
    elif to_status == CandidateStatus.REJECTED.value:
        expected = CANDIDATE_TRANSITIONS.get((prior_status, "reject"))
    else:
        raise _fail("submit_pool_decision status must be freeze_ready or rejected")
    if expected is None or expected.value != to_status:
        raise _fail("submit_pool_decision illegal status path")
    if event.from_status != prior_cand["status"] or event.to_status != to_status:
        raise _fail("submit_pool_decision declared transition mismatch")
    for field in (
        "candidate_id",
        "factor_ref",
        "parent_ref",
        "revision",
        "preflight_ref",
        "execution_ref",
        "evaluation_ref",
        "compare_ref",
        "review_refs",
        "freeze_manifest_ref",
    ):
        _require_equal(
            f"submit_pool_decision.{field}",
            prior_cand.get(field),
            current_cand.get(field),
            field=field,
        )
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"candidates"}),
    )
    expected_inputs = [
        prior_cand.get("evaluation_ref"),
        prior_cand.get("compare_ref"),
        *(prior_cand.get("review_refs") or ()),
        decision_ref,
    ]
    _require_event_refs(
        event,
        label="submit_pool_decision",
        input_refs=expected_inputs,
        output_refs=[decision_ref],
    )


def _validate_reject_candidate_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "candidate":
        raise _fail("reject_candidate aggregate_kind must be candidate")
    target_id = event.aggregate_id
    if target_id not in prior.candidates:
        raise _fail("reject_candidate target missing", candidate_id=target_id)
    ordinary = _ordinary_outputs(outputs)
    prior_cands = _cand_map(prior.to_payload())
    current_cands = _cand_map(out_run)
    if set(current_cands) != set(prior_cands):
        raise _fail("reject_candidate must not add/remove candidates")
    _require_unrelated_candidates_equal(prior_cands, current_cands, target_id=target_id)
    prior_cand = prior_cands[target_id]
    current_cand = current_cands[target_id]
    prior_status = CandidateStatus(prior_cand["status"])
    expected = CANDIDATE_TRANSITIONS.get((prior_status, "reject"))
    if expected is None:
        raise _fail("reject_candidate illegal from status", status=prior_status.value)
    if current_cand.get("status") != expected.value:
        raise _fail("reject_candidate status must be rejected")
    if int(current_cand.get("version", -1)) != int(prior_cand.get("version", 0)) + 1:
        raise _fail("reject_candidate version must advance by exactly 1")
    if event.from_status != prior_cand["status"] or event.to_status != expected.value:
        raise _fail("reject_candidate declared transition mismatch")
    for field in (
        "candidate_id",
        "factor_ref",
        "parent_ref",
        "revision",
        "preflight_ref",
        "execution_ref",
        "evaluation_ref",
        "compare_ref",
        "review_refs",
        "pool_decision_ref",
        "freeze_manifest_ref",
    ):
        _require_equal(
            f"reject_candidate.{field}",
            prior_cand.get(field),
            current_cand.get(field),
            field=field,
        )
    knowledge_id = ordinary.get("knowledge_id")
    prior_fk = list(prior.failure_knowledge_ids)
    current_fk = list(out_run.get("failure_knowledge_ids") or [])
    if knowledge_id is None:
        if _plain(current_fk) != _plain(prior_fk):
            raise _fail("reject_candidate failure_knowledge_ids must stay equal")
        allowed = frozenset({"candidates"})
    else:
        if not isinstance(knowledge_id, str) or not knowledge_id:
            raise _fail("reject_candidate knowledge_id must be a non-empty str")
        if _plain(current_fk) != _plain(prior_fk + [knowledge_id]):
            raise _fail("reject_candidate must append exactly outputs.knowledge_id")
        allowed = frozenset({"candidates", "failure_knowledge_ids"})
    _require_only_business_changes(prior.to_payload(), out_run, allowed=allowed)
    if knowledge_id is None:
        _require_event_refs(
            event,
            label="reject_candidate",
            input_refs=[_plain(prior.brief_ref), prior_cand.get("factor_ref")],
        )
    else:
        knowledge_ref = ordinary.get("failure_knowledge_ref")
        if not isinstance(knowledge_ref, Mapping):
            raise _fail("reject_candidate failure_knowledge_ref required")
        if ordinary.get("staging_content_hash") != knowledge_ref.get("content_hash"):
            raise _fail("reject_candidate staging_content_hash must equal fk ref hash")
        if ordinary.get("staging_kind") != _KIND_STAGING:
            raise _fail("reject_candidate staging_kind mismatch")
        if ordinary.get("staging_artifact_id") != f"FailureKnowledgeEntry-{knowledge_id}":
            raise _fail("reject_candidate staging_artifact_id mismatch")
        _require_event_refs(
            event,
            label="reject_candidate",
            input_refs=[
                _plain(prior.brief_ref),
                prior_cand.get("factor_ref"),
                knowledge_ref,
            ],
            output_refs=[knowledge_ref],
        )


def _require_budgets_unchanged(prior: RunAggregate, out_run: Mapping[str, Any]) -> None:
    _require_equal(
        "budget_limits", prior.budget_limits, out_run.get("budget_limits") or {}
    )
    _require_equal(
        "budget_remaining",
        prior.budget_remaining,
        out_run.get("budget_remaining") or {},
    )
    _require_equal(
        "budget_reservations",
        prior.budget_reservations,
        out_run.get("budget_reservations") or {},
    )


def _validate_pipeline_calls_prefix(calls: Any) -> list[str]:
    if not isinstance(calls, (list, tuple)) or not calls:
        raise _fail("pipeline calls must be a non-empty list")
    cleaned = [str(item) for item in calls]
    expected = list(_PIPELINE_CALLS[: len(cleaned)])
    if cleaned != expected:
        raise _fail(
            "pipeline calls must be an exact prefix of stage order",
            expected=expected,
            got=cleaned,
        )
    return cleaned


def _validate_pipeline_started_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "candidate":
        raise _fail("run_candidate_pipeline aggregate_kind must be candidate")
    target_id = event.aggregate_id
    if target_id not in prior.candidates:
        raise _fail("pipeline started target missing", candidate_id=target_id)
    if event.result_status != "started":
        raise _fail("pipeline started result_status must be started")
    if event.failure is None or event.failure.code is not FailureCode.RECOVERY_REQUIRED:
        raise _fail("pipeline started failure must be RECOVERY_REQUIRED")
    ordinary = _ordinary_outputs(outputs)
    if ordinary.get("pipeline_phase") != "started":
        raise _fail("pipeline started outputs.pipeline_phase must be started")
    reservation_id = f"exp:{target_id}:{event.idempotency_key}"
    if ordinary.get("reservation_id") != reservation_id:
        raise _fail("pipeline started reservation_id mismatch")
    if _plain(ordinary.get("amounts")) != _plain({"experiments": 1}):
        raise _fail("pipeline started amounts must exact-match experiment lease")
    if _plain(ordinary.get("calls")) != _plain([]):
        raise _fail("pipeline started calls must be empty")
    prior_cand = prior.candidates[target_id]
    if event.from_status != prior_cand.status.value:
        raise _fail("pipeline started from_status must equal prior candidate status")
    if event.to_status != prior_cand.status.value:
        raise _fail("pipeline started to_status must equal prior candidate status")
    _require_budget_remaining_delta(prior, out_run, key="experiments", delta=-1)
    # All candidates/tasks/run-only fields equal except budget_remaining.
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"budget_remaining"}),
    )
    _require_event_refs(
        event,
        label="pipeline started",
        input_refs=[_plain(prior.brief_ref), _plain(prior_cand.factor_ref)],
    )


def _validate_pipeline_success_terminal(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
    *,
    target_id: str,
    prior_cand: Mapping[str, Any],
    current_cand: Mapping[str, Any],
) -> None:
    ordinary = _ordinary_outputs(outputs)
    calls = _validate_pipeline_calls_prefix(ordinary.get("calls"))
    if calls != list(_PIPELINE_CALLS):
        raise _fail("pipeline success calls must be the full stage list")
    if prior_cand.get("status") != CandidateStatus.PROPOSED.value:
        raise _fail("pipeline success requires prior Proposed candidate")
    if current_cand.get("status") != CandidateStatus.REVIEW_PENDING.value:
        raise _fail("pipeline success status must be review_pending")
    if int(current_cand.get("version", -1)) != int(prior_cand.get("version", 0)) + 4:
        raise _fail("pipeline success version must be prior+4")
    for field in _PIPELINE_REF_FIELDS:
        if current_cand.get(field) is None:
            raise _fail(f"pipeline success {field} must be non-null")
        if prior_cand.get(field) is not None:
            raise _fail(f"pipeline success prior {field} must have been null")
    for field in (
        "candidate_id",
        "factor_ref",
        "parent_ref",
        "revision",
        "review_refs",
        "pool_decision_ref",
        "freeze_manifest_ref",
    ):
        _require_equal(
            f"pipeline success.{field}",
            prior_cand.get(field),
            current_cand.get(field),
            field=field,
        )
    if _plain(ordinary.get("candidate")) != _plain(current_cand):
        raise _fail("pipeline success outputs.candidate must equal target payload")
    eval_ref = ordinary.get("evaluation_ref")
    if _plain(eval_ref) != _plain(current_cand.get("evaluation_ref")):
        raise _fail(
            "pipeline success evaluation_ref must equal candidate.evaluation_ref"
        )
    stage_refs = [
        current_cand[field]
        for field in _PIPELINE_REF_FIELDS
        if current_cand.get(field) is not None
    ]
    _require_exact_refs(
        "pipeline success output_refs", event.output_refs, stage_refs
    )
    _require_exact_refs(
        "pipeline success input_refs",
        event.input_refs,
        [_plain(prior.brief_ref), prior_cand.get("factor_ref")],
    )
    if event.from_status != CandidateStatus.PROPOSED.value:
        raise _fail("pipeline success from_status must be proposed")
    if event.to_status != CandidateStatus.REVIEW_PENDING.value:
        raise _fail("pipeline success to_status must be review_pending")
    if event.result_status != "ok":
        raise _fail("pipeline success result_status must be ok")
    _require_equal(
        "pipeline success failure_knowledge_ids",
        list(prior.failure_knowledge_ids),
        list(out_run.get("failure_knowledge_ids") or []),
    )


def _validate_pipeline_reject_terminal(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
    *,
    target_id: str,
    prior_cand: Mapping[str, Any],
    current_cand: Mapping[str, Any],
) -> None:
    ordinary = _ordinary_outputs(outputs)
    calls = _validate_pipeline_calls_prefix(ordinary.get("calls"))
    stage = ordinary.get("stage")
    if stage != calls[-1]:
        raise _fail("pipeline reject stage must equal final call")
    completed = len(calls) - 1
    expected_from = _PIPELINE_STATUS_AFTER_STAGES[completed].value
    if event.from_status != expected_from:
        raise _fail(
            "pipeline reject from_status mismatch vs completed stages",
            expected=expected_from,
            got=event.from_status,
        )
    if (
        event.to_status != CandidateStatus.REJECTED.value
        or current_cand.get("status") != CandidateStatus.REJECTED.value
    ):
        raise _fail("pipeline reject status must be rejected")
    if int(current_cand.get("version", -1)) != int(prior_cand.get("version", 0)) + len(
        calls
    ):
        raise _fail("pipeline reject version must be prior+len(calls)")
    for index, field in enumerate(_PIPELINE_REF_FIELDS):
        prior_ref = prior_cand.get(field)
        current_ref = current_cand.get(field)
        if prior_ref is not None:
            raise _fail(f"pipeline reject prior {field} must have been null")
        if index < completed:
            if current_ref is None:
                raise _fail(f"pipeline reject {field} must be set for completed stage")
        elif current_ref is not None:
            raise _fail(f"pipeline reject {field} must stay None")
    for field in (
        "candidate_id",
        "factor_ref",
        "parent_ref",
        "revision",
        "review_refs",
        "pool_decision_ref",
        "freeze_manifest_ref",
    ):
        _require_equal(
            f"pipeline reject.{field}",
            prior_cand.get(field),
            current_cand.get(field),
            field=field,
        )
    knowledge_id = ordinary.get("knowledge_id")
    if not isinstance(knowledge_id, str) or not knowledge_id:
        raise _fail("pipeline reject outputs.knowledge_id required")
    prior_fk = list(prior.failure_knowledge_ids)
    current_fk = list(out_run.get("failure_knowledge_ids") or [])
    if _plain(current_fk) != _plain(prior_fk + [knowledge_id]):
        raise _fail("pipeline reject must append exactly outputs.knowledge_id")
    fk_ref = ordinary.get("failure_knowledge_ref")
    if not isinstance(fk_ref, Mapping):
        raise _fail("pipeline reject failure_knowledge_ref required")
    if ordinary.get("staging_content_hash") != fk_ref.get("content_hash"):
        raise _fail("pipeline reject staging_content_hash must equal fk ref hash")
    if ordinary.get("staging_kind") != _KIND_STAGING:
        raise _fail("pipeline reject staging_kind mismatch")
    if ordinary.get("staging_artifact_id") != f"FailureKnowledgeEntry-{knowledge_id}":
        raise _fail("pipeline reject staging_artifact_id mismatch")
    _require_exact_refs("pipeline reject output_refs", event.output_refs, [fk_ref])
    factor_ref = current_cand.get("factor_ref")
    if not isinstance(factor_ref, Mapping):
        raise _fail("pipeline reject candidate factor_ref required")
    _require_exact_refs(
        "pipeline reject input_refs",
        event.input_refs,
        [_plain(prior.brief_ref), factor_ref, fk_ref],
    )
    if event.result_status != "failed":
        raise _fail("pipeline reject result_status must be failed")


def _validate_pipeline_recovery_terminal(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
    *,
    target_id: str,
    prior_cand: Mapping[str, Any],
    current_cand: Mapping[str, Any],
) -> None:
    ordinary = _ordinary_outputs(outputs)
    if ordinary.get("recovery") is not True:
        raise _fail("pipeline recovery outputs.recovery must be true")
    calls = ordinary.get("calls")
    if calls is None:
        raise _fail("pipeline recovery calls required")
    if isinstance(calls, (list, tuple)) and calls:
        _validate_pipeline_calls_prefix(calls)
    elif not isinstance(calls, (list, tuple)):
        raise _fail("pipeline recovery calls must be a list")
    _require_equal("pipeline recovery target", prior_cand, current_cand)
    if event.from_status != prior_cand["status"] or event.to_status != prior_cand["status"]:
        raise _fail("pipeline recovery must be a candidate status self-loop")
    if event.result_status != "failed":
        raise _fail("pipeline recovery result_status must be failed")
    if event.failure is None or event.failure.code is not FailureCode.RECOVERY_REQUIRED:
        raise _fail("pipeline recovery failure must be RECOVERY_REQUIRED")
    _require_event_refs(
        event,
        label="pipeline recovery",
        input_refs=[_plain(prior.brief_ref), prior_cand.get("factor_ref")],
    )
    _require_equal(
        "pipeline recovery failure_knowledge_ids",
        list(prior.failure_knowledge_ids),
        list(out_run.get("failure_knowledge_ids") or []),
    )


def _validate_pipeline_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "candidate":
        raise _fail("run_candidate_pipeline aggregate_kind must be candidate")
    target_id = event.aggregate_id
    if target_id not in prior.candidates:
        raise _fail("pipeline target missing", candidate_id=target_id)
    ordinary = _ordinary_outputs(outputs)
    phase = ordinary.get("pipeline_phase")
    if phase == "started" or event.result_status == "started":
        _validate_pipeline_started_delta(prior, event, out_run, outputs)
        return
    if phase != "terminal":
        raise _fail("pipeline terminal outputs.pipeline_phase must be terminal")
    _require_budgets_unchanged(prior, out_run)
    prior_cands = _cand_map(prior.to_payload())
    current_cands = _cand_map(out_run)
    if set(current_cands) != set(prior_cands):
        raise _fail("pipeline terminal must not add/remove candidates")
    _require_unrelated_candidates_equal(prior_cands, current_cands, target_id=target_id)
    prior_cand = prior_cands[target_id]
    current_cand = current_cands[target_id]
    if ordinary.get("recovery") is True:
        _validate_pipeline_recovery_terminal(
            prior,
            event,
            out_run,
            outputs,
            target_id=target_id,
            prior_cand=prior_cand,
            current_cand=current_cand,
        )
        allowed = frozenset()
    elif (
        current_cand.get("status") == CandidateStatus.REVIEW_PENDING.value
        and event.result_status == "ok"
    ):
        _validate_pipeline_success_terminal(
            prior,
            event,
            out_run,
            outputs,
            target_id=target_id,
            prior_cand=prior_cand,
            current_cand=current_cand,
        )
        allowed = frozenset({"candidates"})
    elif current_cand.get("status") == CandidateStatus.REJECTED.value:
        _validate_pipeline_reject_terminal(
            prior,
            event,
            out_run,
            outputs,
            target_id=target_id,
            prior_cand=prior_cand,
            current_cand=current_cand,
        )
        allowed = frozenset({"candidates", "failure_knowledge_ids"})
    else:
        raise _fail("pipeline terminal unrecognized outcome")
    _require_only_business_changes(prior.to_payload(), out_run, allowed=allowed)


def _validate_freeze_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "run":
        raise _fail("freeze aggregate_kind must be run")
    target_id = event.aggregate_id
    if target_id not in prior.candidates:
        raise _fail("freeze aggregate_id must be an existing candidate")
    if prior.status is not ResearchRunStatus.FREEZE_PENDING:
        raise _fail("freeze requires prior freeze_pending run")
    prior_target = prior.candidates[target_id]
    if prior_target.status is not CandidateStatus.FREEZE_READY:
        raise _fail("freeze requires freeze_ready target candidate")
    ordinary = _ordinary_outputs(outputs)
    manifest_ref = ordinary.get("manifest_ref")
    if not isinstance(manifest_ref, Mapping):
        raise _fail("freeze outputs.manifest_ref required")
    manifest = ordinary.get("manifest")
    if not isinstance(manifest, Mapping):
        raise _fail("freeze outputs.manifest required")
    manifest_hash = ordinary.get("manifest_hash")
    if not isinstance(manifest_hash, str) or not manifest_hash:
        raise _fail("freeze outputs.manifest_hash required")
    if manifest_hash != manifest.get("content_hash"):
        raise _fail("freeze manifest_hash must equal manifest.content_hash")
    if ordinary.get("staging_content_hash") != manifest_ref.get("content_hash"):
        raise _fail("freeze staging_content_hash must equal manifest_ref.content_hash")
    if ordinary.get("staging_kind") != _KIND_STAGING:
        raise _fail("freeze staging_kind mismatch")
    manifest_id = manifest.get("manifest_id")
    if not isinstance(manifest_id, str) or not manifest_id:
        raise _fail("freeze manifest.manifest_id required")
    if ordinary.get("staging_artifact_id") != f"FreezeManifest-{manifest_id}":
        raise _fail("freeze staging_artifact_id mismatch")
    fingerprint = ordinary.get("freeze_intent_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise _fail("freeze outputs.freeze_intent_fingerprint required")
    if out_run.get("status") != ResearchRunStatus.FROZEN.value:
        raise _fail("freeze must set run status to frozen")
    if event.from_status != ResearchRunStatus.FREEZE_PENDING.value:
        raise _fail("freeze from_status must be freeze_pending")
    if event.to_status != ResearchRunStatus.FROZEN.value:
        raise _fail("freeze to_status must be frozen")
    if _plain(out_run.get("freeze_manifest_ref")) != _plain(manifest_ref):
        raise _fail("run.freeze_manifest_ref must equal outputs.manifest_ref")
    if prior.freeze_manifest_ref is not None:
        raise _fail("freeze requires prior run.freeze_manifest_ref None")
    prior_cands = _cand_map(prior.to_payload())
    current_cands = _cand_map(out_run)
    if set(current_cands) != set(prior_cands):
        raise _fail("freeze must not add/remove candidates")
    _require_unrelated_candidates_equal(prior_cands, current_cands, target_id=target_id)
    current_target = current_cands[target_id]
    prior_target_payload = prior_cands[target_id]
    if current_target.get("status") != CandidateStatus.FROZEN.value:
        raise _fail("freeze target status must be frozen")
    if int(current_target.get("version", -1)) != int(prior_target_payload.get("version", 0)) + 1:
        raise _fail("freeze target version must advance by exactly 1")
    if _plain(current_target.get("freeze_manifest_ref")) != _plain(manifest_ref):
        raise _fail("target.freeze_manifest_ref must equal outputs.manifest_ref")
    for field in (
        "candidate_id",
        "factor_ref",
        "parent_ref",
        "revision",
        "preflight_ref",
        "execution_ref",
        "evaluation_ref",
        "compare_ref",
        "review_refs",
        "pool_decision_ref",
    ):
        _require_equal(
            f"freeze target.{field}",
            prior_target_payload.get(field),
            current_target.get(field),
            field=field,
        )
    _require_exact_refs("freeze output_refs", event.output_refs, [manifest_ref])
    approval = prior.gate1_approval_ref
    if approval is None:
        raise _fail("freeze requires prior gate1_approval_ref")
    closed_inputs: list[Any] = [
        _plain(prior.brief_ref),
        prior_target_payload.get("factor_ref"),
        _plain(approval),
    ]
    for field in (
        "preflight_ref",
        "execution_ref",
        "evaluation_ref",
        "compare_ref",
        "pool_decision_ref",
    ):
        ref = prior_target_payload.get(field)
        if ref is not None:
            closed_inputs.append(ref)
    for ref in prior_target_payload.get("review_refs") or ():
        closed_inputs.append(ref)
    for item in manifest.get("pool_baseline_refs") or ():
        closed_inputs.append(item)
    _require_exact_refs("freeze input_refs", event.input_refs, closed_inputs)
    _require_budgets_unchanged(prior, out_run)
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"status", "freeze_manifest_ref", "candidates"}),
    )


_TASK_IDENTITY_FIELDS = (
    "task_id",
    "run_id",
    "role_id",
    "parent_task_id",
    "candidate_id",
    "attempt",
    "debate_round",
    "visibility",
    "input_refs",
    "expected_output_type",
)


def _task_map(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = payload.get("tasks") or {}
    if not isinstance(raw, Mapping):
        raise _fail("tasks must be a mapping")
    return {str(key): dict(value) for key, value in raw.items()}


def _require_unrelated_tasks_equal(
    prior_tasks: Mapping[str, Any],
    current_tasks: Mapping[str, Any],
    *,
    target_id: str,
) -> None:
    for task_id, prior_body in prior_tasks.items():
        if task_id == target_id:
            continue
        if task_id not in current_tasks:
            raise _fail("unrelated task removed", task_id=task_id)
        _require_equal(
            f"unrelated task {task_id}",
            prior_body,
            current_tasks[task_id],
            task_id=task_id,
        )


def _require_task_identity_equal(
    prior_task: Mapping[str, Any], current_task: Mapping[str, Any], *, label: str
) -> None:
    for field in _TASK_IDENTITY_FIELDS:
        _require_equal(
            f"{label}.{field}",
            prior_task.get(field),
            current_task.get(field),
            field=field,
        )


def _require_candidates_unchanged(prior: RunAggregate, out_run: Mapping[str, Any]) -> None:
    _require_equal(
        "candidates",
        _cand_map(prior.to_payload()),
        _cand_map(out_run),
    )


def _require_candidates_unchanged_except(
    prior: RunAggregate, out_run: Mapping[str, Any], target_id: str
) -> None:
    before = _cand_map(prior.to_payload())
    after = _cand_map(out_run)
    if set(before) != set(after) or target_id not in before:
        raise _fail("candidate set changed during sealed OOS/release")
    _require_unrelated_candidates_equal(before, after, target_id=target_id)


def _reservation_amounts(reservations: Mapping[str, Any], reservation_id: str) -> dict[str, int]:
    raw = reservations.get(reservation_id) or {}
    if not isinstance(raw, Mapping):
        raise _fail("reservation amounts must be a mapping", reservation_id=reservation_id)
    return {str(key): int(value) for key, value in raw.items() if int(value)}


def _require_settle_reservation(
    prior: RunAggregate, out_run: Mapping[str, Any], *, reservation_id: str
) -> None:
    prior_res = {
        key: dict(value) for key, value in prior.budget_reservations.items()
    }
    if reservation_id not in prior_res:
        raise _fail("settle requires prior reservation", reservation_id=reservation_id)
    expected = dict(prior_res)
    expected.pop(reservation_id)
    _require_equal("budget_remaining", prior.budget_remaining, out_run.get("budget_remaining"))
    _require_equal("budget_reservations", expected, out_run.get("budget_reservations") or {})
    _require_equal("budget_limits", prior.budget_limits, out_run.get("budget_limits") or {})


def _require_release_reservation(
    prior: RunAggregate, out_run: Mapping[str, Any], *, reservation_id: str
) -> None:
    prior_res = {
        key: dict(value) for key, value in prior.budget_reservations.items()
    }
    if reservation_id not in prior_res:
        raise _fail("release requires prior reservation", reservation_id=reservation_id)
    amounts = _reservation_amounts(prior_res, reservation_id)
    expected_remaining = dict(prior.budget_remaining)
    for key, value in amounts.items():
        expected_remaining[key] = int(expected_remaining.get(key, 0)) + value
    expected_res = dict(prior_res)
    expected_res.pop(reservation_id)
    _require_equal("budget_remaining", expected_remaining, out_run.get("budget_remaining"))
    _require_equal("budget_reservations", expected_res, out_run.get("budget_reservations") or {})
    _require_equal("budget_limits", prior.budget_limits, out_run.get("budget_limits") or {})


def _validate_create_task_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "task":
        raise _fail("create_task aggregate_kind must be task")
    target_id = event.aggregate_id
    if not target_id:
        raise _fail("create_task aggregate_id required")
    if target_id in prior.tasks:
        raise _fail("create_task target already existed", task_id=target_id)
    prior_tasks = _task_map(prior.to_payload())
    current_tasks = _task_map(out_run)
    if set(current_tasks) != set(prior_tasks) | {target_id}:
        raise _fail("create_task must add exactly one task key")
    _require_unrelated_tasks_equal(prior_tasks, current_tasks, target_id=target_id)
    task = current_tasks[target_id]
    if str(task.get("task_id")) != target_id:
        raise _fail("create_task task_id must equal map key")
    if str(task.get("run_id")) != prior.run_id:
        raise _fail("create_task run_id must equal run")
    if str(task.get("role_id")) != event.role_id:
        raise _fail("create_task role_id must equal event.role_id")
    if task.get("parent_task_id") != event.parent_task_id:
        raise _fail("create_task parent_task_id must equal event.parent_task_id")
    if task.get("status") != TaskLifecycleStatus.PENDING.value:
        raise _fail("create_task status must be pending")
    if int(task.get("version", -1)) != 1:
        raise _fail("create_task version must be 1")
    if task.get("lease_id") is not None or task.get("reservation_id") is not None:
        raise _fail("create_task lease/reservation must be None")
    if task.get("output_ref") is not None:
        raise _fail("create_task output_ref must be None")
    visibility = tuple(task.get("visibility") or ())
    if VIS_SEALED in {str(item) for item in visibility}:
        raise _fail(
            "create_task sealed visibility forbidden",
            visibility=list(visibility),
        )
    if (
        len(set(visibility)) != len(visibility)
        or any(item not in DEFAULT_RESEARCH_VISIBILITY for item in visibility)
    ):
        raise _fail("create_task visibility must be a unique research subset")
    attempt = int(task.get("attempt", 0))
    if attempt != 1:
        raise _fail("create_task attempt must be 1")
    debate_round = int(task.get("debate_round", -1))
    if debate_round != 0:
        raise _fail("create_task debate_round must be 0")
    candidate_id = task.get("candidate_id")
    if candidate_id is not None and candidate_id not in prior.candidates:
        raise _fail("create_task candidate_id must name existing candidate")
    parent_task_id = task.get("parent_task_id")
    if parent_task_id is not None and parent_task_id not in prior.tasks:
        raise _fail("create_task parent_task_id must name existing task")
    raw_task_input_refs = task.get("input_refs") or ()
    if not isinstance(raw_task_input_refs, (list, tuple)):
        raise _fail("create_task input_refs must be a sequence")
    task_input_refs = list(raw_task_input_refs)
    authorized_inputs: list[Any] = [_plain(prior.brief_ref)]
    for candidate in prior.candidates.values():
        authorized_inputs.append(_plain(candidate.factor_ref))
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
                authorized_inputs.append(_plain(ref))
        authorized_inputs.extend(_plain(ref) for ref in candidate.review_refs)
    if any(_plain(ref) not in authorized_inputs for ref in task_input_refs):
        raise _fail(
            "create_task input_refs must be controller-authorized run lineage"
        )
    expected_output_type = task.get("expected_output_type")
    if not isinstance(expected_output_type, str) or not expected_output_type:
        raise _fail("create_task expected_output_type required")
    if event.from_status != "none" or event.to_status != TaskLifecycleStatus.PENDING.value:
        raise _fail("create_task must transition none→pending")
    expected_inputs = [_plain(prior.brief_ref), *task_input_refs]
    if candidate_id is not None:
        expected_inputs.append(_plain(prior.candidates[str(candidate_id)].factor_ref))
    _require_event_refs(
        event,
        label="create_task",
        input_refs=expected_inputs,
    )
    _require_budgets_unchanged(prior, out_run)
    _require_candidates_unchanged(prior, out_run)
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"tasks"}),
    )


def _validate_claim_task_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "task":
        raise _fail("claim_task aggregate_kind must be task")
    target_id = event.aggregate_id
    if target_id not in prior.tasks:
        raise _fail("claim_task target missing", task_id=target_id)
    prior_tasks = _task_map(prior.to_payload())
    current_tasks = _task_map(out_run)
    if set(current_tasks) != set(prior_tasks):
        raise _fail("claim_task must not add/remove tasks")
    _require_unrelated_tasks_equal(prior_tasks, current_tasks, target_id=target_id)
    prior_task = prior_tasks[target_id]
    current_task = current_tasks[target_id]
    if prior_task.get("status") != TaskLifecycleStatus.PENDING.value:
        raise _fail("claim_task requires prior pending task")
    if current_task.get("status") != TaskLifecycleStatus.CLAIMED.value:
        raise _fail("claim_task status must be claimed")
    if int(current_task.get("version", -1)) != int(prior_task.get("version", 0)) + 1:
        raise _fail("claim_task version must advance by exactly 1")
    reservation_id = f"task:{target_id}:{event.idempotency_key}"
    if current_task.get("reservation_id") != reservation_id:
        raise _fail("claim_task reservation_id mismatch")
    if current_task.get("lease_id") != reservation_id:
        raise _fail("claim_task lease_id must equal deterministic reservation_id")
    _require_task_identity_equal(prior_task, current_task, label="claim_task")
    if prior_task.get("output_ref") is not None or current_task.get("output_ref") is not None:
        raise _fail("claim_task output_ref must remain None")
    if event.from_status != prior_task["status"] or event.to_status != current_task["status"]:
        raise _fail("claim_task declared transition mismatch")
    delta = {str(k): int(v) for k, v in dict(event.budget_delta or {}).items()}
    amounts = {k: -v for k, v in delta.items() if v < 0}
    if any(v > 0 for v in delta.values()):
        raise _fail("claim_task budget_delta must only decrease remaining")
    expected_remaining = dict(prior.budget_remaining)
    for key, value in amounts.items():
        expected_remaining[key] = int(expected_remaining.get(key, 0)) - value
    expected_res = {
        key: dict(value) for key, value in prior.budget_reservations.items()
    }
    expected_res[reservation_id] = {k: v for k, v in amounts.items() if v}
    _require_equal("budget_remaining", expected_remaining, out_run.get("budget_remaining"))
    _require_equal("budget_reservations", expected_res, out_run.get("budget_reservations") or {})
    _require_equal("budget_limits", prior.budget_limits, out_run.get("budget_limits") or {})
    _require_candidates_unchanged(prior, out_run)
    _require_only_business_changes(
        prior.to_payload(),
        out_run,
        allowed=frozenset({"tasks", "budget_remaining", "budget_reservations"}),
    )
    ordinary = _ordinary_outputs(event.outputs)
    if ordinary.get("reservation_id") != reservation_id:
        raise _fail("claim_task outputs.reservation_id mismatch")
    if ordinary.get("lease_id") != reservation_id:
        raise _fail("claim_task outputs.lease_id mismatch")
    if _plain(ordinary.get("amounts")) != _plain(expected_res[reservation_id]):
        raise _fail("claim_task outputs.amounts mismatch")
    _require_event_refs(
        event,
        label="claim_task",
        input_refs=[_plain(prior.brief_ref)],
    )


def _validate_start_task_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "task":
        raise _fail("start_task aggregate_kind must be task")
    target_id = event.aggregate_id
    if target_id not in prior.tasks:
        raise _fail("start_task target missing", task_id=target_id)
    prior_tasks = _task_map(prior.to_payload())
    current_tasks = _task_map(out_run)
    if set(current_tasks) != set(prior_tasks):
        raise _fail("start_task must not add/remove tasks")
    _require_unrelated_tasks_equal(prior_tasks, current_tasks, target_id=target_id)
    prior_task = prior_tasks[target_id]
    current_task = current_tasks[target_id]
    expected = TASK_TRANSITIONS.get(
        (TaskLifecycleStatus(prior_task["status"]), "start")
    )
    if expected is None or current_task.get("status") != expected.value:
        raise _fail("start_task status mismatch")
    if int(current_task.get("version", -1)) != int(prior_task.get("version", 0)) + 1:
        raise _fail("start_task version must advance by exactly 1")
    _require_task_identity_equal(prior_task, current_task, label="start_task")
    for field in ("lease_id", "reservation_id", "output_ref"):
        _require_equal(
            f"start_task.{field}",
            prior_task.get(field),
            current_task.get(field),
            field=field,
        )
    if event.from_status != prior_task["status"] or event.to_status != current_task["status"]:
        raise _fail("start_task declared transition mismatch")
    _require_budgets_unchanged(prior, out_run)
    _require_candidates_unchanged(prior, out_run)
    _require_only_business_changes(
        prior.to_payload(), out_run, allowed=frozenset({"tasks"})
    )
    _require_event_refs(
        event,
        label="start_task",
        input_refs=[_plain(prior.brief_ref)],
    )


def _validate_submit_task_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "task":
        raise _fail("submit_task aggregate_kind must be task")
    target_id = event.aggregate_id
    if target_id not in prior.tasks:
        raise _fail("submit_task target missing", task_id=target_id)
    ordinary = _ordinary_outputs(outputs)
    output_ref = ordinary.get("output_ref")
    if not isinstance(output_ref, Mapping):
        raise _fail("submit_task outputs.output_ref required")
    _require_event_refs(
        event,
        label="submit_task",
        input_refs=[_plain(prior.brief_ref)],
        output_refs=[output_ref],
    )
    prior_tasks = _task_map(prior.to_payload())
    current_tasks = _task_map(out_run)
    if set(current_tasks) != set(prior_tasks):
        raise _fail("submit_task must not add/remove tasks")
    _require_unrelated_tasks_equal(prior_tasks, current_tasks, target_id=target_id)
    prior_task = prior_tasks[target_id]
    current_task = current_tasks[target_id]
    if output_ref.get("object_type") != prior_task.get("expected_output_type"):
        raise _fail("submit_task output_ref type mismatch vs task expected_output_type")
    expected = TASK_TRANSITIONS.get(
        (TaskLifecycleStatus(prior_task["status"]), "submit")
    )
    if expected is None or current_task.get("status") != expected.value:
        raise _fail("submit_task status mismatch")
    if int(current_task.get("version", -1)) != int(prior_task.get("version", 0)) + 1:
        raise _fail("submit_task version must advance by exactly 1")
    if _plain(current_task.get("output_ref")) != _plain(output_ref):
        raise _fail("submit_task output_ref mismatch vs outputs")
    if current_task.get("reservation_id") is not None:
        raise _fail("submit_task reservation_id must be cleared")
    _require_task_identity_equal(prior_task, current_task, label="submit_task")
    _require_equal(
        "submit_task.lease_id", prior_task.get("lease_id"), current_task.get("lease_id")
    )
    if event.from_status != prior_task["status"] or event.to_status != current_task["status"]:
        raise _fail("submit_task declared transition mismatch")
    prior_res_id = prior_task.get("reservation_id")
    if prior_res_id:
        _require_settle_reservation(prior, out_run, reservation_id=str(prior_res_id))
        allowed = frozenset({"tasks", "budget_reservations"})
    else:
        _require_budgets_unchanged(prior, out_run)
        allowed = frozenset({"tasks"})
    _require_candidates_unchanged(prior, out_run)
    _require_only_business_changes(prior.to_payload(), out_run, allowed=allowed)


def _validate_end_task_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    *,
    command: str,
    transition_token: str,
) -> None:
    if event.aggregate_kind != "task":
        raise _fail(f"{command} aggregate_kind must be task")
    target_id = event.aggregate_id
    if target_id not in prior.tasks:
        raise _fail(f"{command} target missing", task_id=target_id)
    prior_tasks = _task_map(prior.to_payload())
    current_tasks = _task_map(out_run)
    if set(current_tasks) != set(prior_tasks):
        raise _fail(f"{command} must not add/remove tasks")
    _require_unrelated_tasks_equal(prior_tasks, current_tasks, target_id=target_id)
    prior_task = prior_tasks[target_id]
    current_task = current_tasks[target_id]
    expected = TASK_TRANSITIONS.get(
        (TaskLifecycleStatus(prior_task["status"]), transition_token)
    )
    if expected is None or current_task.get("status") != expected.value:
        raise _fail(f"{command} status mismatch")
    if int(current_task.get("version", -1)) != int(prior_task.get("version", 0)) + 1:
        raise _fail(f"{command} version must advance by exactly 1")
    if current_task.get("reservation_id") is not None:
        raise _fail(f"{command} reservation_id must be cleared")
    _require_task_identity_equal(prior_task, current_task, label=command)
    for field in ("lease_id", "output_ref"):
        _require_equal(
            f"{command}.{field}",
            prior_task.get(field),
            current_task.get(field),
            field=field,
        )
    if event.from_status != prior_task["status"] or event.to_status != current_task["status"]:
        raise _fail(f"{command} declared transition mismatch")
    prior_res_id = prior_task.get("reservation_id")
    prior_status = TaskLifecycleStatus(prior_task["status"])
    if command == "cancel_task" and prior_status is TaskLifecycleStatus.CLAIMED:
        if not prior_res_id:
            raise _fail("cancel_task from claimed requires reservation_id")
        _require_release_reservation(prior, out_run, reservation_id=str(prior_res_id))
        allowed = frozenset({"tasks", "budget_remaining", "budget_reservations"})
    elif prior_res_id:
        _require_settle_reservation(prior, out_run, reservation_id=str(prior_res_id))
        allowed = frozenset({"tasks", "budget_reservations"})
    else:
        _require_budgets_unchanged(prior, out_run)
        allowed = frozenset({"tasks"})
    _require_candidates_unchanged(prior, out_run)
    _require_only_business_changes(prior.to_payload(), out_run, allowed=allowed)
    _require_event_refs(
        event,
        label=command,
        input_refs=[_plain(prior.brief_ref)],
    )


def _validate_build_task_view_delta(
    prior: RunAggregate,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> None:
    if event.aggregate_kind != "task":
        raise _fail("build_task_view aggregate_kind must be task")
    target_id = event.aggregate_id
    if target_id not in prior.tasks:
        raise _fail("build_task_view target missing", task_id=target_id)
    prior_status = prior.tasks[target_id].status.value
    if event.from_status != prior_status or event.to_status != prior_status:
        raise _fail("build_task_view must be a status self-loop")
    # True state self-loop: no business-field changes at all.
    _require_only_business_changes(prior.to_payload(), out_run, allowed=frozenset())
    if event.output_refs:
        raise _fail("build_task_view must not bind output_refs")
    ordinary = _ordinary_outputs(outputs)
    prior_task = _task_map(prior.to_payload())[target_id]
    task_visibility = tuple(prior_task.get("visibility") or ())
    expected_vis = task_visibility or DEFAULT_RESEARCH_VISIBILITY
    if event.result_status == "ok":
        view = ordinary.get("task_view")
        if not isinstance(view, Mapping):
            raise _fail("build_task_view outputs.task_view required")
        got_keys = frozenset(view)
        if got_keys != _AGENT_TASK_VIEW_KEYS:
            raise _fail(
                "build_task_view task_view schema mismatch",
                missing=sorted(_AGENT_TASK_VIEW_KEYS - got_keys),
                unexpected=sorted(got_keys - _AGENT_TASK_VIEW_KEYS),
            )
        if VIS_SEALED in {str(item) for item in expected_vis}:
            raise _fail("build_task_view sealed visibility cannot succeed")
        if is_sealed_marker(view):
            raise _fail("build_task_view task_view must not contain sealed markers")
        if str(view.get("task_id")) != target_id:
            raise _fail("build_task_view.task_view.task_id mismatch")
        if str(view.get("run_id")) != prior.run_id:
            raise _fail("build_task_view.task_view.run_id mismatch")
        if view.get("parent_task_id") != prior_task.get("parent_task_id"):
            raise _fail("build_task_view.task_view.parent_task_id mismatch")
        if str(view.get("role_id")) != str(prior_task.get("role_id")):
            raise _fail("build_task_view.task_view.role_id mismatch")
        if int(view.get("attempt", -1)) != int(prior_task.get("attempt", 0)):
            raise _fail("build_task_view.task_view.attempt mismatch")
        if int(view.get("debate_round", -1)) != int(prior_task.get("debate_round", 0)):
            raise _fail("build_task_view.task_view.debate_round mismatch")
        if view.get("expected_schema_version") != SCHEMA_VERSION:
            raise _fail("build_task_view expected_schema_version mismatch")
        goal = view.get("goal")
        if not isinstance(goal, str) or not goal:
            raise _fail("build_task_view goal required")
        expected_output_type = view.get("expected_output_type")
        if expected_output_type != prior_task.get("expected_output_type"):
            raise _fail("build_task_view expected_output_type mismatch vs task")
        vis = tuple(view.get("visibility") or ())
        if _plain(list(vis)) != _plain(list(expected_vis)):
            raise _fail("build_task_view visibility mismatch vs task")
        if VIS_SEALED in {str(item) for item in vis}:
            raise _fail("build_task_view visibility must not include sealed")
        for field in ("forbidden_actions", "must_check", "stop_conditions"):
            if tuple(view.get(field) or ()) != ():
                raise _fail(f"build_task_view {field} must be empty")
        view_input_refs = list(view.get("input_refs") or ())
        task_input_refs = list(prior_task.get("input_refs") or ())
        if _plain(view_input_refs) != _plain(task_input_refs):
            raise _fail("build_task_view input_refs mismatch vs task authorization")
        candidate_ref = view.get("candidate_ref")
        expected_event_inputs: list[Any] = [_plain(prior.brief_ref), *task_input_refs]
        task_candidate_id = prior_task.get("candidate_id")
        if task_candidate_id is None:
            if candidate_ref is not None:
                raise _fail("build_task_view run-level task must not carry candidate_ref")
        else:
            candidate = prior.candidates.get(str(task_candidate_id))
            if candidate is None:
                raise _fail("build_task_view task candidate missing from run")
            expected_candidate_ref = _plain(candidate.factor_ref)
            if _plain(candidate_ref) != expected_candidate_ref:
                raise _fail("build_task_view candidate_ref mismatch vs task candidate")
            expected_event_inputs.append(expected_candidate_ref)
        _require_exact_refs(
            "build_task_view input_refs", event.input_refs, expected_event_inputs
        )
        hashes = view.get("input_hashes")
        if not isinstance(hashes, Mapping):
            raise _fail("build_task_view input_hashes required")
        expected_hashes: dict[str, str] = {}
        for idx, ref in enumerate(view_input_refs):
            if not isinstance(ref, Mapping):
                raise _fail("build_task_view input_refs entries must be mappings")
            digest = str(ref.get("content_hash") or "") or content_hash(_plain(ref))
            expected_hashes[f"ref:{idx}"] = digest
        if _plain(hashes) != _plain(expected_hashes):
            raise _fail("build_task_view input_hashes mismatch vs input_refs")
        if candidate_ref is not None:
            if not isinstance(candidate_ref, Mapping):
                raise _fail("build_task_view candidate_ref must be a mapping")
            if str(candidate_ref.get("namespace")) != prior.namespace:
                raise _fail("build_task_view candidate_ref namespace mismatch")
            if is_sealed_marker(candidate_ref):
                raise _fail("build_task_view candidate_ref must not be sealed")
        lease = view.get("lease")
        if not isinstance(lease, Mapping):
            raise _fail("build_task_view lease required")
        if frozenset(lease) != _TASK_LEASE_KEYS:
            raise _fail(
                "build_task_view lease schema mismatch",
                missing=sorted(_TASK_LEASE_KEYS - frozenset(lease)),
                unexpected=sorted(frozenset(lease) - _TASK_LEASE_KEYS),
            )
        expected_lease_id = prior_task.get("lease_id") or f"lease-{target_id}"
        if lease.get("lease_id") != expected_lease_id:
            raise _fail("build_task_view lease_id mismatch")
        if str(lease.get("run_id")) != prior.run_id:
            raise _fail("build_task_view lease.run_id mismatch")
        if str(lease.get("task_id")) != target_id:
            raise _fail("build_task_view lease.task_id mismatch")
        if str(lease.get("role_id")) != str(prior_task.get("role_id")):
            raise _fail("build_task_view lease.role_id mismatch")
        rem = dict(prior.budget_remaining)
        for key, field in (
            ("candidates", "candidates_remaining"),
            ("experiments", "experiments_remaining"),
            ("revisions", "revisions_remaining"),
            ("debate_rounds", "debate_rounds_remaining"),
        ):
            if int(lease.get(field, -1)) != int(rem.get(key, 0)):
                raise _fail(f"build_task_view lease.{field} mismatch")
    elif event.result_status == "denied":
        if event.failure is None:
            raise _fail("build_task_view denied requires failure")
        if ordinary:
            raise _fail("build_task_view denied must have empty ordinary outputs")
        # Denied attempts still commit the inspected lineage (brief + payload refs).
        event_inputs = list(event.input_refs or ())
        if not event_inputs:
            raise _fail("build_task_view denied input_refs required")
        if _plain(event_inputs[0]) != _plain(prior.brief_ref):
            raise _fail("build_task_view denied input_refs must start with brief_ref")
    else:
        raise _fail("build_task_view result_status must be ok or denied")


def _validate_command_delta(
    *,
    command: str,
    prior: RunAggregate | None,
    event: Any,
    out_run: Mapping[str, Any],
    outputs: Mapping[str, Any],
    run_id: str,
    namespace: str,
) -> None:
    """Exact minimal business-field delta for every known Phase04 command."""
    if command not in _DELTA_IMPLEMENTED:
        raise _fail("unknown or unimplemented command", command=command)
    ordinary = _ordinary_outputs(outputs)
    _validate_ordinary_schema(command, ordinary, event)
    if command == "create_run":
        if prior is not None:
            raise _fail("create_run must be the first event")
        _validate_create_run_delta(event, out_run, run_id=run_id, namespace=namespace)
        return
    if prior is None:
        raise _fail("non-create command requires prior aggregate", command=command)
    if command == "activate":
        _validate_activate_delta(prior, event, out_run)
    elif command == "request_freeze":
        _validate_request_freeze_delta(prior, event, out_run)
    elif command == "stop":
        _validate_stop_delta(prior, event, out_run, outputs)
    elif command == "reject_run":
        if prior.status is ResearchRunStatus.OOS_TESTED:
            _validate_release_delta(
                prior, event, out_run, outputs, disposition="rejected"
            )
        else:
            _validate_reject_run_delta(prior, event, out_run)
    elif command == "record_gate1_approval":
        _validate_record_gate1_delta(prior, event, out_run, outputs)
    elif command == "authorize_oos":
        _validate_authorize_oos_delta(prior, event, out_run, outputs)
    elif command == "complete_oos":
        _validate_complete_oos_delta(prior, event, out_run, outputs)
    elif command == "record_gate2_approval":
        _validate_record_gate2_delta(prior, event, out_run, outputs)
    elif command == "promote":
        _validate_release_delta(prior, event, out_run, outputs, disposition="promoted")
    elif command == "propose_candidate":
        _validate_propose_candidate_delta(prior, event, out_run, outputs)
    elif command == "revise_candidate":
        _validate_revise_candidate_delta(prior, event, out_run, outputs)
    elif command == "submit_review":
        _validate_submit_review_delta(prior, event, out_run, outputs)
    elif command == "submit_pool_decision":
        _validate_submit_pool_decision_delta(prior, event, out_run, outputs)
    elif command == "reject_candidate":
        _validate_reject_candidate_delta(prior, event, out_run, outputs)
    elif command == "run_candidate_pipeline":
        _validate_pipeline_delta(prior, event, out_run, outputs)
    elif command == "freeze":
        _validate_freeze_delta(prior, event, out_run, outputs)
    elif command == "create_task":
        _validate_create_task_delta(prior, event, out_run)
    elif command == "claim_task":
        _validate_claim_task_delta(prior, event, out_run)
    elif command == "start_task":
        _validate_start_task_delta(prior, event, out_run)
    elif command == "submit_task":
        _validate_submit_task_delta(prior, event, out_run, outputs)
    elif command == "fail_task":
        _validate_end_task_delta(
            prior, event, out_run, command=command, transition_token="fail"
        )
    elif command == "cancel_task":
        _validate_end_task_delta(
            prior, event, out_run, command=command, transition_token="cancel"
        )
    elif command == "timeout_task":
        _validate_end_task_delta(
            prior, event, out_run, command=command, transition_token="timeout"
        )
    elif command == "build_task_view":
        _validate_build_task_view_delta(prior, event, out_run, outputs)
    else:
        raise _fail("delta validator missing implemented command", command=command)


def replay_with_semantics(
    verified_events: Sequence[Mapping[str, Any]],
    *,
    namespace: str,
    run_id: str,
    external_validator: Callable[[Any, RunAggregate | None, Mapping[str, Any], Mapping[str, Any]], None]
    | None = None,
) -> RunAggregate:
    """Rebuild RunAggregate while enforcing deterministic semantic invariants."""
    if not verified_events:
        raise _fail("events required")

    prior: RunAggregate | None = None
    seen_idem: dict[str, Mapping[str, Any]] = {}
    pipeline_phases: dict[str, list[str]] = {}
    immutable_brief: dict[str, Any] | None = None
    immutable_limits: dict[str, int] | None = None

    for index, raw in enumerate(verified_events):
        body = {k: v for k, v in dict(raw).items() if k != "event_hash"}
        event_hash = str(raw["event_hash"])
        event = event_from_body(body, event_hash=event_hash)
        outputs = dict(event.outputs or {})
        out_run_raw = outputs.get("run")
        if not isinstance(out_run_raw, Mapping):
            raise _fail("event outputs.run missing", sequence=event.sequence)

        if event.run_id != run_id:
            raise _fail("event run_id mismatch vs replay target")
        if str(out_run_raw.get("run_id")) != run_id:
            raise _fail("outputs.run.run_id immutable mismatch")
        if str(out_run_raw.get("namespace")) != namespace:
            raise _fail("outputs.run.namespace immutable mismatch")

        if out_run_raw.get("event_head_seq") != event.sequence:
            raise _fail(
                "outputs.run.event_head_seq must equal event.sequence",
                expected=event.sequence,
                got=out_run_raw.get("event_head_seq"),
            )
        if out_run_raw.get("event_head_hash") is not None:
            raise _fail(
                "outputs.run.event_head_hash must be None before reconstruction",
                sequence=event.sequence,
            )

        out_idem = out_run_raw.get("idempotency")
        if not isinstance(out_idem, Mapping):
            raise _fail("outputs.run.idempotency must be a mapping")
        if to_plain_dict(out_idem) != to_plain_dict(seen_idem):
            raise _fail(
                "outputs.run.idempotency must equal previously reconstructed index",
                sequence=event.sequence,
            )

        brief_ref = ObjectRef(**dict(out_run_raw["brief_ref"]))
        limits = _require_budget_map(
            dict(out_run_raw.get("budget_limits") or {}), label="budget_limits"
        )
        remaining = _require_budget_map(
            dict(out_run_raw.get("budget_remaining") or {}), label="budget_remaining"
        )
        for key, rem in remaining.items():
            if rem > limits[key]:
                raise _fail(
                    "budget remaining exceeds limits",
                    key=key,
                    remaining=rem,
                    limit=limits[key],
                )
        reservations = _require_reservations(
            dict(out_run_raw.get("budget_reservations") or {}), limits=limits
        )

        if immutable_brief is None:
            immutable_brief = to_plain_dict(brief_ref)
            immutable_limits = dict(limits)
        else:
            if to_plain_dict(brief_ref) != immutable_brief:
                raise _fail("brief_ref mutated across event prefix")
            if limits != immutable_limits:
                raise _fail("budget_limits mutated across event prefix")

        expected_version = 2 if index == 0 else int(prior.version) + 1  # type: ignore[union-attr]
        got_version = int(out_run_raw.get("version", -1))
        if got_version != expected_version:
            raise _fail(
                "run version must advance exactly one per event",
                expected=expected_version,
                got=got_version,
                sequence=event.sequence,
            )

        delta = dict(event.budget_delta or {})
        unknown_delta = set(delta) - set(BUDGET_KEYS)
        if unknown_delta:
            raise _fail("budget_delta has unknown keys", keys=sorted(unknown_delta))
        if prior is None:
            for key in BUDGET_KEYS:
                expected_delta = remaining[key] - limits[key]
                got_delta = int(delta[key]) if key in delta else 0
                if got_delta != expected_delta:
                    raise _fail(
                        "event.budget_delta mismatch vs remaining change",
                        key=key,
                        expected=expected_delta,
                        got=got_delta,
                    )
        else:
            prior_remaining = _require_budget_map(
                dict(prior.budget_remaining), label="prior_remaining"
            )
            for key in BUDGET_KEYS:
                expected_delta = remaining[key] - prior_remaining[key]
                got_delta = int(delta[key]) if key in delta else 0
                if got_delta != expected_delta:
                    raise _fail(
                        "event.budget_delta mismatch vs remaining change",
                        key=key,
                        expected=expected_delta,
                        got=got_delta,
                        sequence=event.sequence,
                    )

        if index == 0:
            if event.command != "create_run":
                raise _fail("first event must be create_run")
            if (
                event.from_status != "none"
                or event.to_status != ResearchRunStatus.BRIEFED.value
            ):
                raise _fail("create_run must transition none→briefed")
        elif not _transition_legal(
            aggregate_kind=event.aggregate_kind,
            command=event.command,
            from_status=event.from_status,
            to_status=event.to_status,
            result_status=event.result_status,
        ):
            raise _fail(
                "illegal from_status/to_status for command",
                command=event.command,
                from_status=event.from_status,
                to_status=event.to_status,
                aggregate_kind=event.aggregate_kind,
            )

        _validate_command_result(event, outputs, out_run_raw)
        _validate_command_delta(
            command=event.command,
            prior=prior,
            event=event,
            out_run=out_run_raw,
            outputs=outputs,
            run_id=run_id,
            namespace=namespace,
        )
        if event.command in {
            "record_gate1_approval",
            "freeze",
            "authorize_oos",
            "complete_oos",
            "record_gate2_approval",
            "promote",
        } and external_validator is None:
            raise _fail(
                "trusted external authority validator required for gate/sealed replay",
                command=event.command,
            )
        if external_validator is not None:
            try:
                external_validator(event, prior, out_run_raw, outputs)
            except ReplaySemanticsError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise _fail(
                    "trusted external authority binding failed",
                    command=event.command,
                    cause_type=type(exc).__name__,
                    cause=str(exc),
                ) from exc

        idem_key = command_identity_key(
            run_id=event.run_id,
            aggregate_id=event.aggregate_id,
            idempotency_key=event.idempotency_key,
        )
        phase = _phase_of(event, outputs)
        if event.command == "run_candidate_pipeline":
            history = pipeline_phases.setdefault(idem_key, [])
            if phase == "started":
                if history:
                    raise _fail("duplicate pipeline_started for idempotency key")
                history.append("started")
            elif phase == "terminal":
                if history != ["started"]:
                    raise _fail(
                        "pipeline terminal requires exactly one prior started",
                        history=list(history),
                    )
                history.append("terminal")
            else:
                raise _fail(
                    "run_candidate_pipeline event missing started/terminal phase"
                )
        else:
            if idem_key in seen_idem:
                raise _fail(
                    "duplicate logical idempotency key",
                    idempotency_key=event.idempotency_key,
                )
            if phase in {"started", "terminal"}:
                raise _fail("non-pipeline event must not carry pipeline phases")

        rebuilt = RunAggregate.from_payload(out_run_raw)
        rebuilt = replace(
            rebuilt,
            event_head_seq=event.sequence,
            event_head_hash=event_hash,
            budget_limits=limits,
            budget_remaining=remaining,
            budget_reservations=reservations,
        )

        event_outputs = dict(outputs)
        event_outputs.pop("run", None)
        cmd_result = event_outputs.pop("command_result", None)
        if isinstance(cmd_result, Mapping):
            entry_ok = bool(cmd_result.get("ok", False))
            entry_failure = (
                to_plain_dict(cmd_result["failure"])
                if cmd_result.get("failure")
                else None
            )
            entry_outputs = dict(cmd_result.get("outputs") or {})
            stored_cmd = to_plain_dict(cmd_result)
        else:
            entry_ok = event.result_status == "ok"
            entry_failure = to_plain_dict(event.failure) if event.failure else None
            entry_outputs = dict(event_outputs)
            stored_cmd = {
                "ok": entry_ok,
                "failure": entry_failure,
                "outputs": entry_outputs,
                "run": {
                    **dict(out_run_raw),
                    "event_head_hash": None,
                    "idempotency": {},
                },
                "replayed": False,
            }
        idem_entry = {
            "ok": entry_ok,
            "failure": entry_failure,
            "outputs": entry_outputs,
            "event_hash": event_hash,
            "sequence": event.sequence,
            "command_result": stored_cmd,
        }
        if phase:
            idem_entry["pipeline_phase"] = phase
        seen_idem[idem_key] = to_plain_dict(idem_entry)
        rebuilt = replace(rebuilt, idempotency=dict(seen_idem))

        stored = dict(out_run_raw)
        stored["event_head_hash"] = None
        expected_stored = content_hash(
            {k: v for k, v in stored.items() if k != "event_head_hash"}
        )
        if event.state_after_digest != expected_stored:
            raise _fail(
                "state_after_digest mismatch vs outputs.run",
                sequence=event.sequence,
            )

        prior = rebuilt

    assert prior is not None
    return prior


__all__ = [
    "ReplaySemanticsError",
    "replay_with_semantics",
]
