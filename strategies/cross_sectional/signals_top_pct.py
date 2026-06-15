"""Top-percent cross-sectional selection strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .signals_base import BaseStrategy, StrategyContext, StrategyResult


def _wide_to_long(frame: pd.DataFrame, target_index: pd.MultiIndex) -> pd.Series:
    """Convert a date x symbol frame back to the repository's MultiIndex order."""
    long_index = pd.MultiIndex.from_product(
        [frame.columns, frame.index],
        names=["symbol", "eob"],
    )
    values = frame.transpose().to_numpy().reshape(-1)
    return pd.Series(values, index=long_index).reindex(target_index)


class TopPctStrategy(BaseStrategy):
    """Replicate the legacy top-pct vote-and-weight strategy in modular form."""

    def generate(
        self,
        factor_df: pd.DataFrame,
        factor_pivots: dict[str, pd.DataFrame],
        context: StrategyContext,
    ) -> StrategyResult:
        votes_df = self._calculate_votes(factor_pivots, context)
        selected_df = votes_df > 0
        base_weights = self._calculate_weights(votes_df, context)
        signal_weights = self._apply_portfolio_overlays(base_weights, context)

        signal_df = factor_df.copy()
        signal_df["strategy__vote_count"] = _wide_to_long(votes_df, signal_df.index).astype(int)
        signal_df["strategy__selected"] = _wide_to_long(selected_df, signal_df.index).fillna(False)
        signal_df["strategy__signal"] = (
            _wide_to_long(
                signal_weights.gt(0).astype(int),
                signal_df.index,
            )
            .fillna(0)
            .astype(int)
        )
        signal_df["strategy__target_weight"] = _wide_to_long(
            signal_weights,
            signal_df.index,
        ).fillna(0.0)

        return StrategyResult(
            signal_df=signal_df,
            signal_weights=signal_weights,
            votes_df=votes_df,
        )

    def _calculate_votes(
        self,
        factor_pivots: dict[str, pd.DataFrame],
        context: StrategyContext,
    ) -> pd.DataFrame:
        direction_map = {
            config.get("name", config["func"].__name__): config.get("direction", 1)
            for config in context.factor_configs
        }

        first_pivot = next(iter(factor_pivots.values()))
        votes_df = pd.DataFrame(0, index=first_pivot.index, columns=first_pivot.columns)

        for name, pivot in factor_pivots.items():
            aligned = pivot.reindex(index=votes_df.index, columns=votes_df.columns)
            valid_count = aligned.notna().sum(axis=1)
            n_select = (valid_count * context.top_pct).clip(lower=1).astype(int)
            ascending = direction_map.get(name, 1) == -1
            ranked = aligned.rank(axis=1, ascending=ascending, na_option="keep")
            selected = ranked.le(n_select, axis=0) & aligned.notna()
            votes_df = votes_df.add(selected.astype(int), fill_value=0).astype(int)

        return votes_df

    def _calculate_weights(self, votes_df: pd.DataFrame, context: StrategyContext) -> pd.DataFrame:
        if context.weight_method == "equal":
            row_sums = votes_df.sum(axis=1).replace(0, np.nan)
            return votes_df.div(row_sums, axis=0).fillna(0.0)

        from skills.backtest.weighting import WEIGHT_METHODS

        method_fn = WEIGHT_METHODS.get(context.weight_method)
        if method_fn is None:
            available = ", ".join(sorted(WEIGHT_METHODS))
            raise ValueError(
                f"Unknown weight_method: {context.weight_method}. Available: {available}"
            )

        common_cols = votes_df.columns.intersection(context.execution_returns.columns)
        return method_fn(
            votes_df[common_cols],
            returns_df=context.execution_returns[common_cols],
        ).fillna(0.0)

    def _compute_filter_pivot(self, data: pd.DataFrame, config: dict) -> pd.DataFrame:
        func = config["func"]
        kwargs = config.get("kwargs", {})
        factor_series = data.groupby(level="symbol", group_keys=False).apply(
            lambda group, _func=func, _kwargs=kwargs: _func(group, **_kwargs)
        )
        return factor_series.unstack(level="symbol")

    def _apply_exit_filters(
        self,
        weights_df: pd.DataFrame,
        context: StrategyContext,
    ) -> pd.DataFrame:
        filtered = weights_df.copy()
        for config in context.exit_filters:
            condition = config.get("condition", lambda values: values >= 0)
            pivot = self._compute_filter_pivot(context.data, config).reindex_like(filtered)
            filtered = filtered.where(condition(pivot), 0.0)

        if context.exposure_policy == "keep_cash":
            return filtered
        if context.exposure_policy == "renormalize":
            row_sums = filtered.sum(axis=1).replace(0, np.nan)
            return filtered.div(row_sums, axis=0).fillna(0.0)
        if context.exposure_policy == "allocate_defensive":
            return self._allocate_to_defensive(filtered, context)
        raise ValueError(
            "exposure_policy must be one of 'keep_cash', 'renormalize', 'allocate_defensive'."
        )

    def _allocate_to_defensive(
        self,
        filtered_weights: pd.DataFrame,
        context: StrategyContext,
    ) -> pd.DataFrame:
        result = filtered_weights.copy()
        spare_weight = (1.0 - filtered_weights.sum(axis=1)).clip(lower=0.0)

        if context.defensive_symbols:
            available = [symbol for symbol in context.defensive_symbols if symbol in result.columns]
            if not available:
                raise ValueError("No defensive_symbols are present in the weight matrix columns.")
            for symbol in available:
                result[symbol] = result[symbol] + spare_weight / len(available)
            return result

        vol = context.execution_returns.rolling(60, min_periods=20).std().reindex_like(result)
        held_mask = result > 0
        chosen_symbol = vol.where(held_mask, np.inf).idxmin(axis=1)

        for symbol in result.columns:
            symbol_mask = (chosen_symbol == symbol) & (spare_weight > 0.0)
            result.loc[symbol_mask, symbol] += spare_weight[symbol_mask]

        return result

    def _apply_rebalance_freq(self, weights_df: pd.DataFrame, rebalance_freq: int) -> pd.DataFrame:
        rebalance_dates = set(weights_df.index[::rebalance_freq])
        sampled = weights_df.copy()
        sampled.loc[~sampled.index.isin(rebalance_dates)] = np.nan
        return sampled.ffill().fillna(0.0)

    def _apply_vol_target(
        self,
        weights_df: pd.DataFrame,
        context: StrategyContext,
        lookback: int = 60,
    ) -> pd.DataFrame:
        common_cols = weights_df.columns.intersection(context.execution_returns.columns)
        common_dates = weights_df.index.intersection(context.execution_returns.index)
        aligned_weights = weights_df.loc[common_dates, common_cols]
        aligned_returns = context.execution_returns.loc[common_dates, common_cols]

        portfolio_returns = (aligned_weights.shift(context.signal_lag) * aligned_returns).sum(
            axis=1
        )
        realized_vol = portfolio_returns.rolling(lookback, min_periods=20).std() * np.sqrt(252)
        scale = (context.vol_target / realized_vol.replace(0, np.nan)).clip(upper=1.0).fillna(1.0)
        return weights_df.mul(scale.reindex(weights_df.index, fill_value=1.0), axis=0)

    def _apply_portfolio_overlays(
        self,
        weights_df: pd.DataFrame,
        context: StrategyContext,
    ) -> pd.DataFrame:
        overlaid = weights_df.copy()
        if context.exit_filters:
            overlaid = self._apply_exit_filters(overlaid, context)
        if context.rebalance_freq > 1:
            overlaid = self._apply_rebalance_freq(overlaid, context.rebalance_freq)
        if context.vol_target is not None:
            overlaid = self._apply_vol_target(overlaid, context)
        return overlaid
