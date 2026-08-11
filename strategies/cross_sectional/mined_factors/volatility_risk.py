"""volatility_risk_regime_generator 角色产出的 NEW 因子候选 (volatility/risk/regime 族)."""

from __future__ import annotations

import numpy as np
import pandas as pd

# =============================================================================
# 因子函数
# =============================================================================


def vr_downside_semivariance_premium(
    group: pd.DataFrame,
    period: int = 20,
) -> pd.Series:
    """下行半方差倒数因子。

    经济假设：资产收益的下行风险（负收益的半方差）比全样本方差更能反映
    投资者真实厌恶的尾部损失。下行半方差越低，说明资产在下跌行情中抗跌
    能力越强，长期风险溢价越高。用滚动窗口内仅取负收益计算的半方差倒数
    作为因子，区分「低下行风险」与「低总波动」——后者会被上行波动拉高而
    失真。与 volatility_inv（1/std，上行下行不分）不同，本因子只奖励下行
    稳健的品种。NaN 用于 warm-up，输出 tanh 压缩至 [-1, 1]。
    """
    close = group["close"].astype(float)
    ret = close.pct_change()

    # 下行半方差：仅取负收益，平方后取均值
    neg_ret = ret.where(ret < 0.0, 0.0)
    semivar = neg_ret.pow(2).rolling(window=period, min_periods=period).mean()
    semivar = semivar.where(semivar > 1e-12, np.nan)

    # 倒数（下行风险越低因子越高）+ tanh 压缩尾部
    inv_semi = 1.0 / np.sqrt(semivar)
    result = np.tanh(inv_semi)
    return result.astype("float64")


def vr_vol_quantile_rank(
    group: pd.DataFrame,
    short_period: int = 10,
    long_lookback: int = 120,
) -> pd.Series:
    """波动率锥分位因子。

    经济假设：当前实现波动率在自身长期分布中的分位位置刻画了风险 regime。
    处于历史低分位（如 <20%）时为低波动 regime，未来风险调整收益更优；
    高分位（>80%）时风险已释放或拥挤，后续承压。与 volatility_regime（短
    /长 std 比值，受尺度影响）不同，分位数是 rank-based、跨周期稳定的
    regime 指标。用滚动短窗 std 在长窗历史 std 序列中的百分位取负（低分位
    -> 高因子值）。
    """
    close = group["close"].astype(float)
    ret = close.pct_change()

    short_vol = ret.rolling(window=short_period, min_periods=short_period).std()

    # 滚动长窗内 short_vol 的分位数（rank 百分位）
    def _quantile_rank(w: np.ndarray) -> float:
        if np.isnan(w).any() or len(w) < 2:
            return np.nan
        cur = w[-1]
        if np.isnan(cur):
            return np.nan
        # 当前值在历史窗口中的百分位 [0, 1]
        rank = np.nanmean(w <= cur)
        return float(rank)

    q_rank = short_vol.rolling(window=long_lookback, min_periods=long_lookback).apply(
        _quantile_rank, raw=True
    )

    # 取负：低分位（低波动 regime）-> 高因子值
    result = -q_rank
    return result.astype("float64")


def vr_vol_mean_reversion_speed(
    group: pd.DataFrame,
    period: int = 20,
    lag: int = 5,
) -> pd.Series:
    """波动率均值回归速度因子。

    经济假设：波动率具有强均值回归特性，但回归速度因资产与 regime 而异。
    回归速度快的品种（波动率冲击迅速消散）尾部风险更低、更适合持有；回
    归速度慢的品种风险持续期长。用「波动率一阶自回归系数」的负值刻画：
    当期 vol 与 lag 期 vol 的相关系数越低（甚至负），说明冲击消散快。与
    vol_clustering_autocorr（绝对收益自相关）不同，本因子作用于 std 序列
    本身而非绝对收益，度量的是「波动率水平」的持久性。
    """
    close = group["close"].astype(float)
    ret = close.pct_change()
    vol = ret.rolling(window=period, min_periods=period).std()

    vol_lagged = vol.shift(lag)

    # 滚动窗口内 vol 与 vol_lagged 的 Pearson 相关
    # 用 rolling.corr 直接计算
    corr = vol.rolling(window=period, min_periods=period).corr(vol_lagged)

    # 取负：自相关越低（回归越快）-> 因子值越高
    result = -corr
    # 压缩到 [-1, 1]（corr 本身已在 [-1,1]，取负后仍在此范围）
    result = result.clip(-1.0, 1.0)
    return result.astype("float64")


