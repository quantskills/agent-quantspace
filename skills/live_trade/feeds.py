"""Minute bars for a live strategy: PandaData history, today's bars from AKShare (Sina).

Each trading day starts with :meth:`MinuteFeed.refresh`, before the session opens
(futures after 17:55, when PandaData has published the day's minute bars and the next
trading day's dominant contracts; stocks and funds the next morning). It reloads the whole
warm-up window from PandaData, which replaces the AKShare bars of the day before, and
compares the two first. During the session :meth:`MinuteFeed.update` appends today's
finished bars from AKShare. Both write one file per symbol in the research store layout
under ``<data_root>/live/<strategy_id>/market/<frequency>/``; the ``source`` column says
where each bar came from.

Signals of stocks and funds use backward-adjusted prices when the spec asks for them:
today's raw bars are multiplied by the factor known before the open. A stock whose
ex-date is today but whose factor PandaData has not published yet is halted for the day.
Futures bars are never adjusted; a continuous contract (``RB_DOMINANT.SHF``) maps to the
actual contract PandaData names dominant for the trading day.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd

from .clock import (
    EQUITY_SESSIONS,
    Session,
    TradingCalendar,
    bar_ends,
    bars_per_day,
    parse_trading_hours,
)
from .history import adjustment_factors, daily_closes, dominant_contracts, today_factors
from .history import as_day as _day
from .history import yyyymmdd as _yyyymmdd
from .spec import Instrument, LiveSpec

PANDADATA = "pandadata"
FEED_STATE = "feed.json"
STORE_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "open_interest",
    "factor",
    "contract",
    "trading_date",
    "source",
]
# A trading day's session is over for scheduling purposes after this time.
DAY_CLOSE = time(15, 30)
# Days of trading calendar loaded around the trading date.
CALENDAR_BACK_DAYS = 400
CALENDAR_AHEAD_DAYS = 20


class FeedNotReady(RuntimeError):
    """The pre-open refresh for the trading day has not run."""


def load_calendar(client, around: date) -> TradingCalendar:
    """Trading days from PandaData's calendar around ``around``."""
    table = client.get_trade_cal(
        _yyyymmdd(around - timedelta(CALENDAR_BACK_DAYS)),
        _yyyymmdd(around + timedelta(CALENDAR_AHEAD_DAYS)),
    )
    if table is None or table.empty:
        raise ValueError("PandaData returned no trading calendar")
    days = [_day(row) for row, flag in zip(table["nature_date"], table["is_trade"]) if int(flag)]
    return TradingCalendar.from_days(days)


def upcoming_trading_date(now: datetime, calendar: TradingCalendar) -> date:
    """The trading day whose bars come next: today before 15:30, otherwise the next one.

    A futures night session after 15:30 already belongs to the next trading day.
    """
    today = now.date()
    if calendar.is_trading_day(today) and now.time() < DAY_CLOSE:
        return today
    return calendar.next(today)


@dataclass(frozen=True)
class FeedState:
    """What the last refresh decided for one trading day; saved as ``feed.json``."""

    strategy_id: str
    trading_date: str
    frequency: str
    refreshed_at: str
    history_end: str
    contracts: dict[str, str]
    factors: dict[str, float]
    multipliers: dict[str, float]
    halted: dict[str, str]
    sessions: list[str]
    bar_ends: list[str]
    delay_seconds: int
    deadline_seconds: int
    keep_bars: int

    @property
    def day(self) -> date:
        return date.fromisoformat(self.trading_date)

    @property
    def schedule(self) -> list[datetime]:
        return [datetime.fromisoformat(item) for item in self.bar_ends]


def read_feed_state(strategy_id: str, data_root: str | Path | None = None) -> FeedState | None:
    from skills.store.workspace import resolve_workspace_paths

    path = (
        resolve_workspace_paths(data_root=data_root).data_root / "live" / strategy_id / FEED_STATE
    )
    if not path.exists():
        return None
    return FeedState(**json.loads(path.read_text(encoding="utf-8")))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@dataclass(frozen=True)
class BarComparison:
    """AKShare bars of one symbol and trading day against PandaData's bars for the same day."""

    symbol: str
    trading_date: str
    pandadata_bars: int
    akshare_bars: int
    compared: int
    missing_in_akshare: int
    close_differs: int
    max_close_diff: float
    volume_akshare: float
    volume_pandadata: float


@dataclass(frozen=True)
class RefreshReport:
    state: FeedState
    rows: dict[str, int]
    comparisons: list[BarComparison] = field(default_factory=list)


