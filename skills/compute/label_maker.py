"""Public label generators for supervised learning on bar series."""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _load_bars(bar_file_path: str | Path | None, data: pd.DataFrame | None) -> pd.DataFrame:
    """Return a copy of bar data indexed by ``eob``."""
    if data is not None and not data.empty:
        bars = data.copy()
    elif bar_file_path is not None:
        bars = pd.read_parquet(bar_file_path)
        if "eob" in bars.columns:
            bars = bars.set_index("eob")
    else:
        raise ValueError("Provide either non-empty data or bar_file_path.")

    bars.index = pd.to_datetime(bars.index)
    bars.index.name = "eob"
    if "close" not in bars.columns:
        raise ValueError("Label generation requires a 'close' column.")
    return bars.sort_index()


class ForwardReturnLabelMaker:
    """Create labels from forward returns.

    Labels are ``1`` when the forward return is above ``up_threshold``, ``-1``
    when below ``down_threshold``, and ``0`` otherwise.
    """

    def __init__(
        self,
        bar_file_path: str | Path | None = None,
        data: pd.DataFrame | None = None,
        horizon: int = 1,
        up_threshold: float = 0.0,
        down_threshold: float = 0.0,
    ):
        if horizon <= 0:
            raise ValueError("horizon must be positive.")
        self.bar_file_path = str(bar_file_path) if bar_file_path is not None else ""
        self.data = _load_bars(bar_file_path, data)
        self.horizon = horizon
        self.up_threshold = up_threshold
        self.down_threshold = down_threshold
        self.labels: pd.DataFrame | None = None

    def generate_labels(self) -> pd.DataFrame:
        close = self.data["close"].astype(float)
        forward_return = close.shift(-self.horizon) / close - 1.0
        state = pd.Series(0, index=self.data.index, dtype=int)
        state.loc[forward_return.gt(self.up_threshold)] = 1
        state.loc[forward_return.lt(-abs(self.down_threshold))] = -1

        self.labels = pd.DataFrame(
            {
                "state": state,
                "forward_return": forward_return,
                "close": close,
                "logreturn": np.log(close).diff(),
                "sign_state_prob": state.astype(float),
            },
            index=self.data.index,
        )
        for column in ("open", "high", "low"):
            if column in self.data.columns:
                self.labels[column] = self.data[column]
        return self.labels

    def store_labels(self, path: str | Path | None = None) -> Path:
        if self.labels is None:
            raise ValueError("No labels to save. Call generate_labels() first.")
        out_path = Path(path) if path is not None else self.default_file_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.labels.to_parquet(out_path)
        return out_path

    @property
    def default_file_path(self) -> Path:
        if self.bar_file_path:
            stem = Path(self.bar_file_path).with_suffix("")
            return stem.parent / f"{stem.name}_labels_fwd_h{self.horizon}.parquet"
        return Path(f"labels_fwd_h{self.horizon}.parquet")


class TripleBarrierLabelMaker:
    """Triple-barrier labels using the AFML profit, stop, and time barriers."""

    def __init__(
        self,
        bar_file_path: str | Path | None = None,
        data: pd.DataFrame | None = None,
        L: int = 5,
        pt_sl: float = 1.0,
        t_limit: int = 10,
    ):
        if L <= 0:
            raise ValueError("L must be positive.")
        if pt_sl <= 0:
            raise ValueError("pt_sl must be positive.")
        if t_limit <= 0:
            raise ValueError("t_limit must be positive.")
        self.bar_file_path = str(bar_file_path) if bar_file_path is not None else ""
        self.data = _load_bars(bar_file_path, data)
        self.L = L
        self.pt_sl = pt_sl
        self.t_limit = t_limit
        self.labels: pd.DataFrame | None = None

    @property
    def file_path(self) -> str:
        if self.bar_file_path:
            stem = Path(self.bar_file_path).with_suffix("")
            return str(stem.parent / f"{stem.name}_labels_tbm_L{self.L}_t{self.t_limit}.parquet")
        return f"labels_tbm_L{self.L}_t{self.t_limit}.parquet"

    def generate_labels(self) -> pd.DataFrame:
        close = self.data["close"].astype(float)
        returns = close.pct_change()
        volatility = returns.ewm(span=100, min_periods=max(2, self.L)).std() * np.sqrt(self.L)

        close_values = close.to_numpy(dtype=float)
        vol_values = volatility.to_numpy(dtype=float)
        states = np.zeros(len(self.data), dtype=int)

        for i in range(len(self.data) - self.t_limit):
            if np.isnan(vol_values[i]):
                continue
            start_price = close_values[i]
            upper = start_price * (1.0 + vol_values[i] * self.pt_sl)
            lower = start_price * (1.0 - vol_values[i] * self.pt_sl)
            window = close_values[i + 1 : i + 1 + self.t_limit]

            up_hits = np.flatnonzero(window >= upper)
            down_hits = np.flatnonzero(window <= lower)
            first_up = up_hits[0] if len(up_hits) else np.inf
            first_down = down_hits[0] if len(down_hits) else np.inf

            if first_up < first_down:
                states[i] = 1
            elif first_down < first_up:
                states[i] = -1

        self.labels = pd.DataFrame(
            {
                "state": states,
                "close": close,
                "logreturn": np.log(close).diff(),
                "sign_state_prob": states.astype(float),
            },
            index=self.data.index,
        )
        for column in ("open", "high", "low"):
            if column in self.data.columns:
                self.labels[column] = self.data[column]

        logger.info(
            "Triple-barrier labels generated at %s: up=%s down=%s neutral=%s",
            dt.datetime.utcnow().isoformat(timespec="seconds"),
            int((states == 1).sum()),
            int((states == -1).sum()),
            int((states == 0).sum()),
        )
        return self.labels

    def store_labels(self, path: str | Path | None = None) -> Path:
        if self.labels is None:
            raise ValueError("No labels to save. Call generate_labels() first.")
        out_path = Path(path) if path is not None else Path(self.file_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.labels.to_parquet(out_path)
        return out_path

    def process(self) -> pd.DataFrame:
        labels = self.generate_labels()
        self.store_labels()
        return labels
