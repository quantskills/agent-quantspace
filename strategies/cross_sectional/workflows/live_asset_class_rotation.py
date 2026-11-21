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

import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pandas as pd

from skills.live_trade.runner import LiveInputs, run_live
from skills.live_trade.scheduler import workflow_arguments
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


def is_trading_day(client, day: date) -> bool:
    stamp = day.strftime("%Y%m%d")
    calendar = client.get_trade_cal(stamp, stamp)
    if calendar is None or calendar.empty:
        raise ValueError(f"PandaData has no trading calendar for {day}")
    return bool(int(calendar["is_trade"].iloc[0]))


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


def _login_expired(exc: BaseException) -> bool:
    while exc is not None:
        if "init_token" in str(exc) or "登录已过期" in str(exc):
            return True
        exc = exc.__cause__
    return False


def load_with_relogin(make_client, trade_date: date, market_dir: Path | None = None) -> LiveInputs:
    """``load_inputs`` with one retry on a fresh login when PandaData drops the session."""
    try:
        return load_inputs(make_client(), trade_date, market_dir)
    except Exception as exc:
        if not _login_expired(exc):
            raise
        return load_inputs(make_client(), trade_date, market_dir)


def main(argv: Sequence[str] | None = None) -> int:
    from skills.ingest import PandaDataClient
    from skills.store.workspace import resolve_workspace_paths

    args = workflow_arguments(argv)
    client = PandaDataClient()
    root = resolve_workspace_paths(data_root=args.data_root).data_root
    market_dir = root / "live" / STRATEGY_ID / "market" if args.write else None
    try:
        trading = is_trading_day(client, args.date)
    except Exception as exc:  # noqa: BLE001 - reported as a run error below
        trading, calendar_error = True, exc
    else:
        calendar_error = None

    def load() -> LiveInputs:
        if calendar_error is not None:
            raise calendar_error
        return load_with_relogin(PandaDataClient, args.date, market_dir)

    outcome = run_live(
        STRATEGY_ID,
        load,
        trade_date=args.date,
        is_trading_day=trading,
        write=args.write,
        final=args.final,
        capital=args.capital,
        lot_size=args.lot_size,
        data_root=args.data_root,
    )
    delivery = outcome.delivery
    report = {
        "strategy_id": outcome.strategy_id,
        "trade_date": outcome.trade_date,
        "status": outcome.status,
        "detail": outcome.detail,
        "signal_id": delivery.signal.signal_id if delivery else None,
        "target": delivery.signal.target if delivery else None,
        "message": f"{delivery.title}\n{delivery.body}" if delivery else None,
        "deliveries": [vars(item) for item in delivery.results] if delivery else [],
        "alerts": [vars(item) for item in outcome.alerts],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
