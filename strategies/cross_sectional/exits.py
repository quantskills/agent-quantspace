"""
出场风控因子模块

包含尾部风险型的出场过滤指标，用于识别标的的风险状态：
1. drawdown_from_high_filter - 相对高点回撤过滤 (推荐)
2. gap_down_filter - 跳空/大跌过滤
3. vol_spike_filter - 波动率突增过滤
4. consecutive_loss_filter - 连续下跌过滤
5. big_loss_filter - 单日大跌过滤
6. etf_premium_rate - ETF溢价率过滤（需要fund NAV数据）

软风控机制（非硬退出）：
6. soft_dd_scaledown - 触发时按比例减仓而非清零
7. soft_vol_hysteresis - 迟滞机制，触发和恢复使用不同阈值

所有因子返回风险信号值（越大=风险越高）。
exit_filters 中使用 condition=lambda x: x < threshold 过滤。
"""

import os
from functools import wraps

import pandas as pd


def multiindex_factor(func):
    """装饰器：确保因子函数接收和返回 MultiIndex Series"""

    @wraps(func)
    def wrapper(data, **kwargs):
        if not isinstance(data.index, pd.MultiIndex):
            raise ValueError(f"{func.__name__}: 需要 MultiIndex DataFrame (symbol, eob)")

        result_list = []
        for symbol, group_df in data.groupby(level="symbol"):
            series = func(group_df.droplevel("symbol"), **kwargs)
            series.index = pd.MultiIndex.from_product(
                [[symbol], series.index], names=["symbol", "eob"]
            )
            result_list.append(series)

        return pd.concat(result_list)

    return wrapper


# trailing_drawdown_stop 已合并到 drawdown_from_high_filter（功能一致）
trailing_drawdown_stop = None  # 向后兼容别名，在模块底部赋值


@multiindex_factor
def gap_down_filter(
    df: pd.DataFrame, gap_threshold: float = 0.02, drop_threshold: float = 0.03
) -> pd.Series:
    """
    跳空低开/单日大跌过滤器

    识别跳空低开或单日大跌的风险信号。

    Parameters
    ----------
    df : pd.DataFrame
        单标的数据，包含 open, close, high, low 列
    gap_threshold : float
        跳空阈值，默认 0.02 (2%)
    drop_threshold : float
        单日跌幅阈值，默认 0.03 (3%)

    Returns
    -------
    pd.Series
        风险信号值（0=无风险，1=有风险）

    Notes
    -----
    使用方式：
    exit_filters=[
        {'func': gap_down_filter, 'kwargs': {'gap_threshold': 0.02, 'drop_threshold': 0.03},
         'condition': lambda x: x < 0.5}  # 过滤有风险信号的
    ]
    """
    close = df["close"]
    open_price = df["open"]
    prev_close = close.shift(1)

    # 跳空低开幅度
    gap_down = (prev_close - open_price) / prev_close
    gap_signal = (gap_down > gap_threshold).astype(float)

    # 单日跌幅
    daily_drop = (prev_close - close) / prev_close
    drop_signal = (daily_drop > drop_threshold).astype(float)

    # 合并信号（有任一触发即为风险）
    risk_signal = ((gap_signal > 0) | (drop_signal > 0)).astype(float)

    return risk_signal


