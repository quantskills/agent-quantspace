"""The 5-minute rebar MA-cross live workflow, run offline on fake PandaData and Sina."""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from skills.live_trade.workflow import replay_mismatches
from strategies.time_series.rules import ma_golden_death_cross_weights
from strategies.time_series.workflows import live_rb_ma_cross_5m as workflow
from tests.skills.live_trade.fakes import FakePandaData, FakeSina


@pytest.fixture
def offline(monkeypatch):
    import skills.ingest
    import skills.ingest.akshare_bars

    sina = FakeSina()
    monkeypatch.setattr(skills.ingest, "PandaDataClient", FakePandaData)
    monkeypatch.setattr(skills.ingest.akshare_bars, "_load_akshare", lambda: sina)
    return sina


def _main(capsys, *argv) -> tuple[int, dict]:
    code = workflow.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def test_spec_matches_the_strategy():
    assert workflow.SPEC.symbols == [workflow.SYMBOL] and workflow.SPEC.futures
    assert workflow.SPEC.warmup_bars == workflow.LONG and workflow.SPEC.adjust == "none"


def test_refresh_then_a_bar_previews_the_backtest_rule(tmp_path, offline, capsys):
    root = str(tmp_path)
    code, refreshed = _main(
        capsys, "--refresh", "--now", "2026-11-20T18:00:00", "--data-root", root
    )
    assert code == 0 and refreshed["status"] == "refreshed"
    assert refreshed["trade_date"] == "2026-11-23" and refreshed["bars_today"] == 69
    assert refreshed["contracts"] == {"RB_DOMINANT.SHF": "RB2701.SHF"}

    offline.add("RB2701", (datetime(2026, 11, 20, 21, 5), 3100.0))  # lifts the 12-bar MA
    code, bar = _main(
        capsys, "--bar", "2026-11-20T21:05:00", "--now", "2026-11-20T21:05:25", "--data-root", root
    )

    assert (code, bar["status"], bar["bar"]) == (0, "preview", "2026-11-20T21:05")
    assert bar["target"] == {"RB_DOMINANT.SHF": 1.0}
    assert "当前对应 RB2701.SHF" in bar["message"]


def test_target_weights_are_the_backtest_function(tmp_path, offline, capsys):
    from skills.live_trade.feeds import MinuteFeed

    _main(capsys, "--refresh", "--now", "2026-11-20T18:00:00", "--data-root", str(tmp_path))
    panel = MinuteFeed(workflow.SPEC, FakePandaData(), data_root=tmp_path).panel()
    bars = panel.xs(workflow.SYMBOL, level="symbol")

    expected = ma_golden_death_cross_weights(bars, workflow.SYMBOL, short=12, long=48)
    assert workflow.target_weights(panel).equals(expected)


def test_a_bar_or_mode_is_required(tmp_path, offline, capsys):
    assert workflow.main(["--data-root", str(tmp_path)]) == 2


def _walk(rows: int = 400) -> pd.DataFrame:
    """A random-walk 5-minute panel of the strategy's symbol, long and flat in turn."""
    close = 3000.0 * np.exp(np.cumsum(np.random.default_rng(7).normal(0.0, 0.002, rows)))
    index = pd.date_range("2026-11-02 09:05", periods=rows, freq="5min", name="eob")
    bars = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 100.0},
        index=index,
    )
    return pd.concat({workflow.SYMBOL: bars}, names=["symbol"])


def test_live_rows_need_only_the_warmup_window():
    """A bar's live run sees at least warmup_bars bars; that is enough for the backtest row."""
    panel = _walk()
    assert workflow.target_weights(panel)[workflow.SYMBOL].iloc[-100:].nunique() == 2

    window = workflow.SPEC.warmup_bars
    assert replay_mismatches(workflow.target_weights, panel, window=window, last=100) == []
    assert replay_mismatches(workflow.target_weights, panel, window=window - 1, last=100)


def test_the_live_panel_backtests_with_a_one_bar_lag():
    """The backtest runs the same function on the same panel; row t trades on bar t + 1."""
    from skills.backtest import VectorBacktester

    panel = _walk()
    weights = workflow.target_weights(panel)
    result = VectorBacktester(
        panel, trade_at="open", signal_lag=1, commission=0.0001, slippage_bp=1.0
    ).run(weights)

    pd.testing.assert_frame_equal(
        result.executed_weights, weights.shift(1).fillna(0.0), check_names=False
    )
