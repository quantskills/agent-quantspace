"""Shared vectorized backtesting utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

TradeAt = Literal["open", "close"]


@dataclass
class BacktestResult:
    """Result bundle returned by the vectorized backtester."""

    executed_weights: pd.DataFrame
    result_df: pd.DataFrame
    metrics: dict[str, float]


def bp_to_rate(bp: int | float) -> float:
    """Convert basis points to a decimal rate."""
    return float(bp) / 10_000.0


def calculate_month_span(index: pd.DatetimeIndex) -> float:
    """Return the span of a DatetimeIndex in fractional months."""
    start_date = index.min()
    end_date = index.max()
    month_count = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
    days_in_start_month = (start_date + pd.offsets.MonthEnd(0)).day
    days_in_end_month = (end_date + pd.offsets.MonthEnd(0)).day
    fraction = (end_date.day / days_in_end_month) - (start_date.day / days_in_start_month)
    return month_count + fraction


def annual_return_metrics(result_df: pd.DataFrame) -> dict[str, float]:
    """Return calendar-year compounded strategy returns."""
    rows: dict[str, float] = {}
    if result_df.empty:
        return rows
    for year, group in result_df.groupby(result_df.index.year):
        equity = (1.0 + group["return"]).cumprod()
        rows[f"{year}_return"] = float(equity.iloc[-1] - 1.0)
    return rows


def activity_metrics(result_df: pd.DataFrame) -> dict[str, float]:
    """Return simple trading activity diagnostics from a result frame."""
    if result_df.empty or "turnover" not in result_df.columns:
        return {"trade_days": 0.0, "active_day_ratio": 0.0}
    trade_days = float(result_df["turnover"].gt(1e-8).sum())
    return {
        "trade_days": trade_days,
        "active_day_ratio": trade_days / float(len(result_df)),
    }


def benchmark_return_corr(result_df: pd.DataFrame, benchmark_close: pd.Series) -> float:
    """Correlation between strategy daily returns and benchmark close returns."""
    if result_df.empty:
        return np.nan
    benchmark_return = benchmark_close.pct_change(fill_method=None)
    return float(result_df["return"].corr(benchmark_return.reindex(result_df.index)))


class VectorBacktester:
    """根据日期 × 标的的目标权重，计算下一根 K 线的组合收益。

    ``self.data`` 只保存输入行情，不保存交易信号。策略生成的交易信号以
    ``weights_df`` 传入 :meth:`run`，经过信号延迟和交易约束后，通过
    :class:`BacktestResult` 的 ``executed_weights`` 字段返回。
    """

    def __init__(
        self,
        data: pd.DataFrame,
        trade_at: TradeAt = "close",
        signal_lag: int = 1,
        commission: float | None = None,
        slippage_bp: float | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        enforce_trade_constraints: bool = False,
    ) -> None:
        """校验并复制行情数据，同时保存回测参数和初始化内部缓存。

        Args:
            data: 以 ``(symbol, eob)`` 为 MultiIndex 的行情 DataFrame。
            trade_at: 使用 ``open`` 或 ``close`` 作为成交价格。
            signal_lag: 将原始信号向后移动的 K 线数量。
            commission: 单边佣金率，例如 ``0.0002`` 表示 2bp。
            slippage_bp: 单边滑点，单位为基点。
            start_date: 回测结果的可选起始日期，不会裁剪 ``self.data``。
            end_date: 回测结果的可选结束日期，不会裁剪 ``self.data``。
            enforce_trade_constraints: 是否应用停牌、涨停和跌停约束。
        """
        if commission is None or slippage_bp is None:
            raise ValueError("commission and slippage_bp must be explicitly provided.")
        if trade_at not in {"open", "close"}:
            raise ValueError("trade_at must be either 'open' or 'close'.")
        if not isinstance(data.index, pd.MultiIndex):
            raise ValueError("data.index must be a MultiIndex with levels ['symbol', 'eob'].")
        if list(data.index.names) != ["symbol", "eob"]:
            raise ValueError("data.index names must be exactly ['symbol', 'eob'].")
        if trade_at not in data.columns:
            raise ValueError(f"data must contain the trade_at column {trade_at!r}.")

        self.data = data.copy()
        self.trade_at = trade_at
        self.signal_lag = int(signal_lag)
        self.commission = float(commission)
        self.slippage_bp = float(slippage_bp)
        self.start_date = pd.Timestamp(start_date) if start_date else None
        self.end_date = pd.Timestamp(end_date) if end_date else None
        self.enforce_trade_constraints = bool(enforce_trade_constraints)

        self._price_pivots: dict[str, pd.DataFrame] = {}
        self._return_cache: dict[str, pd.DataFrame] = {}
        self._constraint_diagnostics: pd.DataFrame | None = None

    @property
    def execution_price_pivot(self) -> pd.DataFrame:
        """返回日期 × 标的的成交价矩阵，并按成交字段缓存结果。"""
        if self.trade_at not in self._price_pivots:
            self._price_pivots[self.trade_at] = self.data[self.trade_at].unstack(level="symbol")
        return self._price_pivots[self.trade_at]

    @property
    def execution_returns(self) -> pd.DataFrame:
        """返回日期 × 标的的下一根 K 线收益率矩阵，并缓存计算结果。

        日期 ``t`` 上的值为 ``price[t + 1] / price[t] - 1``，因此日期
        ``t`` 的执行权重赚取下一根 K 线的收益。
        """
        if self.trade_at not in self._return_cache:
            price = self.execution_price_pivot
            self._return_cache[self.trade_at] = price.shift(-1).div(price).sub(1.0)
        return self._return_cache[self.trade_at]

    def _build_executed_weights(self, signal_weights: pd.DataFrame) -> pd.DataFrame:
        """将策略信号权重转换成实际执行权重。

        ``signal_weights`` 就是策略层传入的交易信号。先应用
        ``signal_lag``，再按需应用停牌和涨跌停等交易约束。
        """
        target_weights = signal_weights.shift(self.signal_lag).fillna(0.0)
        if not self.enforce_trade_constraints:
            self._constraint_diagnostics = None
            return target_weights
        return self._apply_trade_constraints(target_weights)

    def _constraint_pivot(self, column: str, index: pd.Index, columns: pd.Index) -> pd.DataFrame:
        """把行情中的布尔交易约束列转换成日期 × 标的矩阵。"""
        if column not in self.data.columns:
            raise ValueError(f"enforce_trade_constraints=True requires data column {column!r}.")
        return (
            self.data[column]
            .unstack(level="symbol")
            .reindex(index=index, columns=columns)
            .fillna(False)
            .astype(bool)
        )

    def _apply_trade_constraints(self, target_weights: pd.DataFrame) -> pd.DataFrame:
        """逐日模拟交易约束，返回实际可成交的持仓权重。

        停牌时禁止买卖，涨停时禁止买入，跌停时禁止卖出；若剩余现金不足，
        则按比例缩减当日允许执行的买入权重。同时记录受阻权重和现金权重。
        """
        target = target_weights.fillna(0.0).clip(lower=0.0)
        dates = target.index
        symbols = target.columns
        suspended = self._constraint_pivot("is_suspended", dates, symbols)
        limit_up = self._constraint_pivot("is_limit_up", dates, symbols)
        limit_down = self._constraint_pivot("is_limit_down", dates, symbols)

        executed_rows: list[np.ndarray] = []
        diagnostic_rows: list[dict[str, float]] = []
        previous = np.zeros(len(symbols), dtype=float)
        suspended_values = suspended.to_numpy(dtype=bool)
        limit_up_values = limit_up.to_numpy(dtype=bool)
        limit_down_values = limit_down.to_numpy(dtype=bool)
        target_values = target.to_numpy(dtype=float)

        for row_idx, desired in enumerate(target_values):
            desired = np.nan_to_num(desired, nan=0.0, posinf=0.0, neginf=0.0)
            delta = desired - previous
            requested_sell = np.clip(-delta, 0.0, None)
            requested_buy = np.clip(delta, 0.0, None)

            blocked_sell_mask = requested_sell > 1e-12
            blocked_sell_mask &= suspended_values[row_idx] | limit_down_values[row_idx]
            blocked_buy_mask = requested_buy > 1e-12
            blocked_buy_mask &= suspended_values[row_idx] | limit_up_values[row_idx]

            allowed_sell = requested_sell.copy()
            allowed_sell[blocked_sell_mask] = 0.0
            after_sell = np.maximum(previous - allowed_sell, 0.0)

            allowed_buy = requested_buy.copy()
            allowed_buy[blocked_buy_mask] = 0.0
            cash_available = max(0.0, 1.0 - float(after_sell.sum()))
            allowed_buy_total = float(allowed_buy.sum())
            unfilled_cash_buy = 0.0
            if allowed_buy_total > cash_available + 1e-12:
                scale = cash_available / allowed_buy_total if allowed_buy_total > 0 else 0.0
                unfilled_cash_buy = allowed_buy_total - cash_available
                allowed_buy = allowed_buy * scale

            current = after_sell + allowed_buy
            current[np.abs(current) <= 1e-12] = 0.0
            executed_rows.append(current.copy())
            diagnostic_rows.append(
                {
                    "blocked_buy_weight": float(
                        requested_buy[blocked_buy_mask].sum() + unfilled_cash_buy
                    ),
                    "blocked_sell_weight": float(requested_sell[blocked_sell_mask].sum()),
                    "cash_weight": float(max(0.0, 1.0 - current.sum())),
                }
            )
            previous = current

        executed = pd.DataFrame(executed_rows, index=dates, columns=symbols)
        executed.columns.name = target_weights.columns.name
        self._constraint_diagnostics = pd.DataFrame(diagnostic_rows, index=dates)
        return executed

    def compute_execution_returns(self, executed_weights: pd.DataFrame) -> pd.DataFrame:
        """根据执行权重计算每日组合收益、换手率和交易成本。

        Returns:
            包含 ``raw_return``、``transaction_cost``、``return`` 和
            ``turnover`` 的 DataFrame；启用交易约束时还会包含约束诊断列。
        """
        common_dates = executed_weights.index.intersection(self.execution_returns.index)
        common_symbols = executed_weights.columns.intersection(self.execution_returns.columns)
        if len(common_dates) == 0 or len(common_symbols) == 0:
            raise ValueError("weights_df has no overlap with the backtest data.")

        aligned_weights = executed_weights.loc[common_dates, common_symbols].fillna(0.0)
        aligned_returns = self.execution_returns.loc[common_dates, common_symbols]

        active_weight_mask = aligned_weights.abs() > 1e-12
        missing_active_returns = active_weight_mask & aligned_returns.isna()
        if missing_active_returns.any(axis=1).any():
            missing_dates = missing_active_returns.any(axis=1)
            allowed_boundary = aligned_returns.index.max()
            problem_dates = missing_dates[missing_dates].index.difference([allowed_boundary])
            if len(problem_dates) > 0:
                sample = ", ".join(str(pd.Timestamp(date).date()) for date in problem_dates[:5])
                raise ValueError(
                    f"Missing execution returns for active positions on dates: {sample}"
                )

        raw_returns = (aligned_weights * aligned_returns).sum(axis=1, min_count=1)
        raw_returns = raw_returns.mask(missing_active_returns.any(axis=1))
        symbol_turnover = aligned_weights.diff().fillna(aligned_weights).abs()
        turnover = symbol_turnover.sum(axis=1)
        transaction_costs = turnover * (self.commission + bp_to_rate(self.slippage_bp))

        result = pd.DataFrame(
            {
                "raw_return": raw_returns,
                "transaction_cost": transaction_costs,
                "return": raw_returns - transaction_costs,
                "turnover": turnover,
            }
        )
        if self._constraint_diagnostics is not None:
            diagnostics = self._constraint_diagnostics.reindex(common_dates).fillna(0.0)
            for column in diagnostics.columns:
                result[column] = diagnostics[column]
            relevant_mask = (aligned_weights.abs().sum(axis=1) > 0) | diagnostics[
                ["blocked_buy_weight", "blocked_sell_weight"]
            ].sum(axis=1).gt(0)
        else:
            relevant_mask = aligned_weights.abs().sum(axis=1) > 0

        if relevant_mask.any():
            first_relevant_date = relevant_mask[relevant_mask].index[0]
            result.loc[result.index < first_relevant_date, ["raw_return", "return"]] = np.nan
        return result

    def _apply_date_range(self, result_df: pd.DataFrame) -> pd.DataFrame:
        """按配置的起止日期裁剪回测结果，不修改原始行情。"""
        mask = pd.Series(True, index=result_df.index)
        if self.start_date is not None:
            mask &= result_df.index >= self.start_date
        if self.end_date is not None:
            mask &= result_df.index <= self.end_date
        return result_df.loc[mask]

    def build_result_frame(self, executed_weights: pd.DataFrame) -> pd.DataFrame:
        """构建包含日收益、累计净值、累计收益和回撤的完整结果表。"""
        result_df = self.compute_execution_returns(executed_weights)
        result_df = self._apply_date_range(result_df)
        result_df = result_df.dropna(subset=["raw_return"])
        result_df["equity"] = (1.0 + result_df["return"]).cumprod()
        result_df["raw_equity"] = (1.0 + result_df["raw_return"]).cumprod()
        result_df["cum_return"] = result_df["equity"] - 1.0
        result_df["cum_raw_return"] = result_df["raw_equity"] - 1.0
        result_df["cum_return_max"] = result_df["equity"].cummax()
        result_df["drawdown"] = result_df["equity"] / result_df["cum_return_max"] - 1.0
        return result_df

    def calculate_metrics(self, result_df: pd.DataFrame) -> dict[str, float]:
        """从完整结果表计算收益、风险、成本和交易约束统计指标。"""
        if result_df.empty:
            return {}

        month_span = calculate_month_span(result_df.index)
        total_return = float(result_df["equity"].iloc[-1] - 1.0)
        max_drawdown = float(abs(result_df["drawdown"].min()))
        metrics: dict[str, float] = {
            "month_num": month_span,
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "avg_daily_turnover": float(result_df["turnover"].mean()),
            "total_transaction_cost": float(result_df["transaction_cost"].sum()),
        }
        if {"blocked_buy_weight", "blocked_sell_weight", "cash_weight"}.issubset(result_df.columns):
            blocked = result_df[["blocked_buy_weight", "blocked_sell_weight"]]
            metrics.update(
                {
                    "total_blocked_buy_weight": float(result_df["blocked_buy_weight"].sum()),
                    "total_blocked_sell_weight": float(result_df["blocked_sell_weight"].sum()),
                    "max_cash_weight": float(result_df["cash_weight"].max()),
                    "blocked_trade_days": float(blocked.sum(axis=1).gt(0).sum()),
                }
            )

        if month_span > 0:
            ann_return = (
                -1.0
                if total_return <= -1.0
                else float((1.0 + total_return) ** (12.0 / month_span) - 1.0)
            )
            metrics["ann_return"] = ann_return
            metrics["calmar_ratio"] = (
                ann_return / max_drawdown
                if max_drawdown > 0
                else (np.inf if ann_return > 0 else 0.0)
            )

            annual_factor = np.sqrt(len(result_df) / month_span * 12.0)
            ann_volatility = float(result_df["return"].std() * annual_factor)
            metrics["ann_volatility"] = ann_volatility
            metrics["sharpe_ratio"] = ann_return / ann_volatility if ann_volatility > 0 else 0.0

            downside = result_df["return"].where(result_df["return"] < 0, 0.0)
            downside_risk = float(downside.std() * annual_factor)
            metrics["sortino_ratio"] = ann_return / downside_risk if downside_risk > 0 else 0.0
        else:
            metrics["ann_return"] = 0.0
            metrics["calmar_ratio"] = 0.0
            metrics["ann_volatility"] = 0.0
            metrics["sharpe_ratio"] = 0.0
            metrics["sortino_ratio"] = 0.0

        return metrics

    def run(self, weights_df: pd.DataFrame) -> BacktestResult:
        """执行完整回测，并返回执行权重、逐日结果和汇总指标。

        Args:
            weights_df: 策略生成的目标权重，即本回测器接收的交易信号。
                行索引为日期，列为标的；权重变化代表调仓指令。

        Returns:
            ``BacktestResult``。其中 ``executed_weights`` 保存延迟和交易约束
            处理后的真实交易/持仓信号，``result_df`` 保存逐日回测结果。
        """
        if weights_df.empty:
            raise ValueError("weights_df cannot be empty.")
        # 原始交易信号只在本次调用中使用；self.data 始终只保存行情数据。
        weights = weights_df.sort_index().astype(float)
        executed_weights = self._build_executed_weights(weights)
        result_df = self.build_result_frame(executed_weights)
        metrics = self.calculate_metrics(result_df)
        return BacktestResult(
            executed_weights=executed_weights,
            result_df=result_df,
            metrics=metrics,
        )


__all__ = [
    "BacktestResult",
    "VectorBacktester",
    "activity_metrics",
    "annual_return_metrics",
    "benchmark_return_corr",
    "bp_to_rate",
    "calculate_month_span",
]
