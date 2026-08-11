"""Signal-frame execution adapter backed by the shared vector backtester."""

from __future__ import annotations

import pandas as pd

from skills.backtest import BacktestResult, VectorBacktester


class SignalBacktestExecutor:
    """Execute long-form signal frames that contain strategy target weights."""

    def __init__(
        self,
        *,
        data: pd.DataFrame,
        trade_at: str = "close",
        signal_lag: int = 1,
        commission: float,
        slippage_bp: float,
        start_date: str | None = None,
        end_date: str | None = None,
        enforce_trade_constraints: bool = False,
    ) -> None:
        self.data = data
        self.trade_at = trade_at
        self.signal_lag = int(signal_lag)
        self.commission = float(commission)
        self.slippage_bp = float(slippage_bp)
        self.start_date = start_date
        self.end_date = end_date
        self.enforce_trade_constraints = bool(enforce_trade_constraints)
        self.executed_weights: pd.DataFrame | None = None
        self.result_df: pd.DataFrame | None = None
        self.metrics: dict[str, float] = {}

    def _target_weights(self, signal_df: pd.DataFrame) -> pd.DataFrame:
        if "strategy__target_weight" not in signal_df.columns:
            raise ValueError("signal_df must contain 'strategy__target_weight'.")
        if not isinstance(signal_df.index, pd.MultiIndex):
            raise ValueError("signal_df.index must be a MultiIndex with ['symbol', 'eob'].")
        if list(signal_df.index.names) != ["symbol", "eob"]:
            raise ValueError("signal_df.index names must be exactly ['symbol', 'eob'].")
        weights = signal_df["strategy__target_weight"].unstack(level="symbol").sort_index()
        weights.index.name = "eob"
        weights.columns.name = None
        return weights.fillna(0.0)

    def run(self, signal_df: pd.DataFrame) -> BacktestResult:
        """Execute target weights and retain the result views for inspection."""
        result = VectorBacktester(
            data=self.data,
            trade_at=self.trade_at,
            signal_lag=self.signal_lag,
            commission=self.commission,
            slippage_bp=self.slippage_bp,
            start_date=self.start_date,
            end_date=self.end_date,
            enforce_trade_constraints=self.enforce_trade_constraints,
        ).run(self._target_weights(signal_df))
        self.executed_weights = result.executed_weights
        self.result_df = result.result_df
        self.metrics = result.metrics
        return result


__all__ = ["SignalBacktestExecutor"]
