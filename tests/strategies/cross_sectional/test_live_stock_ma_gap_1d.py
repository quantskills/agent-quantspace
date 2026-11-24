"""The daily stock MA-gap live workflow at 14:50, offline on fake PandaData and Sina."""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from skills.ingest.akshare_bars import SinaQuote
from skills.live_trade.history import daily_closes
from skills.live_trade.workflow import replay_mismatches
from strategies.cross_sectional.rules import ma_gap_reversal_weights
from strategies.cross_sectional.workflows import live_stock_ma_gap_1d as workflow
from tests.skills.live_trade.fakes import DAYS, FRIDAY, MONDAY, FakePandaData, FakeSina

AT = datetime(2026, 11, 23, 14, 50)


def _client() -> FakePandaData:
    """Random-walk closes for the six stocks; Monday is not published yet."""
    client = FakePandaData()
    client.daily_until = FRIDAY
    rng = np.random.default_rng(7)
    for offset, symbol in enumerate(workflow.SYMBOLS):
        path = 10.0 * np.exp(np.cumsum(rng.normal(0.0003 * offset, 0.02, len(DAYS))))
        for day, close in zip(DAYS, path, strict=True):
            client.daily[(symbol, day)] = round(float(close), 2)
    return client


@pytest.fixture
def client(monkeypatch):
    """PandaData, Sina bars ending at 14:50 and Sina quotes, all fake."""
    import skills.ingest
    import skills.ingest.akshare_bars

    fake = _client()
    sina = FakeSina()
    for symbol in workflow.SYMBOLS:
        code = ("sh" if symbol.endswith(".SH") else "sz") + symbol[:6]
        close = fake.daily[(symbol, MONDAY)]
        sina.add(code, (datetime(2026, 11, 23, 9, 31), close - 0.1), (AT, close))

    def quotes(symbols):
        found = {
            symbol: SinaQuote(symbol, fake.daily[(symbol, FRIDAY)], 0.0, 0.0, "2026-11-23", "14:50")
            for symbol in symbols
        }
        return found, {}

    monkeypatch.setattr(skills.ingest, "PandaDataClient", lambda: fake)
    monkeypatch.setattr(skills.ingest.akshare_bars, "_load_akshare", lambda: sina)
    monkeypatch.setattr("skills.live_trade.daily._now", lambda: datetime(2026, 11, 23, 14, 51))
    monkeypatch.setattr(skills.ingest.akshare_bars, "fetch_sina_quotes", quotes)
    return fake


def test_target_weights_are_the_backtest_rule():
    close = daily_closes(_client(), list(workflow.SYMBOLS), "stock", DAYS[0], FRIDAY)

    expected = ma_gap_reversal_weights(
        close, list(workflow.SYMBOLS), lookback=120, top_n=2, vol_lookback=60, rebalance_days=5
    )
    pd.testing.assert_frame_equal(workflow.target_weights(close), expected)


def test_load_inputs_ends_with_the_1450_row(client, tmp_path):
    inputs = workflow.load_inputs(client, MONDAY, tmp_path / "market")

    assert inputs.weights.index[-1].date() == MONDAY
    today = inputs.weights.iloc[-1]
    assert (today >= 0).all() and today.sum() == pytest.approx(1.0)
    expected = {symbol: client.daily[(symbol, MONDAY)] for symbol in workflow.SYMBOLS}
    assert inputs.prices.iloc[-1].to_dict() == pytest.approx(expected)
    saved = pd.read_parquet(tmp_path / "market" / "bars_raw.parquet")
    assert saved.xs(pd.Timestamp(MONDAY), level="eob")["close"].to_dict() == pytest.approx(expected)


def test_live_rows_replay_the_backtest_from_the_fixed_start():
    close = daily_closes(_client(), list(workflow.SYMBOLS), "stock", DAYS[0], FRIDAY)

    weights = workflow.target_weights(close)
    assert weights.iloc[-60:].nunique().gt(1).any()  # the window changes holdings
    assert replay_mismatches(workflow.target_weights, close, last=60) == []


def test_main_previews_without_writing(client, tmp_path, capsys):
    code = workflow.main(
        ["--date", "2026-11-23", "--capital", "1000000", "--data-root", str(tmp_path)]
    )

    report = json.loads(capsys.readouterr().out)
    assert (code, report["status"]) == (0, "preview")
    assert set(report["target"]) <= set(workflow.SYMBOLS) and len(report["target"]) == 2
    assert "当日收盘价取 14:50" in report["message"]
    assert not (tmp_path / "live").exists()
