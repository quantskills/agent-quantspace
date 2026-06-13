"""Universal OHLCV technical indicators.

These functions operate on single-symbol DataFrames and are strategy-agnostic.
Cross-sectional alpha expressions live in strategies/cross_sectional/factors.py.
"""

import inspect as _inspect
from collections.abc import Callable

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .utils import (
    calculate_atr,
    clip_outliers,
    rolling_regression_vectorized,
    rolling_zscore,
    safe_divide,
)

# =============================================================================
# Price / Momentum
# =============================================================================


def roc(group: pd.DataFrame, period: int = 20):
    """
    计算 ROC (Rate of Change) 变化率因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    period : int, optional
        计算周期, 默认为20天

    Returns
    -------
    pd.Series
        ROC因子序列
        公式: (close[t] - close[t-period]) / close[t-period]
    """
    return group["close"].pct_change(periods=period)


def ma(group: pd.DataFrame, period: int = 5):
    """
    计算 MA (Moving Average) 移动平均线因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    period : int, optional
        移动平均周期, 默认为5天

    Returns
    -------
    pd.Series
        MA因子序列
        返回当前价格相对于移动平均线的偏离度: (close - ma) / ma
    """
    close_prices = group["close"]
    ma_values = close_prices.rolling(window=period, min_periods=period).mean()
    return safe_divide(close_prices - ma_values, ma_values)


def daily_return(group: pd.DataFrame, **kwargs):
    """
    日收益率因子

    用于出场过滤：单日跌幅超过阈值时出场
    condition: lambda x: x > -0.04  (单日跌幅不超过4%)
    """
    close = group["close"]
    return close.pct_change()


def ma_cross(group: pd.DataFrame, short: int = 5, long: int = 20):
    """
    均线交叉因子

    返回短期均线相对长期均线的位置：
    > 0: 短期均线在长期均线上方 (多头排列)
    < 0: 短期均线在长期均线下方 (空头排列)

    用于出场过滤：
    condition: lambda x: x > 0  (只保留多头排列)
    """
    close = group["close"]
    ma_short = close.rolling(window=short, min_periods=short).mean()
    ma_long = close.rolling(window=long, min_periods=long).mean()
    return ma_short - ma_long


def price_above_ma(group: pd.DataFrame, period: int = 20):
    """
    价格相对均线位置因子

    返回价格相对于N日均线的偏离：
    > 0: 价格在均线上方
    < 0: 价格在均线下方

    用于出场过滤：
    condition: lambda x: x > 0  (价格在均线上方才持有)
    """
    close = group["close"]
    ma = close.rolling(window=period, min_periods=period).mean()
    return close - ma


def momentum_acceleration(group: pd.DataFrame, period: int = 10):
    """
    动量加速度因子（动量一阶导数）

    返回动量的变化速度：
    > 0: 动量加速（趋势增强）
    < 0: 动量减速（趋势减弱，可能反转）

    用于出场过滤：
    condition: lambda x: x > -0.01  (动量减速不超过阈值)
    """
    close = group["close"]

    # 动量 = N日涨跌幅
    momentum = close.pct_change(periods=period)

    # 动量加速度 = 动量的变化
    acceleration = momentum.diff()

    return acceleration


def momentum_weighted(group: pd.DataFrame, period: int = 25):
    """
    线性加权动量因子

    来源: 策略 #38 核心资产ETF轮动（线性增加权重）

    改进动量因子: 给近期数据更高权重（从1到2线性递增），
    更敏感地捕捉趋势变化。对 log(close) 做加权线性回归，
    计算 年化收益率 × R²。
    """
    close = group["close"]

    if len(close) < period:
        return pd.Series(np.full_like(close, np.nan), index=group.index)

    y = np.log(close.values)
    windows = np.lib.stride_tricks.sliding_window_view(y, window_shape=period)
    x = np.arange(period)
    w = np.linspace(1, 2, period)  # 线性递增权重

    n = period  # noqa: F841
    # 加权回归: slope = Σ(w*x*y)*Σ(w) - Σ(w*x)*Σ(w*y) / (Σ(w*x²)*Σ(w) - (Σ(w*x))²)
    wx = w * x
    sum_w = w.sum()
    sum_wx = wx.sum()
    sum_wx2 = (w * x**2).sum()
    denom = sum_wx2 * sum_w - sum_wx**2

    # 向量化计算
    sum_wy = (windows * w).sum(axis=1)
    sum_wxy = (windows * wx).sum(axis=1)

    slopes = (sum_wxy * sum_w - sum_wx * sum_wy) / denom
    intercepts = (sum_wy - slopes * sum_wx) / sum_w

    # 年化收益率
    annualized = (np.exp(slopes) ** 250) - 1

    # R² 计算
    predicted = intercepts[:, None] + slopes[:, None] * x[None, :]
    ss_res = (w * (windows - predicted) ** 2).sum(axis=1)
    y_mean_w = sum_wy / sum_w
    ss_tot = (w * (windows - y_mean_w[:, None]) ** 2).sum(axis=1)
    r_squared = np.where(ss_tot > 0, 1 - ss_res / ss_tot, 0)

    result = annualized * r_squared
    result = np.concatenate([np.full(period - 1, np.nan), result])

    return pd.Series(result, index=group.index)


def bias_momentum(group: pd.DataFrame, ma_period: int = 90, momentum_day: int = 25):
    """
    乖离动量因子

    来源: 策略 #36 RSRS择时+乖离动量

    计算价格相对 MA90 的乖离率序列，再对乖离率序列做线性拟合，
    得到乖离变化速度。比直接看价格更能反映"趋势加速/减速"。
    """
    close = group["close"]

    if len(close) < max(ma_period, momentum_day) + momentum_day:
        return pd.Series(np.full_like(close, np.nan), index=group.index)

    ma = close.rolling(window=ma_period, min_periods=ma_period).mean()
    bias = close / ma  # 乖离率

    # 滚动窗口对 bias 做线性拟合
    bias_vals = bias.values
    windows = np.lib.stride_tricks.sliding_window_view(bias_vals, window_shape=momentum_day)
    x = np.arange(momentum_day)

    n = momentum_day
    sum_x = x.sum()
    sum_x2 = (x**2).sum()
    denom = n * sum_x2 - sum_x**2

    sum_y = windows.sum(axis=1)
    sum_xy = (windows * x).sum(axis=1)

    slopes = (n * sum_xy - sum_x * sum_y) / denom

    # 用斜率作为乖离动量
    pad = max(ma_period, momentum_day) + momentum_day - 2
    result = np.concatenate([np.full(pad, np.nan), slopes])

    # 对齐长度
    if len(result) < len(close):
        result = np.concatenate([np.full(len(close) - len(result), np.nan), result])
    elif len(result) > len(close):
        result = result[-len(close) :]

    return pd.Series(result, index=group.index)