def vr_up_down_vol_asymmetry(
    group: pd.DataFrame,
    period: int = 20,
) -> pd.Series:
    """涨跌波动率不对称因子。

    经济假设：上行日波动率与下行日波动率的不对称性反映市场对方向的偏向。
    上行波动 > 下行波动 时，市场在上涨日更激进（risk-on regime），后续
    收益更优；反之下行波动占优为 risk-off regime。与 rsi（涨跌幅度比）和
    momentum_score（净收益）不同，本因子度量的是「波动率方向不对称」而非
    收益方向，捕捉的是价格路径的凸性特征。用 log(up_vol / down_vol) 对
    称化处理。
    """
    close = group["close"].astype(float)
    ret = close.pct_change()

    # 分别累计上行 / 下行收益的平方和与计数，计算各自波动率
    # 用 min_periods=1 保证只要窗口内有正/负收益即可计算
    up_ret_sq = (ret.where(ret > 0.0, 0.0)).pow(2)
    down_ret_sq = (ret.where(ret < 0.0, 0.0)).pow(2)
    up_count = (ret > 0.0).astype(float)
    down_count = (ret < 0.0).astype(float)

    up_sum_sq = up_ret_sq.rolling(window=period, min_periods=period).sum()
    down_sum_sq = down_ret_sq.rolling(window=period, min_periods=period).sum()
    up_n = up_count.rolling(window=period, min_periods=period).sum()
    down_n = down_count.rolling(window=period, min_periods=period).sum()

    # 半标准差（避免 zero-count 除零）
    up_vol = np.sqrt(up_sum_sq / up_n.where(up_n > 0.0, np.nan))
    down_vol = np.sqrt(down_sum_sq / down_n.where(down_n > 0.0, np.nan))

    # log 比率对称化，避免除零；两 vol 都需 > 0
    valid = (up_vol > 1e-10) & (down_vol > 1e-10)
    ratio = (np.log(up_vol) - np.log(down_vol)).where(valid)
    # tanh 压缩尾部
    result = np.tanh(ratio)
    return result.astype("float64")


def vr_var_tail_risk_inverse(
    group: pd.DataFrame,
    period: int = 60,
    quantile: float = 0.05,
) -> pd.Series:
    """历史 VaR 尾部风险倒数因子。

    经济假设：左尾 VaR（如 5% 分位收益）直接刻画极端损失风险。VaR 越接近
    0（损失越小）的资产，尾部风险越低，长期复利效应越显著。与
    downside_semivariance_premium（二阶矩）和 volatility_inv（全样本 std）
    不同，本因子是分位数-based，只关心最坏的尾部样本，对「黑天鹅韧性」更
    敏感。用滚动窗口内收益的 quantile 分位数取倒数（VaR 越接近 0 越好），
    tanh 压缩。
    """
    close = group["close"].astype(float)
    ret = close.pct_change()

    def _var(w: np.ndarray) -> float:
        if np.isnan(w).any() or len(w) < period:
            return np.nan
        # 历史 VaR：收益分布的左尾分位（负值）
        return float(np.nanquantile(w, quantile))

    var_series = ret.rolling(window=period, min_periods=period).apply(_var, raw=True)

    # VaR 为负值（损失），越接近 0 越好；取倒数并 tanh 压缩
    # |VaR| 越小 -> 1/|VaR| 越大 -> 因子越高
    abs_var = var_series.abs()
    abs_var = abs_var.where(abs_var > 1e-8, np.nan)
    inv_var = 1.0 / abs_var
    result = np.tanh(inv_var)
    return result.astype("float64")


def vr_vol_clustering_autocorr(
    group: pd.DataFrame,
    period: int = 20,
    lag: int = 1,
) -> pd.Series:
    """波动率聚集度（绝对收益自相关）因子。

    经济假设：GARCH 族的核心事实是「波动率聚集」——大波动紧跟大波动。绝
    对收益的自相关越高，波动率聚集越强，意味着风险一旦升高会持续，对该资
    产是负面信号（持续高波动侵蚀复利）。低自相关则说明风险冲击独立、消散
    快，更友好。用滚动窗口内 |收益| 的 lag 阶自相关取负：低聚集度 -> 高因
    子值。与 vol_mean_reversion_speed（作用于 std 序列）不同，本因子直接
    作用于绝对收益，是 GARCH 聚集效应的一阶度量。
    """
    close = group["close"].astype(float)
    ret = close.pct_change()
    abs_ret = ret.abs()

    abs_ret_lagged = abs_ret.shift(lag)
    corr = abs_ret.rolling(window=period, min_periods=period).corr(abs_ret_lagged)

    # 取负：低自相关（冲击独立）-> 高因子值
    result = -corr
    result = result.clip(-1.0, 1.0)
    return result.astype("float64")


