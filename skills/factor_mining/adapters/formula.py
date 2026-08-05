"""Versioned allowlist resolution and constrained expression compilation."""

from __future__ import annotations

import inspect
import math
from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd

from skills.compute import indicators as compute_indicators
from skills.factor_mining.contracts import (
    FailureCode,
    FormulaKind,
    FunctionRef,
    StructuredFormula,
    content_hash,
)

ALLOWLIST_VERSION = "1.0.0"
INDICATOR_MODULE = "skills.compute.indicators"

# Frozen Phase 02 top-level FunctionRef manifest. New public indicators are NOT
# auto-admitted; bump ALLOWLIST_VERSION and extend this tuple explicitly.
_FROZEN_INDICATOR_NAMES: tuple[str, ...] = (
    "atr_stop",
    "bias_momentum",
    "bollinger_reversal",
    "cci",
    "daily_return",
    "donchian_channel",
    "er",
    "er_adaptive",
    "er_directional",
    "er_enhanced",
    "fund_premium_rate",
    "high_vol_odds",
    "ma",
    "ma_cross",
    "ma_vol",
    "ma_vol_ratio",
    "mean_reversion",
    "mom_skip",
    "momentum_acceleration",
    "momentum_weighted",
    "orb",
    "orb_relvol",
    "price_above_ma",
    "price_drawdown",
    "roc",
    "rsi",
    "rsi_divergence",
    "rsrs",
    "rsrs_norm",
    "rsrs_v1",
    "rsrs_v2",
    "rsrs_v3",
    "slowkdj",
    "stand_orb_relvol",
    "supertrend",
    "trend_score",
    "trend_score_v2",
    "trend_score_v2_skip",
    "volatility_inv",
    "volatility_regime",
    "williams_r",
)

_BINOPS = frozenset({"add", "sub", "mul", "truediv"})
_CMPOPS = frozenset({"gt", "ge", "lt", "le", "eq", "ne"})
_BINOP_IMPL = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "mul": lambda a, b: a * b,
    "truediv": lambda a, b: a / b,
}
_CMPOP_IMPL = {
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}

_MAX_EXPRESSION_DEPTH = 32
_MAX_EXPRESSION_NODES = 128

_NODE_KEYS: dict[str, frozenset[str]] = {
    "field": frozenset({"type", "name"}),
    "const": frozenset({"type", "value"}),
    "param": frozenset({"type", "name"}),
    "binop": frozenset({"type", "op", "left", "right"}),
    "compare": frozenset({"type", "op", "left", "right"}),
    "call": frozenset({"type", "module", "name", "kwargs"}),
}


