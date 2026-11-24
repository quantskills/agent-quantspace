"""The command-line entry of a live strategy workflow, and the check that it matches the backtest.

``qs live-trade serve`` starts every run as ``python -m <workflow module> ...``. The module
supplies only the strategy: its id or :class:`~skills.live_trade.spec.LiveSpec`, how to load
the data, and the ``target_weights`` function the backtest also calls. :func:`daily_main` or
:func:`minute_main` parses the arguments, runs the day or the bar, prints one JSON report on
stdout, and returns the exit code the scheduler reads::

    STRATEGY_ID = "my_strategy"

    def target_weights(close): ...                    # the backtest calls it too

    def load_inputs(client, trade_date, market_dir=None) -> LiveInputs: ...

    def main(argv=None) -> int:
        return daily_main(STRATEGY_ID, load_inputs, argv)

    SPEC = LiveSpec(strategy_id="my_strategy_5m", frequency="5m", ...)

    def main(argv=None) -> int:
        return minute_main(SPEC, target_weights, argv)

A live run sees only the data up to its bar, so its target equals the backtest's row only if
the weight function is causal and, for minute strategies, needs no more than the warm-up
window; :func:`replay_mismatches` checks both on history.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from skills.backtest.units import check_unit

from .daily import CUTOFF, DAY_CLOSE, INTRADAY_SOURCE
from .feeds import MinuteFeed
from .minute import Compute, refresh_day, run_bar
from .runner import DataNotReady, Delivery, LiveInputs, run_live
from .scheduler import DEFAULT_TIMEZONE
from .spec import INTRADAY_SOURCES, LiveSpec

# ``load(client, trade_date, market_dir)`` returns a daily workflow's full target table; it
# saves what it downloaded under ``market_dir`` when that is not None.
DailyLoad = Callable[[Any, date, Path | None], LiveInputs]


def workflow_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """The options every live workflow accepts from ``run_job`` and ``tick``."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Trade date YYYY-MM-DD; default: today in Asia/Shanghai.")
    parser.add_argument("--bar", help="Minute strategies: end time of the bar to run.")
    parser.add_argument(
        "--refresh", action="store_true", help="Minute strategies: pre-open reload and reconcile."
    )
    parser.add_argument("--now", help="Override the current time (YYYY-MM-DDTHH:MM:SS).")
    parser.add_argument("--write", action="store_true", help="Push and log; otherwise preview.")
    parser.add_argument("--final", action="store_true", help="Last attempt of the day.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send the latest full target as a marked test message at any hour; "
        "no trading-day check, ledger, run log, or alerts.",
    )
    parser.add_argument("--data-root", default=None, help="Data root for live state and data.")
    parser.add_argument(
        "--capital",
        type=float,
        default=None,
        help="Capital for target units; lots strategies only show the share of capital.",
    )
    parser.add_argument("--lot-size", type=int, default=100, help="Board lot for non-futures.")
    parser.add_argument(
        "--account",
        default=None,
        help="Futures strategies: PandaAI account code or id to trade with --write; "
        "only SimNow accounts (broker 9999) are traded.",
    )
    parser.add_argument(
        "--max-lots",
        type=int,
        default=None,
        help="Futures strategies: most contracts any actual contract may target; "
        "a larger target places no order and alerts over_limit.",
    )
    parser.add_argument(
        "--intraday-source",
        choices=INTRADAY_SOURCES,
        default=None,
        help="Where today's bars of futures come from: akshare (Sina) or tqsdk (built from "
        "TqSdk ticks; needs TQ_USERNAME and TQ_PASSWORD). Default: what the strategy "
        "declares, else akshare. Stocks and funds always use akshare.",
    )
    args = parser.parse_args(argv)
    if args.max_lots is not None and args.max_lots < 1:
        parser.error("--max-lots must be at least 1")
    zone = ZoneInfo(DEFAULT_TIMEZONE)
    args.bar = datetime.fromisoformat(args.bar) if args.bar else None
    args.now = (
        datetime.fromisoformat(args.now) if args.now else datetime.now(zone).replace(tzinfo=None)
    )
    args.date = date.fromisoformat(args.date) if args.date else datetime.now(zone).date()
    return args


