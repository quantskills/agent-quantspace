"""XGBoost rank strategy helpers for cross-sectional futures examples."""

from __future__ import annotations

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from skills.backtest.weighting import risk_parity
from strategies.cross_sectional.factors import (
    mean_reversion_score,
    momentum_score,
    trend_score,
    volatility_score,
)


def make_cross_sectional_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Build generic public cross-sectional factors for an OHLCV panel."""
    frames = []
    factor_specs = {
        "momentum_10": lambda group: momentum_score(group, lookback=10),
        "momentum_20": lambda group: momentum_score(group, lookback=20),
        "momentum_60": lambda group: momentum_score(group, lookback=60),
        "low_vol_20": lambda group: volatility_score(group, lookback=20),
        "low_vol_60": lambda group: volatility_score(group, lookback=60),
        "trend_40": lambda group: trend_score(group, lookback=40),
        "trend_120": lambda group: trend_score(group, lookback=120),
        "mean_reversion_10": lambda group: mean_reversion_score(group, lookback=10),
    }
    for symbol, group in panel.groupby(level="symbol", sort=False):
        single = group.droplevel("symbol")
        frame = pd.DataFrame(index=single.index)
        for name, func in factor_specs.items():
            frame[name] = func(single)
        frame["symbol"] = symbol
        frames.append(frame.reset_index().set_index(["symbol", "eob"]))
    if not frames:
        raise ValueError("panel cannot be empty.")
    return pd.concat(frames).sort_index()


def cross_sectional_rank_labels(panel: pd.DataFrame, horizon: int = 60) -> pd.Series:
    """Percentile rank of each symbol's forward return within each date."""
    if horizon < 1:
        raise ValueError("horizon must be positive.")
    close = panel["close"].unstack(level="symbol").sort_index()
    forward_return = close.shift(-horizon).div(close).sub(1.0)
    rank_label = forward_return.rank(axis=1, pct=True).stack().rename("rank_label")
    rank_label.index.names = ["eob", "symbol"]
    return rank_label.reorder_levels(["symbol", "eob"]).sort_index()


def rank_scores_to_weights(
    score_df: pd.DataFrame,
    close: pd.DataFrame,
    top_n: int = 2,
    vol_lookback: int = 60,
) -> pd.DataFrame:
    """Convert predicted rank scores into risk-parity weights on top names."""
    if top_n < 1:
        raise ValueError("top_n must be positive.")
    ranks = score_df.rank(axis=1, ascending=False, method="first")
    votes = ranks.le(top_n).astype(float).where(score_df.notna(), 0.0)
    returns = close.reindex(columns=score_df.columns).pct_change(fill_method=None)
    return risk_parity(
        votes,
        returns_df=returns,
        lookback=vol_lookback,
        min_periods=vol_lookback,
    ).fillna(0.0)


def _purged_multiindex_train(dataset: pd.DataFrame, split: pd.Timestamp, purge_window: int) -> pd.DataFrame:
    """Training rows whose forward labels are fully before the split date."""
    date_values = pd.DatetimeIndex(dataset.index.get_level_values("eob"))
    train_dates = pd.DatetimeIndex(date_values[date_values < split].unique()).sort_values()
    if purge_window > 0:
        train_dates = train_dates[:-purge_window]
    if len(train_dates) == 0:
        return dataset.iloc[0:0]
    return dataset[date_values.isin(train_dates)]


def xgboost_rank_weights(
    panel: pd.DataFrame,
    *,
    split_date: str = "2024-01-01",
    horizon: int = 60,
    top_n: int = 2,
    vol_lookback: int = 60,
    random_state: int = 42,
) -> pd.DataFrame:
    """Train a fixed-split XGBoost rank model and return target weights."""
    features = make_cross_sectional_features(panel).replace([np.inf, -np.inf], np.nan).dropna()
    labels = cross_sectional_rank_labels(panel, horizon=horizon)
    dataset = features.join(labels).dropna()
    split = pd.Timestamp(split_date)
    train = _purged_multiindex_train(dataset, split, purge_window=horizon)
    test = features[pd.DatetimeIndex(features.index.get_level_values("eob")) >= split]
    if train.empty or test.empty:
        raise ValueError("xgboost_rank_weights requires non-empty train and test datasets.")

    feature_cols = list(features.columns)
    model = XGBRegressor(
        n_estimators=80,
        max_depth=2,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="reg:squarederror",
        random_state=random_state,
        n_jobs=1,
    )
    model.fit(train[feature_cols], train["rank_label"])
    score = pd.Series(model.predict(test[feature_cols]), index=test.index, name="score")
    score_df = score.unstack(level="symbol").sort_index()
    close = panel["close"].unstack(level="symbol").sort_index()
    return rank_scores_to_weights(score_df, close, top_n=top_n, vol_lookback=vol_lookback)


__all__ = [
    "cross_sectional_rank_labels",
    "make_cross_sectional_features",
    "rank_scores_to_weights",
    "xgboost_rank_weights",
]