def mom_skip(group: pd.DataFrame, skip: int = 22, total: int = 252):
    """
    计算剔除近期的动量因子 (Skip-Month Momentum)

    排除最近 skip 天的收益，只看 skip~total 天之间的涨跌幅。
    用于避免短期反转效应对中长期动量的干扰。

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    skip : int, optional
        跳过的近期天数, 默认为22天
    total : int, optional
        总回看天数, 默认为252天

    Returns
    -------
    pd.Series
        Skip动量因子序列
        公式: close[t-skip] / close[t-total] - 1
    """
    close = group["close"]
    return close.shift(skip) / close.shift(total) - 1


def high_vol_odds(group: pd.DataFrame, period: int = 20):
    """
    High-Vol Odds Factor (Huaxin Research Report)

    Logic: past `period`-day volatility (high = oversold release) + return inverted (low = post-decline).
    Standardize then equal-weight combine. Higher value = high vol + low return = mean-reversion opportunity.
    """
    close = group["close"]
    ret = close.pct_change()

    lookback = period * 5
    min_p = max(period, lookback)

    # Rolling volatility z-score
    vol = ret.rolling(period, min_periods=period).std()
    vol_mean = vol.rolling(lookback, min_periods=min_p).mean()
    vol_std = vol.rolling(lookback, min_periods=min_p).std()
    vol_z = (vol - vol_mean) / vol_std.replace(0, np.nan)

    # Rolling ROC z-score (inverted)
    roc_val = close / close.shift(period) - 1
    roc_mean = roc_val.rolling(lookback, min_periods=min_p).mean()
    roc_std = roc_val.rolling(lookback, min_periods=min_p).std()
    roc_z = (roc_val - roc_mean) / roc_std.replace(0, np.nan)

    # Composite: high vol + low return (invert ROC)
    return vol_z - roc_z


# =============================================================================
# Trend
# =============================================================================


def rsrs_v3(group: pd.DataFrame, period: int = 20):
    """
    计算 RSRS (Resistance Support Relative Strength) 因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high' 和 'low' 列
    period : int, optional
        计算 OLS 线性回归的滚动窗口期，默认为 20 天

    Returns
    -------
    pd.Series
        RSRS 因子序列
    """
    N = period
    M = N * 3

    # 使用向量化的滚动回归
    slopes, r_squareds = rolling_regression_vectorized(group["high"], group["low"], N)

    # 计算斜率的Z-score标准分
    z_score_beta = rolling_zscore(slopes, M, M)

    # 计算最终RSRS因子值
    return z_score_beta * r_squareds


def rsrs_v2(group: pd.DataFrame, period: int = 10):
    """
    计算 RSRS_V2 (阻力支撑相对强度 版本2) 因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high' 和 'low' 列
    period : int, optional
        回归窗口期, 默认为10天

    Returns
    -------
    pd.Series
        RSRS_V2因子序列
    """
    high_prices = group["high"]
    low_prices = group["low"]

    # 计算差分序列（向量化操作）
    delta_high = high_prices.diff()
    delta_low = low_prices.diff()

    # 向量化计算滚动线性回归斜率
    rolling_corr = delta_high.rolling(window=period, min_periods=3).corr(delta_low)
    rolling_std_high = delta_high.rolling(window=period, min_periods=3).std()
    rolling_std_low = delta_low.rolling(window=period, min_periods=3).std()

    # 计算斜率
    return safe_divide(rolling_corr * rolling_std_high, rolling_std_low)


def rsrs_v1(group: pd.DataFrame, period: int = 10):
    """
    计算 RSRS_V1 (阻力支撑相对强度 版本1) 因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high' 和 'low' 列
    period : int, optional
        差分周期, 默认为10天

    Returns
    -------
    pd.Series
        RSRS_V1因子序列
    """
    high_prices = group["high"]
    low_prices = group["low"]

    # 计算period天的差分
    delta_high = high_prices.diff(period)
    delta_low = low_prices.diff(period)

    # 安全的除法操作
    result = safe_divide(delta_high, delta_low, np.nan)

    # 对于过大的异常值设为NaN
    return result.where(result.abs() <= 100, np.nan)


def rsrs(group: pd.DataFrame, period: int = 18):
    """
    计算 RSRS (阻力支撑相对强度) 因子 - 基础版本
    使用OLS回归计算high对low的斜率

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high' 和 'low' 列
    period : int, optional
        回归窗口期, 默认为18天

    Returns
    -------
    pd.Series
        RSRS因子序列（原始斜率值）
    """
    import statsmodels.api as sm

    high_prices = group["high"]
    low_prices = group["low"]

    # 初始化结果序列
    rsrs_values = pd.Series(index=group.index, dtype=float)

    # 滚动计算OLS回归
    for i in range(period - 1, len(group)):
        window_low = low_prices.iloc[i - period + 1 : i + 1].values
        window_high = high_prices.iloc[i - period + 1 : i + 1].values

        try:
            # 添加常数项并进行OLS回归
            X = sm.add_constant(window_low)
            model = sm.OLS(window_high, X)
            results = model.fit()
            rsrs_values.iloc[i] = results.params[1]  # 斜率
        except Exception:
            rsrs_values.iloc[i] = np.nan

    return rsrs_values


