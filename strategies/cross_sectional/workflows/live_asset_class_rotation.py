"""Live run of the 18-ETF asset-class rotation: refresh data, compute targets, push the signal.

Run by ``qs live-trade serve`` or by hand::

    uv run python -m strategies.cross_sectional.workflows.live_asset_class_rotation --date 2026-11-20
    uv run python -m strategies.cross_sectional.workflows.live_asset_class_rotation --write --capital 100000

Signals use backward-adjusted closes (the same series as the ``1d_adj`` research data);
target units use unadjusted closes. Each run downloads the whole history again into
``<data_root>/live/<strategy>/market/`` so research data under ``data/market/`` is never
touched, and adjustment changes never leave a seam in the history.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pandas as pd

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


def _closes(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError("PandaData returned no fund bars")
    table = frame.assign(eob=pd.to_datetime(frame["date"].astype(str), format="%Y%m%d"))
    close = table.pivot_table(index="eob", columns="symbol", values="close", aggfunc="last")
    return close.sort_index().astype(float)


def target_weights(close: pd.DataFrame) -> pd.DataFrame:
    """The strategy's target weights; the backtest and live runs both call this."""
    return asset_class_top3_weights(
        close.reindex(columns=list(ASSET_CLASS_ETF_SYMBOLS)),
        rebalance_start=HISTORY_START,
    )


def load_inputs(client, trade_date: date, market_dir: Path | None = None) -> LiveInputs:
    """Download history up to ``trade_date`` and build weights and reference prices."""
    symbols = list(ASSET_CLASS_ETF_SYMBOLS)
    start, end = HISTORY_START.replace("-", ""), trade_date.strftime("%Y%m%d")
    adjusted = _closes(client.get_fund_daily_post(start, end, symbol=symbols))
    raw = _closes(client.get_fund_daily(start, end, symbol=symbols))
    if market_dir is not None:
        market_dir.mkdir(parents=True, exist_ok=True)
        adjusted.to_parquet(market_dir / "close_post.parquet")
        raw.to_parquet(market_dir / "close_raw.parquet")
    return LiveInputs(weights=target_weights(adjusted), prices=raw)


def main(argv: Sequence[str] | None = None) -> int:
    return daily_main(STRATEGY_ID, load_inputs, argv)


if __name__ == "__main__":
    sys.exit(main())