def vr_hurst_regime_persistence(
    group: pd.DataFrame,
    period: int = 100,
) -> pd.Series:
    """简化 Hurst 指数 regime 持续性因子。

    经济假设：Hurst 指数 H 刻画序列的长记忆性。H > 0.5 为持续性 regime
    （趋势延续），H < 0.5 为均值回归 regime，H ≈ 0.5 为随机游走。对 ETF
    轮动而言，持续性 regime（H 偏高）下动量策略更有效，应给予更高权重。
    用滚动窗口的 R/S（重标极差）法估计 H，再减 0.5 使中性值为 0，正值代
    表持续性 regime。与 trend_score（价格斜率）不同，Hurst 度量的是「自
    相似结构」而非方向，是 regime 分类指标。
    """
    close = group["close"].astype(float)
    log_close = np.log(close.where(close > 0.0))

    def _hurst(w: np.ndarray) -> float:
        if np.isnan(w).any() or len(w) < 20:
            return np.nan
        n = len(w)
        # R/S 法：对若干子区间长度 k 计算 mean(R/S)
        # 简化为对数收益的累积偏差极差 / 标准差
        y = w - w.mean()
        cum_y = np.cumsum(y)
        r = float(np.max(cum_y) - np.min(cum_y))
        s = float(np.std(w, ddof=1))
        if s <= 1e-12:
            return np.nan
        rs = r / s
        if rs <= 0.0:
            return np.nan
        # H = log(R/S) / log(n)
        h = float(np.log(rs) / np.log(n))
        return h

    hurst = log_close.rolling(window=period, min_periods=period).apply(_hurst, raw=True)

    # 减 0.5：持续性 regime 为正，均值回归为负
    result = hurst - 0.5
    # clip 到合理范围
    result = result.clip(-0.5, 0.5)
    return result.astype("float64")


# =============================================================================
# 候选因子注册表
# =============================================================================

CANDIDATES = [
    {
        "factor_id": "vr_downside_semivariance_premium",
        "family": "volatility_risk",
        "hypothesis": "下行半方差倒数刻画尾部抗跌能力，下行风险越低长期风险溢价越高，区别于全样本波动率",
        "direction": "positive",
        "func_name": "vr_downside_semivariance_premium",
        "params": {"period": 20},
    },
    {
        "factor_id": "vr_vol_quantile_rank",
        "family": "volatility_risk",
        "hypothesis": "当前实现波动率在长期分布中的分位刻画风险 regime，低分位低波动 regime 未来风险调整收益更优",
        "direction": "positive",
        "func_name": "vr_vol_quantile_rank",
        "params": {"short_period": 10, "long_lookback": 120},
    },
    {
        "factor_id": "vr_vol_mean_reversion_speed",
        "family": "volatility_risk",
        "hypothesis": "波动率均值回归速度越快尾部风险越低，用 vol 序列自相关负值刻画冲击消散速度",
        "direction": "positive",
        "func_name": "vr_vol_mean_reversion_speed",
        "params": {"period": 20, "lag": 5},
    },
    {
        "factor_id": "vr_up_down_vol_asymmetry",
        "family": "volatility_risk",
        "hypothesis": "上行波动率与下行波动率不对称反映 risk-on/off regime，上行波动占优为 risk-on 信号",
        "direction": "positive",
        "func_name": "vr_up_down_vol_asymmetry",
        "params": {"period": 20},
    },
    {
        "factor_id": "vr_var_tail_risk_inverse",
        "family": "volatility_risk",
        "hypothesis": "历史 VaR 尾部风险倒数刻画黑天鹅韧性，左尾损失越接近 0 复利效应越显著",
        "direction": "positive",
        "func_name": "vr_var_tail_risk_inverse",
        "params": {"period": 60, "quantile": 0.05},
    },
    {
        "factor_id": "vr_vol_clustering_autocorr",
        "family": "volatility_risk",
        "hypothesis": "绝对收益自相关越低波动率聚集越弱风险冲击越独立，低聚集度资产更友好",
        "direction": "positive",
        "func_name": "vr_vol_clustering_autocorr",
        "params": {"period": 20, "lag": 1},
    },
    {
        "factor_id": "vr_hurst_regime_persistence",
        "family": "volatility_risk",
        "hypothesis": "Hurst 指数偏离 0.5 刻画 regime 持续性，持续性 regime（H 偏高）下动量策略更有效",
        "direction": "positive",
        "func_name": "vr_hurst_regime_persistence",
        "params": {"period": 100},
    },
]
