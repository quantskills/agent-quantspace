"""Live workflow of the asset-class rotation, with a fake PandaData client."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from skills.live_trade.workflow import replay_mismatches
from strategies.cross_sectional.asset_class_rotation import ASSET_CLASS_ETF_SYMBOLS
from strategies.cross_sectional.workflows import live_asset_class_rotation as workflow


class FakeClient:
    def __init__(self, days: int = 260):
        self.dates = pd.bdate_range("2025-11-03", periods=days)
        self.calls = []

    def _bars(self, start, end, scale):
        rng = np.random.default_rng(3)
        rows = []
        for offset, symbol in enumerate(ASSET_CLASS_ETF_SYMBOLS):
            path = 10.0 * np.exp(np.cumsum(rng.normal(0.0005 * offset, 0.01, len(self.dates))))
            for day, close in zip(self.dates, path, strict=True):
                if start <= day.strftime("%Y%m%d") <= end:
                    rows.append(
                        {"symbol": symbol, "date": day.strftime("%Y%m%d"), "close": close * scale}
                    )
        return pd.DataFrame(rows)

    def get_fund_daily_post(self, start, end, *, symbol):
        self.calls.append(("post", start, end))
        return self._bars(start, end, 3.0)

    def get_fund_daily(self, start, end, *, symbol):
        self.calls.append(("raw", start, end))
        return self._bars(start, end, 1.0)

    def get_trade_cal(self, start, end):
        day = pd.Timestamp(start)
        return pd.DataFrame({"nature_date": [int(start)], "is_trade": [int(day.weekday() < 5)]})


def test_load_inputs_stops_at_the_trade_date_and_saves_both_series(tmp_path):
    client = FakeClient()
    trade_date = client.dates[200].date()

    inputs = workflow.load_inputs(client, trade_date, tmp_path / "market")

    assert inputs.weights.index[-1].date() == trade_date
    assert list(inputs.weights.columns) == list(ASSET_CLASS_ETF_SYMBOLS)
    assert inputs.weights.iloc[-1].sum() == pytest.approx(1.0)
    # Unadjusted closes size the orders; adjusted closes only drive the signal.
    raw = pd.read_parquet(tmp_path / "market" / "close_raw.parquet")
    post = pd.read_parquet(tmp_path / "market" / "close_post.parquet")
    pd.testing.assert_frame_equal(inputs.prices, raw)
    assert (post / raw).stack().round(9).unique().tolist() == [3.0]
    assert {call[1] for call in client.calls} == {workflow.HISTORY_START.replace("-", "")}


def test_live_rows_replay_the_backtest_from_the_fixed_start():
    """Each day's live run reloads from HISTORY_START, so its row is the backtest's row."""
    client = FakeClient(days=200)
    close = workflow._closes(client.get_fund_daily_post("20190102", "20991231", symbol=None))

    assert not workflow.target_weights(close).iloc[-60:].eq(0).all(axis=None)
    assert replay_mismatches(workflow.target_weights, close, last=60) == []


def test_main_previews_without_writing(tmp_path, monkeypatch, capsys):
    client = FakeClient()
    monkeypatch.setattr("skills.ingest.PandaDataClient", lambda: client)
    trade_date = client.dates[-1].date().isoformat()

    code = workflow.main(["--date", trade_date, "--data-root", str(tmp_path)])

    assert code == 0 and '"status": "preview"' in capsys.readouterr().out
    assert not (tmp_path / "live").exists()


def test_main_test_mode_skips_the_calendar(tmp_path, monkeypatch, capsys):
    client = FakeClient()

    def closed(*args, **kwargs):
        raise AssertionError("test mode must not ask the calendar")

    client.get_trade_cal = closed
    monkeypatch.setattr("skills.ingest.PandaDataClient", lambda: client)

    code = workflow.main(["--date", "2026-11-21", "--test", "--data-root", str(tmp_path)])

    assert code == 0 and '"status": "preview"' in capsys.readouterr().out
    assert not (tmp_path / "live").exists()
