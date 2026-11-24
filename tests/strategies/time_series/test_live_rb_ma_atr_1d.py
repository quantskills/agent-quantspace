"""The daily rebar MA/ATR live workflow at 14:50, offline on fake PandaData and Sina."""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from skills.live_trade.history import daily_bars
from skills.live_trade.workflow import replay_mismatches
from strategies.time_series.rules import ma_reversion_atr_stop_weights
from strategies.time_series.workflows import live_rb_ma_atr_1d as workflow
from tests.skills.live_trade.fakes import DAYS, FRIDAY, MONDAY, FakePandaData, FakeSina

AT = datetime(2026, 11, 23, 14, 50)
# Monday's 1-minute bars: Friday night belongs to Monday's trading day.
MONDAY_BARS = (
    (datetime(2026, 11, 20, 21, 1), 3005.0),
    (datetime(2026, 11, 23, 9, 1), 3020.0),
    (AT, 3010.0),
)


def _client() -> FakePandaData:
    client = FakePandaData()
    client.daily_until = FRIDAY
    rng = np.random.default_rng(11)
    path = 3000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.012, len(DAYS))))
    for day, close in zip(DAYS, path, strict=True):
        client.daily[(workflow.SYMBOL, day)] = round(float(close))
    return client


@pytest.fixture
def client(monkeypatch):
    import skills.ingest
    import skills.ingest.akshare_bars

    fake = _client()
    sina = FakeSina()
    sina.add("RB2701", (datetime(2026, 11, 20, 14, 50), 2990.0), *MONDAY_BARS)
    monkeypatch.setattr(skills.ingest, "PandaDataClient", lambda: fake)
    monkeypatch.setattr(skills.ingest.akshare_bars, "_load_akshare", lambda: sina)
    monkeypatch.setattr("skills.live_trade.daily._now", lambda: datetime(2026, 11, 23, 14, 51))
    return fake


def _history() -> pd.DataFrame:
    return daily_bars(_client(), [workflow.SYMBOL], "future", DAYS[0], FRIDAY)


def test_target_weights_are_the_backtest_rule():
    panel = _history()

    bars = panel.xs(workflow.SYMBOL, level="symbol")
    expected = ma_reversion_atr_stop_weights(
        bars, workflow.SYMBOL, ma_lookback=10, atr_lookback=14, atr_multiplier=2.0
    )
    pd.testing.assert_frame_equal(workflow.target_weights(panel), expected)


def test_todays_bar_is_the_1_minute_bars_up_to_1450(client, tmp_path):
    inputs = workflow.load_inputs(client, MONDAY, tmp_path / "market")

    assert inputs.weights.index[-1].date() == MONDAY
    assert inputs.contracts == {workflow.SYMBOL: "RB2701.SHF"}
    assert inputs.multipliers == {workflow.SYMBOL: 10.0}
    saved = pd.read_parquet(tmp_path / "market" / "bars.parquet")
    today = saved.loc[(workflow.SYMBOL, pd.Timestamp(MONDAY))]
    # FakeSina bars: open = close, high = close + 1, low = close - 1, volume 50.
    assert today.to_dict() == {
        "open": 3005.0,  # Friday 21:01, the first bar of Monday's trading day
        "high": 3021.0,
        "low": 3004.0,
        "close": 3010.0,  # 14:50
        "volume": 150.0,
    }


def test_live_rows_replay_the_backtest_from_the_fixed_start():
    panel = _history()

    weights = workflow.target_weights(panel)
    assert weights.iloc[-80:].nunique().gt(1).any()  # the stop and entries both fire
    assert replay_mismatches(workflow.target_weights, panel, last=80) == []


def test_main_previews_the_dominant_contract(client, tmp_path, capsys):
    code = workflow.main(
        ["--date", "2026-11-23", "--capital", "100000", "--data-root", str(tmp_path)]
    )

    report = json.loads(capsys.readouterr().out)
    assert (code, report["status"], report["execution"]) == (0, "preview", None)
    assert "RB_DOMINANT.SHF 当前对应 RB2701.SHF" in report["message"]
    assert not (tmp_path / "live").exists()
