"""qs strategy commands build the same targets as the strategy APIs."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from tests.fixtures.market_data import make_ohlcv

SYMBOLS = ("SHSE.510300", "SHSE.510500", "SHSE.512100", "SHSE.512880", "SZSE.159915")
EXITS = "skills.strategy.cross_sectional.exits:drawdown_from_high_filter"


def invoke(capsys, *args):
    from skills.cli import main

    code = main(list(args))
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture
def panel():
    frames = []
    for index, symbol in enumerate(SYMBOLS):
        rng = np.random.default_rng(100 + index)
        prices = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, 220)))
        frames.append(make_ohlcv(prices, symbol=symbol))
    return pd.concat(frames).sort_index()


@pytest.fixture
def panel_path(tmp_path, panel):
    path = tmp_path / "panel.parquet"
    panel.to_parquet(path)
    return path


@pytest.fixture
def factors(tmp_path, panel):
    close = panel["close"].unstack("symbol")
    frames = {
        "mom": close.pct_change(10, fill_method=None),
        "rev": close.pct_change(3, fill_method=None),
    }
    paths = {}
    for name, frame in frames.items():
        paths[name] = tmp_path / f"{name}.parquet"
        frame.to_parquet(paths[name])
    return frames, paths


def test_top_n_matches_top_n_weights(factors, tmp_path, capsys):
    from skills.strategy.cross_sectional import top_n_weights

    frames, paths = factors
    output = tmp_path / "targets.parquet"
    code, result = invoke(
        capsys,
        "strategy",
        "top-n",
        "--scores",
        str(paths["mom"]),
        "--top-n",
        "2",
        "--gross-exposure",
        "0.8",
        "--output",
        str(output),
        "--preview",
        "1",
    )
    assert code == 0, result
    expected = top_n_weights(frames["mom"], top_n=2, gross_exposure=0.8)
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected, check_freq=False)
    assert result["data"]["rows"] == len(expected) and len(result["data"]["preview"]) == 1


def test_signal_weights_match_single_asset_helper(tmp_path, capsys):
    from skills.strategy.time_series import signal_to_single_asset_weights

    signal = pd.DataFrame(
        {"eob": pd.date_range("2024-01-01", periods=6), "position": [0, 1, 1, -1, 2, 0.5]}
    )
    source, output = tmp_path / "signal.csv", tmp_path / "weights.parquet"
    signal.to_csv(source, index=False)
    code, result = invoke(
        capsys,
        "strategy",
        "signal-weights",
        "--signal",
        str(source),
        "--column",
        "position",
        "--symbol",
        "CFFEX.IF99",
        "--exposure",
        "0.5",
        "--output",
        str(output),
    )
    assert code == 0, result
    expected = signal_to_single_asset_weights(
        signal.set_index("eob")["position"], symbol="CFFEX.IF99", exposure=0.5
    )
    pd.testing.assert_frame_equal(
        pd.read_parquet(output), expected, check_freq=False, check_names=False
    )
    code, result = invoke(
        capsys,
        "strategy",
        "signal-weights",
        "--signal",
        str(source),
        "--symbol",
        "X",
        "--output",
        str(tmp_path / "other.parquet"),
    )
    assert code == 2 and "no column 'signal'" in result["error"]["message"]


def test_hold_calendar_matches_helper(panel, panel_path, tmp_path, capsys):
    from skills.strategy.cross_sectional import hold_weights_on_calendar

    dates = panel.index.get_level_values("eob").unique().sort_values()
    signal_days = pd.DataFrame(
        {"SHSE.510300": [1.0, 0.0], "SZSE.159915": [0.0, 1.0]},
        index=pd.DatetimeIndex([dates[10], dates[50]], name="eob"),
    )
    source, output = tmp_path / "signal_days.parquet", tmp_path / "held.parquet"
    signal_days.to_parquet(source)
    code, result = invoke(
        capsys,
        "strategy",
        "hold-calendar",
        "--panel",
        str(panel_path),
        "--weights",
        str(source),
        "--output",
        str(output),
    )
    assert code == 0, result
    expected = hold_weights_on_calendar(
        signal_days, dates=dates, symbols=panel.index.get_level_values("symbol").unique()
    )
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected, check_freq=False)


def _read_outputs(out):
    return {
        name: pd.read_parquet(out / f"{name}.parquet")
        for name in ("factor_weights", "composite_scores", "target_weights")
    }


def _assert_result(out, expected):
    outputs = _read_outputs(out)
    for name, frame in outputs.items():
        pd.testing.assert_frame_equal(frame, getattr(expected, name), check_freq=False)


def test_combine_equal_rank_matches_combine_factor_scores(factors, tmp_path, capsys):
    from skills.strategy.cross_sectional import combine_factor_scores

    frames, paths = factors
    out = tmp_path / "combined"
    code, result = invoke(
        capsys,
        *[
            "strategy",
            "combine",
            "--factors",
            f"mom={paths['mom']}",
            "--factors",
            f"rev={paths['rev']}",
        ],
        *["--directions", '{"mom": 1, "rev": -1}', "--method", "equal_rank", "--top-n", "2"],
        *["--normalization", "zscore", "--out-dir", str(out)],
    )
    assert code == 0, result
    expected = combine_factor_scores(
        frames,
        method="equal_rank",
        directions={"mom": 1, "rev": -1},
        normalization="zscore",
        top_n=2,
    )
    _assert_result(out, expected)
    assert result["data"]["factors"] == ["mom", "rev"]
    assert result["data"]["latest_factor_weights"] == pytest.approx(
        expected.factor_weights.iloc[-1].to_dict()
    )


def test_combine_dynamic_methods_read_ic_and_correlation_history(factors, tmp_path, capsys):
    from skills.strategy.cross_sectional import DynamicFactorWeightConfig, combine_factor_scores

    frames, paths = factors
    dates = frames["mom"].index
    rng = np.random.default_rng(3)
    ic_history = pd.DataFrame(
        {"mom": rng.normal(0.03, 0.1, len(dates)), "rev": rng.normal(0.01, 0.1, len(dates))},
        index=dates,
    )
    correlations = pd.DataFrame(
        {
            "eob": dates,
            "factor_a": "mom",
            "factor_b": "rev",
            "correlation": rng.uniform(-0.3, 0.3, len(dates)),
        }
    )
    ic_path, corr_path = tmp_path / "ic.parquet", tmp_path / "corr.csv"
    ic_history.to_parquet(ic_path)
    correlations.to_csv(corr_path, index=False)
    out = tmp_path / "max_icir"
    code, result = invoke(
        capsys,
        *[
            "strategy",
            "combine",
            "--factors",
            f"mom={paths['mom']}",
            "--factors",
            f"rev={paths['rev']}",
        ],
        *[
            "--directions",
            '{"mom": 1, "rev": 1}',
            "--method",
            "max_icir",
            "--ic-history",
            str(ic_path),
        ],
        *["--correlation-history", str(corr_path), "--availability-delay", "2", "--lookback", "60"],
        *["--min-periods", "20", "--out-dir", str(out)],
    )
    assert code == 0, result
    expected = combine_factor_scores(
        frames,
        method="max_icir",
        directions={"mom": 1, "rev": 1},
        ic_history=ic_history,
        correlation_history=correlations.assign(eob=pd.to_datetime(correlations["eob"])),
        dynamic_config=DynamicFactorWeightConfig(availability_delay=2, lookback=60, min_periods=20),
    )
    _assert_result(out, expected)


def _tidy_daily_ic(dates, rng, horizons=(1, 5), lags=(0, 2)):
    """A tidy table shaped like the daily_ic that `qs analyze ic-surface` writes."""
    rows = [
        pd.DataFrame(
            {
                "factor": name,
                "horizon": horizon,
                "lag": lag,
                "eob": dates,
                "ic": rng.normal(0.02 + 0.01 * horizon, 0.1, len(dates)),
            }
        )
        for horizon in horizons
        for lag in lags
        for name in ("mom", "rev")
    ]
    return pd.concat(rows, ignore_index=True)


def _combine_argv(paths, out, *extra):
    return [
        *["strategy", "combine", "--factors", f"mom={paths['mom']}"],
        *["--factors", f"rev={paths['rev']}", "--directions", '{"mom": 1, "rev": 1}'],
        *["--method", "max_icir", "--availability-delay", "2", "--lookback", "60"],
        *["--min-periods", "20", "--max-weight", "1", "--out-dir", str(out), *extra],
    ]


@pytest.fixture
def histories(factors, tmp_path):
    frames, paths = factors
    dates = frames["mom"].index
    rng = np.random.default_rng(3)
    tidy = _tidy_daily_ic(dates, rng)
    tidy_path, wide_path = tmp_path / "daily_ic.parquet", tmp_path / "wide_ic.parquet"
    tidy.to_parquet(tidy_path)
    chosen = tidy[(tidy["horizon"] == 5) & (tidy["lag"] == 2)]
    wide = chosen.pivot(index="eob", columns="factor", values="ic")
    wide.to_parquet(wide_path)
    correlations = pd.DataFrame(
        {
            "eob": dates,
            "factor_a": "mom",
            "factor_b": "rev",
            "correlation": rng.uniform(-0.3, 0.3, len(dates)),
        }
    )
    corr_path = tmp_path / "corr.parquet"
    correlations.to_parquet(corr_path)
    return tidy, tidy_path, wide, wide_path, correlations, corr_path


def test_combine_tidy_daily_ic_equals_the_wide_table_run(factors, histories, tmp_path, capsys):
    from skills.strategy.cross_sectional import DynamicFactorWeightConfig, combine_factor_scores

    frames, paths = factors
    tidy, tidy_path, wide, wide_path, correlations, corr_path = histories
    common = ["--correlation-history", str(corr_path)]
    code, result = invoke(
        capsys,
        *_combine_argv(paths, tmp_path / "wide", "--ic-history", str(wide_path), *common),
    )
    assert code == 0, result
    code, result = invoke(
        capsys,
        *_combine_argv(
            paths,
            tmp_path / "tidy",
            *["--ic-history", str(tidy_path), "--ic-horizon", "5", "--ic-lag", "2", *common],
        ),
    )
    assert code == 0, result
    expected = combine_factor_scores(
        frames,
        method="max_icir",
        directions={"mom": 1, "rev": 1},
        ic_history=wide,
        correlation_history=correlations,
        dynamic_config=DynamicFactorWeightConfig(
            availability_delay=2, lookback=60, min_periods=20, max_weight=1.0
        ),
    )
    _assert_result(tmp_path / "tidy", expected)
    for name in ("factor_weights", "composite_scores", "target_weights"):
        pd.testing.assert_frame_equal(
            pd.read_parquet(tmp_path / "tidy" / f"{name}.parquet"),
            pd.read_parquet(tmp_path / "wide" / f"{name}.parquet"),
        )
    # The lag filter matters: lag 0 is a different IC history, hence different weights.
    code, result = invoke(
        capsys,
        *_combine_argv(
            paths,
            tmp_path / "lag0",
            *["--ic-history", str(tidy_path), "--ic-horizon", "5", *common],
        ),
    )
    assert code == 0, result
    assert not pd.read_parquet(tmp_path / "lag0" / "factor_weights.parquet").equals(
        expected.factor_weights
    )


def test_combine_tidy_daily_ic_input_errors(factors, histories, tmp_path, capsys):
    _, paths = factors
    tidy, tidy_path, wide, wide_path, _, corr_path = histories
    out = tmp_path / "never"
    common = ["--correlation-history", str(corr_path)]

    def failing(*extra, ic_history=tidy_path):
        code, result = invoke(
            capsys, *_combine_argv(paths, out, "--ic-history", str(ic_history), *common, *extra)
        )
        assert code == 2 and result["error"]["code"] == "INVALID_INPUT", result
        assert not out.exists()
        return result["error"]["message"]

    assert "[1, 5]" in failing()  # tidy input without --ic-horizon lists the horizons
    message = failing("--ic-horizon", "7")
    assert "horizon=7" in message and "(1, 0)" in message and "(5, 2)" in message
    assert "wide table" in failing("--ic-horizon", "5", ic_history=wide_path)
    assert "wide table" in failing("--ic-lag", "2", ic_history=wide_path)
    duplicated = tmp_path / "dup.parquet"
    pd.concat([tidy, tidy.iloc[[0]]], ignore_index=True).to_parquet(duplicated)
    assert "duplicated" in failing("--ic-horizon", "1", ic_history=duplicated)
    partial = tmp_path / "partial.parquet"
    tidy[tidy["factor"] == "mom"].to_parquet(partial)
    assert "rev" in failing("--ic-horizon", "1", ic_history=partial)
    code, result = invoke(
        capsys,
        *["strategy", "combine", "--factors", f"mom={paths['mom']}", "--directions", '{"mom": 1}'],
        *["--method", "equal_rank", "--ic-horizon", "5", "--out-dir", str(out)],
    )
    assert code == 2 and "ic_horizon requires ic_history" in json.dumps(result["error"])
    assert not out.exists()


def test_combine_dynamic_method_requires_availability_delay(factors, tmp_path, capsys):
    _, paths = factors
    code, result = invoke(
        capsys,
        "strategy",
        "combine",
        "--factors",
        f"mom={paths['mom']}",
        "--directions",
        '{"mom": 1}',
        "--method",
        "rolling_ic",
        "--out-dir",
        str(tmp_path / "x"),
    )
    assert code == 2 and "availability_delay" in json.dumps(result["error"])
    assert not (tmp_path / "x").exists()


def _run_config(panel_path, **extra):
    config = {
        "panel": str(panel_path),
        "factors": [{"indicator": "roc", "params": {"period": 10}, "name": "mom"}],
        "exit_filters": [
            {
                "function": EXITS,
                "params": {"lookback": 10},
                "condition": {"op": "lt", "value": 0.08},
            }
        ],
        "top_pct": 0.4,
        "slippage_bp": 1.0,
        "rebalance_freq": "W",
    }
    config.update(extra)
    return config


def test_cs_run_matches_modular_backtester(panel, panel_path, tmp_path, capsys):
    from skills.compute.indicators import discover_indicators
    from skills.strategy.cross_sectional import ModularBacktester, drawdown_from_high_filter

    config_path, out = tmp_path / "run.json", tmp_path / "run"
    config_path.write_text(json.dumps(_run_config(panel_path, start="2024-03-01")))
    code, result = invoke(
        capsys, "strategy", "cs-run", "--input-json", str(config_path), "--out-dir", str(out)
    )
    assert code == 0, result
    backtester = ModularBacktester(
        panel,
        [
            {
                "func": discover_indicators()["roc"],
                "kwargs": {"period": 10},
                "direction": 1,
                "name": "mom",
            }
        ],
        top_pct=0.4,
        slippage_bp=1.0,
        start_date="2024-03-01",
        exit_filters=[
            {
                "func": drawdown_from_high_filter,
                "kwargs": {"lookback": 10},
                "condition": lambda values: values < 0.08,
            }
        ],
        rebalance_freq="W",
    )
    expected = backtester.run()
    pd.testing.assert_frame_equal(pd.read_parquet(out / "result_df.parquet"), expected)
    pd.testing.assert_frame_equal(
        pd.read_parquet(out / "signal_weights.parquet"), backtester.signal_weights
    )
    pd.testing.assert_frame_equal(
        pd.read_parquet(out / "executed_weights.parquet"), backtester.executed_weights
    )
    assert result["data"]["metrics"] == pytest.approx(backtester.metrics)
    assert result["data"]["weight_stats"] == {
        str(key): int(value) for key, value in backtester.get_weight_stats().items()
    }
    assert result["data"]["start"].startswith("2024-03-01")


def test_cs_run_exit_filter_without_condition_uses_the_backtester_default(
    panel, panel_path, tmp_path, capsys
):
    from skills.compute.indicators import discover_indicators
    from skills.strategy.cross_sectional import ModularBacktester, drawdown_from_high_filter

    config = _run_config(panel_path, exit_filters=[{"function": EXITS, "params": {"lookback": 10}}])
    config_path = tmp_path / "run.json"
    config_path.write_text(json.dumps(config))
    code, result = invoke(capsys, "strategy", "cs-run", "--input-json", str(config_path))
    assert code == 0, result
    backtester = ModularBacktester(
        panel,
        [
            {
                "func": discover_indicators()["roc"],
                "kwargs": {"period": 10},
                "direction": 1,
                "name": "mom",
            }
        ],
        top_pct=0.4,
        slippage_bp=1.0,
        exit_filters=[{"func": drawdown_from_high_filter, "kwargs": {"lookback": 10}}],
        rebalance_freq="W",
    )
    backtester.run()
    assert result["data"]["metrics"] == pytest.approx(backtester.metrics)
    assert result["artifacts"] == []


def test_cs_run_validates_before_running(panel_path, tmp_path, capsys):
    out = tmp_path / "taken"
    out.mkdir()
    (out / "result_df.parquet").write_bytes(b"keep")
    config_path = tmp_path / "run.json"
    config_path.write_text(json.dumps(_run_config(panel_path)))
    code, result = invoke(
        capsys, "strategy", "cs-run", "--input-json", str(config_path), "--out-dir", str(out)
    )
    assert code == 2 and result["error"]["code"] == "CONFLICT"
    assert (out / "result_df.parquet").read_bytes() == b"keep"
    bad = _run_config(panel_path, factors=[{"indicator": "roc", "function": EXITS}])
    config_path.write_text(json.dumps(bad))
    code, result = invoke(capsys, "strategy", "cs-run", "--input-json", str(config_path))
    assert code == 2 and "Exactly one" in json.dumps(result["error"])
    unknown = _run_config(panel_path, factors=[{"indicator": "no_such_indicator"}])
    config_path.write_text(json.dumps(unknown))
    code, result = invoke(capsys, "strategy", "cs-run", "--input-json", str(config_path))
    assert code == 2 and "Unknown indicator" in result["error"]["message"]


def test_cli_chain_mirrors_the_lesson06_dynamic_weight_flow(panel, panel_path, tmp_path, capsys):
    """ic-surface -> factor-correlation -> combine, all on direction-oriented factors."""
    from skills.analyze.factor_information import (
        compute_ic_information_surface,
        rolling_factor_rank_correlation,
    )
    from skills.strategy.cross_sectional import DynamicFactorWeightConfig, combine_factor_scores
    from skills.strategy.cross_sectional.factor_combination import (
        orient_factor_frames,
        rank_factor_frames,
    )

    close = panel["close"].unstack("symbol").sort_index()
    raw = {
        "mom": close.pct_change(10, fill_method=None),
        "rev": close.pct_change(3, fill_method=None),
        "vol": close.pct_change(fill_method=None).rolling(10).std(),
    }
    directions = {"mom": 1, "rev": -1, "vol": -1}
    paths = {}
    for name, frame in raw.items():
        paths[name] = tmp_path / f"{name}.parquet"
        frame.to_parquet(paths[name])
    factor_args = [item for name, path in paths.items() for item in ("--factors", f"{name}={path}")]
    horizon, signal_lag = 5, 1
    ic_dir, corr_dir, out = tmp_path / "ic", tmp_path / "corr", tmp_path / "combined"

    code, result = invoke(
        capsys,
        *["analyze", "ic-surface", "--panel", str(panel_path), *factor_args],
        *["--directions", json.dumps(directions), "--horizons", str(horizon)],
        *["--signal-lag", str(signal_lag), "--min-cross-section", "3", "--out-dir", str(ic_dir)],
    )
    assert code == 0, result
    code, result = invoke(
        capsys,
        *["analyze", "factor-correlation", *factor_args, "--directions", json.dumps(directions)],
        *["--window", "40", "--min-periods", "20", "--out-dir", str(corr_dir)],
    )
    assert code == 0, result
    code, result = invoke(
        capsys,
        *["strategy", "combine", *factor_args, "--directions", json.dumps(directions)],
        *["--method", "max_ic", "--top-n", "2", "--max-weight", "0.6"],
        *["--ic-history", str(ic_dir / "daily_ic.parquet"), "--ic-horizon", str(horizon)],
        *["--correlation-history", str(corr_dir / "correlation_history.parquet")],
        *["--availability-delay", str(signal_lag + horizon), "--lookback", "60"],
        *["--min-periods", "20", "--out-dir", str(out)],
    )
    assert code == 0, result

    oriented = orient_factor_frames(raw, directions)
    daily_ic = compute_ic_information_surface(
        oriented, close, horizons=[horizon], lags=[0], signal_lag=signal_lag, min_cross_section=3
    ).daily_ic
    ic_history = daily_ic.pivot(index="eob", columns="factor", values="ic")
    config = DynamicFactorWeightConfig(
        availability_delay=signal_lag + horizon, lookback=60, min_periods=20, max_weight=0.6
    )
    expected = combine_factor_scores(
        raw,
        method="max_ic",
        directions=directions,
        top_n=2,
        ic_history=ic_history,
        correlation_history=rolling_factor_rank_correlation(
            rank_factor_frames(oriented), window=40, min_periods=20
        ),
        dynamic_config=config,
    )
    _assert_result(out, expected)
    # The weights are genuinely dynamic, not the equal-weight fallback.
    weights = expected.factor_weights
    assert weights.iloc[-1].nunique() > 1 and weights.nunique().max() > 2
    # Feeding IC computed on the raw (unoriented) factors would give a different answer.
    raw_ic = compute_ic_information_surface(
        raw, close, horizons=[horizon], lags=[0], signal_lag=signal_lag, min_cross_section=3
    ).daily_ic.pivot(index="eob", columns="factor", values="ic")
    misoriented = combine_factor_scores(
        raw,
        method="max_ic",
        directions=directions,
        top_n=2,
        ic_history=raw_ic,
        correlation_history=rolling_factor_rank_correlation(
            rank_factor_frames(oriented), window=40, min_periods=20
        ),
        dynamic_config=config,
    )
    assert not misoriented.factor_weights.equals(expected.factor_weights)