# --------------------------------------------------------------------------- daily


def is_trading_day(client, day: date) -> bool:
    """Whether PandaData's calendar has ``day`` as a trading day."""
    stamp = day.strftime("%Y%m%d")
    calendar = client.get_trade_cal(stamp, stamp)
    if calendar is None or calendar.empty:
        raise ValueError(f"PandaData has no trading calendar for {day}")
    return bool(int(calendar["is_trade"].iloc[0]))


def _login_expired(exc: BaseException | None) -> bool:
    while exc is not None:
        if "init_token" in str(exc) or "登录已过期" in str(exc):
            return True
        exc = exc.__cause__
    return False


def load_with_relogin(
    load: DailyLoad, make_client: Callable[[], Any], trade_date: date, market_dir: Path | None
) -> LiveInputs:
    """``load`` on a new client, once more on a fresh login when PandaData drops the session."""
    try:
        return load(make_client(), trade_date, market_dir)
    except Exception as exc:
        if not _login_expired(exc):
            raise
        return load(make_client(), trade_date, market_dir)


def latest_inputs(load: DailyLoad, make_client: Callable[[], Any], day: date) -> LiveInputs:
    """The inputs of the newest trading day at or before ``day`` whose data is ready.

    For ``--test`` at any hour: a weekend falls back to the last trading day, and a trading
    day before its cut-off (:class:`~skills.live_trade.runner.DataNotReady`) to the one
    before it.
    """
    from .feeds import load_calendar

    calendar = load_calendar(make_client(), day)
    if not calendar.is_trading_day(day):
        day = calendar.previous(day)
    try:
        return load_with_relogin(load, make_client, day, None)
    except DataNotReady:
        return load_with_relogin(load, make_client, calendar.previous(day), None)


def daily_main(
    strategy_id: str,
    load: DailyLoad,
    argv: Sequence[str] | None = None,
    *,
    unit: str = "percent",
) -> int:
    """One run of a daily workflow for ``--date``; prints the report and returns the exit code.

    The trading day comes from PandaData's calendar; a calendar failure is reported as the
    run's ``error``. ``--test`` runs the newest ready trading day at or before ``--date``
    (:func:`latest_inputs`). ``load`` gets a PandaData client, the trade date, and
    ``<data_root>/live/<strategy_id>/market`` to keep its download with ``--write`` (None
    for previews and tests); it raises :class:`~skills.live_trade.runner.DataNotReady`
    while the day's data is not there, which makes the run ``stale``. The rest is
    :func:`~skills.live_trade.runner.run_live`. With ``--write``, ``--capital`` and
    ``--account`` a futures strategy also trades its target on that SimNow account through
    the PandaAI client CLI, capped by ``--max-lots``, but only from the cut-off to the end
    of the trade date's day session (``--now``); at any other time the run still signals
    and its execution is ``closed``. ``--intraday-source`` is the source
    :func:`~skills.live_trade.daily.load_daily_bars` uses when ``load`` names none.

    ``unit`` is the unit of the table ``load`` returns: ``percent`` (shares of capital) or
    ``lots`` (whole lots; orders take them as they are and ``--capital`` only adds the
    share of capital to the message). The backtest takes the same value.
    """
    check_unit(unit)
    args = workflow_arguments(argv)
    token = INTRADAY_SOURCE.set(args.intraday_source or INTRADAY_SOURCE.get())
    try:
        return _daily_run(strategy_id, load, args, unit)
    finally:
        INTRADAY_SOURCE.reset(token)


