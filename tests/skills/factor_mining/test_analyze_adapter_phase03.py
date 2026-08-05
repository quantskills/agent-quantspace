"""Adapter-level adversarial checks for Phase 03 round-4/5 identity/pool/issuer."""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from skills.analyze import AnalyzeFacade
from skills.factor_mining import (
    AnalyzeAdapter,
    EvaluationRequest,
    FactorComputeRequest,
    FormulaKind,
    FunctionRef,
    StructuredFormula,
    TypedPoolMember,
)
from skills.factor_mining.adapters import (
    DataManagerArtifactStore,
    FactorExecutionAdapter,
    build_prefix_recompute_capability,
    load_execution_series,
)
from skills.factor_mining.adapters.failure_codes import (
    assert_no_unknown_hard_names,
    map_hard_fail_code,
)
from skills.factor_mining.contracts import FailureCode, content_hash
from skills.store.data_manager import DataManager
from tests.fixtures.market_data import make_panel
from tests.integration.test_factor_mining_phase03_analyze import _protocol_for
from tests.skills.factor_mining.builders import (
    make_brief,
    make_factor_spec,
    make_object_ref,
    make_provenance,
)


def _adapter_stack(
    tmp_path,
    *,
    protocol=None,
    persist=True,
    load_panel=None,
    load_series=None,
    load_pool=None,
    facade=None,
):
    from skills.factor_mining.contracts import TradingConstraints

    panel = make_panel(("AAA", "BBB", "CCC"), periods=24)
    panel = panel.copy()
    panel.index = panel.index.reorder_levels(["eob", "symbol"]).set_names(
        ["date", "symbol"]
    )
    brief = make_brief(
        datetime_level="date",
        timezone="naive",
        horizon_bars=1,
        rebalance="daily",
        universe=("AAA", "BBB", "CCC"),
        trading=TradingConstraints(
            long_only=False,
            allow_short=True,
            rebalance="daily",
            execution_delay_bars=1,
        ),
    )
    spec = make_factor_spec(
        brief=brief,
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
        lag=0,
    )
    proto = protocol or _protocol_for(brief, spec)
    dm = DataManager(data_root=str(tmp_path))
    store = DataManagerArtifactStore(dm)
    persisted = []

    def _persist(key, payload):
        from skills.factor_mining.contracts import ArtifactRef

        ref = ArtifactRef(
            kind="analyze_native",
            artifact_id=key.replace("/", "_"),
            namespace="ns.demo",
            content_hash=content_hash(payload),
            uri=f"mem://{key}",
        )
        persisted.append((ref, payload))
        return ref

    exec_adapter = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: spec,
        resolve_panel=lambda request: panel,
        artifact_store=store,
    )
    compute_req = FactorComputeRequest(
        request_id="p3-exec",
        namespace="ns.demo",
        experiment_id="exp-p3",
        execution_id="exec-p3",
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
    execution = exec_adapter.execute(compute_req)
    assert execution.failure is None

    adapter = AnalyzeAdapter(
        facade=facade or AnalyzeFacade(),
        resolve_brief=lambda ref: brief,
        resolve_factor=lambda ref: spec,
        resolve_protocol=lambda protocol_id: proto,
        resolve_execution=lambda ref: execution,
        load_series=load_series or (lambda ref: load_execution_series(store, ref)),
        load_panel=load_panel or (lambda request: panel),
        load_pool=load_pool,
        persist_artifact=_persist if persist else None,
    )
    eval_req = EvaluationRequest(
        request_id="p3-eval",
        namespace="ns.demo",
        brief_ref=spec.brief_ref,
        factor_ref=make_object_ref(
            object_type="FactorSpec",
            object_id=spec.factor_id,
            content_hash=spec.content_hash,
            namespace=spec.provenance.namespace,
        ),
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id=execution.execution_id,
            content_hash=execution.fingerprint,
            namespace=spec.provenance.namespace,
        ),
        protocol_id="protocol-1",
        data_version="data-v1",
        split_id="train",
    )
    return adapter, eval_req, brief, spec, execution, proto, persisted, panel, store


def test_b4_public_arbitrary_issuer_absent_official_path_works(tmp_path) -> None:
    import skills.analyze.causality as causality

    assert "issue_prefix_recompute_capability" not in causality.__all__
    assert not hasattr(causality, "issue_prefix_recompute_capability")
    adapter, eval_req, _, spec, execution, *_ = _adapter_stack(tmp_path)
    bound = build_prefix_recompute_capability(factor=spec, execution=execution)
    assert bound.spec_content_hash == spec.content_hash
    assert bound.formula_fingerprint == execution.callable_fingerprint
    report = adapter.evaluate(eval_req)
    assert report.failure is None, report.failure


def test_b1_typed_pool_happy_path(tmp_path) -> None:
    adapter, eval_req, _, spec, _, _, _, _, store = _adapter_stack(tmp_path)
    panel = make_panel(("AAA", "BBB", "CCC"), periods=24)
    panel = panel.copy()
    panel.index = panel.index.reorder_levels(["eob", "symbol"]).set_names(
        ["date", "symbol"]
    )
    exec2 = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: spec,
        resolve_panel=lambda request: panel,
        artifact_store=store,
    ).execute(
        FactorComputeRequest(
            request_id="pool-exec",
            namespace="ns.demo",
            experiment_id="exp-pool",
            execution_id="pool-a",
            brief_ref=spec.brief_ref,
            factor_ref=eval_req.factor_ref,
            data_version="data-v1",
            split_id="train",
        )
    )
    assert exec2.failure is None
    pool_values = load_execution_series(store, exec2.values_ref)
    pool_ref = make_object_ref(
        object_type="FactorExecutionResult",
        object_id=exec2.execution_id,
        content_hash=exec2.fingerprint,
        namespace=eval_req.namespace,
    )
    adapter._load_pool = lambda request: [  # type: ignore[method-assign]
        TypedPoolMember(execution=exec2, values=pool_values)
    ]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=eval_req.execution_ref,
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
        pool_refs=(pool_ref,),
    )
    report = adapter.compare_to_pool(req)
    assert report.failure is None, report.failure
    assert any(s.name == "pool_incremental" for s in report.sections)


