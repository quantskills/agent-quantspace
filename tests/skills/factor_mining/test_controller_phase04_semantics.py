"""Phase04 adversarial semantic-replay, snapshot-cache, freeze lineage, review policy."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from skills.factor_mining.contracts import (
    CandidateStatus,
    FailureCode,
    ReviewConclusion,
    content_hash,
    to_plain_dict,
)
from skills.factor_mining.controller import KIND_SNAPSHOT, CommandRequest
from skills.factor_mining.event_chain import (
    state_after_digest_from_run_payload,
    verify_event_chain,
)
from skills.factor_mining.events import GENESIS_HASH, hash_event_body
from skills.factor_mining.objects import put_formal_object
from skills.factor_mining.replay_semantics import ReplaySemanticsError, replay_with_semantics
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
    _pipeline_to_review_pending,
)


def _rehash(event: dict) -> dict:
    """Recompute event_hash; sync state_after_digest when outputs.run is present."""
    body = {k: v for k, v in event.items() if k != "event_hash"}
    outputs = body.get("outputs")
    if isinstance(outputs, dict) and isinstance(outputs.get("run"), dict):
        body = {
            **body,
            "state_after_digest": state_after_digest_from_run_payload(outputs["run"]),
        }
    return {**body, "event_hash": hash_event_body(body)}


def test_phase04_snapshot_only_run_is_not_loadable() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="snap-only")
    # Authoritative events exist; delete them via public list then corrupt by
    # writing a snapshot while removing events is done by using a fresh store
    # with only a snapshot put through the public put API.
    store2, _, brief_ref2 = _brief_and_store()
    ctrl2, _, _ = _controller(store2, brief_ref2)
    store2.put(
        namespace=NS,
        kind=KIND_SNAPSHOT,
        artifact_id="ghost-run",
        payload=run.to_payload() | {"run_id": "ghost-run"},
        input_refs=(brief_ref2,),
    )
    assert ctrl2.load_run(namespace=NS, run_id="ghost-run") is None


def test_phase04_semantic_replay_rejects_adversarial_chains() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="sem-adv")
    events = _list_run_event_payloads(store, run_id="sem-adv")
    assert len(events) >= 2  # create_run + activate

    # Illegal transition: activate from briefed → frozen.
    bad = deepcopy(events)
    bad[1] = dict(bad[1])
    bad[1]["to_status"] = "frozen"
    bad[1] = _rehash(bad[1])
    with pytest.raises(ValueError, match="illegal from_status/to_status"):
        ctrl.replay_events(namespace=NS, run_id="sem-adv", events=bad)

    # Forged budget delta.
    bad = deepcopy(events)
    bad[1] = dict(bad[1])
    bad[1]["budget_delta"] = {"candidates": -1}
    bad[1] = _rehash(bad[1])
    with pytest.raises(ValueError, match="budget_delta"):
        ctrl.replay_events(namespace=NS, run_id="sem-adv", events=bad)

    # Injected idempotency in outputs.run.
    bad = deepcopy(events)
    bad[1] = dict(bad[1])
    outputs = dict(bad[1]["outputs"])
    run_payload = dict(outputs["run"])
    run_payload["idempotency"] = {"forged": {"ok": True}}
    outputs["run"] = run_payload
    bad[1]["outputs"] = outputs
    bad[1] = _rehash(bad[1])
    with pytest.raises(ValueError, match="idempotency"):
        ctrl.replay_events(namespace=NS, run_id="sem-adv", events=bad)

    # Version jump.
    bad = deepcopy(events)
    bad[1] = dict(bad[1])
    outputs = dict(bad[1]["outputs"])
    run_payload = dict(outputs["run"])
    run_payload["version"] = int(run_payload["version"]) + 5
    outputs["run"] = run_payload
    bad[1]["outputs"] = outputs
    bad[1] = _rehash(bad[1])
    with pytest.raises(ValueError, match="version"):
        ctrl.replay_events(namespace=NS, run_id="sem-adv", events=bad)

    # Pipeline: terminal without started.
    factor_ref, _ = _persist_factor(store, brief, factor_id="f1")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="p",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert prop.ok
    pipe = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe-sem",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=_pipeline_payload(brief_ref, factor_ref),
        )
    )
    assert pipe.ok, pipe.failure
    full = _list_run_event_payloads(store, run_id="sem-adv")
    started_idx = next(
        i
        for i, e in enumerate(full)
        if e.get("command") == "run_candidate_pipeline"
        and (e.get("outputs") or {}).get("pipeline_phase") == "started"
    )
    terminal_idx = next(
        i
        for i, e in enumerate(full)
        if e.get("command") == "run_candidate_pipeline"
        and (e.get("outputs") or {}).get("pipeline_phase") == "terminal"
    )
    # Duplicate started: prefix through first started + resequenced second started.
    prefix_started = [deepcopy(e) for e in full[: started_idx + 1]]
    prior_after_started = replay_with_semantics(
        verify_event_chain(prefix_started, namespace=NS, run_id="sem-adv"),
        namespace=NS,
        run_id="sem-adv",
    )
    dup = deepcopy(full[started_idx])
    seq = len(prefix_started) + 1
    prev = prefix_started[-1]["event_hash"]
    dup["sequence"] = seq
    dup["prev_hash"] = prev
    outs = dict(dup["outputs"])
    run_payload = dict(outs["run"])
    run_payload["event_head_seq"] = seq
    run_payload["event_head_hash"] = None
    run_payload["version"] = int(prior_after_started.version) + 1
    run_payload["idempotency"] = to_plain_dict(prior_after_started.idempotency)
    rem = dict(prior_after_started.budget_remaining)
    rem["experiments"] = int(rem["experiments"]) - 1
    run_payload["budget_remaining"] = rem
    run_payload["budget_reservations"] = {
        k: dict(v) for k, v in prior_after_started.budget_reservations.items()
    }
    dup["budget_delta"] = {"experiments": -1}
    outs["run"] = run_payload
    outs["pipeline_phase"] = "started"
    outs["command_result"] = dict(outs.get("command_result") or {})
    outs["command_result"]["ok"] = False
    outs["command_result"]["outputs"] = {
        key: value
        for key, value in outs.items()
        if key not in {"run", "command_result"}
    }
    outs["command_result"]["run"] = {
        **run_payload,
        "event_head_hash": None,
        "idempotency": {},
    }
    dup["outputs"] = outs
    dup["result_status"] = "started"
    dup = _rehash(dup)
    with pytest.raises(ValueError, match="duplicate pipeline_started"):
        ctrl.replay_events(
            namespace=NS, run_id="sem-adv", events=prefix_started + [dup]
        )

    # Terminal without started: prefix up to started + resequenced terminal only.

    prefix = [deepcopy(e) for e in full[:started_idx]]
    term = deepcopy(full[terminal_idx])
    seq = len(prefix) + 1
    prev = prefix[-1]["event_hash"] if prefix else GENESIS_HASH
    term["sequence"] = seq
    term["prev_hash"] = prev
    outs = dict(term["outputs"])
    run_payload = dict(outs["run"])
    run_payload["event_head_seq"] = seq
    run_payload["event_head_hash"] = None
    prior_version = int(prefix[-1]["outputs"]["run"]["version"])
    run_payload["version"] = prior_version + 1
    # Idempotency must equal previously reconstructed index from prefix.
    # Rebuild expected idempotency by replaying prefix first.
    prior_run = replay_with_semantics(
        verify_event_chain(prefix, namespace=NS, run_id="sem-adv"),
        namespace=NS,
        run_id="sem-adv",
    )
    run_payload["idempotency"] = to_plain_dict(prior_run.idempotency)
    prior_rem = dict(prior_run.budget_remaining)
    run_payload["budget_remaining"] = prior_rem
    run_payload["budget_reservations"] = {
        k: dict(v) for k, v in prior_run.budget_reservations.items()
    }
    term["budget_delta"] = {}
    outs["run"] = run_payload
    digest_src = {k: v for k, v in run_payload.items() if k != "event_head_hash"}
    term["state_after_digest"] = content_hash(digest_src)
    outs["command_result"] = dict(outs.get("command_result") or {})
    outs["command_result"]["run"] = {
        **run_payload,
        "event_head_hash": None,
        "idempotency": {},
    }
    term["outputs"] = outs
    term = _rehash(term)
    chain = prefix + [term]
    verified = verify_event_chain(chain, namespace=NS, run_id="sem-adv")
    with pytest.raises(ReplaySemanticsError, match="prior started"):
        replay_with_semantics(verified, namespace=NS, run_id="sem-adv")


def test_phase04_review_policy_debate_revise_self_loops_and_reject() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run, factor_ref, _ = _pipeline_to_review_pending(
        ctrl, store, brief, brief_ref, run_id="rev-pol"
    )
    cand = run.candidates["cand-1"]

    # DEBATE from REVIEW_PENDING → DEBATING
    dref, _ = _persist_review(
        store,
        report_id="rv-d1",
        role_id="methodology_critic",
        factor_ref=factor_ref,
        evaluation_ref=cand.evaluation_ref,
        conclusion=ReviewConclusion.DEBATE,
    )
    out = ctrl.handle(
        CommandRequest(
            command="submit_review",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="d1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "review_ref": to_plain_dict(dref)},
        )
    )
    assert out.ok, out.failure
    assert out.run.candidates["cand-1"].status is CandidateStatus.DEBATING

    # DEBATE again stays DEBATING
    dref2, _ = _persist_review(
        store,
        report_id="rv-d2",
        role_id="leakage_and_code_reviewer",
        factor_ref=factor_ref,
        evaluation_ref=cand.evaluation_ref,
        conclusion=ReviewConclusion.DEBATE,
    )
    out2 = ctrl.handle(
        CommandRequest(
            command="submit_review",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="d2",
            actor_id="a",
            role_id="orchestrator",
            expected_version=out.run.version,
            payload={"namespace": NS, "review_ref": to_plain_dict(dref2)},
        )
    )
    assert out2.ok, out2.failure
    assert out2.run.candidates["cand-1"].status is CandidateStatus.DEBATING

    # Fresh run: REVISE from REVIEW_PENDING → SYNTHESIZING, then REVISE stays
    store_b, brief_b, brief_ref_b = _brief_and_store()
    ctrl_b, _, _ = _controller(store_b, brief_ref_b)
    run_b, factor_b, _ = _pipeline_to_review_pending(
        ctrl_b, store_b, brief_b, brief_ref_b, run_id="rev-syn"
    )
    cand_b = run_b.candidates["cand-1"]
    r1, _ = _persist_review(
        store_b,
        report_id="rv-s1",
        role_id="methodology_critic",
        factor_ref=factor_b,
        evaluation_ref=cand_b.evaluation_ref,
        conclusion=ReviewConclusion.REVISE,
    )
    s1 = ctrl_b.handle(
        CommandRequest(
            command="submit_review",
            run_id=run_b.run_id,
            aggregate_id="cand-1",
            idempotency_key="s1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run_b.version,
            payload={"namespace": NS, "review_ref": to_plain_dict(r1)},
        )
    )
    assert s1.ok and s1.run.candidates["cand-1"].status is CandidateStatus.SYNTHESIZING
    r2, _ = _persist_review(
        store_b,
        report_id="rv-s2",
        role_id="leakage_and_code_reviewer",
        factor_ref=factor_b,
        evaluation_ref=cand_b.evaluation_ref,
        conclusion=ReviewConclusion.REVISE,
    )
    s2 = ctrl_b.handle(
        CommandRequest(
            command="submit_review",
            run_id=run_b.run_id,
            aggregate_id="cand-1",
            idempotency_key="s2",
            actor_id="a",
            role_id="orchestrator",
            expected_version=s1.run.version,
            payload={"namespace": NS, "review_ref": to_plain_dict(r2)},
        )
    )
    assert s2.ok and s2.run.candidates["cand-1"].status is CandidateStatus.SYNTHESIZING

    # DEBATE from SYNTHESIZING is invalid (no transition table bypass).
    store_c, brief_c, brief_ref_c = _brief_and_store()
    ctrl_c, _, _ = _controller(store_c, brief_ref_c)
    run_c, factor_c, _ = _pipeline_to_review_pending(
        ctrl_c, store_c, brief_c, brief_ref_c, run_id="rev-bad"
    )
    cand_c = run_c.candidates["cand-1"]
    r_syn, _ = _persist_review(
        store_c,
        report_id="rv-bad1",
        role_id="methodology_critic",
        factor_ref=factor_c,
        evaluation_ref=cand_c.evaluation_ref,
        conclusion=ReviewConclusion.REVISE,
    )
    syn = ctrl_c.handle(
        CommandRequest(
            command="submit_review",
            run_id=run_c.run_id,
            aggregate_id="cand-1",
            idempotency_key="bad1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run_c.version,
            payload={"namespace": NS, "review_ref": to_plain_dict(r_syn)},
        )
    )
    assert syn.ok
    r_deb, _ = _persist_review(
        store_c,
        report_id="rv-bad2",
        role_id="leakage_and_code_reviewer",
        factor_ref=factor_c,
        evaluation_ref=cand_c.evaluation_ref,
        conclusion=ReviewConclusion.DEBATE,
    )
    denied = ctrl_c.handle(
        CommandRequest(
            command="submit_review",
            run_id=run_c.run_id,
            aggregate_id="cand-1",
            idempotency_key="bad2",
            actor_id="a",
            role_id="orchestrator",
            expected_version=syn.run.version,
            payload={"namespace": NS, "review_ref": to_plain_dict(r_deb)},
        )
    )
    assert denied.ok is False
    assert denied.failure is not None
    assert denied.failure.code is FailureCode.INVALID_STATE


def test_phase04_gate1_rejects_empty_caller_fields() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run, factor_ref, _ = _pipeline_to_review_pending(
        ctrl, store, brief, brief_ref, run_id="g1-empty"
    )
    cand = run.candidates["cand-1"]
    run_cur = run
    for role, rid, key in (
        ("methodology_critic", "rv-m", "rev-m"),
        ("leakage_and_code_reviewer", "rv-l", "rev-l"),
    ):
        review_ref, _ = _persist_review(
            store,
            report_id=rid,
            role_id=role,
            factor_ref=factor_ref,
            evaluation_ref=cand.evaluation_ref,
        )
        rev = ctrl.handle(
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
        assert rev.ok, rev.failure
        run_cur = rev.run
    pool_ref, _ = _persist_pool(store, decision_id="pd-1", factor_ref=factor_ref)
    pool = ctrl.handle(
        CommandRequest(
            command="submit_pool_decision",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pool",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run_cur.version,
            payload={"namespace": NS, "pool_decision_ref": to_plain_dict(pool_ref)},
        )
    )
    assert pool.ok
    for field, intent in (
        ("manifest_id", {**_caller_freeze_intent(), "manifest_id": ""}),
        ("outlier_policy", {**_caller_freeze_intent(), "outlier_policy": ""}),
        (
            "neutralization_policy",
            {**_caller_freeze_intent(), "neutralization_policy": "  "},
        ),
    ):
        denied = ctrl.handle(
            CommandRequest(
                command="record_gate1_approval",
                run_id=run.run_id,
                aggregate_id=run.run_id,
                idempotency_key=f"g1-{field}",
                actor_id="human",
                role_id="human",
                expected_version=pool.run.version,
                payload={
                    "namespace": NS,
                    "approved": True,
                    "human_approval_token": "trusted-human-token",
                    "candidate_id": "cand-1",
                    "freeze_intent": intent,
                },
            )
        )
        assert denied.ok is False
        assert denied.failure is not None
        assert denied.failure.code is FailureCode.INVALID_PARAMETERS


def test_phase04_freeze_manifest_one_field_lineage_mutation_changes_hash() -> None:
    from tests.skills.factor_mining.builders import make_object_ref
    from tests.skills.factor_mining.test_contracts import _make_freeze_manifest

    base = _make_freeze_manifest()
    mutated = replace(
        base,
        preflight_ref=make_object_ref(
            object_type="EvaluationReport",
            object_id="pre-mut",
            content_hash="9" * 64,
            namespace=base.provenance.namespace,
        ),
        content_hash="",
    )
    assert mutated.content_hash != base.content_hash
    for field, ref in (
        (
            "execution_ref",
            make_object_ref(
                object_type="FactorExecutionResult",
                object_id="ex-mut",
                content_hash="8" * 64,
                namespace=base.provenance.namespace,
            ),
        ),
        (
            "compare_ref",
            make_object_ref(
                object_type="EvaluationReport",
                object_id="cmp-mut",
                content_hash="7" * 64,
                namespace=base.provenance.namespace,
            ),
        ),
        (
            "evaluation_ref",
            make_object_ref(
                object_type="EvaluationReport",
                object_id="ev-mut",
                content_hash="6" * 64,
                namespace=base.provenance.namespace,
            ),
        ),
    ):
        other = replace(base, **{field: ref, "content_hash": ""})
        assert other.content_hash != base.content_hash
        assert content_hash(other.payload_for_hash()) == other.content_hash


def test_phase04_activate_rejects_forged_stop_reason_and_gate_refs() -> None:
    """Root exploit: hash-valid activate must not accept unauthorized business fields."""
    store, _brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    _create_active_run(ctrl, brief_ref, run_id="delta-a")
    events = _list_run_event_payloads(store, run_id="delta-a")
    assert events[1]["command"] == "activate"

    # 1) Forged stop_reason (root reproduction).
    bad = deepcopy(events)
    bad[1] = dict(bad[1])
    outputs = dict(bad[1]["outputs"])
    run_payload = dict(outputs["run"])
    run_payload["stop_reason"] = "FORGED_BUT_HASH_VALID"
    outputs["run"] = run_payload
    # Keep command_result.run consistent so only the business delta fails.
    cr = dict(outputs.get("command_result") or {})
    cr_run = dict(cr.get("run") or {})
    cr_run["stop_reason"] = "FORGED_BUT_HASH_VALID"
    cr["run"] = cr_run
    outputs["command_result"] = cr
    bad[1]["outputs"] = outputs
    bad[1] = _rehash(bad[1])
    with pytest.raises(ValueError, match="unauthorized run delta: stop_reason"):
        ctrl.replay_events(namespace=NS, run_id="delta-a", events=bad)

    # 2) Forged gate1_approval_ref on activate.
    bad = deepcopy(events)
    bad[1] = dict(bad[1])
    outputs = dict(bad[1]["outputs"])
    run_payload = dict(outputs["run"])
    forged_gate = {
        "kind": "gate1_approval",
        "namespace": NS,
        "artifact_id": "forged-gate",
        "content_hash": "a" * 64,
    }
    run_payload["gate1_approval_ref"] = forged_gate
    outputs["run"] = run_payload
    cr = dict(outputs.get("command_result") or {})
    cr_run = dict(cr.get("run") or {})
    cr_run["gate1_approval_ref"] = forged_gate
    cr["run"] = cr_run
    outputs["command_result"] = cr
    bad[1]["outputs"] = outputs
    bad[1] = _rehash(bad[1])
    with pytest.raises(ValueError, match="unauthorized run delta: gate1_approval_ref"):
        ctrl.replay_events(namespace=NS, run_id="delta-a", events=bad)

    # 3) Forged freeze_manifest_ref on activate.
    bad = deepcopy(events)
    bad[1] = dict(bad[1])
    outputs = dict(bad[1]["outputs"])
    run_payload = dict(outputs["run"])
    forged_freeze = {
        "object_type": "FreezeManifest",
        "object_id": "forged-fm",
        "content_hash": "b" * 64,
        "namespace": NS,
    }
    run_payload["freeze_manifest_ref"] = forged_freeze
    outputs["run"] = run_payload
    cr = dict(outputs.get("command_result") or {})
    cr_run = dict(cr.get("run") or {})
    cr_run["freeze_manifest_ref"] = forged_freeze
    cr["run"] = cr_run
    outputs["command_result"] = cr
    bad[1]["outputs"] = outputs
    bad[1] = _rehash(bad[1])
    with pytest.raises(ValueError, match="unauthorized run delta: freeze_manifest_ref"):
        ctrl.replay_events(namespace=NS, run_id="delta-a", events=bad)


def test_phase04_activate_rejects_forged_command_result() -> None:
    store, _brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    _create_active_run(ctrl, brief_ref, run_id="delta-cr")
    events = _list_run_event_payloads(store, run_id="delta-cr")

    bad = deepcopy(events)
    bad[1] = dict(bad[1])
    outputs = dict(bad[1]["outputs"])
    cr = dict(outputs["command_result"])
    cr["ok"] = False  # activate is ok=True / result_status=ok
    outputs["command_result"] = cr
    bad[1]["outputs"] = outputs
    bad[1] = _rehash(bad[1])
    with pytest.raises(ValueError, match="command_result.ok mismatch"):
        ctrl.replay_events(namespace=NS, run_id="delta-cr", events=bad)

    bad = deepcopy(events)
    bad[1] = dict(bad[1])
    outputs = dict(bad[1]["outputs"])
    cr = dict(outputs["command_result"])
    cr_run = dict(cr["run"])
    cr_run["stop_reason"] = "FORGED_IN_COMMAND_RESULT"
    cr["run"] = cr_run
    outputs["command_result"] = cr
    bad[1]["outputs"] = outputs
    bad[1] = _rehash(bad[1])
    with pytest.raises(ValueError, match="command_result.run mismatch"):
        ctrl.replay_events(namespace=NS, run_id="delta-cr", events=bad)


def _sync_command_result_run(event: dict) -> dict:
    outputs = dict(event["outputs"])
    run_payload = dict(outputs["run"])
    cr = dict(outputs.get("command_result") or {})
    cr["run"] = {
        **run_payload,
        "event_head_hash": None,
        "idempotency": {},
    }
    # Keep ordinary outputs mirrored inside command_result.
    ordinary = {
        key: value
        for key, value in outputs.items()
        if key not in {"run", "command_result"}
    }
    cr["outputs"] = ordinary
    outputs["command_result"] = cr
    event = {**event, "outputs": outputs}
    return _rehash(event)


def test_phase04_b1_propose_rejects_unrelated_and_budget_forgeries() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="b1-prop")
    factor_ref, _ = _persist_factor(store, brief, factor_id="f1")
    # Seed a second candidate that must stay byte-equal when proposing another.
    first = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-a",
            idempotency_key="pa",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert first.ok, first.failure
    factor_b, _ = _persist_factor(store, brief, factor_id="f2")
    second = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-b",
            idempotency_key="pb",
            actor_id="a",
            role_id="orchestrator",
            expected_version=first.run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_b)},
        )
    )
    assert second.ok, second.failure
    events = _list_run_event_payloads(store, run_id="b1-prop")
    prop_idx = next(
        i for i, e in enumerate(events) if e.get("command") == "propose_candidate"
        and e.get("aggregate_id") == "cand-b"
    )

    # Unrelated candidate mutation.
    bad = deepcopy(events)
    bad[prop_idx] = dict(bad[prop_idx])
    outputs = dict(bad[prop_idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    unrelated = dict(cands["cand-a"])
    unrelated["version"] = int(unrelated["version"]) + 9
    cands["cand-a"] = unrelated
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[prop_idx]["outputs"] = outputs
    bad[prop_idx] = _sync_command_result_run(bad[prop_idx])
    with pytest.raises(ValueError, match="unrelated candidate"):
        ctrl.replay_events(namespace=NS, run_id="b1-prop", events=bad)

    # Unauthorized budget: forge experiments remaining.
    bad = deepcopy(events)
    bad[prop_idx] = dict(bad[prop_idx])
    outputs = dict(bad[prop_idx]["outputs"])
    run_payload = dict(outputs["run"])
    rem = dict(run_payload["budget_remaining"])
    rem["experiments"] = int(rem["experiments"]) - 1
    run_payload["budget_remaining"] = rem
    # Keep budget_delta consistent with remaining so only business delta fails.
    delta = dict(bad[prop_idx].get("budget_delta") or {})
    delta["experiments"] = -1
    bad[prop_idx]["budget_delta"] = delta
    outputs["run"] = run_payload
    bad[prop_idx]["outputs"] = outputs
    bad[prop_idx] = _sync_command_result_run(bad[prop_idx])
    with pytest.raises(ValueError, match="unauthorized budget_remaining.experiments"):
        ctrl.replay_events(namespace=NS, run_id="b1-prop", events=bad)

    # Target identity / status forgery on new candidate.
    bad = deepcopy(events)
    bad[prop_idx] = dict(bad[prop_idx])
    outputs = dict(bad[prop_idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    target = dict(cands["cand-b"])
    target["status"] = CandidateStatus.REJECTED.value
    cands["cand-b"] = target
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[prop_idx]["outputs"] = outputs
    bad[prop_idx] = _sync_command_result_run(bad[prop_idx])
    with pytest.raises(ValueError, match="propose_candidate status must be proposed"):
        ctrl.replay_events(namespace=NS, run_id="b1-prop", events=bad)


def test_phase04_b1_submit_review_rejects_forged_ref_and_identity() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run, factor_ref, _ = _pipeline_to_review_pending(
        ctrl, store, brief, brief_ref, run_id="b1-rev"
    )
    # Propose a second unrelated candidate after pipeline so map has a sibling.
    factor2, _ = _persist_factor(store, brief, factor_id="f-sib")
    sib = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-sib",
            idempotency_key="sib",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor2)},
        )
    )
    assert sib.ok, sib.failure
    run = sib.run
    dref, _ = _persist_review(
        store,
        report_id="rv-b1",
        role_id="methodology_critic",
        factor_ref=factor_ref,
        evaluation_ref=run.candidates["cand-1"].evaluation_ref,
        conclusion=ReviewConclusion.PASS,
    )
    out = ctrl.handle(
        CommandRequest(
            command="submit_review",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rev-b1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "review_ref": to_plain_dict(dref)},
        )
    )
    assert out.ok, out.failure
    events = _list_run_event_payloads(store, run_id="b1-rev")
    idx = next(i for i, e in enumerate(events) if e.get("command") == "submit_review")

    # Unrelated sibling mutation.
    bad = deepcopy(events)
    bad[idx] = dict(bad[idx])
    outputs = dict(bad[idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    sib_body = dict(cands["cand-sib"])
    sib_body["revision"] = int(sib_body["revision"]) + 3
    cands["cand-sib"] = sib_body
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[idx]["outputs"] = outputs
    bad[idx] = _sync_command_result_run(bad[idx])
    with pytest.raises(ValueError, match="unrelated candidate"):
        ctrl.replay_events(namespace=NS, run_id="b1-rev", events=bad)

    # Forged appended review ref (extra fake ref).
    bad = deepcopy(events)
    bad[idx] = dict(bad[idx])
    outputs = dict(bad[idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    target = dict(cands["cand-1"])
    reviews = list(target.get("review_refs") or [])
    forged = {
        "object_type": "ReviewReport",
        "object_id": "forged-rv",
        "content_hash": "c" * 64,
        "namespace": NS,
    }
    reviews.append(forged)
    target["review_refs"] = reviews
    cands["cand-1"] = target
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[idx]["outputs"] = outputs
    bad[idx] = _sync_command_result_run(bad[idx])
    with pytest.raises(ValueError, match="append exactly outputs.review_ref"):
        ctrl.replay_events(namespace=NS, run_id="b1-rev", events=bad)

    # Target factor_ref identity mutation.
    bad = deepcopy(events)
    bad[idx] = dict(bad[idx])
    outputs = dict(bad[idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    target = dict(cands["cand-1"])
    factor = dict(target["factor_ref"])
    factor["content_hash"] = "d" * 64
    target["factor_ref"] = factor
    cands["cand-1"] = target
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[idx]["outputs"] = outputs
    bad[idx] = _sync_command_result_run(bad[idx])
    with pytest.raises(ValueError, match="submit_review.factor_ref"):
        ctrl.replay_events(namespace=NS, run_id="b1-rev", events=bad)

    # Target version jump.
    bad = deepcopy(events)
    bad[idx] = dict(bad[idx])
    outputs = dict(bad[idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    target = dict(cands["cand-1"])
    target["version"] = int(target["version"]) + 5
    cands["cand-1"] = target
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[idx]["outputs"] = outputs
    bad[idx] = _sync_command_result_run(bad[idx])
    with pytest.raises(ValueError, match="submit_review version must advance"):
        ctrl.replay_events(namespace=NS, run_id="b1-rev", events=bad)


def test_phase04_b1_pool_and_reject_forgeries() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run, factor_ref, _ = _pipeline_to_review_pending(
        ctrl, store, brief, brief_ref, run_id="b1-pool"
    )
    # Two independent reviews required before pool.
    cur = run
    for role, rid, key in (
        ("methodology_critic", "r-m", "rm"),
        ("leakage_and_code_reviewer", "r-l", "rl"),
    ):
        ref, _ = _persist_review(
            store,
            report_id=rid,
            role_id=role,
            factor_ref=factor_ref,
            evaluation_ref=cur.candidates["cand-1"].evaluation_ref,
            conclusion=ReviewConclusion.PASS,
        )
        out = ctrl.handle(
            CommandRequest(
                command="submit_review",
                run_id=cur.run_id,
                aggregate_id="cand-1",
                idempotency_key=key,
                actor_id="a",
                role_id="orchestrator",
                expected_version=cur.version,
                payload={"namespace": NS, "review_ref": to_plain_dict(ref)},
            )
        )
        assert out.ok, out.failure
        cur = out.run
    pool_ref, _ = _persist_pool(
        store,
        decision_id="pd-b1",
        factor_ref=factor_ref,
        decision="accept",
    )
    pooled = ctrl.handle(
        CommandRequest(
            command="submit_pool_decision",
            run_id=cur.run_id,
            aggregate_id="cand-1",
            idempotency_key="pool-b1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=cur.version,
            payload={"namespace": NS, "pool_decision_ref": to_plain_dict(pool_ref)},
        )
    )
    assert pooled.ok, pooled.failure
    events = _list_run_event_payloads(store, run_id="b1-pool")
    pool_idx = next(
        i for i, e in enumerate(events) if e.get("command") == "submit_pool_decision"
    )

    # Forged pool ref on candidate body.
    bad = deepcopy(events)
    bad[pool_idx] = dict(bad[pool_idx])
    outputs = dict(bad[pool_idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    target = dict(cands["cand-1"])
    target["pool_decision_ref"] = {
        "object_type": "PoolDecision",
        "object_id": "forged-pd",
        "content_hash": "e" * 64,
        "namespace": NS,
    }
    cands["cand-1"] = target
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[pool_idx]["outputs"] = outputs
    bad[pool_idx] = _sync_command_result_run(bad[pool_idx])
    with pytest.raises(ValueError, match="pool_decision_ref mismatch"):
        ctrl.replay_events(namespace=NS, run_id="b1-pool", events=bad)

    # Reject-candidate path with forged status without version bump consistency.
    rejected = ctrl.handle(
        CommandRequest(
            command="reject_candidate",
            run_id=pooled.run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rej-b1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=pooled.run.version,
            payload={"namespace": NS},
        )
    )
    # freeze_ready can reject
    assert rejected.ok, rejected.failure
    events2 = _list_run_event_payloads(store, run_id="b1-pool")
    rej_idx = next(
        i for i, e in enumerate(events2) if e.get("command") == "reject_candidate"
    )
    bad = deepcopy(events2)
    bad[rej_idx] = dict(bad[rej_idx])
    outputs = dict(bad[rej_idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    target = dict(cands["cand-1"])
    # Mutate an immutable evidence ref.
    target["evaluation_ref"] = {
        "object_type": "EvaluationReport",
        "object_id": "forged-ev",
        "content_hash": "f" * 64,
        "namespace": NS,
    }
    cands["cand-1"] = target
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[rej_idx]["outputs"] = outputs
    bad[rej_idx] = _sync_command_result_run(bad[rej_idx])
    with pytest.raises(ValueError, match="reject_candidate.evaluation_ref"):
        ctrl.replay_events(namespace=NS, run_id="b1-pool", events=bad)


def test_phase04_b2_pipeline_started_rejects_candidate_mutation() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="b2-start")
    factor_ref, _ = _persist_factor(store, brief, factor_id="f1")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="p",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert prop.ok
    pipe = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=_pipeline_payload(brief_ref, factor_ref),
        )
    )
    assert pipe.ok, pipe.failure
    events = _list_run_event_payloads(store, run_id="b2-start")
    started_idx = next(
        i
        for i, e in enumerate(events)
        if e.get("command") == "run_candidate_pipeline"
        and (e.get("outputs") or {}).get("pipeline_phase") == "started"
    )
    # Prefix through started only for replay of forged started.
    prefix = deepcopy(events[: started_idx + 1])
    bad = deepcopy(prefix)
    outputs = dict(bad[started_idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    target = dict(cands["cand-1"])
    target["version"] = int(target["version"]) + 1
    cands["cand-1"] = target
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[started_idx]["outputs"] = outputs
    bad[started_idx] = _sync_command_result_run(bad[started_idx])
    with pytest.raises(ValueError, match="unauthorized run delta: candidates"):
        ctrl.replay_events(namespace=NS, run_id="b2-start", events=bad)


def test_phase04_b2_pipeline_terminal_forgeries() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="b2-term")
    factor_ref, _ = _persist_factor(store, brief, factor_id="f1")
    factor2, _ = _persist_factor(store, brief, factor_id="f2")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="p",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    sib = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-sib",
            idempotency_key="sib",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor2)},
        )
    )
    assert sib.ok
    pipe = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe",
            actor_id="a",
            role_id="orchestrator",
            expected_version=sib.run.version,
            payload=_pipeline_payload(brief_ref, factor_ref),
        )
    )
    assert pipe.ok, pipe.failure
    events = _list_run_event_payloads(store, run_id="b2-term")
    term_idx = next(
        i
        for i, e in enumerate(events)
        if e.get("command") == "run_candidate_pipeline"
        and (e.get("outputs") or {}).get("pipeline_phase") == "terminal"
    )

    # Unrelated candidate mutation on terminal.
    bad = deepcopy(events)
    outputs = dict(bad[term_idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    sib_body = dict(cands["cand-sib"])
    sib_body["revision"] = int(sib_body["revision"]) + 2
    cands["cand-sib"] = sib_body
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[term_idx]["outputs"] = outputs
    bad[term_idx] = _sync_command_result_run(bad[term_idx])
    with pytest.raises(ValueError, match="unrelated candidate"):
        ctrl.replay_events(namespace=NS, run_id="b2-term", events=bad)

    # Forged version (not prior+4).
    bad = deepcopy(events)
    outputs = dict(bad[term_idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    target = dict(cands["cand-1"])
    target["version"] = int(target["version"]) + 1
    cands["cand-1"] = target
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    # Keep outputs.candidate in sync or candidate equality fails first.
    outputs["candidate"] = target
    bad[term_idx]["outputs"] = outputs
    bad[term_idx] = _sync_command_result_run(bad[term_idx])
    with pytest.raises(ValueError, match="pipeline success version must be prior\\+4"):
        ctrl.replay_events(namespace=NS, run_id="b2-term", events=bad)

    # Forged status.
    bad = deepcopy(events)
    outputs = dict(bad[term_idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    target = dict(cands["cand-1"])
    target["status"] = CandidateStatus.REJECTED.value
    cands["cand-1"] = target
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    outputs["candidate"] = target
    bad[term_idx]["outputs"] = outputs
    bad[term_idx]["to_status"] = CandidateStatus.REJECTED.value
    bad[term_idx] = _sync_command_result_run(bad[term_idx])
    with pytest.raises(ValueError, match="pipeline reject|pipeline success|unrecognized"):
        ctrl.replay_events(namespace=NS, run_id="b2-term", events=bad)

    # Forged budget on terminal.
    bad = deepcopy(events)
    outputs = dict(bad[term_idx]["outputs"])
    run_payload = dict(outputs["run"])
    rem = dict(run_payload["budget_remaining"])
    rem["candidates"] = int(rem["candidates"]) - 1
    run_payload["budget_remaining"] = rem
    outputs["run"] = run_payload
    bad[term_idx]["outputs"] = outputs
    bad[term_idx]["budget_delta"] = {"candidates": -1}
    bad[term_idx] = _sync_command_result_run(bad[term_idx])
    with pytest.raises(ValueError, match="unauthorized run delta: budget_remaining|budget_remaining"):
        ctrl.replay_events(namespace=NS, run_id="b2-term", events=bad)

    # Forged FK append on success terminal.
    bad = deepcopy(events)
    outputs = dict(bad[term_idx]["outputs"])
    run_payload = dict(outputs["run"])
    run_payload["failure_knowledge_ids"] = list(
        run_payload.get("failure_knowledge_ids") or []
    ) + ["forged-fk"]
    outputs["run"] = run_payload
    bad[term_idx]["outputs"] = outputs
    bad[term_idx] = _sync_command_result_run(bad[term_idx])
    with pytest.raises(ValueError, match="failure_knowledge_ids"):
        ctrl.replay_events(namespace=NS, run_id="b2-term", events=bad)

    # Recovery mutation: rewrite success as recovery with mutated target.
    bad = deepcopy(events)
    outputs = dict(bad[term_idx]["outputs"])
    outputs["recovery"] = True
    outputs["pipeline_phase"] = "terminal"
    outputs.pop("candidate", None)
    outputs.pop("evaluation_ref", None)
    run_payload = dict(outputs["run"])
    # Restore target to prior-started candidate (byte-equal required), then mutate.
    # Use started event candidate as the committed prior for terminal.
    started = next(
        e
        for e in events
        if e.get("command") == "run_candidate_pipeline"
        and (e.get("outputs") or {}).get("pipeline_phase") == "started"
    )
    prior_cand = dict(started["outputs"]["run"]["candidates"]["cand-1"])
    mutated = dict(prior_cand)
    mutated["version"] = int(mutated["version"]) + 1
    cands = dict(run_payload["candidates"])
    cands["cand-1"] = mutated
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[term_idx]["outputs"] = outputs
    bad[term_idx]["result_status"] = "failed"
    bad[term_idx]["from_status"] = prior_cand["status"]
    bad[term_idx]["to_status"] = prior_cand["status"]
    bad[term_idx]["failure"] = deepcopy(started["failure"])
    bad[term_idx] = _sync_command_result_run(bad[term_idx])
    outputs = dict(bad[term_idx]["outputs"])
    cr = dict(outputs["command_result"])
    cr["ok"] = False
    cr["failure"] = bad[term_idx]["failure"]
    outputs["command_result"] = cr
    bad[term_idx]["outputs"] = outputs
    bad[term_idx] = _rehash(bad[term_idx])
    with pytest.raises(ValueError, match="pipeline recovery target"):
        ctrl.replay_events(namespace=NS, run_id="b2-term", events=bad)


def test_phase04_b2_freeze_manifest_and_unrelated_forgeries() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run, factor_ref, _ = _pipeline_to_review_pending(
        ctrl, store, brief, brief_ref, run_id="b2-fz"
    )
    cur = run
    for role, rid, key in (
        ("methodology_critic", "r-m", "rm"),
        ("leakage_and_code_reviewer", "r-l", "rl"),
    ):
        ref, _ = _persist_review(
            store,
            report_id=rid,
            role_id=role,
            factor_ref=factor_ref,
            evaluation_ref=cur.candidates["cand-1"].evaluation_ref,
            conclusion=ReviewConclusion.PASS,
        )
        out = ctrl.handle(
            CommandRequest(
                command="submit_review",
                run_id=cur.run_id,
                aggregate_id="cand-1",
                idempotency_key=key,
                actor_id="a",
                role_id="orchestrator",
                expected_version=cur.version,
                payload={"namespace": NS, "review_ref": to_plain_dict(ref)},
            )
        )
        assert out.ok, out.failure
        cur = out.run
    pool_ref, _ = _persist_pool(
        store, decision_id="pd-b2", factor_ref=factor_ref, decision="accept"
    )
    pooled = ctrl.handle(
        CommandRequest(
            command="submit_pool_decision",
            run_id=cur.run_id,
            aggregate_id="cand-1",
            idempotency_key="pool",
            actor_id="a",
            role_id="orchestrator",
            expected_version=cur.version,
            payload={"namespace": NS, "pool_decision_ref": to_plain_dict(pool_ref)},
        )
    )
    assert pooled.ok, pooled.failure
    gate = ctrl.handle(
        CommandRequest(
            command="record_gate1_approval",
            run_id=pooled.run.run_id,
            aggregate_id=pooled.run.run_id,
            idempotency_key="g1",
            actor_id="human",
            role_id="human",
            expected_version=pooled.run.version,
            payload={
                "namespace": NS,
                "approved": True,
                "human_approval_token": "trusted-human-token",
                "candidate_id": "cand-1",
                "freeze_intent": _caller_freeze_intent(manifest_id="fm-b2"),
            },
        )
    )
    assert gate.ok, gate.failure
    req = ctrl.handle(
        CommandRequest(
            command="request_freeze",
            run_id=gate.run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rf",
            actor_id="a",
            role_id="orchestrator",
            expected_version=gate.run.version,
            payload={"namespace": NS},
        )
    )
    assert req.ok, req.failure
    frozen = ctrl.handle(
        CommandRequest(
            command="freeze",
            run_id=req.run.run_id,
            aggregate_id="cand-1",
            idempotency_key="fz",
            actor_id="a",
            role_id="orchestrator",
            expected_version=req.run.version,
            payload={"namespace": NS},
        )
    )
    assert frozen.ok, frozen.failure
    events = _list_run_event_payloads(store, run_id="b2-fz")
    fz_idx = next(i for i, e in enumerate(events) if e.get("command") == "freeze")

    # Mismatched run vs target freeze_manifest_ref.
    bad = deepcopy(events)
    outputs = dict(bad[fz_idx]["outputs"])
    run_payload = dict(outputs["run"])
    forged = {
        "object_type": "FreezeManifest",
        "object_id": "forged-fm",
        "content_hash": "1" * 64,
        "namespace": NS,
    }
    run_payload["freeze_manifest_ref"] = forged
    outputs["run"] = run_payload
    bad[fz_idx]["outputs"] = outputs
    bad[fz_idx] = _sync_command_result_run(bad[fz_idx])
    with pytest.raises(ValueError, match="freeze_manifest_ref must equal"):
        ctrl.replay_events(namespace=NS, run_id="b2-fz", events=bad)

    # Unrelated candidate mutation during freeze.
    # First add a sibling before freeze in a fresh run is heavy; mutate by injecting
    # a sibling key into freeze outputs instead — that is add/remove rejection.
    bad = deepcopy(events)
    outputs = dict(bad[fz_idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    cands["ghost"] = dict(cands["cand-1"])
    cands["ghost"]["candidate_id"] = "ghost"
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[fz_idx]["outputs"] = outputs
    bad[fz_idx] = _sync_command_result_run(bad[fz_idx])
    with pytest.raises(ValueError, match="must not add/remove candidates"):
        ctrl.replay_events(namespace=NS, run_id="b2-fz", events=bad)


def test_phase04_b3_task_deltas_reject_forgeries() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="b3-task")
    # Seed a candidate so unrelated-candidate mutations are meaningful.
    factor_ref, _ = _persist_factor(store, brief, factor_id="f1")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="p",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert prop.ok
    t1 = ctrl.handle(
        CommandRequest(
            command="create_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="ct1",
            actor_id="a",
            role_id="worker",
            expected_version=prop.run.version,
            payload={"namespace": NS, "visibility": ["brief"]},
        )
    )
    assert t1.ok
    t2 = ctrl.handle(
        CommandRequest(
            command="create_task",
            run_id=run.run_id,
            aggregate_id="task-2",
            idempotency_key="ct2",
            actor_id="a",
            role_id="worker",
            expected_version=t1.run.version,
            payload={"namespace": NS},
        )
    )
    assert t2.ok
    claimed = ctrl.handle(
        CommandRequest(
            command="claim_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="cl1",
            actor_id="a",
            role_id="worker",
            expected_version=t2.run.version,
            payload={
                "namespace": NS,
                "amounts": {"debate_rounds": 1},
                "lease_id": "lease-1",
            },
        )
    )
    assert claimed.ok, claimed.failure
    started = ctrl.handle(
        CommandRequest(
            command="start_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="st1",
            actor_id="a",
            role_id="worker",
            expected_version=claimed.run.version,
            payload={"namespace": NS},
        )
    )
    assert started.ok, started.failure
    # Claim+cancel sibling to exercise CLAIMED release path later if needed.
    claimed2 = ctrl.handle(
        CommandRequest(
            command="claim_task",
            run_id=run.run_id,
            aggregate_id="task-2",
            idempotency_key="cl2",
            actor_id="a",
            role_id="worker",
            expected_version=started.run.version,
            payload={
                "namespace": NS,
                "amounts": {"revisions": 1},
                "lease_id": "lease-2",
            },
        )
    )
    assert claimed2.ok, claimed2.failure
    cancelled = ctrl.handle(
        CommandRequest(
            command="cancel_task",
            run_id=run.run_id,
            aggregate_id="task-2",
            idempotency_key="cancel2",
            actor_id="a",
            role_id="worker",
            expected_version=claimed2.run.version,
            payload={"namespace": NS},
        )
    )
    assert cancelled.ok, cancelled.failure
    events = _list_run_event_payloads(store, run_id="b3-task")

    # aggregate_kind mismatch on create_task.
    create_idx = next(
        i
        for i, e in enumerate(events)
        if e.get("command") == "create_task" and e.get("aggregate_id") == "task-1"
    )
    bad = deepcopy(events[: create_idx + 1])
    bad[create_idx] = dict(bad[create_idx])
    bad[create_idx]["aggregate_kind"] = "candidate"
    bad[create_idx] = _rehash(bad[create_idx])
    with pytest.raises(
        ValueError,
        match="create_task aggregate_kind must be task|illegal from_status",
    ):
        ctrl.replay_events(namespace=NS, run_id="b3-task", events=bad)

    # Unrelated task mutation on claim.
    claim_idx = next(i for i, e in enumerate(events) if e.get("command") == "claim_task")
    bad = deepcopy(events[: claim_idx + 1])
    outputs = dict(bad[claim_idx]["outputs"])
    run_payload = dict(outputs["run"])
    tasks = dict(run_payload["tasks"])
    other = dict(tasks["task-2"])
    other["attempt"] = int(other.get("attempt", 1)) + 3
    tasks["task-2"] = other
    run_payload["tasks"] = tasks
    outputs["run"] = run_payload
    bad[claim_idx]["outputs"] = outputs
    bad[claim_idx] = _sync_command_result_run(bad[claim_idx])
    with pytest.raises(ValueError, match="unrelated task"):
        ctrl.replay_events(namespace=NS, run_id="b3-task", events=bad)

    # Unrelated candidate mutation on start_task.
    start_idx = next(i for i, e in enumerate(events) if e.get("command") == "start_task")
    bad = deepcopy(events[: start_idx + 1])
    outputs = dict(bad[start_idx]["outputs"])
    run_payload = dict(outputs["run"])
    cands = dict(run_payload["candidates"])
    cand = dict(cands["cand-1"])
    cand["revision"] = int(cand["revision"]) + 1
    cands["cand-1"] = cand
    run_payload["candidates"] = cands
    outputs["run"] = run_payload
    bad[start_idx]["outputs"] = outputs
    bad[start_idx] = _sync_command_result_run(bad[start_idx])
    with pytest.raises(ValueError, match="unauthorized run delta: candidates"):
        ctrl.replay_events(namespace=NS, run_id="b3-task", events=bad)

    # Task identity/linkage mutation on claim (role_id).
    bad = deepcopy(events[: claim_idx + 1])
    outputs = dict(bad[claim_idx]["outputs"])
    run_payload = dict(outputs["run"])
    tasks = dict(run_payload["tasks"])
    target = dict(tasks["task-1"])
    target["role_id"] = "forged-role"
    tasks["task-1"] = target
    run_payload["tasks"] = tasks
    outputs["run"] = run_payload
    bad[claim_idx]["outputs"] = outputs
    bad[claim_idx] = _sync_command_result_run(bad[claim_idx])
    with pytest.raises(ValueError, match="claim_task.role_id"):
        ctrl.replay_events(namespace=NS, run_id="b3-task", events=bad)

    # Illegal version jump on start.
    bad = deepcopy(events[: start_idx + 1])
    outputs = dict(bad[start_idx]["outputs"])
    run_payload = dict(outputs["run"])
    tasks = dict(run_payload["tasks"])
    target = dict(tasks["task-1"])
    target["version"] = int(target["version"]) + 5
    tasks["task-1"] = target
    run_payload["tasks"] = tasks
    outputs["run"] = run_payload
    bad[start_idx]["outputs"] = outputs
    bad[start_idx] = _sync_command_result_run(bad[start_idx])
    with pytest.raises(ValueError, match="start_task version must advance"):
        ctrl.replay_events(namespace=NS, run_id="b3-task", events=bad)

    # Illegal status on start.
    bad = deepcopy(events[: start_idx + 1])
    outputs = dict(bad[start_idx]["outputs"])
    run_payload = dict(outputs["run"])
    tasks = dict(run_payload["tasks"])
    target = dict(tasks["task-1"])
    target["status"] = "failed"
    tasks["task-1"] = target
    run_payload["tasks"] = tasks
    outputs["run"] = run_payload
    bad[start_idx]["outputs"] = outputs
    bad[start_idx]["to_status"] = "failed"
    bad[start_idx] = _sync_command_result_run(bad[start_idx])
    with pytest.raises(ValueError, match="start_task status mismatch|illegal from_status"):
        ctrl.replay_events(namespace=NS, run_id="b3-task", events=bad)

    # Forged lease on start (lease must remain equal).
    bad = deepcopy(events[: start_idx + 1])
    outputs = dict(bad[start_idx]["outputs"])
    run_payload = dict(outputs["run"])
    tasks = dict(run_payload["tasks"])
    target = dict(tasks["task-1"])
    target["lease_id"] = "forged-lease"
    tasks["task-1"] = target
    run_payload["tasks"] = tasks
    outputs["run"] = run_payload
    bad[start_idx]["outputs"] = outputs
    bad[start_idx] = _sync_command_result_run(bad[start_idx])
    with pytest.raises(ValueError, match="start_task.lease_id"):
        ctrl.replay_events(namespace=NS, run_id="b3-task", events=bad)

    # Forged budget on claim (extra experiments decrement).
    bad = deepcopy(events[: claim_idx + 1])
    outputs = dict(bad[claim_idx]["outputs"])
    run_payload = dict(outputs["run"])
    rem = dict(run_payload["budget_remaining"])
    rem["experiments"] = int(rem["experiments"]) - 1
    run_payload["budget_remaining"] = rem
    outputs["run"] = run_payload
    bad[claim_idx]["outputs"] = outputs
    delta = dict(bad[claim_idx].get("budget_delta") or {})
    delta["experiments"] = -1
    bad[claim_idx]["budget_delta"] = delta
    bad[claim_idx] = _sync_command_result_run(bad[claim_idx])
    with pytest.raises(ValueError, match="budget_remaining|budget_reservations"):
        ctrl.replay_events(namespace=NS, run_id="b3-task", events=bad)

    # build_task_view state mutation (cancelled task-2 has empty visibility).
    view = ctrl.handle(
        CommandRequest(
            command="build_task_view",
            run_id=run.run_id,
            aggregate_id="task-2",
            idempotency_key="view2",
            actor_id="a",
            role_id="worker",
            expected_version=cancelled.run.version,
            payload={
                "namespace": NS,
                "goal": "inspect",
                "expected_output_type": "ResearchDecision",
                "input_refs": [],
            },
        )
    )
    assert view.ok, view.failure
    events2 = _list_run_event_payloads(store, run_id="b3-task")
    view_idx = next(
        i
        for i, e in enumerate(events2)
        if e.get("command") == "build_task_view" and e.get("idempotency_key") == "view2"
    )
    bad = deepcopy(events2[: view_idx + 1])
    outputs = dict(bad[view_idx]["outputs"])
    run_payload = dict(outputs["run"])
    run_payload["stop_reason"] = "FORGED_VIEW_MUTATION"
    outputs["run"] = run_payload
    bad[view_idx]["outputs"] = outputs
    bad[view_idx] = _sync_command_result_run(bad[view_idx])
    with pytest.raises(ValueError, match="unauthorized run delta: stop_reason"):
        ctrl.replay_events(namespace=NS, run_id="b3-task", events=bad)

    # Unknown same-status command must fail closed.
    bad = deepcopy(events2[: view_idx + 1])
    bad[view_idx] = dict(bad[view_idx])
    bad[view_idx]["command"] = "noop_unknown"
    # Keep from_status == to_status as a same-status self-loop forgery.
    bad[view_idx] = _rehash(bad[view_idx])
    with pytest.raises(
        ValueError, match="unknown or unimplemented command|illegal from_status"
    ):
        ctrl.replay_events(namespace=NS, run_id="b3-task", events=bad)


def test_phase04_b4_sealed_create_and_view_forgeries() -> None:
    """Confirmed B4 exploits: sealed create_task + sealed/forged AgentTaskView."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="b4-seal")
    created = ctrl.handle(
        CommandRequest(
            command="create_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="ct1",
            actor_id="a",
            role_id="worker",
            expected_version=run.version,
            payload={"namespace": NS, "visibility": ["brief", "factor"]},
        )
    )
    assert created.ok, created.failure
    # Controller rejects sealed at create time (no event).
    denied = ctrl.handle(
        CommandRequest(
            command="create_task",
            run_id=run.run_id,
            aggregate_id="task-sealed",
            idempotency_key="ct-seal",
            actor_id="a",
            role_id="worker",
            expected_version=created.run.version,
            payload={"namespace": NS, "visibility": ["sealed"]},
        )
    )
    assert denied.ok is False
    assert denied.failure.code is FailureCode.FORBIDDEN_INPUT
    assert denied.event is None

    events = _list_run_event_payloads(store, run_id="b4-seal")
    ct_idx = next(
        i
        for i, e in enumerate(events)
        if e.get("command") == "create_task" and e.get("aggregate_id") == "task-1"
    )
    # SEALED_FORGERY_ACCEPTED: rehash a successful create_task with sealed visibility.
    bad = deepcopy(events[: ct_idx + 1])
    outputs = dict(bad[ct_idx]["outputs"])
    run_payload = dict(outputs["run"])
    tasks = dict(run_payload["tasks"])
    forged_task = dict(tasks["task-1"])
    forged_task["visibility"] = ["sealed"]
    tasks["task-1"] = forged_task
    run_payload["tasks"] = tasks
    outputs["run"] = run_payload
    bad[ct_idx]["outputs"] = outputs
    bad[ct_idx] = _sync_command_result_run(bad[ct_idx])
    verify_event_chain(bad, namespace=NS, run_id="b4-seal")
    with pytest.raises(ValueError, match="create_task sealed visibility forbidden"):
        ctrl.replay_events(namespace=NS, run_id="b4-seal", events=bad)

    claimed = ctrl.handle(
        CommandRequest(
            command="claim_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="cl1",
            actor_id="a",
            role_id="worker",
            expected_version=created.run.version,
            payload={
                "namespace": NS,
                "amounts": {"experiments": 1},
                "lease_id": "lease-b4",
            },
        )
    )
    assert claimed.ok, claimed.failure
    view = ctrl.handle(
        CommandRequest(
            command="build_task_view",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="view1",
            actor_id="a",
            role_id="worker",
            expected_version=claimed.run.version,
            payload={
                "namespace": NS,
                "goal": "inspect",
                "expected_output_type": "ResearchDecision",
                "input_refs": [],
            },
        )
    )
    assert view.ok, view.failure
    events2 = _list_run_event_payloads(store, run_id="b4-seal")
    view_idx = next(
        i
        for i, e in enumerate(events2)
        if e.get("command") == "build_task_view" and e.get("idempotency_key") == "view1"
    )
    # VIEW_FORGERY_ACCEPTED: sealed visibility + inflated budget + sealed OOS markers.
    bad = deepcopy(events2[: view_idx + 1])
    outputs = dict(bad[view_idx]["outputs"])
    tv = dict(outputs["task_view"])
    lease = dict(tv["lease"])
    lease["experiments_remaining"] = 999999
    tv["lease"] = lease
    tv["visibility"] = ["sealed"]
    sealed_oos = {
        "object_type": "OOSResult",
        "object_id": "forged-oos",
        "content_hash": "a" * 64,
        "namespace": NS,
        "schema_version": "1.4.0",
    }
    tv["candidate_ref"] = sealed_oos
    outputs["task_view"] = tv
    # Keep event input_refs consistent with forged candidate_ref trailing slot.
    bad[view_idx]["input_refs"] = [
        *list(bad[view_idx].get("input_refs") or []),
        sealed_oos,
    ]
    bad[view_idx]["outputs"] = outputs
    bad[view_idx] = _sync_command_result_run(bad[view_idx])
    verify_event_chain(bad, namespace=NS, run_id="b4-seal")
    with pytest.raises(
        ValueError,
        match=(
            "build_task_view visibility must not include sealed"
            "|build_task_view task_view must not contain sealed markers"
            "|build_task_view lease.experiments_remaining mismatch"
            "|build_task_view visibility mismatch"
        ),
    ):
        ctrl.replay_events(namespace=NS, run_id="b4-seal", events=bad)


