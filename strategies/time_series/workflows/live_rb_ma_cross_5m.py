"""Live 5-minute MA cross on rebar's dominant contract: push each signal to the IM groups.

The target function is the backtest's ``ma_golden_death_cross_weights`` on
``RB_DOMINANT.SHF`` 5-minute bars: long while the 12-bar MA is above the 48-bar MA, flat
otherwise. History comes from PandaData; during the session today's bars come from Sina
through AKShare. Run by ``qs live-trade serve`` (``frequency: "5m"``) or by hand::

    uv run python -m strategies.time_series.workflows.live_rb_ma_cross_5m --refresh
    uv run python -m strategies.time_series.workflows.live_rb_ma_cross_5m --bar 2026-11-23T09:05:00
    uv run python -m strategies.time_series.workflows.live_rb_ma_cross_5m --test

Add ``--write`` to push and log; without it every run only previews.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence

import pandas as pd

from skills.live_trade.minute import refresh_day, run_bar
from skills.live_trade.runner import LiveInputs, run_live
from skills.live_trade.scheduler import workflow_arguments
from skills.live_trade.spec import Instrument, LiveSpec
from strategies.time_series.rules import ma_golden_death_cross_weights

STRATEGY_ID = "rb_ma_cross_5m"
SYMBOL = "RB_DOMINANT.SHF"
SHORT, LONG = 12, 48
SPEC = LiveSpec(
    strategy_id=STRATEGY_ID,
    frequency="5m",
    instruments=(Instrument(symbol=SYMBOL, asset="future"),),
    warmup_bars=LONG,
    adjust="none",
)


def target_weights(panel: pd.DataFrame) -> pd.DataFrame:
    """The strategy's target weights; the backtest and live runs both call this."""
    bars = panel.xs(SYMBOL, level="symbol").sort_index()
    return ma_golden_death_cross_weights(bars, SYMBOL, short=SHORT, long=LONG)


def _delivery(delivery) -> dict:
    if delivery is None:
        return {}
    return {
        "signal_id": delivery.signal.signal_id,
        "target": delivery.signal.target,
        "message": f"{delivery.title}\n{delivery.body}",
        "deliveries": [vars(item) for item in delivery.results],
    }


def main(argv: Sequence[str] | None = None) -> int:
    from skills.ingest import PandaDataClient
    from skills.live_trade.feeds import MinuteFeed

    args = workflow_arguments(argv)
    feed = MinuteFeed(SPEC, PandaDataClient(), data_root=args.data_root)
    if args.refresh:
        outcome = refresh_day(
            SPEC, feed, target_weights, now=args.now, write=args.write, data_root=args.data_root
        )
        state = outcome.report.state if outcome.report else None
        report = {
            "strategy_id": STRATEGY_ID,
            "trade_date": outcome.trade_date,
            "status": outcome.status,
            "detail": outcome.detail,
            "contracts": state.contracts if state else None,
            "bars_today": len(state.bar_ends) if state else None,
            "rows": outcome.report.rows if outcome.report else None,
            "mismatches": {day: len(items) for day, items in outcome.mismatches.items()},
            "alerts": [vars(item) for item in outcome.alerts],
        }
    elif args.test:

        def load() -> LiveInputs:
            state = feed.state()
            return LiveInputs(
                weights=target_weights(feed.panel()),
                prices=feed.raw_closes(),
                multipliers=state.multipliers,
            )

        outcome = run_live(
            STRATEGY_ID,
            load,
            trade_date=args.now.date(),
            is_trading_day=True,
            write=args.write,
            capital=args.capital,
            lot_size=args.lot_size,
            data_root=args.data_root,
            test=True,
        )
        report = {
            "strategy_id": STRATEGY_ID,
            "status": outcome.status,
            "detail": outcome.detail,
            **_delivery(outcome.delivery),
        }
    else:
        if args.bar is None:
            print("--bar, --refresh or --test is required", file=sys.stderr)
            return 2
        outcome = run_bar(
            SPEC,
            feed,
            target_weights,
            bar=args.bar,
            now=args.now,
            write=args.write,
            capital=args.capital,
            lot_size=args.lot_size,
            data_root=args.data_root,
        )
        report = {
            "strategy_id": STRATEGY_ID,
            "bar": outcome.trade_date,
            "status": outcome.status,
            "detail": outcome.detail,
            **_delivery(outcome.delivery),
            "alerts": [vars(item) for item in outcome.alerts],
        }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
