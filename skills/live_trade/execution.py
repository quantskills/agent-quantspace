"""Trade futures target positions through the PandaAI client CLI, SimNow accounts only.

A minute strategy hands :func:`execute_targets` the whole contracts it wants per actual
contract (``{"RB2701.SHF": 2}``; negative is short). Each call:

1. re-reads the account and refuses anything but a SimNow account (broker ``9999``) that
   the CLI may use, connected and ready;
2. stops on an order whose state the client does not know (``UNKNOWN``) and cancels the
   working orders of the same products left from an earlier bar (the account is meant to
   be the strategy's own);
3. builds one ``target-position`` plan for the wanted contracts and every other month of
   the same products still held (target 0), executes that frozen plan, and follows its
   orders for a few seconds.

The client prices plan orders at the best opposite quote, good for the day; what is still
working when the call returns is cancelled and re-targeted by the next bar. Nothing is
retried within a call, so an order is never sent twice for the same target.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from .panda_cli import PandaAccount, PandaCliError, run_cli

# Order states, as the client reports them.
WORKING = frozenset({"SUBMITTING", "SUBMITTED", "ACCEPTED", "PARTIALLY_FILLED"})
UNKNOWN = "UNKNOWN"
FILLED = "FILLED"
# How long one call follows its orders and its cancels before handing over to the next bar.
DEFAULT_WAIT_SECONDS = 15.0
POLL_SECONDS = 1.0

_PRODUCT = re.compile(r"[A-Za-z]+")


class ExecutionRefused(RuntimeError):
    """The account may not be traded automatically; nothing was sent."""


def product_of(symbol: str) -> str:
    """``RB`` for ``RB2701.SHF``, ``rb2701`` or ``RB_DOMINANT.SHF``."""
    found = _PRODUCT.match(symbol)
    if not found:
        raise ValueError(f"cannot read the product of {symbol!r}")
    return found.group(0).upper()


@dataclass(frozen=True)
class LegResult:
    """One order of an executed plan as last seen."""

    contract: str
    side: str
    offset: str
    quantity: int
    price: float | None
    status: str
    filled: int
    operation_id: str
    error: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    """What one call did; ``status`` says whether the account now holds the target.

    Statuses: ``in_position`` (nothing to do), ``filled`` (the target is held),
    ``working`` (orders still open; the next bar cancels and re-targets), ``rejected``
    (an order failed), ``pending_cancel`` (an earlier order could not be cancelled yet),
    ``unknown`` (the client lost track of an order; trading stops until it is resolved),
    ``blocked`` (the account cannot trade now), ``error``.
    """

    status: str
    detail: str = ""
    account: str = ""
    wanted: dict[str, int] = field(default_factory=dict)
    before: dict[str, int] = field(default_factory=dict)
    after: dict[str, int] = field(default_factory=dict)
    cancelled: list[str] = field(default_factory=list)
    plan_id: str = ""
    legs: list[LegResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("in_position", "filled", "working")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PandaTrader:
    """The CLI calls one account needs; every call carries ``trace_id`` for the audit trail."""

    def __init__(
        self,
        command: list[str],
        account: str,
        *,
        trace_id: str = "",
        runner: Callable[..., Any] = run_cli,
    ):
        self.command = command
        self.account = str(account)
        self.env = {"PANDA_LIVE_TRACE_ID": trace_id} if trace_id else {}
        self._run = runner

    def _call(self, *args: str, read_only: bool = False) -> Any:
        """Run one command; a read-only one is tried once more if the client fails it.

        The client sometimes answers a query with a cut-off ``ok: false`` while it is busy;
        cancels and plan executions are never repeated.
        """
        try:
            return self._run(self.command, *args, env=self.env)
        except (PandaCliError, TimeoutError):
            if not read_only:
                raise
            time.sleep(POLL_SECONDS)
            return self._run(self.command, *args, env=self.env)

    def _scoped(self, *args: str, read_only: bool = False) -> Any:
        return self._call(*args, "--account", self.account, read_only=read_only)

    def account_info(self) -> PandaAccount:
        for item in self._call("accounts", read_only=True) or []:
            found = PandaAccount.from_cli(item)
            if self.account in (found.code, str(found.account_id)):
                return found
        raise ExecutionRefused(f"the client has no account {self.account}")

    def connection(self) -> dict:
        return (self._scoped("connection", read_only=True) or {}).get("connection") or {}

    def positions(self) -> list[dict]:
        return (self._scoped("positions", read_only=True) or {}).get("items") or []

    def orders(self) -> list[dict]:
        return (self._scoped("orders", read_only=True) or {}).get("items") or []

    def operation(self, operation_id: str) -> dict:
        return self._scoped("operation", "--id", operation_id, read_only=True) or {}

    def cancel(self, order_id: str, request_id: str) -> dict:
        return (
            self._scoped("cancel", "--order-id", order_id, "--client-request-id", request_id) or {}
        )

    def target_position(self, targets: list[dict]) -> dict:
        return self._scoped("target-position", "--targets", json.dumps(targets)) or {}

    def execute_plan(self, plan_id: str) -> dict:
        return self._scoped("plan", "execute", "--plan-id", plan_id, "--yes") or {}


def _net_positions(items: list[dict], products: set[str]) -> dict[str, int]:
    net: dict[str, int] = {}
    for item in items:
        symbol = str(item.get("symbol") or "")
        if not symbol or product_of(symbol) not in products:
            continue
        volume = int(item.get("volume") or item.get("position") or 0)
        sign = -1 if str(item.get("direction")).lower() == "short" else 1
        net[symbol] = net.get(symbol, 0) + sign * volume
    return {symbol: units for symbol, units in net.items() if units}


def _held_sides(items: list[dict], symbol: str) -> set[str]:
    return {
        str(item.get("direction")).lower()
        for item in items
        if item.get("symbol") == symbol and int(item.get("volume") or 0)
    }


def check_account(trader: PandaTrader) -> PandaAccount:
    """The account if it is a SimNow account the CLI may trade now; raise otherwise."""
    account = trader.account_info()
    if not account.is_simnow:
        raise ExecutionRefused(
            f"{account.name}（{account.code}）不是 SimNow 账号（broker {account.broker_id}），"
            "实盘账号不自动下单"
        )
    if not account.cli_eligible:
        raise ExecutionRefused(account.unavailable_reason or "账号未开启 CLI")
    if not account.runtime_state_known or account.running_asset_units:
        raise ExecutionRefused("账号下有运行中的资金单元或运行状态未确认")
    return account


def _wait(poll: Callable[[], bool], wait_seconds: float, sleep: Callable[[float], None]) -> bool:
    deadline = time.monotonic() + wait_seconds
    while True:
        if poll():
            return True
        if time.monotonic() >= deadline:
            return False
        sleep(POLL_SECONDS)


def execute_targets(
    trader: PandaTrader,
    wanted: Mapping[str, int],
    *,
    request_id: str,
    wait_seconds: float = DEFAULT_WAIT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> ExecutionResult:
    """Bring the account to ``wanted`` whole contracts per actual contract (see the module).

    ``request_id`` (strategy and bar) names the cancel requests so a repeated call cannot
    cancel twice under different names. Contracts of other products are left alone.
    """
    wanted = {symbol: int(units) for symbol, units in wanted.items()}
    products = {product_of(symbol) for symbol in wanted}
    result: dict[str, Any] = {"account": trader.account, "wanted": wanted}
    try:
        account = check_account(trader)
        result["account"] = f"{account.name}（{account.code}）"
        connection = trader.connection()
        if not (connection.get("connected") and connection.get("cli_ready")):
            state = connection.get("connection_status") or "未知"
            return ExecutionResult("blocked", f"柜台未就绪（{state}）", **result)

        mine = [
            order
            for order in trader.orders()
            if product_of(str(order.get("contract_code") or "?")) in products
        ]
        lost = [order for order in mine if order.get("status") == UNKNOWN]
        if lost:
            names = ", ".join(str(order.get("cli_order_id")) for order in lost)
            return ExecutionResult("unknown", f"客户端无法确认这些委托的状态：{names}", **result)
        working = [order for order in mine if order.get("status") in WORKING]
        cancelled = []
        for order in working:
            order_id = str(order["cli_order_id"])
            trader.cancel(order_id, f"{request_id}:cancel:{order_id}")
            cancelled.append(order_id)
        result["cancelled"] = cancelled
        if cancelled:

            def cancels_done() -> bool:
                return not any(
                    order.get("status") in WORKING or order.get("status") == UNKNOWN
                    for order in trader.orders()
                    if str(order.get("cli_order_id")) in cancelled
                )

            if not _wait(cancels_done, wait_seconds, sleep):
                return ExecutionResult(
                    "pending_cancel", "上一根 K 线的委托还没撤完，本根不下新单", **result
                )

        items = trader.positions()
        before = _net_positions(items, products)
        result["before"] = before
        targets = []
        for symbol in sorted(set(wanted) | set(before)):
            units = wanted.get(symbol, 0)
            if units == before.get(symbol, 0) and len(_held_sides(items, symbol)) <= 1:
                continue
            if units:
                direction = "long" if units > 0 else "short"
                targets.append({"symbol": symbol, "direction": direction, "volume": abs(units)})
            else:
                for side in sorted(_held_sides(items, symbol)):
                    targets.append({"symbol": symbol, "direction": side, "volume": 0})
        if not targets:
            return ExecutionResult("in_position", **result, after=before)

        plan = trader.target_position(targets)
        result["plan_id"] = str(plan.get("plan_id") or "")
        if not plan.get("legs"):
            return ExecutionResult("in_position", "客户端认为无需调仓", **result, after=before)
        executed = trader.execute_plan(result["plan_id"])
        raw = executed.get("result_json")
        summary = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
        operations = [
            str((leg.get("result") or {}).get("operation_id") or "")
            for leg in summary.get("legs") or []
        ]
        legs: dict[str, LegResult] = {}

        def refresh_legs() -> bool:
            for operation_id in operations:
                if not operation_id:
                    continue
                if operation_id in legs and legs[operation_id].status not in WORKING:
                    continue
                found = trader.operation(operation_id)
                order = found.get("order") or {}
                legs[operation_id] = LegResult(
                    contract=str(order.get("contract_code") or ""),
                    side=str(order.get("side") or ""),
                    offset=str(order.get("offset") or ""),
                    quantity=int(order.get("quantity") or 0),
                    price=order.get("price"),
                    status=str(order.get("status") or found.get("status") or ""),
                    filled=int(order.get("filled_quantity") or 0),
                    operation_id=operation_id,
                    error=str(found.get("error_message") or ""),
                )
            return all(leg.status not in WORKING for leg in legs.values())

        _wait(refresh_legs, wait_seconds, sleep)
        result["legs"] = list(legs.values())
        after = _net_positions(trader.positions(), products)
        result["after"] = after
    except ExecutionRefused as exc:
        return ExecutionResult("blocked", str(exc), **result)
    except (PandaCliError, TimeoutError, ValueError, KeyError) as exc:
        return ExecutionResult("error", f"{type(exc).__name__}: {exc}", **result)

    statuses = {leg.status for leg in result["legs"]}
    held = {symbol: units for symbol, units in wanted.items() if units}
    if UNKNOWN in statuses:
        return ExecutionResult("unknown", "有委托回报不明，停止自动下单直到核实", **result)
    if after == held:
        return ExecutionResult("filled", **result)
    if statuses & WORKING:
        return ExecutionResult("working", "部分委托仍在挂单，下一根 K 线撤单重下", **result)
    failed = [leg for leg in result["legs"] if leg.status != FILLED]
    detail = "；".join(
        f"{leg.contract} {leg.side} {leg.offset}: {leg.status} {leg.error}" for leg in failed
    )
    return ExecutionResult("rejected", detail or "持仓与目标不一致", **result)


__all__ = [
    "DEFAULT_WAIT_SECONDS",
    "ExecutionRefused",
    "ExecutionResult",
    "LegResult",
    "PandaTrader",
    "check_account",
    "execute_targets",
    "product_of",
]