def _daily_run(strategy_id: str, load: DailyLoad, args: argparse.Namespace, unit: str) -> int:
    from skills.ingest import PandaDataClient
    from skills.store.workspace import resolve_workspace_paths

    client = PandaDataClient()
    root = resolve_workspace_paths(data_root=args.data_root).data_root
    market_dir = root / "live" / strategy_id / "market" if args.write and not args.test else None
    trading, calendar_error = True, None
    if not args.test:
        try:
            trading = is_trading_day(client, args.date)
        except Exception as exc:  # noqa: BLE001 - reported as a run error below
            calendar_error = exc

    def inputs() -> LiveInputs:
        if calendar_error is not None:
            raise calendar_error
        if args.test:
            return latest_inputs(load, PandaDataClient, args.date)
        return load_with_relogin(load, PandaDataClient, args.date, market_dir)

    execute, closed = None, ""
    if args.account and not args.test:
        execute = _panda_executor(strategy_id, args.account, datetime.combine(args.date, CUTOFF))
        start, end = (datetime.combine(args.date, moment) for moment in (CUTOFF, DAY_CLOSE))
        if not start <= args.now < end:
            closed = f"{args.now:%Y-%m-%d %H:%M} 不在 {start:%Y-%m-%d %H:%M}–{end:%H:%M} 内，不下单"
    outcome = run_live(
        strategy_id,
        inputs,
        trade_date=args.date,
        is_trading_day=trading,
        write=args.write,
        final=args.final,
        capital=args.capital,
        lot_size=args.lot_size,
        data_root=args.data_root,
        test=args.test,
        execute=execute,
        max_lots=args.max_lots,
        closed=closed,
        unit=unit,
    )
    delivery = _delivery_fields(outcome.delivery)
    report = {
        "strategy_id": outcome.strategy_id,
        "trade_date": outcome.trade_date,
        "status": outcome.status,
        "detail": outcome.detail,
        "execution": outcome.execution.to_dict() if outcome.execution else None,
        "signal_id": delivery.get("signal_id"),
        "target": delivery.get("target"),
        "message": delivery.get("message"),
        "deliveries": delivery.get("deliveries", []),
        "alerts": [vars(item) for item in outcome.alerts],
    }
    return _emit(report, outcome.exit_code)


# --------------------------------------------------------------------------- minute


def _panda_executor(strategy_id: str, account: str, bar: datetime):
    """``execute`` for :func:`run_bar`: trade ``account`` through the PandaAI client CLI."""
    from .execution import PandaTrader, execute_targets
    from .panda_cli import discover_cli

    command = discover_cli()
    if command is None:
        raise SystemExit("PandaAI client CLI not found")
    trader = PandaTrader(command, account, trace_id=f"{strategy_id}-{bar:%Y%m%dT%H%M}")

    def execute(wanted, request_id):
        return execute_targets(trader, wanted, request_id=request_id)

    return execute


def minute_main(spec: LiveSpec, compute: Compute, argv: Sequence[str] | None = None) -> int:
    """One run of a minute-level workflow; prints the report and returns the exit code.

    ``--refresh`` is the pre-open reload (:func:`refresh_day`), ``--bar <end time>`` one bar
    (:func:`run_bar`), and ``--test`` sends the latest stored target as a marked test
    message. With ``--write``, ``--capital`` and ``--account`` a futures bar also trades the
    target on that SimNow account through the PandaAI client CLI. No mode exits 2.
    """
    from skills.ingest import PandaDataClient

    args = workflow_arguments(argv)
    if args.intraday_source:
        try:
            spec = spec.with_source(args.intraday_source)
        except ValueError as exc:
            print(f"--intraday-source {args.intraday_source}: {exc}", file=sys.stderr)
            return 2
    feed = MinuteFeed(spec, PandaDataClient(), data_root=args.data_root)
    if args.refresh:
        refreshed = refresh_day(
            spec, feed, compute, now=args.now, write=args.write, data_root=args.data_root
        )
        report = refreshed.report
        state = report.state if report else None
        return _emit(
            {
                "strategy_id": spec.strategy_id,
                "trade_date": refreshed.trade_date,
                "status": refreshed.status,
                "detail": refreshed.detail,
                "contracts": state.contracts if state else None,
                "bars_today": len(state.bar_ends) if state else None,
                "rows": report.rows if report else None,
                "mismatches": {day: len(items) for day, items in refreshed.mismatches.items()},
                "alerts": [vars(item) for item in refreshed.alerts],
            },
            refreshed.exit_code,
        )
    if args.test:

        def load() -> LiveInputs:
            state = feed.state()
            return LiveInputs(
                weights=compute(feed.panel()),
                prices=feed.raw_closes(),
                multipliers=state.multipliers,
            )

        outcome = run_live(
            spec.strategy_id,
            load,
            trade_date=args.now.date(),
            is_trading_day=True,
            write=args.write,
            capital=args.capital,
            lot_size=args.lot_size,
            data_root=args.data_root,
            test=True,
            unit=spec.unit,
        )
        return _emit(
            {
                "strategy_id": spec.strategy_id,
                "status": outcome.status,
                "detail": outcome.detail,
                **_delivery_fields(outcome.delivery),
            },
            outcome.exit_code,
        )
    if args.bar is None:
        print("--bar, --refresh or --test is required", file=sys.stderr)
        return 2
    execute = _panda_executor(spec.strategy_id, args.account, args.bar) if args.account else None
    outcome = run_bar(
        spec,
        feed,
        compute,
        bar=args.bar,
        now=args.now,
        write=args.write,
        capital=args.capital,
        lot_size=args.lot_size,
        data_root=args.data_root,
        execute=execute,
        max_lots=args.max_lots,
    )
    return _emit(
        {
            "strategy_id": spec.strategy_id,
            "bar": outcome.trade_date,
            "execution": outcome.execution.to_dict() if outcome.execution else None,
            "status": outcome.status,
            "detail": outcome.detail,
            **_delivery_fields(outcome.delivery),
            "alerts": [vars(item) for item in outcome.alerts],
        },
        outcome.exit_code,
    )


