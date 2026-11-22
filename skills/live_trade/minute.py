"""Minute-level live runs: one process per bar, plus the pre-open refresh and reconciliation.

A strategy workflow builds its :class:`~skills.live_trade.spec.LiveSpec`, a
:class:`~skills.live_trade.feeds.MinuteFeed`, and a ``compute(panel) -> weights`` function
that the backtest also uses, then calls :func:`run_bar` for a bar or :func:`refresh_day`
before the session. This module never imports strategy code.

Every bar is logged in the run log under its end time with the target it computed, so the
next refresh can recompute the same bars on PandaData's bars and report any bar where the
target would have been different.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from .contracts import DeliveryResult, TargetSnapshot, diff_weights
from .feeds import FeedNotReady, MinuteFeed, RefreshReport, _write_json, upcoming_trading_date
from .ledger import SignalLedger
from .runner import Delivery, RunLog, RunOutcome, deliver_signal, send_alert
from .spec import LiveSpec

Compute = Callable[[pd.DataFrame], pd.DataFrame]

_BAR_ALERTS = {
    "error": "这根 K 线运行出错，没有生成信号。",
    "source_error": "AKShare 取数失败，这根 K 线还没有数据。",
    "missed": "到截止时刻仍没有处理这根 K 线，已跳过。",
    "failed": "信号没有送达任何 IM 通道。",
    "partial": "信号只送达了部分 IM 通道。",
    "not_ready": "开盘前的整段重拉还没完成，盘中无法取数。",
}


def _notes(spec: LiveSpec, contracts: dict[str, str], halted: dict[str, str]) -> list[str]:
    lines = [
        f"- {symbol} 当前对应 {contract}"
        for symbol, contract in contracts.items()
        if symbol != contract
    ]
    lines += [f"- {symbol} 今天暂停调仓：{reason}" for symbol, reason in halted.items()]
    return (["说明："] + lines) if lines else []


def _hold_halted(snapshot: TargetSnapshot, halted: dict[str, str], base: dict[str, float]):
    """Keep the last delivered weight of halted symbols instead of the computed one."""
    if not halted:
        return snapshot
    weights = {k: v for k, v in snapshot.weights.items() if k not in halted}
    weights.update({k: base[k] for k in halted if k in base})
    return TargetSnapshot(snapshot.strategy_id, snapshot.as_of, weights, snapshot.prices)


def run_bar(
    spec: LiveSpec,
    feed: MinuteFeed,
    compute: Compute,
    *,
    bar: datetime,
    now: datetime,
    write: bool = False,
    capital: float | None = None,
    lot_size: int = 100,
    data_root: str | Path | None = None,
    urls: Sequence[str] | None = None,
) -> RunOutcome:
    """Run the strategy for the bar ending at ``bar``.

    Statuses: ``done`` (the bar already finished), ``missed`` (past its deadline),
    ``stale`` (some symbol has no bar at ``bar`` yet; retried), ``source_error`` (AKShare
    failed for a lagging symbol; retried and alerted), ``not_ready`` (no refresh for the
    day), ``error``, or the delivery status. With ``write`` every attempt is logged and each
    kind of problem alerts once per trade date.
    """
    runs = RunLog(spec.strategy_id, data_root)
    alerts: list[DeliveryResult] = []
    label = bar.isoformat(timespec="minutes")
    try:
        state = feed.state()
        trade_date = state.day
    except FeedNotReady as exc:
        state, trade_date = None, now.date()
        not_ready = str(exc)
    else:
        not_ready = ""

    def finish(status, detail="", delivery: Delivery | None = None, target=None) -> RunOutcome:
        if write:
            signal_id = delivery.signal.signal_id if delivery else None
            runs.record(bar, status, detail, signal_id, target=target, trade_date=trade_date)
            if status in _BAR_ALERTS and runs.claim_alert(trade_date, status):
                text = f"K 线：{label}\n{_BAR_ALERTS[status]}" + (f"\n{detail}" if detail else "")
                alerts.extend(send_alert(spec.strategy_id, trade_date, status, text, urls=urls))
        return RunOutcome(spec.strategy_id, label, status, detail, delivery, alerts)

    if state is None:
        return finish("not_ready", not_ready)
    if bar.isoformat() not in state.bar_ends:
        return finish("error", f"{label} 不是 {state.trading_date} 的 K 线结束时刻")
    if write and runs.is_done(bar):
        previous = runs.get(bar) or {}
        return RunOutcome(spec.strategy_id, label, "done", previous.get("status", ""))
    if now >= bar + timedelta(seconds=state.deadline_seconds):
        return finish(
            "missed", f"截止时刻 {bar + timedelta(seconds=state.deadline_seconds):%H:%M:%S}"
        )
    try:
        update = feed.update(now)
        lagging = {
            symbol: latest
            for symbol, latest in update.latest.items()
            if latest is None or datetime.fromisoformat(latest) < bar
        }
        if lagging:
            failed = {
                symbol: update.errors[symbol] for symbol in lagging if symbol in update.errors
            }
            detail = "；".join(f"{symbol} 最新 K 线 {latest}" for symbol, latest in lagging.items())
            if failed:
                detail += "；" + "；".join(f"{symbol}: {text}" for symbol, text in failed.items())
                return finish("source_error", detail)
            return finish("stale", detail)
        weights = compute(feed.panel()).sort_index()
        if weights.empty:
            raise ValueError("the strategy returned an empty weights table")
        last = pd.Timestamp(weights.index[-1])
        if last < pd.Timestamp(bar):
            return finish("stale", f"最新权重时间 {last}，早于 K 线 {label}")
        if last > pd.Timestamp(bar):
            raise ValueError(f"weights reach {last} after the bar {label}")
        ledger = SignalLedger(spec.strategy_id, data_root)
        computed = TargetSnapshot.from_frames(
            weights, spec.strategy_id, as_of=bar, prices=feed.raw_closes()
        )
        snapshot = _hold_halted(computed, state.halted, ledger.base_weights())
        delivery = deliver_signal(
            snapshot,
            ledger,
            write=write,
            urls=urls,
            capital=capital,
            multipliers=state.multipliers,
            lot_size=lot_size,
            notes=_notes(spec, state.contracts, state.halted),
        )
    except Exception as exc:  # noqa: BLE001 - any failure must be logged and alerted
        return finish("error", f"{type(exc).__name__}: {exc}")
    return finish(delivery.status, delivery=delivery, target=computed.weights)


@dataclass(frozen=True)
class SignalMismatch:
    """A bar whose target differs when recomputed on PandaData's bars."""

    bar: str
    sent: dict[str, float]
    recomputed: dict[str, float]
    symbols: list[str]


