from __future__ import annotations

import json
import sys
import threading
import time

import pytest

from skills.live_trade import DeliveryResult, SignalLedger, TargetSnapshot, build_signal
from skills.live_trade.ledger import (
    MAX_SIGNALS,
    replace_file,
    validate_strategy_id,
    write_json_atomic,
)


# Windows drops a trailing dot from folder names and reserves device names such as NUL.
@pytest.mark.parametrize(
    "bad", ["", "../x", "a/b", "a..b", ".hidden", "a b", "demo.", "con", "NUL", "com1", "Lpt9.x"]
)
def test_strategy_id_must_be_one_safe_path_segment(bad, tmp_path):
    with pytest.raises(ValueError, match="Invalid strategy id"):
        SignalLedger(bad, tmp_path)


@pytest.mark.parametrize("good", ["rb_ma_cross_5m", "etf.v2", "console", "com10", "nul_1"])
def test_strategy_ids_that_are_safe_everywhere_pass(good):
    assert validate_strategy_id(good) == good


def test_replace_is_retried_while_the_target_is_in_use(tmp_path, monkeypatch):
    import skills.live_trade.ledger as module

    source, target = tmp_path / "new.json", tmp_path / "state.json"
    source.write_text("new"), target.write_text("old")
    real, refusals, waits = module.os.replace, [2], []

    def replace(src, dst):
        if refusals[0]:
            refusals[0] -= 1
            raise PermissionError(13, "The process cannot access the file")
        real(src, dst)

    monkeypatch.setattr(module.os, "replace", replace)
    replace_file(source, target, sleep=waits.append)
    assert (target.read_text(), waits) == ("new", [0.1, 0.1])

    source.write_text("newer")
    refusals[0] = 99
    with pytest.raises(PermissionError):
        replace_file(source, target, retries=3, sleep=waits.append)
    assert target.read_text() == "new" and len(waits) == 5


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows refuses to replace an open file")
def test_a_state_file_held_open_by_a_reader_is_replaced_once_released(tmp_path):
    path = tmp_path / "runs.json"
    write_json_atomic(path, {"n": 1})
    stream = path.open(encoding="utf-8")
    threading.Timer(0.3, stream.close).start()
    started = time.monotonic()
    write_json_atomic(path, {"n": 2, "detail": "已撤单 ✓"})
    assert time.monotonic() - started >= 0.2
    assert json.loads(path.read_text(encoding="utf-8")) == {"n": 2, "detail": "已撤单 ✓"}
    assert path.read_bytes().count(b"\r") == 0
    assert [item.name for item in tmp_path.iterdir()] == ["runs.json"]


def test_partial_delivery_keeps_base_until_every_channel_succeeds(weights, tmp_path):
    ledger = SignalLedger("demo", tmp_path)
    assert ledger.path == tmp_path.resolve() / "live" / "demo" / "ledger.json"
    signal = build_signal(TargetSnapshot.from_frames(weights, "demo"), ledger.base_weights())

    complete = ledger.record(
        signal,
        [DeliveryResult("wecom-1", True), DeliveryResult("slack-2", False, "500")],
        ["wecom-1", "slack-2"],
    )
    assert not complete
    assert ledger.base_weights() == {}
    assert ledger.delivered_channels(signal.signal_id) == {"wecom-1"}

    # The rerun rebuilds the same signal against the unchanged base.
    again = build_signal(TargetSnapshot.from_frames(weights, "demo"), ledger.base_weights())
    assert again.signal_id == signal.signal_id
    assert ledger.record(again, [DeliveryResult("slack-2", True)], ["wecom-1", "slack-2"])
    assert ledger.base_weights() == signal.target
    state = json.loads(ledger.path.read_text(encoding="utf-8"))
    assert state["signals"][signal.signal_id]["complete"] is True


def test_success_is_never_overwritten_by_a_later_failure(weights, tmp_path):
    ledger = SignalLedger("demo", tmp_path)
    signal = build_signal(TargetSnapshot.from_frames(weights, "demo"))
    ledger.record(signal, [DeliveryResult("wecom-1", True)], ["wecom-1", "slack-2"])
    ledger.record(signal, [DeliveryResult("wecom-1", False, "late")], ["wecom-1", "slack-2"])
    assert ledger.delivered_channels(signal.signal_id) == {"wecom-1"}


def test_ledger_keeps_only_recent_signals(weights, tmp_path):
    ledger = SignalLedger("demo", tmp_path)
    snapshot = TargetSnapshot.from_frames(weights, "demo")
    for index in range(MAX_SIGNALS + 5):
        signal = build_signal(snapshot, {"510300.SH": index / 1000})
        ledger.record(signal, [DeliveryResult("wecom-1", False)], ["wecom-1"])
    state = json.loads(ledger.path.read_text(encoding="utf-8"))
    assert len(state["signals"]) == MAX_SIGNALS
