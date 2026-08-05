"""Static FactorSpec / formula safety checks (analyze-native)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from skills.analyze.contracts import Finding, FindingSeverity, SpecSnapshot

# Mirror of Phase 02 frozen indicator names. analyze does not import factor_mining;
# callers may inject a narrower/wider allowlist via ``allowed_functions``.
DEFAULT_INDICATOR_NAMES: frozenset[str] = frozenset(
    {
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
    }
)
DEFAULT_FUNCTION_MODULE = "skills.compute.indicators"

_BINOPS = frozenset({"add", "sub", "mul", "truediv"})
_CMPOPS = frozenset({"gt", "ge", "lt", "le", "eq", "ne"})
_NODE_KEYS: dict[str, frozenset[str]] = {
    "field": frozenset({"type", "name"}),
    "const": frozenset({"type", "value"}),
    "param": frozenset({"type", "name"}),
    "binop": frozenset({"type", "op", "left", "right"}),
    "compare": frozenset({"type", "op", "left", "right"}),
    "call": frozenset({"type", "module", "name", "kwargs"}),
}
_FORBIDDEN_NAME_FRAGMENTS = (
    "eval",
    "exec",
    "import",
    "__",
    "open",
    "os.",
    "sys.",
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "pathlib",
    "getenv",
    "environ",
    "random",
    "time.time",
    "datetime.now",
    "globals",
    "locals",
    "builtin",
)
_MAX_DEPTH = 32
_MAX_NODES = 128


def _finding(
    name: str,
    *,
    passed: bool,
    message: str,
    severity: FindingSeverity = FindingSeverity.HARD_FAIL,
    details: Mapping[str, Any] | None = None,
) -> Finding:
    return Finding(
        name=name,
        severity=severity,
        passed=passed,
        message=message,
        details=dict(details or {}),
    )


def _walk_expression(
    node: Any,
    *,
    depth: int,
    counter: list[int],
    findings: list[Finding],
    allowed_functions: frozenset[tuple[str, str]],
    allowed_fields: Sequence[str] | None,
) -> None:
    counter[0] += 1
    if counter[0] > _MAX_NODES:
        findings.append(
            _finding(
                "SPEC_EXPRESSION_TOO_LARGE",
                passed=False,
                message="expression exceeds max node count",
            )
        )
        return
    if depth > _MAX_DEPTH:
        findings.append(
            _finding(
                "SPEC_EXPRESSION_TOO_DEEP",
                passed=False,
                message="expression exceeds max depth",
            )
        )
        return
    if not isinstance(node, Mapping):
        findings.append(
            _finding(
                "SPEC_UNSUPPORTED_FORMULA",
                passed=False,
                message="expression nodes must be mappings",
            )
        )
        return
    node_type = node.get("type")
    if node_type not in _NODE_KEYS:
        findings.append(
            _finding(
                "SPEC_UNSUPPORTED_FORMULA",
                passed=False,
                message=f"unsupported expression node type: {node_type!r}",
            )
        )
        return
    unknown = set(node.keys()) - _NODE_KEYS[node_type]
    if unknown:
        findings.append(
            _finding(
                "SPEC_UNSUPPORTED_FORMULA",
                passed=False,
                message="expression node has unknown keys",
                details={"unknown": sorted(unknown), "type": node_type},
            )
        )
        return
    text = str(node).lower()
    for frag in _FORBIDDEN_NAME_FRAGMENTS:
        if frag in text and node_type not in {"field", "param", "const"}:
            findings.append(
                _finding(
                    "SPEC_FORBIDDEN_CAPABILITY",
                    passed=False,
                    message=f"forbidden capability fragment {frag!r}",
                )
            )
            return

    if node_type == "field":
        name = node.get("name")
        if not isinstance(name, str) or not name:
            findings.append(
                _finding(
                    "SPEC_INVALID_FIELD",
                    passed=False,
                    message="field node requires a non-empty name",
                )
            )
        elif allowed_fields is not None and name not in allowed_fields:
            findings.append(
                _finding(
                    "SPEC_FIELD_NOT_ALLOWED",
                    passed=False,
                    message=f"field {name!r} is not allowed",
                )
            )
    elif node_type == "const":
        value = node.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            findings.append(
                _finding(
                    "SPEC_INVALID_CONST",
                    passed=False,
                    message="const value must be int or float",
                )
            )
    elif node_type == "param":
        name = node.get("name")
        if not isinstance(name, str) or not name:
            findings.append(
                _finding(
                    "SPEC_INVALID_PARAM",
                    passed=False,
                    message="param node requires a non-empty name",
                )
            )
    elif node_type in {"binop", "compare"}:
        op = node.get("op")
        allowed_ops = _BINOPS if node_type == "binop" else _CMPOPS
        if op not in allowed_ops:
            findings.append(
                _finding(
                    "SPEC_UNSUPPORTED_FORMULA",
                    passed=False,
                    message=f"unsupported operator {op!r}",
                )
            )
        _walk_expression(
            node.get("left"),
            depth=depth + 1,
            counter=counter,
            findings=findings,
            allowed_functions=allowed_functions,
            allowed_fields=allowed_fields,
        )
        _walk_expression(
            node.get("right"),
            depth=depth + 1,
            counter=counter,
            findings=findings,
            allowed_functions=allowed_functions,
            allowed_fields=allowed_fields,
        )
    elif node_type == "call":
        module = node.get("module")
        name = node.get("name")
        if not isinstance(module, str) or not isinstance(name, str):
            findings.append(
                _finding(
                    "SPEC_FUNCTION_NOT_ALLOWED",
                    passed=False,
                    message="call nodes require module and name strings",
                )
            )
            return
        if (module, name) not in allowed_functions:
            findings.append(
                _finding(
                    "SPEC_FUNCTION_NOT_ALLOWED",
                    passed=False,
                    message=f"function {module}.{name} is not allowlisted",
                )
            )
        kwargs = node.get("kwargs", {})
        if not isinstance(kwargs, Mapping):
            findings.append(
                _finding(
                    "SPEC_UNSUPPORTED_FORMULA",
                    passed=False,
                    message="call kwargs must be a mapping",
                )
            )
            return
        _check_call_kwargs_causality(name, kwargs, findings)
        for value in kwargs.values():
            if isinstance(value, Mapping) and "type" in value:
                _walk_expression(
                    value,
                    depth=depth + 1,
                    counter=counter,
                    findings=findings,
                    allowed_functions=allowed_functions,
                    allowed_fields=allowed_fields,
                )


def _check_call_kwargs_causality(
    name: str, kwargs: Mapping[str, Any], findings: list[Finding]
) -> None:
    for key, value in kwargs.items():
        key_l = str(key).lower()
        if key_l in {"center", "centred", "centered"} and value is True:
            findings.append(
                _finding(
                    "CAUSALITY_CENTERED_WINDOW",
                    passed=False,
                    message=f"centered window rejected on {name}",
                )
            )
        if key_l in {"shift", "periods", "lag"} and isinstance(value, (int, float)):
            if float(value) < 0:
                findings.append(
                    _finding(
                        "CAUSALITY_NEGATIVE_SHIFT",
                        passed=False,
                        message=f"negative shift/periods rejected on {name}",
                        details={"key": key, "value": value},
                    )
                )
        if key_l in {"offset", "label"} and isinstance(value, str):
            if value.lower() in {"future", "forward", "lead"}:
                findings.append(
                    _finding(
                        "CAUSALITY_FUTURE_LABEL",
                        passed=False,
                        message=f"future label rejected on {name}",
                    )
                )


def validate_spec(
    spec: SpecSnapshot,
    *,
    allowed_functions: frozenset[tuple[str, str]] | None = None,
    allowed_fields: Sequence[str] | None = None,
    protocol_fields: Sequence[str] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    allow = allowed_functions or frozenset(
        (DEFAULT_FUNCTION_MODULE, name) for name in DEFAULT_INDICATOR_NAMES
    )
    fields = protocol_fields if protocol_fields is not None else allowed_fields

    if not isinstance(spec.window, int) or isinstance(spec.window, bool) or spec.window <= 0:
        findings.append(
            _finding(
                "SPEC_INVALID_WINDOW",
                passed=False,
                message="window must be a positive int",
                details={"window": spec.window},
            )
        )
    if not isinstance(spec.lag, int) or isinstance(spec.lag, bool) or spec.lag < 0:
        findings.append(
            _finding(
                "SPEC_INVALID_LAG",
                passed=False,
                message="lag must be a non-negative int",
                details={"lag": spec.lag},
            )
        )
    if not isinstance(spec.warmup, int) or isinstance(spec.warmup, bool) or spec.warmup < 0:
        findings.append(
            _finding(
                "SPEC_INVALID_WINDOW",
                passed=False,
                message="warmup must be a non-negative int",
                details={"warmup": spec.warmup},
            )
        )
    if spec.output_dtype != "float64":
        findings.append(
            _finding(
                "SPEC_INVALID_OUTPUT_DTYPE",
                passed=False,
                message="only float64 output_dtype is supported in Phase 03",
            )
        )
    if spec.missing_policy not in {"keep_nan", "drop_nan"}:
        findings.append(
            _finding(
                "SPEC_INVALID_MISSING_POLICY",
                passed=False,
                message=f"unsupported missing_policy {spec.missing_policy!r}",
            )
        )

    missing_req = [name for name in spec.required_fields if fields and name not in fields]
    if fields is not None and missing_req:
        findings.append(
            _finding(
                "SPEC_FIELD_UNAVAILABLE",
                passed=False,
                message="required_fields unavailable on panel/protocol",
                details={"missing": missing_req},
            )
        )

    for key, value in spec.params.items():
        text = f"{key}={value}".lower()
        for frag in _FORBIDDEN_NAME_FRAGMENTS:
            if frag in text:
                findings.append(
                    _finding(
                        "SPEC_FORBIDDEN_CAPABILITY",
                        passed=False,
                        message=f"forbidden capability in params: {frag}",
                    )
                )
        key_l = str(key).lower()
        if key_l in {"period", "window", "n", "lookback"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                findings.append(
                    _finding(
                        "SPEC_INVALID_PERIOD",
                        passed=False,
                        message=f"param {key!r} must be a positive number",
                        details={"key": key, "value": value},
                    )
                )
            elif float(value) != int(value) or int(value) <= 0:
                findings.append(
                    _finding(
                        "SPEC_INVALID_PERIOD",
                        passed=False,
                        message=f"param {key!r} must be a positive int",
                        details={"key": key, "value": value},
                    )
                )
        if key_l in {"shift", "periods", "lag"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                findings.append(
                    _finding(
                        "SPEC_INVALID_LAG",
                        passed=False,
                        message=f"param {key!r} must be a non-negative int",
                        details={"key": key, "value": value},
                    )
                )
            elif float(value) != int(value) or int(value) < 0:
                if float(value) < 0:
                    findings.append(
                        _finding(
                            "CAUSALITY_NEGATIVE_SHIFT",
                            passed=False,
                            message=f"param {key!r} must be a non-negative int",
                            details={"key": key, "value": value},
                        )
                    )
                else:
                    findings.append(
                        _finding(
                            "SPEC_INVALID_LAG",
                            passed=False,
                            message=f"param {key!r} must be a non-negative int",
                            details={"key": key, "value": value},
                        )
                    )
        if key_l in {"center", "centered"} and value is True:
            findings.append(
                _finding(
                    "CAUSALITY_CENTERED_WINDOW",
                    passed=False,
                    message="centered window param rejected",
                )
            )

    # Consistency between top-level window/lag and known param names.
    if "period" in spec.params and isinstance(spec.params["period"], (int, float)):
        if (
            not isinstance(spec.params["period"], bool)
            and float(spec.params["period"]) == int(spec.params["period"])
            and int(spec.params["period"]) != spec.window
            and isinstance(spec.window, int)
            and not isinstance(spec.window, bool)
            and spec.window > 0
        ):
            findings.append(
                _finding(
                    "SPEC_INVALID_PARAM",
                    passed=False,
                    message="params.period must equal top-level window when both are set",
                    details={"period": spec.params["period"], "window": spec.window},
                )
            )
    if "window" in spec.params and isinstance(spec.params["window"], (int, float)):
        if (
            not isinstance(spec.params["window"], bool)
            and float(spec.params["window"]) == int(spec.params["window"])
            and int(spec.params["window"]) != spec.window
            and isinstance(spec.window, int)
            and not isinstance(spec.window, bool)
            and spec.window > 0
        ):
            findings.append(
                _finding(
                    "SPEC_INVALID_PARAM",
                    passed=False,
                    message="params.window must equal top-level window when both are set",
                    details={"params_window": spec.params["window"], "window": spec.window},
                )
            )
    if "lag" in spec.params and isinstance(spec.params["lag"], (int, float)):
        if (
            not isinstance(spec.params["lag"], bool)
            and float(spec.params["lag"]) == int(spec.params["lag"])
            and int(spec.params["lag"]) != spec.lag
            and isinstance(spec.lag, int)
            and not isinstance(spec.lag, bool)
            and spec.lag >= 0
        ):
            findings.append(
                _finding(
                    "SPEC_INVALID_PARAM",
                    passed=False,
                    message="params.lag must equal top-level lag when both are set",
                    details={"params_lag": spec.params["lag"], "lag": spec.lag},
                )
            )

    if spec.formula_kind == "function_ref":
        if not spec.function_module or not spec.function_name:
            findings.append(
                _finding(
                    "SPEC_UNSUPPORTED_FORMULA",
                    passed=False,
                    message="function_ref requires module and name",
                )
            )
        elif (spec.function_module, spec.function_name) not in allow:
            findings.append(
                _finding(
                    "SPEC_FUNCTION_NOT_ALLOWED",
                    passed=False,
                    message=(
                        f"function {spec.function_module}.{spec.function_name} "
                        "is not allowlisted"
                    ),
                )
            )
        else:
            findings.append(
                _finding(
                    "SPEC_FUNCTION_ALLOWLIST",
                    passed=True,
                    severity=FindingSeverity.INFO,
                    message="function_ref is allowlisted",
                )
            )
        if spec.expression is not None:
            findings.append(
                _finding(
                    "SPEC_UNSUPPORTED_FORMULA",
                    passed=False,
                    message="function_ref must not set expression",
                )
            )
    elif spec.formula_kind == "expression":
        if not spec.expression:
            findings.append(
                _finding(
                    "SPEC_UNSUPPORTED_FORMULA",
                    passed=False,
                    message="expression formula requires a non-empty mapping",
                )
            )
        else:
            counter = [0]
            _walk_expression(
                dict(spec.expression),
                depth=0,
                counter=counter,
                findings=findings,
                allowed_functions=allow,
                allowed_fields=fields,
            )
    else:
        findings.append(
            _finding(
                "SPEC_UNSUPPORTED_FORMULA",
                passed=False,
                message=f"unsupported formula_kind {spec.formula_kind!r}",
            )
        )

    # Free-python / eval path markers on params or expression string dumps.
    blob = f"{spec.params}|{spec.expression}|{spec.function_name}".lower()
    for token in ("eval(", "exec(", "__import__", "open(", "os.system"):
        if token in blob:
            findings.append(
                _finding(
                    "SPEC_FORBIDDEN_CAPABILITY",
                    passed=False,
                    message=f"forbidden free-python token {token!r}",
                )
            )

    if not any(
        (not f.passed) and f.severity is FindingSeverity.HARD_FAIL for f in findings
    ):
        findings.append(
            _finding(
                "SPEC_STRUCTURE_OK",
                passed=True,
                severity=FindingSeverity.INFO,
                message="FactorSpec structure passed static checks",
            )
        )
    return findings


__all__ = [
    "DEFAULT_FUNCTION_MODULE",
    "DEFAULT_INDICATOR_NAMES",
    "validate_spec",
]
