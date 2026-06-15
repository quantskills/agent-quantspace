"""Composable backtester built from factor, strategy, and execution stages."""

from __future__ import annotations

from typing import Literal

import pandas as pd

from skills.backtest import VectorBacktester

from .factor_frame import FactorFrameBuilder
from .signals_base import BaseStrategy, StrategyContext
from .signals_top_pct import TopPctStrategy
from .types import (
    ExitFilterConfig,
    FactorConfig,
    _normalize_rebalance_freq,
)

TradeAt = Literal["open", "close"]


class ModularBacktester:
    """Stage-based extension that keeps the legacy Backtester untouched."""

    def __init__(
        self,
        data: pd.DataFrame,
        factor_configs: list[FactorConfig],
        top_pct: float = 0.2,
        trade_at: TradeAt = "close",
        signal_lag: int = 1,
        commission: float = 0.0002,
        slippage_bp: float | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        exit_filters: list[ExitFilterConfig] | None = None,
        rebalance_freq: int | str = 1,
        weight_method: str = "equal",
        vol_target: float | None = None,
        exposure_policy: str = "keep_cash",
        defensive_symbols: list[str] | None = None,
        strategy: BaseStrategy | None = None,
    ) -> None:
        self.data = data.copy()
        self.factor_configs = factor_configs
        self.top_pct = float(top_pct)
        self.trade_at = trade_at
        self.signal_lag = int(signal_lag)
        self.commission = float(commission)
        self.slippage_bp = slippage_bp
        self.start_date = pd.Timestamp(start_date) if start_date else None
        self.end_date = pd.Timestamp(end_date) if end_date else None
        self.exit_filters = exit_filters or []
        self.rebalance_freq = _normalize_rebalance_freq(rebalance_freq)
        self.weight_method = weight_method
        self.vol_target = vol_target
        self.exposure_policy = exposure_policy
        self.defensive_symbols = defensive_symbols or []
        self.strategy = strategy or TopPctStrategy()

        self._price_pivots: dict[str, pd.DataFrame] = {}
        self._return_cache: dict[str, pd.DataFrame] = {}

        self.factor_df: pd.DataFrame | None = None
        self.factor_pivots: dict[str, pd.DataFrame] = {}
        self.signal_df: pd.DataFrame | None = None
        self.votes_df: pd.DataFrame | None = None
        self.signal_weights: pd.DataFrame | None = None
        self.executed_weights: pd.DataFrame | None = None
        self.weights_df: pd.DataFrame | None = None
        self.result_df: pd.DataFrame | None = None
        self.metrics: dict[str, float] = {}

        self._validate_inputs()

    def _validate_inputs(self) -> None:
        if not isinstance(self.data.index, pd.MultiIndex):
            raise ValueError("data.index must be a MultiIndex with levels ['symbol', 'eob'].")
        if list(self.data.index.names) != ["symbol", "eob"]:
            raise ValueError("data.index names must be exactly ['symbol', 'eob'].")
        if not self.data.index.is_monotonic_increasing:
            raise ValueError("data must be sorted by ['symbol', 'eob'] in ascending order.")
        if not self.factor_configs:
            raise ValueError("factor_configs cannot be empty.")
        if not 0 < self.top_pct <= 1:
            raise ValueError("top_pct must be in the interval (0, 1].")
        if self.signal_lag < 0:
            raise ValueError("signal_lag must be greater than or equal to 0.")
        if self.slippage_bp is None:
            raise ValueError("slippage_bp must be explicitly provided.")
        if self.trade_at not in {"open", "close"}:
            raise ValueError("trade_at must be either 'open' or 'close'.")
        if "close" not in self.data.columns:
            raise ValueError("data must contain a 'close' column.")
        if self.trade_at == "open" and "open" not in self.data.columns:
            raise ValueError("trade_at='open' requires an 'open' column in data.")

    @property
    def execution_price_pivot(self) -> pd.DataFrame:
        if self.trade_at not in self._price_pivots:
            self._price_pivots[self.trade_at] = self.data[self.trade_at].unstack(level="symbol")
        return self._price_pivots[self.trade_at]

    @property
    def execution_returns(self) -> pd.DataFrame:
        if self.trade_at not in self._return_cache:
            self._return_cache[self.trade_at] = self.execution_price_pivot.pct_change(
                fill_method=None
            )
        return self._return_cache[self.trade_at]

    def build_factor_frame(self) -> pd.DataFrame:
        if self.factor_df is None:
            build_result = FactorFrameBuilder(self.data, self.factor_configs).build()
            self.factor_df = build_result.factor_df
            self.factor_pivots = build_result.factor_pivots
        return self.factor_df

    def _make_strategy_context(self) -> StrategyContext:
        return StrategyContext(
            data=self.data,
            factor_configs=self.factor_configs,
            exit_filters=self.exit_filters,
            top_pct=self.top_pct,
            weight_method=self.weight_method,
            rebalance_freq=self.rebalance_freq,
            vol_target=self.vol_target,
            exposure_policy=self.exposure_policy,
            defensive_symbols=self.defensive_symbols,
            execution_returns=self.execution_returns,
            signal_lag=self.signal_lag,
        )

    def build_signal_frame(self) -> pd.DataFrame:
        factor_df = self.build_factor_frame()
        strategy_result = self.strategy.generate(
            factor_df=factor_df,
            factor_pivots=self.factor_pivots,
            context=self._make_strategy_context(),
        )
        self.signal_df = strategy_result.signal_df
        self.votes_df = strategy_result.votes_df
        self.signal_weights = strategy_result.signal_weights
        self.weights_df = self.signal_weights
        return self.signal_df

    def run(self) -> pd.DataFrame:
        self.build_signal_frame()
        execution_result = VectorBacktester(
            data=self.data,
            trade_at=self.trade_at,
            signal_lag=self.signal_lag,
            commission=self.commission,
            slippage_bp=float(self.slippage_bp),
            start_date=self.start_date.isoformat() if self.start_date is not None else None,
            end_date=self.end_date.isoformat() if self.end_date is not None else None,
        ).run(self.signal_weights)
        self.executed_weights = execution_result.executed_weights
        self.result_df = execution_result.result_df
        self.metrics = execution_result.metrics
        return self.result_df

    def get_daily_weights(self, date: str) -> pd.Series:
        if self.signal_weights is None:
            raise ValueError("run() must be called before get_daily_weights().")

        ts = pd.Timestamp(date)
        if ts not in self.signal_weights.index:
            idx = self.signal_weights.index.get_indexer([ts], method="nearest")[0]
            ts = self.signal_weights.index[idx]

        row = self.signal_weights.loc[ts]
        return row[row > 0].sort_values(ascending=False)

    def get_weight_stats(self) -> pd.Series:
        if self.signal_weights is None:
            raise ValueError("run() must be called before get_weight_stats().")

        return (self.signal_weights > 0).sum(axis=0).sort_values(ascending=False)
