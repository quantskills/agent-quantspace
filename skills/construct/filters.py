"""
组合级风险开关模块

组合级（而非单标的级）的风险控制机制：
1. market_breadth_filter - 市场宽度过滤（池内趋势标的占比）
2. index_trend_filter - 基准指数趋势过滤
3. portfolio_vol_targeting - 组合波动率目标控制

这些机制在 sectional.py 的回测引擎层面实现，不是单标的因子。

Author: AI Assistant
Date: 2026-02-06
"""

import numpy as np
import pandas as pd


def calculate_market_breadth(close_pivot: pd.DataFrame, ma_period: int = 20) -> pd.Series:
    """
    计算市场宽度：池内收盘价高于MA的标的占比

    Parameters
    ----------
    close_pivot : pd.DataFrame
        收盘价 pivot 矩阵 (date × symbol)
    ma_period : int
        均线周期，默认 20

    Returns
    -------
    pd.Series
        每日的市场宽度（0-1之间），索引为日期
    """
    ma = close_pivot.rolling(ma_period, min_periods=max(1, ma_period // 2)).mean()
    above_ma = (close_pivot > ma).sum(axis=1)
    total_symbols = close_pivot.notna().sum(axis=1)
    breadth = above_ma / total_symbols.replace(0, np.nan)
    return breadth.fillna(0.5)


def calculate_index_trend(index_close: pd.Series, ma_period: int = 120) -> pd.Series:
    """
    计算基准指数趋势信号

    Parameters
    ----------
    index_close : pd.Series
        基准指数收盘价序列
    ma_period : int
        均线周期，默认 120

    Returns
    -------
    pd.Series
        趋势信号（1=上涨趋势，0=下跌趋势）
    """
    ma = index_close.rolling(ma_period, min_periods=max(1, ma_period // 2)).mean()
    trend = (index_close > ma).astype(float)
    return trend


def apply_market_breadth_scale(
    weights_df: pd.DataFrame,
    close_pivot: pd.DataFrame,
    breadth_threshold: float = 0.3,
    scale_below: float = 0.5,
    ma_period: int = 20,
) -> pd.DataFrame:
    """
    根据市场宽度对组合整体缩仓

    Parameters
    ----------
    weights_df : pd.DataFrame
        权重矩阵 (date × symbol)
    close_pivot : pd.DataFrame
        收盘价 pivot 矩阵 (date × symbol)
    breadth_threshold : float
        宽度阈值，默认 0.3 (30%)
    scale_below : float
        宽度低于阈值时的缩仓系数，默认 0.5 (减半)
    ma_period : int
        均线周期，默认 20

    Returns
    -------
    pd.DataFrame
        调整后的权重矩阵
    """
    breadth = calculate_market_breadth(close_pivot, ma_period)

    scale = pd.Series(1.0, index=breadth.index)
    scale[breadth < breadth_threshold] = scale_below

    # 向量化乘法（自动按索引对齐）
    result = weights_df.mul(scale.reindex(weights_df.index, fill_value=1.0), axis=0)

    low_breadth_days = (breadth < breadth_threshold).sum()
    print(
        f"   market_breadth: 阈值={breadth_threshold:.1%}, "
        f"缩仓系数={scale_below:.1f}, "
        f"触发天数={low_breadth_days} ({low_breadth_days / len(breadth):.1%})"
    )
    return result


def apply_index_trend_scale(
    weights_df: pd.DataFrame,
    index_close: pd.Series,
    scale_downtrend: float = 0.5,
    ma_period: int = 120,
) -> pd.DataFrame:
    """
    根据基准指数趋势对组合整体缩仓

    Parameters
    ----------
    weights_df : pd.DataFrame
        权重矩阵 (date × symbol)
    index_close : pd.Series
        基准指数收盘价序列
    scale_downtrend : float
        下跌趋势时的缩仓系数，默认 0.5 (减半)
    ma_period : int
        均线周期，默认 120

    Returns
    -------
    pd.DataFrame
        调整后的权重矩阵
    """
    trend = calculate_index_trend(index_close, ma_period)

    scale = trend.where(trend == 1, scale_downtrend)

    result = weights_df.mul(scale.reindex(weights_df.index, fill_value=1.0), axis=0)

    downtrend_days = (trend == 0).sum()
    print(
        f"   index_trend: MA={ma_period}, "
        f"缩仓系数={scale_downtrend:.1f}, "
        f"下跌天数={downtrend_days} ({downtrend_days / len(trend):.1%})"
    )
    return result


def apply_portfolio_vol_targeting(
    weights_df: pd.DataFrame, returns_df: pd.DataFrame, vol_target: float = 0.10, lookback: int = 60
) -> pd.DataFrame:
    """
    组合波动率目标控制（已在 sectional.py 中实现，这里提供独立版本）

    Parameters
    ----------
    weights_df : pd.DataFrame
        权重矩阵 (date × symbol)
    returns_df : pd.DataFrame
        收益率矩阵 (date × symbol)
    vol_target : float
        目标年化波动率，默认 0.10 (10%)
    lookback : int
        回看期间，默认 60 天

    Returns
    -------
    pd.DataFrame
        调整后的权重矩阵
    """
    common_cols = weights_df.columns.intersection(returns_df.columns)
    common_dates = weights_df.index.intersection(returns_df.index)
    w = weights_df.loc[common_dates, common_cols]
    r = returns_df.loc[common_dates, common_cols]

    port_ret = (w.shift(1) * r).sum(axis=1)
    realized_vol = port_ret.rolling(lookback, min_periods=20).std() * np.sqrt(252)

    scale = (vol_target / realized_vol.replace(0, np.nan)).clip(upper=1.0).fillna(1.0)
    result = weights_df.mul(scale.reindex(weights_df.index, fill_value=1.0), axis=0)

    avg_scale = scale.mean()
    below_target = (scale < 1.0).mean()
    print(
        f"   vol_targeting: 目标={vol_target:.1%}, "
        f"平均缩放={avg_scale:.2f}, "
        f"触发天数比例={below_target:.1%}"
    )
    return result


# 集成函数：在权重上依次应用多个组合级过滤器
def apply_portfolio_filters(
    weights_df: pd.DataFrame,
    close_pivot: pd.DataFrame,
    returns_df: pd.DataFrame,
    index_close: pd.Series | None = None,
    market_breadth_config: dict | None = None,
    index_trend_config: dict | None = None,
    vol_target_config: dict | None = None,
) -> pd.DataFrame:
    """
    依次应用多个组合级过滤器

    Parameters
    ----------
    weights_df : pd.DataFrame
        权重矩阵 (date × symbol)
    close_pivot : pd.DataFrame
        收盘价 pivot 矩阵 (date × symbol)
    returns_df : pd.DataFrame
        收益率矩阵 (date × symbol)
    index_close : pd.Series, optional
        基准指数收盘价序列（如果使用 index_trend_config）
    market_breadth_config : dict, optional
        市场宽度配置，例如 {'breadth_threshold': 0.3, 'scale_below': 0.5}
    index_trend_config : dict, optional
        指数趋势配置，例如 {'scale_downtrend': 0.5, 'ma_period': 120}
    vol_target_config : dict, optional
        波动率目标配置，例如 {'vol_target': 0.10, 'lookback': 60}

    Returns
    -------
    pd.DataFrame
        应用所有过滤器后的权重矩阵
    """
    result = weights_df.copy()

    print("\n[Portfolio-level Filters]")

    if market_breadth_config:
        result = apply_market_breadth_scale(result, close_pivot, **market_breadth_config)

    if index_trend_config:
        if index_close is None:
            print("   警告: 需要 index_close 才能应用 index_trend_filter")
        else:
            result = apply_index_trend_scale(result, index_close, **index_trend_config)

    if vol_target_config:
        result = apply_portfolio_vol_targeting(result, returns_df, **vol_target_config)

    return result


__all__ = [
    "calculate_market_breadth",
    "calculate_index_trend",
    "apply_market_breadth_scale",
    "apply_index_trend_scale",
    "apply_portfolio_vol_targeting",
    "apply_portfolio_filters",
]