def test_phase04_b4_ordinary_schema_submit_pipeline_freeze_forgeries() -> None:
    """Ordinary-key injection, submit output_refs, pipeline eval_ref, freeze schema."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="b4-ord")
    events = _list_run_event_payloads(store, run_id="b4-ord")
    # Unexpected ordinary-output injection on activate (empty schema).
    act_idx = next(i for i, e in enumerate(events) if e.get("command") == "activate")
    bad = deepcopy(events[: act_idx + 1])
    outputs = dict(bad[act_idx]["outputs"])
    outputs["injected_extra"] = {"evil": True}
    bad[act_idx]["outputs"] = outputs
    bad[act_idx] = _sync_command_result_run(bad[act_idx])
    verify_event_chain(bad, namespace=NS, run_id="b4-ord")
    with pytest.raises(ValueError, match="ordinary outputs schema mismatch"):
        ctrl.replay_events(namespace=NS, run_id="b4-ord", events=bad)

    # submit_task output_refs must equal exactly (output_ref,).
    created = ctrl.handle(
        CommandRequest(
            command="create_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="ct1",
            actor_id="a",
            role_id="worker",
            expected_version=run.version,
            payload={"namespace": NS, "visibility": ["brief"]},
        )
    )
    assert created.ok, created.failure
    claimed = ctrl.handle(
        CommandRequest(
            command="claim_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="cl1",
            actor_id="a",
            role_id="worker",
            expected_version=created.run.version,
            payload={"namespace": NS, "amounts": {"candidates": 1}, "lease_id": "L1"},
        )
    )
    assert claimed.ok, claimed.failure
    started = ctrl.handle(
        CommandRequest(
            command="start_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="st1",
            actor_id="a",
            role_id="worker",
            expected_version=claimed.run.version,
            payload={"namespace": NS},
        )
    )
    assert started.ok, started.failure
    out_body = {"decision": "ok", "content_hash": ""}
    out_body["content_hash"] = content_hash(
        {k: v for k, v in out_body.items() if k != "content_hash"}
    )
    output_ref = put_formal_object(
        store,
        namespace=NS,
        object_type="ResearchDecision",
        object_id="dec-b4",
        body=out_body,
    )
    submitted = ctrl.handle(
        CommandRequest(
            command="submit_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="sub1",
            actor_id="a",
            role_id="worker",
            expected_version=started.run.version,
            payload={"namespace": NS, "output_ref": to_plain_dict(output_ref)},
        )
    )
    assert submitted.ok, submitted.failure
    events_sub = _list_run_event_payloads(store, run_id="b4-ord")
    sub_idx = next(
        i for i, e in enumerate(events_sub) if e.get("command") == "submit_task"
    )
    bad = deepcopy(events_sub[: sub_idx + 1])
    extra = {
        "object_type": "ResearchDecision",
        "object_id": "extra",
        "content_hash": "b" * 64,
        "namespace": NS,
        "schema_version": "1.4.0",
    }
    bad[sub_idx]["output_refs"] = list(bad[sub_idx].get("output_refs") or []) + [extra]
    bad[sub_idx] = _rehash(bad[sub_idx])
    verify_event_chain(bad, namespace=NS, run_id="b4-ord")
    with pytest.raises(ValueError, match="submit_task output_refs"):
        ctrl.replay_events(namespace=NS, run_id="b4-ord", events=bad)

    # Pipeline success evaluation_ref mismatch vs candidate.
    run2, _factor_ref, _ = _pipeline_to_review_pending(
        ctrl, store, brief, brief_ref, run_id="b4-pipe"
    )
    events_p = _list_run_event_payloads(store, run_id="b4-pipe")
    term_idx = next(
        i
        for i, e in enumerate(events_p)
        if e.get("command") == "run_candidate_pipeline"
        and e.get("result_status") == "ok"
    )
    bad = deepcopy(events_p[: term_idx + 1])
    outputs = dict(bad[term_idx]["outputs"])
    forged_eval = dict(outputs["evaluation_ref"])
    forged_eval["content_hash"] = "c" * 64
    outputs["evaluation_ref"] = forged_eval
    bad[term_idx]["outputs"] = outputs
    bad[term_idx] = _sync_command_result_run(bad[term_idx])
    verify_event_chain(bad, namespace=NS, run_id="b4-pipe")
    with pytest.raises(
        ValueError,
        match="pipeline success evaluation_ref must equal candidate.evaluation_ref",
    ):
        ctrl.replay_events(namespace=NS, run_id="b4-pipe", events=bad)

    # Freeze: missing manifest / manifest_hash rejected by ordinary schema.
    cur = run2
    for role, rid, key in (
        ("methodology_critic", "r-m", "rm"),
        ("leakage_and_code_reviewer", "r-l", "rl"),
    ):
        ref, _ = _persist_review(
            store,
            report_id=rid,
            role_id=role,
            factor_ref=cur.candidates["cand-1"].factor_ref,
            evaluation_ref=cur.candidates["cand-1"].evaluation_ref,
            conclusion=ReviewConclusion.PASS,
        )
        out = ctrl.handle(
            CommandRequest(
                command="submit_review",
                run_id=cur.run_id,
                aggregate_id="cand-1",
                idempotency_key=key,
                actor_id="a",
                role_id="orchestrator",
                expected_version=cur.version,
                payload={"namespace": NS, "review_ref": to_plain_dict(ref)},
            )
        )
        assert out.ok, out.failure
        cur = out.run
    pool_ref, _ = _persist_pool(
        store, decision_id="pd-b4", factor_ref=cur.candidates["cand-1"].factor_ref, decision="accept"
    )
    pooled = ctrl.handle(
        CommandRequest(
            command="submit_pool_decision",
            run_id=cur.run_id,
            aggregate_id="cand-1",
            idempotency_key="pool",
            actor_id="a",
            role_id="orchestrator",
            expected_version=cur.version,
            payload={"namespace": NS, "pool_decision_ref": to_plain_dict(pool_ref)},
        )
    )
    assert pooled.ok, pooled.failure
    gate = ctrl.handle(
        CommandRequest(
            command="record_gate1_approval",
            run_id=pooled.run.run_id,
            aggregate_id=pooled.run.run_id,
            idempotency_key="g1",
            actor_id="human",
            role_id="human",
            expected_version=pooled.run.version,
            payload={
                "namespace": NS,
                "approved": True,
                "human_approval_token": "trusted-human-token",
                "candidate_id": "cand-1",
                "freeze_intent": _caller_freeze_intent(manifest_id="fm-b4"),
            },
        )
    )
    assert gate.ok, gate.failure
    req = ctrl.handle(
        CommandRequest(
            command="request_freeze",
            run_id=gate.run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rf",
            actor_id="a",
            role_id="orchestrator",
            expected_version=gate.run.version,
            payload={"namespace": NS},
        )
    )
    assert req.ok, req.failure
    frozen = ctrl.handle(
        CommandRequest(
            command="freeze",
            run_id=req.run.run_id,
            aggregate_id="cand-1",
            idempotency_key="fz",
            actor_id="a",
            role_id="orchestrator",
            expected_version=req.run.version,
            payload={"namespace": NS},
        )
    )
    assert frozen.ok, frozen.failure
    events_fz = _list_run_event_payloads(store, run_id="b4-pipe")
    fz_idx = next(i for i, e in enumerate(events_fz) if e.get("command") == "freeze")

    bad = deepcopy(events_fz[: fz_idx + 1])
    outputs = dict(bad[fz_idx]["outputs"])
    outputs.pop("manifest", None)
    bad[fz_idx]["outputs"] = outputs
    bad[fz_idx] = _sync_command_result_run(bad[fz_idx])
    verify_event_chain(bad, namespace=NS, run_id="b4-pipe")
    with pytest.raises(
        ValueError,
        match="ordinary outputs schema mismatch|freeze outputs.manifest required",
    ):
        ctrl.replay_events(namespace=NS, run_id="b4-pipe", events=bad)

    bad = deepcopy(events_fz[: fz_idx + 1])
    outputs = dict(bad[fz_idx]["outputs"])
    outputs.pop("manifest_hash", None)
    bad[fz_idx]["outputs"] = outputs
    bad[fz_idx] = _sync_command_result_run(bad[fz_idx])
    verify_event_chain(bad, namespace=NS, run_id="b4-pipe")
    with pytest.raises(
        ValueError,
        match="ordinary outputs schema mismatch|freeze outputs.manifest_hash required",
    ):
        ctrl.replay_events(namespace=NS, run_id="b4-pipe", events=bad)

    # A full hash-chain rewrite can make the run, embedded command result,
    # manifest hash, staging identity, and event hash agree with each other.
    # It must still lose to the Gate-1 intent and formal objects in the trusted
    # store, which are re-derived by Controller replay rather than self-attested
    # by the event copy.
    bad = deepcopy(events_fz[: fz_idx + 1])
    outputs = dict(bad[fz_idx]["outputs"])
    forged_manifest = dict(outputs["manifest"])
    forged_manifest["direction"] = "forged-direction"
    forged_manifest["content_hash"] = content_hash(
        {key: value for key, value in forged_manifest.items() if key != "content_hash"}
    )
    forged_ref = dict(outputs["manifest_ref"])
    forged_ref["content_hash"] = forged_manifest["content_hash"]
    outputs["manifest"] = forged_manifest
    outputs["manifest_ref"] = forged_ref
    outputs["manifest_hash"] = forged_manifest["content_hash"]
    outputs["staging_content_hash"] = forged_manifest["content_hash"]
    run_payload = dict(outputs["run"])
    run_payload["freeze_manifest_ref"] = forged_ref
    candidates = dict(run_payload["candidates"])
    candidate = dict(candidates["cand-1"])
    candidate["freeze_manifest_ref"] = forged_ref
    candidates["cand-1"] = candidate
    run_payload["candidates"] = candidates
    outputs["run"] = run_payload
    bad[fz_idx]["outputs"] = outputs
    bad[fz_idx]["output_refs"] = [forged_ref]
    bad[fz_idx] = _sync_command_result_run(bad[fz_idx])
    verify_event_chain(bad, namespace=NS, run_id="b4-pipe")
    with pytest.raises(
        ValueError,
        match="trusted external authority binding failed",
    ):
        ctrl.replay_events(namespace=NS, run_id="b4-pipe", events=bad)


def test_phase04_b5_replay_rejects_rehashed_command_reference_injection() -> None:
    """Every command's event refs are an exact, state-derived command binding."""
    store, _brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="b5-ref-injection")
    events = _list_run_event_payloads(store, run_id=run.run_id)
    activate_idx = next(i for i, event in enumerate(events) if event["command"] == "activate")

    # This used to be accepted because state/status/digest/event hash all agree,
    # while replay did not bind activate.input_refs to the Controller's only
    # authoritative input (the run's persisted brief_ref).
    bad = deepcopy(events[: activate_idx + 1])
    bad[activate_idx]["input_refs"] = [
        *bad[activate_idx]["input_refs"],
        {
            "object_type": "FactorSpec",
            "object_id": "injected",
            "content_hash": "f" * 64,
            "namespace": NS,
            "schema_version": "1.4.0",
        },
    ]
    bad[activate_idx] = _rehash(bad[activate_idx])
    verify_event_chain(bad, namespace=NS, run_id=run.run_id)
    with pytest.raises(ValueError, match="activate input_refs"):
        ctrl.replay_events(namespace=NS, run_id=run.run_id, events=bad)


