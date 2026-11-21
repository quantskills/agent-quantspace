from __future__ import annotations

import json

import pytest

from skills.live_trade import DeliveryResult, SignalLedger, TargetSnapshot, build_signal
from skills.live_trade.ledger import MAX_SIGNALS


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "a..b", ".hidden", "a b"])
def test_strategy_id_must_be_one_safe_path_segment(bad, tmp_path):
    with pytest.raises(ValueError, match="Invalid strategy id"):
        SignalLedger(bad, tmp_path)


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