@dataclass(frozen=True)
class RefreshOutcome:
    strategy_id: str
    trade_date: str
    status: str
    detail: str = ""
    report: RefreshReport | None = None
    mismatches: dict[str, list[SignalMismatch]] = field(default_factory=dict)
    alerts: list[DeliveryResult] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.status == "error" else 0


def reconcile_signals(
    spec: LiveSpec,
    weights: pd.DataFrame,
    runs: RunLog,
    trade_date: date,
) -> list[SignalMismatch]:
    """Bars of ``trade_date`` whose logged target differs from ``weights`` at the same bar."""
    mismatches = []
    ordered = weights.sort_index()
    for key, entry in sorted(runs.bars(trade_date).items()):
        if "target" not in entry:
            continue
        stamp = pd.Timestamp(key)
        if stamp not in ordered.index:
            continue
        row = ordered.loc[stamp]
        recomputed = {
            str(symbol): float(value)
            for symbol, value in row.items()
            if pd.notna(value) and abs(float(value)) > 1e-6
        }
        changes = diff_weights(entry["target"], recomputed)
        if changes:
            mismatches.append(
                SignalMismatch(key, dict(entry["target"]), recomputed, [c.symbol for c in changes])
            )
    return mismatches


def refresh_day(
    spec: LiveSpec,
    feed: MinuteFeed,
    compute: Compute,
    *,
    now: datetime,
    write: bool = False,
    data_root: str | Path | None = None,
    urls: Sequence[str] | None = None,
) -> RefreshOutcome:
    """Reload PandaData history for the next trading day, then reconcile the days it replaced.

    Alerts (with ``write``, once per trade date and kind): ``refresh_error`` when the
    refresh fails, ``halted`` when a symbol cannot trade today, ``reconcile`` when a bar's
    target differs on PandaData's bars. The comparison is written to
    ``<data_root>/live/<strategy_id>/reconcile/<trade date>.signals.json``.
    """
    runs = RunLog(spec.strategy_id, data_root)
    alerts: list[DeliveryResult] = []
    trade_date = now.date()

    def alert(day: date, kind: str, text: str) -> None:
        if write and runs.claim_alert(day, kind):
            alerts.extend(send_alert(spec.strategy_id, day, kind, text, urls=urls))

    try:
        trade_date = upcoming_trading_date(now, feed.calendar(now.date()))
        report = feed.refresh(trade_date, now=now)
        days = sorted({item.trading_date for item in report.comparisons})
        mismatches: dict[str, list[SignalMismatch]] = {}
        if days:
            weights = compute(feed.panel())
            for day in days:
                found = reconcile_signals(spec, weights, runs, date.fromisoformat(day))
                mismatches[day] = found
                _write_json(
                    feed.root / "reconcile" / f"{day}.signals.json",
                    {"trading_date": day, "mismatches": [asdict(item) for item in found]},
                )
    except Exception as exc:  # noqa: BLE001 - reported and alerted
        detail = f"{type(exc).__name__}: {exc}"
        alert(
            trade_date, "refresh_error", f"开盘前整段重拉失败，今天的盘中信号无法生成。\n{detail}"
        )
        return RefreshOutcome(
            spec.strategy_id, trade_date.isoformat(), "error", detail, alerts=alerts
        )
    if report.state.halted:
        lines = "\n".join(f"- {symbol}：{reason}" for symbol, reason in report.state.halted.items())
        alert(trade_date, "halted", f"以下标的今天暂停调仓：\n{lines}")
    for day, found in mismatches.items():
        if not found:
            continue
        bars = [item for item in report.comparisons if item.trading_date == day]
        differs = sum(item.close_differs for item in bars)
        compared = sum(item.compared for item in bars)
        sample = "\n".join(f"- {item.bar}：{', '.join(item.symbols)}" for item in found[:5])
        alert(
            date.fromisoformat(day),
            "reconcile",
            f"{day} 用 PandaData 的 K 线复算，有 {len(found)} 根 K 线的目标和当时发出的不同"
            f"（收盘价不同的 K 线 {differs}/{compared}）：\n{sample}",
        )
    return RefreshOutcome(
        spec.strategy_id,
        trade_date.isoformat(),
        "refreshed",
        report=report,
        mismatches=mismatches,
        alerts=alerts,
    )


__all__ = [
    "Compute",
    "RefreshOutcome",
    "SignalMismatch",
    "reconcile_signals",
    "refresh_day",
    "run_bar",
]
