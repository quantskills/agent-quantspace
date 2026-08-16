"""Unrestricted Python function resolution and expression compiler tests."""

from __future__ import annotations

import pytest

from skills.factor_mining.adapters.formula import (
    FORMULA_RESOLVER_VERSION,
    FormulaAdapterError,
    callable_implementation_hash,
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


def test_unrestricted_resolver_accepts_strategy_and_utility_functions() -> None:
    utility = resolve_function_ref(
        FunctionRef(module="skills.compute.utils", name="rolling_zscore")
    )
    generated = resolve_function_ref(
        FunctionRef(
            module="strategies.cross_sectional.mined_factors.mean_reversion",
            name="mr_quantile_deviation",
        )
    )
    assert utility.__name__ == "rolling_zscore"
    assert generated.__name__ == "mr_quantile_deviation"
    assert len(callable_implementation_hash(generated)) == 64

    with pytest.raises(FormulaAdapterError) as exc:
        resolve_function_ref(
            FunctionRef(module="does.not.exist", name="factor")
        )
    assert exc.value.code is FailureCode.INVALID_REFERENCE


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
    assert FORMULA_RESOLVER_VERSION == "2.0.0"
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


def test_expression_call_accepts_generated_strategy_function() -> None:
    formula = StructuredFormula(
        kind=FormulaKind.EXPRESSION,
        expression={
            "type": "call",
            "module": "strategies.cross_sectional.mined_factors.mean_reversion",
            "name": "mr_quantile_deviation",
            "kwargs": {
                "period": {"type": "const", "value": 3},
                "q": {"type": "const", "value": 0.5},
            },
        },
        params={},
    )
    func, fingerprint, _bound = compile_formula(
        formula,
        required_fields=("close",),
        adapter_schema_version="2.0.0",
    )
    frame = make_ohlcv([10.0, 12.0, 14.0, 16.0])
    out = func(frame)
    assert out.index.equals(frame.index)
    assert len(fingerprint) == 64
