"""volume_liquidity_generator 角色产出的 NEW 因子候选.

每个因子函数遵循 ``skills.compute.wrappers.Factor`` 契约：
单 symbol ``DataFrame``（DatetimeIndex 名为 ``eob``，含 ``open, high, low, close,
volume``）→ 与输入索引逐项相等且顺序一致的 float64 ``Series``，warm-up 用 NaN。

数据源 ``data/market/1d_adj`` 仅有 OHLCV，无 ``amount`` 列；需用成交额时以
``volume * close`` 近似（PandaData 日频复权口径）。

所有因子均为 volume/liquidity 族，不复用已有指标
（roc/ma/ma_vol/ma_vol_ratio/orb/orb_relvol/stand_orb_relvol/er*/trend_score*
等见 skills/compute/indicators.py 与 strategies/cross_sectional/factors.py）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# =============================================================================
# 1. 量价相关结构反转 (Volume-Price Correlation Reversal)
# =============================================================================


def vl_volume_price_corr_reversal(
    group: pd.DataFrame, period: int = 20
) -> pd.Series:
    """量价相关结构反转因子。

    经济假设：在窗口内计算日收益率与成交量变化的滚动 Pearson 相关。
    正常趋势行情中量价同向（正相关）；当正相关极端高（量价齐升/齐跌过度透支）
    后，短期均值回归使未来收益反向；当负相关极端（价涨量缩/价跌量缩背离）
    时同样预示动能衰竭。对滚动相关取负并做 tanh 饱和，使其对极端量价结构
    给出反向信号。
    """
    close = group["close"].astype(float)
    volume = group["volume"].astype(float)

    ret = close.pct_change()
    vol_chg = volume.pct_change()

    corr = ret.rolling(window=period, min_periods=period).corr(vol_chg)
    # 饱和后取负：正相关越强 → 反转信号越强（负值越大）
    saturated = np.tanh(corr)
    return (-saturated).astype("float64")


# =============================================================================
# 2. 成交量分位数动量 (Volume Quantile Momentum)
# =============================================================================


def vl_volume_quantile_momentum(
    group: pd.DataFrame, period: int = 60, short: int = 5
) -> pd.Series:
    """成交量分位数动量因子。

    经济假设：当前短期成交量在过去 ``period`` 日成交量分布中的分位数位置，
    反映短期资金关注度。高成交量分位数（放量）资产在流动性溢价下短期延续
    强势（资金涌入推升价格）；用滚动 percentile 避免被极端成交量尖峰主导。
    分位数 ∈ [0,1]，减 0.5 居中。
    """
    volume = group["volume"].astype(float)

    short_avg = volume.rolling(window=short, min_periods=short).mean()

    def _rolling_quantile_rank(window: np.ndarray) -> float:
        if len(window) == 0:
            return np.nan
        last = window[-1]
        if np.isnan(last):
            return np.nan
        valid = window[~np.isnan(window)]
        if len(valid) == 0:
            return np.nan
        # 分位数 rank（含自身）
        return float(np.sum(valid <= last) / len(valid))

    quantile_rank_short = short_avg.rolling(
        window=period, min_periods=period
    ).apply(_rolling_quantile_rank, raw=True)

    score = quantile_rank_short - 0.5
    return score.astype("float64")


# =============================================================================
# 3. 量能集中度 Herfindahl (Volume Concentration Herfindahl)
# =============================================================================


def vl_volume_concentration_herfindahl(
    group: pd.DataFrame, period: int = 20
) -> pd.Series:
    """量能集中度（Herfindahl 式）因子。

    经济假设：成交量在 ``period`` 日内的集中度反映资金进出节奏。
    Herfindahl 指数 H = Σ(volume_i / Σvolume)^2。H 越高表示成交量越集中于
    少数几日（脉冲式资金行为），这类资产后续往往动能衰竭（一次性资金推动
    难以持续）。取负方向：集中度高 → 因子值低 → 排序靠后（看空）。
    """
    volume = group["volume"].astype(float)

    def _herfindahl(window: np.ndarray) -> float:
        valid = window[~np.isnan(window)]
        if len(valid) == 0:
            return np.nan
        total = valid.sum()
        if total <= 0:
            return np.nan
        shares = valid / total
        return float(np.sum(shares**2))

    h_index = volume.rolling(window=period, min_periods=period).apply(
        _herfindahl, raw=True
    )
    # 取负：高集中度 → 低因子值（看空）
    return (-h_index).astype("float64")


# =============================================================================
# 4. 上涨日成交量占比 (Up-Day Volume Share)
# =============================================================================


def vl_up_day_volume_share(
    group: pd.DataFrame, period: int = 20
) -> pd.Series:
    """上涨日成交量占比因子。

    经济假设：在 ``period`` 日窗口内，上涨日的成交量占总成交量的比例。
    上涨日放量（占比高）表示买方主动承接、资金净流入，资产短期延续强势；
    下跌日放量（占比低）表示抛压主导，资产短期承压。占比 ∈ [0,1]，减 0.5
    居中后作为正向信号。
    """
    close = group["close"].astype(float)
    volume = group["volume"].astype(float)

    up = (close.diff() > 0).astype(float)
    up_volume = up * volume

    up_vol_sum = up_volume.rolling(window=period, min_periods=period).sum()
    total_vol_sum = volume.rolling(window=period, min_periods=period).sum()

    share = up_vol_sum / total_vol_sum.replace(0.0, np.nan)
    score = share - 0.5
    return score.astype("float64")


# =============================================================================
# 5. Amihud 非流动性倒数 (Amihud Illiquidity Inverse)
# =============================================================================


def vl_amihud_illiquidity_inverse(
    group: pd.DataFrame, period: int = 20
) -> pd.Series:
    """Amihud 非流动性倒数因子。

    经济假设：Amihud 非流动性 ILLIQ = mean(|ret| / 成交额)。ILLIQ 越高表示
    单位成交额引起的价格变动越大，即流动性越差。流动性好的资产（ILLIQ 低）
    享有流动性溢价反转（低流动性溢价在 ETF 跨资产上表现为流动性好的资产
    短期资金更愿意进驻，延续强势）。取 ILLIQ 的倒数作为正向因子，并对窗口
    内做平滑。成交额用 ``volume * close`` 近似（无 amount 列）。
    """
    close = group["close"].astype(float)
    volume = group["volume"].astype(float)

    ret = close.pct_change()
    turnover = (volume * close).replace(0.0, np.nan)
    abs_ret = ret.abs()

    daily_illiq = abs_ret / turnover
    # 窗口内平滑非流动性
    illiq_smooth = daily_illiq.rolling(window=period, min_periods=period).mean()
    # 取倒数并做对数变换：流动性好（ILLIQ 低）→ 因子值高（看多）。
    # log 变换避免量纲跨度过大，对 rank-based IC 无影响但数值更稳健。
    inverse = 1.0 / illiq_smooth.replace(0.0, np.nan)
    log_inverse = np.log(inverse.where(inverse > 0))
    return log_inverse.astype("float64")


# =============================================================================
# 6. 量能加速度 (Volume Acceleration)
# =============================================================================


def vl_volume_acceleration(
    group: pd.DataFrame, period: int = 10
) -> pd.Series:
    """量能加速度（量的一阶差分的动量）因子。

    经济假设：对成交量短期均线求一阶差分（量的"加速度"），衡量资金流入
    速度的变化。成交量加速度为正且上升（放量加速）表示资金涌入趋势加强，
    资产短期延续强势；加速度为负（缩量减速）表示资金退潮，资产承压。
    用对数成交量平滑后取二阶差分避免量纲问题。
    """
    volume = group["volume"].astype(float)
    log_vol = np.log(volume.where(volume > 0))

    ma_short = log_vol.rolling(window=period, min_periods=period).mean()
    # 一阶差分 = 速度
    velocity = ma_short.diff()
    # 二阶差分 = 加速度
    acceleration = velocity.diff()

    return acceleration.astype("float64")


# =============================================================================
# 7. 价量背离反转 (Price-Volume Divergence Reversal)
# =============================================================================


def vl_price_volume_divergence(
    group: pd.DataFrame, period: int = 20
) -> pd.Series:
    """价量背离反转因子。

    经济假设：价量背离（价涨量缩 或 价跌量缩）往往是趋势衰竭信号。
    用窗口内价格收益率斜率与成交量斜率的差衡量背离程度：
      divergence = price_slope - vol_slope（标准化后）
    价涨量缩 → price_slope > 0, vol_slope < 0 → divergence 大 → 看空反转；
    价跌量增 → price_slope < 0, vol_slope > 0 → divergence 小 → 看多反转。
    对两斜率分别 z-score 后求差并取负，使"价涨量缩"给出负信号。
    """
    close = group["close"].astype(float)
    volume = group["volume"].astype(float)

    log_close = np.log(close.where(close > 0))
    log_vol = np.log(volume.where(volume > 0))

    x = np.arange(period, dtype=float)
    x_mean = x.mean()
    x_centered = x - x_mean
    denom = float(np.dot(x_centered, x_centered))

    def _slope(window: np.ndarray) -> float:
        valid = ~np.isnan(window)
        if valid.sum() < period:
            return np.nan
        y = window
        y_mean = y.mean()
        y_centered = y - y_mean
        return float(np.dot(x_centered, y_centered) / denom)

    price_slope = log_close.rolling(window=period, min_periods=period).apply(
        _slope, raw=True
    )
    vol_slope = log_vol.rolling(window=period, min_periods=period).apply(
        _slope, raw=True
    )

    # 分别标准化（滚动）
    price_slope_mean = price_slope.rolling(window=period * 3, min_periods=period).mean()
    price_slope_std = price_slope.rolling(
        window=period * 3, min_periods=period
    ).std()
    price_slope_z = (price_slope - price_slope_mean) / price_slope_std.replace(
        0.0, np.nan
    )

    vol_slope_mean = vol_slope.rolling(window=period * 3, min_periods=period).mean()
    vol_slope_std = vol_slope.rolling(window=period * 3, min_periods=period).std()
    vol_slope_z = (vol_slope - vol_slope_mean) / vol_slope_std.replace(0.0, np.nan)

    divergence = price_slope_z - vol_slope_z
    # 取负：价涨量缩（divergence 大）→ 负信号（看空反转）
    return (-divergence).astype("float64")


# =============================================================================
# Candidate registry
# =============================================================================

CANDIDATES = [
    {
        "factor_id": "vl_vp_corr_reversal_20",
        "family": "volume_liquidity",
        "hypothesis": "量价滚动相关极端化后反转：量价同向过度透支预示短期均值回归",
        "direction": "negative",
        "func_name": "vl_volume_price_corr_reversal",
        "params": {"period": 20},
    },
    {
        "factor_id": "vl_vol_quantile_mom_60_5",
        "family": "volume_liquidity",
        "hypothesis": "短期成交量在长期分布中的分位数动量：高成交量分位数资产短期延续强势",
        "direction": "positive",
        "func_name": "vl_volume_quantile_momentum",
        "params": {"period": 60, "short": 5},
    },
    {
        "factor_id": "vol_concentration_herfindahl_20",
        "family": "volume_liquidity",
        "hypothesis": "成交量 Herfindahl 集中度：脉冲式放量集中度高预示动能衰竭（反向）",
        "direction": "negative",
        "func_name": "vl_volume_concentration_herfindahl",
        "params": {"period": 20},
    },
    {
        "factor_id": "vl_up_day_vol_share_20",
        "family": "volume_liquidity",
        "hypothesis": "上涨日成交量占比：买方主动承接（上涨日放量）资产短期延续强势",
        "direction": "positive",
        "func_name": "vl_up_day_volume_share",
        "params": {"period": 20},
    },
    {
        "factor_id": "vl_amihud_illiq_inv_20",
        "family": "volume_liquidity",
        "hypothesis": "Amihud 非流动性倒数：流动性好的资产吸引资金进驻，短期延续强势",
        "direction": "positive",
        "func_name": "vl_amihud_illiquidity_inverse",
        "params": {"period": 20},
    },
    {
        "factor_id": "vl_volume_acceleration_10",
        "family": "volume_liquidity",
        "hypothesis": "量能加速度（对数成交量均线二阶差分）：放量加速预示资金涌入趋势加强",
        "direction": "positive",
        "func_name": "vl_volume_acceleration",
        "params": {"period": 10},
    },
    {
        "factor_id": "vl_price_volume_divergence_20",
        "family": "volume_liquidity",
        "hypothesis": "价量背离反转：价涨量缩（动能衰竭）看空，价跌量增看多",
        "direction": "negative",
        "func_name": "vl_price_volume_divergence",
        "params": {"period": 20},
    },
]
