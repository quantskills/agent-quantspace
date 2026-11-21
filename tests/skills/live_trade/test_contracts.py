from __future__ import annotations

import pandas as pd
import pytest

from skills.live_trade import TargetSnapshot, build_signal, diff_weights, is_futures_symbol


def test_snapshot_uses_last_row_and_drops_zero_or_missing_weights(weights, prices):
    snapshot = TargetSnapshot.from_frames(weights, "demo", prices=prices)
    assert snapshot.as_of == "2026-11-19"
    assert snapshot.weights == {"510300.SH": 0.35, "M2605.DCE": -0.4}
    assert snapshot.prices["510300.SH"] == pytest.approx(4.123)


def test_snapshot_as_of_takes_row_at_or_before(weights):
    snapshot = TargetSnapshot.from_frames(weights, "demo", as_of="2026-11-18 15:00")
    assert snapshot.as_of == "2026-11-18"
    assert snapshot.weights["RB2601.SHF"] == 0.25
    with pytest.raises(ValueError, match="no row at or before"):
        TargetSnapshot.from_frames(weights, "demo", as_of="2026-11-01")


def test_snapshot_keeps_intraday_time_and_leaves_missing_prices_missing():
    index = pd.DatetimeIndex(["2026-11-19 14:50"], name="eob")
    weights = pd.DataFrame({"510300.SH": [1.0], "159915.SZ": [0.0]}, index=index)
    prices = pd.DataFrame({"510300.SH": [float("nan")]}, index=index)
    snapshot = TargetSnapshot.from_frames(weights, "demo", prices=prices)
    assert snapshot.as_of == "2026-11-19 14:50:00"
    assert snapshot.prices == {}


def test_snapshot_rejects_tables_without_time_index():
    with pytest.raises(ValueError, match="datetime index"):
        TargetSnapshot.from_frames(pd.DataFrame({"510300.SH": [1.0]}), "demo")


def test_diff_includes_exits_and_ignores_tiny_moves():
    changes = diff_weights(
        {"510300.SH": 0.5, "159915.SZ": 0.5}, {"510300.SH": 0.5 + 1e-9, "M2605.DCE": -0.4}
    )
    assert [(c.symbol, c.previous, c.target) for c in changes] == [
        ("159915.SZ", 0.5, 0.0),
        ("M2605.DCE", 0.0, -0.4),
    ]
    assert changes[0].delta == -0.5


def test_signal_id_is_deterministic_and_depends_on_base(weights):
    snapshot = TargetSnapshot.from_frames(weights, "demo")
    first = build_signal(snapshot, {"510300.SH": 0.5})
    assert first.signal_id == build_signal(snapshot, {"510300.SH": 0.5}).signal_id
    assert first.signal_id != build_signal(snapshot, {}).signal_id
    assert build_signal(snapshot, snapshot.weights).is_empty


def test_futures_symbols_are_detected_by_exchange():
    assert is_futures_symbol("RB2601.SHF")
    assert is_futures_symbol("IF2612.CFE")
    assert not is_futures_symbol("510300.SH")
