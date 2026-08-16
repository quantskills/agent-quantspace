"""trend_momentum_generator 角色产出的 NEW 因子候选 (trend/momentum 族)."""

from __future__ import annotations

import numpy as np
import pandas as pd

# =============================================================================
# 因子函数
# =============================================================================


def tm_multi_window_momentum_fusion(
    group: pd.DataFrame,
    short: int = 10,
    mid: int = 21,
    long: int = 63,
) -> pd.Series:
    """多窗口动量加权融合因子。

    经济假设：趋势的持续性可由多周期动量的「一致性」刻画。当短/中/长
    三个回看窗口的动量方向一致且幅度接近时，趋势更可靠；方向分歧则预
    示趋势衰竭。用三窗口动量的符号乘积作为一致性门控，再乘以三窗口动
    量的均值，得到同时反映方向一致性与幅度的新因子。
    """
    close = group["close"].astype(float)

    mom_short = close / close.shift(short) - 1.0
    mom_mid = close / close.shift(mid) - 1.0
    mom_long = close / close.shift(long) - 1.0

    # 方向一致性：三者同号为 ±1，分歧为 0（非线性门控）
    sign_product = np.sign(mom_short) * np.sign(mom_mid) * np.sign(mom_long)

    # 幅度项：三窗口动量均值
    avg_mom = (mom_short + mom_mid + mom_long) / 3.0

    result = sign_product * avg_mom
    return result.astype("float64")


def tm_momentum_jerk(
    group: pd.DataFrame,
    period: int = 10,
) -> pd.Series:
    """动量急动度因子（动量的三阶差分）。

    经济假设：进一步取动量的「急动度」（jerk，三阶导数近似），刻画趋势
    力量的二阶变化率。当 jerk 由负转正时，说明趋势力量正在从减速转入
    加速初期，具有领先意义。对连续三阶 diff 做 tanh 压缩以控制尾部。
    """
    close = group["close"].astype(float)
    momentum = close.pct_change(periods=period)
    # 三阶差分 ≈ momentum 的 jerk
    jerk = momentum.diff().diff().diff()
    # tanh 压缩尾部，避免极端值
    result = np.tanh(jerk)
    return result.astype("float64")


def tm_trend_persistence_weighted(
    group: pd.DataFrame,
    period: int = 20,
    lookback: int = 60,
) -> pd.Series:
    """趋势持续期加权动量因子。

    经济假设：趋势维持越久（连续同向收盘日占比越高），后续延续概率越
    大。计算滚动窗口内日收益为正的天数占比作为「持续度」，再与同期累计
    收益相乘，使方向一致且持续度高的趋势得到放大。
    """
    close = group["close"].astype(float)
    ret = close.pct_change()

    # 滚动窗口内正收益天数占比
    up_ratio = ret.rolling(window=period, min_periods=period).apply(
        lambda w: np.mean(w > 0.0), raw=True
    )

    # 同窗口累计收益
    cum_ret = close / close.shift(period) - 1.0

    # 持续度门控：up_ratio 偏离 0.5 越多，方向越一致
    persistence = (up_ratio - 0.5) * 2.0  # 映射到 [-1, 1]

    raw = persistence * cum_ret

    # 用 lookback 窗口做 z-score 标准化并裁剪极值
    mean = raw.rolling(window=lookback, min_periods=period).mean()
    std = raw.rolling(window=lookback, min_periods=period).std()
    std = std.where(std > 1e-8, np.nan)
    z = (raw - mean) / std
    z = z.clip(-3.0, 3.0)
    return z.astype("float64")


def tm_log_return_skew_momentum(
    group: pd.DataFrame,
    period: int = 20,
) -> pd.Series:
    """对数收益偏度动量因子。

    经济假设：在有效趋势中，收益分布应呈现正偏（上行日幅度大于下行日），
    而反转/震荡行情偏度趋于零或负偏。滚动窗口内对数收益的偏度与平均收
    益的乘积可同时捕捉「方向」与「分布形态」，正偏 + 正均值为强趋势上
    行信号。偏度用标准化三阶矩计算。
    """
    close = group["close"].astype(float)
    log_ret = np.log(close / close.shift(1))

    rolling_mean = log_ret.rolling(window=period, min_periods=period).mean()
    rolling_std = log_ret.rolling(window=period, min_periods=period).std()
    rolling_std = rolling_std.where(rolling_std > 1e-10, np.nan)

    # 标准化三阶矩 = E[((x-mean)/std)^3]
    def _skew(w: np.ndarray) -> float:
        if np.isnan(w).any():
            return np.nan
        m = w.mean()
        s = w.std()
        if s <= 1e-10:
            return 0.0
        return float(np.mean(((w - m) / s) ** 3))

    skew = log_ret.rolling(window=period, min_periods=period).apply(_skew, raw=True)

    # 偏度 × 均值收益：方向 + 形态
    result = skew * rolling_mean
    return result.astype("float64")


def tm_path_curvature_momentum(
    group: pd.DataFrame,
    period: int = 20,
) -> pd.Series:
    """价格路径曲率动量因子。

    经济假设：价格路径的「曲率」反映趋势的平滑程度。曲率低（路径近似
    直线）意味着趋势干净有力；曲率高意味着路径迂回、趋势不稳。用滚动
    窗口内对数价格的二阶差分方差（即路径弯曲程度）取负，再乘以窗口斜
    率方向，得到「低曲率 + 有方向」的趋势强度信号。
    """
    close = group["close"].astype(float)
    log_close = np.log(close.where(close > 0.0))

    # 二阶差分方差 = 路径弯曲程度
    second_diff = log_close.diff().diff()
    curvature = second_diff.rolling(window=period, min_periods=period).var()

    # 一阶斜率方向（窗口首末对数价差符号）
    slope_sign = np.sign(log_close - log_close.shift(period))

    # 曲率倒数（低曲率=高分），用 tanh 压缩
    # curvature >= 0，取负后 tanh 映射到 [-1, 0]
    curvature_signal = np.tanh(-curvature)

    result = curvature_signal * slope_sign
    return result.astype("float64")