def rsrs_norm(group: pd.DataFrame, N: int = 18, M: int = 200):
    """
    计算标准化RSRS因子
    仿造backtrader_indicators.py中的RSRS_Norm逻辑

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high' 和 'low' 列
    N : int, optional
        回归窗口期, 默认为18天
    M : int, optional
        标准化窗口期, 默认为600天

    Returns
    -------
    pd.Series
        标准化RSRS因子序列
    """

    high_prices = group["high"]
    low_prices = group["low"]

    # 初始化结果序列
    rsrs_values = pd.Series(index=group.index, dtype=float)
    r2_values = pd.Series(index=group.index, dtype=float)

    # 滚动计算OLS回归
    for i in range(N - 1, len(group)):
        window_low = low_prices.iloc[i - N + 1 : i + 1].values
        window_high = high_prices.iloc[i - N + 1 : i + 1].values

        try:
            # 添加常数项并进行OLS回归
            X = sm.add_constant(window_low)
            model = sm.OLS(window_high, X)
            results = model.fit()
            rsrs_values.iloc[i] = results.params[1]  # 斜率
            r2_values.iloc[i] = results.rsquared  # R平方
        except Exception:
            rsrs_values.iloc[i] = np.nan
            r2_values.iloc[i] = np.nan

    # 标准化处理：(RSRS - MA(RSRS)) / STD(RSRS)
    rsrs_ma = rsrs_values.rolling(window=M, min_periods=N).mean()
    rsrs_std = rsrs_values.rolling(window=M, min_periods=N).std()
    rsrs_norm = safe_divide(rsrs_values - rsrs_ma, rsrs_std, 0.0)

    # RSRS_R2 = RSRS_Norm * R2
    rsrs_r2 = rsrs_norm * r2_values

    # Beta_right = RSRS * RSRS_R2
    beta_right = rsrs_values * rsrs_r2

    # 返回beta_right作为最终因子值
    return beta_right


def trend_score(group: pd.DataFrame, period: int = 25):
    """
    计算 trend_score 趋势评分因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    period : int, optional
        回归窗口期, 默认为25天

    Returns
    -------
    pd.Series
        trend_score 因子序列
    """
    close_prices = group["close"]

    # 创建时间序列作为x轴
    x = np.arange(period)
    # 预计算以提高效率
    std_x = np.std(x)

    if std_x == 0:  # 避免除零
        return pd.Series(np.nan, index=group.index)

    def rolling_trend(y: np.ndarray) -> float:
        """为单个窗口计算趋势"""
        if np.isnan(y).any():
            return np.nan

        # 计算相关性和斜率
        r = np.corrcoef(x, y)[0, 1]
        if np.isnan(r):
            return np.nan

        std_y = np.std(y)
        slope = r * (std_y / std_x)

        return slope * (r**2)

    # 使用滚动应用函数
    trend_scores = close_prices.rolling(window=period).apply(rolling_trend, raw=True)

    # 标准化处理
    standardization_window = 2 * period
    return rolling_zscore(trend_scores, standardization_window, period)


def trend_score_v2(group: pd.DataFrame, period: int = 25):
    """
    向量化计算趋势评分：年化收益率 × R平方

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    period : int, optional
        计算窗口长度，默认25天

    Returns
    -------
    pd.Series
        趋势评分数组
        前period-1位为NaN
    """
    close = group["close"]

    if len(close) < period:
        return pd.Series(np.full_like(close, np.nan), index=group.index)

    y = np.log(close.values)
    windows = np.lib.stride_tricks.sliding_window_view(y, window_shape=period)
    x = np.arange(period)

    # 预计算固定值
    n = period
    sum_x = x.sum()
    sum_x2 = (x**2).sum()
    denominator = n * sum_x2 - sum_x**2

    # 滑动窗口统计量
    sum_y = windows.sum(axis=1)
    sum_xy = (windows * x).sum(axis=1)

    # 回归系数
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n

    # 年化收益率
    annualized_returns = np.exp(slope * 250) - 1

    # R平方计算
    y_pred = slope[:, None] * x + intercept[:, None]
    residuals = windows - y_pred
    ss_res = np.sum(residuals**2, axis=1)

    sum_y2 = np.sum(windows**2, axis=1)
    ss_tot = sum_y2 - (sum_y**2) / n
    r_squared = 1 - (ss_res / ss_tot)
    r_squared = np.nan_to_num(r_squared, nan=0.0)  # 处理零方差情况

    # 综合评分
    score = annualized_returns * r_squared

    # 对齐原始序列长度
    full_score = pd.Series(np.full_like(close, np.nan), index=close.index)
    full_score.iloc[period - 1 :] = score

    return full_score


def trend_score_v2_skip(group: pd.DataFrame, period: int = 252, skip: int = 22):
    """
    计算剔除近期的 trend_score_v2

    排除最近 skip 天的收益，只看 skip~period 天之间的趋势。
    用于避免短期反转效应对中长期动量的干扰。

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    period : int, optional
        总回看天数，默认252天
    skip : int, optional
        跳过的近期天数，默认22天

    Returns
    -------
    pd.Series
        剔除近期后的趋势评分序列
    """
    if skip < 0 or period <= skip:
        raise ValueError("period must be greater than skip, and skip must be non-negative")

    shifted_group = group.copy()
    shifted_group["close"] = group["close"].shift(skip)
    return trend_score_v2(shifted_group, period=period - skip)