def test_b1_mapping_loader_rejected(tmp_path) -> None:
    adapter, eval_req, _, _, execution, _, _, _, store = _adapter_stack(tmp_path)
    values = load_execution_series(store, execution.values_ref)
    pool_ref = make_object_ref(
        object_type="FactorExecutionResult",
        object_id="pool-a",
        content_hash="d" * 64,
        namespace=eval_req.namespace,
    )
    adapter._load_pool = lambda request: {"pool-a": values}  # type: ignore[method-assign]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=eval_req.execution_ref,
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
        pool_refs=(pool_ref,),
    )
    report = adapter.compare_to_pool(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE
    assert report.failure.details.get("cause_type") == "mapping_pool_loader_rejected"


def test_b1_typed_pool_wrong_split_fails(tmp_path) -> None:
    adapter, eval_req, _, spec, _, _, _, _, store = _adapter_stack(tmp_path)
    panel = make_panel(("AAA", "BBB", "CCC"), periods=24)
    panel = panel.copy()
    panel.index = panel.index.reorder_levels(["eob", "symbol"]).set_names(
        ["date", "symbol"]
    )
    exec2 = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: spec,
        resolve_panel=lambda request: panel,
        artifact_store=store,
    ).execute(
        FactorComputeRequest(
            request_id="pool-exec",
            namespace="ns.demo",
            experiment_id="exp-pool",
            execution_id="pool-a",
            brief_ref=spec.brief_ref,
            factor_ref=eval_req.factor_ref,
            data_version="data-v1",
            split_id="validation",  # wrong vs request.train
        )
    )
    assert exec2.failure is None
    pool_values = load_execution_series(store, exec2.values_ref)
    pool_ref = make_object_ref(
        object_type="FactorExecutionResult",
        object_id=exec2.execution_id,
        content_hash=exec2.fingerprint,
        namespace=eval_req.namespace,
    )
    adapter._load_pool = lambda request: [  # type: ignore[method-assign]
        TypedPoolMember(execution=exec2, values=pool_values)
    ]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=eval_req.execution_ref,
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
        pool_refs=(pool_ref,),
    )
    report = adapter.compare_to_pool(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_PARAMETERS
    assert "split_id" in str(report.failure.details)


def test_b2_exact_provenance_wrong_refs_fail(tmp_path) -> None:
    adapter, eval_req, brief, spec, execution, *_rest = _adapter_stack(tmp_path)
    from dataclasses import replace

    from skills.factor_mining.adapters.execution_identity import (
        execution_envelope_identity_from_parts,
    )

    wrong_brief = make_object_ref(
        object_type="ResearchBrief",
        object_id="wrong-brief",
        content_hash="b" * 64,
        namespace=eval_req.namespace,
    )
    wrong_factor = make_object_ref(
        object_type="FactorSpec",
        object_id="wrong-factor",
        content_hash="c" * 64,
        namespace=eval_req.namespace,
    )
    forged_prov = make_provenance(
        producer=execution.provenance.producer,
        input_refs=(wrong_brief, wrong_factor),
    )
    # Rebuild envelope with forged provenance but keep request refs for evaluate.
    envelope = execution_envelope_identity_from_parts(
        request_id=execution.request_id,
        experiment_id=execution.experiment_id,
        execution_id=execution.execution_id,
        brief_ref=execution.brief_ref,
        factor_ref=execution.factor_ref,
        values_ref=execution.values_ref,
        valid_mask_ref=execution.valid_mask_ref,
        index_schema=execution.index_schema,
        provenance=forged_prov,
        callable_fingerprint=execution.callable_fingerprint,
        data_version=execution.data_version,
        split_id=execution.split_id,
        values_content_hash=execution.values_content_hash,
        valid_mask_content_hash=execution.valid_mask_content_hash,
    )
    forged_exec = replace(
        execution,
        provenance=forged_prov,
        fingerprint=envelope,
    )
    adapter._resolve_execution = lambda ref: forged_exec  # type: ignore[method-assign]
    forged_req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id=forged_exec.execution_id,
            content_hash=forged_exec.fingerprint,
            namespace=eval_req.namespace,
        ),
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
    )
    report = adapter.evaluate(forged_req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE
    assert "exact" in report.failure.message


def test_b5_facade_exceptions_structured(tmp_path) -> None:
    class BoomFacade(AnalyzeFacade):
        def preflight(self, *args, **kwargs):
            raise RuntimeError("preflight secret")

        def evaluate(self, *args, **kwargs):
            raise RuntimeError("evaluate secret")

        def compare_to_pool(self, *args, **kwargs):
            raise RuntimeError("compare secret")

    adapter, eval_req, *_ = _adapter_stack(tmp_path, facade=BoomFacade())
    pf = adapter.preflight(eval_req)
    assert pf.failure is not None
    assert pf.failure.details.get("cause_type") == "RuntimeError"
    assert "secret" not in pf.failure.message

    ev = adapter.evaluate(eval_req)
    assert ev.failure is not None
    assert ev.failure.details.get("cause_type") == "RuntimeError"
    assert "secret" not in str(ev.failure.details)

    # Mapping path also covers compare facade catch once pool binds;
    # empty pool still hits facade.
    cp = adapter.compare_to_pool(eval_req)
    assert cp.failure is not None
    assert cp.failure.details.get("cause_type") == "RuntimeError"


def test_p0_3_wrong_execution_object_id_fails(tmp_path) -> None:
    adapter, eval_req, _, _, execution, _, _, _, _ = _adapter_stack(tmp_path)
    forged = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id="totally-wrong-id",
            content_hash=execution.fingerprint,
            namespace=eval_req.namespace,
        ),
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
    )
    report = adapter.evaluate(forged)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE
    assert "execution_id" in report.failure.message