@dataclass(frozen=True)
class UpdateReport:
    """Today's bars appended from AKShare."""

    as_of: str
    latest: dict[str, str | None]
    added: dict[str, int]
    rewritten: dict[str, int]
    errors: dict[str, str]


class MinuteFeed:
    """Refresh and update a live strategy's minute bars; read them back as panels."""

    def __init__(
        self,
        spec: LiveSpec,
        client,
        *,
        data_root: str | Path | None = None,
        akshare=None,
        pause: float = 0.3,
    ):
        from skills.store.data_manager import DataManager
        from skills.store.workspace import resolve_workspace_paths

        self.spec = spec
        self.client = client
        self.akshare = akshare
        self.pause = pause
        self.root = (
            resolve_workspace_paths(data_root=data_root).data_root / "live" / spec.strategy_id
        )
        self.store = DataManager(self.root, create_layout=False)
        self._calendar: TradingCalendar | None = None

    # ------------------------------------------------------------------ calendar
    def calendar(self, around: date) -> TradingCalendar:
        cached = self._calendar
        if cached is None or not cached.days[0] + timedelta(60) <= around <= cached.days[-1]:
            self._calendar = load_calendar(self.client, around)
        return self._calendar

    # ------------------------------------------------------------------ state
    @property
    def state_path(self) -> Path:
        return self.root / FEED_STATE

    def state(self) -> FeedState:
        state = read_feed_state(self.spec.strategy_id, self.root.parent.parent)
        if state is None:
            raise FeedNotReady("the pre-open refresh has not run yet")
        return state

    # ------------------------------------------------------------------ refresh
    def _contracts(self, trading_date: date) -> dict[str, str]:
        return dominant_contracts(self.client, self.spec.instruments, trading_date)

    def _futures_reference(
        self, contracts: dict[str, str]
    ) -> tuple[tuple[Session, ...], dict[str, float]]:
        actual = sorted(set(contracts.values()))
        table = self.client.get_future_detail(
            actual, fields=["symbol", "trading_hours", "contract_multiplier"]
        )
        rows = {str(row["symbol"]): row for _, row in table.iterrows()}
        missing = [code for code in actual if code not in rows]
        if missing:
            raise ValueError(f"PandaData has no contract details for {missing}")
        hours = {str(rows[code]["trading_hours"]) for code in actual}
        if len(hours) > 1:
            raise ValueError(f"the contracts trade different sessions: {sorted(hours)}")
        multipliers = {
            symbol: float(rows[contract]["contract_multiplier"])
            for symbol, contract in contracts.items()
        }
        return parse_trading_hours(hours.pop()), multipliers

    def _futures_history(self, item: Instrument, start: date, end: date) -> pd.DataFrame:
        raw = self.client.fetch_market_min_data(
            item.symbol,
            _yyyymmdd(start),
            _yyyymmdd(end),
            symbol_type="future",
            frequency=self.spec.frequency,
        )
        if raw is None or raw.empty:
            raise ValueError(f"PandaData returned no {self.spec.frequency} bars for {item.symbol}")
        if item.continuous:
            contract = raw["dominant_id"].astype(str) + "." + raw["exchange"].astype(str)
        else:
            contract = item.symbol
        frame = pd.DataFrame(
            {
                "eob": pd.to_datetime(raw["datetime"]),
                "open": raw["open"].astype(float),
                "high": raw["high"].astype(float),
                "low": raw["low"].astype(float),
                "close": raw["close"].astype(float),
                "volume": raw["volume"].astype(float),
                "open_interest": pd.to_numeric(raw.get("open_interest"), errors="coerce"),
                "factor": 1.0,
                "contract": contract,
                "trading_date": raw["trading_date"].map(lambda v: _day(v).isoformat()),
                "source": PANDADATA,
            }
        )
        return frame.set_index("eob").sort_index()

    def _equity_factors(
        self, item: Instrument, start: date, end: date, trading_date: date
    ) -> tuple[dict[str, float], float, str | None]:
        """Backward-adjustment factor per trading date up to ``end``, today's factor, halt."""
        if self.spec.adjust == "none":
            return {}, 1.0, None
        raw = daily_closes(self.client, [item.symbol], item.asset, start, end)
        post = daily_closes(self.client, [item.symbol], item.asset, start, end, adjust="post")
        factors = adjustment_factors(raw[item.symbol], post[item.symbol])
        if not factors:
            raise ValueError(f"PandaData returned no daily bars to adjust {item.symbol}")
        today, halted = today_factors(
            self.client, [item], {item.symbol: factors[max(factors)]}, trading_date
        )
        return factors, today[item.symbol], halted.get(item.symbol)

    def _equity_history(
        self, item: Instrument, start: date, end: date, factors: dict[str, float]
    ) -> pd.DataFrame:
        raw = self.client.fetch_market_min_data(
            item.symbol,
            _yyyymmdd(start),
            _yyyymmdd(end),
            symbol_type=item.asset,
            frequency=self.spec.frequency,
        )
        if raw is None or raw.empty:
            raise ValueError(f"PandaData returned no {self.spec.frequency} bars for {item.symbol}")
        days = raw["date"].map(lambda v: _day(v).isoformat())
        factor = days.map(factors).astype(float) if factors else pd.Series(1.0, index=raw.index)
        if factor.isna().any():
            missing = sorted(set(days[factor.isna()]))
            raise ValueError(f"no adjustment factor for {item.symbol} on {missing}")
        frame = pd.DataFrame(
            {
                "eob": pd.to_datetime(raw["datetime"]),
                **{
                    name: raw[name].astype(float) * factor
                    for name in ("open", "high", "low", "close")
                },
                "volume": raw["volume"].astype(float),
                "open_interest": float("nan"),
                "factor": factor,
                "contract": item.symbol,
                "trading_date": days,
                "source": PANDADATA,
            }
        )
        return frame.set_index("eob").sort_index()

    def _compare(self, symbol: str, history: pd.DataFrame) -> list[BarComparison]:
        """AKShare bars stored before this refresh against PandaData's bars of the same days."""
        path = self.store.root / "market" / self.spec.frequency / f"{symbol}.parquet"
        if not path.exists():
            return []
        stored = pd.read_parquet(path)
        ours = stored[stored["source"] != PANDADATA]
        results = []
        for day, group in ours.groupby("trading_date"):
            theirs = history[history["trading_date"] == day]
            if theirs.empty:
                continue
            common = group.index.intersection(theirs.index)
            diff = (group.loc[common, "close"] - theirs.loc[common, "close"]).abs()
            results.append(
                BarComparison(
                    symbol=symbol,
                    trading_date=str(day),
                    pandadata_bars=len(theirs),
                    akshare_bars=len(group),
                    compared=len(common),
                    missing_in_akshare=len(theirs.index.difference(group.index)),
                    close_differs=int((diff > 1e-9).sum()),
                    max_close_diff=float(diff.max()) if len(diff) else 0.0,
                    volume_akshare=float(group["volume"].sum()),
                    volume_pandadata=float(theirs["volume"].sum()),
                )
            )
        return results

    def refresh(self, trading_date: date, *, now: datetime | None = None) -> RefreshReport:
        """Reload the warm-up window from PandaData and prepare ``trading_date``."""
        calendar = self.calendar(trading_date)
        if not calendar.is_trading_day(trading_date):
            raise ValueError(f"{trading_date} is not a trading day")
        spec = self.spec
        history_end = calendar.previous(trading_date)
        contracts = self._contracts(trading_date)
        if spec.futures:
            sessions, multipliers = self._futures_reference(contracts)
        else:
            sessions, multipliers = EQUITY_SESSIONS, {}
        per_day = bars_per_day(spec.frequency, sessions)
        days = math.ceil(spec.warmup_bars / per_day) + spec.spare_days + 1
        start = calendar.shift(history_end, -(days - 1))
        keep = days * per_day + bars_per_day(spec.frequency, sessions)
        rows, comparisons, factors, halted = {}, [], {}, {}
        for item in spec.instruments:
            if item.asset == "future":
                history = self._futures_history(item, start, history_end)
                factors[item.symbol] = 1.0
            else:
                by_day, today, halt = self._equity_factors(item, start, history_end, trading_date)
                history = self._equity_history(item, start, history_end, by_day)
                factors[item.symbol] = today
                if halt:
                    halted[item.symbol] = halt
            comparisons.extend(self._compare(item.symbol, history))
            path = self.store.root / "market" / spec.frequency / f"{item.symbol}.parquet"
            path.unlink(missing_ok=True)
            rows[item.symbol] = self.store.upsert_symbol(
                item.symbol,
                history[STORE_COLUMNS[:-1] + ["source"]],
                spec.frequency,
                keep_last=keep,
            ).rows
        state = FeedState(
            strategy_id=spec.strategy_id,
            trading_date=trading_date.isoformat(),
            frequency=spec.frequency,
            refreshed_at=(now or datetime.now()).isoformat(timespec="seconds"),
            history_end=history_end.isoformat(),
            contracts=contracts,
            factors=factors,
            multipliers=multipliers,
            halted=halted,
            sessions=[session.label() for session in sessions],
            bar_ends=[
                item.isoformat()
                for item in bar_ends(trading_date, spec.frequency, sessions, calendar)
            ],
            delay_seconds=spec.bar_delay_seconds,
            deadline_seconds=spec.deadline,
            keep_bars=keep,
        )
        _write_json(self.state_path, asdict(state))
        if comparisons:
            for day in sorted({item.trading_date for item in comparisons}):
                _write_json(
                    self.root / "reconcile" / f"{day}.bars.json",
                    {
                        "trading_date": day,
                        "bars": [asdict(item) for item in comparisons if item.trading_date == day],
                    },
                )
        return RefreshReport(state=state, rows=rows, comparisons=comparisons)

    # ------------------------------------------------------------------ update
    def update(self, now: datetime) -> UpdateReport:
        """Append today's finished bars from AKShare; errors are reported per symbol."""
        from skills.ingest.akshare_bars import fetch_intraday_bars

        state = self.state()
        schedule = set(state.schedule)
        if not schedule or now < min(schedule) - timedelta(hours=1):
            raise FeedNotReady(
                f"the refresh is for {state.trading_date}, not for {now:%Y-%m-%d %H:%M}"
            )
        if now > max(schedule) + timedelta(hours=12):
            raise FeedNotReady(f"the last refresh was for {state.trading_date}; refresh again")
        wanted = sorted(set(state.contracts.values()))
        result = fetch_intraday_bars(
            wanted, self.spec.frequency, now=now, pause=self.pause, akshare=self.akshare
        )
        latest, added, rewritten, errors = {}, {}, {}, {}
        for item in self.spec.instruments:
            contract = state.contracts[item.symbol]
            if contract in result.errors:
                errors[item.symbol] = result.errors[contract]
            bars = result.bars[result.bars["symbol"] == contract]
            bars = bars[bars["eob"].isin(schedule)]
            if bars.empty:
                latest[item.symbol] = self._latest(item.symbol)
                added[item.symbol] = 0
                rewritten[item.symbol] = 0
                continue
            factor = state.factors.get(item.symbol, 1.0)
            frame = pd.DataFrame(
                {
                    "eob": bars["eob"].to_numpy(),
                    **{
                        name: bars[name].to_numpy() * factor
                        for name in ("open", "high", "low", "close")
                    },
                    "volume": bars["volume"].to_numpy(),
                    "open_interest": bars["open_interest"].to_numpy(),
                    "factor": factor,
                    "contract": contract,
                    "trading_date": state.trading_date,
                    "source": bars["source"].to_numpy(),
                }
            ).set_index("eob")
            report = self.store.upsert_symbol(
                item.symbol, frame, self.spec.frequency, keep_last=state.keep_bars
            )
            added[item.symbol] = report.added
            rewritten[item.symbol] = (
                int(report.changed["eob"].nunique()) if len(report.changed) else 0
            )
            latest[item.symbol] = self._latest(item.symbol)
        return UpdateReport(
            as_of=result.as_of.isoformat(timespec="minutes"),
            latest=latest,
            added=added,
            rewritten=rewritten,
            errors=errors,
        )

    def _latest(self, symbol: str) -> str | None:
        path = self.store.root / "market" / self.spec.frequency / f"{symbol}.parquet"
        if not path.exists():
            return None
        index = pd.read_parquet(path, columns=["close"]).index
        return pd.Timestamp(index.max()).isoformat() if len(index) else None

    # ------------------------------------------------------------------ read
    def panel(self) -> pd.DataFrame:
        """All stored bars as a ``(symbol, eob)`` panel; prices adjusted as the spec says."""
        return self.store.read_symbols(self.spec.symbols, self.spec.frequency)

    def closes(self) -> pd.DataFrame:
        """Signal closes: eob by symbol."""
        return self.panel()["close"].unstack("symbol").sort_index()

    def raw_closes(self) -> pd.DataFrame:
        """Unadjusted closes of the traded contracts, for sizing: eob by symbol."""
        panel = self.panel()
        return (panel["close"] / panel["factor"]).unstack("symbol").sort_index()


__all__ = [
    "FEED_STATE",
    "PANDADATA",
    "BarComparison",
    "FeedNotReady",
    "FeedState",
    "MinuteFeed",
    "RefreshReport",
    "UpdateReport",
    "load_calendar",
    "read_feed_state",
    "upcoming_trading_date",
]
