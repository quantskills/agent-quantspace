"""Expanding walk-forward folds with label purge for time-ordered ML."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class ExpandingPurgeFold:
    """One chronological expanding fold with a purged train / predict split."""

    fold_id: int
    train_dates: pd.DatetimeIndex
    pred_dates: pd.DatetimeIndex
    retrain_idx: int
    purge: int


def expanding_purged_folds(
    dates: Sequence[pd.Timestamp] | pd.DatetimeIndex,
    *,
    min_train: int = 250,
    retrain_step: int = 126,
    purge: int = 20,
) -> list[ExpandingPurgeFold]:
    """Build expanding walk-forward folds with purge between train and predict.

    Each fold uses cumulative training dates ``dates[0:retrain_idx]``. The last
    ``purge`` training dates are removed so forward labels do not leak into the
    predict window. Predictions are generated on
    ``dates[retrain_idx:retrain_idx + retrain_step]``.

    Folds are strictly chronological; there is no random or shuffled split.
    """
    if min_train < 1:
        raise ValueError("min_train must be positive.")
    if retrain_step < 1:
        raise ValueError("retrain_step must be positive.")
    if purge < 0:
        raise ValueError("purge must be non-negative.")

    ordered = pd.DatetimeIndex(pd.unique(pd.DatetimeIndex(dates))).sort_values()
    n_dates = len(ordered)
    if n_dates == 0:
        return []

    folds: list[ExpandingPurgeFold] = []
    for fold_id, retrain_idx in enumerate(range(min_train, n_dates, retrain_step)):
        pred_end = min(retrain_idx + retrain_step, n_dates)
        pred_dates = ordered[retrain_idx:pred_end]
        if len(pred_dates) == 0:
            continue

        raw_train = ordered[:retrain_idx]
        if purge > 0:
            if len(raw_train) <= purge:
                continue
            train_dates = raw_train[:-purge]
        else:
            train_dates = raw_train

        if len(train_dates) == 0:
            continue

        folds.append(
            ExpandingPurgeFold(
                fold_id=fold_id,
                train_dates=train_dates,
                pred_dates=pred_dates,
                retrain_idx=retrain_idx,
                purge=purge,
            )
        )
    return folds


def date_level_mask(
    index: pd.MultiIndex,
    dates: pd.DatetimeIndex | Sequence[pd.Timestamp],
    *,
    level: str = "eob",
) -> np.ndarray:
    """Boolean row mask for MultiIndex rows whose ``level`` value is in ``dates``.

    A mask keeps the same rows selectable from a DataFrame, a Series, and the
    matching feature matrix without materializing intermediate frames.
    """
    level_values = pd.DatetimeIndex(index.get_level_values(level))
    return level_values.isin(pd.DatetimeIndex(dates))


__all__ = [
    "ExpandingPurgeFold",
    "date_level_mask",
    "expanding_purged_folds",
]