def test_p1_6_load_series_runtimeerror_structured(tmp_path) -> None:
    def boom(ref):
        raise RuntimeError("secret internals must not leak")

    adapter, eval_req, *_ = _adapter_stack(tmp_path, load_series=boom)
    report = adapter.evaluate(eval_req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE
    assert report.failure.details.get("cause_type") == "RuntimeError"
    assert "secret" not in report.failure.message


def test_p1_7_wrong_namespace_persist_mapping_loss_no_raise(tmp_path) -> None:
    adapter, eval_req, *_ = _adapter_stack(tmp_path)

    def bad_persist(key, payload):
        from skills.factor_mining.contracts import ArtifactRef

        return ArtifactRef(
            kind="analyze_native",
            artifact_id="x",
            namespace="wrong.ns",
            content_hash=content_hash(payload),
            uri="mem://x",
        )

    adapter._persist_artifact = bad_persist  # type: ignore[method-assign]
    report = adapter.evaluate(eval_req)
    assert report.failure is None, report.failure
    loss_checks = [
        c
        for s in report.sections
        for c in s.checks
        if c.name == "ADAPTER_MAPPING_LOSS"
    ]
    assert loss_checks
    assert loss_checks[0].evidence is not None
    assert loss_checks[0].evidence.artifact is None


def _const_finding_severity(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute) and node.attr in {
        "HARD_FAIL",
        "SOFT_FAIL",
        "INFO",
        "WARNING",
    }:
        return node.attr
    return None


def _const_bool_ast(node: ast.AST) -> bool | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return None


def _call_func_name(node: ast.Call) -> str | None:
    """Return bare or qualified Finding/_finding name, else None."""
    func = node.func
    if isinstance(func, ast.Name) and func.id in {"_finding", "Finding"}:
        return func.id
    if isinstance(func, ast.Attribute) and func.attr in {"_finding", "Finding"}:
        return func.attr
    return None


def _extract_hard_capable_finding_names(
    tree: ast.AST,
) -> tuple[set[str], list[str]]:
    """Collect hard-capable Finding/_finding names; list unresolved dynamics.

    ``Finding`` positional order: name, severity, passed, message.
    ``_finding``: name positional or keyword; severity/passed keyword-only.
    Supports qualified ``*.Finding`` / ``*._finding``. Dynamic/variable/f-string
    names are unresolved (tests must fail). ``from ... import Finding as F`` and
    ``F = Finding`` / ``F = *.Finding`` rebinds are unresolved (must not be
    silently missed). The ``Finding(name=name, ...)`` body inside a local
    ``def _finding`` factory is a passthrough wrapper and is ignored (not a
    production code site). No registry / name / suffix pre-filter.
    """
    hard_capable: set[str] = set()
    unresolved: list[str] = []
    finding_ids = {"Finding", "_finding"}

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._fn_stack: list[str | None] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._fn_stack.append(node.name)
            self.generic_visit(node)
            self._fn_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._fn_stack.append(node.name)
            self.generic_visit(node)
            self._fn_stack.pop()

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            for alias in node.names:
                if alias.name in finding_ids and alias.asname is not None:
                    unresolved.append(ast.dump(node, include_attributes=False))
                    break
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            value = node.value
            is_finding_rhs = (
                isinstance(value, ast.Name) and value.id in finding_ids
            ) or (
                isinstance(value, ast.Attribute) and value.attr in finding_ids
            )
            if is_finding_rhs:
                unresolved.append(ast.dump(node, include_attributes=False))
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            value = node.value
            if value is not None:
                is_finding_rhs = (
                    isinstance(value, ast.Name) and value.id in finding_ids
                ) or (
                    isinstance(value, ast.Attribute) and value.attr in finding_ids
                )
                if is_finding_rhs:
                    unresolved.append(ast.dump(node, include_attributes=False))
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            func_id = _call_func_name(node)
            if func_id is None:
                self.generic_visit(node)
                return
            # Passthrough factory body: def _finding(...): return Finding(name=name, ...)
            if (
                func_id == "Finding"
                and self._fn_stack
                and self._fn_stack[-1] == "_finding"
            ):
                self.generic_visit(node)
                return

            name_val: str | None = None
            name_dynamic = False
            passed_const: bool | None = None
            sev_const: str | None = None
            sev_dynamic = False

            if func_id == "Finding":
                if len(node.args) >= 1:
                    if (
                        isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    ):
                        name_val = node.args[0].value
                    else:
                        name_dynamic = True
                if len(node.args) >= 2:
                    sev_pos = _const_finding_severity(node.args[1])
                    if sev_pos is not None:
                        sev_const = sev_pos
                    else:
                        sev_dynamic = True
                if len(node.args) >= 3:
                    passed_const = _const_bool_ast(node.args[2])
            else:
                if node.args:
                    if (
                        isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    ):
                        name_val = node.args[0].value
                    else:
                        name_dynamic = True

            for kw in node.keywords or []:
                if kw.arg == "name":
                    if (
                        isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, str)
                    ):
                        name_val = kw.value.value
                        name_dynamic = False
                    else:
                        name_dynamic = True
                        name_val = None
                elif kw.arg == "passed":
                    passed_const = _const_bool_ast(kw.value)
                elif kw.arg == "severity":
                    sev_kw = _const_finding_severity(kw.value)
                    if sev_kw is not None:
                        sev_const = sev_kw
                        sev_dynamic = False
                    else:
                        sev_dynamic = True
                        sev_const = None

            if name_dynamic or not isinstance(name_val, str):
                unresolved.append(ast.dump(node, include_attributes=False))
            elif passed_const is True or sev_const in {"INFO", "SOFT_FAIL", "WARNING"}:
                pass
            elif (
                (sev_const is None and not sev_dynamic)
                or sev_const == "HARD_FAIL"
                or (sev_dynamic and passed_const is not True)
            ):
                hard_capable.add(name_val)
            self.generic_visit(node)

    Visitor().visit(tree)
    return hard_capable, unresolved


