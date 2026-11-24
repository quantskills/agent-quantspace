"""Live daily MA-gap reversal on six large-cap stocks, at 14:50: push the signal to IM.

An example of a daily stock strategy going live. The target function is the backtest's
``ma_gap_reversal_weights``: every five trading days, hold the two stocks furthest below
their 120-day average, weighted by inverse 60-day volatility. The run happens at 14:51
(retried at 14:53 and 14:55) on backward-adjusted closes: PandaData up to yesterday, today
the 14:50 price times today's factor (:mod:`skills.live_trade.daily`). Target units use
unadjusted prices and 100-share lots::

    uv run python -m strategies.cross_sectional.workflows.live_stock_ma_gap_1d
    uv run python -m strategies.cross_sectional.workflows.live_stock_ma_gap_1d --write --capital 1000000

Stocks are never ordered automatically; the signal goes to the IM groups. The five-day
rebalance count starts at ``HISTORY_START``, so the matching backtest uses the same start
and fills at the signal day's close (``trade_at="close", signal_lag=0``).
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
from strategies.cross_sectional.rules import ma_gap_reversal_weights

STRATEGY_ID = "stock_ma_gap_1d"
# Kweichow Moutai, Wuliangye, Ping An, China Merchants Bank, Midea, Yangtze Power.
SYMBOLS = ("600519.SH", "000858.SZ", "601318.SH", "600036.SH", "000333.SZ", "600900.SH")
# Fixed: the five-day rebalance count starts at the first row.
HISTORY_START = "2021-01-04"
LOOKBACK, TOP_N, VOL_LOOKBACK, REBALANCE_DAYS = 120, 2, 60, 5


def target_weights(close: pd.DataFrame) -> pd.DataFrame:
    """The strategy's target weights; the backtest and live runs both call this."""
    return ma_gap_reversal_weights(
        close.reindex(columns=list(SYMBOLS)),
        list(SYMBOLS),
        lookback=LOOKBACK,
        top_n=TOP_N,
        vol_lookback=VOL_LOOKBACK,
        rebalance_days=REBALANCE_DAYS,
    )


def load_inputs(client, trade_date: date, market_dir: Path | None = None) -> LiveInputs:
    """Adjusted closes up to yesterday plus today's 14:50 prices, and the weights on them."""
    bars = load_daily_bars(client, list(SYMBOLS), HISTORY_START, trade_date, asset="stock")
    if market_dir is not None:
        market_dir.mkdir(parents=True, exist_ok=True)
        bars.panel.to_parquet(market_dir / "bars_post.parquet")
        bars.raw_panel.to_parquet(market_dir / "bars_raw.parquet")
    return bars.inputs(target_weights(bars.close))


def main(argv: Sequence[str] | None = None) -> int:
    return daily_main(STRATEGY_ID, load_inputs, argv)


if __name__ == "__main__":
    sys.exit(main())
