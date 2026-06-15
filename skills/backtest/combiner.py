"""
Multi-Strategy Combiner Module

Combines multiple sub-strategy return streams into a single portfolio.
Supports:
- Equal weight combination
- Risk-parity weighted combination
- Custom weight combination

Reference: Huaxin Research Report - Core-Satellite 885001 Enhancement
"""

import numpy as np
import pandas as pd


class StrategyCombiner:
    """
    Combine multiple strategy return streams.

    Parameters
    ----------
    strategies : dict
        {name: pd.Series} mapping strategy names to daily return series
    method : str
        Combination method: 'equal', 'risk_parity', 'custom'
    custom_weights : dict, optional
        {name: weight} for 'custom' method
    lookback : int
        Rolling window for risk_parity vol estimation
    """

    def __init__(
        self,
        strategies: dict[str, pd.Series],
        method: str = "equal",
        custom_weights: dict[str, float] = None,
        lookback: int = 60,
    ):
        self.strategies = strategies
        self.method = method
        self.custom_weights = custom_weights or {}
        self.lookback = lookback
        self.result_df = None
        self.metrics = None

    def run(self) -> pd.DataFrame:
        """
        Combine strategies and compute portfolio metrics.

        Returns
        -------
        pd.DataFrame with columns: each strategy return, combined_return,
                                     cum_combined, drawdown
        """
        # Align all return series
        ret_df = pd.DataFrame(self.strategies)
        ret_df = ret_df.dropna(how="all")

        # Calculate weights
        if self.method == "equal":
            n = len(self.strategies)
            weights = dict.fromkeys(self.strategies, 1.0 / n)
            print(f"Equal weight: {n} strategies, {1 / n:.2%} each")

        elif self.method == "custom":
            weights = self.custom_weights
            total = sum(weights.values())
            weights = {k: v / total for k, v in weights.items()}
            print(f"Custom weights: {weights}")

        elif self.method == "risk_parity":
            weights = self._compute_risk_parity_weights(ret_df)
            print(f"Risk parity weights: { {k: f'{v:.2%}' for k, v in weights.items()} }")

        else:
            raise ValueError(f"Unknown method: {self.method}")

        # Combine
        combined = sum(ret_df[name] * w for name, w in weights.items())

        # Build result
        result = ret_df.copy()
        result["combined_return"] = combined
        result["cum_combined"] = combined.cumsum()
        cum_max = result["cum_combined"].cummax()
        result["drawdown"] = result["cum_combined"] - cum_max

        # Add individual cumulative returns
        for name in self.strategies:
            result[f"cum_{name}"] = ret_df[name].cumsum()

        self.result_df = result
        self._calculate_metrics(weights)
        self._print_metrics()

        return result

    def _compute_risk_parity_weights(self, ret_df: pd.DataFrame) -> dict[str, float]:
        """Inverse-vol weights using recent data."""
        vol = ret_df.iloc[-self.lookback :].std() * np.sqrt(252)
        inv_vol = 1.0 / vol.replace(0, np.nan)
        inv_vol = inv_vol.fillna(0)
        total = inv_vol.sum()
        if total == 0:
            n = len(ret_df.columns)
            return dict.fromkeys(ret_df.columns, 1.0 / n)
        return {name: inv_vol[name] / total for name in ret_df.columns}

    def _calculate_metrics(self, weights: dict[str, float]):
        """Compute combined portfolio metrics."""
        df = self.result_df
        ret = df["combined_return"]
        n_days = len(ret)
        n_years = n_days / 252

        self.metrics = {
            "total_return": df["cum_combined"].iloc[-1],
            "annualized_return": df["cum_combined"].iloc[-1] / n_years if n_years > 0 else 0,
            "volatility": ret.std() * np.sqrt(252),
            "sharpe_ratio": (ret.mean() / ret.std() * np.sqrt(252)) if ret.std() > 0 else 0,
            "max_drawdown": abs(df["drawdown"].min()),
            "calmar_ratio": (df["cum_combined"].iloc[-1] / n_years / abs(df["drawdown"].min()))
            if df["drawdown"].min() != 0
            else 0,
            "weights": weights,
        }

        # Per-strategy metrics
        for name in self.strategies:
            cum = df[f"cum_{name}"].iloc[-1]
            self.metrics[f"{name}_return"] = cum

    def _print_metrics(self):
        m = self.metrics
        print(f"\n{'=' * 60}")
        print("  Combined Portfolio Summary")
        print(f"{'=' * 60}")
        print(f"  Total Return:     {m['total_return']:.2%}")
        print(f"  Annual Return:    {m['annualized_return']:.2%}")
        print(f"  Volatility:       {m['volatility']:.2%}")
        print(f"  Sharpe Ratio:     {m['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown:     {m['max_drawdown']:.2%}")
        print(f"  Calmar Ratio:     {m['calmar_ratio']:.2f}")
        print("\n  Sub-strategy Returns:")
        for name in self.strategies:
            print(f"    {name}: {m[f'{name}_return']:.2%}")
        print(f"{'=' * 60}")
