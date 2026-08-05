"""Integration: Phase 01 contracts → panel → Factor → restore → store."""

from __future__ import annotations

import pandas as pd

from skills.factor_mining import (
    FactorComputeRequest,
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
from skills.store.data_manager import DataManager
from tests.fixtures.market_data import make_panel
from tests.skills.factor_mining.builders import make_factor_spec, make_object_ref


def test_phase02_contract_to_store_round_trip(tmp_path) -> None:
    panel = make_panel(("AAA", "BBB"), periods=10)
    # Reversed physical order with custom datetime name.
    panel = panel.copy()
    panel.index = panel.index.reorder_levels(["eob", "symbol"]).set_names(
        ["date", "symbol"]
    )
    snapshot = panel.copy(deep=True)

    spec = make_factor_spec(
        formula=StructuredFormula(
            kind=FormulaKind.FUNCTION_REF,
            function_ref=FunctionRef(
                module="skills.compute.indicators",
                name="roc",
            ),
            params={"period": 2},
        ),
        required_fields=("close",),
        window=2,
        warmup=2,
        content_hash="",
    )
    dm = DataManager(data_root=str(tmp_path))
    store = DataManagerArtifactStore(dm)
    adapter = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: spec,
        resolve_panel=lambda request: panel,
        artifact_store=store,
    )
    request = FactorComputeRequest(
        request_id="integ-1",
        namespace="ns.demo",
        experiment_id="exp-integ",
        execution_id="exec-integ",
        brief_ref=spec.brief_ref,
        factor_ref=make_object_ref(
            object_type="FactorSpec",
            object_id=spec.factor_id,
            content_hash=spec.content_hash,
            namespace=spec.provenance.namespace,
        ),
        data_version="data-v1",
        split_id="train",
    )
    result = adapter.execute(request)
    assert result.failure is None
    assert result.index_schema.datetime_level == "date"
    assert result.index_schema.level_order == (1, 0)
    values = load_execution_series(store, result.values_ref)
    assert values.index.equals(snapshot.index)
    pd.testing.assert_frame_equal(snapshot, panel)

    cache_key = build_factor_cache_key(
        spec_hash=spec.content_hash,
        data_version=request.data_version,
        split_id=request.split_id,
        compute_fingerprint=result.fingerprint,
    )
    path = store.save_factor_pivot(
        namespace=request.namespace,
        cache_key=cache_key,
        values=values,
    )
    assert path.exists()
    loaded = store.read_factor_pivot(namespace=request.namespace, cache_key=cache_key)
    assert loaded is not None
    assert loaded.shape[1] == 2