def test_d3_ast_extract_positional_finding_signatures() -> None:
    """Synthetic AST: Finding positional severity/passed must be honored."""
    source = '''
Finding("POS_PASSED_TRUE", FindingSeverity.HARD_FAIL, True, "ok")
Finding("POS_INFO", FindingSeverity.INFO, False, "info")
Finding("POS_SOFT", FindingSeverity.SOFT_FAIL, False, "soft")
Finding("POS_HARD_FAIL", FindingSeverity.HARD_FAIL, False, "hard")
Finding("POS_DYNAMIC_SEV", dyn_sev, False, "dyn")
Finding("POS_DYNAMIC_PASSED_TRUE", FindingSeverity.HARD_FAIL, dyn_passed, "x")
_finding("KW_PASSED_TRUE", passed=True, message="ok")
_finding("KW_INFO", passed=False, message="i", severity=FindingSeverity.INFO)
_finding("KW_HARD", passed=False, message="h")
_finding("KW_DYNAMIC_SEV", passed=False, message="d", severity=dyn_sev)
mod.Finding("QUAL_HARD", FindingSeverity.HARD_FAIL, False, "q")
'''
    names, unresolved = _extract_hard_capable_finding_names(ast.parse(source))
    assert unresolved == []
    assert "POS_PASSED_TRUE" not in names
    assert "POS_INFO" not in names
    assert "POS_SOFT" not in names
    assert "KW_PASSED_TRUE" not in names
    assert "KW_INFO" not in names
    assert "POS_HARD_FAIL" in names
    assert "POS_DYNAMIC_SEV" in names
    assert "KW_HARD" in names
    assert "KW_DYNAMIC_SEV" in names
    assert "QUAL_HARD" in names
    assert "POS_DYNAMIC_PASSED_TRUE" in names


def test_e3_ast_dynamic_name_and_qualified_unresolved() -> None:
    """Dynamic/f-string Finding names must be unresolved; qualified still scanned."""
    dynamic_src = '''
Finding(dyn_name, FindingSeverity.HARD_FAIL, False, "x")
_finding(f"ROBUSTNESS_{label}", passed=False, message="x")
'''
    _names, unresolved = _extract_hard_capable_finding_names(ast.parse(dynamic_src))
    assert len(unresolved) == 2
    qual_src = '''
pkg.mod.Finding("QUALIFIED_HARD", FindingSeverity.HARD_FAIL, False, "ok")
'''
    names, unresolved2 = _extract_hard_capable_finding_names(ast.parse(qual_src))
    assert unresolved2 == []
    assert "QUALIFIED_HARD" in names


def test_f4_ast_import_alias_and_assign_unresolved() -> None:
    """Import alias / Assign rebinds of Finding must be unresolved, not silent."""
    import_src = '''
from skills.analyze.contracts import Finding as F
F("ALIASED_HARD", FindingSeverity.HARD_FAIL, False, "x")
'''
    _names, unresolved_import = _extract_hard_capable_finding_names(ast.parse(import_src))
    assert any("ImportFrom" in u for u in unresolved_import), unresolved_import

    assign_src = '''
Finding = object
F = Finding
G = mod.Finding
F("ASSIGN_HARD", FindingSeverity.HARD_FAIL, False, "x")
'''
    _names2, unresolved_assign = _extract_hard_capable_finding_names(ast.parse(assign_src))
    assert len(unresolved_assign) >= 2
    assert any("Assign" in u for u in unresolved_assign), unresolved_assign

    # Legitimate _finding passthrough factory still ignored.
    wrapper_src = '''
def _finding(name, *, passed, message, severity=FindingSeverity.HARD_FAIL, details=None):
    return Finding(name=name, severity=severity, passed=passed, message=message, details=details or {})
_finding("WRAP_HARD", passed=False, message="h")
'''
    names3, unresolved3 = _extract_hard_capable_finding_names(ast.parse(wrapper_src))
    assert unresolved3 == []
    assert "WRAP_HARD" in names3


def test_r2_11_failure_registry_hard_capable_scan() -> None:
    """Hard-capable Finding/_finding callsites must map non-UNKNOWN; SKIPPED never root.

    Rules (no registry self-filter of candidates):
    - direct and qualified ``_finding`` / ``Finding`` calls
    - Finding positional: name, severity, passed, message
    - dynamic/variable/f-string names fail the scan (unresolved)
    - ``from ... import Finding as F`` and ``F = Finding`` / ``F = *.Finding``
      rebinds are unresolved (must not be silently missed)
    - exclude ``passed=True`` constant (cannot be hard failure)
    - exclude explicit constant INFO / SOFT_FAIL / WARNING severity
    - include default severity (HARD), explicit HARD, or dynamic severity when
      ``passed`` is not constantly True
    """
    root = Path(__file__).resolve().parents[3] / "skills" / "analyze"
    hard_capable: set[str] = set()
    unresolved: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names, bad = _extract_hard_capable_finding_names(tree)
        hard_capable |= names
        unresolved.extend(f"{path}:{u}" for u in bad)

    assert unresolved == [], unresolved
    assert hard_capable
    unknown = assert_no_unknown_hard_names(sorted(hard_capable))
    assert unknown == [], unknown
    for skipped in (
        "ALIGNMENT_SKIPPED",
        "EVALUATION_SKIPPED",
        "ROBUSTNESS_SKIPPED",
        "BACKTEST_SKIPPED",
        "POOL_SKIPPED",
    ):
        probe = type(
            "P",
            (),
            {
                "name": skipped,
                "passed": False,
                "severity": type("S", (), {"value": "hard_fail"})(),
            },
        )()
        assert map_hard_fail_code(probe) is not FailureCode.UNKNOWN


