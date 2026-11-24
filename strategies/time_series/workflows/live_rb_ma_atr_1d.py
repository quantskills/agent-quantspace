"""Live daily MA reversion with an ATR trailing stop on rebar's dominant contract, at 14:50.

An example of a daily futures strategy going live. The target function is the backtest's
``ma_reversion_atr_stop_weights`` on ``RB_DOMINANT.SHF`` daily bars: long when the close
falls below its 10-day average, out when it drops two 14-day ATRs below the highest price
since entry. The run happens at 14:51 (retried at 14:53 and 14:55) and takes today's bar
from the 1-minute bars up to 14:50 (:mod:`skills.live_trade.daily`), so the stop sees
today's high and low too::

    uv run python -m strategies.time_series.workflows.live_rb_ma_atr_1d
    uv run python -m strategies.time_series.workflows.live_rb_ma_atr_1d \
        --write --capital 100000 --account <SimNow account code>

Without ``--write`` it only previews. With ``--write --capital --account`` it also trades
the dominant contract on that SimNow account through the PandaAI client. Prices are the
unadjusted dominant series, as the minute strategies use. The trailing stop depends on
every day since entry, so history always starts at ``HISTORY_START``; the matching
backtest uses the same start and fills at the signal day's close
(``trade_at="close", signal_lag=0``).
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pandas as pd

from skills.live_trade.daily import load_daily_bars
from skills.live_trade.runner import LiveInputs
from skills.live_trade.spec import Instrument
from skills.live_trade.workflow import daily_main
from strategies.time_series.rules import ma_reversion_atr_stop_weights

STRATEGY_ID = "rb_ma_atr_1d"
SYMBOL = "RB_DOMINANT.SHF"
# Fixed: the trailing stop carries state from the first bar on.
HISTORY_START = "2021-01-04"
MA_LOOKBACK, ATR_LOOKBACK, ATR_MULTIPLIER = 10, 14, 2.0


def target_weights(panel: pd.DataFrame) -> pd.DataFrame:
    """The strategy's target weights; the backtest and live runs both call this."""
    bars = panel.xs(SYMBOL, level="symbol").sort_index()
    return ma_reversion_atr_stop_weights(
        bars,
        SYMBOL,
        ma_lookback=MA_LOOKBACK,
        atr_lookback=ATR_LOOKBACK,
        atr_multiplier=ATR_MULTIPLIER,
    )


def load_inputs(client, trade_date: date, market_dir: Path | None = None) -> LiveInputs:
    """Daily bars up to yesterday plus today's up to 14:50, and the weights on them."""
    bars = load_daily_bars(
        client, [Instrument(symbol=SYMBOL, asset="future")], HISTORY_START, trade_date
    )
    if market_dir is not None:
        market_dir.mkdir(parents=True, exist_ok=True)
        bars.raw_panel.to_parquet(market_dir / "bars.parquet")
    return bars.inputs(target_weights(bars.panel))


def main(argv: Sequence[str] | None = None) -> int:
    return daily_main(STRATEGY_ID, load_inputs, argv)


if __name__ == "__main__":
    sys.exit(main())
