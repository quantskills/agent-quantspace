"""volatility_risk_regime_generator 修订轮 NEW 因子候选.

修订轮：第一轮 vr_vol_quantile_rank / vr_vol_mean_reversion_speed /
vr_up_down_vol_asymmetry / vr_var_tail_risk_inverse / vr_vol_clustering_autocorr /
vr_hurst_regime_persistence / vr_downside_semivariance_premium 全部 IC<0.03
或报错。本轮避开分位/自相关/Hurst/半方差/聚集度等方向，改用 Sortino 式
下行风险调整动量、波动率期限结构非线性变换、Calmar 风险调整、ATR 相对
收价 z-score、收益分布偏度风险溢价等全新假设。

遵循 skills.compute.wrappers.Factor 契约：
- 输入: 单 symbol DataFrame，索引名为 eob 的 DatetimeIndex，列含 OHLCV
- 输出: float64 Series，索引与输入完全相同且顺序一致，NaN 用于 warm-up

不复用 indicators.py / factors.py / volatility_risk.py 已存在的因子。
可用 numpy/pandas 与 skills.compute.utils (calculate_atr / safe_divide /
rolling_zscore / clip_outliers)。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from skills.compute.utils import calculate_atr, rolling_zscore, safe_divide

# =============================================================================
# 1. Sortino 式下行风险调整动量
# =============================================================================


def vr2_sortino_downside_momentum(
    group: pd.DataFrame,
    period: int = 20,
    downside_target: float = 0.0,
) -> pd.Series:
    """Sortino 式下行风险调整动量因子。

    经济假设：传统动量用收益均值除以全样本标准差（Sharpe 式），上行波动
    被当作「风险」惩罚，但投资者实际厌恶的只是下行波动。Sortino 比率用
    「均值收益 / 下行半标准差」更贴近行为金融。跨截面看，下行半标准差低
    且均值收益为正的资产（抗跌 + 有趋势）应获得更高风险调整溢价。本因子
    用滚动窗口内收益均值除以下行半标准差，低下行风险 + 正趋势 -> 高因子
    值。本因子显式融合「趋势方向」与「下行风险调整」。

    参数:
        period: 滚动窗口长度
        downside_target: 下行目标收益率，默认 0（仅惩罚负收益）
    """
    close = group["close"].astype(float)
    ret = close.pct_change()

    mean_ret = ret.rolling(window=period, min_periods=period).mean()

    # 下行偏差：仅取低于 target 的部分
    downside = (ret - downside_target).where(ret < downside_target, 0.0)
    downside_var = downside.pow(2).rolling(window=period, min_periods=period).mean()
    downside_std = np.sqrt(downside_var)
    downside_std = downside_std.where(downside_std > 1e-10, np.nan)

    # Sortino 式：均值 / 下行半标准差
    sortino = safe_divide(mean_ret, downside_std, np.nan)
    # tanh 压缩尾部，避免极端值主导 rank
    result = np.tanh(sortino)
    return result.astype("float64")


# =============================================================================
# 2. 波动率期限结构非线性变换
# =============================================================================


def vr2_vol_term_structure_tanh(
    group: pd.DataFrame,
    short_period: int = 10,
    long_period: int = 60,
) -> pd.Series:
    """波动率期限结构非线性变换因子。

    经济假设：短期波动率与长期波动率的比率（vol term structure）反映风险
    regime 的状态。短 vol < 长 vol（期限结构「贴水」）时为风险释放后的低波
    动 regime，后续均值回归向上；短 vol > 长 vol（期限结构「升水」）时风
    险正在积聚。本因子用 tanh(short/long - 1) 做非线性变换，使「适度贴水」与
    「极端贴水」区分化，同时用长期 vol 自身做 z-score 标准化以去除资产固
    有波动率尺度差异。

    参数:
        short_period: 短期波动率窗口
        long_period: 长期波动率窗口
    """
    close = group["close"].astype(float)
    ret = close.pct_change()

    short_vol = ret.rolling(window=short_period, min_periods=short_period).std()
    long_vol = ret.rolling(window=long_period, min_periods=long_period).std()
    long_vol = long_vol.where(long_vol > 1e-10, np.nan)

    # 期限结构比率 - 1
    ratio_minus_1 = safe_divide(short_vol, long_vol, np.nan) - 1.0
    # tanh 非线性变换：贴水（<0）映射为负，升水（>0）映射为正
    # 取负：贴水（低波动 regime）-> 高因子值
    term_signal = -np.tanh(ratio_minus_1)

    # 用 long_vol 的长期 z-score 标准化去除资产固有波动率尺度
    # （不同 ETF 固有波动率不同，需标准化才能跨截面比较）
    long_vol_z = rolling_zscore(long_vol, long_period * 2, long_period)

    # 期限信号 × 低波动溢价：贴水 + 低绝对波动 -> 更强信号
    # low_vol_signal: long_vol 越低（z 越负）-> 因子越高
    low_vol_signal = -np.tanh(long_vol_z)
    result = term_signal * 0.6 + low_vol_signal * 0.4
    return result.astype("float64")


# =============================================================================
# 3. Calmar 风险调整动量
# =============================================================================


def vr2_calmar_risk_adjusted(
    group: pd.DataFrame,
    period: int = 60,
) -> pd.Series:
    """Calmar 式风险调整动量因子。

    经济假设：Calmar 比率（年化收益 / 最大回撤）综合衡量收益与尾部回撤
    风险。最大回撤低且收益正的资产，在风险调整后更具吸引力。第一轮的
    VaR / 半方差因子只看下行风险大小，未与收益结合；本因子显式计算滚动
    窗口内「累计收益 / 最大回撤」，使「有趋势 + 低回撤」的资产排序靠前。
    用滚动窗口避免前视，回撤用窗口内 close 相对 rolling max 的回撤。

    参数:
        period: 滚动窗口长度（回看期）
    """
    close = group["close"].astype(float)
    idx = group.index

    if len(close) < period:
        return pd.Series(np.full(len(close), np.nan), index=idx, dtype=np.float64)

    vals = close.values
    n = len(vals)
    out = np.full(n, np.nan, dtype=np.float64)

    for i in range(period - 1, n):
        window = vals[i - period + 1 : i + 1]
        # 窗口内累计收益
        if window[0] <= 0:
            continue
        cum_ret = window[-1] / window[0] - 1.0
        # 窗口内最大回撤（负值）
        running_max = np.maximum.accumulate(window)
        drawdowns = (window - running_max) / running_max
        max_dd = drawdowns.min()  # 负值
        abs_dd = abs(max_dd)
        if abs_dd > 1e-8:
            # Calmar 式：收益 / 回撤
            calmar = cum_ret / abs_dd
            out[i] = calmar

    # tanh 压缩尾部
    result = np.tanh(out)
    return pd.Series(result, index=idx, dtype=np.float64)


# =============================================================================
# 4. ATR 相对收价 z-score
# =============================================================================


def vr2_atr_close_zscore(
    group: pd.DataFrame,
    atr_period: int = 14,
    zscore_window: int = 60,
) -> pd.Series:
    """ATR 相对收价 z-score 因子。

    经济假设：ATR（真实波幅）刻画资产当期的绝对波动幅度（元/单位价格）。
    当 ATR 相对自身历史分布处于低位（z-score 为负）时，市场处于低波压缩
    regime，后续倾向于波动率扩张（方向待定但风险溢价上升）；ATR 处于高
    位时风险已释放或过度。本因子用 ATR 的滚动 z-score 取负，使「低 ATR
    压缩」资产排序靠前（低风险溢价）。ATR 包含 high/low 信息，对日内波幅
    更敏感，是「路径波动率」而非「收盘波动率」。

    参数:
        atr_period: ATR 计算周期
        zscore_window: z-score 标准化窗口
    """
    high = group["high"].astype(float)
    low = group["low"].astype(float)
    close = group["close"].astype(float)

    atr = calculate_atr(high, low, close, atr_period)

    # ATR 相对收价归一化（去除价格尺度差异）
    close_safe = close.where(close > 0, np.nan)
    atr_norm = safe_divide(atr, close_safe, np.nan)

    # 滚动 z-score
    z = rolling_zscore(atr_norm, zscore_window, atr_period)
    # 取负：低 ATR z-score（低波压缩）-> 高因子值
    result = -np.tanh(z)
    return result.astype("float64")


# =============================================================================
# 5. 收益分布偏度风险溢价
# =============================================================================


def vr2_return_skew_risk_premium(
    group: pd.DataFrame,
    period: int = 40,
) -> pd.Series:
    """收益分布偏度风险溢价因子。

    经济假设：行为金融与期权定价表明，投资者厌恶负偏资产（左尾厚），要求
    更高预期补偿。跨截面看，负偏程度越深的资产（历史收益分布左尾越厚），
    后续风险溢价补偿越高（反向看多）；正偏资产已被高估（反向看空）。这
    与「低波动溢价」不同：偏度刻画分布的非对称性，而非离散度。第一轮未
    涉及偏度。本因子用滚动窗口内对数收益的样本偏度取负，使负偏资产（左
    尾厚）获得高因子值。偏度用标准化三阶矩。

    参数:
        period: 滚动窗口长度（需 >= 30 保证偏度估计稳定）
    """
    close = group["close"].astype(float)
    log_ret = np.log(close.where(close > 0) / close.shift(1))

    def _skew(w: np.ndarray) -> float:
        if np.isnan(w).any() or len(w) < period:
            return np.nan
        m = w.mean()
        s = w.std(ddof=1)
        if s <= 1e-10:
            return np.nan
        # 标准化三阶矩偏度
        return float(np.mean(((w - m) / s) ** 3))

    skew = log_ret.rolling(window=period, min_periods=period).apply(_skew, raw=True)

    # 取负：负偏（左尾厚）-> 高因子值（风险溢价看多）
    # tanh 压缩尾部，偏度经验范围约 [-2, 2]
    result = -np.tanh(skew)
    return result.astype("float64")


# =============================================================================
# 候选因子注册表
# =============================================================================

CANDIDATES = [
    {
        "factor_id": "vr2_sortino_downside_momentum",
        "family": "volatility_risk",
        "module": "volatility_risk_revise2",
        "hypothesis": "Sortino 式均值收益除以下行半标准差，低下行风险+正趋势资产获风险调整溢价",
        "direction": "positive",
        "func_name": "vr2_sortino_downside_momentum",
        "params": {"period": 20, "downside_target": 0.0},
    },
    {
        "factor_id": "vr2_vol_term_structure_tanh",
        "family": "volatility_risk",
        "module": "volatility_risk_revise2",
        "hypothesis": "短/长波动率比率的 tanh 非线性变换，贴水 regime（短<长）叠加低绝对波动获溢价",
        "direction": "positive",
        "func_name": "vr2_vol_term_structure_tanh",
        "params": {"short_period": 10, "long_period": 60},
    },
    {
        "factor_id": "vr2_calmar_risk_adjusted",
        "family": "volatility_risk",
        "module": "volatility_risk_revise2",
        "hypothesis": "滚动窗口累计收益除以最大回撤，有趋势+低回撤资产风险调整后更优",
        "direction": "positive",
        "func_name": "vr2_calmar_risk_adjusted",
        "params": {"period": 60},
    },
    {
        "factor_id": "vr2_atr_close_zscore",
        "family": "volatility_risk",
        "module": "volatility_risk_revise2",
        "hypothesis": "ATR/收价 的滚动 z-score 取负，低波压缩 regime 资产获低风险溢价",
        "direction": "positive",
        "func_name": "vr2_atr_close_zscore",
        "params": {"atr_period": 14, "zscore_window": 60},
    },
    {
        "factor_id": "vr2_return_skew_risk_premium",
        "family": "volatility_risk",
        "module": "volatility_risk_revise2",
        "hypothesis": "收益分布偏度取负，负偏资产（左尾厚）要求更高风险溢价补偿",
        "direction": "positive",
        "func_name": "vr2_return_skew_risk_premium",
        "params": {"period": 40},
    },
]
