"""FactorExecutionAdapter and ArtifactStoreAdapter tests."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from skills.factor_mining import (
    FactorComputeRequest,
    FactorExecutionPort,
    FormulaKind,
    FunctionRef,
    StructuredFormula,
)
from skills.factor_mining.adapters import (
    DataManagerArtifactStore,
    FactorExecutionAdapter,
    build_factor_cache_key,
    load_execution_series,
)
from skills.factor_mining.adapters.store import ArtifactStoreAdapterError
from skills.factor_mining.contracts import FailureCode, ObjectRef
from skills.store.data_manager import DataManager
from tests.fixtures.market_data import make_panel
from tests.skills.factor_mining.builders import make_factor_spec, make_object_ref


def _execution_stack(tmp_path, panel, spec):
    dm = DataManager(data_root=str(tmp_path))
    store = DataManagerArtifactStore(dm)

    def resolve_spec(ref):
        return spec

    def resolve_panel(request):
        return panel

    adapter = FactorExecutionAdapter(
        resolve_factor_spec=resolve_spec,
        resolve_panel=resolve_panel,
        artifact_store=store,
    )
    return adapter, store, dm


def _request_for(spec, *, request_id="req-1", execution_id="exec-1"):
    return FactorComputeRequest(
        request_id=request_id,
        namespace=spec.provenance.namespace,
        experiment_id="exp-1",
        execution_id=execution_id,
        brief_ref=spec.brief_ref,
        factor_ref=make_object_ref(
            object_type="FactorSpec",
            object_id=spec.factor_id,
            content_hash=spec.content_hash,
            namespace=spec.provenance.namespace,
        ),
        data_version=spec.provenance.data_version,
        split_id="validation",
    )


def test_factor_execution_adapter_preserves_panel_lag_and_warmup_nan(tmp_path) -> None:
    panel = make_panel(("AAA", "BBB"), periods=8)
    before = panel.copy(deep=True)
    spec = make_factor_spec(
        formula=StructuredFormula(
            kind=FormulaKind.FUNCTION_REF,
            function_ref=FunctionRef(
                module="skills.compute.indicators",
                name="roc",
            ),
            params={"period": 3},
        ),
        required_fields=("close",),
        window=3,
        warmup=3,
        lag=1,
        content_hash="",
    )
    adapter, store, _dm = _execution_stack(tmp_path, panel, spec)
    port: FactorExecutionPort = adapter
    result = port.execute(_request_for(spec))
    assert result.failure is None
    assert result.values_ref is not None
    pd.testing.assert_frame_equal(before, panel)
    values = load_execution_series(store, result.values_ref)
    assert values.index.equals(panel.index)
    assert values.isna().any()
    payload = store.get(result.values_ref)
    meta = payload["metadata"]
    assert meta["lag"] == 1
    assert meta["missing_policy"] == "keep_nan"
    assert meta["formula_resolver_version"] == "2.0.0"
    assert "start" in meta and "end" in meta
    assert "input_index_schema" in meta and "output_index_schema" in meta


def test_execution_rejects_identity_and_panel_type_mismatches(tmp_path) -> None:
    panel = make_panel(("AAA",), periods=4)
    spec = make_factor_spec(content_hash="")
    dm = DataManager(data_root=str(tmp_path))
    store = DataManagerArtifactStore(dm)

    adapter = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: spec,
        resolve_panel=lambda request: "not-a-dataframe",
        artifact_store=store,
    )
    result = adapter.execute(_request_for(spec, request_id="req-panel"))
    assert result.failure is not None
    assert result.failure.code is FailureCode.INVALID_PANEL_TYPE

    bad_ref_request = FactorComputeRequest(
        request_id="req-hash",
        namespace=spec.provenance.namespace,
        experiment_id="exp-1",
        execution_id="exec-hash",
        brief_ref=spec.brief_ref,
        factor_ref=ObjectRef(
            object_type="FactorSpec",
            object_id=spec.factor_id,
            content_hash="a" * 64,
            namespace=spec.provenance.namespace,
        ),
        data_version=spec.provenance.data_version,
        split_id="validation",
    )
    ok_adapter = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: spec,
        resolve_panel=lambda request: panel,
        artifact_store=store,
    )
    result2 = ok_adapter.execute(bad_ref_request)
    assert result2.failure is not None
    assert result2.failure.code is FailureCode.HASH_MISMATCH

    unsupported = make_factor_spec(missing_policy="drop", content_hash="")
    result3 = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: unsupported,
        resolve_panel=lambda request: panel,
        artifact_store=store,
    ).execute(_request_for(unsupported, request_id="req-policy", execution_id="exec-policy"))
    assert result3.failure is not None
    assert result3.failure.code is FailureCode.INVALID_PARAMETERS


def test_execution_accepts_generated_strategy_function(tmp_path) -> None:
    panel = make_panel(("AAA",), periods=5)
    spec = make_factor_spec(
        formula=StructuredFormula(
            kind=FormulaKind.FUNCTION_REF,
            function_ref=FunctionRef(
                module="strategies.cross_sectional.mined_factors.mean_reversion",
                name="mr_quantile_deviation",
            ),
            params={"period": 3, "q": 0.5},
        ),
        required_fields=("close",),
        window=3,
        warmup=2,
        content_hash="",
    )
    adapter, store, _dm = _execution_stack(tmp_path, panel, spec)
    result = adapter.execute(_request_for(spec, request_id="req-2", execution_id="exec-2"))
    assert result.failure is None
    assert result.values_ref is not None
    values = load_execution_series(store, result.values_ref)
    assert values.index.equals(panel.index)


def test_execution_maps_unresolvable_function_without_leaking_panel_values(tmp_path) -> None:
    panel = make_panel(("AAA",), periods=5)
    spec = make_factor_spec(
        formula=StructuredFormula(
            kind=FormulaKind.FUNCTION_REF,
            function_ref=FunctionRef(module="does.not.exist", name="factor"),
            params={},
        ),
        required_fields=("close",),
        content_hash="",
    )
    adapter, _store, _dm = _execution_stack(tmp_path, panel, spec)
    result = adapter.execute(_request_for(spec, request_id="req-3", execution_id="exec-3"))
    assert result.failure is not None
    assert result.failure.code is FailureCode.INVALID_REFERENCE
    assert result.values_ref is None
    assert "100.0" not in result.failure.message


def test_artifact_store_path_safety_namespaces_and_checksums(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    store = DataManagerArtifactStore(dm)
    ref_a = store.put(
        namespace="ns.a",
        kind="note",
        artifact_id="n1",
        payload={"v": 1},
    )
    ref_b = store.put(
        namespace="ns.b",
        kind="note",
        artifact_id="n1",
        payload={"v": 1},
    )
    assert ref_a.uri != ref_b.uri
    assert store.get(ref_a)["v"] == 1
    with pytest.raises(ArtifactStoreAdapterError):
        store.put(namespace="../escape", kind="note", artifact_id="n1", payload={"v": 1})
    with pytest.raises(ArtifactStoreAdapterError):
        store.put(namespace="/abs", kind="note", artifact_id="n1", payload={"v": 1})
    with pytest.raises(ArtifactStoreAdapterError):
        store.put(
            namespace="ns.a",
            kind="note",
            artifact_id="n2",
            payload={"v": 1},
            input_refs=(
                ObjectRef(
                    object_type="ResearchBrief",
                    object_id="brief-1",
                    content_hash="b" * 64,
                    namespace="other.ns",
                ),
            ),
        )
    bad = ref_a.__class__(
        kind=ref_a.kind,
        artifact_id=ref_a.artifact_id,
        namespace=ref_a.namespace,
        content_hash="a" * 64,
        uri=ref_a.uri,
    )
    with pytest.raises(ArtifactStoreAdapterError):
        store.get(bad)
    path = Path(tmp_path) / "factors" / "ns.a" / "artifacts" / "note" / "n1.json"
    assert path.exists()
    assert path.resolve().is_relative_to((Path(tmp_path) / "factors" / "ns.a").resolve())


def test_artifact_store_rejects_namespace_and_nested_symlinks(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    store = DataManagerArtifactStore(dm)
    factors = Path(tmp_path) / "factors"
    factors.mkdir(parents=True, exist_ok=True)

    outside = Path(tmp_path) / "outside_escape"
    outside.mkdir()
    escape_ns = factors / "escape"
    escape_ns.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactStoreAdapterError, match="namespace escapes"):
        store.put(namespace="escape", kind="note", artifact_id="x", payload={"ok": True})
    assert list(outside.rglob("*")) == []

    # Nested artifact directory symlink escape under a normal namespace.
    ok_ns = factors / "ns.safe"
    ok_ns.mkdir(exist_ok=True)
    artifacts = ok_ns / "artifacts"
    nested_outside = Path(tmp_path) / "nested_outside"
    nested_outside.mkdir()
    artifacts.symlink_to(nested_outside, target_is_directory=True)
    with pytest.raises(ArtifactStoreAdapterError, match="escaped factors root"):
        store.put(namespace="ns.safe", kind="note", artifact_id="y", payload={"ok": True})
    assert list(nested_outside.rglob("*")) == []

    # Normal namespace still works.
    ref = store.put(namespace="ns.ok", kind="note", artifact_id="z", payload={"ok": True})
    assert store.get(ref)["ok"] is True


def test_artifact_store_never_follows_predictable_tmp_symlink(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    store = DataManagerArtifactStore(dm)
    note_dir = Path(tmp_path) / "factors" / "ns" / "artifacts" / "note"
    note_dir.mkdir(parents=True)
    outside = Path(tmp_path) / "outside"
    outside.mkdir()
    victim = outside / "victim.txt"
    victim.write_text("SAFE", encoding="utf-8")
    planted_tmp = note_dir / "x.json.tmp"
    planted_tmp.symlink_to(victim)

    # Put must not follow the planted *.json.tmp symlink. Either success under
    # the namespace or a pre-write rejection is acceptable; victim stays SAFE.
    try:
        ref = store.put(namespace="ns", kind="note", artifact_id="x", payload={"ok": True})
        assert store.get(ref)["ok"] is True
        dest = note_dir / "x.json"
        assert dest.is_file() and not dest.is_symlink()
        assert dest.resolve().is_relative_to((Path(tmp_path) / "factors" / "ns").resolve())
    except ArtifactStoreAdapterError:
        pass
    assert victim.read_text(encoding="utf-8") == "SAFE"
    assert planted_tmp.is_symlink()
    assert list(outside.rglob("*")) == [victim]


def test_artifact_store_rejects_target_file_symlink_escape(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    store = DataManagerArtifactStore(dm)
    note_dir = Path(tmp_path) / "factors" / "ns.target" / "artifacts" / "note"
    note_dir.mkdir(parents=True)
    outside = Path(tmp_path) / "target_outside"
    outside.mkdir()
    victim = outside / "victim.json"
    victim.write_text("SAFE", encoding="utf-8")
    (note_dir / "escape.json").symlink_to(victim)
    with pytest.raises(ArtifactStoreAdapterError):
        store.put(
            namespace="ns.target",
            kind="note",
            artifact_id="escape",
            payload={"ok": True},
        )
    assert victim.read_text(encoding="utf-8") == "SAFE"


def test_cache_key_changes_independently_for_each_component() -> None:
    base = {
        "spec_hash": "a" * 64,
        "data_version": "data-v1",
        "split_id": "validation",
        "compute_fingerprint": "b" * 64,
        "adapter_schema_version": "2.0.0",
    }
    keys = {
        "base": build_factor_cache_key(**base),
        "spec": build_factor_cache_key(**{**base, "spec_hash": "c" * 64}),
        "data": build_factor_cache_key(**{**base, "data_version": "data-v2"}),
        "split": build_factor_cache_key(**{**base, "split_id": "train"}),
        "fp": build_factor_cache_key(**{**base, "compute_fingerprint": "d" * 64}),
        "adapter": build_factor_cache_key(**{**base, "adapter_schema_version": "2.0.1"}),
    }
    assert len(set(keys.values())) == len(keys)


def test_long_wide_round_trip_custom_none_and_missing_inf(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    store = DataManagerArtifactStore(dm)
    idx = pd.MultiIndex.from_arrays(
        [
            pd.Index(["AAA", "BBB", "AAA"], dtype=object),
            pd.Index([None, None, None]),
        ],
        names=["symbol", None],
    )
    # Rebuild with real datetime unnamed level.
    dates = pd.DatetimeIndex(["2024-01-01", "2024-01-01", "2024-01-02"])
    idx = pd.MultiIndex.from_arrays(
        [pd.Index(["AAA", "BBB", "AAA"], dtype=object), dates],
        names=["symbol", None],
    )
    values = pd.Series([1.0, math.inf, float("nan")], index=idx)
    cache_key = "a" * 64
    path = store.save_factor_pivot(namespace="ns.demo", cache_key=cache_key, values=values)
    assert path.exists()
    loaded = store.read_factor_pivot(namespace="ns.demo", cache_key=cache_key)
    assert loaded is not None
    assert "AAA" in loaded.columns
