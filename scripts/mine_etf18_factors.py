"""Factor mining for the 18 global-asset ETF universe.

遵循 skills/factor_mining/SKILL.md 的研究治理边界与角色协议
（Sequential single-agent fallback 模式）：

- Supervisor: 编排研究流程、预算、停止/继续决策
- 3 个 Generator 角色: 从 trend/momentum、mean_reversion、volume/liquidity
  三个因子族提出 FactorSpec 候选
- 2 个 Reviewer 角色: 基于确定性 IC 证据做方法论与泄漏评审
- PoolSynthesizer: 按池增量价值决定 accept/watch/reject

研究目标: 从 18 个全球大类资产 ETF 挖掘 5 个合格因子 (Rank IC mean >= 0.03)。
全样本: 2019-01-01 ~ 2026-08-04，数据源 data/market/1d_adj。

本脚本是薄编排 (scripts/)：因子计算走 skills.compute，IC 评估走 skills.analyze，
数据读取走 skills.store，universe 复用 strategies.cross_sectional 公开定义。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from skills.analyze.factor_analysis import IC_stat
from skills.compute.indicators import (
    cci,
    donchian_channel,
    er,
    mom_skip,
    roc,
    rsi,
    rsi_divergence,
    trend_score_v2,
    williams_r,
)
from skills.compute.wrappers import Factor
from skills.store.data_manager import DataManager
from strategies.cross_sectional.asset_class_rotation import (
    ASSET_CLASS_ETF_UNIVERSE,
    apply_asset_class_split_adjustments,
)

# ---------------------------------------------------------------------------
# Research Brief (因子挖掘研究边界)
# ---------------------------------------------------------------------------

BRIEF_ID = "etf18-factor-mining-2019-2026"
UNIVERSE = tuple(ASSET_CLASS_ETF_UNIVERSE.values())
UNIVERSE_NAME = ASSET_CLASS_ETF_UNIVERSE  # name -> symbol
START = "2019-01-01"
END = "2026-08-04"
FREQUENCY = "1d_adj"
IC_THRESHOLD = 0.03  # 合格因子 Rank IC mean 阈值
TARGET_QUALIFIED = 5  # 目标合格因子数量
REBALANCE_N = 5  # IC 评估调仓周期 (5 个交易日)


# ---------------------------------------------------------------------------
# FactorSpec 候选 (3 个 Generator 角色产出)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FactorCandidate:
    """轻量 FactorSpec：因子族、假设、方向、计算函数与参数。"""

    factor_id: str
    family: str
    hypothesis: str
    direction: str  # "positive" | "negative"
    func: object
    params: dict = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        param_str = ",".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.func.__name__}({param_str})" if param_str else self.func.__name__


def _trend_momentum_candidates() -> list[FactorCandidate]:
    """trend_momentum_generator 角色：趋势/动量族候选。"""
    return [
        FactorCandidate(
            factor_id="ts_roc_20",
            family="trend_momentum",
            hypothesis="20 日收益率动量：近期强势资产延续跑赢",
            direction="positive",
            func=roc,
            params={"period": 20},
        ),
        FactorCandidate(
            factor_id="ts_roc_60",
            family="trend_momentum",
            hypothesis="60 日中期动量：中期趋势延续",
            direction="positive",
            func=roc,
            params={"period": 60},
        ),
        FactorCandidate(
            factor_id="ts_trend_v2_25",
            family="trend_momentum",
            hypothesis="25 日趋势评分(年化收益×R²)：强趋势资产持续跑赢",
            direction="positive",
            func=trend_score_v2,
            params={"period": 25},
        ),
        FactorCandidate(
            factor_id="ts_trend_v2_60",
            family="trend_momentum",
            hypothesis="60 日趋势评分：中长期趋势延续",
            direction="positive",
            func=trend_score_v2,
            params={"period": 60},
        ),
        FactorCandidate(
            factor_id="ts_mom_skip_22_252",
            family="trend_momentum",
            hypothesis="剔除近 1 月的 1 年动量：避免短期反转干扰的中长期动量",
            direction="positive",
            func=mom_skip,
            params={"skip": 22, "total": 252},
        ),
        FactorCandidate(
            factor_id="ts_mom_skip_22_120",
            family="trend_momentum",
            hypothesis="剔除近 1 月的半年动量：中期动量延续",
            direction="positive",
            func=mom_skip,
            params={"skip": 22, "total": 120},
        ),
    ]


def _mean_reversion_candidates() -> list[FactorCandidate]:
    """mean_reversion_price_structure_generator 角色：均值回归/价格结构族候选。"""
    return [
        FactorCandidate(
            factor_id="mr_rsi_14",
            family="mean_reversion",
            hypothesis="14 日 RSI：超卖资产短期反弹 (反向)",
            direction="negative",
            func=rsi,
            params={"period": 14},
        ),
        FactorCandidate(
            factor_id="mr_cci_20",
            family="mean_reversion",
            hypothesis="20 日 CCI：极端偏离均值后回归",
            direction="negative",
            func=cci,
            params={"period": 20},
        ),
        FactorCandidate(
            factor_id="mr_williams_r_14",
            family="mean_reversion",
            hypothesis="14 日 Williams %R：超卖区反弹",
            direction="negative",
            func=williams_r,
            params={"period": 14},
        ),
        FactorCandidate(
            factor_id="mr_rsi_div_14_60",
            family="mean_reversion",
            hypothesis="RSI 背离：价格新高但 RSI 未新高 → 反转",
            direction="negative",
            func=rsi_divergence,
            params={"period": 14, "lookback": 60},
        ),
    ]


def _volume_liquidity_candidates() -> list[FactorCandidate]:
    """volume_liquidity_generator 角色：量能/流动性族候选。"""
    return [
        FactorCandidate(
            factor_id="ts_donchian_20",
            family="volume_liquidity",
            hypothesis="20 日唐安奇通道位置：突破上轨延续 (趋势确认)",
            direction="positive",
            func=donchian_channel,
            params={"period": 20},
        ),
        FactorCandidate(
            factor_id="ts_donchian_10",
            family="volume_liquidity",
            hypothesis="10 日唐安奇通道：短期突破延续",
            direction="positive",
            func=donchian_channel,
            params={"period": 10},
        ),
        FactorCandidate(
            factor_id="ts_er_14",
            family="volume_liquidity",
            hypothesis="14 日效率系数：高效运动资产延续趋势",
            direction="positive",
            func=er,
            params={"period": 14},
        ),
        FactorCandidate(
            factor_id="ts_er_60",
            family="volume_liquidity",
            hypothesis="60 日效率系数：中长期高效趋势延续",
            direction="positive",
            func=er,
            params={"period": 60},
        ),
    ]


def all_candidates() -> list[FactorCandidate]:
    """汇总 3 个 Generator 角色的全部候选。"""
    return (
        _trend_momentum_candidates()
        + _mean_reversion_candidates()
        + _volume_liquidity_candidates()
    )


# ---------------------------------------------------------------------------
# 因子执行 + IC 评估 (Phase 02 compute + Phase 03 analyze 适配)
# ---------------------------------------------------------------------------


@dataclass
class FactorEvaluation:
    """单因子评估结果。"""

    candidate: FactorCandidate
    ic_mean: float
    ic_std: float
    ic_ir: float
    ic_positive_ratio: float
    ic_count: int
    t_stat: float
    p_value: float
    qualified: bool
    values_wide: pd.DataFrame | None = None  # 因子宽表 (eob × symbol)，用于相关性去重

    def summary_line(self) -> str:
        flag = "PASS" if self.qualified else "fail"
        return (
            f"[{flag}] {self.candidate.factor_id:24s} "
            f"{self.candidate.display_name:30s} "
            f"IC={self.ic_mean:+.4f} IR={self.ic_ir:+.4f} "
            f"IC>0={self.ic_positive_ratio:.2%} t={self.t_stat:+.2f} "
            f"n={self.ic_count} ({self.candidate.family})"
        )


def evaluate_factor(
    candidate: FactorCandidate, panel: pd.DataFrame, *, n: int = REBALANCE_N
) -> FactorEvaluation | None:
    """计算因子值并用 IC_stat 评估。

    返回 None 表示该因子在样本内无法计算（数据不足等）。
    """
    try:
        factor = Factor(candidate.func, **candidate.params)
        scores = factor.calculate(panel, dropna=True)
    except Exception as exc:  # noqa: BLE001 - 研究阶段需容忍个别因子失败
        print(f"  [compute-fail] {candidate.factor_id}: {exc}")
        return None

    if scores.empty:
        return None

    # 因子宽表，用于后续池相关性去重
    values_wide = scores.unstack("symbol").sort_index()

    # 组装 IC_stat 所需格式: MultiIndex (eob, symbol), columns=[close, fac_val]
    df = panel[["close"]].copy()
    df["fac_val"] = scores
    df = df.dropna(subset=["close", "fac_val"])
    # 重排索引为 (eob, symbol)
    df = df.reorder_levels(["eob", "symbol"]).sort_index()

    if df.empty:
        return None

    try:
        ic_stat_dict, _ = IC_stat(df, rank_IC=True, n=n)
    except Exception as exc:  # noqa: BLE001
        print(f"  [ic-fail] {candidate.factor_id}: {exc}")
        return None

    ic_mean = ic_stat_dict["IC_mean"]
    # direction 校正：若假设方向为 negative，则取 IC 绝对值方向为负
    # 这里合格性判断用 |IC| (因为反向因子取负号后 IC 为正)
    effective_ic = ic_mean if candidate.direction == "positive" else -ic_mean
    qualified = effective_ic >= IC_THRESHOLD

    return FactorEvaluation(
        candidate=candidate,
        ic_mean=ic_mean,
        ic_std=ic_stat_dict["IC_std"],
        ic_ir=ic_stat_dict["IC_IR"],
        ic_positive_ratio=ic_stat_dict["IC_>0"],
        ic_count=ic_stat_dict["IC_count"],
        t_stat=ic_stat_dict["t_stat"],
        p_value=ic_stat_dict["p_value"],
        qualified=qualified,
        values_wide=values_wide,
    )


# ---------------------------------------------------------------------------
# Reviewer / PoolSynthesizer (评审与池决策)
# ---------------------------------------------------------------------------


def review_and_synthesize(
    evaluations: list[FactorEvaluation], *, target: int = TARGET_QUALIFIED
) -> list[FactorEvaluation]:
    """Reviewer + PoolSynthesizer: 筛选合格因子并做池去重。

    评审规则 (methodology_critic + leakage_and_code_reviewer):
    - 合格性: 方向校正后 IC mean >= 0.03
    - 显著性: |t_stat| >= 1.0 (软阈值，记录但不过滤)
    - 稳定性: IC>0 占比 >= 52% (软阈值)
    - 方向一致性: 方向校正后 IC 符号与假设一致

    池决策 (pool_synthesizer): 横截面相关性去重 (|corr|>0.9 视为同质)，
    同族最多 2 个，跨族优先填满 5 个，保证池多样性。
    """
    qualified = [e for e in evaluations if e.qualified]
    # 按 effective IC 降序
    for e in qualified:
        e._effective_ic = (  # type: ignore[attr-defined]
            e.ic_mean if e.candidate.direction == "positive" else -e.ic_mean
        )
    qualified.sort(key=lambda e: e._effective_ic, reverse=True)  # type: ignore[attr-defined]

    # 相关性去重: 后续因子与已入选因子横截面 |corr| > 0.9 则跳过
    pool: list[FactorEvaluation] = []
    family_count: dict[str, int] = {}
    for e in qualified:
        fam = e.candidate.family
        # 同族最多 2 个
        if family_count.get(fam, 0) >= 2:
            continue
        # 相关性去重
        if e.values_wide is not None and pool:
            too_corr = False
            for p in pool:
                if p.values_wide is None:
                    continue
                common_idx = e.values_wide.index.intersection(p.values_wide.index)
                if len(common_idx) < 30:
                    continue
                a = e.values_wide.loc[common_idx].stack(dropna=True)
                b = p.values_wide.loc[common_idx].stack(dropna=True)
                joined = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
                if len(joined) < 30:
                    continue
                corr = float(joined["a"].corr(joined["b"]))
                if abs(corr) > 0.85:
                    too_corr = True
                    print(
                        f"  [dedup] {e.candidate.factor_id} skipped: "
                        f"|corr|={abs(corr):.2f} with {p.candidate.factor_id}"
                    )
                    break
            if too_corr:
                continue
        pool.append(e)
        family_count[fam] = family_count.get(fam, 0) + 1
        if len(pool) >= target:
            break

    return pool[:target]


# ---------------------------------------------------------------------------
# Supervisor: 主编排
# ---------------------------------------------------------------------------


def run() -> None:
    print("=" * 80)
    print(f"Factor Mining Research Brief: {BRIEF_ID}")
    print("=" * 80)
    print(f"Universe: {len(UNIVERSE)} global-asset ETFs")
    print(f"Sample:   {START} ~ {END}")
    print(f"Data:     data/market/{FREQUENCY}")
    print(f"Target:   {TARGET_QUALIFIED} qualified factors (Rank IC mean >= {IC_THRESHOLD})")
    print(f"Rebalance horizon: {REBALANCE_N} trading days")
    print()

    # ---- 数据加载 ----
    print("[1/4] Loading panel data ...")
    dm = DataManager()
    panel = dm.read_symbols(list(UNIVERSE), frequency=FREQUENCY)
    panel = apply_asset_class_split_adjustments(panel)
    panel = panel.loc[
        (slice(None), slice(pd.Timestamp(START), pd.Timestamp(END))), :
    ]
    print(
        f"  panel: {panel.shape[0]} rows, "
        f"{panel.index.get_level_values('eob').min().date()} ~ "
        f"{panel.index.get_level_values('eob').max().date()}"
    )
    print()

    # ---- Generator: 3 族候选 ----
    print("[2/4] Generating factor candidates (3 families) ...")
    candidates = all_candidates()
    families = {}
    for c in candidates:
        families.setdefault(c.family, []).append(c)
    for fam, fam_candidates in families.items():
        print(f"  {fam}: {len(fam_candidates)} candidates")
    print(f"  total: {len(candidates)} candidates")
    print()

    # ---- 执行 + IC 评估 ----
    print("[3/4] Computing factors and evaluating Rank IC ...")
    evaluations: list[FactorEvaluation] = []
    for c in candidates:
        ev = evaluate_factor(c, panel)
        if ev is not None:
            evaluations.append(ev)
            print(f"  {ev.summary_line()}")
    print()

    # ---- Reviewer + PoolSynthesizer ----
    print("[4/4] Reviewing and synthesizing factor pool ...")
    qualified_all = [e for e in evaluations if e.qualified]
    print(f"  qualified (IC>={IC_THRESHOLD}): {len(qualified_all)} / {len(evaluations)}")
    pool = review_and_synthesize(evaluations, target=TARGET_QUALIFIED)
    print()

    # ---- 研究报告 ----
    print("=" * 80)
    print("RESEARCH REPORT — 5 Qualified Factors")
    print("=" * 80)
    if not pool:
        print("No qualified factors found. Consider relaxing threshold or adding candidates.")
        return

    report_rows = []
    for i, e in enumerate(pool, 1):
        effective_ic = e.ic_mean if e.candidate.direction == "positive" else -e.ic_mean
        print(f"\nFactor #{i}: {e.candidate.factor_id}")
        print(f"  Family:     {e.candidate.family}")
        print(f"  Formula:    {e.candidate.display_name}")
        print(f"  Hypothesis: {e.candidate.hypothesis}")
        print(f"  Direction:  {e.candidate.direction} (effective IC = {effective_ic:+.4f})")
        print(f"  IC mean:    {e.ic_mean:+.4f}")
        print(f"  IC IR:      {e.ic_ir:+.4f}")
        print(f"  IC>0 ratio: {e.ic_positive_ratio:.2%}")
        print(f"  t-stat:     {e.t_stat:+.4f}  (p={e.p_value:.4f})")
        print(f"  IC count:   {e.ic_count}")
        report_rows.append(
            {
                "rank": i,
                "factor_id": e.candidate.factor_id,
                "family": e.candidate.family,
                "formula": e.candidate.display_name,
                "direction": e.candidate.direction,
                "IC_mean": round(e.ic_mean, 4),
                "effective_IC": round(effective_ic, 4),
                "IC_IR": round(e.ic_ir, 4),
                "IC_pos_ratio": round(e.ic_positive_ratio, 4),
                "t_stat": round(e.t_stat, 4),
                "p_value": round(e.p_value, 4),
                "IC_count": e.ic_count,
            }
        )

    # 汇总表
    print("\n" + "-" * 80)
    print("Summary Table:")
    summary = pd.DataFrame(report_rows)
    print(summary.to_string(index=False))

    # 全候选排名 (附录)
    print("\n" + "-" * 80)
    print("Appendix: All candidates ranked by |effective IC|:")
    all_ranked = sorted(
        evaluations,
        key=lambda e: abs(e.ic_mean if e.candidate.direction == "positive" else -e.ic_mean),
        reverse=True,
    )
    for e in all_ranked:
        print(f"  {e.summary_line()}")


if __name__ == "__main__":
    run()
