"""Deterministic AnalyzeFacade: preflight / evaluate / compare_to_pool."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pandas as pd

from skills.analyze.causality import (
    BoundPrefixRecompute,
    _exact_numeric_equal,
    validate_output_alignment,
    verify_prefix_causality,
)
from skills.analyze.content_fingerprint import fingerprint_frame, fingerprint_series
from skills.analyze.contracts import (
    ANALYZE_SCHEMA_VERSION,
    ENGINE_VERSION,
    AnalyzeResult,
    ArtifactBundle,
    CompletionStatus,
    EvidenceItem,
    Finding,
    FindingSeverity,
    FormalBacktestPair,
    MetricResult,
    ProtocolSnapshot,
    SectionResult,
    SectionStatus,
    SpecSnapshot,
    UncertaintyResult,
    content_hash,
    has_hard_fail,
    protocol_content_hash,
    sorted_findings,
)
from skills.analyze.factor_evaluation import (
    BacktesterFactory,
    compute_predictive_metrics,
    run_formal_backtest,
)
from skills.analyze.factor_incremental import compare_candidate_to_pool
from skills.analyze.factor_robustness import compute_robustness
from skills.analyze.spec_checks import validate_spec
from skills.analyze.validation import identify_levels, validate_panel

PrefixRecomputeFactory = Callable[[SpecSnapshot], BoundPrefixRecompute]


def _section(
    name: str,
    findings: Sequence[Finding],
    metrics: Sequence[MetricResult] = (),
    uncertainty: Sequence[UncertaintyResult] = (),
    *,
    notes: str = "",
    forced_status: SectionStatus | None = None,
) -> SectionResult:
    findings_t = sorted_findings(findings)
    if forced_status is not None:
        status = forced_status
    elif has_hard_fail(findings_t):
        status = SectionStatus.FAILED
    elif any(not f.passed for f in findings_t) or any(m.unavailable_reason for m in metrics) or any(
        u.unavailable_reason for u in uncertainty
    ):
        status = SectionStatus.PARTIAL
    else:
        status = SectionStatus.COMPLETE
    return SectionResult(
        name=name,
        status=status,
        findings=findings_t,
        metrics=tuple(metrics),
        uncertainty=tuple(uncertainty),
        notes=notes,
    )


def _evidence_from_sections(
    sections: Sequence[SectionResult],
) -> tuple[EvidenceItem, ...]:
    items: list[EvidenceItem] = []
    for section in sections:
        payload = {
            "findings": [
                {
                    "name": f.name,
                    "passed": f.passed,
                    "severity": f.severity.value,
                    "message": f.message,
                    "details": dict(f.details),
                }
                for f in section.findings
            ],
            "metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "unit": m.unit,
                    "sample_range": m.sample_range,
                    "unavailable_reason": m.unavailable_reason,
                }
                for m in section.metrics
            ],
            "uncertainty": [
                {
                    "name": u.name,
                    "method": u.method,
                    "estimates": dict(u.estimates),
                    "unavailable_reason": u.unavailable_reason,
                }
                for u in section.uncertainty
            ],
            "status": section.status.value,
            "notes": section.notes,
        }
        items.append(
            EvidenceItem(
                evidence_id=f"{section.name}:{content_hash(payload)[:16]}",
                section=section.name,
                summary=f"{section.name} status={section.status.value}",
                content_hash=content_hash(payload),
                details={"status": section.status.value},
            )
        )
    return tuple(items)


def _finalize(
    *,
    operation: str,
    protocol: ProtocolSnapshot,
    input_hashes: Mapping[str, str],
    sections: Sequence[SectionResult],
    tables: Mapping[str, Any],
) -> AnalyzeResult:
    findings = sorted_findings([f for section in sections for f in section.findings])
    metrics = tuple(
        sorted(
            (m for section in sections for m in section.metrics),
            key=lambda item: item.name,
        )
    )
    uncertainty = tuple(
        sorted(
            (u for section in sections for u in section.uncertainty),
            key=lambda item: item.name,
        )
    )
    hard = has_hard_fail(findings)
    if hard:
        completion = CompletionStatus.HARD_FAILED
    elif any(section.status is SectionStatus.PARTIAL for section in sections):
        completion = CompletionStatus.PARTIAL
    else:
        completion = CompletionStatus.COMPLETE
    evidence = _evidence_from_sections(sections)
    return AnalyzeResult(
        operation=operation,
        engine_version=ENGINE_VERSION,
        schema_version=ANALYZE_SCHEMA_VERSION,
        input_hashes=dict(input_hashes),
        protocol=protocol,
        completion_status=completion,
        sections=tuple(sections),
        findings=findings,
        metrics=metrics,
        uncertainty=uncertainty,
        evidence=evidence,
        artifacts=ArtifactBundle(tables=dict(tables)),
        hard_failed=hard,
    )


def _resolve_bound_recompute(
    factory: PrefixRecomputeFactory | BoundPrefixRecompute | None,
    spec: SpecSnapshot,
) -> BoundPrefixRecompute | None:
    if factory is None:
        return None
    if isinstance(factory, BoundPrefixRecompute):
        return factory
    return factory(spec)


class AnalyzeFacade:
    """Read-only deterministic analysis entrypoint (no implicit I/O)."""

    def __init__(
        self,
        *,
        backtester_factory: BacktesterFactory | None = None,
        prefix_recompute: PrefixRecomputeFactory | BoundPrefixRecompute | None = None,
        allowed_functions: frozenset[tuple[str, str]] | None = None,
    ) -> None:
        self._backtester_factory = backtester_factory
        self._prefix_recompute = prefix_recompute
        self._allowed_functions = allowed_functions

    def preflight(
        self,
        *,
        panel: pd.DataFrame,
        spec: SpecSnapshot,
        protocol: ProtocolSnapshot,
        allowed_fields: Sequence[str] | None = None,
        prefix_recompute: PrefixRecomputeFactory | BoundPrefixRecompute | None = None,
    ) -> AnalyzeResult:
        """Hard checks before factor execution / return-based scoring."""
        panel_findings, panel_metrics, panel_facts = validate_panel(
            panel,
            protocol,
            allowed_fields=allowed_fields,
        )
        spec_findings = validate_spec(
            spec,
            allowed_functions=self._allowed_functions,
            allowed_fields=allowed_fields,
            protocol_fields=protocol.required_fields,
        )
        if protocol.direction != spec.expected_direction:
            spec_findings.append(
                Finding(
                    name="SPEC_DIRECTION_MISMATCH",
                    severity=FindingSeverity.HARD_FAIL,
                    passed=False,
                    message="protocol.direction must equal spec.expected_direction",
                    details={
                        "protocol_direction": protocol.direction,
                        "expected_direction": spec.expected_direction,
                    },
                )
            )
        causality_findings: list[Finding] = [
            f for f in spec_findings if f.name.startswith("CAUSALITY_")
        ]
        formula_findings = [
            f for f in spec_findings if not f.name.startswith("CAUSALITY_")
        ]
        bound = _resolve_bound_recompute(
            prefix_recompute if prefix_recompute is not None else self._prefix_recompute,
            spec,
        )
        if isinstance(panel, pd.DataFrame) and isinstance(panel.index, pd.MultiIndex):
            _, _, datetime_pos = identify_levels(panel.index, protocol)
            if datetime_pos is not None:
                causality_findings.extend(
                    verify_prefix_causality(
                        panel,
                        datetime_pos=datetime_pos,
                        recompute=bound,
                        spec=spec,
                        require_prefix_recompute=protocol.require_prefix_recompute,
                    )
                )
            else:
                causality_findings.append(
                    Finding(
                        name="CAUSALITY_PREFIX_RECOMPUTE",
                        severity=FindingSeverity.SOFT_FAIL,
                        passed=False,
                        message="prefix-recompute skipped due to invalid index",
                        details={
                            "reason": "invalid_index",
                            "spec_content_hash": spec.content_hash,
                        },
                    )
                )
        else:
            causality_findings.append(
                Finding(
                    name="CAUSALITY_PREFIX_RECOMPUTE",
                    severity=FindingSeverity.SOFT_FAIL,
                    passed=False,
                    message="prefix-recompute skipped due to invalid panel",
                    details={
                        "reason": "invalid_panel",
                        "spec_content_hash": spec.content_hash,
                    },
                )
            )

        sections = [
            _section("data_quality", panel_findings, panel_metrics),
            _section("formula_safety", formula_findings),
            _section("causality", causality_findings),
            _section(
                "alignment",
                (),
                forced_status=SectionStatus.NOT_RUN,
                notes="alignment requires execution outputs",
            ),
            _section(
                "predictive",
                (),
                forced_status=SectionStatus.NOT_RUN,
            ),
            _section(
                "robustness",
                (),
                forced_status=SectionStatus.NOT_RUN,
            ),
            _section(
                "trading",
                (),
                forced_status=SectionStatus.NOT_RUN,
            ),
            _section(
                "pool_incremental",
                (),
                forced_status=SectionStatus.NOT_RUN,
            ),
        ]
        panel_hash = str(panel_facts.get("panel_hash", ""))
        if not panel_hash and isinstance(panel, pd.DataFrame):
            panel_hash = fingerprint_frame(panel)
        input_hashes = {
            "panel": panel_hash,
            "spec": spec.content_hash,
            "protocol": protocol_content_hash(protocol),
            "recompute_binding": (
                f"{bound.spec_content_hash}:{bound.formula_fingerprint}:{bound._seal}"
                if bound is not None
                else "unbound"
            ),
        }
        return _finalize(
            operation="preflight",
            protocol=protocol,
            input_hashes=input_hashes,
            sections=sections,
            tables={"panel_facts": panel_facts},
        )

    def evaluate(
        self,
        *,
        panel: pd.DataFrame,
        spec: SpecSnapshot,
        protocol: ProtocolSnapshot,
        values: pd.Series,
        valid_mask: pd.Series | None = None,
        execution_fingerprint: str | None = None,
        data_version: str | None = None,
        allowed_fields: Sequence[str] | None = None,
        regime_masks: Mapping[str, pd.Series] | None = None,
        parameter_outputs: Mapping[str, pd.Series] | None = None,
        include_backtest: bool = True,
        prefix_recompute: PrefixRecomputeFactory | BoundPrefixRecompute | None = None,
        formal_returns: pd.Series | None = None,
        candidate_returns: pd.DataFrame | None = None,
        liquidity_scores: pd.Series | None = None,
        volatility_scores: pd.Series | None = None,
        time_subsample_masks: Mapping[str, pd.Series] | None = None,
    ) -> AnalyzeResult:
        """Run alignment + predictive + robustness + optional formal backtest."""
        pre = self.preflight(
            panel=panel,
            spec=spec,
            protocol=protocol,
            allowed_fields=allowed_fields,
            prefix_recompute=prefix_recompute,
        )
        tables: dict[str, Any] = {"preflight": dict(pre.artifacts.tables)}
        values_hash = fingerprint_series(values) if isinstance(values, pd.Series) else ""
        mask_hash = (
            fingerprint_series(valid_mask) if isinstance(valid_mask, pd.Series) else ""
        )
        if pre.hard_failed:
            blocked = [
                section
                for section in pre.sections
                if section.name
                in {"data_quality", "formula_safety", "causality"}
            ]
            blocked.extend(
                [
                    _section(
                        "alignment",
                        [
                            Finding(
                                name="ALIGNMENT_SKIPPED",
                                severity=FindingSeverity.HARD_FAIL,
                                passed=False,
                                message="skipped due to hard preflight failure",
                                details={"root_hard_failed": True},
                            )
                        ],
                    ),
                    _section(
                        "predictive",
                        [
                            Finding(
                                name="EVALUATION_SKIPPED",
                                severity=FindingSeverity.HARD_FAIL,
                                passed=False,
                                message="skipped due to hard preflight failure",
                                details={"root_hard_failed": True},
                            )
                        ],
                    ),
                    _section(
                        "robustness",
                        [
                            Finding(
                                name="ROBUSTNESS_SKIPPED",
                                severity=FindingSeverity.HARD_FAIL,
                                passed=False,
                                message="skipped due to hard preflight failure",
                                details={"root_hard_failed": True},
                            )
                        ],
                    ),
                    _section(
                        "trading",
                        [
                            Finding(
                                name="BACKTEST_SKIPPED",
                                severity=FindingSeverity.HARD_FAIL,
                                passed=False,
                                message="skipped due to hard preflight failure",
                                details={"root_hard_failed": True},
                            )
                        ],
                    ),
                    _section(
                        "pool_incremental",
                        (),
                        forced_status=SectionStatus.NOT_RUN,
                    ),
                ]
            )
            return _finalize(
                operation="evaluate",
                protocol=protocol,
                input_hashes={
                    **dict(pre.input_hashes),
                    "values": values_hash,
                    "valid_mask": mask_hash,
                },
                sections=blocked,
                tables=tables,
            )

        align_findings = validate_output_alignment(
            values=values,
            valid_mask=valid_mask,
            panel=panel,
            warmup=spec.warmup,
            missing_policy=spec.missing_policy,
            symbol_level=protocol.symbol_level,
            datetime_level=protocol.datetime_level,
            require_valid_mask=True,
        )
        # Issued recompute must reproduce the evaluated values (rejects sealed zeros).
        bound_eval = _resolve_bound_recompute(
            prefix_recompute if prefix_recompute is not None else self._prefix_recompute,
            spec,
        )
        if bound_eval is not None and isinstance(values, pd.Series):
            panel_snap = panel.copy(deep=True) if isinstance(panel, pd.DataFrame) else None
            try:
                recomputed = bound_eval.recompute(panel.copy(deep=True))
            except Exception as exc:  # noqa: BLE001
                align_findings.append(
                    Finding(
                        name="CAUSALITY_RECOMPUTE_VALUE_MISMATCH",
                        severity=FindingSeverity.HARD_FAIL,
                        passed=False,
                        message="issued prefix recompute failed while matching values",
                        details={"cause_type": type(exc).__name__},
                    )
                )
            else:
                if panel_snap is not None and not panel.equals(panel_snap):
                    align_findings.append(
                        Finding(
                            name="CAUSALITY_FULL_INPUT_MUTATED",
                            severity=FindingSeverity.HARD_FAIL,
                            passed=False,
                            message="recompute mutated panel while matching values",
                        )
                    )
                elif not isinstance(recomputed, pd.Series) or not _exact_numeric_equal(
                    recomputed.reindex(values.index).astype(float),
                    values.astype(float),
                ):
                    align_findings.append(
                        Finding(
                            name="CAUSALITY_RECOMPUTE_VALUE_MISMATCH",
                            severity=FindingSeverity.HARD_FAIL,
                            passed=False,
                            message=(
                                "issued prefix recompute does not reproduce "
                                "execution values for this SpecSnapshot"
                            ),
                        )
                    )
        if execution_fingerprint is not None and not execution_fingerprint.strip():
            align_findings.append(
                Finding(
                    name="ALIGNMENT_EXECUTION_IDENTITY",
                    severity=FindingSeverity.HARD_FAIL,
                    passed=False,
                    message="execution fingerprint must be non-empty when provided",
                )
            )
        if data_version is not None and data_version != "":
            align_findings.append(
                Finding(
                    name="ALIGNMENT_DATA_VERSION",
                    severity=FindingSeverity.INFO,
                    passed=True,
                    message="data_version recorded",
                    details={"data_version": data_version},
                )
            )

        if has_hard_fail(align_findings):
            sections = [
                s
                for s in pre.sections
                if s.name in {"data_quality", "formula_safety", "causality"}
            ]
            sections.append(_section("alignment", align_findings))
            sections.extend(
                [
                    _section(
                        "predictive",
                        [
                            Finding(
                                name="EVALUATION_SKIPPED",
                                severity=FindingSeverity.HARD_FAIL,
                                passed=False,
                                message="skipped due to hard alignment failure",
                                details={"root_hard_failed": True},
                            )
                        ],
                    ),
                    _section(
                        "robustness",
                        [
                            Finding(
                                name="ROBUSTNESS_SKIPPED",
                                severity=FindingSeverity.HARD_FAIL,
                                passed=False,
                                message="skipped due to hard alignment failure",
                                details={"root_hard_failed": True},
                            )
                        ],
                    ),
                    _section(
                        "trading",
                        [
                            Finding(
                                name="BACKTEST_SKIPPED",
                                severity=FindingSeverity.HARD_FAIL,
                                passed=False,
                                message="skipped due to hard alignment failure",
                                details={"root_hard_failed": True},
                            )
                        ],
                    ),
                    _section(
                        "pool_incremental",
                        (),
                        forced_status=SectionStatus.NOT_RUN,
                    ),
                ]
            )
            return _finalize(
                operation="evaluate",
                protocol=protocol,
                input_hashes={
                    **dict(pre.input_hashes),
                    "values": values_hash,
                    "valid_mask": mask_hash,
                    "execution_fingerprint": execution_fingerprint or "",
                },
                sections=sections,
                tables=tables,
            )

        pred_findings, pred_metrics, pred_unc, pred_tables = compute_predictive_metrics(
            panel, values, protocol
        )
        tables["predictive"] = pred_tables
        rob_findings, rob_metrics, rob_unc, rob_tables = compute_robustness(
            panel,
            values,
            protocol,
            regime_masks=regime_masks,
            time_subsample_masks=time_subsample_masks,
            parameter_outputs=parameter_outputs,
            liquidity_scores=liquidity_scores,
            volatility_scores=volatility_scores,
            formal_returns=formal_returns,
            candidate_returns=candidate_returns,
        )
        tables["robustness"] = rob_tables

        if include_backtest:
            bt_findings, bt_metrics, bt_tables = run_formal_backtest(
                panel,
                values,
                protocol,
                backtester_factory=self._backtester_factory,
            )
            tables["trading"] = bt_tables
        else:
            bt_findings = [
                Finding(
                    name="BACKTEST_NOT_REQUESTED",
                    severity=FindingSeverity.INFO,
                    passed=True,
                    message="formal backtest not requested",
                )
            ]
            bt_metrics = []

        sections = [
            s
            for s in pre.sections
            if s.name in {"data_quality", "formula_safety", "causality"}
        ]
        sections.extend(
            [
                _section("alignment", align_findings),
                _section("predictive", pred_findings, pred_metrics, pred_unc),
                _section("robustness", rob_findings, rob_metrics, rob_unc),
                _section("trading", bt_findings, bt_metrics),
                _section(
                    "pool_incremental",
                    (),
                    forced_status=SectionStatus.NOT_RUN,
                    notes="use compare_to_pool",
                ),
            ]
        )
        input_hashes = {
            **dict(pre.input_hashes),
            "values": values_hash,
            "valid_mask": mask_hash,
            "execution_fingerprint": execution_fingerprint or "",
        }
        return _finalize(
            operation="evaluate",
            protocol=protocol,
            input_hashes=input_hashes,
            sections=sections,
            tables=tables,
        )

    def compare_to_pool(
        self,
        *,
        panel: pd.DataFrame,
        protocol: ProtocolSnapshot,
        candidate: pd.Series,
        pool: Mapping[str, pd.Series] | Sequence[Any] | None,
        formal_before_after: FormalBacktestPair | None = None,
    ) -> AnalyzeResult:
        # Preflight panel levels before pool stats so hard index failures surface.
        panel_findings, panel_metrics, panel_facts = validate_panel(panel, protocol)
        if has_hard_fail(panel_findings):
            sections = [
                _section("data_quality", panel_findings, panel_metrics),
                _section(
                    "formula_safety",
                    (),
                    forced_status=SectionStatus.NOT_RUN,
                ),
                _section(
                    "causality",
                    (),
                    forced_status=SectionStatus.NOT_RUN,
                ),
                _section(
                    "alignment",
                    (),
                    forced_status=SectionStatus.NOT_RUN,
                ),
                _section(
                    "predictive",
                    (),
                    forced_status=SectionStatus.NOT_RUN,
                ),
                _section(
                    "robustness",
                    (),
                    forced_status=SectionStatus.NOT_RUN,
                ),
                _section(
                    "trading",
                    (),
                    forced_status=SectionStatus.NOT_RUN,
                ),
                _section(
                    "pool_incremental",
                    [
                        Finding(
                            name="POOL_SKIPPED",
                            severity=FindingSeverity.HARD_FAIL,
                            passed=False,
                            message="skipped due to hard panel validation failure",
                            details={"root_hard_failed": True},
                        )
                    ],
                ),
            ]
            return _finalize(
                operation="compare_to_pool",
                protocol=protocol,
                input_hashes={
                    "protocol": protocol_content_hash(protocol),
                    "panel": str(panel_facts.get("panel_hash", "")),
                    "candidate": fingerprint_series(candidate)
                    if isinstance(candidate, pd.Series)
                    else "",
                },
                sections=sections,
                tables={"panel_facts": panel_facts},
            )

        findings, metrics, tables = compare_candidate_to_pool(
            panel,
            candidate,
            pool,
            protocol,
            formal_before_after=formal_before_after,
        )
        sections = [
            _section(
                "data_quality",
                panel_findings,
                panel_metrics,
            ),
            _section(
                "formula_safety",
                (),
                forced_status=SectionStatus.NOT_RUN,
            ),
            _section(
                "causality",
                (),
                forced_status=SectionStatus.NOT_RUN,
            ),
            _section(
                "alignment",
                (),
                forced_status=SectionStatus.NOT_RUN,
            ),
            _section(
                "predictive",
                (),
                forced_status=SectionStatus.NOT_RUN,
            ),
            _section(
                "robustness",
                (),
                forced_status=SectionStatus.NOT_RUN,
            ),
            _section(
                "trading",
                (),
                forced_status=SectionStatus.NOT_RUN,
            ),
            _section("pool_incremental", findings, metrics),
        ]
        pool_hashes: dict[str, str] = {}
        if isinstance(pool, Mapping):
            for name, series in sorted(pool.items()):
                if isinstance(series, pd.Series):
                    pool_hashes[str(name)] = fingerprint_series(series)
        elif isinstance(pool, Sequence):
            for member in pool:
                if hasattr(member, "ref_object_id") and hasattr(member, "values"):
                    series = member.values
                    if isinstance(series, pd.Series):
                        pool_hashes[str(member.ref_object_id)] = fingerprint_series(
                            series
                        )
        return _finalize(
            operation="compare_to_pool",
            protocol=protocol,
            input_hashes={
                "protocol": protocol_content_hash(protocol),
                "panel": str(panel_facts.get("panel_hash", "")),
                "candidate": fingerprint_series(candidate),
                "pool": content_hash(pool_hashes),
            },
            sections=sections,
            tables={"pool_incremental": tables, "panel_facts": panel_facts},
        )


__all__ = ["AnalyzeFacade", "BoundPrefixRecompute", "PrefixRecomputeFactory"]