def supertrend(
    group: pd.DataFrame, period: int = 14, multiplier: float = 2.0, standardize_window: int = 60
):
    """
    计算超级趋势线 (SuperTrend) 连续因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high', 'low', 'close' 列
    period : int, optional
        ATR计算周期, 默认为14天
    multiplier : float, optional
        ATR倍数，默认为2.0
    standardize_window : int, optional
        滚动标准化窗口期, 默认为60天

    Returns
    -------
    pd.Series
        超级趋势线因子序列
    """
    high_prices = group["high"]
    low_prices = group["low"]
    close_prices = group["close"]

    # 计算ATR
    atr = calculate_atr(high_prices, low_prices, close_prices, period)

    # 计算中心线
    hl_avg = (high_prices + low_prices) / 2

    # 动态multiplier
    atr_rolling_mean = atr.rolling(window=period * 2, min_periods=period).mean()
    volatility_ratio = safe_divide(atr, atr_rolling_mean, 1.0)
    adaptive_multiplier = multiplier * (0.8 + 0.4 * np.tanh(volatility_ratio - 1))

    # 基础上下轨
    basic_upper = hl_avg + adaptive_multiplier * atr
    basic_lower = hl_avg - adaptive_multiplier * atr

    # 动态调整轨道
    final_upper = pd.Series(np.nan, index=group.index)
    final_lower = pd.Series(np.nan, index=group.index)
    supertrend_direction = pd.Series(np.nan, index=group.index)

    # 初始化
    final_upper.iloc[:period] = basic_upper.iloc[:period]
    final_lower.iloc[:period] = basic_lower.iloc[:period]

    for i in range(period, len(group)):
        prev_close = close_prices.iloc[i - 1]
        curr_close = close_prices.iloc[i]

        # 上轨调整
        if basic_upper.iloc[i] < final_upper.iloc[i - 1] or prev_close > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        # 下轨调整
        if basic_lower.iloc[i] > final_lower.iloc[i - 1] or prev_close < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

        # 趋势方向
        if curr_close <= final_lower.iloc[i]:
            supertrend_direction.iloc[i] = -1
        elif curr_close >= final_upper.iloc[i]:
            supertrend_direction.iloc[i] = 1
        else:
            supertrend_direction.iloc[i] = supertrend_direction.iloc[i - 1]

    # 向量化计算SuperTrend线
    supertrend_line = pd.Series(np.nan, index=group.index)
    supertrend_line = np.where(
        supertrend_direction == 1,
        final_lower,
        np.where(supertrend_direction == -1, final_upper, supertrend_line),
    )
    supertrend_line = pd.Series(supertrend_line, index=group.index, name="supertrend_line")

    # 计算连续因子值
    price_deviation = safe_divide(close_prices - supertrend_line, supertrend_line, 0.0)

    # 趋势强度
    channel_width = final_upper - final_lower
    channel_position = safe_divide(close_prices - final_lower, channel_width, 0.5)
    trend_strength = (channel_position - 0.5) * 2

    # 向量化计算趋势持续时间
    direction_changes = supertrend_direction.diff().ne(0)
    trend_block = direction_changes.cumsum()
    trend_duration = (group.groupby(trend_block).cumcount() + 1).rename("trend_duration")

    duration_weight = np.clip(np.log1p(trend_duration) / np.log1p(period), 0.1, 2.0)

    # 波动率调整
    price_volatility = close_prices.pct_change().rolling(window=period).std()
    avg_volatility = price_volatility.rolling(window=period * 2).mean()
    vol_adjustment = np.tanh(safe_divide(price_volatility, avg_volatility, 1.0))

    # 综合因子
    raw_factor = (
        price_deviation * 0.4 * supertrend_direction
        + trend_strength * 0.3
        + duration_weight * 0.2 * supertrend_direction
        + vol_adjustment * 0.1 * supertrend_direction
    )

    # 标准化和平滑
    standardized = rolling_zscore(raw_factor, standardize_window, period)
    smoothed = standardized.ewm(alpha=0.15, adjust=False).mean()

    return clip_outliers(smoothed)


def donchian_channel(group: pd.DataFrame, period: int = 20, standardize_window: int = 60):
    """
    计算唐安奇通道因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high', 'low', 'close' 列
    period : int, optional
        唐安奇通道周期, 默认为20天
    standardize_window : int, optional
        滚动标准化窗口期, 默认为60天

    Returns
    -------
    pd.Series
        唐安奇通道因子序列
    """
    high_prices = group["high"]
    low_prices = group["low"]
    close_prices = group["close"]

    # 计算唐安奇通道
    upper_channel = high_prices.rolling(window=period, min_periods=period).max()
    lower_channel = low_prices.rolling(window=period, min_periods=period).min()
    middle_channel = (upper_channel + lower_channel) / 2
    channel_width = upper_channel - lower_channel

    # 价格在通道中的相对位置
    position_ratio = safe_divide(close_prices - lower_channel, channel_width, 0.5)
    position_factor = (position_ratio - 0.5) * 2

    # 突破强度
    upper_breakout = np.maximum(0, close_prices - upper_channel)
    lower_breakout = np.minimum(0, close_prices - lower_channel)
    breakout_strength = safe_divide(upper_breakout + lower_breakout, channel_width, 0.0)

    # 通道宽度调整
    avg_channel_width = channel_width.rolling(window=period * 2, min_periods=period).mean()
    width_ratio = safe_divide(channel_width, avg_channel_width, 1.0)
    width_adjustment = np.tanh(2 - width_ratio)

    # 趋势确认
    trend_confirmation = safe_divide(close_prices - middle_channel, channel_width, 0.0)

    # 综合因子
    raw_factor = (
        position_factor * 0.4
        + breakout_strength * 0.3
        + trend_confirmation * 0.2
        + width_adjustment * 0.1
    )

    # 标准化和平滑
    standardized = rolling_zscore(raw_factor, standardize_window, period)
    smoothed = standardized.ewm(alpha=0.1, adjust=False).mean()

    return clip_outliers(smoothed)


# =============================================================================
# Volume
# =============================================================================


def ma_vol(group: pd.DataFrame, period: int = 5):
    """
    计算 MA_VOL (成交量移动平均) 因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'volume' 列
    period : int, optional
        移动平均周期, 默认为5天

    Returns
    -------
    pd.Series
        MA_VOL因子序列
    """
    return group["volume"].rolling(window=period, min_periods=period).mean()


def ma_vol_ratio(group: pd.DataFrame, period_short: int = 5, period_long: int = 20):
    """
    计算 MA_VOL_RATIO (短期/长期成交量移动平均比率) 因子

    Parameters
    ----------
    df : pd.DataFrame
        数据矩阵，必须包含 'volume' 列，且索引为 ('symbol', 'eob')
    period_short : int, optional
        短期移动平均周期, 默认为5天
    period_long : int, optional
        长期移动平均周期, 默认为20天

    Returns
    -------
    pd.Series
        MA_VOL_RATIO因子序列，索引为 ('symbol', 'eob')
    """
    short_ma = ma_vol(group, period_short)
    long_ma = ma_vol(group, period_long)

    return safe_divide(short_ma, long_ma, np.nan)


