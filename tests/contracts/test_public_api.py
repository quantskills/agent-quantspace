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
    "strategies.cross_sectional.factors",
    "strategies.cross_sectional.rules",
    "strategies.cross_sectional.ml_rank",
    "strategies.cross_sectional.modular_backtester",
    "strategies.time_series.rules",
    "strategies.time_series.features",
    "strategies.time_series.ml",
    "strategies.time_series.signal_engine",
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