def _make_pool_execution(tmp_path_store, spec, eval_req, *, execution_id="pool-a", split_id="train", data_version="data-v1"):
    panel = make_panel(("AAA", "BBB", "CCC"), periods=24)
    panel = panel.copy()
    panel.index = panel.index.reorder_levels(["eob", "symbol"]).set_names(
        ["date", "symbol"]
    )
    exec2 = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: spec,
        resolve_panel=lambda request: panel,
        artifact_store=tmp_path_store,
    ).execute(
        FactorComputeRequest(
            request_id="pool-exec",
            namespace="ns.demo",
            experiment_id="exp-pool",
            execution_id=execution_id,
            brief_ref=spec.brief_ref,
            factor_ref=eval_req.factor_ref,
            data_version=data_version,
            split_id=split_id,
        )
    )
    assert exec2.failure is None
    return exec2


def test_c1_adapter_preflight_official_compiled_capability_succeeds(tmp_path) -> None:
    adapter, eval_req, _, spec, _, proto, _, panel, store = _adapter_stack(tmp_path)
    report = adapter.preflight(eval_req)
    assert report.failure is None, report.failure
    # End-to-end: preflight → execute → evaluate
    exec_adapter = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: spec,
        resolve_panel=lambda request: panel,
        artifact_store=store,
    )
    execution = exec_adapter.execute(
        FactorComputeRequest(
            request_id="e2e-exec",
            namespace="ns.demo",
            experiment_id="exp-e2e",
            execution_id="exec-e2e",
            brief_ref=eval_req.brief_ref,
            factor_ref=eval_req.factor_ref,
            data_version="data-v1",
            split_id="train",
        )
    )
    assert execution.failure is None
    adapter._resolve_execution = lambda ref: execution  # type: ignore[method-assign]
    eval_req2 = EvaluationRequest(
        request_id="e2e-eval",
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id=execution.execution_id,
            content_hash=execution.fingerprint,
            namespace=eval_req.namespace,
        ),
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
    )
    report2 = adapter.evaluate(eval_req2)
    assert report2.failure is None, report2.failure


def test_c2_forged_pool_values_rejected(tmp_path) -> None:
    adapter, eval_req, _, spec, _, _, _, _, store = _adapter_stack(tmp_path)
    exec2 = _make_pool_execution(store, spec, eval_req)
    authentic = load_execution_series(store, exec2.values_ref)
    forged = pd.Series(777.0, index=authentic.index, dtype="float64")
    pool_ref = make_object_ref(
        object_type="FactorExecutionResult",
        object_id=exec2.execution_id,
        content_hash=exec2.fingerprint,
        namespace=eval_req.namespace,
    )
    adapter._load_pool = lambda request: [  # type: ignore[method-assign]
        TypedPoolMember(execution=exec2, values=forged)
    ]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=eval_req.execution_ref,
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
        pool_refs=(pool_ref,),
    )
    report = adapter.compare_to_pool(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.HASH_MISMATCH


def test_c2_authentic_pool_values_accepted(tmp_path) -> None:
    adapter, eval_req, _, spec, _, _, _, _, store = _adapter_stack(tmp_path)
    exec2 = _make_pool_execution(store, spec, eval_req)
    authentic = load_execution_series(store, exec2.values_ref)
    pool_ref = make_object_ref(
        object_type="FactorExecutionResult",
        object_id=exec2.execution_id,
        content_hash=exec2.fingerprint,
        namespace=eval_req.namespace,
    )
    adapter._load_pool = lambda request: [  # type: ignore[method-assign]
        TypedPoolMember(execution=exec2, values=authentic)
    ]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=eval_req.execution_ref,
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
        pool_refs=(pool_ref,),
    )
    report = adapter.compare_to_pool(req)
    assert report.failure is None, report.failure


