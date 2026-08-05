from __future__ import annotations

import importlib
import importlib.util

import pytest

PUBLIC_MODULES = [
    "skills.ingest",
    "skills.ingest.panda_data",
    "skills.ingest.symbol_map",
    "skills.store.data_manager",
    "skills.compute.label_maker",
    "skills.compute.indicators",
    "skills.backtest",
    "skills.backtest.cost_model",
    "skills.backtest.exit_analysis",
    "skills.backtest.filters",
    "skills.backtest.overlay_metrics",
    "skills.backtest.weighting",
    "skills.analyze.factor_analysis",
    "skills.ml.lasso_tracker",
    "skills.ml.ml_engine",
    "skills.ml.ml_factor",
    "skills.research",
    "skills.report",
    "skills.report.strategy_markdown",
    "skills.factor_mining",
    "skills.factor_mining.contracts",
    "skills.factor_mining.ports",
    "skills.strategy",
    "skills.strategy.contracts",
    "skills.strategy.ports",
    "skills.strategy.cross_sectional",
    "skills.strategy.cross_sectional.modular_backtester",
    "skills.strategy.cross_sectional.strategy_comparison",
    "skills.strategy.time_series",
    "strategies.cross_sectional.factors",
    "strategies.cross_sectional.rules",
    "strategies.cross_sectional.ml_rank",
    "strategies.time_series.rules",
    "strategies.time_series.features",
    "strategies.time_series.ml",
]


def test_public_modules_import() -> None:
    for module in PUBLIC_MODULES:
        importlib.import_module(module)


def test_ingest_public_api() -> None:
    from skills.ingest import PandaDataClient, to_panda_data_symbol, to_quantspace_symbol

    assert PandaDataClient is not None
    assert to_panda_data_symbol("SHSE.510300") == "510300.SH"
    assert to_quantspace_symbol("510300.SH") == "SHSE.510300"


def test_removed_compute_modules_are_not_importable() -> None:
    removed_modules = [
        "skills.compute.cs_factor_examples",
        "skills.compute.ts_factor_examples",
        "skills.compute.ts_features",
        "skills.compute.ts_features_base",
        "skills.compute." + "j" + "q_etf_cs_library",
        "skills.compute." + "j" + "q_ts_library",
    ]
    for module in removed_modules:
        assert importlib.util.find_spec(module) is None
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)


def test_strategy_public_api() -> None:
    from skills.strategy import (
        StrategyContext,
        StrategyResult,
        TimeSeriesConfig,
        WeightGenerator,
        signal_to_single_asset_weights,
        top_n_weights,
    )
    from skills.strategy.cross_sectional import (
        FactorFrameBuilder,
        ModularBacktester,
        compare_strategies,
        drawdown_from_high_filter,
    )

    for symbol in [
        StrategyContext,
        StrategyResult,
        TimeSeriesConfig,
        WeightGenerator,
        signal_to_single_asset_weights,
        top_n_weights,
        FactorFrameBuilder,
        ModularBacktester,
        compare_strategies,
        drawdown_from_high_filter,
    ]:
        assert symbol is not None


def test_removed_strategy_type_modules_are_not_importable() -> None:
    cross_sectional = "strategies." + "cross_sectional"
    time_series = "strategies." + "time_series"
    removed_modules = [
        f"{cross_sectional}.exits",
        f"{cross_sectional}.factor_frame",
        f"{cross_sectional}.io",
        f"{cross_sectional}.modular_backtester",
        f"{cross_sectional}.plotting",
        f"{cross_sectional}.signals_base",
        f"{cross_sectional}.signals_top_pct",
        f"{cross_sectional}.types",
        f"{time_series}.signal_engine",
        f"{time_series}.types",
        "skills.research." + "strategy_comparison",
    ]
    for module in removed_modules:
        assert importlib.util.find_spec(module) is None
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)


def test_strategy_packages_do_not_reexport_removed_types() -> None:
    cross_sectional = importlib.import_module("strategies.cross_sectional")
    time_series = importlib.import_module("strategies.time_series")

    for name in ["ModularBacktester", "FactorFrameBuilder", "TopPctStrategy"]:
        assert not hasattr(cross_sectional, name)
    for name in ["SignalEngine", "TimeSeriesBacktester", "TimeSeriesConfig"]:
        assert not hasattr(time_series, name)


def test_removed_skill_boundaries_are_not_importable() -> None:
    removed_modules = [
        "skills." + "construct",
        "skills." + "construct" + ".weighting",
        "skills." + "model",
        "skills." + "model" + ".ml_engine",
        "skills.analyze." + "backtest",
        "skills.analyze." + "exit_analysis",
        "skills.analyze." + "overlay_metrics",
        "skills.compute." + "cost_model",
    ]
    for module in removed_modules:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)
