"""Live run of the 18-ETF asset-class rotation at 14:50: compute targets, push the signal.

Run by ``qs live-trade serve`` at 14:51 (retried at 14:53 and 14:55) or by hand::

    uv run python -m strategies.cross_sectional.workflows.live_asset_class_rotation
    uv run python -m strategies.cross_sectional.workflows.live_asset_class_rotation --write --capital 100000

The signal and the trade use the 14:50 price as today's close
(:mod:`skills.live_trade.daily`): PandaData backward-adjusted closes up to yesterday, the
same series as the ``1d_adj`` research data, plus today's Sina 14:50 price times today's
factor. Target units use unadjusted prices. With ``--write`` the closes are kept under
``<data_root>/live/<strategy>/market/``; research data under ``data/market/`` is never
touched. The matching backtest trades at the signal day's close (``trade_at="close"``,
``signal_lag=0``).
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pandas as pd

from skills.live_trade.daily import load_daily_bars
from skills.live_trade.runner import LiveInputs
from skills.live_trade.workflow import daily_main
from strategies.cross_sectional.asset_class_rotation import (
    ASSET_CLASS_ETF_SYMBOLS,
    asset_class_top3_weights,
)

STRATEGY_ID = "asset_class_rotation"
# First bar loaded and the anchor of the 20-day rebalance count. Keep it fixed: moving it
# moves every rebalance date. A backtest that should match live signals uses the same date.
HISTORY_START = "2019-01-02"


def target_weights(close: pd.DataFrame) -> pd.DataFrame:
    """The strategy's target weights; the backtest and live runs both call this."""
    return asset_class_top3_weights(
        close.reindex(columns=list(ASSET_CLASS_ETF_SYMBOLS)),
        rebalance_start=HISTORY_START,
    )


def load_inputs(client, trade_date: date, market_dir: Path | None = None) -> LiveInputs:
    """History up to yesterday plus today's 14:50 prices, and the weights on them."""
    closes = load_daily_bars(
        client, list(ASSET_CLASS_ETF_SYMBOLS), HISTORY_START, trade_date, asset="fund"
    )
    if market_dir is not None:
        market_dir.mkdir(parents=True, exist_ok=True)
        closes.close.to_parquet(market_dir / "close_post.parquet")
        closes.raw_close.to_parquet(market_dir / "close_raw.parquet")
    return closes.inputs(target_weights(closes.close))


def main(argv: Sequence[str] | None = None) -> int:
    return daily_main(STRATEGY_ID, load_inputs, argv)


if __name__ == "__main__":
    sys.exit(main())