def test_c2_load_series_wrong_values_rejected(tmp_path) -> None:
    adapter, eval_req, _, _, execution, _, _, _, store = _adapter_stack(tmp_path)
    authentic = load_execution_series(store, execution.values_ref)
    mask = load_execution_series(store, execution.valid_mask_ref)
    forged = pd.Series(777.0, index=authentic.index, dtype="float64")

    def bad_load(ref):
        if ref.kind == "factor_values":
            return forged
        return mask

    adapter._load_series = bad_load  # type: ignore[method-assign]
    report = adapter.evaluate(eval_req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.HASH_MISMATCH


def test_c2_load_series_wrong_mask_rejected(tmp_path) -> None:
    adapter, eval_req, _, _, execution, _, _, _, store = _adapter_stack(tmp_path)
    authentic = load_execution_series(store, execution.values_ref)
    mask = load_execution_series(store, execution.valid_mask_ref)
    forged_mask = pd.Series(False, index=mask.index, dtype=bool)

    def bad_load(ref):
        if ref.kind == "valid_mask":
            return forged_mask
        return authentic

    adapter._load_series = bad_load  # type: ignore[method-assign]
    report = adapter.evaluate(eval_req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.HASH_MISMATCH


def test_c2_envelope_tamper_hash_rejected(tmp_path) -> None:
    from dataclasses import replace

    adapter, eval_req, _, _, execution, *_ = _adapter_stack(tmp_path)
    tampered = replace(execution, fingerprint="0" * 64)
    adapter._resolve_execution = lambda ref: tampered  # type: ignore[method-assign]
    forged_req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id=tampered.execution_id,
            content_hash=tampered.fingerprint,
            namespace=eval_req.namespace,
        ),
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
    )
    report = adapter.evaluate(forged_req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.HASH_MISMATCH


def test_c2_values_ref_wrong_kind_rejected(tmp_path) -> None:
    from dataclasses import replace

    from skills.factor_mining.adapters.execution_identity import (
        execution_envelope_identity_from_parts,
    )
    from skills.factor_mining.contracts import ArtifactRef

    adapter, eval_req, _, _, execution, *_ = _adapter_stack(tmp_path)
    bad_ref = ArtifactRef(
        kind="not_factor_values",
        artifact_id=execution.values_ref.artifact_id,
        namespace=execution.values_ref.namespace,
        content_hash=execution.values_ref.content_hash,
        uri=execution.values_ref.uri,
    )
    envelope = execution_envelope_identity_from_parts(
        request_id=execution.request_id,
        experiment_id=execution.experiment_id,
        execution_id=execution.execution_id,
        brief_ref=execution.brief_ref,
        factor_ref=execution.factor_ref,
        values_ref=bad_ref,
        valid_mask_ref=execution.valid_mask_ref,
        index_schema=execution.index_schema,
        provenance=execution.provenance,
        callable_fingerprint=execution.callable_fingerprint,
        data_version=execution.data_version,
        split_id=execution.split_id,
        values_content_hash=execution.values_content_hash,
        valid_mask_content_hash=execution.valid_mask_content_hash,
    )
    forged = replace(execution, values_ref=bad_ref, fingerprint=envelope)
    adapter._resolve_execution = lambda ref: forged  # type: ignore[method-assign]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id=forged.execution_id,
            content_hash=forged.fingerprint,
            namespace=eval_req.namespace,
        ),
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
    )
    report = adapter.evaluate(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE


def _forge_values_ref(execution, **overrides):
    from dataclasses import replace

    from skills.factor_mining.adapters.execution_identity import (
        execution_envelope_identity_from_parts,
    )
    from skills.factor_mining.contracts import SCHEMA_VERSION, ArtifactRef

    assert execution.values_ref is not None
    schema_override = overrides.pop("schema_version", None)
    namespace_override = overrides.pop("namespace", None)
    base = {
        "kind": execution.values_ref.kind,
        "artifact_id": execution.values_ref.artifact_id,
        "namespace": execution.values_ref.namespace,
        "content_hash": execution.values_ref.content_hash,
        "uri": execution.values_ref.uri,
        "schema_version": SCHEMA_VERSION,
    }
    base.update(overrides)
    bad_ref = ArtifactRef(**base)
    if schema_override is not None:
        object.__setattr__(bad_ref, "schema_version", schema_override)
    if namespace_override is not None:
        object.__setattr__(bad_ref, "namespace", namespace_override)
    envelope = execution_envelope_identity_from_parts(
        request_id=execution.request_id,
        experiment_id=execution.experiment_id,
        execution_id=execution.execution_id,
        brief_ref=execution.brief_ref,
        factor_ref=execution.factor_ref,
        values_ref=bad_ref,
        valid_mask_ref=execution.valid_mask_ref,
        index_schema=execution.index_schema,
        provenance=execution.provenance,
        callable_fingerprint=execution.callable_fingerprint,
        data_version=execution.data_version,
        split_id=execution.split_id,
        values_content_hash=execution.values_content_hash,
        valid_mask_content_hash=execution.valid_mask_content_hash,
    )
    # Contract __post_init__ rejects namespace-mismatched refs; bypass so the
    # adapter path can surface INVALID_REFERENCE.
    forged = replace(execution, fingerprint=envelope)
    object.__setattr__(forged, "values_ref", bad_ref)
    return forged


def test_c2_values_ref_wrong_id_rejected(tmp_path) -> None:
    adapter, eval_req, _, _, execution, *_ = _adapter_stack(tmp_path)
    forged = _forge_values_ref(execution, artifact_id="wrong-id:values")
    adapter._resolve_execution = lambda ref: forged  # type: ignore[method-assign]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id=forged.execution_id,
            content_hash=forged.fingerprint,
            namespace=eval_req.namespace,
        ),
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
    )
    report = adapter.evaluate(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE


def test_c2_values_ref_wrong_hash_rejected(tmp_path) -> None:
    adapter, eval_req, _, _, execution, *_ = _adapter_stack(tmp_path)
    forged = _forge_values_ref(execution, content_hash="0" * 64)
    adapter._resolve_execution = lambda ref: forged  # type: ignore[method-assign]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id=forged.execution_id,
            content_hash=forged.fingerprint,
            namespace=eval_req.namespace,
        ),
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
    )
    report = adapter.evaluate(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.HASH_MISMATCH


def test_c2_values_ref_wrong_namespace_rejected(tmp_path) -> None:
    adapter, eval_req, _, _, execution, *_ = _adapter_stack(tmp_path)
    forged = _forge_values_ref(execution, namespace="ns.other")
    adapter._resolve_execution = lambda ref: forged  # type: ignore[method-assign]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id=forged.execution_id,
            content_hash=forged.fingerprint,
            namespace=eval_req.namespace,
        ),
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
    )
    report = adapter.evaluate(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE


def test_c2_values_ref_wrong_schema_rejected(tmp_path) -> None:
    adapter, eval_req, _, _, execution, *_ = _adapter_stack(tmp_path)
    forged = _forge_values_ref(execution, schema_version="9.9.9")
    adapter._resolve_execution = lambda ref: forged  # type: ignore[method-assign]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id=forged.execution_id,
            content_hash=forged.fingerprint,
            namespace=eval_req.namespace,
        ),
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
    )
    report = adapter.evaluate(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.SCHEMA_MISMATCH


def test_c4_pool_wrong_brief_ref_rejected(tmp_path) -> None:
    """Provenance ResearchBrief must exact-match execution.brief_ref (all fields).

    Pool brief_ref must also equal request.brief_ref; this adversary keeps
    first-class brief_ref authentic but forges provenance to a wrong brief.
    """
    from dataclasses import replace

    from skills.factor_mining.adapters.execution_identity import (
        execution_envelope_identity_from_parts,
    )

    adapter, eval_req, _, spec, _, _, _, _, store = _adapter_stack(tmp_path)
    exec2 = _make_pool_execution(store, spec, eval_req)
    authentic = load_execution_series(store, exec2.values_ref)
    wrong_brief = make_object_ref(
        object_type="ResearchBrief",
        object_id="wrong-brief-id",
        content_hash="e" * 64,
        namespace=eval_req.namespace,
    )
    # Keep first-class execution.brief_ref; forge provenance to a wrong brief.
    forged_prov = make_provenance(
        producer=exec2.provenance.producer,
        input_refs=(wrong_brief, exec2.factor_ref),
    )
    envelope = execution_envelope_identity_from_parts(
        request_id=exec2.request_id,
        experiment_id=exec2.experiment_id,
        execution_id=exec2.execution_id,
        brief_ref=exec2.brief_ref,
        factor_ref=exec2.factor_ref,
        values_ref=exec2.values_ref,
        valid_mask_ref=exec2.valid_mask_ref,
        index_schema=exec2.index_schema,
        provenance=forged_prov,
        callable_fingerprint=exec2.callable_fingerprint,
        data_version=exec2.data_version,
        split_id=exec2.split_id,
        values_content_hash=exec2.values_content_hash,
        valid_mask_content_hash=exec2.valid_mask_content_hash,
    )
    forged_exec = replace(exec2, provenance=forged_prov, fingerprint=envelope)
    pool_ref = make_object_ref(
        object_type="FactorExecutionResult",
        object_id=forged_exec.execution_id,
        content_hash=forged_exec.fingerprint,
        namespace=eval_req.namespace,
    )
    adapter._load_pool = lambda request: [  # type: ignore[method-assign]
        TypedPoolMember(execution=forged_exec, values=authentic)
    ]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=eval_req.execution_ref,
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
        pool_refs=(pool_ref,),
    )
    report = adapter.compare_to_pool(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE
    assert "brief_ref" in str(report.failure.details)


def test_d1_pool_attacker_brief_ref_and_provenance_rejected(tmp_path) -> None:
    """Consistent attacker brief on execution.brief_ref + provenance must fail.

    Pool factor_ref may differ from the candidate; brief_ref must still
    exact-equal request.brief_ref on all ObjectRef fields.
    """
    from dataclasses import replace

    from skills.factor_mining.adapters.execution_identity import (
        execution_envelope_identity_from_parts,
    )

    adapter, eval_req, _, spec, _, _, _, _, store = _adapter_stack(tmp_path)
    exec2 = _make_pool_execution(store, spec, eval_req)
    authentic = load_execution_series(store, exec2.values_ref)
    attacker_brief = make_object_ref(
        object_type="ResearchBrief",
        object_id="attacker-brief",
        content_hash="a" * 64,
        namespace=eval_req.namespace,
    )
    other_factor = make_object_ref(
        object_type="FactorSpec",
        object_id="pool-other-factor",
        content_hash="b" * 64,
        namespace=eval_req.namespace,
    )
    forged_prov = make_provenance(
        producer=exec2.provenance.producer,
        input_refs=(attacker_brief, other_factor),
    )
    envelope = execution_envelope_identity_from_parts(
        request_id=exec2.request_id,
        experiment_id=exec2.experiment_id,
        execution_id=exec2.execution_id,
        brief_ref=attacker_brief,
        factor_ref=other_factor,
        values_ref=exec2.values_ref,
        valid_mask_ref=exec2.valid_mask_ref,
        index_schema=exec2.index_schema,
        provenance=forged_prov,
        callable_fingerprint=exec2.callable_fingerprint,
        data_version=exec2.data_version,
        split_id=exec2.split_id,
        values_content_hash=exec2.values_content_hash,
        valid_mask_content_hash=exec2.valid_mask_content_hash,
    )
    forged_exec = replace(
        exec2,
        brief_ref=attacker_brief,
        factor_ref=other_factor,
        provenance=forged_prov,
        fingerprint=envelope,
    )
    pool_ref = make_object_ref(
        object_type="FactorExecutionResult",
        object_id=forged_exec.execution_id,
        content_hash=forged_exec.fingerprint,
        namespace=eval_req.namespace,
    )
    adapter._load_pool = lambda request: [  # type: ignore[method-assign]
        TypedPoolMember(execution=forged_exec, values=authentic)
    ]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=eval_req.execution_ref,
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
        pool_refs=(pool_ref,),
    )
    report = adapter.compare_to_pool(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE
    assert "brief_ref" in str(report.failure.details)


def test_d2_compare_to_pool_forged_candidate_values_hash_mismatch(tmp_path) -> None:
    adapter, eval_req, _, spec, execution, _, _, _, store = _adapter_stack(tmp_path)
    pool_exec = _make_pool_execution(store, spec, eval_req)
    pool_values = load_execution_series(store, pool_exec.values_ref)
    authentic_cand = load_execution_series(store, execution.values_ref)
    forged_cand = pd.Series(777.0, index=authentic_cand.index, dtype="float64")

    def bad_load(ref):
        if (
            ref.kind == "factor_values"
            and ref.artifact_id == execution.values_ref.artifact_id
        ):
            return forged_cand
        return load_execution_series(store, ref)

    adapter._load_series = bad_load  # type: ignore[method-assign]
    adapter._load_pool = lambda request: [  # type: ignore[method-assign]
        TypedPoolMember(execution=pool_exec, values=pool_values)
    ]
    pool_ref = make_object_ref(
        object_type="FactorExecutionResult",
        object_id=pool_exec.execution_id,
        content_hash=pool_exec.fingerprint,
        namespace=eval_req.namespace,
    )
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=eval_req.execution_ref,
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
        pool_refs=(pool_ref,),
    )
    report = adapter.compare_to_pool(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.HASH_MISMATCH


def test_d2_compare_to_pool_load_series_code_passthrough(tmp_path) -> None:
    from skills.factor_mining.adapters.store import ArtifactStoreAdapterError

    adapter, eval_req, *_ = _adapter_stack(tmp_path)

    def boom(_ref):
        raise ArtifactStoreAdapterError(
            FailureCode.HASH_MISMATCH, "artifact content_hash mismatch"
        )

    adapter._load_series = boom  # type: ignore[method-assign]
    report = adapter.compare_to_pool(eval_req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.HASH_MISMATCH


def test_c4_pool_wrong_factor_ref_provenance_rejected(tmp_path) -> None:
    from dataclasses import replace

    from skills.factor_mining.adapters.execution_identity import (
        execution_envelope_identity_from_parts,
    )

    adapter, eval_req, _, spec, _, _, _, _, store = _adapter_stack(tmp_path)
    exec2 = _make_pool_execution(store, spec, eval_req)
    authentic = load_execution_series(store, exec2.values_ref)
    wrong_factor = make_object_ref(
        object_type="FactorSpec",
        object_id="wrong-factor",
        content_hash="f" * 64,
        namespace=eval_req.namespace,
    )
    forged_prov = make_provenance(
        producer=exec2.provenance.producer,
        input_refs=(exec2.brief_ref, wrong_factor),
    )
    envelope = execution_envelope_identity_from_parts(
        request_id=exec2.request_id,
        experiment_id=exec2.experiment_id,
        execution_id=exec2.execution_id,
        brief_ref=exec2.brief_ref,
        factor_ref=exec2.factor_ref,
        values_ref=exec2.values_ref,
        valid_mask_ref=exec2.valid_mask_ref,
        index_schema=exec2.index_schema,
        provenance=forged_prov,
        callable_fingerprint=exec2.callable_fingerprint,
        data_version=exec2.data_version,
        split_id=exec2.split_id,
        values_content_hash=exec2.values_content_hash,
        valid_mask_content_hash=exec2.valid_mask_content_hash,
    )
    forged_exec = replace(exec2, provenance=forged_prov, fingerprint=envelope)
    pool_ref = make_object_ref(
        object_type="FactorExecutionResult",
        object_id=forged_exec.execution_id,
        content_hash=forged_exec.fingerprint,
        namespace=eval_req.namespace,
    )
    adapter._load_pool = lambda request: [  # type: ignore[method-assign]
        TypedPoolMember(execution=forged_exec, values=authentic)
    ]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=eval_req.execution_ref,
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
        pool_refs=(pool_ref,),
    )
    report = adapter.compare_to_pool(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE


def test_c2_pool_wrong_data_version_hash_mismatch(tmp_path) -> None:
    from dataclasses import replace

    from skills.factor_mining.adapters.execution_identity import (
        execution_envelope_identity_from_parts,
    )

    adapter, eval_req, _, spec, _, _, _, _, store = _adapter_stack(tmp_path)
    exec_ok = _make_pool_execution(store, spec, eval_req, execution_id="pool-dv")
    authentic = load_execution_series(store, exec_ok.values_ref)
    forged_prov = replace(exec_ok.provenance, data_version="data-other")
    envelope = execution_envelope_identity_from_parts(
        request_id=exec_ok.request_id,
        experiment_id=exec_ok.experiment_id,
        execution_id=exec_ok.execution_id,
        brief_ref=exec_ok.brief_ref,
        factor_ref=exec_ok.factor_ref,
        values_ref=exec_ok.values_ref,
        valid_mask_ref=exec_ok.valid_mask_ref,
        index_schema=exec_ok.index_schema,
        provenance=forged_prov,
        callable_fingerprint=exec_ok.callable_fingerprint,
        data_version="data-other",
        split_id=exec_ok.split_id,
        values_content_hash=exec_ok.values_content_hash,
        valid_mask_content_hash=exec_ok.valid_mask_content_hash,
    )
    forged = replace(
        exec_ok,
        data_version="data-other",
        provenance=forged_prov,
        fingerprint=envelope,
    )
    pool_ref = make_object_ref(
        object_type="FactorExecutionResult",
        object_id=forged.execution_id,
        content_hash=forged.fingerprint,
        namespace=eval_req.namespace,
    )
    adapter._load_pool = lambda request: [  # type: ignore[method-assign]
        TypedPoolMember(execution=forged, values=authentic)
    ]
    req = EvaluationRequest(
        request_id=eval_req.request_id,
        namespace=eval_req.namespace,
        brief_ref=eval_req.brief_ref,
        factor_ref=eval_req.factor_ref,
        execution_ref=eval_req.execution_ref,
        protocol_id=eval_req.protocol_id,
        data_version=eval_req.data_version,
        split_id=eval_req.split_id,
        pool_refs=(pool_ref,),
    )
    report = adapter.compare_to_pool(req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.HASH_MISMATCH


def test_e4_resolve_brief_none_invalid_reference(tmp_path) -> None:
    adapter, eval_req, *_ = _adapter_stack(tmp_path)
    adapter._resolve_brief = lambda ref: None  # type: ignore[method-assign]
    report = adapter.preflight(eval_req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE
    assert "ResearchBrief" in report.failure.message


def test_e4_resolve_factor_wrong_type_invalid_reference(tmp_path) -> None:
    adapter, eval_req, *_ = _adapter_stack(tmp_path)
    adapter._resolve_factor = lambda ref: {"not": "a factor"}  # type: ignore[method-assign]
    report = adapter.preflight(eval_req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE
    assert "FactorSpec" in report.failure.message


def test_e4_resolve_execution_none_invalid_reference(tmp_path) -> None:
    adapter, eval_req, *_ = _adapter_stack(tmp_path)
    adapter._resolve_execution = lambda ref: None  # type: ignore[method-assign]
    report = adapter.evaluate(eval_req)
    assert report.failure is not None
    assert report.failure.code is FailureCode.INVALID_REFERENCE
    assert "FactorExecutionResult" in report.failure.message
