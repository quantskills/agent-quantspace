"""Math utility functions shared by indicators and factor expressions."""

import numpy as np
import pandas as pd

# =============================================================================
# 通用辅助函数
# =============================================================================


def safe_divide(numerator: pd.Series, denominator: pd.Series, fill_value: float = 0.0) -> pd.Series:
    """安全除法操作，避免除零错误"""
    result = numerator / denominator
    result = result.replace([np.inf, -np.inf], np.nan)
    return result.fillna(fill_value)


def rolling_zscore(series: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    """计算滚动Z-score标准化"""
    if min_periods is None:
        min_periods = max(1, window // 2)

    rolling_mean = series.rolling(window=window, min_periods=min_periods).mean()
    rolling_std = series.rolling(window=window, min_periods=min_periods).std()

    # 避免除零错误
    rolling_std = rolling_std.where(rolling_std > 1e-6, 1e-6)

    return (series - rolling_mean) / rolling_std


def rolling_regression_vectorized(
    y: pd.Series, x: pd.Series, window: int
) -> tuple[pd.Series, pd.Series]:
    """
    向量化的滚动线性回归计算

    Returns:
        tuple: (slopes, r_squared_values)
    """
    # 使用pandas内置的滚动函数进行向量化计算
    rolling_corr = x.rolling(window=window).corr(y)
    rolling_std_y = y.rolling(window=window).std()
    rolling_std_x = x.rolling(window=window).std()

    # 避免除零错误
    rolling_std_x = rolling_std_x.where(rolling_std_x > 1e-8, np.nan)

    slopes = rolling_corr * (rolling_std_y / rolling_std_x)
    r_squareds = rolling_corr.pow(2)

    return slopes, r_squareds


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """计算真实波幅ATR"""
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def clip_outliers(series: pd.Series, lower: float = -3, upper: float = 3) -> pd.Series:
    """限制极值在合理范围内"""
    return series.clip(lower, upper)


def round_away_from_zero(values: pd.Series | np.ndarray | float, decimals: int = 3):
    """Round values away from zero with a fixed decimal precision."""
    scale = 10**decimals
    array = np.asarray(values, dtype=float)
    rounded = np.where(
        array > 0,
        np.ceil(array * scale) / scale,
        np.where(array < 0, np.floor(array * scale) / scale, 0.0),
    )
    if np.isscalar(values):
        return float(rounded)
    if isinstance(values, pd.Series):
        return pd.Series(rounded, index=values.index, dtype=float)
    return rounded


_WPETF_RSI_ADJUSTMENT = np.polyfit(
    np.array([1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 99], dtype=float),
    np.array([50, 2, 0.1, 0, 0, 0, 0, 0, -0.1, -2, -50], dtype=float),
    deg=5,
)


def _weighted_polyfit_coefficients(
    windows: np.ndarray,
    x: np.ndarray,
    weights: np.ndarray,
    degree: int,
) -> np.ndarray:
    """Solve repeated weighted polyfit problems with fixed x/weights."""
    design = np.vander(x, N=degree + 1, increasing=False)
    weighted_design = design * weights[:, None]
    solver = np.linalg.pinv(design.T @ weighted_design) @ weighted_design.T
    return windows @ solver.T


def _rolling_linear_regression(
    windows: np.ndarray, x: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return slope, intercept, and R-squared for fixed-x rolling windows."""
    n = windows.shape[1]
    sum_x = float(x.sum())
    sum_x2 = float((x**2).sum())
    denominator = n * sum_x2 - sum_x**2

    sum_y = windows.sum(axis=1)
    sum_xy = windows @ x

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n

    fitted = slope[:, None] * x[None, :] + intercept[:, None]
    ss_res = ((windows - fitted) ** 2).sum(axis=1)
    ss_tot = ((windows - (sum_y / n)[:, None]) ** 2).sum(axis=1)
    r_squared = np.where(ss_tot > 0.0, 1.0 - (ss_res / ss_tot), 0.0)
    return slope, intercept, r_squared


def _scalar_kalman_smoother(observations: np.ndarray, observation_covariance: float) -> np.ndarray:
    """Smooth a 1D path with a compact scalar Kalman configuration."""
    observations = np.asarray(observations, dtype=float)
    if observations.ndim != 1:
        raise ValueError("_scalar_kalman_smoother requires 1D observations")
    if len(observations) == 0:
        return observations.copy()

    transition_covariance = 0.1
    filtered_state_means = np.empty(len(observations), dtype=float)
    filtered_state_covariances = np.empty(len(observations), dtype=float)
    predicted_state_means = np.empty(len(observations), dtype=float)
    predicted_state_covariances = np.empty(len(observations), dtype=float)

    filtered_state_means[0] = observations[0]
    filtered_state_covariances[0] = observation_covariance
    predicted_state_means[0] = observations[0]
    predicted_state_covariances[0] = observation_covariance

    for idx in range(1, len(observations)):
        predicted_state_means[idx] = filtered_state_means[idx - 1]
        predicted_state_covariances[idx] = (
            filtered_state_covariances[idx - 1] + transition_covariance
        )
        innovation = observations[idx] - predicted_state_means[idx]
        innovation_covariance = predicted_state_covariances[idx] + observation_covariance
        kalman_gain = predicted_state_covariances[idx] / innovation_covariance
        filtered_state_means[idx] = predicted_state_means[idx] + kalman_gain * innovation
        filtered_state_covariances[idx] = (1.0 - kalman_gain) * predicted_state_covariances[idx]

    smoothed_state_means = filtered_state_means.copy()
    for idx in range(len(observations) - 2, -1, -1):
        smoothing_gain = filtered_state_covariances[idx] / predicted_state_covariances[idx + 1]
        smoothed_state_means[idx] = filtered_state_means[idx] + smoothing_gain * (
            smoothed_state_means[idx + 1] - predicted_state_means[idx + 1]
        )

    return smoothed_state_means
