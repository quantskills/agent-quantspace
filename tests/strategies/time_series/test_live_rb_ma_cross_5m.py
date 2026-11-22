"""The 5-minute rebar MA-cross live workflow, run offline on fake PandaData and Sina."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

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