def test_phase04_b5_task_inputs_must_come_from_prior_controller_lineage() -> None:
    """A valid same-namespace object is not task authority by itself."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="b5-task-authority")
    unrelated_factor_ref, _ = _persist_factor(store, brief, factor_id="unrelated")

    # Live command cannot use an object merely because it is valid in the
    # namespace: it first needs publication in Controller-owned run state.
    denied = ctrl.handle(
        CommandRequest(
            command="create_task",
            run_id=run.run_id,
            aggregate_id="denied-task",
            idempotency_key="denied",
            actor_id="a",
            role_id="worker",
            expected_version=run.version,
            payload={
                "namespace": NS,
                "visibility": ["factor"],
                "input_refs": [to_plain_dict(unrelated_factor_ref)],
            },
        )
    )
    assert denied.ok is False
    assert denied.failure is not None
    assert denied.failure.code is FailureCode.FORBIDDEN_INPUT

    created = ctrl.handle(
        CommandRequest(
            command="create_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="create",
            actor_id="a",
            role_id="worker",
            expected_version=run.version,
            payload={"namespace": NS, "visibility": ["factor"]},
        )
    )
    assert created.ok, created.failure
    events = _list_run_event_payloads(store, run_id=run.run_id)
    create_idx = next(
        i
        for i, event in enumerate(events)
        if event["command"] == "create_task" and event["aggregate_id"] == "task-1"
    )

    # Simulate a complete event/state/hash rewrite that names a real formal
    # FactorSpec. Semantic replay must still reject it because the ref was never
    # published in the prior Controller aggregate.
    bad = deepcopy(events[: create_idx + 1])
    outputs = dict(bad[create_idx]["outputs"])
    run_payload = dict(outputs["run"])
    tasks = dict(run_payload["tasks"])
    task = dict(tasks["task-1"])
    task["input_refs"] = [to_plain_dict(unrelated_factor_ref)]
    tasks["task-1"] = task
    run_payload["tasks"] = tasks
    outputs["run"] = run_payload
    bad[create_idx]["outputs"] = outputs
    bad[create_idx]["input_refs"] = [
        to_plain_dict(brief_ref),
        to_plain_dict(unrelated_factor_ref),
    ]
    bad[create_idx] = _sync_command_result_run(bad[create_idx])
    verify_event_chain(bad, namespace=NS, run_id=run.run_id)
    with pytest.raises(ValueError, match="controller-authorized run lineage"):
        ctrl.replay_events(namespace=NS, run_id=run.run_id, events=bad)
