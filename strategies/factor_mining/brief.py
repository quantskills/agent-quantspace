"""Brief loading, content validation, and protocol mapping for factor mining."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skills.analyze import ProtocolSnapshot
from skills.factor_mining import (
    AcceptanceCriteria,
    CostConstraints,
    FactorSpec,
    Provenance,
    ResearchBrief,
    ResearchBudget,
    RiskConstraints,
    RobustnessGrid,
    SplitWindow,
    TradingConstraints,
    rebuild_dataclass,
    to_plain_dict,
)
from strategies.cross_sectional.asset_class_rotation import ASSET_CLASS_ETF_SYMBOLS

PROTOCOL_ID_PREFIX = "factor_mining.v1"
CODE_VERSION_WORKFLOW = "factor_mining.v1"
EXAMPLE_BRIEF_ID = "etf18-example-v1"


def load_brief(path: str | Path) -> ResearchBrief:
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"ResearchBrief not found: {path}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    brief = rebuild_dataclass(ResearchBrief, payload)
    brief.validate_hash()
    return brief


def dump_brief(brief: ResearchBrief, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(to_plain_dict(brief), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def protocol_id_for(spec: FactorSpec) -> str:
    return f"{PROTOCOL_ID_PREFIX}:{spec.factor_id}"


def protocol_for(brief: ResearchBrief, spec: FactorSpec) -> ProtocolSnapshot:
    """The one mapping from a Brief plus FactorSpec-owned direction/fields to a protocol."""

    thresholds: dict[str, Any] = {}
    if brief.acceptance.min_coverage is not None:
        thresholds["min_coverage"] = brief.acceptance.min_coverage
    if brief.acceptance.min_rank_ic_ir is not None:
        thresholds["min_rank_ic_ir"] = brief.acceptance.min_rank_ic_ir
    if brief.acceptance.max_turnover is not None:
        thresholds["max_turnover"] = brief.acceptance.max_turnover
    n_symbols = len(brief.universe)
    n_groups = min(5, max(2, n_symbols))
    min_cross_section = min(3, n_symbols) if n_symbols >= 3 else 2
    return ProtocolSnapshot(
        horizon_bars=brief.horizon_bars,
        direction=spec.expected_direction,
        n_groups=n_groups,
        tie_rule="average",
        rebalance=brief.rebalance,
        commission=float(brief.cost.commission),
        slippage=float(brief.cost.slippage),
        parameter_neighborhood={
            str(key): tuple(value)
            for key, value in dict(brief.robustness.parameter_neighborhood).items()
        },
        regimes=tuple(brief.robustness.regime_slices),
        time_subsamples=tuple(brief.robustness.time_subsamples),
        random_seed=int(brief.robustness.random_seed),
        multiple_testing_budget=int(brief.multiple_testing_budget),
        thresholds=thresholds,
        symbol_level=brief.symbol_level,
        datetime_level=brief.datetime_level,
        timezone=brief.timezone,
        required_fields=tuple(spec.required_fields),
        min_cross_section=min_cross_section,
        min_ic_samples=5,
        bootstrap_samples=20,
        bootstrap_block_size=3,
        ic_decay_horizons=(1,),
        trade_at="close",
        signal_lag=int(brief.trading.execution_delay_bars),
        return_mode="forward",
        allow_short=bool(brief.trading.allow_short),
        require_prefix_recompute=True,
        universe=tuple(brief.universe),
    )


def make_example_brief(*, data_version: str) -> ResearchBrief:
    """Example Brief on the 18 asset-class ETFs.

    ``data_version`` must be the fingerprint of the research-window panel
    (``research.research_data_version``); the ``init`` phase computes it from local data.
    The factor pool starts empty, so ``freeze_criteria.require_pool_incremental`` is
    false and at most one candidate can be frozen.
    """
    namespace = f"factor_mining.{EXAMPLE_BRIEF_ID}"
    provenance = Provenance(
        producer="factor_mining",
        data_version=data_version,
        code_version=CODE_VERSION_WORKFLOW,
        experiment_version=EXAMPLE_BRIEF_ID,
        namespace=namespace,
    )
    return ResearchBrief(
        brief_id=EXAMPLE_BRIEF_ID,
        market="CN",
        asset_class="etf",
        universe=tuple(ASSET_CLASS_ETF_SYMBOLS),
        frequency="1d_adj",
        allowed_fields=("open", "high", "low", "close", "volume"),
        symbol_level="symbol",
        datetime_level="eob",
        timezone="naive",
        adjustment="post",
        data_version=data_version,
        train=SplitWindow("train", "2019-01-01", "2022-12-31", sealed=False),
        validation=SplitWindow("validation", "2023-01-01", "2024-12-31", sealed=False),
        sealed=SplitWindow("sealed", "2025-01-01", "2026-08-04", sealed=True),
        horizon_bars=20,
        rebalance="monthly",
        cost=CostConstraints(commission=0.0003, slippage=0.0002),
        risk=RiskConstraints(max_weight=0.25),
        trading=TradingConstraints(
            long_only=True,
            allow_short=False,
            rebalance="monthly",
            execution_delay_bars=1,
        ),
        robustness=RobustnessGrid(random_seed=7),
        multiple_testing_budget=20,
        budget=ResearchBudget(
            max_candidates=12,
            max_experiments=40,
            max_revisions=2,
            max_debate_rounds=2,
        ),
        acceptance=AcceptanceCriteria(min_coverage=0.6),
        freeze_criteria=AcceptanceCriteria(require_pool_incremental=False),
        oos_criteria=AcceptanceCriteria(min_rank_ic_ir=0.0),
        provenance=provenance,
        notes=(
            "Example Brief for the 18 asset-class ETFs. data_version is the fingerprint "
            "of the research-window panel; a new sealed test needs a new Brief."
        ),
    )
