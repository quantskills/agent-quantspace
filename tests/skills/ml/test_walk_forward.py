from __future__ import annotations

import pandas as pd
import pytest

from skills.ml.walk_forward import date_level_mask, expanding_purged_folds


def test_expanding_purged_folds_boundaries_and_purge_gap() -> None:
    dates = pd.date_range("2020-01-01", periods=20, freq="B")
    folds = expanding_purged_folds(
        dates,
        min_train=8,
        retrain_step=4,
        purge=2,
    )

    assert len(folds) == 3
    first = folds[0]
    assert first.retrain_idx == 8
    assert first.train_dates.tolist() == dates[:6].tolist()
    assert first.pred_dates.tolist() == dates[8:12].tolist()
    assert first.purge == 2
    assert set(dates[6:8]).isdisjoint(set(first.train_dates))
    assert set(dates[6:8]).isdisjoint(set(first.pred_dates))
    assert first.train_dates[-1] == dates[5]
    assert first.pred_dates[0] == dates[8]


def test_expanding_purged_folds_are_chronological_without_shuffle() -> None:
    dates = pd.date_range("2020-01-01", periods=30, freq="B")
    folds = expanding_purged_folds(dates, min_train=10, retrain_step=5, purge=1)

    retrain_indices = [fold.retrain_idx for fold in folds]
    assert retrain_indices == sorted(retrain_indices)
    assert retrain_indices == [10, 15, 20, 25]

    for fold in folds:
        assert fold.train_dates.is_monotonic_increasing
        assert fold.pred_dates.is_monotonic_increasing
        assert fold.train_dates.max() < fold.pred_dates.min()
        assert set(fold.train_dates).isdisjoint(set(fold.pred_dates))


def test_expanding_purged_folds_default_frozen_protocol() -> None:
    dates = pd.date_range("2015-01-01", periods=600, freq="B")
    folds = expanding_purged_folds(dates, purge=20)

    assert folds[0].retrain_idx == 250
    assert len(folds[0].train_dates) == 230
    assert len(folds[0].pred_dates) == 126
    assert folds[1].retrain_idx == 376


def test_expanding_purged_folds_rejects_invalid_params() -> None:
    dates = pd.date_range("2020-01-01", periods=5, freq="B")
    with pytest.raises(ValueError, match="min_train"):
        expanding_purged_folds(dates, min_train=0)
    with pytest.raises(ValueError, match="retrain_step"):
        expanding_purged_folds(dates, retrain_step=0)
    with pytest.raises(ValueError, match="purge"):
        expanding_purged_folds(dates, purge=-1)


def test_date_level_mask_selects_matching_rows() -> None:
    dates = pd.date_range("2024-01-01", periods=3, name="eob")
    index = pd.MultiIndex.from_product([["A", "B"], dates], names=["symbol", "eob"])
    frame = pd.DataFrame({"value": range(len(index))}, index=index)

    mask = date_level_mask(index, dates[:2])

    assert mask.sum() == 4
    assert frame[mask].index.get_level_values("eob").max() == dates[1]
    assert frame["value"].to_numpy()[mask].tolist() == [0, 1, 3, 4]
