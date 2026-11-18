"""Governed factor-mining workflow tests on a synthetic panel."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from skills.factor_mining import (
    AcceptanceCriteria,
    DataManagerArtifactStore,
    EvaluationReport,
    ObjectRef,
    PoolDecision,
    PoolDecisionKind,
    Provenance,
    ResearchBrief,
    ResearchBudget,
    ReviewConclusion,
    ReviewReport,
    SplitWindow,
    rebuild_dataclass,
    to_plain_dict,
)
from skills.factor_mining.adapters.store import ArtifactStoreAdapterError
from skills.store.data_manager import DataManager
from strategies.factor_mining.brief import (
    dump_brief,
    load_brief,
    make_example_brief,
)
from strategies.factor_mining.mined_factors import CANDIDATES
from strategies.factor_mining.research import (
    MINED_MODULE_PREFIX,
    POOL_ROLE,
    REVIEW_ROLES,
    UNBLIND_COMPLETED,
    UNBLIND_FAILED,
    UNBLIND_STARTED,
    load_candidates,
    research_data_version,
    run_factor_mining,
    specs_from_candidates,
    write_example_brief,
)
from tests.fixtures.market_data import make_panel, write_symbol_parquet

SYMBOLS = ("AAA", "BBB", "CCC", "DDD", "EEE")
NAMESPACE = "factor_mining.test-brief"
TRAIN_END = "2024-01-31"
VALIDATION_END = "2024-02-20"
SEALED_START = "2024-02-21"
SEALED_END = "2024-03-10"


def _candidate(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "factor_id": "etf18-roc-3",
        "family": "trend_momentum",
        "hypothesis": "Short-horizon close ROC ranks persist in the cross-section.",
        "expected_direction": "long_high",
        "required_fields": ("close",),
        "module": "skills.compute.indicators",
        "name": "roc",
        "params": {"period": 3},
        "window": 3,
        "lag": 0,
        "warmup": 3,
        "missing_policy": "keep_nan",
        "availability_rule": "point_in_time",
        "output_dtype": "float64",
        "index_restore_policy": "restore_original_names_and_order",
        "applicable_regimes": ("trend",),
        "known_relations": (),
        "falsification_tests": ("shuffle_labels_should_kill_ic",),
    }
    row.update(overrides)
    return row


def _write_panel(root: Path, panel: pd.DataFrame) -> None:
    for symbol in SYMBOLS:
        write_symbol_parquet(root, symbol, panel.xs(symbol, level="symbol"), frequency="1d")


def _event_types(data_root: Path) -> set[str]:
    """Kinds of sealed-test records the workflow wrote for the test Brief."""
    store = DataManagerArtifactStore(DataManager(data_root=str(data_root)))
    return {
        kind
        for kind in (UNBLIND_STARTED, UNBLIND_COMPLETED, UNBLIND_FAILED)
        if "test-brief" in store.list_artifact_ids(namespace=NAMESPACE, kind=kind)
    }


def _artifact_store(data_root: Path) -> DataManagerArtifactStore:
    return DataManagerArtifactStore(DataManager(data_root=str(data_root)))


def _brief_for_panel(
    panel: pd.DataFrame, *, max_candidates: int = 4, require_pool_incremental: bool = False
) -> ResearchBrief:
    template = make_example_brief(data_version="pending")
    pending = Provenance(
        producer="test",
        data_version="pending",
        code_version="test",
        experiment_version="test-brief",
        namespace=NAMESPACE,
    )
    draft = ResearchBrief(
        brief_id="test-brief",
        market=template.market,
        asset_class=template.asset_class,
        universe=SYMBOLS,
        frequency="1d",
        allowed_fields=template.allowed_fields,
        symbol_level="symbol",
        datetime_level="eob",
        timezone="naive",
        adjustment=template.adjustment,
        data_version="pending",
        train=SplitWindow("train", "2024-01-01", TRAIN_END, sealed=False),
        validation=SplitWindow("validation", "2024-02-01", VALIDATION_END, sealed=False),
        sealed=SplitWindow("sealed", SEALED_START, SEALED_END, sealed=True),
        horizon_bars=1,
        rebalance="daily",
        cost=template.cost,
        risk=template.risk,
        trading=replace(template.trading, rebalance="daily"),
        robustness=template.robustness,
        multiple_testing_budget=template.multiple_testing_budget,
        budget=ResearchBudget(
            max_candidates=max_candidates,
            max_experiments=40,
            max_revisions=2,
            max_debate_rounds=2,
        ),
        acceptance=AcceptanceCriteria(min_rank_ic_ir=0.3),
        freeze_criteria=replace(
            template.freeze_criteria, require_pool_incremental=require_pool_incremental
        ),
        oos_criteria=AcceptanceCriteria(min_rank_ic_ir=0.2),
        provenance=pending,
    )
    data_version = research_data_version(panel, draft)
    return ResearchBrief(
        brief_id=draft.brief_id,
        market=draft.market,
        asset_class=draft.asset_class,
        universe=draft.universe,
        frequency=draft.frequency,
        allowed_fields=draft.allowed_fields,
        symbol_level=draft.symbol_level,
        datetime_level=draft.datetime_level,
        timezone=draft.timezone,
        adjustment=draft.adjustment,
        data_version=data_version,
        train=draft.train,
        validation=draft.validation,
        sealed=draft.sealed,
        horizon_bars=draft.horizon_bars,
        rebalance=draft.rebalance,
        cost=draft.cost,
        risk=draft.risk,
        trading=draft.trading,
        robustness=draft.robustness,
        multiple_testing_budget=draft.multiple_testing_budget,
        budget=draft.budget,
        acceptance=draft.acceptance,
        freeze_criteria=draft.freeze_criteria,
        oos_criteria=draft.oos_criteria,
        provenance=Provenance(
            producer="test",
            data_version=data_version,
            code_version="test",
            experiment_version="test-brief",
            namespace=NAMESPACE,
        ),
    )


def _setup(
    tmp_path: Path, *, max_candidates: int = 4, require_pool_incremental: bool = False
) -> tuple[ResearchBrief, Path, Path, pd.DataFrame]:
    panel = make_panel(SYMBOLS, periods=70)
    data_root = tmp_path / "data"
    _write_panel(data_root, panel)
    brief = _brief_for_panel(
        panel, max_candidates=max_candidates, require_pool_incremental=require_pool_incremental
    )
    dump_brief(brief, tmp_path / "brief.json")
    return brief, data_root, tmp_path / "reports", panel


def _factor_ref(spec) -> ObjectRef:
    return ObjectRef(
        object_type="FactorSpec",
        object_id=spec.factor_id,
        content_hash=spec.content_hash,
        namespace=spec.provenance.namespace,
    )


def _load_validation(data_root: Path, brief: ResearchBrief, spec):
    store = _artifact_store(data_root)
    payload = store.get_by_identity(
        namespace=brief.provenance.namespace,
        kind="evaluation_report",
        artifact_id=f"eval.{spec.factor_id}.{brief.validation.split_id}",
    )
    report = rebuild_dataclass(EvaluationReport, payload)
    report.validate_hash()
    return report


def _compare(data_root: Path, brief: ResearchBrief, spec) -> EvaluationReport:
    """Run the compare phase against the current pool and load its report."""
    result = run_factor_mining(
        brief=brief,
        phase="compare",
        data_root=data_root,
        output_dir=data_root.parent / "reports",
        factor_id=spec.factor_id,
    )
    payload = _artifact_store(data_root).get_by_identity(
        namespace=brief.provenance.namespace,
        kind="evaluation_report",
        artifact_id=f"compare.{spec.factor_id}.p{len(result.pool_factor_ids)}",
    )
    report = rebuild_dataclass(EvaluationReport, payload)
    report.validate_hash()
    return report


def _pool_evidence(compare: EvaluationReport):
    """The evidence an accepting decision cites: the unavailable check or a pool fact."""
    section = next(item for item in compare.sections if item.name == "pool_incremental")
    if not compare.pool_refs:
        return next(item.evidence for item in section.checks if item.name == "POOL_UNAVAILABLE")
    return next(item.evidence for item in section.facts if item.value is not None)


def _pool_decision(
    brief: ResearchBrief, spec, compare: EvaluationReport, **overrides
) -> PoolDecision:
    fields: dict[str, object] = {
        "decision_id": f"pool.{spec.factor_id}",
        "factor_ref": _factor_ref(spec),
        "decision": PoolDecisionKind.ACCEPT,
        "incremental_evidence": (_pool_evidence(compare),),
        "residual_risks": () if compare.pool_refs else ("POOL_INCREMENTAL_UNAVAILABLE",),
        "role_id": "pool_synthesizer",
        "provenance": Provenance(
            producer="pool_synthesizer",
            data_version=brief.data_version,
            code_version="test",
            experiment_version=brief.brief_id,
            namespace=brief.provenance.namespace,
            input_refs=(_factor_ref(spec),),
        ),
    }
    fields.update(overrides)
    return PoolDecision(**fields)


def _record_pool(data_root: Path, brief: ResearchBrief, decision: PoolDecision):
    return run_factor_mining(
        brief=brief,
        phase="record",
        data_root=data_root,
        record_object={"object_type": "PoolDecision", "payload": to_plain_dict(decision)},
    )


def _put_reviews(
    data_root: Path,
    brief: ResearchBrief,
    spec,
    validation,
    *,
    conclusion: ReviewConclusion = ReviewConclusion.PASS,
    include_pool: bool = True,
) -> None:
    """Record both reviews, then compare with the pool and record an accepting decision."""
    namespace = brief.provenance.namespace
    factor_ref = _factor_ref(spec)
    evaluation_ref = ObjectRef(
        object_type="EvaluationReport",
        object_id=validation.report_id,
        content_hash=validation.content_hash,
        namespace=namespace,
    )
    for role_id in REVIEW_ROLES:
        review = ReviewReport(
            report_id=f"rev.{spec.factor_id}.{role_id}",
            role_id=role_id,
            factor_ref=factor_ref,
            evaluation_ref=evaluation_ref,
            conclusion=conclusion,
            issues=(),
            allow_revision=False,
            requires_full_rerun=False,
            provenance=Provenance(
                producer=role_id,
                data_version=brief.data_version,
                code_version="test",
                experiment_version=brief.brief_id,
                namespace=namespace,
                input_refs=(factor_ref,),
            ),
        )
        run_factor_mining(
            brief=brief,
            phase="record",
            data_root=data_root,
            record_object={"object_type": "ReviewReport", "payload": to_plain_dict(review)},
        )
    if include_pool:
        _record_pool(
            data_root, brief, _pool_decision(brief, spec, _compare(data_root, brief, spec))
        )


def test_example_brief_round_trips(tmp_path: Path) -> None:
    brief = make_example_brief(data_version="local-panel-fingerprint")
    path = tmp_path / "brief.json"
    dump_brief(brief, path)
    restored = load_brief(path)
    assert restored.content_hash == brief.content_hash


def test_candidates_use_indicators_or_a_mined_factors_package() -> None:
    assert CANDIDATES
    assert len({row["factor_id"] for row in CANDIDATES}) == len(CANDIDATES)
    brief = make_example_brief(data_version="local-panel-fingerprint")
    assert len(specs_from_candidates(brief)) == len(CANDIDATES)
    assert load_candidates(None) == tuple(CANDIDATES)
    assert load_candidates("strategies.factor_mining.mined_factors.baseline") == tuple(CANDIDATES)
    for module in (
        f"{MINED_MODULE_PREFIX}.generated",
        "strategies.cross_sectional.mined_factors.trend_momentum",
    ):
        assert len(specs_from_candidates(brief, (_candidate(module=module),))) == 1


def test_candidate_module_outside_the_allowed_packages_is_rejected() -> None:
    brief = make_example_brief(data_version="local-panel-fingerprint")
    with pytest.raises(ValueError, match="function_ref.module must be"):
        specs_from_candidates(brief, (_candidate(module="skills.compute.wrappers"),))


def test_screening_adapter_panel_excludes_sealed_rows(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path)
    result = run_factor_mining(
        brief=brief,
        phase="screening",
        data_root=data_root,
        output_dir=output_dir,
        candidates=(_candidate(),),
        panel=panel,
    )
    assert result.contains_sealed_rows is False
    assert result.observed_panel_end is not None
    assert result.observed_panel_end <= VALIDATION_END
    assert pd.Timestamp(result.observed_panel_end) < pd.Timestamp(SEALED_START)
    sealed = panel.loc[
        pd.DatetimeIndex(pd.to_datetime(panel.index.get_level_values("eob")))
        >= pd.Timestamp(SEALED_START)
    ]
    assert not sealed.empty


def test_screening_keeps_screened_candidates_and_adds_new_ones(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path)
    candidate = _candidate()
    kwargs = {"brief": brief, "phase": "screening", "data_root": data_root, "panel": panel}
    first = run_factor_mining(output_dir=output_dir, candidates=(candidate,), **kwargs)
    index_path = output_dir / "screening_index.json"
    screened = json.loads(index_path.read_text())["candidates"][0]
    table = pd.read_csv(output_dir / "screening_results.csv")
    assert list(table["factor_id"]) == ["etf18-roc-3"]
    assert {"train_rank_ic_mean", "validation_rank_ic_ir"} <= set(table.columns)

    added = _candidate(factor_id="etf18-roc-5", params={"period": 5}, window=5, warmup=5)
    second = run_factor_mining(output_dir=output_dir, candidates=(candidate, added), **kwargs)
    rows = json.loads(index_path.read_text())["candidates"]
    assert first.factor_ids == ("etf18-roc-3",)
    assert second.factor_ids == ("etf18-roc-3", "etf18-roc-5")
    # The first candidate's reports are the ones reviews would already be bound to.
    assert rows[0] == screened

    changed = _candidate(params={"period": 4})
    with pytest.raises(ValueError, match="candidate changed after it was screened"):
        run_factor_mining(output_dir=output_dir, candidates=(changed,), **kwargs)
    with pytest.raises(ValueError, match="belongs to another Brief"):
        other = replace(brief, notes="another brief", content_hash="")
        run_factor_mining(
            brief=other,
            phase="screening",
            data_root=data_root,
            output_dir=output_dir,
            candidates=(candidate,),
            panel=panel,
        )


def test_final_without_write_is_rejected(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path)
    with pytest.raises(ValueError, match="final requires --write"):
        run_factor_mining(
            brief=brief,
            phase="final",
            data_root=data_root,
            output_dir=output_dir,
            write=False,
            panel=panel,
            candidates=(_candidate(),),
        )


def test_budget_excess_is_rejected(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path, max_candidates=1)
    with pytest.raises(ValueError, match="candidate count exceeds budget"):
        run_factor_mining(
            brief=brief,
            phase="screening",
            data_root=data_root,
            output_dir=output_dir,
            candidates=(_candidate(), _candidate(factor_id="etf18-roc-4")),
            panel=panel,
        )


def test_data_version_mismatch_is_rejected(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path)
    mutated = panel.copy()
    mutated.loc[:, "close"] = mutated["close"] * 1.01
    with pytest.raises(ValueError, match="data_version mismatch"):
        run_factor_mining(
            brief=brief,
            phase="screening",
            data_root=data_root,
            output_dir=output_dir,
            candidates=(_candidate(),),
            panel=mutated,
        )


def _screen(tmp_path: Path, *candidates, **setup):
    brief, data_root, output_dir, panel = _setup(tmp_path, **setup)
    rows = candidates or (_candidate(),)
    run_factor_mining(
        brief=brief,
        phase="screening",
        data_root=data_root,
        output_dir=output_dir,
        candidates=rows,
        panel=panel,
    )
    return brief, data_root, output_dir, panel, specs_from_candidates(brief, rows)


def _freeze(brief, data_root, output_dir, *factor_ids):
    return run_factor_mining(
        brief=brief, phase="freeze", data_root=data_root, output_dir=output_dir, approve=factor_ids
    )


def test_pool_acceptance_requires_both_reviews_without_hard_fail(tmp_path: Path) -> None:
    brief, data_root, output_dir, _panel, (spec,) = _screen(tmp_path)
    with pytest.raises(ValueError, match="first factors of the pool"):
        _freeze(brief, data_root, output_dir, spec.factor_id)
    compare = _compare(data_root, brief, spec)
    with pytest.raises(ValueError, match="missing review"):
        _record_pool(data_root, brief, _pool_decision(brief, spec, compare))
    validation = _load_validation(data_root, brief, spec)
    with pytest.raises(ValueError, match="reviews without hard fail"):
        _put_reviews(data_root, brief, spec, validation, conclusion=ReviewConclusion.FAIL)
    with pytest.raises(ValueError, match="first factors of the pool"):
        _freeze(brief, data_root, output_dir, spec.factor_id)


def test_freeze_requires_an_accepted_pool_member(tmp_path: Path) -> None:
    brief, data_root, output_dir, _panel, (spec,) = _screen(tmp_path)
    _put_reviews(
        data_root, brief, spec, _load_validation(data_root, brief, spec), include_pool=False
    )
    with pytest.raises(ValueError, match="first factors of the pool"):
        _freeze(brief, data_root, output_dir, spec.factor_id)


def test_empty_pool_bootstrap_requires_brief_opt_in(tmp_path: Path) -> None:
    brief, data_root, output_dir, _panel, (spec,) = _screen(tmp_path, require_pool_incremental=True)
    with pytest.raises(ValueError, match="empty-pool bootstrap evidence or Brief opt-in missing"):
        _put_reviews(data_root, brief, spec, _load_validation(data_root, brief, spec))
    with pytest.raises(ValueError, match="first factors of the pool"):
        _freeze(brief, data_root, output_dir, spec.factor_id)
    with pytest.raises(ArtifactStoreAdapterError):
        _artifact_store(data_root).get_by_identity(
            namespace=brief.provenance.namespace,
            kind="human_gate_1",
            artifact_id=f"approve.{spec.factor_id}",
        )


def test_empty_pool_bootstrap_requires_unavailable_evidence(tmp_path: Path) -> None:
    brief, data_root, _output_dir, _panel, (spec,) = _screen(tmp_path)
    _put_reviews(
        data_root, brief, spec, _load_validation(data_root, brief, spec), include_pool=False
    )
    compare = _compare(data_root, brief, spec)
    decision = _pool_decision(brief, spec, compare, incremental_evidence=(), residual_risks=())
    with pytest.raises(ValueError, match="empty-pool bootstrap evidence or Brief opt-in missing"):
        _record_pool(data_root, brief, decision)


def _two_candidates():
    return (
        _candidate(),
        _candidate(factor_id="etf18-roc-5", params={"period": 5}, window=5, warmup=5),
    )


def test_second_factor_needs_evidence_against_the_current_pool(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel, (first, second) = _screen(tmp_path, *_two_candidates())
    _put_reviews(
        data_root, brief, second, _load_validation(data_root, brief, second), include_pool=False
    )
    # Compared while the pool was still empty; the first factor is accepted afterwards.
    stale = _compare(data_root, brief, second)
    assert stale.pool_refs == ()
    _put_reviews(data_root, brief, first, _load_validation(data_root, brief, first))
    with pytest.raises(ValueError, match="run the compare phase first"):
        _record_pool(data_root, brief, _pool_decision(brief, second, stale))

    current = _compare(data_root, brief, second)
    assert [ref.object_id for ref in current.pool_refs] == [f"{first.factor_id}__validation"]
    summary = json.loads((output_dir / f"compare.{second.factor_id}.p1.json").read_text())
    assert summary["pool_factor_ids"] == [first.factor_id]
    uncited = _pool_decision(brief, second, current, incremental_evidence=())
    with pytest.raises(ValueError, match="must cite incremental evidence"):
        _record_pool(data_root, brief, uncited)
    accepted = _record_pool(data_root, brief, _pool_decision(brief, second, current))
    assert accepted.pool_factor_ids == (first.factor_id, second.factor_id)
    with pytest.raises(ValueError, match="already in the pool"):
        _compare(data_root, brief, second)

    with pytest.raises(ValueError, match="first factors of the pool"):
        _freeze(brief, data_root, output_dir, second.factor_id)
    with pytest.raises(ValueError, match="first factors of the pool"):
        _freeze(brief, data_root, output_dir, second.factor_id, first.factor_id)
    frozen = _freeze(brief, data_root, output_dir, first.factor_id, second.factor_id)
    assert len(frozen.manifest_hashes) == 2
    manifests = [
        _artifact_store(data_root).get_by_identity(
            namespace=NAMESPACE, kind="freeze_manifest", artifact_id=spec.factor_id
        )
        for spec in (first, second)
    ]
    assert manifests[0]["pool_baseline_refs"] == []
    assert [ref["object_id"] for ref in manifests[1]["pool_baseline_refs"]] == [
        f"{first.factor_id}__validation"
    ]
    final = run_factor_mining(
        brief=brief,
        phase="final",
        data_root=data_root,
        output_dir=output_dir,
        write=True,
        panel=panel,
    )
    assert final.factor_ids == (first.factor_id, second.factor_id)
    sealed = json.loads((output_dir / "final_summary.json").read_text())["sealed"]
    assert [row["factor_id"] for row in sealed] == [first.factor_id, second.factor_id]


def test_a_leading_part_of_the_pool_can_be_frozen(tmp_path: Path) -> None:
    brief, data_root, output_dir, _panel, (first, second) = _screen(tmp_path, *_two_candidates())
    for spec in (first, second):
        _put_reviews(data_root, brief, spec, _load_validation(data_root, brief, spec))
    frozen = _freeze(brief, data_root, output_dir, first.factor_id)
    assert frozen.factor_ids == (first.factor_id,)


def test_second_final_with_same_manifest_digest_is_rejected(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path)
    candidates = (_candidate(),)
    run_factor_mining(
        brief=brief,
        phase="screening",
        data_root=data_root,
        output_dir=output_dir,
        candidates=candidates,
        panel=panel,
    )
    spec = specs_from_candidates(brief, candidates)[0]
    validation = _load_validation(data_root, brief, spec)
    _put_reviews(data_root, brief, spec, validation)
    freeze = run_factor_mining(
        brief=brief,
        phase="freeze",
        data_root=data_root,
        output_dir=output_dir,
        approve=(spec.factor_id,),
    )
    assert freeze.manifest_hashes
    first = run_factor_mining(
        brief=brief,
        phase="final",
        data_root=data_root,
        output_dir=output_dir,
        write=True,
        panel=panel,
        candidates=candidates,
    )
    events = _event_types(data_root)
    assert UNBLIND_STARTED in events
    assert UNBLIND_COMPLETED in events
    assert first.once_key
    sealed_result = json.loads((output_dir / "final_summary.json").read_text())["sealed"][0]
    assert sealed_result["oos_thresholds"]
    assert set(sealed_result["oos_metrics"]) == set(sealed_result["oos_thresholds"])
    assert isinstance(sealed_result["oos_passed"], bool)
    with pytest.raises(ValueError, match="sealed OOS already started"):
        run_factor_mining(
            brief=brief,
            phase="final",
            data_root=data_root,
            output_dir=output_dir,
            write=True,
            panel=panel,
            candidates=candidates,
        )


def test_init_writes_a_brief_bound_to_local_research_data(tmp_path: Path) -> None:
    panel = make_panel(tuple(make_example_brief(data_version="pending").universe), periods=2400)
    data_root = tmp_path / "data"
    for symbol in panel.index.get_level_values("symbol").unique():
        write_symbol_parquet(
            data_root, symbol, panel.xs(symbol, level="symbol"), frequency="1d_adj"
        )
    path = tmp_path / "brief.json"
    brief = write_example_brief(path, data_root=data_root)
    assert load_brief(path).content_hash == brief.content_hash
    assert brief.data_version == research_data_version(panel, brief)
    assert pd.Timestamp(brief.validation.end) < pd.Timestamp(brief.sealed.start)
    with pytest.raises(FileExistsError):
        write_example_brief(path, data_root=data_root)


def test_record_rejects_bad_hash_and_wrong_factor(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path)
    candidate = _candidate()
    run_factor_mining(
        brief=brief,
        phase="screening",
        data_root=data_root,
        output_dir=output_dir,
        candidates=(candidate,),
        panel=panel,
    )
    spec = specs_from_candidates(brief, (candidate,))[0]
    validation = _load_validation(data_root, brief, spec)
    wrong_ref = replace(_factor_ref(spec), content_hash="0" * 64)
    review = ReviewReport(
        report_id=f"rev.{spec.factor_id}.{REVIEW_ROLES[0]}",
        role_id=REVIEW_ROLES[0],
        factor_ref=wrong_ref,
        evaluation_ref=ObjectRef(
            "EvaluationReport",
            validation.report_id,
            content_hash=validation.content_hash,
            namespace=NAMESPACE,
        ),
        conclusion=ReviewConclusion.PASS,
        issues=(),
        allow_revision=False,
        requires_full_rerun=False,
        provenance=Provenance(
            producer=REVIEW_ROLES[0],
            data_version=brief.data_version,
            code_version="test",
            experiment_version=brief.brief_id,
            namespace=NAMESPACE,
        ),
    )
    with pytest.raises(ValueError, match="object reference mismatch"):
        run_factor_mining(
            brief=brief,
            phase="record",
            data_root=data_root,
            record_object={"object_type": "ReviewReport", "payload": to_plain_dict(review)},
        )
    forged = to_plain_dict(review)
    forged["content_hash"] = "0" * 64
    with pytest.raises(ValueError, match="content_hash mismatch"):
        run_factor_mining(
            brief=brief,
            phase="record",
            data_root=data_root,
            record_object={"object_type": "ReviewReport", "payload": forged},
        )


def test_record_rejects_wrong_type_missing_reference_and_duplicate_id(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path)
    candidate = _candidate()
    run_factor_mining(
        brief=brief,
        phase="screening",
        data_root=data_root,
        output_dir=output_dir,
        candidates=(candidate,),
        panel=panel,
    )
    spec = specs_from_candidates(brief, (candidate,))[0]
    validation = _load_validation(data_root, brief, spec)
    with pytest.raises(ValueError, match="record supports"):
        run_factor_mining(
            brief=brief,
            phase="record",
            data_root=data_root,
            record_object={"object_type": "FactorSpec", "payload": to_plain_dict(spec)},
        )
    ref = ObjectRef(
        "EvaluationReport",
        validation.report_id,
        content_hash=validation.content_hash,
        namespace=NAMESPACE,
    )
    base = ReviewReport(
        report_id=f"rev.{spec.factor_id}.{REVIEW_ROLES[0]}",
        role_id=REVIEW_ROLES[0],
        factor_ref=_factor_ref(spec),
        evaluation_ref=ref,
        conclusion=ReviewConclusion.PASS,
        issues=(),
        allow_revision=False,
        requires_full_rerun=False,
        provenance=Provenance(
            producer=REVIEW_ROLES[0],
            data_version=brief.data_version,
            code_version="test",
            experiment_version=brief.brief_id,
            namespace=NAMESPACE,
            input_refs=(_factor_ref(spec),),
        ),
    )
    missing = replace(
        base,
        evaluation_ref=replace(ref, object_id="eval-missing"),
        content_hash="",
    )
    with pytest.raises(ArtifactStoreAdapterError, match="artifact not found"):
        run_factor_mining(
            brief=brief,
            phase="record",
            data_root=data_root,
            record_object={"object_type": "ReviewReport", "payload": to_plain_dict(missing)},
        )
    run_factor_mining(
        brief=brief,
        phase="record",
        data_root=data_root,
        record_object={"object_type": "ReviewReport", "payload": to_plain_dict(base)},
    )
    changed = replace(base, rationale="changed", content_hash="")
    with pytest.raises(
        ArtifactStoreAdapterError, match="append-only artifact exists with different content"
    ):
        run_factor_mining(
            brief=brief,
            phase="record",
            data_root=data_root,
            record_object={"object_type": "ReviewReport", "payload": to_plain_dict(changed)},
        )
    evidence = next(fact.evidence for section in validation.sections for fact in section.facts)
    uncompared = PoolDecision(
        decision_id=f"pool.{spec.factor_id}",
        factor_ref=_factor_ref(spec),
        decision=PoolDecisionKind.ACCEPT,
        incremental_evidence=(evidence,),
        residual_risks=(),
        role_id="pool_synthesizer",
        provenance=Provenance(
            producer="pool_synthesizer",
            data_version=brief.data_version,
            code_version="test",
            experiment_version=brief.brief_id,
            namespace=NAMESPACE,
        ),
    )
    with pytest.raises(ValueError, match="run the compare phase first"):
        _record_pool(data_root, brief, uncompared)
    with pytest.raises(ArtifactStoreAdapterError):
        _artifact_store(data_root).get_by_identity(
            namespace=NAMESPACE,
            kind="pool_decision",
            artifact_id=f"{spec.factor_id}.pool_synthesizer",
        )


def test_rejected_pool_decision_does_not_enter_the_pool(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path)
    candidate = _candidate()
    run_factor_mining(
        brief=brief,
        phase="screening",
        data_root=data_root,
        output_dir=output_dir,
        candidates=(candidate,),
        panel=panel,
    )
    spec = specs_from_candidates(brief, (candidate,))[0]
    _put_reviews(
        data_root, brief, spec, _load_validation(data_root, brief, spec), include_pool=False
    )
    pool = PoolDecision(
        decision_id=f"pool.{spec.factor_id}",
        factor_ref=_factor_ref(spec),
        decision=PoolDecisionKind.REJECT,
        incremental_evidence=(),
        residual_risks=(),
        role_id="pool_synthesizer",
        provenance=Provenance(
            producer="pool_synthesizer",
            data_version=brief.data_version,
            code_version="test",
            experiment_version=brief.brief_id,
            namespace=NAMESPACE,
        ),
    )
    run_factor_mining(
        brief=brief,
        phase="record",
        data_root=data_root,
        record_object={"object_type": "PoolDecision", "payload": to_plain_dict(pool)},
    )
    with pytest.raises(ValueError, match="first factors of the pool"):
        run_factor_mining(
            brief=brief,
            phase="freeze",
            data_root=data_root,
            output_dir=output_dir,
            approve=(spec.factor_id,),
        )


def test_pool_decision_rejects_review_bound_to_another_factor(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path)
    candidates = (_candidate(), _candidate(factor_id="etf18-roc-4"))
    run_factor_mining(
        brief=brief,
        phase="screening",
        data_root=data_root,
        output_dir=output_dir,
        candidates=candidates,
        panel=panel,
    )
    first, second = specs_from_candidates(brief, candidates)
    validation = _load_validation(data_root, brief, first)
    review = ReviewReport(
        report_id=f"rev.{first.factor_id}.{REVIEW_ROLES[0]}",
        role_id=REVIEW_ROLES[0],
        factor_ref=_factor_ref(second),
        evaluation_ref=ObjectRef(
            "EvaluationReport",
            validation.report_id,
            content_hash=validation.content_hash,
            namespace=NAMESPACE,
        ),
        conclusion=ReviewConclusion.PASS,
        issues=(),
        allow_revision=False,
        requires_full_rerun=False,
        provenance=Provenance(
            producer=REVIEW_ROLES[0],
            data_version=brief.data_version,
            code_version="test",
            experiment_version=brief.brief_id,
            namespace=NAMESPACE,
        ),
    )
    _artifact_store(data_root).put_if_absent(
        namespace=NAMESPACE,
        kind="review_report",
        artifact_id=f"{first.factor_id}.{REVIEW_ROLES[0]}",
        payload=to_plain_dict(review),
    )
    compare = _compare(data_root, brief, first)
    with pytest.raises(ValueError, match="review factor reference mismatch"):
        _record_pool(data_root, brief, _pool_decision(brief, first, compare))


def test_final_rejects_mutable_freeze_index_before_claim(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path)
    candidate = _candidate()
    run_factor_mining(
        brief=brief,
        phase="screening",
        data_root=data_root,
        output_dir=output_dir,
        candidates=(candidate,),
        panel=panel,
    )
    spec = specs_from_candidates(brief, (candidate,))[0]
    _put_reviews(data_root, brief, spec, _load_validation(data_root, brief, spec))
    run_factor_mining(
        brief=brief,
        phase="freeze",
        data_root=data_root,
        output_dir=output_dir,
        approve=(spec.factor_id,),
    )
    path = output_dir / "freeze_index.json"
    index = json.loads(path.read_text())
    index["manifests"] = []
    path.write_text(json.dumps(index))
    with pytest.raises(ValueError, match="immutable freeze batch"):
        run_factor_mining(
            brief=brief,
            phase="final",
            data_root=data_root,
            output_dir=output_dir,
            write=True,
            panel=panel,
            candidates=(candidate,),
        )
    assert _event_types(data_root) == set()


def test_final_preflight_failure_does_not_claim_brief(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel = _setup(tmp_path)
    candidate = _candidate()
    run_factor_mining(
        brief=brief,
        phase="screening",
        data_root=data_root,
        output_dir=output_dir,
        candidates=(candidate,),
        panel=panel,
    )
    spec = specs_from_candidates(brief, (candidate,))[0]
    _put_reviews(data_root, brief, spec, _load_validation(data_root, brief, spec))
    run_factor_mining(
        brief=brief,
        phase="freeze",
        data_root=data_root,
        output_dir=output_dir,
        approve=(spec.factor_id,),
    )
    changed = panel.copy()
    research_rows = pd.to_datetime(changed.index.get_level_values("eob")) <= pd.Timestamp(
        VALIDATION_END
    )
    changed.loc[research_rows, "close"] *= 1.01
    with pytest.raises(ValueError, match="data_version mismatch"):
        run_factor_mining(
            brief=brief,
            phase="final",
            data_root=data_root,
            output_dir=output_dir,
            write=True,
            panel=changed,
            candidates=(candidate,),
        )
    assert _event_types(data_root) == set()
    result = run_factor_mining(
        brief=brief,
        phase="final",
        data_root=data_root,
        output_dir=output_dir,
        write=True,
        panel=panel,
        candidates=(candidate,),
    )
    assert result.once_key == brief.content_hash


def test_final_failure_after_claim_consumes_brief(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import strategies.factor_mining.research as workflow

    brief, data_root, output_dir, _panel = _setup(tmp_path)
    candidate = _candidate()
    run_factor_mining(
        brief=brief,
        phase="screening",
        data_root=data_root,
        output_dir=output_dir,
        candidates=(candidate,),
    )
    spec = specs_from_candidates(brief, (candidate,))[0]
    _put_reviews(data_root, brief, spec, _load_validation(data_root, brief, spec))
    run_factor_mining(
        brief=brief,
        phase="freeze",
        data_root=data_root,
        output_dir=output_dir,
        approve=(spec.factor_id,),
    )
    real_load = workflow._load_market_panel

    def fail_after_claim(*args, research_only: bool, **kwargs):
        if not research_only:
            raise RuntimeError("injected sealed read failure")
        return real_load(*args, research_only=research_only, **kwargs)

    monkeypatch.setattr(workflow, "_load_market_panel", fail_after_claim)
    with pytest.raises(RuntimeError, match="injected sealed read failure"):
        run_factor_mining(
            brief=brief,
            phase="final",
            data_root=data_root,
            output_dir=output_dir,
            write=True,
            candidates=(candidate,),
        )
    assert _event_types(data_root) == {UNBLIND_STARTED, UNBLIND_FAILED}
    monkeypatch.setattr(workflow, "_load_market_panel", real_load)
    with pytest.raises(ValueError, match="sealed OOS already started"):
        run_factor_mining(
            brief=brief,
            phase="final",
            data_root=data_root,
            output_dir=output_dir,
            write=True,
            candidates=(candidate,),
        )


def test_drafts_carry_identifiers_and_references_that_record_accepts(tmp_path: Path) -> None:
    """draft -> fill in the judgement -> fill the hash -> record, for all three roles."""
    brief, data_root, output_dir, panel, (spec,) = _screen(tmp_path)

    def draft(role_id: str) -> tuple[dict, dict]:
        result = run_factor_mining(
            brief=brief,
            phase="draft",
            data_root=data_root,
            output_dir=output_dir,
            factor_id=spec.factor_id,
            role_id=role_id,
        )
        payload_path, evidence_path = (Path(item) for item in result.files)
        return json.loads(payload_path.read_text()), json.loads(evidence_path.read_text())

    def record(cls, payload: dict):
        # The bare contract, as `qs factor-mining validate --fill-hash --output` writes it.
        finished = to_plain_dict(rebuild_dataclass(cls, payload))
        assert finished["content_hash"]
        return run_factor_mining(
            brief=brief, phase="record", data_root=data_root, record_object=finished
        )

    with pytest.raises(ValueError, match="run the compare phase first"):
        draft(POOL_ROLE)
    for role_id in REVIEW_ROLES:
        payload, evidence = draft(role_id)
        assert payload["report_id"] == f"rev.{spec.factor_id}.{role_id}"
        assert payload["conclusion"] == "" and payload["content_hash"] == ""
        assert evidence["source_report_id"] == f"eval-eval.{spec.factor_id}__validation"
        assert any(choice.get("fact") == "rank_ic_mean" for choice in evidence["choices"])
        record(ReviewReport, {**payload, "conclusion": "pass", "rationale": "checked"})

    _compare(data_root, brief, spec)
    payload, evidence = draft(POOL_ROLE)
    assert payload["decision_id"] == f"pool.{spec.factor_id}"
    unavailable = next(
        choice["evidence"]
        for choice in evidence["choices"]
        if choice.get("check") == "POOL_UNAVAILABLE"
    )
    accepted = record(
        PoolDecision,
        {
            **payload,
            "decision": "accept",
            "incremental_evidence": [unavailable],
            "residual_risks": ["POOL_INCREMENTAL_UNAVAILABLE"],
        },
    )
    assert accepted.pool_factor_ids == (spec.factor_id,)


def test_draft_rejects_unknown_role_and_unscreened_factor(tmp_path: Path) -> None:
    brief, data_root, output_dir, panel, (spec,) = _screen(tmp_path)
    common = {"brief": brief, "phase": "draft", "data_root": data_root, "output_dir": output_dir}
    with pytest.raises(ValueError, match="draft role must be one of"):
        run_factor_mining(**common, factor_id=spec.factor_id, role_id="supervisor")
    with pytest.raises(ValueError, match="has not been screened"):
        run_factor_mining(**common, factor_id="unknown-v1", role_id=REVIEW_ROLES[0])
