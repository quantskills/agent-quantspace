"""XGBoost time-series ML signal helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from skills.compute.label_maker import TripleBarrierLabelMaker
from strategies.time_series.features import make_price_volume_features


def class_probability(
    probabilities: np.ndarray,
    classes: np.ndarray,
    encoded_label: int,
) -> np.ndarray:
    """Extract one encoded class probability, failing if the class is absent."""
    class_positions = {int(label): i for i, label in enumerate(classes)}
    if encoded_label not in class_positions:
        raise ValueError(f"Missing required encoded label {encoded_label} in model classes.")
    return probabilities[:, class_positions[encoded_label]]


def probability_spread_weights(
    probabilities: np.ndarray,
    classes: np.ndarray,
    index: pd.Index,
    symbol: str,
    threshold: float = 0.15,
    positive_encoded_label: int = 2,
    negative_encoded_label: int = 0,
) -> pd.DataFrame:
    """Map positive-minus-negative class probability spread to target weights."""
    if threshold <= 0:
        raise ValueError("threshold must be positive.")
    positive_probability = pd.Series(
        class_probability(probabilities, classes, positive_encoded_label),
        index=index,
    )
    negative_probability = pd.Series(
        class_probability(probabilities, classes, negative_encoded_label),
        index=index,
    )
    probability_spread = positive_probability - negative_probability
    weights = pd.Series(0.0, index=index)
    weights[probability_spread > threshold] = 1.0
    weights[probability_spread < -threshold] = -1.0
    return weights.to_frame(symbol)


def _purged_datetime_train(dataset: pd.DataFrame, split: pd.Timestamp, purge_window: int) -> pd.DataFrame:
    """Training rows whose forward labels are fully before the split date."""
    train_dates = pd.DatetimeIndex(dataset.index[dataset.index < split].unique()).sort_values()
    if purge_window > 0:
        train_dates = train_dates[:-purge_window]
    if len(train_dates) == 0:
        return dataset.iloc[0:0]
    return dataset[dataset.index.isin(train_dates)]


def xgboost_triple_barrier_weights(
    bars: pd.DataFrame,
    *,
    symbol: str,
    split_date: str = "2024-01-01",
    diff_lookback: int = 5,
    label_l: int = 5,
    label_pt_sl: float = 0.8,
    label_t_limit: int = 5,
    threshold: float = 0.15,
    random_state: int = 7,
) -> pd.DataFrame:
    """Train fixed-split XGBoost triple-barrier classifier and return weights."""
    features = make_price_volume_features(bars, diff_lookback=diff_lookback)
    labels = TripleBarrierLabelMaker(
        data=bars,
        L=label_l,
        pt_sl=label_pt_sl,
        t_limit=label_t_limit,
    ).generate_labels()
    features = features.replace([np.inf, -np.inf], np.nan).dropna()
    dataset = features.join(labels[["state"]].rename(columns={"state": "label"})).dropna()
    split = pd.Timestamp(split_date)
    train = _purged_datetime_train(dataset, split, purge_window=label_t_limit)
    test = features[features.index >= split]
    if train.empty or test.empty:
        raise ValueError("xgboost_triple_barrier_weights requires non-empty train and test datasets.")

    label_to_code = {-1: 0, 0: 1, 1: 2}
    encoded_train_label = train["label"].map(label_to_code)
    if encoded_train_label.isna().any():
        raise ValueError("Triple-barrier labels must be in {-1, 0, 1}.")

    model = XGBClassifier(
        n_estimators=50,
        max_depth=2,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="multi:softprob",
        eval_metric="mlogloss",
        random_state=random_state,
        n_jobs=1,
    )
    model.fit(train.drop(columns=["label"]), encoded_train_label)
    probabilities = model.predict_proba(test)
    return probability_spread_weights(
        probabilities,
        model.classes_,
        index=test.index,
        symbol=symbol,
        threshold=threshold,
    )


__all__ = [
    "class_probability",
    "probability_spread_weights",
    "xgboost_triple_barrier_weights",
]