def orb(df: pd.DataFrame, period: int = 14):
    """
    计算ORB (Opening Range Breakout) 连续因子值

    Parameters
    ----------
    df : pd.DataFrame
        输入的行情数据，必须包含 'open', 'high', 'low', 'close', 'volume' 列
    period : int, optional
        计算ATR和历史统计的回看周期（天），默认为14

    Returns
    -------
    pd.Series
        ORB强度因子序列，索引为 ('symbol', 'eob')
    """
    # 移除 validate_multiindex 和 prepare_daily_data
    # 假设 df 是单个 symbol 的数据 (但包含日期作为索引)

    # 警告：ORB 需要日度数据，如果是 5min 数据，FunctionFactor 的 groupby 会传入单个 symbol 的 5min 数据
    # 如果原始逻辑需要聚合为日度，这里需要自己处理
    # 这里的原始逻辑比较复杂，因为它之前自己处理了日度聚合

    # 简单起见，我们保留原有逻辑的核心，但适应 FunctionFactor 的传入数据
    # 假设传入的 df 已经是时间序列索引 (因为 FunctionFactor 会传入 Series/DF)

    prev_close = df["close"].shift(1)

    # 计算ATR
    atr = calculate_atr(df["high"], df["low"], df["close"], period)

    # 计算开盘缺口强度
    gap_strength = safe_divide(df["open"] - prev_close, atr, np.nan)

    # 计算开盘后动量强度
    intraday_momentum = safe_divide(df["close"] - df["open"], atr, np.nan)

    # 计算相对成交量
    avg_volume = df["volume"].rolling(window=period, min_periods=1).mean().shift(1)
    relative_volume = safe_divide(df["volume"], avg_volume, 1.0)

    # 计算价格波动率
    price_volatility = safe_divide(atr, df["close"].shift(1), np.nan)

    # 综合ORB强度因子
    orb_raw = (gap_strength + intraday_momentum) * np.log1p(relative_volume) * price_volatility

    # 标准化
    standardization_window = period * 3
    return rolling_zscore(orb_raw, standardization_window, period)


def orb_relvol(df: pd.DataFrame, period: int = 14):
    """
    计算相对成交量（Relative Volume）因子

    Parameters
    ----------
    df : pd.DataFrame
        输入的行情数据，必须包含 'volume' 列
    period : int, optional
        计算平均成交量的回看窗口期，默认为14天

    Returns
    -------
    pd.Series
        相对成交量因子序列，索引为 ('symbol', 'eob')
    """
    # 计算历史平均开盘成交量 (这里直接用平均成交量替代)
    # 原逻辑比较复杂，涉及到 prepare_daily_data 和开盘成交量提取
    # 如果数据是日线的，这里就是相对成交量

    avg_volume = df["volume"].rolling(window=period, min_periods=1).mean().shift(1)
    relative_volume = safe_divide(df["volume"], avg_volume, 1.0)

    return relative_volume


def stand_orb_relvol(df: pd.DataFrame, period: int = 14):
    """
    计算标准化相对成交量（Standardized Relative Volume）因子

    Parameters
    ----------
    df : pd.DataFrame
        输入的行情数据，必须包含 'volume' 列
    period : int, optional
        计算平均成交量的回看窗口期，默认为14天

    Returns
    -------
    pd.Series
        标准化相对成交量因子序列，索引为 ('symbol', 'eob')
    """
    # 获取原始相对成交量因子
    raw_relvol = orb_relvol(df, period)

    # 标准化处理
    standardization_window = period * 5
    return rolling_zscore(raw_relvol, standardization_window, period)


# =============================================================================
# Efficiency
# =============================================================================


def er(group: pd.DataFrame, period: int = 14):
    """
    计算 ER (Efficiency Ratio) 效率系数因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    period : int, optional
        计算周期, 默认为14天

    Returns
    -------
    pd.Series
        ER因子序列
    """
    close_prices = group["close"]

    # 向量化计算价格变化和路径长度
    price_changes = close_prices.diff(period).abs()
    path_lengths = close_prices.diff().abs().rolling(window=period, min_periods=period).sum()

    # 计算效率系数
    return safe_divide(price_changes, path_lengths, 0.0)


def er_enhanced(group: pd.DataFrame, period: int = 14, lookback: int = 60):
    """
    计算增强版 ER (Enhanced Efficiency Ratio) 效率系数因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high', 'low', 'close' 列
    period : int, optional
        计算ER的基础周期, 默认为14天
    lookback : int, optional
        用于标准化的回看周期, 默认为60天

    Returns
    -------
    pd.Series
        增强ER因子序列
    """
    close_prices = group["close"]

    # 计算基础ER和价格变化
    price_changes = close_prices.diff(period)
    price_changes_abs = price_changes.abs()
    path_lengths = close_prices.diff().abs().rolling(window=period, min_periods=period).sum()

    er_values = safe_divide(price_changes_abs, path_lengths, 0.0)

    # 计算ATR
    atr = calculate_atr(group["high"], group["low"], group["close"], period)

    # ATR相对比率
    atr_ma = atr.rolling(window=lookback, min_periods=period).mean()
    atr_ratio = safe_divide(atr, atr_ma, 1.0)

    # 方向性ER
    directional_er = er_values * np.sign(price_changes)

    # 相对ER
    relative_er = rolling_zscore(er_values, lookback, period)

    # 波动率调整
    volatility_adj = np.tanh(atr_ratio - 1)

    # 增强ER
    enhanced_er = directional_er * (1 + relative_er * 0.3) * (1 + volatility_adj * 0.2)

    # 最终标准化
    final_standardized = rolling_zscore(enhanced_er, lookback, period)

    return clip_outliers(final_standardized)


def er_adaptive(
    group: pd.DataFrame, short_period: int = 7, long_period: int = 21, adapt_period: int = 60
):
    """
    计算自适应 ER (Adaptive Efficiency Ratio) 因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high', 'low', 'close' 列
    short_period : int, optional
        短期周期, 默认为7天
    long_period : int, optional
        长期周期, 默认为21天
    adapt_period : int, optional
        自适应周期, 默认为60天

    Returns
    -------
    pd.Series
        自适应ER因子序列
    """
    close_prices = group["close"]

    # 计算短期和长期ER
    def calc_er_vectorized(period):
        price_changes = close_prices.diff(period).abs()
        path_lengths = close_prices.diff().abs().rolling(window=period, min_periods=period).sum()
        return safe_divide(price_changes, path_lengths, 0.0)

    short_er = calc_er_vectorized(short_period)
    long_er = calc_er_vectorized(long_period)

    # 市场状态识别
    returns = close_prices.pct_change()
    volatility = returns.rolling(window=adapt_period).std()
    volatility_ma = volatility.rolling(window=adapt_period).mean()

    # 自适应权重
    vol_ratio = safe_divide(volatility, volatility_ma, 1.0)
    short_weight = 1 / (1 + np.exp(-2 * (vol_ratio - 1)))
    long_weight = 1 - short_weight

    # 加权ER
    adaptive_er = short_weight * short_er + long_weight * long_er

    # 添加趋势方向
    price_trend = close_prices.rolling(window=long_period).apply(
        lambda x: np.sign(x.iloc[-1] - x.iloc[0]) if len(x) == long_period else 0, raw=False
    )

    directional_adaptive_er = adaptive_er * price_trend

    # 标准化
    standardized = rolling_zscore(directional_adaptive_er, adapt_period, short_period)

    return clip_outliers(standardized)


