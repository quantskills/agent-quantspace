"""qs backtest commands produce exactly what the backtest APIs produce."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from tests.fixtures.market_data import make_ohlcv

SYMBOLS = ("SHSE.510300", "SHSE.510500", "SHSE.512100", "SZSE.159915")


def invoke(capsys, *args):
    from skills.cli import main

    code = main(list(args))
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture
def panel():
    frames = []
    for index, symbol in enumerate(SYMBOLS):
        rng = np.random.default_rng(index)
        prices = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, 160)))
        frames.append(make_ohlcv(prices, symbol=symbol))
    return pd.concat(frames).sort_index()


@pytest.fixture
def files(tmp_path, panel):
    panel_path = tmp_path / "panel.parquet"
    panel.to_parquet(panel_path)
    close = panel["close"].unstack("symbol")
    momentum = close.pct_change(20, fill_method=None)
    votes = momentum.rank(axis=1, ascending=False).le(2).astype(float).where(momentum.notna(), 0.0)
    weights = votes.div(votes.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    votes_path, weights_path = tmp_path / "votes.parquet", tmp_path / "weights.parquet"
    votes.to_parquet(votes_path)
    weights.to_parquet(weights_path)
    return {
        "panel": panel_path,
        "votes": votes_path,
        "weights": weights_path,
        "close": close,
        "returns": close.pct_change(fill_method=None),
        "votes_frame": votes,
        "weights_frame": weights,
    }


def test_run_matches_vector_backtester(files, panel, tmp_path, capsys):
    from skills.backtest import VectorBacktester, activity_metrics, annual_return_metrics

    out = tmp_path / "run"
    code, result = invoke(
        capsys,
        *["backtest", "run", "--panel", str(files["panel"]), "--weights", str(files["weights"])],
        *["--commission", "0.0002", "--slippage-bp", "1.5", "--out-dir", str(out)],
    )
    assert code == 0, result
    expected = VectorBacktester(data=panel, commission=0.0002, slippage_bp=1.5).run(
        files["weights_frame"]
    )
    pd.testing.assert_frame_equal(pd.read_parquet(out / "result.parquet"), expected.result_df)
    pd.testing.assert_frame_equal(
        pd.read_parquet(out / "executed_weights.parquet"), expected.executed_weights
    )
    assert result["data"]["metrics"] == pytest.approx(expected.metrics)
    assert result["data"]["annual_returns"] == pytest.approx(
        annual_return_metrics(expected.result_df)
    )
    assert result["data"]["activity"] == pytest.approx(activity_metrics(expected.result_df))
    saved = json.loads((out / "metrics.json").read_text())
    assert saved["metrics"] == pytest.approx(expected.metrics)
    assert [item["name"] for item in result["artifacts"]] == [
        "result_df",
        "executed_weights",
        "metrics",
    ]


def test_run_window_trims_results_of_a_full_history_run(files, panel, capsys, tmp_path):
    from skills.backtest import VectorBacktester

    out = tmp_path / "window"
    code, result = invoke(
        capsys,
        *["backtest", "run", "--panel", str(files["panel"]), "--weights", str(files["weights"])],
        *["--commission", "0", "--slippage-bp", "0", "--start", "2024-03-01"],
        *["--end", "2024-04-30", "--trade-at", "open", "--signal-lag", "2", "--out-dir", str(out)],
    )
    assert code == 0, result
    expected = VectorBacktester(
        data=panel,
        trade_at="open",
        signal_lag=2,
        commission=0.0,
        slippage_bp=0.0,
        start_date="2024-03-01",
        end_date="2024-04-30",
    ).run(files["weights_frame"])
    pd.testing.assert_frame_equal(pd.read_parquet(out / "result.parquet"), expected.result_df)
    assert result["data"]["start"].startswith("2024-03-01")
    assert result["data"]["end"].startswith("2024-04-30")


def test_run_checks_outputs_before_running_and_needs_slippage(files, tmp_path, capsys):
    out = tmp_path / "taken"
    out.mkdir()
    (out / "metrics.json").write_text("{}")
    base = ["backtest", "run", "--panel", str(files["panel"]), "--weights", str(files["weights"])]
    code, result = invoke(
        capsys, *base, "--commission", "0", "--slippage-bp", "0", "--out-dir", str(out)
    )
    assert code == 2 and result["error"]["code"] == "CONFLICT"
    assert sorted(path.name for path in out.iterdir()) == ["metrics.json"]
    code, result = invoke(capsys, *base, "--commission", "0")
    assert code == 2 and result["error"]["details"][0]["loc"] == ["slippage_bp"]


def test_weigh_equal_and_risk_parity_match_weight_methods(files, tmp_path, capsys):
    from skills.backtest.weighting import WEIGHT_METHODS

    equal = tmp_path / "equal.parquet"
    code, result = invoke(
        capsys, "backtest", "weigh", "--votes", str(files["votes"]), "--output", str(equal)
    )
    assert code == 0 and result["data"]["method"] == "equal"
    pd.testing.assert_frame_equal(
        pd.read_parquet(equal), WEIGHT_METHODS["equal"](files["votes_frame"]), check_freq=False
    )
    parity = tmp_path / "parity.parquet"
    code, result = invoke(
        capsys,
        *["backtest", "weigh", "--votes", str(files["votes"]), "--method", "risk_parity"],
        *["--panel", str(files["panel"]), "--lookback", "30", "--output", str(parity)],
    )
    assert code == 0, result
    expected = WEIGHT_METHODS["risk_parity"](
        files["votes_frame"], returns_df=files["returns"], lookback=30
    )
    pd.testing.assert_frame_equal(pd.read_parquet(parity), expected, check_freq=False)


def test_weigh_epo_uses_its_own_defaults_and_the_lambda_alias(files, tmp_path, capsys):
    from skills.backtest.weighting import WEIGHT_METHODS

    returns_path = tmp_path / "returns.parquet"
    files["returns"].to_parquet(returns_path)
    output = tmp_path / "epo.parquet"
    code, result = invoke(
        capsys,
        *["backtest", "weigh", "--votes", str(files["votes"]), "--method", "epo"],
        *["--returns", str(returns_path), "--lambda", "5", "--min-periods", "40"],
        *["--output", str(output)],
    )
    assert code == 0, result
    expected = WEIGHT_METHODS["epo"](
        files["votes_frame"], returns_df=files["returns"], min_periods=40, lambda_=5.0, shrink_w=0.2
    )
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected, check_freq=False)


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--method", "risk_parity"], "requires --returns or a panel source"),
        (["--method", "risk_parity", "--returns", "R", "--panel", "P"], "not both"),
    ],
)
def test_weigh_rejects_ambiguous_return_sources(files, tmp_path, capsys, extra, message):
    extra = [
        str(files["panel"]) if item == "P" else str(files["votes"]) if item == "R" else item
        for item in extra
    ]
    code, result = invoke(
        capsys,
        "backtest",
        "weigh",
        "--votes",
        str(files["votes"]),
        "--output",
        str(tmp_path / "w.parquet"),
        *extra,
    )
    assert code == 2 and message in json.dumps(result["error"])
    assert not (tmp_path / "w.parquet").exists()


def test_weigh_rejects_returns_missing_voted_symbols(files, tmp_path, capsys):
    partial = tmp_path / "partial.parquet"
    files["returns"].iloc[:, :2].to_parquet(partial)
    code, result = invoke(
        capsys,
        "backtest",
        "weigh",
        "--votes",
        str(files["votes"]),
        "--method",
        "inverse_variance",
        "--returns",
        str(partial),
        "--output",
        str(tmp_path / "w.parquet"),
    )
    assert code == 2 and "missing voted symbol columns" in result["error"]["message"]


def test_overlay_matches_apply_portfolio_filters(files, tmp_path, capsys):
    from skills.backtest.filters import apply_portfolio_filters

    index_path = tmp_path / "index.parquet"
    files["close"].mean(axis=1).rename("close").to_frame().to_parquet(index_path)
    output = tmp_path / "scaled.parquet"
    code, result = invoke(
        capsys,
        *[
            "backtest",
            "overlay",
            "--weights",
            str(files["weights"]),
            "--panel",
            str(files["panel"]),
        ],
        *["--index-close", str(index_path), "--index-trend", '{"ma_period": 30}'],
        *["--vol-target", '{"vol_target": 0.08, "lookback": 20}', "--output", str(output)],
    )
    assert code == 0, result
    expected = apply_portfolio_filters(
        files["weights_frame"],
        files["close"],
        files["returns"],
        index_close=files["close"].mean(axis=1).rename("close"),
        index_trend_config={"ma_period": 30},
        vol_target_config={"vol_target": 0.08, "lookback": 20},
    )
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected, check_freq=False)


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ([], "at least one"),
        (["--index-trend", "{}"], "at least one"),
        (["--index-trend", '{"ma_period": 5}'], "requires index_close"),
    ],
)
def test_overlay_validates_its_configuration(files, tmp_path, capsys, extra, message):
    code, result = invoke(
        capsys,
        "backtest",
        "overlay",
        "--weights",
        str(files["weights"]),
        "--panel",
        str(files["panel"]),
        "--output",
        str(tmp_path / "o.parquet"),
        *extra,
    )
    assert code == 2 and message in json.dumps(result["error"])


@pytest.mark.parametrize(
    ("method", "extra", "custom"),
    [
        ("equal", [], None),
        ("risk_parity", ["--lookback", "20"], None),
        ("custom", ["--weights", '{"a": 3, "b": 1}'], {"a": 3, "b": 1}),
    ],
)
def test_combine_matches_strategy_combiner(tmp_path, capsys, method, extra, custom):
    from skills.backtest.combiner import StrategyCombiner

    rng = np.random.default_rng(7)
    index = pd.date_range("2024-01-01", periods=90, name="eob")
    returns = pd.DataFrame(rng.normal(0, 0.01, (90, 2)), index=index, columns=["a", "b"])
    source, output = tmp_path / "streams.parquet", tmp_path / "combined.parquet"
    returns.to_parquet(source)
    code, result = invoke(
        capsys,
        "backtest",
        "combine",
        "--returns",
        str(source),
        "--method",
        method,
        "--output",
        str(output),
        *extra,
    )
    assert code == 0, result
    combiner = StrategyCombiner(
        {"a": returns["a"], "b": returns["b"]},
        method=method,
        custom_weights=custom,
        lookback=20 if method == "risk_parity" else 60,
    )
    expected = combiner.run()
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected, check_freq=False)
    metrics = dict(combiner.metrics)
    assert result["data"]["weights"] == pytest.approx(metrics.pop("weights"))
    assert result["data"]["metrics"] == pytest.approx(metrics)


def test_combine_rejects_inconsistent_weights(tmp_path, capsys):
    source = tmp_path / "streams.csv"
    pd.DataFrame({"eob": ["2024-01-01", "2024-01-02"], "a": [0.01, 0.0]}).to_csv(
        source, index=False
    )
    code, result = invoke(
        capsys,
        "backtest",
        "combine",
        "--returns",
        str(source),
        "--method",
        "custom",
        "--weights",
        '{"z": 1}',
    )
    assert code == 2 and "unknown strategies" in result["error"]["message"]
    code, result = invoke(
        capsys, "backtest", "combine", "--returns", str(source), "--weights", '{"a": 1}'
    )
    assert code == 2 and "custom method" in json.dumps(result["error"])


def test_cost_matches_the_cost_model(capsys):
    from skills.backtest.cost_model import (
        cost_bp_for_trigger_time,
        cost_layer_for_trigger_time,
        single_T_pnl_bp,
    )

    when = pd.Timestamp("2026-09-23 14:50")
    code, result = invoke(
        capsys,
        "backtest",
        "cost",
        "--time",
        "2026-09-23 14:50",
        "--sell-price",
        "10.5",
        "--buyback-price",
        "10.2",
    )
    gross, net = single_T_pnl_bp(10.5, 10.2, cost_bp_for_trigger_time(when))
    assert code == 0
    assert result["data"] == {
        "time": str(when),
        "layer": cost_layer_for_trigger_time(when),
        "cost_bp": cost_bp_for_trigger_time(when),
        "gross_bp": pytest.approx(gross),
        "net_bp": pytest.approx(net),
    }
    code, result = invoke(
        capsys, "backtest", "cost", "--time", "2026-09-23 10:00", "--sell-price", "1"
    )
    assert code == 2 and "go together" in json.dumps(result["error"])