@multiindex_factor
def vol_spike_filter(
    df: pd.DataFrame, short_window: int = 10, long_window: int = 60, spike_ratio: float = 2.0
) -> pd.Series:
    """
    波动率突增过滤器

    识别短期波动率相对长期波动率突然上升的情况。

    Parameters
    ----------
    df : pd.DataFrame
        单标的数据，包含 close 列
    short_window : int
        短期波动率窗口，默认 10
    long_window : int
        长期波动率窗口，默认 60
    spike_ratio : float
        波动率突增倍数阈值，默认 2.0

    Returns
    -------
    pd.Series
        波动率比率（short_vol / long_vol），超过 spike_ratio 表示风险

    Notes
    -----
    使用方式：
    exit_filters=[
        {'func': vol_spike_filter, 'kwargs': {'spike_ratio': 2.0},
         'condition': lambda x: x < 2.0}  # 过滤波动率突增2倍以上的
    ]
    """
    close = df["close"]
    returns = close.pct_change()

    # 计算短期和长期波动率
    short_vol = returns.rolling(short_window, min_periods=max(1, short_window // 2)).std()
    long_vol = returns.rolling(long_window, min_periods=max(1, long_window // 2)).std()

    # 避免除零
    long_vol = long_vol.where(long_vol > 1e-6, 1e-6)

    # 波动率比率
    vol_ratio = short_vol / long_vol
    vol_ratio = vol_ratio.fillna(1.0)

    return vol_ratio


@multiindex_factor
def consecutive_loss_filter(
    df: pd.DataFrame, n_days: int = 3, loss_threshold: float = 0.0
) -> pd.Series:
    """
    连续下跌天数过滤器

    识别连续下跌的风险信号。

    Parameters
    ----------
    df : pd.DataFrame
        单标的数据，包含 close 列
    n_days : int
        连续下跌天数阈值，默认 3
    loss_threshold : float
        单日跌幅阈值（判定为"下跌"），默认 0.0（任何负收益）

    Returns
    -------
    pd.Series
        连续下跌天数，超过 n_days 表示风险

    Notes
    -----
    使用方式：
    exit_filters=[
        {'func': consecutive_loss_filter, 'kwargs': {'n_days': 3},
         'condition': lambda x: x < 3}  # 过滤连续下跌3天以上的
    ]
    """
    close = df["close"]
    returns = close.pct_change()

    # 向量化计算连续下跌天数：按非下跌日分组后 cumcount
    is_loss = returns < -loss_threshold
    # 每次非下跌日开始新分组
    groups = (~is_loss).cumsum()
    consecutive = is_loss.groupby(groups).cumsum().astype(int)

    return consecutive


@multiindex_factor
def drawdown_from_high_filter(
    df: pd.DataFrame, lookback: int = 20, threshold: float = 0.10
) -> pd.Series:
    """
    相对指定期间高点的回撤过滤器

    计算当前价格相对于过去 lookback 天内最高价的回撤。

    Parameters
    ----------
    df : pd.DataFrame
        单标的数据，包含 close 列
    lookback : int
        回看期间，默认 20 天
    threshold : float
        回撤阈值，默认 0.10 (10%)

    Returns
    -------
    pd.Series
        回撤值（正数），超过 threshold 表示风险

    Notes
    -----
    使用方式：
    exit_filters=[
        {'func': drawdown_from_high_filter, 'kwargs': {'lookback': 20, 'threshold': 0.10},
         'condition': lambda x: x < 0.10}  # 过滤回撤超过10%的
    ]
    """
    close = df["close"]

    # 计算滚动最高价
    rolling_high = close.rolling(lookback, min_periods=1).max()

    # 计算回撤
    drawdown = (rolling_high - close) / rolling_high
    drawdown = drawdown.fillna(0)

    return drawdown


@multiindex_factor
def big_loss_filter(df: pd.DataFrame, threshold: float = 0.03) -> pd.Series:
    """
    单日大跌过滤器（简化版）

    识别单日跌幅超过阈值的情况。

    Parameters
    ----------
    df : pd.DataFrame
        单标的数据，包含 close 列
    threshold : float
        单日跌幅阈值，默认 0.03 (3%)

    Returns
    -------
    pd.Series
        单日跌幅（正数），超过 threshold 表示风险

    Notes
    -----
    使用方式：
    exit_filters=[
        {'func': big_loss_filter, 'kwargs': {'threshold': 0.03},
         'condition': lambda x: x < 0.03}  # 过滤单日跌幅超过3%的
    ]
    """
    close = df["close"]
    returns = close.pct_change()

    # 将负收益转为正数的跌幅
    loss = -returns.clip(upper=0)

    return loss


__all__ = [
    "drawdown_from_high_filter",
    "trailing_drawdown_stop",  # 别名 → drawdown_from_high_filter
    "gap_down_filter",
    "vol_spike_filter",
    "consecutive_loss_filter",
    "big_loss_filter",
    "soft_dd_scaledown",
    "soft_vol_hysteresis",
]


# =============================================================================
# 软风控因子 - 减仓而非清仓
# =============================================================================


@multiindex_factor
def soft_dd_scaledown(
    df: pd.DataFrame, dd_threshold: float = 0.08, scale_factor: float = 0.5, lookback: int = 20
) -> pd.Series:
    """
    软风控：回撤触发时减仓而非清仓

    Parameters
    ----------
    df : pd.DataFrame
        单标的数据，包含 close 列
    dd_threshold : float
        回撤触发阈值，默认 0.08 (8%)
    scale_factor : float
        触发后保留的权重比例，默认 0.5 (减半)
    lookback : int
        回看期间，默认 20 天

    Returns
    -------
    pd.Series
        缩放因子（1=保持不变，0.5=减半，0=清仓）

    Notes
    -----
    这个因子不是用于 condition 过滤，而是需要特殊处理：
    在回测引擎中，不是简单的 keep/kill，而是乘以缩放因子。

    当前实现：返回应该保留的权重比例
    - 回撤 < 阈值: 返回 1.0 (保持不变)
    - 回撤 >= 阈值: 返回 scale_factor (减仓)

    使用方式 (需要特殊处理逻辑):
    weights = weights * soft_dd_scaledown_values
    """
    close = df["close"]
    rolling_high = close.rolling(lookback, min_periods=1).max()
    drawdown = (rolling_high - close) / rolling_high
    drawdown = drawdown.fillna(0)

    # 返回权重缩放因子
    scale = pd.Series(1.0, index=drawdown.index)
    scale[drawdown >= dd_threshold] = scale_factor

    return scale


@multiindex_factor
def soft_vol_hysteresis(
    df: pd.DataFrame,
    trigger_ratio: float = 2.0,
    recover_ratio: float = 1.5,
    short_window: int = 10,
    long_window: int = 60,
) -> pd.Series:
    """
    软风控：波动率迟滞机制（触发和恢复使用不同阈值）

    Parameters
    ----------
    df : pd.DataFrame
        单标的数据，包含 close 列
    trigger_ratio : float
        触发阈值（短期波动率/长期波动率），默认 2.0
    recover_ratio : float
        恢复阈值（必须 < trigger_ratio），默认 1.5
    short_window : int
        短期波动率窗口，默认 10
    long_window : int
        长期波动率窗口，默认 60

    Returns
    -------
    pd.Series
        状态值（0=正常，1=风险状态）

    Notes
    -----
    迟滞逻辑：
    - 当 vol_ratio >= trigger_ratio 时，进入风险状态
    - 进入风险状态后，只有 vol_ratio <= recover_ratio 时才恢复正常
    - 避免在临界值附近频繁切换

    使用方式：
    exit_filters=[
        {'func': soft_vol_hysteresis, 'kwargs': {'trigger_ratio': 2.0, 'recover_ratio': 1.5},
         'condition': lambda x: x < 0.5}  # 过滤处于风险状态的
    ]
    """
    close = df["close"]
    returns = close.pct_change()

    # 计算波动率比率
    short_vol = returns.rolling(short_window, min_periods=max(1, short_window // 2)).std()
    long_vol = returns.rolling(long_window, min_periods=max(1, long_window // 2)).std()
    long_vol = long_vol.where(long_vol > 1e-6, 1e-6)
    vol_ratio = short_vol / long_vol
    vol_ratio = vol_ratio.fillna(1.0)

    # 迟滞状态机
    state = pd.Series(0.0, index=vol_ratio.index)
    current_state = 0  # 0=正常，1=风险

    for i in range(len(vol_ratio)):
        ratio = vol_ratio.iloc[i]

        if current_state == 0:  # 当前正常
            if ratio >= trigger_ratio:
                current_state = 1
        else:  # 当前风险
            if ratio <= recover_ratio:
                current_state = 0

        state.iloc[i] = current_state

    return state


def etf_premium_rate(df, nav_dir=None):
    """
    ETF premium rate = (market_price - NAV) / NAV.

    Loads fund NAV from parquet files and computes premium rate for each date.
    Positive value = overpriced, negative = discounted.

    Parameters
    ----------
    df : pd.DataFrame
        MultiIndex (symbol, eob) DataFrame with 'close' column.
    nav_dir : str, optional
        Directory containing {symbol}.parquet NAV files.
        Defaults to datasets/market/fund_nav/ relative to this module.

    Returns
    -------
    pd.Series
        Premium rate with MultiIndex (symbol, eob).
        Returns 0.0 for symbols without NAV data (passes through filter).

    Notes
    -----
    Usage as exit filter (exit when premium >= 20%):
        exit_filters=[{
            'func': EF.etf_premium_rate,
            'kwargs': {},
            'name': 'premium_20%',
            'condition': lambda x: x < 0.20
        }]
    """
    if nav_dir is None:
        nav_dir = os.path.join(os.path.dirname(__file__), "..", "data", "market", "fund_nav")

    if not isinstance(df.index, pd.MultiIndex):
        raise ValueError("etf_premium_rate: needs MultiIndex (symbol, eob)")

    result_list = []
    for symbol, group_df in df.groupby(level="symbol"):
        close = group_df["close"].droplevel("symbol")

        nav_path = os.path.join(nav_dir, f"{symbol}.parquet")
        if not os.path.exists(nav_path):
            premium = pd.Series(0.0, index=close.index)
        else:
            nav_df = pd.read_parquet(nav_path)
            unit_nv = nav_df["unit_nv"]

            # Align by date, forward-fill NAV for any missing trading dates
            aligned = close.to_frame("close").join(unit_nv, how="left")
            aligned["unit_nv"] = aligned["unit_nv"].ffill()

            # Auto-correct scale mismatch between adjusted close and raw NAV.
            # Market data may be split-adjusted while NAV is raw, causing
            # close/NAV ratio to shift at split events. Using a rolling median
            # baseline adapts to any split at any point in history.
            ratio = aligned["close"] / aligned["unit_nv"]
            baseline = ratio.rolling(60, min_periods=10).median()
            baseline = baseline.clip(lower=1e-6)

            premium = (ratio / baseline) - 1.0
            # Mask split-event artifacts: real ETF premium rarely exceeds 50%
            premium = premium.where(premium.abs() < 0.5, 0.0)
            premium = premium.fillna(0.0)

        premium.index = pd.MultiIndex.from_product(
            [[symbol], premium.index], names=["symbol", "eob"]
        )
        result_list.append(premium)

    return pd.concat(result_list)


# 向后兼容别名
trailing_drawdown_stop = drawdown_from_high_filter
