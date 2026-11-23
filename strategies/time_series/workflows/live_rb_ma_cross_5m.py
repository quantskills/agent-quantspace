"""Live 5-minute MA cross on rebar's dominant contract: push each signal to the IM groups.

The target function is the backtest's ``ma_golden_death_cross_weights`` on
``RB_DOMINANT.SHF`` 5-minute bars: long while the 12-bar MA is above the 48-bar MA, flat
otherwise. History comes from PandaData; during the session today's bars come from Sina
through AKShare. Run by ``qs live-trade serve`` (``frequency: "5m"``) or by hand::

    uv run python -m strategies.time_series.workflows.live_rb_ma_cross_5m --refresh
    uv run python -m strategies.time_series.workflows.live_rb_ma_cross_5m --bar 2026-11-23T09:05:00
    uv run python -m strategies.time_series.workflows.live_rb_ma_cross_5m --test

Add ``--write`` to push and log; without it every run only previews. With ``--write``,
``--capital`` and ``--account <SimNow account>`` each bar also trades the target through
the PandaAI client (SimNow accounts only)::

    uv run python -m strategies.time_series.workflows.live_rb_ma_cross_5m \
        --bar 2026-11-23T09:05:00 --write --capital 100000 --account <code>
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

import pandas as pd

from skills.live_trade.spec import Instrument, LiveSpec
from skills.live_trade.workflow import minute_main
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


def main(argv: Sequence[str] | None = None) -> int:
    return minute_main(SPEC, target_weights, argv)


if __name__ == "__main__":
    sys.exit(main())
