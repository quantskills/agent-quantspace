"""Governed factor-mining run for the public 18-ETF asset-class universe.

This is deliberately thin orchestration. Factor values are issued by the
factor-mining Compute adapter and predictive statistics are issued by Analyze.
The sealed split is not loaded during screening.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from skills.analyze.contracts import ProtocolSnapshot, SpecSnapshot, json_safe
from skills.analyze.facade import AnalyzeFacade
from skills.analyze.factor_evaluation import compute_predictive_metrics
from skills.factor_mining import (
    FactorComputeRequest,
    FactorSpec,
    FormulaKind,
    FunctionRef,
    ObjectRef,
    Provenance,
    StructuredFormula,
)
from skills.factor_mining.adapters import (
    DataManagerArtifactStore,
    FactorExecutionAdapter,
    build_prefix_recompute_capability,
    load_execution_series,
)
from skills.store.data_manager import DataManager
from strategies.cross_sectional.asset_class_rotation import ASSET_CLASS_ETF_UNIVERSE

BRIEF_ID = "etf18-rankic20-2019-20260804-v1"
BRIEF_HASH = "2e90b7822b5d0fc3574a50464be1dea1c67c5fadcc226066dfa0ea4cbe43509b"
NAMESPACE = "factor_mining.etf18.2019_20260804"
DATA_VERSION = "79da79e23754dd3f69d95f82747ac076525b81243b21dec8fcc4867422f4231b"
UNIVERSE = tuple(ASSET_CLASS_ETF_UNIVERSE.values())
RESEARCH_START = pd.Timestamp("2019-01-01")
TRAIN_END = pd.Timestamp("2022-12-31")
VALIDATION_START = pd.Timestamp("2023-01-01")
VALIDATION_END = pd.Timestamp("2024-12-31")
SEALED_START = pd.Timestamp("2025-01-01")
FULL_END = pd.Timestamp("2026-08-04")
IC_THRESHOLD = 0.03
SELECTED_FACTOR_IDS = (
    "trend-bias-momentum-60-20-v1",
    "trend-roc-20-v1",
    "trend-mom-skip-126-21-v1",
)
CANDIDATE_COUNT = 20


@dataclass(frozen=True)
class Candidate:
    factor_id: str
    family: str
    direction: str
    function_name: str
    params: dict[str, Any]
    required_fields: tuple[str, ...]
    window: int
    warmup: int
    hypothesis: str


def _c(
    factor_id: str,
    family: str,
    direction: str,
    function_name: str,
    params: dict[str, Any],
    required_fields: tuple[str, ...],
    window: int,
    warmup: int,
    hypothesis: str,
) -> Candidate:
    return Candidate(
        factor_id, family, direction, function_name, params,
        required_fields, window, warmup, hypothesis,
    )


def candidates() -> list[Candidate]:
    """The three isolated generator-role handoffs, frozen before evaluation."""
    return [
        # Trend / momentum generator (9)
        _c("trend-roc-20-v1", "trend_momentum", "long_high", "roc", {"period": 20}, ("close",), 20, 20, "过去一个月的相对强势在ETF横截面中会延续至随后20个交易日。"),
        _c("trend-roc-60-v1", "trend_momentum", "long_high", "roc", {"period": 60}, ("close",), 60, 60, "过去约一季的跨ETF相对收益反映中期资金配置趋势。"),
        _c("trend-mom-skip-63-5-v1", "trend_momentum", "long_high", "mom_skip", {"skip": 5, "total": 63}, ("close",), 63, 63, "剔除最近一周噪声后的三个月相对动量。"),
        _c("trend-mom-skip-126-21-v1", "trend_momentum", "long_high", "mom_skip", {"skip": 21, "total": 126}, ("close",), 126, 126, "剔除最近一月后的半年相对动量。"),
        _c("trend-ma-deviation-50-v1", "trend_momentum", "long_high", "ma", {"period": 50}, ("close",), 50, 50, "价格相对50日均线的标准化偏离反映趋势位置。"),
        _c("trend-ma-cross-10-50-v1", "trend_momentum", "long_high", "ma_cross", {"short": 10, "long": 50}, ("close",), 50, 50, "10日与50日均线差值刻画多尺度趋势。"),
        _c("trend-bias-momentum-60-20-v1", "trend_momentum", "long_high", "bias_momentum", {"ma_period": 60, "momentum_day": 20}, ("close",), 60, 79, "60日均线乖离率的20日趋势刻画趋势扩张。"),
        _c("trend-score-60-v1", "trend_momentum", "long_high", "trend_score", {"period": 60}, ("close",), 60, 60, "60日对数价格斜率乘拟合优度刻画趋势质量。"),
        _c("trend-score-skip-126-21-v1", "trend_momentum", "long_high", "trend_score_v2_skip", {"period": 126, "skip": 21}, ("close",), 126, 126, "剔除最近一月的半年趋势质量。"),
        # Mean reversion / price structure generator (8)
        _c("mrps-daily-return-1d-v1", "mean_reversion_price_structure", "long_low", "daily_return", {}, ("close",), 1, 1, "单日相对大跌的ETF在未来20日更可能反弹。"),
        _c("mrps-roc-5d-v1", "mean_reversion_price_structure", "long_low", "roc", {"period": 5}, ("close",), 5, 5, "5日相对收益的极端偏离会均值回归。"),
        _c("mrps-ma-deviation-20d-v1", "mean_reversion_price_structure", "long_low", "ma", {"period": 20}, ("close",), 20, 20, "价格相对20日均线的偏离会回归。"),
        _c("mrps-ma-cross-stretch-5x20-v1", "mean_reversion_price_structure", "long_low", "ma_cross", {"short": 5, "long": 20}, ("close",), 20, 20, "5日与20日均线的极端张口会收敛。"),
        _c("mrps-cci-20d-v1", "mean_reversion_price_structure", "long_low", "cci", {"period": 20}, ("high", "low", "close"), 20, 20, "极端CCI刻画超买超卖后的反转。"),
        _c("mrps-slowkdj-14-3-3-v1", "mean_reversion_price_structure", "long_high", "slowkdj", {"k_period": 14, "k_smooth": 3, "d_smooth": 3, "standardize_window": 60}, ("high", "low", "close"), 60, 30, "慢速KDJ的超卖结构预示反转。"),
        _c("mrps-williams-r-14d-v1", "mean_reversion_price_structure", "long_low", "williams_r", {"period": 14, "standardize_window": 60}, ("high", "low", "close"), 60, 26, "Williams %R的区间极值会回归。"),
        _c("mrps-rsi-divergence-14x20-v1", "mean_reversion_price_structure", "long_high", "rsi_divergence", {"rsi_period": 14, "divergence_period": 20, "standardize_window": 60}, ("close",), 60, 32, "价格与RSI背离刻画动量耗竭。"),
        # Volume / liquidity generator (3)
        _c("volliq-orb-relvol-05-v1", "volume_liquidity", "long_high", "orb_relvol", {"period": 5}, ("volume",), 5, 0, "5日相对成交量刻画参与度冲击。"),
        _c("volliq-orb-relvol-20-v1", "volume_liquidity", "long_high", "orb_relvol", {"period": 20}, ("volume",), 20, 0, "20日相对成交量刻画量能确认。"),
        _c("volliq-orb-relvol-60-v1", "volume_liquidity", "long_high", "orb_relvol", {"period": 60}, ("volume",), 60, 0, "60日相对成交量刻画长期量能异常。"),
    ]


def _brief_ref() -> ObjectRef:
    return ObjectRef(
        object_type="ResearchBrief", object_id=BRIEF_ID,
        content_hash=BRIEF_HASH, namespace=NAMESPACE,
    )


def _spec(candidate: Candidate) -> FactorSpec:
    brief_ref = _brief_ref()
    return FactorSpec(
        factor_id=candidate.factor_id,
        revision=1,
        brief_ref=brief_ref,
        family=candidate.family,
        hypothesis=candidate.hypothesis,
        expected_direction=candidate.direction,
        required_fields=candidate.required_fields,
        formula=StructuredFormula(
            kind=FormulaKind.FUNCTION_REF,
            function_ref=FunctionRef(
                module="skills.compute.indicators", name=candidate.function_name,
            ),
            params=candidate.params,
        ),
        window=candidate.window,
        lag=0,
        warmup=candidate.warmup,
        missing_policy="keep_nan",
        availability_rule="Only point-in-time bars through close[t]; keep missing values as NaN.",
        output_dtype="float64",
        index_restore_policy="restore_original_names_and_order",
        provenance=Provenance(
            producer=f"{candidate.family}_generator",
            data_version=DATA_VERSION,
            code_version="factor_mining.adapters.compute@1.0.0",
            experiment_version=BRIEF_ID,
            namespace=NAMESPACE,
            input_refs=(brief_ref,),
            created_at="2026-08-05T00:00:00+08:00",
        ),
        applicable_regimes=("cross_sectional_etf_rotation",),
        known_relations=(candidate.family,),
        falsification_tests=(
            "Frozen train/validation 20-bar Rank-IC direction must agree.",
            "Prefix recompute must reproduce values without future bars.",
        ),
    )


def _protocol(spec: FactorSpec) -> ProtocolSnapshot:
    return ProtocolSnapshot(
        horizon_bars=20,
        direction=spec.expected_direction,
        n_groups=3,
        tie_rule="average",
        rebalance="monthly",
        commission=0.0003,
        slippage=0.0002,
        parameter_neighborhood={},
        regimes=(),
        time_subsamples=(),
        random_seed=20260805,
        multiple_testing_budget=CANDIDATE_COUNT,
        thresholds={"min_coverage": 0.60},
        symbol_level="symbol",
        datetime_level="eob",
        timezone="naive",
        required_fields=spec.required_fields,
        min_cross_section=6,
        min_ic_samples=60,
        bootstrap_samples=30,
        bootstrap_block_size=20,
        ic_decay_horizons=(5, 20, 60),
        trade_at="close",
        signal_lag=1,
        return_mode="forward",
        allow_short=False,
        require_prefix_recompute=True,
        universe=UNIVERSE,
    )


def _slice(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    dates = panel.index.get_level_values("eob")
    return panel.loc[(dates >= start) & (dates <= end)]


def _metric_map(panel: pd.DataFrame, values: pd.Series, protocol: ProtocolSnapshot) -> dict[str, Any]:
    findings, metrics, _uncertainty, _tables = compute_predictive_metrics(panel, values, protocol)
    out = {metric.name: metric.value for metric in metrics}
    out["hard_failed"] = any(
        (not finding.passed) and finding.severity.value == "hard_fail"
        for finding in findings
    )
    out["findings"] = [
        {"name": item.name, "passed": item.passed, "severity": item.severity.value}
        for item in findings
    ]
    return out


def _spec_snapshot(spec: FactorSpec, formula_fingerprint: str) -> SpecSnapshot:
    return SpecSnapshot(
        factor_id=spec.factor_id,
        formula_kind=spec.formula.kind.value,
        function_module=spec.formula.function_ref.module,
        function_name=spec.formula.function_ref.name,
        expression=None,
        params=dict(spec.formula.params),
        required_fields=spec.required_fields,
        window=spec.window,
        lag=spec.lag,
        warmup=spec.warmup,
        missing_policy=spec.missing_policy,
        output_dtype=spec.output_dtype,
        expected_direction=spec.expected_direction,
        content_hash=spec.content_hash,
        formula_fingerprint=formula_fingerprint,
    )


def run_screening(output_dir: Path) -> None:
    specs = [_spec(item) for item in candidates()]
    if len(specs) != CANDIDATE_COUNT or len({item.factor_id for item in specs}) != CANDIDATE_COUNT:
        raise RuntimeError(
            f"candidate budget must contain exactly {CANDIDATE_COUNT} unique FactorSpecs"
        )

    dm = DataManager()
    panel = dm.read_symbols(list(UNIVERSE), frequency="1d_adj")
    panel = _slice(panel, RESEARCH_START, VALIDATION_END).sort_index()
    if panel.empty or panel.index.get_level_values("eob").max() > VALIDATION_END:
        raise RuntimeError("screening panel violated sealed-data boundary")

    store = DataManagerArtifactStore(dm)
    spec_by_id = {item.factor_id: item for item in specs}
    adapter = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: spec_by_id[ref.object_id],
        resolve_panel=lambda request: panel,
        artifact_store=store,
    )
    train_panel = _slice(panel, RESEARCH_START, TRAIN_END)
    validation_panel = _slice(panel, VALIDATION_START, VALIDATION_END)
    rows: list[dict[str, Any]] = []

    for number, spec in enumerate(specs, start=1):
        factor_ref = ObjectRef(
            object_type="FactorSpec", object_id=spec.factor_id,
            content_hash=spec.content_hash, namespace=NAMESPACE,
        )
        execution = adapter.execute(
            FactorComputeRequest(
                request_id=f"screen-{number:02d}",
                namespace=NAMESPACE,
                experiment_id=f"screen-{BRIEF_ID}",
                execution_id=f"screen-{number:02d}-{spec.factor_id}",
                brief_ref=_brief_ref(),
                factor_ref=factor_ref,
                data_version=DATA_VERSION,
                split_id="train_validation",
            )
        )
        row: dict[str, Any] = {
            "factor_id": spec.factor_id,
            "family": spec.family,
            "direction": spec.expected_direction,
            "function_name": spec.formula.function_ref.name,
            "params": json.dumps(dict(spec.formula.params), ensure_ascii=False, sort_keys=True),
            "factor_spec_hash": spec.content_hash,
            "compute_failure": None if execution.failure is None else execution.failure.code.value,
        }
        if execution.failure is None and execution.values_ref is not None:
            values = load_execution_series(store, execution.values_ref)
            train_values = values.reindex(train_panel.index)
            validation_values = values.reindex(validation_panel.index)
            train = _metric_map(train_panel, train_values, _protocol(spec))
            validation = _metric_map(validation_panel, validation_values, _protocol(spec))
            for prefix, facts in (("train", train), ("validation", validation)):
                for key in (
                    "rank_ic_mean", "rank_ic_std", "rank_ic_ir",
                    "rank_ic_hac_t_stat", "rank_ic_hac_p_value",
                    "rank_ic_positive_ratio", "rank_ic_count", "hard_failed",
                ):
                    row[f"{prefix}_{key}"] = facts.get(key)
            row["qualified_research"] = bool(
                not train["hard_failed"]
                and not validation["hard_failed"]
                and train.get("rank_ic_mean") is not None
                and validation.get("rank_ic_mean") is not None
                and float(train["rank_ic_mean"]) > 0.0
                and float(validation["rank_ic_mean"]) >= IC_THRESHOLD
            )
        else:
            row["qualified_research"] = False
        rows.append(row)
        print(
            f"[{number:02d}/{CANDIDATE_COUNT}] {spec.factor_id}: "
            f"train={row.get('train_rank_ic_mean')} "
            f"validation={row.get('validation_rank_ic_mean')} "
            f"qualified={row['qualified_research']}",
            flush=True,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows).sort_values(
        ["qualified_research", "validation_rank_ic_mean"], ascending=[False, False],
        na_position="last",
    )
    frame.to_csv(output_dir / "screening_results.csv", index=False)
    (output_dir / "screening_manifest.json").write_text(
        json.dumps(
            json_safe(
                {
                    "brief_id": BRIEF_ID,
                    "brief_hash": BRIEF_HASH,
                    "namespace": NAMESPACE,
                    "data_version": DATA_VERSION,
                    "universe": UNIVERSE,
                    "data_source": "data/market/1d_adj",
                    "train": [str(RESEARCH_START.date()), str(TRAIN_END.date())],
                    "validation": [str(VALIDATION_START.date()), str(VALIDATION_END.date())],
                    "sealed": [str(SEALED_START.date()), str(FULL_END.date())],
                    "sealed_loaded": False,
                    "horizon_bars": 20,
                    "signal_lag": 1,
                    "ic_threshold": IC_THRESHOLD,
                    "candidate_count": len(specs),
                    "qualified_count": int(frame["qualified_research"].sum()),
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def run_final(output_dir: Path) -> None:
    """Open the sealed split once for the frozen screening selections."""
    screen_path = output_dir / "screening_results.csv"
    if not screen_path.exists():
        raise RuntimeError("screening results are required before final evaluation")
    screening = pd.read_csv(screen_path)
    frozen_ids = tuple(screening.loc[screening["qualified_research"], "factor_id"])
    if set(frozen_ids) != set(SELECTED_FACTOR_IDS) or len(frozen_ids) != len(
        SELECTED_FACTOR_IDS
    ):
        raise RuntimeError("screening selection changed; refusing to open sealed data")

    specs = {item.factor_id: item for item in map(_spec, candidates())}
    dm = DataManager()
    panel = dm.read_symbols(list(UNIVERSE), frequency="1d_adj")
    panel = _slice(panel, RESEARCH_START, FULL_END).sort_index()
    actual_end = panel.index.get_level_values("eob").max()
    if actual_end != FULL_END:
        raise RuntimeError(f"full panel end mismatch: {actual_end} != {FULL_END}")
    sealed_panel = _slice(panel, SEALED_START, FULL_END)
    if sealed_panel.empty:
        raise RuntimeError("sealed split is empty")

    store = DataManagerArtifactStore(dm)
    adapter = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: specs[ref.object_id],
        resolve_panel=lambda request: panel,
        artifact_store=store,
    )
    facade = AnalyzeFacade()
    rows: list[dict[str, Any]] = []
    formal_dir = output_dir / "formal_analyze"
    formal_dir.mkdir(parents=True, exist_ok=True)

    for number, factor_id in enumerate(SELECTED_FACTOR_IDS, start=1):
        spec = specs[factor_id]
        factor_ref = ObjectRef(
            object_type="FactorSpec", object_id=spec.factor_id,
            content_hash=spec.content_hash, namespace=NAMESPACE,
        )
        execution = adapter.execute(
            FactorComputeRequest(
                request_id=f"sealed-full-{number:02d}",
                namespace=NAMESPACE,
                experiment_id=f"sealed-full-{BRIEF_ID}",
                execution_id=f"sealed-full-{number:02d}-{factor_id}",
                brief_ref=_brief_ref(),
                factor_ref=factor_ref,
                data_version=DATA_VERSION,
                split_id="sealed_full_once",
                sealed_execution=True,
            )
        )
        if execution.failure is not None or execution.values_ref is None:
            raise RuntimeError(f"final compute failed for {factor_id}: {execution.failure}")
        values = load_execution_series(store, execution.values_ref)
        valid_mask = load_execution_series(store, execution.valid_mask_ref).astype(bool)
        protocol = _protocol(spec)
        full = _metric_map(panel, values, protocol)
        sealed = _metric_map(
            sealed_panel, values.reindex(sealed_panel.index), protocol,
        )
        capability = build_prefix_recompute_capability(
            factor=spec, execution=execution,
        )
        formal = facade.evaluate(
            panel=panel,
            spec=_spec_snapshot(spec, execution.callable_fingerprint),
            protocol=protocol,
            values=values,
            valid_mask=valid_mask,
            execution_fingerprint=execution.fingerprint,
            data_version=DATA_VERSION,
            allowed_fields=("open", "high", "low", "close", "volume"),
            include_backtest=False,
            prefix_recompute=capability,
        )
        (formal_dir / f"{factor_id}.json").write_text(
            json.dumps(formal.to_public_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        screen_row = screening.loc[screening["factor_id"] == factor_id].iloc[0]
        row = {
            "factor_id": factor_id,
            "family": spec.family,
            "direction": spec.expected_direction,
            "function_name": spec.formula.function_ref.name,
            "params": json.dumps(dict(spec.formula.params), ensure_ascii=False, sort_keys=True),
            "train_rank_ic_mean": screen_row["train_rank_ic_mean"],
            "validation_rank_ic_mean": screen_row["validation_rank_ic_mean"],
            "sealed_rank_ic_mean": sealed.get("rank_ic_mean"),
            "sealed_rank_ic_ir": sealed.get("rank_ic_ir"),
            "sealed_rank_ic_hac_t_stat": sealed.get("rank_ic_hac_t_stat"),
            "sealed_rank_ic_hac_p_value": sealed.get("rank_ic_hac_p_value"),
            "sealed_rank_ic_count": sealed.get("rank_ic_count"),
            "full_rank_ic_mean": full.get("rank_ic_mean"),
            "full_rank_ic_ir": full.get("rank_ic_ir"),
            "full_rank_ic_hac_t_stat": full.get("rank_ic_hac_t_stat"),
            "full_rank_ic_hac_p_value": full.get("rank_ic_hac_p_value"),
            "full_rank_ic_count": full.get("rank_ic_count"),
            "formal_hard_failed": formal.hard_failed,
            "full_qualified": bool(
                not formal.hard_failed
                and full.get("rank_ic_mean") is not None
                and float(full["rank_ic_mean"]) >= IC_THRESHOLD
            ),
        }
        rows.append(row)
        print(
            f"[{number}/{len(SELECTED_FACTOR_IDS)}] {factor_id}: "
            f"sealed={row['sealed_rank_ic_mean']} "
            f"full={row['full_rank_ic_mean']} qualified={row['full_qualified']}",
            flush=True,
        )

    final = pd.DataFrame(rows).sort_values("full_rank_ic_mean", ascending=False)
    final.to_csv(output_dir / "selected_factors.csv", index=False)
    (output_dir / "final_manifest.json").write_text(
        json.dumps(
            json_safe(
                {
                    "brief_id": BRIEF_ID,
                    "brief_hash": BRIEF_HASH,
                    "data_version": DATA_VERSION,
                    "data_source": "data/market/1d_adj",
                    "selected_before_sealed": SELECTED_FACTOR_IDS,
                    "sealed_opened_once": True,
                    "sealed_window": [str(SEALED_START.date()), str(FULL_END.date())],
                    "full_window": [str(RESEARCH_START.date()), str(FULL_END.date())],
                    "qualified_full_count": int(final["full_qualified"].sum()),
                    "ic_threshold": IC_THRESHOLD,
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/local/factor_mining_etf18_2019_20260804"),
    )
    parser.add_argument(
        "--phase", choices=("screening", "final"), default="screening",
    )
    args = parser.parse_args()
    if args.phase == "screening":
        run_screening(args.output_dir)
    else:
        run_final(args.output_dir)


if __name__ == "__main__":
    main()