def er_directional(group: pd.DataFrame, period: int = 14, standardize_window: int = 60):
    """
    计算方向性 ER (Directional Efficiency Ratio) 因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    period : int, optional
        计算ER的基础周期, 默认为14天
    standardize_window : int, optional
        滚动标准化窗口期, 默认为60天

    Returns
    -------
    pd.Series
        方向性ER因子序列
    """
    close_prices = group["close"]

    # 向量化计算价格变化和路径长度
    price_changes = close_prices.diff(period)  # 保留符号
    price_changes_abs = price_changes.abs()
    path_lengths = close_prices.diff().abs().rolling(window=period, min_periods=period).sum()

    # 计算基础ER
    er_base = safe_divide(price_changes_abs, path_lengths, 0.0)

    # 添加方向性
    directional_er = er_base * np.sign(price_changes)

    # 标准化
    standardized = rolling_zscore(directional_er, standardize_window, period)

    return clip_outliers(standardized)


# =============================================================================
# Oscillators
# =============================================================================


def cci(group: pd.DataFrame, period: int = 20):
    """
    计算 CCI (Commodity Channel Index) 商品通道指数因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high', 'low', 'close' 列
    period : int, optional
        计算周期, 默认为20天

    Returns
    -------
    pd.Series
        CCI因子序列
    """
    # 计算典型价格
    typical_price = (group["high"] + group["low"] + group["close"]) / 3

    # 计算简单移动平均
    sma_tp = typical_price.rolling(window=period, min_periods=period).mean()

    # 计算平均绝对偏差
    mad = typical_price.rolling(window=period, min_periods=period).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
    )

    # 计算CCI
    cci_factor = safe_divide(typical_price - sma_tp, 0.015 * mad, np.nan)

    return cci_factor


def slowkdj(
    group: pd.DataFrame,
    k_period: int = 14,
    k_smooth: int = 3,
    d_smooth: int = 3,
    standardize_window: int = 60,
):
    """
    计算 Slow KDJ 慢速随机指标因子（反转因子）

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high', 'low', 'close' 列
    k_period : int, optional
        计算K值的周期, 默认为14天
    k_smooth : int, optional
        K值平滑周期, 默认为3天
    d_smooth : int, optional
        D值平滑周期, 默认为3天
    standardize_window : int, optional
        滚动标准化窗口期, 默认为60天

    Returns
    -------
    pd.Series
        Slow KDJ因子序列
        反转逻辑：K和D值越高表示越超买（未来可能下跌），因子值越低
    """
    high_prices = group["high"]
    low_prices = group["low"]
    close_prices = group["close"]

    # 计算最高价和最低价的滚动窗口
    highest_high = high_prices.rolling(window=k_period, min_periods=k_period).max()
    lowest_low = low_prices.rolling(window=k_period, min_periods=k_period).min()

    # 计算RSV（Raw Stochastic Value）
    rsv = safe_divide(close_prices - lowest_low, highest_high - lowest_low, 0.5) * 100

    # 计算慢速K值（对RSV进行平滑）
    slow_k = rsv.rolling(window=k_smooth, min_periods=k_smooth).mean()

    # 计算慢速D值（对K值进行平滑）
    slow_d = slow_k.rolling(window=d_smooth, min_periods=d_smooth).mean()

    # 计算J值
    j_value = 3 * slow_k - 2 * slow_d

    # KDJ综合信号（反转逻辑）
    # 当K、D值较高时，表示超买，预期价格下跌，因子值应该为负
    # 当K、D值较低时，表示超卖，预期价格上涨，因子值应该为正
    kdj_signal = (100 - slow_k) + (100 - slow_d) + (100 - j_value)
    kdj_factor = kdj_signal / 3 - 50  # 归一化到-50到50之间

    # 添加动量确认
    price_momentum = close_prices.pct_change(k_period)
    momentum_adjustment = np.tanh(price_momentum * 10)  # 限制在-1到1之间

    # 结合KDJ信号和动量确认
    combined_factor = kdj_factor * (1 + momentum_adjustment * 0.3)

    # 标准化处理
    standardized = rolling_zscore(combined_factor, standardize_window, k_period)

    return clip_outliers(standardized)


def williams_r(group: pd.DataFrame, period: int = 14, standardize_window: int = 60):
    """
    计算 Williams %R 威廉指标因子（反转因子）

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'high', 'low', 'close' 列
    period : int, optional
        计算周期, 默认为14天
    standardize_window : int, optional
        滚动标准化窗口期, 默认为60天

    Returns
    -------
    pd.Series
        Williams %R因子序列
        反转逻辑：%R越接近-100表示超卖，越接近0表示超买
    """
    high_prices = group["high"]
    low_prices = group["low"]
    close_prices = group["close"]

    # 计算最高价和最低价的滚动窗口
    highest_high = high_prices.rolling(window=period, min_periods=period).max()
    lowest_low = low_prices.rolling(window=period, min_periods=period).min()

    # 计算Williams %R
    williams_r_raw = safe_divide(highest_high - close_prices, highest_high - lowest_low, 0.5) * (
        -100
    )

    # 反转逻辑：将%R转换为反转信号
    # %R在-80以下为超卖（看多信号），在-20以上为超买（看空信号）
    reversal_signal = williams_r_raw + 50  # 转换到-50到50的范围

    # 添加趋势过滤
    price_trend = close_prices.rolling(window=period).apply(
        lambda x: (x.iloc[-1] - x.iloc[0]) / x.iloc[0] if x.iloc[0] != 0 else 0, raw=False
    )
    trend_filter = np.tanh(price_trend * 20)  # 趋势强度调整

    # 综合反转因子
    combined_factor = reversal_signal * (1 - abs(trend_filter) * 0.5)  # 趋势强时减弱反转信号

    # 标准化处理
    standardized = rolling_zscore(combined_factor, standardize_window, period)

    return clip_outliers(standardized)