def _delivery_fields(delivery: Delivery | None) -> dict:
    if delivery is None:
        return {}
    return {
        "signal_id": delivery.signal.signal_id,
        "target": delivery.signal.target,
        "message": f"{delivery.title}\n{delivery.body}",
        "deliveries": [vars(item) for item in delivery.results],
    }


def _emit(report: dict, exit_code: int) -> int:
    from skills.cli.io import utf8_stdout

    utf8_stdout()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return exit_code


# --------------------------------------------------------------------------- backtest check


def _eob(data: pd.DataFrame) -> pd.DatetimeIndex:
    if isinstance(data.index, pd.MultiIndex):
        return pd.DatetimeIndex(data.index.get_level_values("eob"))
    return pd.DatetimeIndex(data.index)


def _same_row(left: pd.Series, right: pd.Series, tolerance: float) -> bool:
    symbols = left.index.union(right.index)
    left = left.reindex(symbols).astype(float).fillna(0.0)
    right = right.reindex(symbols).astype(float).fillna(0.0)
    return bool(((left - right).abs() <= tolerance).all())


def replay_mismatches(
    compute: Callable[[pd.DataFrame], pd.DataFrame],
    data: pd.DataFrame,
    *,
    window: int | None = None,
    last: int = 50,
    tolerance: float = 1e-9,
) -> list[pd.Timestamp]:
    """Rows of the backtest's weights that a live run would not reproduce.

    ``compute`` is the workflow's ``target_weights`` and ``data`` its input over some
    history: a ``(symbol, eob)`` panel or an ``eob``-indexed table. For each of the last
    ``last`` rows of ``compute(data)``, this recomputes the weights on the data a live run
    has at that bar, everything from the first row (a daily workflow that reloads from a
    fixed start) or only the last ``window`` bars (a minute workflow: pass
    ``LiveSpec.warmup_bars``), and returns the rows whose live target differs. Missing and
    zero weights count as equal. A row appears when the function looks ahead, depends on
    more history than the window, or depends on where the history starts.
    """
    full = compute(data).sort_index()
    eob = _eob(data)
    stamps = eob.unique().sort_values()
    mismatches = []
    for stamp in full.index[-last:]:
        position = int(stamps.searchsorted(stamp, side="right"))
        first = stamps[max(0, position - window)] if window else stamps[0]
        replay = compute(data[(eob >= first) & (eob <= stamp)]).sort_index()
        reproduced = (
            not replay.empty
            and replay.index[-1] == stamp
            and _same_row(replay.iloc[-1], full.loc[stamp], tolerance)
        )
        if not reproduced:
            mismatches.append(pd.Timestamp(stamp))
    return mismatches


__all__ = [
    "DailyLoad",
    "daily_main",
    "is_trading_day",
    "load_with_relogin",
    "minute_main",
    "replay_mismatches",
    "workflow_arguments",
]
