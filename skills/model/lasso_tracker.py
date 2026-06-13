"""
LASSO Index Tracking Module

Replicates a target index using a sparse basket of ETFs.
Uses rolling-window LASSO regression to find optimal weights.

Reference: Huaxin Research Report - 885001 Core-Satellite Enhancement
"""

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


def backtest_lasso_tracker(
    etf_data: pd.DataFrame,
    index_data: pd.Series,
    lookback: int = 120,
    alpha: float = 1e-6,
    rebalance_freq: str = "M",
    commission: float = 0.0002,
    start_date: str = None,
) -> dict:
    """
    Full backtest for LASSO index tracking.

    Parameters
    ----------
    etf_data : pd.DataFrame
        MultiIndex (symbol, eob) OHLCV data for ETF candidates
    index_data : pd.Series
        Close prices of the target index, indexed by date
    lookback : int
        Training window
    alpha : float
        LASSO regularization
    rebalance_freq : str
        'D', 'W', or 'M'
    commission : float
        One-way commission rate
    start_date : str
        Backtest start date

    Returns
    -------
    dict with keys: result_df, weights_df, metrics, tracking_error
    """
    # ETF close prices and returns
    close_pivot = etf_data["close"].unstack(level="symbol")
    etf_returns = close_pivot.pct_change()

    # Index returns
    index_returns = index_data.pct_change()

    # Get LASSO weights
    weights = lasso_track(
        etf_returns,
        index_returns,
        lookback=lookback,
        alpha=alpha,
        rebalance_freq=rebalance_freq,
    )

    # Compute portfolio returns
    common_dates = weights.index.intersection(etf_returns.index).intersection(index_returns.index)
    common_symbols = weights.columns.intersection(etf_returns.columns)

    w = weights.loc[common_dates, common_symbols]
    r = etf_returns.loc[common_dates, common_symbols]
    idx_r = index_returns.loc[common_dates]

    # Shift weights by 1 day
    w_shifted = w.shift(1)
    port_return = (w_shifted * r).sum(axis=1)

    # Turnover & cost
    turnover = w_shifted.diff().fillna(0).abs().sum(axis=1)
    cost = turnover * commission
    net_return = port_return - cost

    # Date filter
    if start_date:
        mask = common_dates >= pd.Timestamp(start_date)
        port_return = port_return[mask]
        net_return = net_return[mask]
        turnover = turnover[mask]
        cost = cost[mask]
        idx_r = idx_r[mask]

    # Build result
    result_df = pd.DataFrame(
        {
            "portfolio_return": net_return,
            "index_return": idx_r,
            "excess_return": net_return - idx_r,
            "turnover": turnover,
            "cost": cost,
        }
    )
    result_df["cum_portfolio"] = result_df["portfolio_return"].cumsum()
    result_df["cum_index"] = result_df["index_return"].cumsum()
    result_df["cum_excess"] = result_df["excess_return"].cumsum()

    # Tracking error
    te = result_df["excess_return"].std() * np.sqrt(252)

    # Metrics
    n_years = len(result_df) / 252
    metrics = {
        "total_return": result_df["cum_portfolio"].iloc[-1],
        "index_return": result_df["cum_index"].iloc[-1],
        "excess_return": result_df["cum_excess"].iloc[-1],
        "annualized_excess": result_df["cum_excess"].iloc[-1] / n_years if n_years > 0 else 0,
        "tracking_error": te,
        "information_ratio": (result_df["excess_return"].mean() * 252) / te if te > 0 else 0,
        "avg_turnover": turnover.mean(),
    }

    print(f"\n  Portfolio Total Return: {metrics['total_return']:.2%}")
    print(f"  Index Total Return:     {metrics['index_return']:.2%}")
    print(f"  Excess Return:          {metrics['excess_return']:.2%}")
    print(f"  Tracking Error:         {metrics['tracking_error']:.2%}")
    print(f"  Information Ratio:      {metrics['information_ratio']:.2f}")

    return {
        "result_df": result_df,
        "weights_df": w,
        "metrics": metrics,
    }