def rsi(group: pd.DataFrame, period: int = 14):
    """
    RSI (Relative Strength Index) 相对强弱指标

    返回 0-100 的 RSI 值：
    > 70: 超买区域
    < 30: 超卖区域

    用于出场过滤：
    condition: lambda x: x < 70  (RSI超买时出场)
    condition: lambda x: x > 30  (RSI超卖时入场)
    """
    close = group["close"]
    delta = close.diff()

    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))

    return rsi_val.fillna(50)  # NaN 填充为中性值


def rsi_divergence(
    group: pd.DataFrame,
    rsi_period: int = 14,
    divergence_period: int = 20,
    standardize_window: int = 60,
):
    """
    计算 RSI 背离因子（反转因子）

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    rsi_period : int, optional
        RSI计算周期, 默认为14天
    divergence_period : int, optional
        背离检测周期, 默认为20天
    standardize_window : int, optional
        滚动标准化窗口期, 默认为60天

    Returns
    -------
    pd.Series
        RSI背离因子序列
        反转逻辑：检测价格与RSI的背离，预示趋势反转
    """
    close_prices = group["close"]

    # 计算RSI
    price_change = close_prices.diff()
    gains = price_change.where(price_change > 0, 0)
    losses = -price_change.where(price_change < 0, 0)

    avg_gains = gains.rolling(window=rsi_period, min_periods=rsi_period).mean()
    avg_losses = losses.rolling(window=rsi_period, min_periods=rsi_period).mean()

    rs = safe_divide(avg_gains, avg_losses, 1.0)
    rsi = 100 - (100 / (1 + rs))

    # 检测价格和RSI的背离
    price_slope = close_prices.rolling(window=divergence_period).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == divergence_period else 0,
        raw=False,
    )

    rsi_slope = rsi.rolling(window=divergence_period).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == divergence_period else 0,
        raw=False,
    )

    # 背离信号：价格和RSI斜率方向相反
    divergence_signal = -price_slope * rsi_slope  # 相反时为正值

    # RSI极值信号
    rsi_extreme = np.where(
        rsi > 70,
        -(rsi - 70) / 30,  # 超买时负信号
        np.where(rsi < 30, (30 - rsi) / 30, 0),
    )  # 超卖时正信号

    # 综合反转因子
    reversal_factor = divergence_signal * 0.6 + rsi_extreme * 0.4

    # 添加波动率调整
    volatility = close_prices.pct_change().rolling(window=rsi_period).std()
    avg_volatility = volatility.rolling(window=standardize_window).mean()
    vol_adjustment = safe_divide(volatility, avg_volatility, 1.0)

    # 波动率高时增强反转信号
    adjusted_factor = reversal_factor * np.sqrt(vol_adjustment)

    # 标准化处理
    standardized = rolling_zscore(adjusted_factor, standardize_window, rsi_period)

    return clip_outliers(standardized)


# =============================================================================
# Mean-reversion
# =============================================================================


def bollinger_reversal(
    group: pd.DataFrame, period: int = 20, std_dev: float = 2.0, standardize_window: int = 60
):
    """
    计算 Bollinger Bands 布林带反转因子

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    period : int, optional
        移动平均周期, 默认为20天
    std_dev : float, optional
        标准差倍数, 默认为2.0
    standardize_window : int, optional
        滚动标准化窗口期, 默认为60天

    Returns
    -------
    pd.Series
        布林带反转因子序列
        反转逻辑：价格触及上轨时看空，触及下轨时看多
    """
    close_prices = group["close"]

    # 计算布林带
    sma = close_prices.rolling(window=period, min_periods=period).mean()
    std = close_prices.rolling(window=period, min_periods=period).std()

    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    _middle_band = sma  # noqa: F841

    # 计算价格相对于布林带的位置
    band_width = upper_band - lower_band
    price_position = safe_divide(close_prices - lower_band, band_width, 0.5)

    # 反转信号：价格位置越极端，反转信号越强
    # 位置 > 0.8 时看空，位置 < 0.2 时看多
    reversal_signal = np.where(
        price_position > 0.8,
        -(price_position - 0.8) * 5,  # 上轨附近看空
        np.where(price_position < 0.2, (0.2 - price_position) * 5, 0),
    )  # 下轨附近看多

    # 布林带收缩/扩张状态
    current_width = band_width
    avg_width = band_width.rolling(window=period * 2, min_periods=period).mean()
    width_ratio = safe_divide(current_width, avg_width, 1.0)

    # 布林带收缩时增强反转信号
    squeeze_multiplier = np.where(width_ratio < 0.8, 1.5, 1.0)

    # 价格突破确认
    upper_break = (close_prices > upper_band).astype(int)
    lower_break = (close_prices < lower_band).astype(int)
    breakout_signal = upper_break * (-1) + lower_break * 1  # 突破上轨为-1，突破下轨为1

    # 综合反转因子
    combined_factor = (reversal_signal + breakout_signal) * squeeze_multiplier

    # 添加成交量确认（如果有成交量数据）
    if "volume" in group.columns:
        volume = group["volume"]
        avg_volume = volume.rolling(window=period, min_periods=period).mean()
        volume_ratio = safe_divide(volume, avg_volume, 1.0)
        volume_confirmation = np.log1p(volume_ratio)  # 成交量放大时增强信号
        combined_factor = combined_factor * volume_confirmation

    # 标准化处理
    standardized = rolling_zscore(combined_factor, standardize_window, period)

    return clip_outliers(standardized)