class FormulaAdapterError(Exception):
    def __init__(self, code: FailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def allowlist_manifest() -> tuple[tuple[str, str], ...]:
    """Return the frozen ``(module, name)`` FunctionRef manifest."""
    return tuple((INDICATOR_MODULE, name) for name in _FROZEN_INDICATOR_NAMES)


def allowlisted_functions() -> dict[tuple[str, str], Callable[..., Any]]:
    """Resolve the frozen allowlist to callables (indicators only)."""
    mapping: dict[tuple[str, str], Callable[..., Any]] = {}
    for module, name in allowlist_manifest():
        func = getattr(compute_indicators, name, None)
        if not callable(func):
            raise FormulaAdapterError(
                FailureCode.FUNCTION_NOT_ALLOWED,
                f"allowlisted function missing from module: {module}.{name}",
            )
        mapping[(module, name)] = func
    return mapping


def resolve_function_ref(ref: FunctionRef) -> Callable[..., Any]:
    """Resolve a FunctionRef against the frozen indicator allowlist only."""
    if ref.module.startswith("strategies"):
        raise FormulaAdapterError(
            FailureCode.FUNCTION_NOT_ALLOWED,
            "function refs must not point into strategies/",
        )
    key = (ref.module, ref.name)
    table = allowlisted_functions()
    if key not in table:
        raise FormulaAdapterError(
            FailureCode.FUNCTION_NOT_ALLOWED,
            f"function not allowlisted: {ref.module}.{ref.name}",
        )
    return table[key]


def _jsonable_params(params: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from skills.factor_mining.contracts import canonical_value

        plain = canonical_value(dict(params))
    except (TypeError, ValueError) as exc:
        raise FormulaAdapterError(
            FailureCode.INVALID_PARAMETERS,
            "parameters must be strict-JSON serializable",
        ) from exc
    if not isinstance(plain, dict):
        raise FormulaAdapterError(
            FailureCode.INVALID_PARAMETERS,
            "parameters must be a mapping",
        )
    return plain


def bind_parameters(
    func: Callable[..., Any], params: Mapping[str, Any]
) -> dict[str, Any]:
    """Fully bind kwargs against the callable signature (excluding the frame)."""
    plain = _jsonable_params(params)
    signature = inspect.signature(func)
    parameters = list(signature.parameters.values())
    if not parameters:
        raise FormulaAdapterError(
            FailureCode.INVALID_PARAMETERS,
            "allowlisted function has no bindable parameters",
        )
    frame_param = parameters[0]
    if frame_param.name in plain:
        raise FormulaAdapterError(
            FailureCode.INVALID_PARAMETERS,
            "parameters must not supply the frame argument",
        )
    has_var_keyword = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters
    )
    accepted = {
        p.name
        for p in parameters[1:]
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }
    if not has_var_keyword:
        unknown = sorted(set(plain) - accepted)
        if unknown:
            raise FormulaAdapterError(
                FailureCode.INVALID_PARAMETERS,
                f"unknown parameters: {unknown}",
            )
    required = [
        p.name
        for p in parameters[1:]
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        and p.default is inspect.Parameter.empty
    ]
    missing = [name for name in required if name not in plain]
    if missing:
        raise FormulaAdapterError(
            FailureCode.INVALID_PARAMETERS,
            f"missing required parameters: {missing}",
        )
    try:
        bound = signature.bind_partial(**{frame_param.name: object(), **plain})
        bound.apply_defaults()
    except TypeError as exc:
        raise FormulaAdapterError(
            FailureCode.INVALID_PARAMETERS,
            "parameters do not match function signature",
        ) from exc
    # bind with a sentinel then re-bind using a real empty frame for full check.
    try:
        signature.bind(pd.DataFrame(), **plain)
    except TypeError as exc:
        raise FormulaAdapterError(
            FailureCode.INVALID_PARAMETERS,
            "parameters do not match function signature",
        ) from exc
    return {key: plain[key] for key in sorted(plain)}


def callable_fingerprint(
    *,
    module: str,
    name: str,
    params: Mapping[str, Any],
    adapter_schema_version: str,
) -> str:
    payload = {
        "allowlist_version": ALLOWLIST_VERSION,
        "allowlist_manifest": list(allowlist_manifest()),
        "adapter_schema_version": adapter_schema_version,
        "module": module,
        "name": name,
        "params": _jsonable_params(params),
    }
    return content_hash(payload)


def expression_fingerprint(
    expression: Mapping[str, Any],
    params: Mapping[str, Any],
    *,
    adapter_schema_version: str,
) -> str:
    payload = {
        "allowlist_version": ALLOWLIST_VERSION,
        "allowlist_manifest": list(allowlist_manifest()),
        "adapter_schema_version": adapter_schema_version,
        "kind": "expression",
        "expression": dict(expression),
        "params": _jsonable_params(params),
    }
    return content_hash(payload)


def _require_mapping(node: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(node, Mapping):
        raise FormulaAdapterError(
            FailureCode.UNSUPPORTED_FORMULA,
            f"{label} must be a mapping",
        )
    return node


def _finite_number(value: Any, *, code: FailureCode, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FormulaAdapterError(code, f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise FormulaAdapterError(code, f"{label} must be a finite number")
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if number.is_integer():
        return int(number)
    return number


def validate_expression(
    expression: Mapping[str, Any],
    *,
    allowed_fields: frozenset[str],
    params: Mapping[str, Any],
) -> None:
    """Compile-time validation of the constrained expression AST."""
    stack: list[tuple[Mapping[str, Any], int]] = [(expression, 1)]
    seen_nodes = 0
    while stack:
        node, depth = stack.pop()
        seen_nodes += 1
        if depth > _MAX_EXPRESSION_DEPTH or seen_nodes > _MAX_EXPRESSION_NODES:
            raise FormulaAdapterError(
                FailureCode.UNSUPPORTED_FORMULA,
                "expression exceeds depth or node limits",
            )
        if not isinstance(node, Mapping):
            raise FormulaAdapterError(
                FailureCode.UNSUPPORTED_FORMULA,
                "expression nodes must be mappings",
            )
        ntype = node.get("type")
        if ntype not in _NODE_KEYS:
            raise FormulaAdapterError(
                FailureCode.UNSUPPORTED_FORMULA,
                f"unsupported expression node type: {ntype!r}",
            )
        allowed_keys = _NODE_KEYS[ntype]
        extra = set(node.keys()) - allowed_keys
        if extra:
            raise FormulaAdapterError(
                FailureCode.UNSUPPORTED_FORMULA,
                f"expression node has unknown keys: {sorted(extra)}",
            )
        required = set(allowed_keys)
        if ntype == "call":
            required = {"type", "module", "name"}
        missing = required - set(node.keys())
        if missing:
            raise FormulaAdapterError(
                FailureCode.UNSUPPORTED_FORMULA,
                f"expression node missing keys: {sorted(missing)}",
            )
        if ntype == "field":
            name = node.get("name")
            if not isinstance(name, str) or name not in allowed_fields:
                raise FormulaAdapterError(
                    FailureCode.UNSUPPORTED_FORMULA,
                    "expression references an unknown or disallowed field",
                )
        elif ntype == "const":
            _finite_number(
                node.get("value"),
                code=FailureCode.UNSUPPORTED_FORMULA,
                label="const value",
            )
        elif ntype == "param":
            name = node.get("name")
            if not isinstance(name, str) or name not in params:
                raise FormulaAdapterError(
                    FailureCode.INVALID_PARAMETERS,
                    "expression param reference is missing",
                )
            _finite_number(
                params[name],
                code=FailureCode.INVALID_PARAMETERS,
                label="expression param",
            )
        elif ntype in {"binop", "compare"}:
            op = node.get("op")
            allowed_ops = _BINOPS if ntype == "binop" else _CMPOPS
            if op not in allowed_ops:
                raise FormulaAdapterError(
                    FailureCode.UNSUPPORTED_FORMULA,
                    f"unsupported {ntype} op: {op!r}",
                )
            stack.append((_require_mapping(node.get("left"), label="left"), depth + 1))
            stack.append(
                (_require_mapping(node.get("right"), label="right"), depth + 1)
            )
        elif ntype == "call":
            module = node.get("module")
            name = node.get("name")
            if module != INDICATOR_MODULE or not isinstance(name, str):
                raise FormulaAdapterError(
                    FailureCode.FUNCTION_NOT_ALLOWED,
                    "expression calls are limited to allowlisted indicators",
                )
            resolve_function_ref(FunctionRef(module=module, name=name))
            raw_kwargs = node.get("kwargs", {})
            if "kwargs" in node and not isinstance(raw_kwargs, Mapping):
                raise FormulaAdapterError(
                    FailureCode.UNSUPPORTED_FORMULA,
                    "call kwargs must be a mapping",
                )
            call_kwargs: dict[str, Any] = {}
            for key, value_node in dict(raw_kwargs or {}).items():
                if not isinstance(key, str):
                    raise FormulaAdapterError(
                        FailureCode.UNSUPPORTED_FORMULA,
                        "call kwargs keys must be strings",
                    )
                value_map = _require_mapping(value_node, label=f"kwargs.{key}")
                validate_expression(
                    value_map,
                    allowed_fields=allowed_fields,
                    params=params,
                )
                vtype = value_map.get("type")
                if vtype == "const":
                    call_kwargs[key] = _finite_number(
                        value_map.get("value"),
                        code=FailureCode.UNSUPPORTED_FORMULA,
                        label="const value",
                    )
                elif vtype == "param":
                    pname = value_map.get("name")
                    call_kwargs[key] = params[pname]  # type: ignore[index]
                else:
                    raise FormulaAdapterError(
                        FailureCode.UNSUPPORTED_FORMULA,
                        "call kwargs only allow const or param nodes",
                    )
            bind_parameters(
                resolve_function_ref(FunctionRef(module=module, name=name)),
                call_kwargs,
            )


def _eval_node(
    node: Mapping[str, Any],
    *,
    frame: pd.DataFrame,
    params: Mapping[str, Any],
    allowed_fields: frozenset[str],
) -> pd.Series:
    ntype = node["type"]
    if ntype == "field":
        name = node["name"]
        return frame[name].astype("float64", copy=False)
    if ntype == "const":
        number = _finite_number(
            node["value"],
            code=FailureCode.UNSUPPORTED_FORMULA,
            label="const value",
        )
        return pd.Series(float(number), index=frame.index, dtype="float64")
    if ntype == "param":
        number = _finite_number(
            params[node["name"]],
            code=FailureCode.INVALID_PARAMETERS,
            label="expression param",
        )
        return pd.Series(float(number), index=frame.index, dtype="float64")
    if ntype == "binop":
        left = _eval_node(
            node["left"], frame=frame, params=params, allowed_fields=allowed_fields
        )
        right = _eval_node(
            node["right"], frame=frame, params=params, allowed_fields=allowed_fields
        )
        return _BINOP_IMPL[node["op"]](left, right)
    if ntype == "compare":
        left = _eval_node(
            node["left"], frame=frame, params=params, allowed_fields=allowed_fields
        )
        right = _eval_node(
            node["right"], frame=frame, params=params, allowed_fields=allowed_fields
        )
        return _CMPOP_IMPL[node["op"]](left, right).astype("float64")
    if ntype == "call":
        func = resolve_function_ref(
            FunctionRef(module=node["module"], name=node["name"])
        )
        raw_kwargs = node.get("kwargs") or {}
        kwargs: dict[str, Any] = {}
        for key, value_node in raw_kwargs.items():
            vtype = value_node["type"]
            if vtype == "const":
                kwargs[key] = _finite_number(
                    value_node["value"],
                    code=FailureCode.UNSUPPORTED_FORMULA,
                    label="const value",
                )
            else:
                kwargs[key] = params[value_node["name"]]
        bound = bind_parameters(func, kwargs)
        result = func(frame, **bound)
        if not isinstance(result, pd.Series):
            raise FormulaAdapterError(
                FailureCode.INVALID_OUTPUT_TYPE,
                "indicator call must return a Series",
            )
        return result.astype("float64", copy=False)
    raise FormulaAdapterError(
        FailureCode.UNSUPPORTED_FORMULA,
        f"unsupported expression node type: {ntype!r}",
    )


def compile_formula(
    formula: StructuredFormula,
    *,
    required_fields: tuple[str, ...],
    adapter_schema_version: str,
) -> tuple[Callable[[pd.DataFrame], pd.Series], str, dict[str, Any]]:
    """Compile a StructuredFormula into a single-symbol callable + fingerprint."""
    params = dict(formula.params)
    _jsonable_params(params)
    allowed_fields = frozenset(required_fields)

    if formula.kind is FormulaKind.FUNCTION_REF:
        assert formula.function_ref is not None
        target = resolve_function_ref(formula.function_ref)
        bound = bind_parameters(target, params)
        fingerprint = callable_fingerprint(
            module=formula.function_ref.module,
            name=formula.function_ref.name,
            params=bound,
            adapter_schema_version=adapter_schema_version,
        )

        def _func(frame: pd.DataFrame, _bound=bound, _target=target) -> pd.Series:
            return _target(frame, **_bound)

        return _func, fingerprint, bound

    if formula.kind is FormulaKind.EXPRESSION:
        assert formula.expression is not None
        expression = dict(formula.expression)
        validate_expression(
            expression,
            allowed_fields=allowed_fields,
            params=params,
        )
        fingerprint = expression_fingerprint(
            expression,
            params,
            adapter_schema_version=adapter_schema_version,
        )

        def _func(
            frame: pd.DataFrame,
            _expression=expression,
            _params=params,
            _fields=allowed_fields,
        ) -> pd.Series:
            return _eval_node(
                _expression,
                frame=frame,
                params=_params,
                allowed_fields=_fields,
            )

        return _func, fingerprint, dict(sorted(params.items()))

    raise FormulaAdapterError(
        FailureCode.UNSUPPORTED_FORMULA,
        f"unsupported formula kind: {formula.kind}",
    )