def tm_up_down_volume_asymmetry_momentum(
    group: pd.DataFrame,
    period: int = 20,
) -> pd.Series:
    """上行成交额占比动量因子。

    经济假设：趋势的可持续性不仅体现在价格方向，也体现在资金流的不对
    称性。上行日的成交额占比越高，说明买方力量主导，趋势更可能延续。
    用滚动窗口内「上行日成交额 / 总成交额」偏离 0.5 的程度，乘以同期
    价格动量，融合量价信息。
    """
    close = group["close"].astype(float)
    volume = group["volume"].astype(float)

    ret = close.pct_change()
    up_volume = volume.where(ret > 0.0, 0.0)
    total_volume = volume.where(ret.notna(), 0.0)

    up_sum = up_volume.rolling(window=period, min_periods=period).sum()
    total_sum = total_volume.rolling(window=period, min_periods=period).sum()
    total_sum = total_sum.where(total_sum > 0.0, np.nan)

    up_ratio = up_sum / total_sum  # [0, 1]
    asymmetry = (up_ratio - 0.5) * 2.0  # 映射到 [-1, 1]

    price_mom = close / close.shift(period) - 1.0

    result = asymmetry * price_mom
    return result.astype("float64")


def tm_momentum_dispersion_reversal(
    group: pd.DataFrame,
    period: int = 20,
    lookback: int = 60,
) -> pd.Series:
    """动量离散度反转因子。

    经济假设：当价格动量在近期窗口内离散度极高（每日收益方差大）时，
    即便方向一致也意味着多空分歧严重，趋势延续概率下降；离散度低则趋
    势干净。用滚动收益方差的倒数作为「干净度」权重，乘以平均收益，得
    到低噪声趋势动量。再用 lookback 窗口标准化。
    """
    close = group["close"].astype(float)
    ret = np.log(close / close.shift(1))

    rolling_mean = ret.rolling(window=period, min_periods=period).mean()
    rolling_var = ret.rolling(window=period, min_periods=period).var()
    rolling_var = rolling_var.where(rolling_var > 1e-12, np.nan)

    # 干净度 = 1 / sqrt(var)，用 tanh 压缩
    cleanliness = np.tanh(1.0 / np.sqrt(rolling_var))

    raw = cleanliness * rolling_mean

    # z-score 标准化
    mean = raw.rolling(window=lookback, min_periods=period).mean()
    std = raw.rolling(window=lookback, min_periods=period).std()
    std = std.where(std > 1e-8, np.nan)
    z = (raw - mean) / std
    z = z.clip(-3.0, 3.0)
    return z.astype("float64")


# =============================================================================
# 候选因子注册表
# =============================================================================

CANDIDATES = [
    {
        "factor_id": "tm_multi_window_momentum_fusion",
        "family": "trend_momentum",
        "hypothesis": "多周期动量方向一致性与幅度融合，一致性越高趋势越可靠",
        "direction": "positive",
        "func_name": "tm_multi_window_momentum_fusion",
        "params": {"short": 10, "mid": 21, "long": 63},
    },
    {
        "factor_id": "tm_momentum_jerk",
        "family": "trend_momentum",
        "hypothesis": "动量三阶差分（急动度）由负转正预示趋势力量从减速转加速的领先信号",
        "direction": "positive",
        "func_name": "tm_momentum_jerk",
        "params": {"period": 10},
    },
    {
        "factor_id": "tm_trend_persistence_weighted",
        "family": "trend_momentum",
        "hypothesis": "连续同向收盘日占比越高趋势延续概率越大，持续度门控放大累计收益",
        "direction": "positive",
        "func_name": "tm_trend_persistence_weighted",
        "params": {"period": 20, "lookback": 60},
    },
    {
        "factor_id": "tm_log_return_skew_momentum",
        "family": "trend_momentum",
        "hypothesis": "正偏收益分布 + 正均值收益 = 干净上行趋势，偏度乘均值捕捉方向与形态",
        "direction": "positive",
        "func_name": "tm_log_return_skew_momentum",
        "params": {"period": 20},
    },
    {
        "factor_id": "tm_path_curvature_momentum",
        "family": "trend_momentum",
        "hypothesis": "价格路径曲率低（近似直线）且方向明确时趋势最强，曲率倒数乘方向",
        "direction": "positive",
        "func_name": "tm_path_curvature_momentum",
        "params": {"period": 20},
    },
    {
        "factor_id": "tm_up_down_volume_asymmetry_momentum",
        "family": "trend_momentum",
        "hypothesis": "上行日成交额占比偏离0.5越多买方主导越强，量价不对称乘价格动量融合量价信息",
        "direction": "positive",
        "func_name": "tm_up_down_volume_asymmetry_momentum",
        "params": {"period": 20},
    },
    {
        "factor_id": "tm_momentum_dispersion_reversal",
        "family": "trend_momentum",
        "hypothesis": "收益方差低（噪声小）的动量更干净可靠，干净度权重乘均值收益并标准化",
        "direction": "positive",
        "func_name": "tm_momentum_dispersion_reversal",
        "params": {"period": 20, "lookback": 60},
    },
]
