from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.cross_sectional.asset_class_rotation import (
    ASSET_CLASS_ETF_UNIVERSE,
    ASSET_CLASS_SPLIT_EVENTS,
    apply_asset_class_split_adjustments,
    asset_class_momentum_score,
    asset_class_top3_weights,
)


def _trend_frame(periods: int = 12) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=periods, name="eob")
    steps = np.arange(periods, dtype=float)
    return pd.DataFrame(
        {
            "A": 100.0 * np.power(1.04, steps),
            "B": 100.0 * np.power(1.03, steps),
            "C": 100.0 * np.power(1.02, steps),
            "D": 100.0 * np.power(1.01, steps),
        },
        index=index,
    )


def test_public_asset_class_universe_contains_requested_eighteen_proxies() -> None:
    assert len(ASSET_CLASS_ETF_UNIVERSE) == 18
    assert set(ASSET_CLASS_ETF_UNIVERSE) == {
        "gold",
        "crude_oil",
        "china_government_bond",
        "csi_300",
        "csi_2000",
        "chi_next",
        "star_50",
        "hang_seng",
        "hang_seng_internet",
        "nasdaq_100",
        "sp_500",
        "nikkei_225",
        "dax",
        "cac_40",
        "india_equity",
        "soybean_meal",
        "nonferrous_metals",
        "broad_commodity",
    }
    assert len(set(ASSET_CLASS_ETF_UNIVERSE.values())) == 18


def test_asset_class_momentum_score_ranks_stronger_trends_higher() -> None:
    close = _trend_frame()

    score = asset_class_momentum_score(
        close,
        symbols=["A", "B", "C", "D"],
        lookbacks=(2, 4, 6),
    )

    assert score.iloc[-1].sort_values(ascending=False).index.tolist() == ["A", "B", "C", "D"]


def test_asset_class_top3_weights_selects_three_equal_weight_assets() -> None:
    close = _trend_frame()

    weights = asset_class_top3_weights(
        close,
        symbols=["A", "B", "C", "D"],
        lookbacks=(2, 4, 6),
        rebalance_days=1,
    )

    assert weights.iloc[-1].to_dict() == pytest.approx(
        {"A": 1.0 / 3.0, "B": 1.0 / 3.0, "C": 1.0 / 3.0, "D": 0.0}
    )
    assert weights.iloc[-1].sum() == pytest.approx(1.0)


def test_asset_class_top3_weights_rejects_missing_configured_symbols() -> None:
    with pytest.raises(ValueError, match="missing configured symbols"):
        asset_class_top3_weights(
            _trend_frame()[["A", "B", "C"]],
            symbols=["A", "B", "C", "D"],
            lookbacks=(2, 4, 6),
        )


@pytest.mark.parametrize("symbol", list(ASSET_CLASS_SPLIT_EVENTS))
def test_public_split_events_remove_raw_price_scale_breaks(symbol: str) -> None:
    ex_date_text, split_ratio = ASSET_CLASS_SPLIT_EVENTS[symbol][0]
    ex_date = pd.Timestamp(ex_date_text)
    dates = pd.DatetimeIndex(
        [ex_date - pd.offsets.BDay(), ex_date, ex_date + pd.offsets.BDay()],
        name="eob",
    )
    raw = (
        pd.DataFrame(
            {
                "open": [split_ratio, split_ratio, 1.01],
                "high": [split_ratio, split_ratio, 1.01],
                "low": [split_ratio, split_ratio, 1.01],
                "close": [split_ratio, split_ratio, 1.01],
                "volume": [100.0, 0.0, 100.0 * split_ratio],
                "symbol": symbol,
            },
            index=dates,
        )
        .reset_index()
        .set_index(["symbol", "eob"])
    )

    adjusted = apply_asset_class_split_adjustments(raw).xs(symbol, level="symbol")

    assert adjusted["close"].tolist() == pytest.approx([1.0, 1.0, 1.01])
    assert adjusted["close"].pct_change().abs().max() < 0.02


def _random_walk_frame(rows: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    index = pd.bdate_range("2024-01-01", periods=rows, name="eob")
    returns = rng.normal(0.0, 0.01, size=(rows, 5))
    return pd.DataFrame(
        100.0 * np.exp(np.cumsum(returns, axis=0)), index=index, columns=list("ABCDE")
    )


def test_live_prefix_weights_match_full_history_with_a_fixed_anchor() -> None:
    """A live run sees only bars up to its day; its last row must equal the full run's row."""
    close = _random_walk_frame()
    options = {
        "symbols": list("ABCDE"),
        "lookbacks": (5, 10, 20),
        "top_n": 2,
        "rebalance_days": 7,
        "rebalance_start": close.index[0],
    }
    full = asset_class_top3_weights(close, **options)

    for end in range(25, len(close)):
        prefix = asset_class_top3_weights(close.iloc[: end + 1], **options)
        pd.testing.assert_series_equal(prefix.iloc[-1], full.iloc[end], check_names=False)


def test_rebalance_dates_follow_the_anchor_not_the_first_loaded_row() -> None:
    close = _random_walk_frame()
    options = {
        "symbols": list("ABCDE"),
        "lookbacks": (5, 10, 20),
        "top_n": 2,
        "rebalance_days": 7,
        "rebalance_start": close.index[30],
    }
    full = asset_class_top3_weights(close, **options)
    later_start = asset_class_top3_weights(close.iloc[3:], **options)

    pd.testing.assert_frame_equal(later_start.loc[close.index[60] :], full.loc[close.index[60] :])
