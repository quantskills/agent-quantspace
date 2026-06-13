"""Streaming signal generation from raw OHLCV bars, features, and a trained classifier."""

from __future__ import annotations

import logging
from collections import deque
from typing import Protocol

import pandas as pd

from skills.model.ml_engine import ModelPredictor
from strategies.time_series.types import DEFAULT_POSITION_MAPPING

logger = logging.getLogger(__name__)


class FeatureLike(Protocol):
    values: pd.DataFrame

    def set_data(self, data: pd.DataFrame) -> None: ...

    def cal_values(self) -> pd.DataFrame: ...


class SignalEngine:
    def __init__(
        self,
        feature: FeatureLike,
        train_feat_path: str,
        model_path: str,
        eo_train: pd.Timestamp | None = None,
        window_size: int = 500,
    ) -> None:
        self.feature = feature
        self.last_target_pos = 0
        self.window_size = window_size
        self.bar_buffer: deque[dict] = deque(maxlen=self.window_size)
        train_df = pd.read_parquet(train_feat_path)
        train_df.set_index("eob", inplace=True)
        train_df.index = pd.to_datetime(train_df.index)
        if eo_train is not None:
            train_df = train_df[train_df.index < eo_train]
        self.train_df = train_df
        self.predictor = ModelPredictor(model_path, self.train_df)
        logger.info("SignalEngine initialized")

    def reset(self) -> None:
        self.bar_buffer.clear()

    def feed_bar(self, bar_dict: dict) -> int | None:
        self.bar_buffer.append(bar_dict)
        bar_df = pd.DataFrame(list(self.bar_buffer)).set_index("eob")
        bar_df.index = pd.to_datetime(bar_df.index)
        self.feature.set_data(bar_df)
        self.feature.cal_values()
        if self.feature.values.dropna().empty:
            return None
        preds = self.predictor.predict(self.feature.values.tail(1))
        label = preds["prediction_label"].iloc[-1]
        score = preds["prediction_score"].iloc[-1]
        signal = DEFAULT_POSITION_MAPPING.get(label)
        if signal != self.last_target_pos:
            self.last_target_pos = signal
            logger.info(
                "%s | %s | signal=%s | score=%s",
                bar_dict["eob"],
                bar_dict["close"],
                signal,
                score,
            )
            return signal
        return None
