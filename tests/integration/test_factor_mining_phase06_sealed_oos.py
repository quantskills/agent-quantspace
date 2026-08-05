"""Phase 06 dry-run: a nonstandard panel reaches only Phase02/03 ports."""

from __future__ import annotations

import pandas as pd

from skills.factor_mining.adapters import FactorExecutionAdapter
from skills.factor_mining.objects import resolve_typed_object
from tests.fixtures.market_data import make_panel
from tests.skills.factor_mining.test_controller_phase04 import NS, _brief_and_store, _controller
from tests.skills.factor_mining.test_controller_phase06 import (
    _freeze_ready_run,
    _oos_factory,
    _OOSAnalyze,
)


def test_phase06_dry_run_uses_phase02_execution_for_reversed_datetime_panel() -> None:
    store, brief, brief_ref = _brief_and_store()
    panel = make_panel(("AAA", "BBB", "CCC"), periods=48)
    panel = panel.copy()
    panel.index = panel.index.reorder_levels(["eob", "symbol"]).set_names(
        ["trade_date", "symbol"]
    )
    snapshot = panel.copy(deep=True)
    phase02 = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: resolve_typed_object(store, ref),
        resolve_panel=lambda _request: panel,
        artifact_store=store,
    )

    class ExecutionSpy:
        def __init__(self) -> None:
            self.request_ids: list[str] = []

        def execute(self, request):
            self.request_ids.append(request.request_id)
            return phase02.execute(request)

    execution = ExecutionSpy()
    analyze = _OOSAnalyze()
    ctrl, _, _ = _controller(
        store,
        brief_ref,
        analyze=analyze,
        execution=execution,
        gate2_verifier=lambda _payload, _request: None,
        oos_request_factory=_oos_factory,
        now=lambda: "2026-08-05T00:00:00+00:00",
    )
    frozen = _freeze_ready_run(ctrl, store, brief, brief_ref, run_id="oos-panel")
    from skills.factor_mining.controller import CommandRequest

    authorized = ctrl.handle(
        CommandRequest(
            command="authorize_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="authorize",
            actor_id="human-1",
            role_id="human",
            expected_version=frozen.version,
            payload={"namespace": NS},
        )
    )
    assert authorized.ok, authorized.failure
    completed = ctrl.handle(
        CommandRequest(
            command="complete_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="sealed-dry-run",
            actor_id="trusted-worker",
            role_id="executor",
            expected_version=authorized.run.version,
            payload={"namespace": NS},
        )
    )
    assert completed.ok, completed.failure
    assert execution.request_ids == ["c1", *[f"oos-compute-{resolve_typed_object(store, authorized.run.oos_authorization_ref).one_shot_key}"]]
    assert analyze.calls == [
        "preflight",
        "evaluate:train",
        "compare_to_pool",
        "evaluate:sealed",
    ]
    report = resolve_typed_object(store, completed.run.oos_result_ref)
    evaluation = resolve_typed_object(store, report.evaluation_ref)
    assert evaluation.execution_ref is not None
    values = resolve_typed_object(store, evaluation.execution_ref)
    assert values.index_schema.names == ("trade_date", "symbol")
    pd.testing.assert_frame_equal(snapshot, panel)
    values_envelope = store.get_envelope(values.values_ref)
    mask_envelope = store.get_envelope(values.valid_mask_ref)
    assert values_envelope["meta"]["sealed"] is True
    assert mask_envelope["meta"]["sealed"] is True
