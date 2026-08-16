"""trend_momentum_generator 修订轮 NEW 因子候选 (trend/momentum 族 第二轮).

设计方向刻意避开第一轮已尝试的多窗口融合/急动度/持续度加权/对数偏度/
路径曲率/量价不对称/离散度反转。本轮聚焦于：
1. 双 EMA 斜率差作为趋势加速度（Kalman-ish 增益动量）
2. 趋势信息比率（slope / std of log close，Sharpe-of-trend）
3. 高阶矩趋势健康度（rolling 偏度-峰度组合刻画分布尾部风险）
4. 突破持续性（滚动新高天数占比 × 趋势斜率）

所有因子遵守 skills.compute.wrappers.Factor 契约：
- 输入 group 为单 symbol DataFrame，eob DatetimeIndex，含 OHLCV 列
- 输出 float64 Series，索引与输入逐项相同且顺序一致
- 不复用 skills.compute.indicators 或 strategies.cross_sectional.factors 中的已有函数
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# =============================================================================
# 因子函数
# =============================================================================


def tm2_ema_slope_acceleration(
    group: pd.DataFrame,
    fast: int = 10,
    slow: int = 30,
    slope_period: int = 5,
) -> pd.Series:
    """双 EMA 斜率差趋势加速度因子。

    经济假设：趋势的「加速度」比趋势本身更具领先意义。用快慢两条 EMA
    分别拟合价格，再对每条 EMA 做短期斜率估计，取快线斜率减慢线斜率作
    为趋势加速度。当加速度为正且扩大时，趋势正在从酝酿期进入加速期；
    加速度转负则预示趋势力量衰减。本因子先做 EMA 平滑再取斜率差，
    抑制噪声并突出趋势力量的二阶变化。
    """
    close = group["close"].astype(float)

    # 快慢 EMA
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()

    # 对 EMA 做斜率估计：用 slope_period 窗口内的首末差分 / (period-1)
    # 向量化：当前 EMA 与 slope_period 期前的 EMA 之差
    slope_fast = (ema_fast - ema_fast.shift(slope_period)) / float(slope_period)
    slope_slow = (ema_slow - ema_slow.shift(slope_period)) / float(slope_period)

    # 加速度 = 快线斜率 - 慢线斜率
    acceleration = slope_fast - slope_slow

    # tanh 压缩尾部
    result = np.tanh(acceleration)
    return result.astype("float64")


def tm2_trend_information_ratio(
    group: pd.DataFrame,
    period: int = 25,
) -> pd.Series:
    """趋势信息比率因子（Sharpe-of-trend）。

    经济假设：干净有力的趋势应同时具备「高斜率」与「低噪声」。借鉴
    Sharpe 比率思想，用滚动窗口内对数收盘价的线性回归斜率除以残差标准
    差，得到「每单位噪声的趋势强度」。相比 trend_score（slope × R²），
    本因子直接用斜率 / 残差 std，对斜率本身更敏感，且不因 R² 的非线性
    压缩而抑制强趋势信号。
    """
    close = group["close"].astype(float)
    log_close = np.log(close.where(close > 0.0))

    n = len(log_close)
    out = np.full(n, np.nan, dtype=float)

    if n >= period:
        y_arr = log_close.values
        windows = np.lib.stride_tricks.sliding_window_view(y_arr, window_shape=period)
        x = np.arange(period, dtype=float)
        x_centered = x - x.mean()
        denom = float(np.dot(x_centered, x_centered))

        # 斜率
        centered_windows = windows - windows.mean(axis=1, keepdims=True)
        slopes = (windows @ x_centered) / denom

        # 拟合值与残差
        fitted = slopes[:, None] * x_centered[None, :]
        residuals = centered_windows - fitted
        resid_std = residuals.std(axis=1, ddof=1)
        resid_std = np.where(resid_std > 1e-12, resid_std, np.nan)

        # 信息比率 = 斜率 / 残差 std
        ir = slopes / resid_std

        # tanh 压缩尾部
        out[period - 1:] = np.tanh(ir)

    return pd.Series(out, index=group.index, dtype="float64")


def tm2_higher_moment_trend_health(
    group: pd.DataFrame,
    period: int = 30,
    lookback: int = 120,
) -> pd.Series:
    """高阶矩趋势健康度因子。

    经济假设：健康的上行趋势在对数收益分布上应表现为「适度正偏 + 低峰
    度」——正偏意味着上行日幅度大于下行日，低峰度意味着极端日少、分布
    集中于均值附近（趋势稳定）。反之，高峰度预示尾部风险积聚，即便方
    向向上也不可持续。用滚动窗口的偏度减去峰度惩罚项，再乘以平均收益，
    得到同时刻画方向、形态与尾部稳定性的趋势健康信号。与第一轮
    log_return_skew_momentum（仅用偏度）不同，本因子引入峰度作为「趋
    势稳定度」约束。
    """
    close = group["close"].astype(float)
    log_ret = np.log(close / close.shift(1))

    rolling_mean = log_ret.rolling(window=period, min_periods=period).mean()
    rolling_std = log_ret.rolling(window=period, min_periods=period).std()
    rolling_std = rolling_std.where(rolling_std > 1e-10, np.nan)

    def _skew(w: np.ndarray) -> float:
        if np.isnan(w).any():
            return np.nan
        m = w.mean()
        s = w.std()
        if s <= 1e-10:
            return 0.0
        return float(np.mean(((w - m) / s) ** 3))

    def _kurt(w: np.ndarray) -> float:
        if np.isnan(w).any():
            return np.nan
        m = w.mean()
        s = w.std()
        if s <= 1e-10:
            return 0.0
        # 超额峰度（excess kurtosis）
        return float(np.mean(((w - m) / s) ** 4) - 3.0)

    skew = log_ret.rolling(window=period, min_periods=period).apply(_skew, raw=True)
    kurt = log_ret.rolling(window=period, min_periods=period).apply(_kurt, raw=True)

    # 健康度 = 偏度 - 峰度惩罚（峰度越高越不健康）
    health = skew - 0.5 * kurt

    raw = health * rolling_mean

    # z-score 标准化并裁剪
    mean = raw.rolling(window=lookback, min_periods=period).mean()
    std = raw.rolling(window=lookback, min_periods=period).std()
    std = std.where(std > 1e-8, np.nan)
    z = (raw - mean) / std
    z = z.clip(-3.0, 3.0)
    return z.astype("float64")


def tm2_breakout_persistence_momentum(
    group: pd.DataFrame,
    period: int = 20,
    slope_period: int = 20,
) -> pd.Series:
    """突破持续性动量因子。

    经济假设：趋势的强弱不仅由斜率刻画，也由「创新高频率」刻画。在滚动
    窗口内，若收盘价频繁创出窗口内新高，说明买方持续突破阻力，趋势更
    可能延续。用滚动窗口内「创新高天数占比」乘以对数价格斜率，融合突
    破频率与趋势幅度。与 Donchian channel（价格在通道中的位置）不同，
    本因子度量的是「新高事件的发生频率」而非单点位置，对趋势持续性更
    敏感。
    """
    close = group["close"].astype(float)
    log_close = np.log(close.where(close > 0.0))

    # 滚动窗口内创新高天数占比
    # 创新高定义：当日 close 等于窗口内最大值（含当日）
    rolling_max = close.rolling(window=period, min_periods=period).max()
    is_new_high = (close >= rolling_max).astype(float)

    # 滚动窗口内新高占比
    new_high_ratio = is_new_high.rolling(window=period, min_periods=period).mean()

    # 对数价格斜率（向量化）
    n_price = len(log_close)
    slope_arr = np.full(n_price, np.nan, dtype=float)
    if n_price >= slope_period:
        y_arr = log_close.values
        windows = np.lib.stride_tricks.sliding_window_view(y_arr, window_shape=slope_period)
        x = np.arange(slope_period, dtype=float)
        x_centered = x - x.mean()
        denom = float(np.dot(x_centered, x_centered))
        slopes = (windows @ x_centered) / denom
        slope_arr[slope_period - 1:] = slopes

    slope = pd.Series(slope_arr, index=group.index, dtype="float64")

    # 新高占比偏离 0 的程度（占比越高越强），乘以斜率
    # new_high_ratio 在 [1/period, 1] 之间，直接作为权重
    raw = new_high_ratio * slope

    return raw.astype("float64")


# =============================================================================
# 候选因子注册表
# =============================================================================

CANDIDATES = [
    {
        "factor_id": "tm2_ema_slope_acceleration",
        "family": "trend_momentum",
        "module": "trend_momentum_revise2",
        "hypothesis": "快慢EMA斜率差作为趋势加速度，加速度由负转正预示趋势从酝酿进入加速期",
        "direction": "positive",
        "func_name": "tm2_ema_slope_acceleration",
        "params": {"fast": 10, "slow": 30, "slope_period": 5},
    },
    {
        "factor_id": "tm2_trend_information_ratio",
        "family": "trend_momentum",
        "module": "trend_momentum_revise2",
        "hypothesis": "对数价格回归斜率除以残差标准差（Sharpe-of-trend），每单位噪声的趋势强度越高趋势越可靠",
        "direction": "positive",
        "func_name": "tm2_trend_information_ratio",
        "params": {"period": 25},
    },
    {
        "factor_id": "tm2_higher_moment_trend_health",
        "family": "trend_momentum",
        "module": "trend_momentum_revise2",
        "hypothesis": "正偏低峰度的收益分布代表健康上行趋势，偏度减峰度惩罚乘均值收益刻画方向形态与尾部稳定性",
        "direction": "positive",
        "func_name": "tm2_higher_moment_trend_health",
        "params": {"period": 30, "lookback": 120},
    },
    {
        "factor_id": "tm2_breakout_persistence_momentum",
        "family": "trend_momentum",
        "module": "trend_momentum_revise2",
        "hypothesis": "滚动窗口内创新高天数占比越高买方突破阻力越持续，新高频率乘对数价格斜率融合突破频率与趋势幅度",
        "direction": "positive",
        "func_name": "tm2_breakout_persistence_momentum",
        "params": {"period": 20, "slope_period": 20},
    },
]
