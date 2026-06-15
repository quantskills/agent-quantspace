"""
Alternative weighting methods for portfolio construction.

Methods:
- equal_weight: 1/N weights (default)
- risk_parity: inverse-variance (simplified risk parity)
- inverse_variance: w_i = 1/var_i, normalized
- epo: Enhanced Portfolio Optimization with shrunk covariance
"""

import numpy as np
import pandas as pd


def equal_weight(votes_df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    Equal-weight based on votes (default method).
    Weights proportional to vote counts.
    """
    row_sums = votes_df.sum(axis=1).replace(0, np.nan)
    return votes_df.div(row_sums, axis=0).fillna(0)


def risk_parity(
    votes_df: pd.DataFrame,
    returns_df: pd.DataFrame,
    lookback: int = 60,
    min_periods: int = 20,
    **kwargs,
) -> pd.DataFrame:
    """
    Risk Parity weighting: inverse-volatility, applied only to voted assets.

    For each date:
    1. Identify assets with votes > 0
    2. Calculate rolling volatility for each asset
    3. Weight = 1/vol, then normalize

    Parameters
    ----------
    votes_df : pd.DataFrame
        Vote matrix (date x symbol), non-zero = selected
    returns_df : pd.DataFrame
        Daily returns matrix (date x symbol)
    lookback : int
        Rolling window for volatility calculation
    min_periods : int
        Minimum periods for valid volatility
    """
    # Rolling volatility
    vol = returns_df.rolling(window=lookback, min_periods=min_periods).std()

    # Inverse vol, only for voted assets
    selected = (votes_df > 0).astype(float)
    inv_vol = (1.0 / vol.replace(0, np.nan)) * selected

    # Normalize per row
    row_sums = inv_vol.sum(axis=1).replace(0, np.nan)
    weights = inv_vol.div(row_sums, axis=0).fillna(0)

    return weights


def inverse_variance(
    votes_df: pd.DataFrame,
    returns_df: pd.DataFrame,
    lookback: int = 60,
    min_periods: int = 20,
    **kwargs,
) -> pd.DataFrame:
    """
    Inverse-variance weighting: w_i = 1/var_i, normalized.
    Same as risk_parity but uses variance instead of volatility.
    """
    var = returns_df.rolling(window=lookback, min_periods=min_periods).var()

    selected = (votes_df > 0).astype(float)
    inv_var = (1.0 / var.replace(0, np.nan)) * selected

    row_sums = inv_var.sum(axis=1).replace(0, np.nan)
    weights = inv_var.div(row_sums, axis=0).fillna(0)

    return weights


def _epo_single_date(ret_slice: pd.DataFrame, lambda_: float, shrink_w: float) -> np.ndarray:
    """
    Compute EPO (Enhanced Portfolio Optimization) weights for a single date.

    Uses anchored EPO method with shrunk correlation matrix.
    Reference: https://www.joinquant.com/post/47208

    Parameters
    ----------
    ret_slice : pd.DataFrame
        Historical returns for selected assets (dates x n_assets)
    lambda_ : float
        Risk aversion parameter
    shrink_w : float
        Shrinkage weight toward identity matrix [0, 1]

    Returns
    -------
    np.ndarray
        Normalized weight vector (length = n_assets), non-negative, sums to 1
    """
    from scipy.linalg import solve

    n = ret_slice.shape[1]
    if n == 0:
        return np.array([])
    if n == 1:
        return np.array([1.0])

    vcov = ret_slice.cov()
    corr = ret_slice.corr()
    eye_matrix = np.eye(n)

    # Diagonal variance matrix and std
    V = np.diag(vcov.values.diagonal())
    std = np.sqrt(V)

    # Shrink correlation toward identity (equation 7)
    shrunk_cor = (1 - shrink_w) * corr.values + shrink_w * eye_matrix
    # Shrunk covariance (topic 2.II: page 11)
    cov_tilde = std @ shrunk_cor @ std

    try:
        inv_shrunk_cov = solve(cov_tilde, eye_matrix, assume_a="pos")
    except np.linalg.LinAlgError:
        # Fallback: equal weight on singular matrix
        return np.ones(n) / n

    # Signal: mean returns
    signal = ret_slice.mean().values

    # Anchor: inverse-variance weights
    d = np.diag(vcov.values)
    d = np.where(d < 1e-12, 1e-12, d)  # avoid division by zero
    anchor = (1.0 / d) / (1.0 / d).sum()

    # Anchored EPO (endogenous gamma)
    s_inv_s = signal @ inv_shrunk_cov @ cov_tilde @ inv_shrunk_cov @ signal
    a_cov_a = anchor @ cov_tilde @ anchor

    if s_inv_s > 1e-12:
        gamma = np.sqrt(a_cov_a / s_inv_s)
    else:
        gamma = 1.0

    w = shrink_w
    epo_w = inv_shrunk_cov @ (((1 - w) * gamma * signal) + (w * V @ anchor))

    # Normalize: clamp negatives to 0, then normalize to sum=1
    epo_w = np.maximum(epo_w, 0.0)
    total = epo_w.sum()
    if total > 1e-12:
        epo_w = epo_w / total
    else:
        epo_w = np.ones(n) / n

    return epo_w


def epo(
    votes_df: pd.DataFrame,
    returns_df: pd.DataFrame,
    lookback: int = 1200,
    min_periods: int = 60,
    lambda_: float = 10.0,
    shrink_w: float = 0.2,
    **kwargs,
) -> pd.DataFrame:
    """
    Enhanced Portfolio Optimization (EPO) weighting.

    For each date, applies the anchored EPO method to selected assets:
    1. Compute shrunk covariance matrix (correlation shrunk toward identity)
    2. Use mean returns as signal, inverse-variance as anchor
    3. Solve for optimal weights with endogenous gamma
    4. Clamp negatives, normalize to sum=1

    Reference: https://www.joinquant.com/post/47208

    Parameters
    ----------
    votes_df : pd.DataFrame
        Vote matrix (date x symbol), non-zero = selected
    returns_df : pd.DataFrame
        Daily returns matrix (date x symbol)
    lookback : int
        Historical window for covariance estimation (default 1200 ~ 4.8 years)
    min_periods : int
        Minimum data points required (default 60)
    lambda_ : float
        Risk aversion parameter (default 10.0)
    shrink_w : float
        Correlation shrinkage weight toward identity [0, 1] (default 0.2)
    """
    selected = votes_df > 0
    dates = votes_df.index
    symbols = votes_df.columns
    weights = pd.DataFrame(0.0, index=dates, columns=symbols)

    # Pre-index returns for fast iloc
    ret_idx = returns_df.index

    # Track previous selection to skip unchanged days
    _prev_sel_key = None
    _prev_weights = None

    for date in dates:
        sel_mask = selected.loc[date]
        sel_symbols = sel_mask[sel_mask].index.tolist()

        if len(sel_symbols) == 0:
            continue
        if len(sel_symbols) == 1:
            weights.loc[date, sel_symbols[0]] = 1.0
            continue

        # Fast date lookup
        date_pos = ret_idx.searchsorted(date, side="right")
        start_pos = max(0, date_pos - lookback)
        ret_slice = returns_df.iloc[start_pos:date_pos][sel_symbols].dropna()

        if len(ret_slice) < min_periods:
            # Fallback: equal weight
            n = len(sel_symbols)
            for s in sel_symbols:
                weights.loc[date, s] = 1.0 / n
            continue

        epo_w = _epo_single_date(ret_slice, lambda_, shrink_w)

        for j, s in enumerate(sel_symbols):
            weights.loc[date, s] = epo_w[j]

    return weights


# Registry for easy lookup
WEIGHT_METHODS = {
    "equal": equal_weight,
    "risk_parity": risk_parity,
    "inverse_variance": inverse_variance,
    "epo": epo,
}
