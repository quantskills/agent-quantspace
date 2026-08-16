"""Universal OHLCV technical indicators.

These functions operate on single-symbol DataFrames and are strategy-agnostic.
Cross-sectional alpha expressions live in strategies/cross_sectional/factors.py.
"""

import inspect as _inspect
from collections.abc import Callable

import numpy as np
import pandas as pd

from .utils import (
    calculate_atr,
    clip_outliers,
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


# =============================================================================
# Trend
# =============================================================================


def trend_score(group: pd.DataFrame, period: int = 25):
    """
    计算无量纲 trend_score 趋势评分因子。

    在滚动窗口内对对数收盘价做线性回归，将年化对数价格斜率与
    回归 R 平方相乘：

        trend_score = 252 * slope(log(close)) * R^2

    Parameters
    ----------
    group : pd.DataFrame
        单个symbol的数据，包含 'close' 列
    period : int, optional
        回归窗口期, 默认为25天

    Returns
    -------
    pd.Series
        trend_score 因子序列，前 period - 1 位为 NaN
    """
    if period <= 1:
        raise ValueError("period must be greater than 1")

    close = group["close"].astype(float)
    log_close = np.log(close.where(close > 0.0))
    x = np.arange(period, dtype=float)
    x -= x.mean()
    denominator = float(np.dot(x, x))

    def rolling_trend(y: np.ndarray) -> float:
        if np.isnan(y).any():
            return np.nan

        centered_y = y - y.mean()
        total_variation = float(np.dot(centered_y, centered_y))
        if total_variation <= 0.0:
            return np.nan

        slope = float(np.dot(x, centered_y) / denominator)
        fitted = slope * x
        r_squared = float(np.dot(fitted, fitted) / total_variation)
        r_squared = min(max(r_squared, 0.0), 1.0)
        return slope * 252.0 * r_squared

    return log_close.rolling(window=period, min_periods=period).apply(
        rolling_trend,
        raw=True,
    )


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
