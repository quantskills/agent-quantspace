"""Live workflow of the asset-class rotation, with a fake PandaData client."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from skills.live_trade.history import daily_closes
from skills.live_trade.workflow import replay_mismatches
from strategies.cross_sectional.asset_class_rotation import ASSET_CLASS_ETF_SYMBOLS
from strategies.cross_sectional.workflows import live_asset_class_rotation as workflow
from tests.skills.live_trade.fakes import FakeSina


class FakeClient:
    """PandaData daily fund bars; ``sina()`` serves each day's close as its 14:50 bar."""

    def __init__(self, days: int = 260):
        self.dates = pd.bdate_range("2025-11-03", periods=days)
        self.calls = []

    def sina(self) -> FakeSina:
        sina = FakeSina()
        raw = self._bars("19000101", "29991231", 1.0)
        for row in raw.itertuples():
            day = pd.Timestamp(row.date)
            code = ("sh" if row.symbol.endswith(".SH") else "sz") + row.symbol[:6]
            sina.add(code, (day.replace(hour=14, minute=50).to_pydatetime(), row.close))
        return sina

    def _bars(self, start, end, scale):
        rng = np.random.default_rng(3)
        rows = []
        for offset, symbol in enumerate(ASSET_CLASS_ETF_SYMBOLS):
            path = 10.0 * np.exp(np.cumsum(rng.normal(0.0005 * offset, 0.01, len(self.dates))))
            previous = np.concatenate([[path[0]], path[:-1]])
            for day, close, pre in zip(self.dates, path, previous, strict=True):
                if start <= day.strftime("%Y%m%d") <= end:
                    rows.append(
                        {
                            "symbol": symbol,
                            "date": day.strftime("%Y%m%d"),
                            "open": pre * scale,
                            "high": max(pre, close) * scale,
                            "low": min(pre, close) * scale,
                            "close": close * scale,
                            "volume": 1e6,
                            "pre_close": pre * scale,
                        }
                    )
        return pd.DataFrame(rows)

    def get_fund_daily_post(self, start, end, *, symbol):
        self.calls.append(("post", start, end))
        return self._bars(start, end, 3.0)

    def get_fund_daily(self, start, end, *, symbol):
        self.calls.append(("raw", start, end))
        return self._bars(start, end, 1.0)

    def get_trade_cal(self, start, end):
        days = pd.date_range(start, end)
        return pd.DataFrame(
            {
                "nature_date": [int(day.strftime("%Y%m%d")) for day in days],
                "is_trade": [int(day.weekday() < 5) for day in days],
            }
        )


@pytest.fixture
def client(monkeypatch):
    """A fake client whose 14:50 bars Sina serves through AKShare."""
    fake = FakeClient()
    sina = fake.sina()
    monkeypatch.setattr("skills.ingest.akshare_bars._load_akshare", lambda: sina)
    return fake


def test_load_inputs_takes_history_to_yesterday_and_today_at_1450(tmp_path, client):
    trade_date = client.dates[200].date()

    inputs = workflow.load_inputs(client, trade_date, tmp_path / "market")

    assert inputs.weights.index[-1].date() == trade_date
    # History up to the day before, plus the day itself for its previous close (published
    # here, so no Sina quote is needed); today's row is Sina's 14:50 close.
    start, before = workflow.HISTORY_START.replace("-", ""), client.dates[199].strftime("%Y%m%d")
    today = client.dates[200].strftime("%Y%m%d")
    assert set(client.calls) == {
        ("post", start, before),
        ("raw", start, before),
        ("raw", today, today),
    }
    assert inputs.prices.iloc[-1].tolist() == pytest.approx(
        client._bars(*[client.dates[200].strftime("%Y%m%d")] * 2, 1.0)["close"].tolist()
    )
    assert "当日收盘价取 14:50" in "\n".join(inputs.notes)
    assert list(inputs.weights.columns) == list(ASSET_CLASS_ETF_SYMBOLS)
    assert inputs.weights.iloc[-1].sum() == pytest.approx(1.0)
    # Unadjusted closes size the orders; adjusted closes only drive the signal.
    raw = pd.read_parquet(tmp_path / "market" / "close_raw.parquet")
    post = pd.read_parquet(tmp_path / "market" / "close_post.parquet")
    pd.testing.assert_frame_equal(inputs.prices, raw, check_freq=False)
    assert (post / raw).stack().round(9).unique().tolist() == [3.0]


def test_live_rows_replay_the_backtest_from_the_fixed_start():
    """Each day's live run reloads from HISTORY_START, so its row is the backtest's row."""
    client = FakeClient(days=200)
    close = daily_closes(
        client,
        list(ASSET_CLASS_ETF_SYMBOLS),
        "fund",
        date(2019, 1, 2),
        date(2099, 12, 31),
        adjust="post",
    )

    assert not workflow.target_weights(close).iloc[-60:].eq(0).all(axis=None)
    assert replay_mismatches(workflow.target_weights, close, last=60) == []


def test_main_previews_without_writing(tmp_path, monkeypatch, capsys, client):
    monkeypatch.setattr("skills.ingest.PandaDataClient", lambda: client)
    trade_date = client.dates[-1].date().isoformat()

    code = workflow.main(["--date", trade_date, "--data-root", str(tmp_path)])

    assert code == 0 and '"status": "preview"' in capsys.readouterr().out
    assert not (tmp_path / "live").exists()


def test_main_before_1450_is_stale(tmp_path, monkeypatch, capsys, client):
    monkeypatch.setattr("skills.ingest.PandaDataClient", lambda: client)
    monkeypatch.setattr("skills.ingest.akshare_bars._load_akshare", lambda: FakeSina())
    trade_date = client.dates[-1].date().isoformat()

    code = workflow.main(["--date", trade_date, "--data-root", str(tmp_path)])

    report = json.loads(capsys.readouterr().out)
    assert code == 3 and report["status"] == "stale" and "14:50" in report["detail"]


def test_main_test_mode_on_a_weekend_uses_the_last_trading_day(
    tmp_path, monkeypatch, capsys, client
):
    monkeypatch.setattr("skills.ingest.PandaDataClient", lambda: client)
    saturday = client.dates[-1] + pd.Timedelta(days=1)
    assert saturday.weekday() == 5

    code = workflow.main(
        ["--date", saturday.date().isoformat(), "--test", "--data-root", str(tmp_path)]
    )

    assert code == 0 and '"status": "preview"' in capsys.readouterr().out
    assert not (tmp_path / "live").exists()
