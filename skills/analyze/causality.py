"""Time-causality checks including issued prefix-recompute capability verification.

Process trust boundary: Python cannot stop a malicious in-process importer from
calling private helpers. Production code must obtain ``BoundPrefixRecompute``
only via ``skills.factor_mining.adapters.analyze.build_prefix_recompute_capability``
after compiling an exact FactorSpec and matching ``execution.callable_fingerprint``.
Analyze exposes no public API that seals arbitrary callables with hash strings.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from skills.analyze.contracts import Finding, FindingSeverity, SpecSnapshot

PrefixRecomputeFn = Callable[[pd.DataFrame], pd.Series]

# Module-private seal registry. Only ``_issue_prefix_recompute_capability`` adds.
_ISSUED_SEALS: set[str] = set()
_ISSUER_NAME = "phase02.compile_formula"


class BoundPrefixRecompute:
    """Issued prefix-recompute capability (not string self-attestation).

    Public construction is forbidden. Production instances come from the Phase 02
    factor_mining adapter builder after ``compile_formula``. A seal registry alone
    is not a security boundary against malicious same-process callers.
    """

    __slots__ = (
        "spec_content_hash",
        "formula_fingerprint",
        "recompute",
        "_seal",
        "_issuer",
        "_compiled_fingerprint",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "BoundPrefixRecompute cannot be constructed directly; use "
            "skills.factor_mining.adapters.analyze.build_prefix_recompute_capability"
        )

    @classmethod
    def _create(
        cls,
        *,
        spec_content_hash: str,
        formula_fingerprint: str,
        recompute: PrefixRecomputeFn,
        seal: str,
        issuer: str,
        compiled_fingerprint: str,
    ) -> BoundPrefixRecompute:
        if issuer != _ISSUER_NAME:
            raise ValueError("untrusted prefix-recompute issuer")
        if not seal or seal not in _ISSUED_SEALS:
            raise ValueError("prefix-recompute seal is not registered")
        if compiled_fingerprint != formula_fingerprint:
            raise ValueError("compiled fingerprint must equal formula_fingerprint")
        obj = object.__new__(cls)
        object.__setattr__(obj, "spec_content_hash", str(spec_content_hash))
        object.__setattr__(obj, "formula_fingerprint", str(formula_fingerprint))
        object.__setattr__(obj, "recompute", recompute)
        object.__setattr__(obj, "_seal", str(seal))
        object.__setattr__(obj, "_issuer", str(issuer))
        object.__setattr__(obj, "_compiled_fingerprint", str(compiled_fingerprint))
        recompute.__qs_formula_fingerprint__ = str(formula_fingerprint)
        recompute.__qs_prefix_seal__ = str(seal)
        return obj

    def is_issued_for(self, spec: SpecSnapshot) -> bool:
        if self._seal not in _ISSUED_SEALS:
            return False
        if self._issuer != _ISSUER_NAME:
            return False
        if self.spec_content_hash != spec.content_hash:
            return False
        if self.formula_fingerprint != (getattr(spec, "formula_fingerprint", "") or ""):
            return False
        if self._compiled_fingerprint != self.formula_fingerprint:
            return False
        marked = getattr(self.recompute, "__qs_formula_fingerprint__", None)
        seal_mark = getattr(self.recompute, "__qs_prefix_seal__", None)
        return marked == self.formula_fingerprint and seal_mark == self._seal


def _register_seal(seal: str) -> None:
    if not seal:
        raise ValueError("seal must be non-empty")
    _ISSUED_SEALS.add(seal)


def _issue_prefix_recompute_capability(
    *,
    spec_content_hash: str,
    formula_fingerprint: str,
    recompute: PrefixRecomputeFn,
    seal: str,
) -> BoundPrefixRecompute:
    """Private seal constructor for Phase02 adapter builder / testing helper."""
    _register_seal(seal)
    return BoundPrefixRecompute._create(
        spec_content_hash=spec_content_hash,
        formula_fingerprint=formula_fingerprint,
        recompute=recompute,
        seal=seal,
        issuer=_ISSUER_NAME,
        compiled_fingerprint=formula_fingerprint,
    )


def _testing_only_bound_prefix_recompute(
    *,
    spec_content_hash: str,
    formula_fingerprint: str,
    recompute: PrefixRecomputeFn,
) -> BoundPrefixRecompute:
    """PRIVATE adversarial/unit-test helper — not a production API.

    Does not prove formula identity beyond the test author's honesty. Production
    orchestration must not call this.
    """
    import secrets

    seal = secrets.token_hex(32)
    return _issue_prefix_recompute_capability(
        spec_content_hash=spec_content_hash,
        formula_fingerprint=formula_fingerprint,
        recompute=recompute,
        seal=seal,
    )


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


def _exact_numeric_equal(left: pd.Series, right: pd.Series) -> bool:
    if len(left) != len(right) or not left.index.equals(right.index):
        return False
    lf = np.asarray(left.to_numpy(copy=True), dtype=float)
    rf = np.asarray(right.to_numpy(copy=True), dtype=float)
    left_nan = np.isnan(lf)
    right_nan = np.isnan(rf)
    if not np.array_equal(left_nan, right_nan):
        return False
    if not np.array_equal(np.isinf(lf), np.isinf(rf)):
        return False
    both_inf = np.isinf(lf) & np.isinf(rf)
    if both_inf.any() and not np.array_equal(np.sign(lf[both_inf]), np.sign(rf[both_inf])):
        return False
    finite = ~(left_nan | np.isinf(lf))
    return (not finite.any()) or bool(np.array_equal(lf[finite], rf[finite]))


def _frame_unchanged(before: pd.DataFrame, after: pd.DataFrame) -> bool:
    if list(before.columns) != list(after.columns):
        return False
    if not before.index.equals(after.index):
        return False
    for col in before.columns:
        left = before[col]
        right = after[col]
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            if not _exact_numeric_equal(left.astype(float), right.astype(float)):
                return False
        else:
            if not left.equals(right):
                return False
    return True


def _keyset(index: pd.Index) -> set[Any]:
    if isinstance(index, pd.MultiIndex):
        return set(map(tuple, index.tolist()))
    return set(index)


def _cut_points(
    unique_times: pd.Index,
    *,
    mode: str = "full",
) -> list[Any]:
    """Deterministic cut schedule for prefix causality.

    Default ``mode="full"`` (authoritative proof): every checkable time prefix
    through the second-to-last unique timestamp (indices ``0 .. n-2``), so a
    single mid-sample lookahead day cannot hide between sparse sample cuts.

    ``mode="sampled"`` is an explicit non-proof / soft schedule (fixed quartiles
    + near-tail) and must not be treated as a default pass proof.
    """
    n = len(unique_times)
    if n < 2:
        return []
    if mode == "sampled":
        if n < 3:
            # Still non-proof: only the single checkable prefix before the last bar.
            return [unique_times[0]]
        idxs = sorted(
            {
                max(0, n // 4),
                max(0, n // 2),
                max(0, (3 * n) // 4),
                max(0, n - 2),
            }
        )
        return [unique_times[i] for i in idxs if 0 <= i < n - 1]
    if mode != "full":
        raise ValueError("cut mode must be 'full' or 'sampled'")
    # Every prefix that leaves at least one future timestamp.
    return [unique_times[i] for i in range(0, n - 1)]


def _run_one_cut(
    *,
    panel: pd.DataFrame,
    ordered_times: pd.Index,
    cut: Any,
    fn: PrefixRecomputeFn,
    binding: Mapping[str, str],
) -> Finding:
    full = panel.copy(deep=True)
    prefix_mask = ordered_times <= cut
    prefix = full.loc[prefix_mask].copy(deep=True)
    prefix_snapshot = prefix.copy(deep=True)
    full_snapshot = full.copy(deep=True)
    expected = prefix.index
    try:
        prefix_out = fn(prefix)
        if not _frame_unchanged(prefix_snapshot, prefix):
            return _finding(
                "CAUSALITY_PREFIX_INPUT_MUTATED",
                passed=False,
                message="recompute mutated the prefix panel copy",
                details={**dict(binding), "cut": str(cut)},
            )
        full_out = fn(full)
        if not _frame_unchanged(full_snapshot, full):
            return _finding(
                "CAUSALITY_FULL_INPUT_MUTATED",
                passed=False,
                message="recompute mutated the full panel copy",
                details={**dict(binding), "cut": str(cut)},
            )
    except Exception as exc:  # noqa: BLE001
        return _finding(
            "CAUSALITY_PREFIX_RECOMPUTE",
            passed=False,
            message="recompute callable failed during causality check",
            details={**dict(binding), "cause_type": type(exc).__name__, "cut": str(cut)},
        )

    if not isinstance(prefix_out, pd.Series) or not isinstance(full_out, pd.Series):
        return _finding(
            "CAUSALITY_PREFIX_RECOMPUTE",
            passed=False,
            message="recompute callable must return a Series",
            details={**dict(binding), "cut": str(cut)},
        )
    if not pd.api.types.is_numeric_dtype(prefix_out.dtype) or not pd.api.types.is_numeric_dtype(
        full_out.dtype
    ):
        return _finding(
            "CAUSALITY_PREFIX_RECOMPUTE",
            passed=False,
            message="recompute outputs must be numeric",
            details={**dict(binding), "cut": str(cut)},
        )
    if prefix_out.index.duplicated().any() or full_out.index.duplicated().any():
        return _finding(
            "CAUSALITY_PREFIX_RECOMPUTE",
            passed=False,
            message="recompute outputs must not contain duplicate index keys",
            details={**dict(binding), "cut": str(cut)},
        )

    expected_set = _keyset(expected)
    prefix_set = _keyset(prefix_out.index)
    if prefix_set != expected_set or len(prefix_out) != len(expected):
        return _finding(
            "CAUSALITY_PREFIX_RECOMPUTE",
            passed=False,
            message="prefix recompute must preserve the expected prefix key set",
            details={
                **dict(binding),
                "cut": str(cut),
                "expected_rows": int(len(expected)),
                "prefix_rows": int(len(prefix_out)),
                "missing": int(len(expected_set - prefix_set)),
                "extra": int(len(prefix_set - expected_set)),
            },
        )
    full_keys = _keyset(full_out.index)
    if not expected_set.issubset(full_keys):
        return _finding(
            "CAUSALITY_PREFIX_RECOMPUTE",
            passed=False,
            message="full recompute missing expected prefix keys",
            details={**dict(binding), "cut": str(cut)},
        )

    ok = _exact_numeric_equal(prefix_out.reindex(expected), full_out.reindex(expected))
    return _finding(
        "CAUSALITY_PREFIX_RECOMPUTE",
        passed=ok,
        severity=FindingSeverity.HARD_FAIL if not ok else FindingSeverity.INFO,
        message=(
            "prefix outputs unchanged after appending future rows"
            if ok
            else "prefix outputs changed or key set not preserved"
        ),
        details={
            **dict(binding),
            "cut": str(cut),
            "expected_rows": int(len(expected)),
        },
    )


def verify_prefix_causality(
    panel: pd.DataFrame,
    *,
    datetime_pos: int,
    recompute: BoundPrefixRecompute | PrefixRecomputeFn | None,
    spec: SpecSnapshot,
    min_prefix_rows: int = 4,
    require_prefix_recompute: bool = False,
    cut_mode: str = "full",
) -> list[Finding]:
    """Verify appending future rows cannot change historical factor outputs.

    Trust boundary: only a Phase02-**issued** ``BoundPrefixRecompute`` whose
    registered seal matches the current ``SpecSnapshot`` (content hash +
    formula fingerprint + callable marks) is accepted. Copying hash strings
    onto an unrelated callable cannot create a registered seal. Default
    ``cut_mode="full"`` evaluates every checkable time prefix through the
    second-to-last timestamp (authoritative). ``cut_mode="sampled"`` is an
    explicit non-proof soft schedule: even when all sampled cuts pass, the
    result is ``CAUSALITY_PREFIX_SAMPLED_NON_PROOF`` (SOFT_FAIL, passed=False),
    never an INFO pass; real leaks under sampled cuts remain HARD_FAIL. Each
    cut snapshots the actual prefix/full copies passed to the callable and
    hard-fails mutation of those copies. Result details always record the
    full ``n_cuts``.
    """
    caller_snapshot = panel.copy(deep=True)
    binding_hash = spec.content_hash
    formula_fp = getattr(spec, "formula_fingerprint", "") or ""
    binding = {
        "spec_content_hash": binding_hash,
        "formula_fingerprint": formula_fp,
        "cut_mode": cut_mode,
    }

    def _unavailable(reason: str, *, hard: bool | None = None) -> list[Finding]:
        severity = (
            FindingSeverity.HARD_FAIL
            if (hard if hard is not None else require_prefix_recompute)
            else FindingSeverity.SOFT_FAIL
        )
        return [
            _finding(
                "CAUSALITY_PREFIX_RECOMPUTE",
                passed=False,
                severity=severity,
                message="prefix-recompute capability unavailable",
                details={**binding, "reason": reason},
            )
        ]

    if recompute is None:
        return _unavailable("no_recompute_callable")
    if not isinstance(recompute, BoundPrefixRecompute):
        return [
            _finding(
                "CAUSALITY_RECOMPUTE_UNBOUND",
                passed=False,
                message="prefix recompute must be an issued BoundPrefixRecompute capability",
                details=binding,
            )
        ]
    if not recompute.is_issued_for(spec):
        # Distinguish common mismatch modes for FailureCode mapping.
        if recompute.spec_content_hash != spec.content_hash:
            return [
                _finding(
                    "CAUSALITY_RECOMPUTE_SPEC_MISMATCH",
                    passed=False,
                    message="prefix recompute is bound to a different FactorSpec",
                    details={
                        "bound_spec_hash": recompute.spec_content_hash,
                        "spec_content_hash": spec.content_hash,
                    },
                )
            ]
        if not formula_fp or recompute.formula_fingerprint != formula_fp:
            return [
                _finding(
                    "CAUSALITY_RECOMPUTE_FORMULA_MISMATCH",
                    passed=False,
                    message="prefix recompute formula fingerprint does not match SpecSnapshot",
                    details={
                        "bound_formula_fingerprint": recompute.formula_fingerprint,
                        "spec_formula_fingerprint": formula_fp,
                    },
                )
            ]
        return [
            _finding(
                "CAUSALITY_RECOMPUTE_UNISSUED",
                passed=False,
                message=(
                    "prefix recompute seal/callable marks are not an issued "
                    "Phase02 capability for this SpecSnapshot"
                ),
                details=binding,
            )
        ]
    fn = recompute.recompute

    if len(panel) < min_prefix_rows + 1:
        return _unavailable("panel_too_short")

    times = panel.index.get_level_values(datetime_pos)
    try:
        ordered_times = pd.Index(pd.to_datetime(pd.Index(times), errors="raise"))
    except (TypeError, ValueError) as exc:
        return [
            _finding(
                "CAUSALITY_PREFIX_RECOMPUTE",
                passed=False,
                message="datetime level unusable for prefix split",
                details={**binding, "cause_type": type(exc).__name__},
            )
        ]

    unique_times = pd.Index(ordered_times).unique().sort_values()
    try:
        cuts = _cut_points(unique_times, mode=cut_mode)
    except ValueError as exc:
        return _unavailable(str(exc), hard=True)
    if not cuts:
        return _unavailable("insufficient_unique_timestamps")
    binding = {**binding, "n_cuts": len(cuts)}

    findings: list[Finding] = []
    for cut in cuts:
        findings.append(
            _run_one_cut(
                panel=panel,
                ordered_times=ordered_times,
                cut=cut,
                fn=fn,
                binding=binding,
            )
        )
    if not panel.equals(caller_snapshot):
        findings.append(
            _finding(
                "CAUSALITY_PREFIX_RECOMPUTE",
                passed=False,
                message="prefix-recompute mutated the caller panel",
                details=binding,
            )
        )
    # Collapse: keep hard fails; sampled all-pass is non-proof SOFT_FAIL, never INFO pass.
    hard = [f for f in findings if (not f.passed) and f.severity is FindingSeverity.HARD_FAIL]
    if hard:
        return findings
    soft = [f for f in findings if not f.passed]
    if soft:
        return findings
    if cut_mode == "sampled":
        return [
            _finding(
                "CAUSALITY_PREFIX_SAMPLED_NON_PROOF",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message=(
                    "sampled prefix cuts are a non-proof schedule; "
                    "use cut_mode='full' for authoritative causality"
                ),
                details={
                    **binding,
                    "cuts": [str(c) for c in cuts],
                    "n_cuts": len(cuts),
                    "cut_mode": "sampled",
                },
            )
        ]
    return [
        _finding(
            "CAUSALITY_PREFIX_RECOMPUTE",
            passed=True,
            severity=FindingSeverity.INFO,
            message="prefix outputs unchanged across deterministic cut points",
            details={
                **binding,
                "cuts": [str(c) for c in cuts],
                "n_cuts": len(cuts),
            },
        )
    ]


def validate_output_alignment(
    *,
    values: pd.Series,
    valid_mask: pd.Series | None,
    panel: pd.DataFrame,
    warmup: int,
    missing_policy: str,
    symbol_level: str = "symbol",
    datetime_level: str | None = "eob",
    require_valid_mask: bool = False,
) -> list[Finding]:
    """Hard-fail on unexpected index/type/alignment/finiteness problems.

    ``valid_mask=True`` means the corresponding value is finite (not NaN/Inf).
    Warmup/interior NaN checks sort each symbol by the resolved datetime level
    without mutating the caller's index order.
    """
    findings: list[Finding] = []
    if not isinstance(values, pd.Series):
        return [
            _finding(
                "ALIGNMENT_INVALID_TYPE",
                passed=False,
                message="factor values must be a Series",
            )
        ]
    if not isinstance(values.index, pd.MultiIndex) or values.index.nlevels != 2:
        findings.append(
            _finding(
                "ALIGNMENT_INVALID_INDEX",
                passed=False,
                message="factor values require a two-level MultiIndex",
            )
        )
        return findings

    if list(values.index.names) != list(panel.index.names):
        findings.append(
            _finding(
                "ALIGNMENT_INDEX_NAMES",
                passed=False,
                message="factor index names/order must match panel exactly",
                details={
                    "values_names": list(values.index.names),
                    "panel_names": list(panel.index.names),
                },
            )
        )
    else:
        findings.append(
            _finding(
                "ALIGNMENT_INDEX_NAMES",
                passed=True,
                severity=FindingSeverity.INFO,
                message="index names and order match panel",
            )
        )

    if values.index.duplicated().any() or panel.index.duplicated().any():
        findings.append(
            _finding(
                "ALIGNMENT_DUPLICATE_INDEX",
                passed=False,
                message="factor/panel index contains duplicate keys",
            )
        )

    if not values.index.equals(panel.index):
        findings.append(
            _finding(
                "ALIGNMENT_INDEX_VALUES",
                passed=False,
                message="factor index keys must equal panel index keys",
                details={
                    "values_len": int(len(values)),
                    "panel_len": int(len(panel)),
                },
            )
        )
    else:
        findings.append(
            _finding(
                "ALIGNMENT_INDEX_VALUES",
                passed=True,
                severity=FindingSeverity.INFO,
                message="factor index keys match panel",
            )
        )

    if not pd.api.types.is_numeric_dtype(values.dtype) or pd.api.types.is_bool_dtype(
        values.dtype
    ):
        findings.append(
            _finding(
                "ALIGNMENT_NON_NUMERIC",
                passed=False,
                message="factor values must be real numeric",
            )
        )
        return findings

    arr = np.asarray(values.to_numpy(copy=True), dtype=float)
    n_inf = int(np.isinf(arr).sum())
    if n_inf:
        findings.append(
            _finding(
                "ALIGNMENT_NON_FINITE",
                passed=False,
                message="factor values contain +/-Inf",
                details={"inf_count": n_inf},
            )
        )

    if missing_policy not in {"keep_nan", "drop_nan"}:
        findings.append(
            _finding(
                "ALIGNMENT_INVALID_MISSING_POLICY",
                passed=False,
                message=f"unsupported missing_policy {missing_policy!r}",
            )
        )
        return findings

    if valid_mask is None:
        if require_valid_mask:
            findings.append(
                _finding(
                    "ALIGNMENT_MASK_REQUIRED",
                    passed=False,
                    message="valid_mask is required for evaluate after successful execution",
                )
            )
            return findings
        mask_bool: np.ndarray | None = None
    else:
        if not isinstance(valid_mask, pd.Series):
            findings.append(
                _finding(
                    "ALIGNMENT_MASK_TYPE",
                    passed=False,
                    message="valid_mask must be a Series when provided",
                )
            )
            return findings
        if not valid_mask.index.equals(values.index):
            findings.append(
                _finding(
                    "ALIGNMENT_MASK_INDEX",
                    passed=False,
                    message="valid_mask index must equal values index",
                )
            )
            return findings
        # Only real bool dtype, or pandas nullable Boolean without any pd.NA.
        # int64 / object / 0-1 numeric masks are rejected (1 == True must not pass).
        dtype = valid_mask.dtype
        is_nullable_bool = str(dtype) == "boolean" or isinstance(dtype, pd.BooleanDtype)
        is_numpy_bool = (not is_nullable_bool) and (
            dtype == np.dtype(bool) or str(dtype) == "bool"
        )
        if is_nullable_bool:
            if valid_mask.isna().any():
                findings.append(
                    _finding(
                        "ALIGNMENT_MASK_NULLABLE_NA",
                        passed=False,
                        message="valid_mask contains pd.NA; mask must be non-null boolean",
                        details={"na_count": int(valid_mask.isna().sum())},
                    )
                )
                return findings
            mask_bool = valid_mask.astype(bool).to_numpy()
        elif is_numpy_bool:
            mask_bool = valid_mask.to_numpy(dtype=bool, copy=False)
        else:
            findings.append(
                _finding(
                    "ALIGNMENT_MASK_DTYPE",
                    passed=False,
                    message="valid_mask must be real bool dtype (int/object/0-1 rejected)",
                    details={"dtype": str(dtype)},
                )
            )
            return findings

    names = list(values.index.names)
    if symbol_level in names:
        sym_pos = names.index(symbol_level)
    elif "symbol" in names:
        sym_pos = names.index("symbol")
    else:
        findings.append(
            _finding(
                "ALIGNMENT_SYMBOL_LEVEL",
                passed=False,
                message="cannot locate symbol level for per-symbol warmup checks",
            )
        )
        return findings

    if datetime_level is not None and datetime_level in names:
        dt_pos = names.index(datetime_level)
    elif None in names and datetime_level is None:
        dt_pos = names.index(None)
    elif "eob" in names:
        dt_pos = names.index("eob")
    else:
        # Fall back to the non-symbol level.
        dt_pos = 1 - sym_pos

    interior_violations = 0
    mask_mismatches = 0
    drop_nan_violations = 0
    # Iterate symbols without mutating caller order: work on a time-sorted view.
    for _symbol, group in values.groupby(level=sym_pos, sort=False):
        # Sort by datetime level for semantic warmup/interior checks.
        try:
            times = pd.to_datetime(group.index.get_level_values(dt_pos), errors="raise")
        except (TypeError, ValueError) as exc:
            findings.append(
                _finding(
                    "ALIGNMENT_TIME_CONVERSION",
                    passed=False,
                    message="datetime level unusable for warmup ordering",
                    details={"cause_type": type(exc).__name__},
                )
            )
            return findings
        order = np.argsort(times.to_numpy(), kind="mergesort")
        ordered_idx = group.index.take(order)
        vals = values.loc[ordered_idx]
        is_na = vals.isna().to_numpy()
        is_inf = np.isinf(np.asarray(vals.to_numpy(dtype=float)))
        is_nonfinite = is_na | is_inf
        if mask_bool is not None:
            m = mask_bool[values.index.get_indexer(ordered_idx)]
            for i in range(len(vals)):
                # valid_mask True <=> finite numeric
                if bool(m[i]) and bool(is_nonfinite[i]):
                    mask_mismatches += 1
                if (not bool(m[i])) and (not bool(is_nonfinite[i])):
                    mask_mismatches += 1
        if missing_policy == "drop_nan":
            drop_nan_violations += int(is_na.sum())
        else:
            seen_valid = False
            leading = 0
            for flag in is_na:
                if not flag:
                    seen_valid = True
                elif not seen_valid:
                    leading += 1
                else:
                    interior_violations += 1
            if leading > warmup:
                findings.append(
                    _finding(
                        "ALIGNMENT_WARMUP_EXCEEDED",
                        passed=False,
                        message="leading NaNs exceed declared warmup",
                        details={"warmup": warmup, "leading_nans": leading},
                    )
                )

    if mask_bool is not None:
        findings.append(
            _finding(
                "ALIGNMENT_MASK_VALUE_AGREEMENT",
                passed=mask_mismatches == 0 and n_inf == 0,
                message=(
                    "valid_mask agrees with value finiteness"
                    if mask_mismatches == 0 and n_inf == 0
                    else "valid_mask disagrees with finite values"
                ),
                details={"mismatches": mask_mismatches, "inf_count": n_inf},
            )
        )
    if missing_policy == "drop_nan":
        findings.append(
            _finding(
                "ALIGNMENT_DROP_NAN",
                passed=drop_nan_violations == 0,
                message=(
                    "drop_nan policy has no NaN values"
                    if drop_nan_violations == 0
                    else "drop_nan policy forbids NaN values"
                ),
                details={"nan_count": drop_nan_violations},
            )
        )
    else:
        findings.append(
            _finding(
                "ALIGNMENT_KEEP_NAN_INTERIOR",
                passed=interior_violations == 0,
                message=(
                    "no unexpected interior NaNs after warmup"
                    if interior_violations == 0
                    else "interior NaNs after warmup are not allowed"
                ),
                details={"interior_nans": interior_violations, "warmup": warmup},
            )
        )
    return findings


__all__ = [
    "BoundPrefixRecompute",
    "PrefixRecomputeFn",
    "validate_output_alignment",
    "verify_prefix_causality",
]
