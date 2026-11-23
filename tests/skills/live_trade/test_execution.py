"""Automatic SimNow orders: account checks, cancels, target plans, and run_bar wiring."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from skills.live_trade.execution import (
    ExecutionResult,
    PandaTrader,
    execute_targets,
    product_of,
)

from .test_panda_cli import ACCOUNTS

CONNECTED = {"connected": True, "cli_ready": True, "connection_status": "CONNECTED"}


class FakeClient:
    """Answers the CLI calls PandaTrader makes; legs end in ``outcome`` (FILLED by default)."""

    def __init__(self, positions=None, orders=None, outcome="FILLED"):
        self.accounts = ACCOUNTS
        self.connection = dict(CONNECTED)
        self.net = dict(positions or {})
        self.orders = list(orders or [])
        self.outcome = outcome
        self.stuck_cancels = False
        self.calls: list[tuple] = []
        self.envs: list[dict] = []
        self.plans: dict[str, list[dict]] = {}
        self.submitted: dict[str, int] = {}
        self.operations: dict[str, dict] = {}

    def __call__(self, command, *args, env=None):
        self.calls.append(args)
        self.envs.append(dict(env or {}))
        name = args[0]
        if name == "accounts":
            return self.accounts
        if name == "connection":
            return {"connection": self.connection}
        if name == "positions":
            return {"items": self._position_items()}
        if name == "orders":
            return {"items": self.orders}
        if name == "cancel":
            order_id = args[args.index("--order-id") + 1]
            for order in self.orders:
                if order["cli_order_id"] == order_id and not self.stuck_cancels:
                    order["status"] = "CANCELLED"
            return {"status": "SUBMITTED"}
        if name == "target-position":
            return self._plan(json.loads(args[args.index("--targets") + 1]))
        if name == "plan":
            return self._execute(args[args.index("--plan-id") + 1])
        if name == "operation":
            return self.operations[args[args.index("--id") + 1]]
        raise AssertionError(f"unexpected CLI call {args}")

    def _position_items(self):
        return [
            {"symbol": symbol, "direction": "long" if units > 0 else "short", "volume": abs(units)}
            for symbol, units in self.net.items()
            if units
        ]

    def _plan(self, targets):
        legs = []
        for target in targets:
            symbol = target["symbol"]
            want = target["volume"] * (1 if target["direction"] == "long" else -1)
            have = self.net.get(symbol, 0)
            if have and (want == 0 or (want > 0) != (have > 0)):
                legs.append((symbol, "SELL" if have > 0 else "BUY", "CLOSETODAY", abs(have)))
                have = 0
            if want != have:
                side = "BUY" if want > have else "SELL"
                legs.append((symbol, side, "OPEN", abs(want - have)))
        plan_id = f"plan-{len(self.plans) + 1}"
        self.plans[plan_id] = [
            {"symbol": s, "side": side, "offset": offset, "quantity": q}
            for s, side, offset, q in legs
        ]
        return {"plan_id": plan_id, "legs": self.plans[plan_id]}

    def _execute(self, plan_id):
        """Like the client: each call submits the next leg once the earlier ones filled."""
        submitted = self.submitted.setdefault(plan_id, 0)
        earlier = [f"{plan_id}-op{number}" for number in range(1, submitted + 1)]
        done = all(self.operations[op]["status"] == "FILLED" for op in earlier)
        if done and submitted < len(self.plans[plan_id]):
            self._submit(plan_id, submitted + 1, self.plans[plan_id][submitted])
            self.submitted[plan_id] = submitted + 1
        results = [
            {"result": {"operation_id": f"{plan_id}-op{number}"}}
            for number in range(1, self.submitted[plan_id] + 1)
        ]
        return {"status": "SUBMITTED", "result_json": json.dumps({"legs": results})}

    def _submit(self, plan_id, number, leg):
        filled = leg["quantity"] if self.outcome == "FILLED" else 0
        if filled:
            sign = 1 if leg["side"] == "BUY" else -1
            self.net[leg["symbol"]] = self.net.get(leg["symbol"], 0) + sign * filled
        self.operations[f"{plan_id}-op{number}"] = {
            "status": self.outcome,
            "error_message": "资金不足" if self.outcome == "REJECTED" else None,
            "order": {
                "contract_code": leg["symbol"].partition(".")[0].lower(),
                "side": leg["side"],
                "offset": leg["offset"],
                "quantity": leg["quantity"],
                "price": 2980.0,
                "status": self.outcome,
                "filled_quantity": filled,
            },
        }

    def names(self):
        return [call[0] for call in self.calls]


def _trade(client, wanted, account="100001"):
    trader = PandaTrader(["panda"], account, trace_id="rb-0905", runner=client)
    return execute_targets(
        trader, wanted, request_id="rb:0905", wait_seconds=0.05, sleep=lambda _: None
    )


def test_products_are_read_from_any_code():
    assert {product_of(code) for code in ("RB2701.SHF", "rb2701", "RB_DOMINANT.SHF")} == {"RB"}


def test_only_simnow_accounts_are_traded():
    client = FakeClient()
    result = _trade(client, {"RB2701.SHF": 1}, account="200002")
    assert result.status == "blocked" and "不是 SimNow 账号" in result.detail
    assert "target-position" not in client.names() and "plan" not in client.names()

    missing = _trade(FakeClient(), {"RB2701.SHF": 1}, account="999999")
    assert missing.status == "blocked" and "no account 999999" in missing.detail


def test_an_unready_counter_blocks_before_any_order():
    client = FakeClient()
    client.connection = {"connected": True, "cli_ready": False, "connection_status": "SYNCING"}
    result = _trade(client, {"RB2701.SHF": 1})
    assert (result.status, result.detail) == ("blocked", "柜台未就绪（SYNCING）")
    assert client.names() == ["accounts", "connection"]


def test_opening_a_target_executes_one_frozen_plan_and_reports_fills():
    client = FakeClient()
    result = _trade(client, {"RB2701.SHF": 2})

    assert (result.status, result.before, result.after) == ("filled", {}, {"RB2701.SHF": 2})
    assert result.account == "simnow_demo（100001）"
    (leg,) = result.legs
    assert (leg.side, leg.offset, leg.quantity, leg.filled) == ("BUY", "OPEN", 2, 2)
    plan_call = next(call for call in client.calls if call[0] == "target-position")
    assert json.loads(plan_call[plan_call.index("--targets") + 1]) == [
        {"symbol": "RB2701.SHF", "direction": "long", "volume": 2}
    ]
    execute_call = next(call for call in client.calls if call[0] == "plan")
    assert execute_call[:5] == ("plan", "execute", "--plan-id", "plan-1", "--yes")
    assert all(env == {"PANDA_LIVE_TRACE_ID": "rb-0905"} for env in client.envs)
    assert result.ok and json.loads(json.dumps(result.to_dict()))["legs"][0]["filled"] == 2


def test_a_held_target_does_nothing():
    client = FakeClient(positions={"RB2701.SHF": 1})
    result = _trade(client, {"RB2701.SHF": 1})
    assert result.status == "in_position" and "target-position" not in client.names()


def test_flat_closes_the_held_side_and_old_months_go_to_zero():
    client = FakeClient(positions={"RB2610.SHF": -1, "RB2701.SHF": 1, "HC2701.SHF": 3})

    result = _trade(client, {"RB2701.SHF": 0})

    plan_call = next(call for call in client.calls if call[0] == "target-position")
    assert json.loads(plan_call[plan_call.index("--targets") + 1]) == [
        {"symbol": "RB2610.SHF", "direction": "short", "volume": 0},
        {"symbol": "RB2701.SHF", "direction": "long", "volume": 0},
    ]
    assert result.status == "filled" and result.after == {}
    assert client.net["HC2701.SHF"] == 3  # other products are left alone


def test_reversal_and_leftover_orders_are_cancelled_first():
    working = {"cli_order_id": "o-1", "contract_code": "rb2701", "status": "ACCEPTED"}
    other = {"cli_order_id": "o-2", "contract_code": "hc2701", "status": "ACCEPTED"}
    client = FakeClient(positions={"RB2701.SHF": 1}, orders=[working, other])

    result = _trade(client, {"RB2701.SHF": -1})

    assert result.cancelled == ["o-1"] and other["status"] == "ACCEPTED"
    cancel = next(call for call in client.calls if call[0] == "cancel")
    assert cancel[cancel.index("--client-request-id") + 1] == "rb:0905:cancel:o-1"
    assert [(leg.side, leg.offset) for leg in result.legs] == [
        ("SELL", "CLOSETODAY"),
        ("SELL", "OPEN"),
    ]
    assert result.status == "filled" and result.after == {"RB2701.SHF": -1}


def test_a_roll_closes_the_old_month_before_opening_the_new_one():
    client = FakeClient(positions={"RB2705.SHF": 1})

    result = _trade(client, {"RB2701.SHF": 1})

    plan_call = next(call for call in client.calls if call[0] == "target-position")
    assert json.loads(plan_call[plan_call.index("--targets") + 1]) == [
        {"symbol": "RB2705.SHF", "direction": "long", "volume": 0},
        {"symbol": "RB2701.SHF", "direction": "long", "volume": 1},
    ]
    # One plan, executed once per leg: the open waits for the close to fill.
    assert client.names().count("target-position") == 1 and client.names().count("plan") == 2
    assert [(leg.contract, leg.side, leg.offset) for leg in result.legs] == [
        ("rb2705", "SELL", "CLOSETODAY"),
        ("rb2701", "BUY", "OPEN"),
    ]
    assert result.status == "filled" and result.after == {"RB2701.SHF": 1}


def test_a_close_that_does_not_fill_holds_back_the_open():
    client = FakeClient(positions={"RB2701.SHF": 1}, outcome="ACCEPTED")

    result = _trade(client, {"RB2701.SHF": -1})

    assert [(leg.side, leg.offset, leg.status) for leg in result.legs] == [
        ("SELL", "CLOSETODAY", "ACCEPTED")
    ]
    assert result.status == "working" and client.names().count("plan") == 1


def test_a_cancel_that_does_not_finish_places_no_new_order():
    client = FakeClient(
        orders=[{"cli_order_id": "o-1", "contract_code": "rb2701", "status": "ACCEPTED"}]
    )
    client.stuck_cancels = True
    result = _trade(client, {"RB2701.SHF": 1})
    assert result.status == "pending_cancel" and "target-position" not in client.names()


def test_an_unknown_order_stops_trading():
    client = FakeClient(
        orders=[{"cli_order_id": "o-9", "contract_code": "rb2701", "status": "UNKNOWN"}]
    )
    result = _trade(client, {"RB2701.SHF": 1})
    assert result.status == "unknown" and "o-9" in result.detail
    assert "cancel" not in client.names() and "target-position" not in client.names()


@pytest.mark.parametrize(
    ("outcome", "status"),
    [("ACCEPTED", "working"), ("REJECTED", "rejected"), ("UNKNOWN", "unknown")],
)
def test_orders_that_do_not_fill(outcome, status):
    result = _trade(FakeClient(outcome=outcome), {"RB2701.SHF": 1})
    assert result.status == status and result.after == {}
    if outcome == "REJECTED":
        assert "资金不足" in result.detail


def test_queries_are_tried_twice_but_orders_never(monkeypatch):
    import skills.live_trade.execution as module
    from skills.live_trade.panda_cli import PandaCliError

    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    client, failures = FakeClient(), {"accounts": 1, "plan": 1}

    def flaky(command, *args, env=None):
        if failures.get(args[0]):
            failures[args[0]] -= 1
            client.calls.append(args)
            raise PandaCliError("printed no JSON (exit 1)")
        return client(command, *args, env=env)

    trader = PandaTrader(["panda"], "100001", runner=flaky)
    result = execute_targets(trader, {"RB2701.SHF": 1}, request_id="x", sleep=lambda _: None)

    assert client.names().count("accounts") == 2 and client.names().count("plan") == 1
    assert result.status == "error" and "printed no JSON" in result.detail


def test_cli_failures_become_errors():
    from skills.live_trade.panda_cli import PandaCliError

    def broken(command, *args, env=None):
        if args[0] == "accounts":
            return ACCOUNTS
        raise PandaCliError("客户端未启动", 1)

    trader = PandaTrader(["panda"], "100001", runner=broken)
    result = execute_targets(trader, {"RB2701.SHF": 1}, request_id="x", sleep=lambda _: None)
    assert (result.status, result.detail) == ("error", "PandaCliError: 客户端未启动")


# --------------------------------------------------------------------------- run_bar wiring


def _bar_run(tmp_path, execute, **options):
    from skills.live_trade.feeds import MinuteFeed
    from skills.live_trade.minute import refresh_day, run_bar

    from .conftest import FEISHU
    from .fakes import RB_SPEC, FakePandaData, FakeSina
    from .test_minute import BAR, READY, _above_3000

    sina = FakeSina()
    sina.add("RB2701", (BAR, 3010.0))
    feed = MinuteFeed(RB_SPEC, FakePandaData(), data_root=tmp_path, akshare=sina, pause=0)
    refresh_day(RB_SPEC, feed, _above_3000, now=datetime(2026, 11, 20, 18, 0), data_root=tmp_path)
    return run_bar(
        RB_SPEC,
        feed,
        _above_3000,
        bar=BAR,
        now=READY,
        data_root=tmp_path,
        urls=[FEISHU],
        execute=execute,
        **options,
    )


def test_run_bar_trades_the_sized_actual_contract_and_pushes_the_fills(tmp_path, http):
    from skills.live_trade.runner import RunLog

    from .test_minute import BAR

    client, seen = FakeClient(), []

    def execute(wanted, request_id):
        seen.append((dict(wanted), request_id))
        return _trade(client, wanted)

    outcome = _bar_run(tmp_path, execute, write=True, capital=100_000)

    # 100000 / (3010 * 10) = 3.3 contracts, rounded toward zero
    assert seen == [({"RB2701.SHF": 3}, "rb_demo:2026-11-20T21:05")]
    assert outcome.status == "sent" and outcome.execution.status == "filled"
    entry = RunLog("rb_demo", tmp_path).get(BAR)
    assert entry["execution"]["after"] == {"RB2701.SHF": 3}
    texts = [json.loads(item["body"])["content"]["text"] for item in http.sent]
    trade = next(text for text in texts if "类型：trade" in text)
    assert "RB2701.SHF +3" in trade and "BUY OPEN 3 手" in trade


def test_run_bar_alerts_execution_problems_once_a_day(tmp_path, http):
    def execute(wanted, request_id):
        return ExecutionResult("blocked", "柜台未就绪（SYNCING）", account="simnow_demo（100001）")

    outcome = _bar_run(tmp_path, execute, write=True, capital=100_000)

    assert outcome.status == "sent" and outcome.execution.status == "blocked"
    texts = [json.loads(item["body"])["content"]["text"] for item in http.sent]
    (alert,) = [text for text in texts if "execution_blocked" in text]
    assert "柜台未就绪" in alert and "simnow_demo（100001）" in alert


def test_run_bar_without_capital_or_write_places_no_order(tmp_path, http):
    calls = []

    def execute(wanted, request_id):
        calls.append(wanted)
        return ExecutionResult("filled")

    preview = _bar_run(tmp_path, execute, capital=100_000)
    assert preview.execution is None and calls == []

    missing = _bar_run(tmp_path / "other", execute, write=True)
    assert missing.execution.status == "error" and "--capital" in missing.execution.detail
    assert calls == []


def test_run_bar_places_no_order_above_max_lots(tmp_path, http):
    calls = []

    def execute(wanted, request_id):
        calls.append(wanted)
        return ExecutionResult("filled")

    # 100000 / (3010 * 10) = 3 contracts, above the cap of 2
    outcome = _bar_run(tmp_path, execute, write=True, capital=100_000, max_lots=2)

    assert calls == [] and outcome.status == "sent"
    assert outcome.execution.status == "over_limit"
    assert "3 units > max 2" in outcome.execution.detail
    texts = [json.loads(item["body"])["content"]["text"] for item in http.sent]
    (alert,) = [text for text in texts if "execution_over_limit" in text]
    assert "超过单合约上限" in alert

    within = _bar_run(tmp_path / "within", execute, write=True, capital=100_000, max_lots=3)
    assert within.execution.status == "filled" and calls == [{"RB2701.SHF": 3}]


def test_a_stop_file_skips_orders_but_not_the_signal(tmp_path, http):
    from skills.live_trade.minute import stop_file
    from skills.live_trade.runner import RunLog

    from .test_minute import BAR

    calls = []

    def execute(wanted, request_id):
        calls.append(wanted)
        return ExecutionResult("filled")

    stop = stop_file("rb_demo", tmp_path)
    stop.parent.mkdir(parents=True)
    stop.write_text("", encoding="utf-8")

    outcome = _bar_run(tmp_path, execute, write=True, capital=100_000)

    assert calls == [] and outcome.status == "sent"
    assert outcome.execution.status == "stopped" and str(stop) in outcome.execution.detail
    assert RunLog("rb_demo", tmp_path).get(BAR)["execution"]["status"] == "stopped"
    texts = [json.loads(item["body"])["content"]["text"] for item in http.sent]
    (alert,) = [text for text in texts if "execution_stopped" in text]
    assert "紧急停止文件" in alert


def test_trading_problems_lists_every_reason_and_skips_real_accounts():
    from skills.live_trade.execution import trading_problems

    client = FakeClient()
    client.accounts = [
        {**ACCOUNTS[0], "cliEligible": False, "cliUnavailableReason": "未开启 CLI 模式"},
        ACCOUNTS[1],
    ]
    account, problems = trading_problems(PandaTrader(["panda"], "100001", runner=client))
    assert account.code == "100001" and problems == ["未开启 CLI 模式"]

    account, problems = trading_problems(PandaTrader(["panda"], "200002", runner=client))
    assert account.code == "200002" and "不是 SimNow 账号" in problems[0]
    assert "connection" not in client.names()

    account, problems = trading_problems(PandaTrader(["panda"], "100001", runner=FakeClient()))
    assert problems == []
