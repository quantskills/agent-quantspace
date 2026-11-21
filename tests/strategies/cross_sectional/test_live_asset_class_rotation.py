"""Live workflow of the asset-class rotation, with a fake PandaData client."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from strategies.cross_sectional.asset_class_rotation import ASSET_CLASS_ETF_SYMBOLS
from strategies.cross_sectional.workflows import live_asset_class_rotation as workflow


class FakeClient:
    def __init__(self, days: int = 260, expire_once: bool = False):
        self.dates = pd.bdate_range("2025-11-03", periods=days)
        self.expire_once = expire_once
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
        if self.expire_once:
            self.expire_once = False
            raise RuntimeError("chunk failed") from RuntimeError(
                "未登录或登录已过期，请调用 panda_data.init_token() 进行登录！"
            )
        return self._bars(start, end, 3.0)

    def get_fund_daily(self, start, end, *, symbol):
        self.calls.append(("raw", start, end))
        return self._bars(start, end, 1.0)

    def get_trade_cal(self, start, end):
        day = pd.Timestamp(start)
        return pd.DataFrame({"nature_date": [int(start)], "is_trade": [int(day.weekday() < 5)]})


def test_trading_day_comes_from_the_calendar():
    client = FakeClient()
    assert workflow.is_trading_day(client, date(2026, 11, 20))
    assert not workflow.is_trading_day(client, date(2026, 11, 21))


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


def test_load_retries_once_after_a_dropped_login():
    clients = [FakeClient(expire_once=True), FakeClient()]
    made = []

    def make_client():
        made.append(clients[len(made)])
        return made[-1]

    inputs = workflow.load_with_relogin(make_client, clients[0].dates[150].date())

    assert len(made) == 2 and not inputs.weights.empty


def test_other_load_errors_are_not_retried():
    class Broken(FakeClient):
        def get_fund_daily_post(self, start, end, *, symbol):
            raise ValueError("bad request")

    made = []

    def make_client():
        made.append(Broken())
        return made[-1]

    with pytest.raises(ValueError, match="bad request"):
        workflow.load_with_relogin(make_client, date(2026, 6, 1))
    assert len(made) == 1


def test_main_previews_without_writing(tmp_path, monkeypatch, capsys):
    client = FakeClient()
    monkeypatch.setattr("skills.ingest.PandaDataClient", lambda: client)
    trade_date = client.dates[-1].date().isoformat()

    code = workflow.main(["--date", trade_date, "--data-root", str(tmp_path)])

    assert code == 0 and '"status": "preview"' in capsys.readouterr().out
    assert not (tmp_path / "live").exists()
