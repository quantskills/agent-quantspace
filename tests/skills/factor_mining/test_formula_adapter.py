"""Allowlist and expression compiler tests."""

from __future__ import annotations

import pytest

from skills.factor_mining.adapters.formula import (
    ALLOWLIST_VERSION,
    FormulaAdapterError,
    allowlist_manifest,
    allowlisted_functions,
    compile_formula,
    resolve_function_ref,
)
from skills.factor_mining.contracts import (
    FailureCode,
    FormulaKind,
    FunctionRef,
    StructuredFormula,
)
from tests.fixtures.market_data import make_ohlcv


def test_frozen_allowlist_excludes_utils_and_unknown() -> None:
    assert all(module == "skills.compute.indicators" for module, _ in allowlist_manifest())
    assert ("skills.compute.utils", "rolling_zscore") not in allowlisted_functions()
    with pytest.raises(FormulaAdapterError) as exc:
        resolve_function_ref(
            FunctionRef(module="skills.compute.utils", name="rolling_zscore")
        )
    assert exc.value.code is FailureCode.FUNCTION_NOT_ALLOWED
    with pytest.raises(FormulaAdapterError) as exc2:
        resolve_function_ref(
            FunctionRef(module="skills.compute.indicators", name="not_a_real_factor")
        )
    assert exc2.value.code is FailureCode.FUNCTION_NOT_ALLOWED


def test_bind_rejects_frame_param_missing_and_unknown_kwargs() -> None:
    formula = StructuredFormula(
        kind=FormulaKind.FUNCTION_REF,
        function_ref=FunctionRef(module="skills.compute.indicators", name="roc"),
        params={"group": 1, "period": 3},
    )
    with pytest.raises(FormulaAdapterError) as exc:
        compile_formula(
            formula, required_fields=("close",), adapter_schema_version="2.0.0"
        )
    assert exc.value.code is FailureCode.INVALID_PARAMETERS

    formula2 = StructuredFormula(
        kind=FormulaKind.FUNCTION_REF,
        function_ref=FunctionRef(module="skills.compute.indicators", name="roc"),
        params={"period": 3, "unexpected": 1},
    )
    with pytest.raises(FormulaAdapterError) as exc2:
        compile_formula(
            formula2, required_fields=("close",), adapter_schema_version="2.0.0"
        )
    assert exc2.value.code is FailureCode.INVALID_PARAMETERS


def test_compile_function_ref_binds_params_and_preserves_warmup_nan() -> None:
    formula = StructuredFormula(
        kind=FormulaKind.FUNCTION_REF,
        function_ref=FunctionRef(module="skills.compute.indicators", name="roc"),
        params={"period": 3},
    )
    func, fingerprint, bound = compile_formula(
        formula,
        required_fields=("close",),
        adapter_schema_version="2.0.0",
    )
    assert bound == {"period": 3}
    assert len(fingerprint) == 64
    assert ALLOWLIST_VERSION in ("1.0.0",)
    frame = make_ohlcv([100.0, 101.0, 102.0, 103.0, 104.0])
    out = func(frame)
    assert out.index.equals(frame.index)
    assert out.isna().sum() == 3


def test_compile_expression_validates_shape_and_forbids_unknown_keys() -> None:
    expression = {
        "type": "binop",
        "op": "sub",
        "left": {"type": "field", "name": "close"},
        "right": {
            "type": "call",
            "module": "skills.compute.indicators",
            "name": "ma",
            "kwargs": {"period": {"type": "const", "value": 2}},
        },
    }
    formula = StructuredFormula(
        kind=FormulaKind.EXPRESSION,
        expression=expression,
        params={},
    )
    func, fingerprint, _bound = compile_formula(
        formula,
        required_fields=("close",),
        adapter_schema_version="2.0.0",
    )
    assert len(fingerprint) == 64
    frame = make_ohlcv([10.0, 12.0, 14.0, 16.0])
    out = func(frame)
    assert out.index.equals(frame.index)

    bad = StructuredFormula(
        kind=FormulaKind.EXPRESSION,
        expression={"type": "field", "name": "close", "extra": 1},
        params={},
    )
    with pytest.raises(FormulaAdapterError) as exc:
        compile_formula(
            bad, required_fields=("close",), adapter_schema_version="2.0.0"
        )
    assert exc.value.code is FailureCode.UNSUPPORTED_FORMULA

    unknown_field = StructuredFormula(
        kind=FormulaKind.EXPRESSION,
        expression={"type": "field", "name": "not_allowed"},
        params={},
    )
    with pytest.raises(FormulaAdapterError) as exc2:
        compile_formula(
            unknown_field,
            required_fields=("close",),
            adapter_schema_version="2.0.0",
        )
    assert exc2.value.code is FailureCode.UNSUPPORTED_FORMULA
