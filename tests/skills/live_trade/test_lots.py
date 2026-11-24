"""Lots strategies live: signals in lots, messages, the ledger's unit, orders without capital."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

import pandas as pd
import pytest

from skills.live_trade.contracts import TargetSnapshot, build_signal
from skills.live_trade.execution import ExecutionResult
from skills.live_trade.ledger import SignalLedger
from skills.live_trade.runner import LiveInputs, deliver_signal, futures_lots, run_live
from skills.live_trade.sizing import SizingLimitError

from .conftest import FEISHU

MONDAY = date(2026, 11, 23)


def table(values: dict[str, list[float]], days=("2026-11-20", "2026-11-23")) -> pd.DataFrame:
    return pd.DataFrame(values, index=pd.DatetimeIndex(pd.to_datetime(list(days)), name="eob"))


def texts(http) -> list[str]:
    return [json.loads(item["body"])["content"]["text"] for item in http.sent]


# --------------------------------------------------------------------- snapshot and signal


def test_lots_snapshot_keeps_whole_lots_and_refuses_fractions():
    snapshot = TargetSnapshot.from_frames(
        table({"RB_DOMINANT.SHF": [1, 3], "600000.SH": [0, 30]}), "demo", unit="lots"
    )
    assert snapshot.unit == "lots"
    assert snapshot.weights == {"RB_DOMINANT.SHF": 3.0, "600000.SH": 30.0}
    with pytest.raises(ValueError, match="whole number"):
        TargetSnapshot.from_frames(table({"RB_DOMINANT.SHF": [1, 1.5]}), "demo", unit="lots")
    with pytest.raises(ValueError, match="cannot be short"):
        TargetSnapshot.from_frames(table({"600000.SH": [1, -2]}), "demo", unit="lots")
    with pytest.raises(ValueError, match="unit must be"):
        TargetSnapshot.from_frames(table({"600000.SH": [1, 2]}), "demo", unit="shares")


def test_percent_signal_ids_hash_what_they_always_did():
    snapshot = TargetSnapshot.from_frames(table({"510300.SH": [0.5, 0.6]}), "demo")
    signal = build_signal(snapshot, {"510300.SH": 0.5})
    payload = json.dumps(
        {
            "strategy_id": "demo",
            "as_of": "2026-11-23",
            "base": {"510300.SH": 0.5},
            "target": {"510300.SH": 0.6},
        },
        sort_keys=True,
    )
    assert signal.signal_id == hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    assert signal.unit == "percent"


def test_lots_signal_ids_differ_from_the_same_numbers_in_percent():
    frame = table({"RB_DOMINANT.SHF": [1, 2]})
    percent = build_signal(TargetSnapshot.from_frames(frame, "demo"))
    lots = build_signal(TargetSnapshot.from_frames(frame, "demo", unit="lots"))
    assert lots.signal_id != percent.signal_id
    assert lots.unit == "lots" and lots.target == {"RB_DOMINANT.SHF": 2.0}


# --------------------------------------------------------------------- delivery and ledger


def test_lots_messages_show_lots_shares_value_and_no_capital_is_needed(tmp_path):
    frame = table({"RB_DOMINANT.SHF": [0, 3], "600000.SH": [0, 30]})
    prices = table({"RB_DOMINANT.SHF": [2990, 2999], "600000.SH": [10.8, 10.87]})
    snapshot = TargetSnapshot.from_frames(frame, "demo", prices=prices, unit="lots")
    ledger = SignalLedger("demo", tmp_path)

    plain = deliver_signal(
        snapshot, ledger, write=False, urls=[], multipliers={"RB_DOMINANT.SHF": 10}
    )
    assert plain.status == "preview"
    assert "- 600000.SH：目标 30 手（3000 股，原 0 手），参考价 10.87，名义 32610" in plain.body
    assert "- RB_DOMINANT.SHF：目标 3 手（原 0 手），参考价 2999，名义 89970" in plain.body
    assert "折合" not in plain.body and "%" not in plain.body

    with_capital = deliver_signal(
        snapshot,
        ledger,
        write=False,
        urls=[],
        capital=100_000,
        multipliers={"RB_DOMINANT.SHF": 10},
    )
    assert "名义 89970，折合 89.97%" in with_capital.body
    assert with_capital.sized["600000.SH"].units == 3000
    assert with_capital.sized["RB_DOMINANT.SHF"].units == 3


def test_lots_signals_diff_against_the_delivered_lots(tmp_path, http):
    ledger = SignalLedger("demo", tmp_path)
    first = TargetSnapshot.from_frames(table({"RB_DOMINANT.SHF": [0, 2]}), "demo", unit="lots")
    assert deliver_signal(first, ledger, write=True, urls=[FEISHU]).status == "sent"
    assert ledger.base_unit() == "lots" and ledger.base_weights("lots") == {"RB_DOMINANT.SHF": 2}

    same = TargetSnapshot.from_frames(
        table({"RB_DOMINANT.SHF": [2, 2]}, days=("2026-11-23", "2026-11-24")), "demo", unit="lots"
    )
    assert deliver_signal(same, ledger, write=True, urls=[FEISHU]).status == "unchanged"

    more = TargetSnapshot.from_frames(
        table({"RB_DOMINANT.SHF": [2, 3]}, days=("2026-11-23", "2026-11-24")), "demo", unit="lots"
    )
    delivery = deliver_signal(more, ledger, write=True, urls=[FEISHU])
    assert delivery.status == "sent"
    assert "目标 3 手（原 2 手）" in texts(http)[-1]


def test_a_percent_ledger_keeps_no_unit_and_a_unit_change_resets_the_baseline(tmp_path, http):
    ledger = SignalLedger("demo", tmp_path)
    percent = TargetSnapshot.from_frames(table({"RB_DOMINANT.SHF": [0, 1.0]}), "demo")
    deliver_signal(percent, ledger, write=True, urls=[FEISHU])
    stored = json.loads(ledger.path.read_text(encoding="utf-8"))["base"]
    assert "unit" not in stored and ledger.base_unit() == "percent"

    lots = TargetSnapshot.from_frames(
        table({"RB_DOMINANT.SHF": [1, 3]}, days=("2026-11-23", "2026-11-24")), "demo", unit="lots"
    )
    delivery = deliver_signal(lots, ledger, write=True, urls=[FEISHU])
    # The percent base (1.0) is not compared with 3 lots: the whole target goes out.
    assert [(c.previous, c.target) for c in delivery.signal.changes] == [(0.0, 3.0)]
    assert "单位从 percent 改为 lots，账本基线已重置" in delivery.body
    assert ledger.base_unit() == "lots"
    assert ledger.base_weights("percent") == {}


# --------------------------------------------------------------------- orders


def test_lots_orders_are_the_target_contracts_without_capital():
    wanted = futures_lots(
        {"RB_DOMINANT.SHF": -2.0},
        {},
        contracts={"RB_DOMINANT.SHF": "RB2701.SHF"},
        multipliers={},
        capital=None,
        unit="lots",
    )
    assert wanted == {"RB2701.SHF": -2}
    with pytest.raises(SizingLimitError, match="RB_DOMINANT.SHF: 3 units > max 2"):
        futures_lots(
            {"RB_DOMINANT.SHF": 3.0},
            {},
            contracts={"RB_DOMINANT.SHF": "RB2701.SHF"},
            multipliers={},
            capital=None,
            max_lots=2,
            unit="lots",
        )
    with pytest.raises(ValueError, match="only wired for futures"):
        futures_lots(
            {"600000.SH": 1.0}, {}, contracts={}, multipliers={}, capital=None, unit="lots"
        )


def test_daily_lots_run_trades_the_lots_and_signals_them(tmp_path, http):
    seen = []

    def execute(wanted, request_id):
        seen.append(dict(wanted))
        return ExecutionResult("filled", after={"RB2701.SHF": 2})

    def load() -> LiveInputs:
        return LiveInputs(
            weights=table({"RB_DOMINANT.SHF": [1, 2]}),
            prices=table({"RB_DOMINANT.SHF": [3000, 3010]}),
            multipliers={"RB_DOMINANT.SHF": 10.0},
            contracts={"RB_DOMINANT.SHF": "RB2701.SHF"},
        )

    outcome = run_live(
        "rb_lots",
        load,
        trade_date=MONDAY,
        is_trading_day=True,
        write=True,
        data_root=tmp_path,
        urls=[FEISHU],
        execute=execute,
        unit="lots",
    )
    assert outcome.status == "sent" and outcome.execution.status == "filled"
    assert seen == [{"RB2701.SHF": 2}]
    assert "目标 2 手（原 0 手），参考价 3010，名义 60200" in texts(http)[0]


def test_daily_lots_run_with_fractional_lots_is_an_error(tmp_path, http):
    def load() -> LiveInputs:
        return LiveInputs(weights=table({"RB_DOMINANT.SHF": [1, 0.5]}))

    outcome = run_live(
        "rb_lots",
        load,
        trade_date=MONDAY,
        is_trading_day=True,
        write=True,
        data_root=tmp_path,
        urls=[FEISHU],
        unit="lots",
    )
    assert outcome.status == "error" and "whole number" in outcome.detail
    assert any("类型：error" in text for text in texts(http))


def _lots_bar_run(tmp_path, execute, **options):
    from skills.live_trade.feeds import MinuteFeed
    from skills.live_trade.minute import refresh_day, run_bar

    from .fakes import RB_SPEC, FakePandaData, FakeSina
    from .test_minute import BAR, READY

    spec = RB_SPEC.model_copy(update={"unit": "lots"})

    def two_lots_above_3000(panel: pd.DataFrame) -> pd.DataFrame:
        close = panel["close"].unstack("symbol").sort_index()
        return (close > 3000).astype(float) * 2

    sina = FakeSina()
    sina.add("RB2701", (BAR, 3010.0))
    feed = MinuteFeed(spec, FakePandaData(), data_root=tmp_path, akshare=sina, pause=0)
    refresh_day(spec, feed, two_lots_above_3000, now=datetime(2026, 11, 20, 18), data_root=tmp_path)
    return run_bar(
        spec,
        feed,
        two_lots_above_3000,
        bar=BAR,
        now=READY,
        data_root=tmp_path,
        urls=[FEISHU],
        execute=execute,
        **options,
    )


def test_minute_lots_bar_trades_the_lots_without_capital(tmp_path, http):
    seen = []

    def execute(wanted, request_id):
        seen.append(dict(wanted))
        return ExecutionResult("filled", after={"RB2701.SHF": 2})

    outcome = _lots_bar_run(tmp_path, execute, write=True)
    assert outcome.status == "sent" and outcome.execution.status == "filled"
    assert seen == [{"RB2701.SHF": 2}]
    signal_text = next(text for text in texts(http) if "调仓信号" in text)
    assert "RB_DOMINANT.SHF：目标 2 手（原 0 手），参考价 3010，名义 60200" in signal_text


def test_minute_lots_bar_over_max_lots_places_no_order(tmp_path, http):
    calls = []

    def execute(wanted, request_id):
        calls.append(wanted)
        return ExecutionResult("filled")

    outcome = _lots_bar_run(tmp_path, execute, write=True, max_lots=1)
    assert calls == [] and outcome.execution.status == "over_limit"
    assert "2 units > max 1" in outcome.execution.detail


def test_notify_command_takes_lots(capsys, tmp_path):
    from skills.cli import main

    path = tmp_path / "lots.parquet"
    table({"RB_DOMINANT.SHF": [1, 2]}).to_parquet(path)
    prices = tmp_path / "prices.parquet"
    table({"RB_DOMINANT.SHF": [3000, 3010]}).to_parquet(prices)
    multipliers = tmp_path / "multipliers.json"
    multipliers.write_text('{"RB_DOMINANT.SHF": 10}')
    code = main(
        [
            "live-trade",
            "notify",
            "--weights",
            str(path),
            "--strategy-id",
            "rb_lots",
            "--unit",
            "lots",
            "--prices",
            str(prices),
            "--multipliers",
            str(multipliers),
            "--data-root",
            str(tmp_path / "data"),
        ]
    )
    response = json.loads(capsys.readouterr().out)
    assert code == 0, response
    assert response["data"]["changes"][0]["units"] == 2
    assert "目标 2 手（原 0 手），参考价 3010，名义 60200" in response["data"]["body"]


def test_daily_main_trades_a_lots_strategy_without_capital(tmp_path, http, monkeypatch, capsys):
    from skills.live_trade.workflow import daily_main

    from .fakes import FakePandaData

    seen = []

    def execute_targets(trader, wanted, *, request_id):
        seen.append(dict(wanted))
        return ExecutionResult("filled", account=trader.account)

    monkeypatch.setattr("skills.ingest.PandaDataClient", lambda: FakePandaData())
    monkeypatch.setattr("skills.live_trade.panda_cli.discover_cli", lambda: ["panda-live-trading"])
    monkeypatch.setattr("skills.live_trade.execution.execute_targets", execute_targets)
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)

    def load(client, day, market_dir):
        return LiveInputs(
            weights=table({"RB_DOMINANT.SHF": [1, 2]}),
            prices=table({"RB_DOMINANT.SHF": [3000, 3010]}),
            multipliers={"RB_DOMINANT.SHF": 10.0},
            contracts={"RB_DOMINANT.SHF": "RB2701.SHF"},
        )

    code = daily_main(
        "rb_lots",
        load,
        ["--date", "2026-11-23", "--write", "--account", "100001"]
        + ["--now", "2026-11-23T14:51:05", "--data-root", str(tmp_path)],
        unit="lots",
    )
    report = json.loads(capsys.readouterr().out)
    assert (code, report["status"], report["execution"]["status"]) == (0, "sent", "filled")
    assert seen == [{"RB2701.SHF": 2}]
    assert "目标 2 手（原 0 手）" in report["message"]


def test_daily_main_refuses_an_unknown_unit():
    from skills.live_trade.workflow import daily_main

    with pytest.raises(ValueError, match="unit must be"):
        daily_main("rb_lots", lambda client, day, market_dir: None, [], unit="contracts")
