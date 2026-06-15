"""Sparse LASSO index-tracking weight generation."""

import numpy as np
import pandas as pd
from sklearn.linear_model import Lasso


def lasso_track(
    etf_returns: pd.DataFrame,
    index_returns: pd.Series,
    lookback: int = 120,
    alpha: float = 1e-6,
    min_periods: int = 60,
    rebalance_freq: str = "M",
    max_weight: float = 0.3,
) -> pd.DataFrame:
    """
    Rolling LASSO index tracking.

    Parameters
    ----------
    etf_returns : pd.DataFrame
        Daily returns of ETF candidates (date x symbol)
    index_returns : pd.Series
        Daily returns of the target index
    lookback : int
        Training window (trading days)
    alpha : float
        LASSO regularization strength (higher = sparser)
    min_periods : int
        Minimum training samples before producing weights
    rebalance_freq : str
        How often to refit: 'D' daily, 'W' weekly, 'M' monthly
    max_weight : float
        Maximum weight per ETF (cap for diversification)

    Returns
    -------
    pd.DataFrame
        Weight matrix (date x symbol), rows sum to ~1
    """
    # Align dates
    common_idx = etf_returns.index.intersection(index_returns.index)
    etf_ret = etf_returns.loc[common_idx]
    idx_ret = index_returns.loc[common_idx]

    # Determine rebalance dates
    if rebalance_freq == "D":
        rebal_dates = common_idx[min_periods:]
    else:
        groups = pd.Series(range(len(common_idx)), index=common_idx)
        freq_map = {"W": "W", "M": "M"}
        period_groups = groups.groupby(pd.Grouper(freq=freq_map[rebalance_freq]))
        rebal_dates = pd.DatetimeIndex(
            [
                g.index[-1]
                for _, g in period_groups
                if len(g) > 0 and g.index[-1] >= common_idx[min_periods]
            ]
        )

    print(f"LASSO tracker: {len(rebal_dates)} rebalance points, lookback={lookback}, alpha={alpha}")

    # Fit LASSO at each rebalance date
    weights_dict = {}
    model = Lasso(alpha=alpha, positive=True, fit_intercept=False, max_iter=5000)

    for date in rebal_dates:
        loc = common_idx.get_loc(date)
        start = max(0, loc - lookback)

        X = etf_ret.iloc[start : loc + 1].values
        y = idx_ret.iloc[start : loc + 1].values

        # Skip if insufficient data or all NaN
        valid_mask = ~(np.isnan(X).any(axis=0))
        if valid_mask.sum() < 2 or len(y) < min_periods:
            continue

        X_clean = X[:, valid_mask]
        valid_cols = etf_ret.columns[valid_mask]

        try:
            model.fit(X_clean, y)
            coefs = model.coef_

            # Apply cap
            coefs = np.minimum(coefs, max_weight)

            # Normalize to sum=1
            total = coefs.sum()
            if total > 0:
                coefs = coefs / total

            w = pd.Series(0.0, index=etf_ret.columns)
            w[valid_cols] = coefs
            weights_dict[date] = w
        except Exception:
            continue

    if not weights_dict:
        return pd.DataFrame(0.0, index=common_idx, columns=etf_ret.columns)

    # Build weight DataFrame
    weights_sparse = pd.DataFrame(weights_dict).T
    weights_full = weights_sparse.reindex(common_idx).ffill().fillna(0)

    # Stats
    n_nonzero = (weights_full > 0.001).sum(axis=1).mean()
    print(f"  Avg non-zero ETFs: {n_nonzero:.1f} / {len(etf_ret.columns)}")

    return weights_full

__all__ = ["lasso_track"]