def mean_reversion(
    group: pd.DataFrame,
    short_period: int = 5,
    long_period: int = 20,
    threshold: float = 1.5,
    standardize_window: int = 60,
):
    """
    计算均值回归因子（反转因子）

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    short_period : int, optional
        短期均线周期, 默认为5天
    long_period : int, optional
        长期均线周期, 默认为20天
    threshold : float, optional
        偏离阈值倍数, 默认为1.5
    standardize_window : int, optional
        滚动标准化窗口期, 默认为60天

    Returns
    -------
    pd.Series
        均值回归因子序列
        反转逻辑：价格偏离长期均值越远，回归概率越大
    """
    close_prices = group["close"]

    # 计算短期和长期均线
    short_ma = close_prices.rolling(window=short_period, min_periods=short_period).mean()
    long_ma = close_prices.rolling(window=long_period, min_periods=long_period).mean()

    # 计算价格相对于长期均线的偏离程度
    long_std = close_prices.rolling(window=long_period, min_periods=long_period).std()
    price_deviation = safe_divide(close_prices - long_ma, long_std, 0.0)

    # 计算短期均线相对于长期均线的偏离
    ma_deviation = safe_divide(short_ma - long_ma, long_std, 0.0)

    # 反转信号：偏离越大，反转信号越强
    price_reversal = -np.sign(price_deviation) * np.maximum(0, abs(price_deviation) - threshold)
    ma_reversal = -np.sign(ma_deviation) * np.maximum(0, abs(ma_deviation) - threshold)

    # 动量衰减检测
    price_momentum = close_prices.pct_change(short_period)
    momentum_ma = price_momentum.rolling(window=short_period).mean()
    momentum_decay = abs(momentum_ma) - abs(price_momentum)  # 动量衰减时为正

    # 综合反转因子
    reversal_factor = price_reversal * 0.5 + ma_reversal * 0.3 + momentum_decay * 0.2

    # 添加波动率状态
    current_vol = close_prices.pct_change().rolling(window=short_period).std()
    historical_vol = current_vol.rolling(window=long_period * 2).mean()
    vol_state = safe_divide(current_vol, historical_vol, 1.0)

    # 高波动时增强反转信号
    vol_multiplier = np.where(vol_state > 1.2, vol_state, 1.0)
    adjusted_factor = reversal_factor * vol_multiplier

    # 标准化处理
    standardized = rolling_zscore(adjusted_factor, standardize_window, long_period)

    return clip_outliers(standardized)


def price_drawdown(group: pd.DataFrame, period: int = 20):
    """
    价格回撤因子

    返回当前价格相对于N日内最高价的回撤幅度（负值）
    如 -0.10 表示从高点回撤了 10%

    用于出场过滤：
    condition: lambda x: x > -0.10  (回撤不超过10%)
    """
    close = group["close"]
    rolling_max = close.rolling(window=period, min_periods=1).max()
    drawdown = (close - rolling_max) / rolling_max
    return drawdown


# =============================================================================
# Volatility / Risk
# =============================================================================


def atr_stop(group: pd.DataFrame, period: int = 14, multiplier: float = 2.0):
    """
    ATR 止损因子

    返回当前价格相对于 ATR 止损线的距离：
    > 0: 价格在止损线上方（安全）
    < 0: 价格跌破止损线（应出场）

    止损线 = 最高价 - multiplier × ATR

    用于出场过滤：
    condition: lambda x: x > 0  (价格在止损线上方)
    """
    high = group["high"]
    low = group["low"]
    close = group["close"]

    # 计算 True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR
    atr = tr.rolling(window=period, min_periods=period).mean()

    # 止损线：近期高点 - multiplier × ATR
    rolling_high = high.rolling(window=period, min_periods=1).max()
    stop_line = rolling_high - multiplier * atr

    return close - stop_line


def volatility_regime(group: pd.DataFrame, short_period: int = 10, long_period: int = 60):
    """
    波动率状态因子

    返回短期波动率相对于长期波动率的比值：
    > 1.5: 高波动状态（风险高）
    < 0.8: 低波动状态（相对安全）

    用于出场过滤：
    condition: lambda x: x < 2.0  (波动率不超过历史2倍时持有)
    """
    close = group["close"]
    returns = close.pct_change()

    short_vol = returns.rolling(window=short_period, min_periods=short_period).std()
    long_vol = returns.rolling(window=long_period, min_periods=long_period).std()

    return short_vol / long_vol.replace(0, np.nan)


def volatility_inv(group: pd.DataFrame, period: int = 20):
    """
    波动率倒数因子

    来源: 策略 #26, #32

    低波动品种长期表现更好。用滚动波动率的倒数作为因子信号，
    波动率越低，因子值越大。
    """
    close = group["close"]
    returns = close.pct_change()
    vol = returns.rolling(window=period, min_periods=period).std()
    return 1.0 / vol.replace(0, np.nan)


def fund_premium_rate(
    group: pd.DataFrame,
    price_col: str = "close",
    nav_col: str = "unit_nv",
    nav_lag: int = 1,
):
    """
    场内基金折溢价率因子，计算公式为 `price / lagged_nav - 1`。

    来源: ETF 日频研究 notebook 的 `fund_nav` 合并口径。
    交易逻辑: 因子值越高表示基金价格相对已知净值溢价越高；因子值越低表示折价越深。
    计算步骤: 先读取 `nav_col` 指定的净值列；再按 `nav_lag` 将净值序列向后移动，确保只使用已知历史净值；最后计算 `price / lagged_nav - 1`。
    输入列: close, unit_nv
    前视偏差防护: 默认 `nav_lag=1`，使用前一交易日净值估计当日折溢价，避免把当日收盘后才完整可得的官方净值直接用于当日信号。
    """
    if price_col not in group.columns:
        raise ValueError(f"fund_premium_rate requires '{price_col}' column.")
    if nav_lag < 0:
        raise ValueError("fund_premium_rate requires nav_lag >= 0")
    if nav_col not in group.columns:
        raise ValueError(f"fund_premium_rate requires '{nav_col}' column.")

    price = group[price_col].astype(float)
    nav = group[nav_col].astype(float).shift(nav_lag)
    return safe_divide(price, nav, np.nan) - 1.0


def discover_indicators() -> dict[str, Callable]:
    """Auto-discover all public indicator functions defined in this module.

    Uses `inspect` rather than a manual registry so new indicators show up
    automatically and deletions never leave stale entries.
    """
    module = _inspect.getmodule(discover_indicators)
    return {
        name: func
        for name, func in _inspect.getmembers(module, _inspect.isfunction)
        if not name.startswith("_")
        and func.__module__ == module.__name__
        and name != "discover_indicators"
    }
