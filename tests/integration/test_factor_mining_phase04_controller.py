"""Phase 04 integration: controller freeze + event replay via public commands only."""

from __future__ import annotations

from skills.factor_mining.contracts import (
    CandidateStatus,
    ResearchRunStatus,
    to_plain_dict,
)
from skills.factor_mining.controller import CommandRequest
from skills.factor_mining.objects import load_formal_payload
from tests.skills.factor_mining.test_controller_phase04 import (
    NS,
    _brief_and_store,
    _caller_freeze_intent,
    _controller,
    _create_active_run,
    _list_run_event_payloads,
    _persist_factor,
    _persist_pool,
    _persist_review,
    _pipeline_payload,
)


def test_integration_phase04_freeze_flow_and_replay() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="integ-run")

    factor_ref, _spec = _persist_factor(store, brief, factor_id="f1")
    proposed = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="p1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert proposed.ok

    pipe = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe-1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=proposed.run.version,
            payload=_pipeline_payload(brief_ref, factor_ref),
        )
    )
    assert pipe.ok, pipe.failure
    cand = pipe.run.candidates["cand-1"]
    run_cur = pipe.run
    for role, rid, key in (
        ("methodology_critic", "r-meth", "rev-m"),
        ("leakage_and_code_reviewer", "r-leak", "rev-l"),
    ):
        review_ref, _ = _persist_review(
            store,
            report_id=rid,
            role_id=role,
            factor_ref=factor_ref,
            evaluation_ref=cand.evaluation_ref,
        )
        reviewed = ctrl.handle(
            CommandRequest(
                command="submit_review",
                run_id=run.run_id,
                aggregate_id="cand-1",
                idempotency_key=key,
                actor_id="a",
                role_id="orchestrator",
                expected_version=run_cur.version,
                payload={"namespace": NS, "review_ref": to_plain_dict(review_ref)},
            )
        )
        assert reviewed.ok, reviewed.failure
        run_cur = reviewed.run

    pool_ref, _ = _persist_pool(store, decision_id="pd-1", factor_ref=factor_ref)
    pool = ctrl.handle(
        CommandRequest(
            command="submit_pool_decision",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pool-1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run_cur.version,
            payload={"namespace": NS, "pool_decision_ref": to_plain_dict(pool_ref)},
        )
    )
    assert pool.ok, pool.failure
    assert pool.run.candidates["cand-1"].status is CandidateStatus.FREEZE_READY

    gate = ctrl.handle(
        CommandRequest(
            command="record_gate1_approval",
            run_id=run.run_id,
            aggregate_id=run.run_id,
            idempotency_key="gate-1",
            actor_id="human",
            role_id="human",
            expected_version=pool.run.version,
            payload={
                "namespace": NS,
                "approved": True,
                "human_approval_token": "trusted-human-token",
                "candidate_id": "cand-1",
                "freeze_intent": _caller_freeze_intent(manifest_id="fm-integ"),
            },
        )
    )
    assert gate.ok, gate.failure

    req_freeze = ctrl.handle(
        CommandRequest(
            command="request_freeze",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rf-1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=gate.run.version,
            payload={"namespace": NS},
        )
    )
    assert req_freeze.ok
    assert req_freeze.run.status is ResearchRunStatus.FREEZE_PENDING

    frozen = ctrl.handle(
        CommandRequest(
            command="freeze",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="fz-1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=req_freeze.run.version,
            payload={"namespace": NS},
        )
    )
    assert frozen.ok, frozen.failure
    assert frozen.run.status is ResearchRunStatus.FROZEN
    assert frozen.run.candidates["cand-1"].status is CandidateStatus.FROZEN
    assert frozen.run.freeze_manifest_ref is not None
    body = load_formal_payload(
        store, frozen.run.freeze_manifest_ref, allow_staging=False
    )
    assert body["content_hash"] == frozen.run.freeze_manifest_ref.content_hash

    events = _list_run_event_payloads(store, run_id="integ-run")
    rebuilt = ctrl.replay_events(namespace=NS, run_id="integ-run", events=events)
    assert rebuilt.status is ResearchRunStatus.FROZEN
    assert rebuilt.event_head_seq == frozen.run.event_head_seq
    assert rebuilt.event_head_hash == frozen.run.event_head_hash
