"""Public large-asset ETF/LOF momentum rotation strategy."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from skills.compute.adjust import forward_adjust
from skills.strategy.cross_sectional import top_n_weights

ASSET_CLASS_ETF_UNIVERSE = {
    "gold": "SHSE.518880",
    "crude_oil": "SHSE.501018",
    "china_government_bond": "SHSE.511130",
    "csi_300": "SHSE.510300",
    "csi_2000": "SHSE.563300",
    "chi_next": "SZSE.159915",
    "star_50": "SHSE.588000",
    "hang_seng": "SZSE.159920",
    "hang_seng_internet": "SHSE.513330",
    "nasdaq_100": "SHSE.513100",
    "sp_500": "SHSE.513500",
    "nikkei_225": "SHSE.513520",
    "dax": "SHSE.513030",
    "cac_40": "SHSE.513080",
    "india_equity": "SZSE.164824",
    "soybean_meal": "SZSE.159985",
    "nonferrous_metals": "SZSE.159980",
    "broad_commodity": "SHSE.510170",
}

ASSET_CLASS_ETF_SYMBOLS = tuple(ASSET_CLASS_ETF_UNIVERSE.values())
DEFAULT_MOMENTUM_LOOKBACKS = (20, 60, 120)
DEFAULT_REBALANCE_DAYS = 20
DEFAULT_TOP_N = 3

# Publicly disclosed ETF share splits. Raw PandaData bars retain the pre-split
# price scale through the suspended split date, so reports apply these events
# before computing either signals or execution returns.
ASSET_CLASS_SPLIT_EVENTS = {
    "SHSE.513100": (("2022-01-13", 5.0),),
    "SHSE.513500": (("2022-03-29", 2.0),),
    "SHSE.510170": (("2022-07-08", 4.0),),
}


def apply_asset_class_split_adjustments(panel: pd.DataFrame) -> pd.DataFrame:
    """Forward-adjust known public ETF splits in a ``(symbol, eob)`` panel."""
    if not isinstance(panel.index, pd.MultiIndex) or panel.index.names != ["symbol", "eob"]:
        raise ValueError("panel index must be MultiIndex (symbol, eob)")

    frames = []
    for symbol, grouped in panel.groupby(level="symbol", sort=False):
        bars = grouped.droplevel("symbol").copy()
        events = ASSET_CLASS_SPLIT_EVENTS.get(str(symbol), ())
        if events:
            cumulative = 1.0
            rows = []
            for ex_date, split_ratio in events:
                cumulative *= split_ratio
                rows.append(
                    {
                        "ex_date": pd.Timestamp(ex_date),
                        "ex_cum_factor": cumulative,
                        "ex_factor": split_ratio,
                    }
                )
            factors = pd.DataFrame(rows).set_index("ex_date")
            bars = forward_adjust(bars, factors)
        bars["symbol"] = symbol
        frames.append(bars.reset_index().set_index(["symbol", "eob"]))
    return pd.concat(frames).sort_index()


def _validated_prices(close: pd.DataFrame, symbols: Sequence[str]) -> pd.DataFrame:
    requested = list(symbols)
    if not requested:
        raise ValueError("symbols cannot be empty")
    if len(requested) != len(set(requested)):
        raise ValueError("symbols cannot contain duplicates")
    missing = sorted(set(requested).difference(close.columns))
    if missing:
        raise ValueError(f"close is missing configured symbols: {missing}")
    return close.loc[:, requested].astype(float)


def asset_class_momentum_score(
    close: pd.DataFrame,
    *,
    symbols: Sequence[str] = ASSET_CLASS_ETF_SYMBOLS,
    lookbacks: Sequence[int] = DEFAULT_MOMENTUM_LOOKBACKS,
) -> pd.DataFrame:
    """Average trailing returns across several horizons; higher is stronger."""
    prices = _validated_prices(close, symbols)
    horizons = tuple(int(lookback) for lookback in lookbacks)
    if not horizons or any(lookback <= 0 for lookback in horizons):
        raise ValueError("lookbacks must contain positive integers")
    if len(horizons) != len(set(horizons)):
        raise ValueError("lookbacks cannot contain duplicates")

    components = [prices.pct_change(lookback, fill_method=None) for lookback in horizons]
    score = sum(components) / float(len(components))
    return score.replace([np.inf, -np.inf], np.nan)


def asset_class_top3_weights(
    close: pd.DataFrame,
    *,
    symbols: Sequence[str] = ASSET_CLASS_ETF_SYMBOLS,
    lookbacks: Sequence[int] = DEFAULT_MOMENTUM_LOOKBACKS,
    top_n: int = DEFAULT_TOP_N,
    rebalance_days: int = DEFAULT_REBALANCE_DAYS,
) -> pd.DataFrame:
    """Select the strongest three assets and hold them at equal target weights."""
    requested = list(symbols)
    if top_n <= 0 or top_n > len(requested):
        raise ValueError("top_n must be between 1 and the number of symbols")
    if rebalance_days <= 0:
        raise ValueError("rebalance_days must be positive")

    score = asset_class_momentum_score(close, symbols=requested, lookbacks=lookbacks)
    weights = top_n_weights(score, top_n=top_n)
    if rebalance_days > 1:
        rebalance_dates = set(weights.index[::rebalance_days])
        sampled = weights.copy()
        sampled.loc[~sampled.index.isin(rebalance_dates)] = np.nan
        weights = sampled.ffill().fillna(0.0)
    return weights.reindex(columns=requested).fillna(0.0)


__all__ = [
    "ASSET_CLASS_ETF_SYMBOLS",
    "ASSET_CLASS_ETF_UNIVERSE",
    "ASSET_CLASS_SPLIT_EVENTS",
    "DEFAULT_MOMENTUM_LOOKBACKS",
    "DEFAULT_REBALANCE_DAYS",
    "DEFAULT_TOP_N",
    "apply_asset_class_split_adjustments",
    "asset_class_momentum_score",
    "asset_class_top3_weights",
]
