"""Helpers shared by Phase 03 analyze tests."""

from __future__ import annotations

from skills.analyze.contracts import ProtocolSnapshot, SpecSnapshot


def make_protocol(**overrides: object) -> ProtocolSnapshot:
    payload = {
        "horizon_bars": 1,
        "direction": "long_high",
        "n_groups": 3,
        "tie_rule": "average",
        "rebalance": "daily",
        "commission": 0.0,
        "slippage": 0.0,
        "parameter_neighborhood": {},
        "regimes": (),
        "time_subsamples": (),
        "random_seed": 7,
        "multiple_testing_budget": 5,
        "thresholds": {},
        "symbol_level": "symbol",
        "datetime_level": "eob",
        "timezone": "naive",
        "required_fields": ("close",),
        "min_cross_section": 2,
        "min_ic_samples": 2,
        "bootstrap_samples": 20,
        "bootstrap_block_size": 3,
        "ic_decay_horizons": (1,),
        "trade_at": "close",
        "signal_lag": 1,
        "return_mode": "forward",
        "allow_short": True,
        "require_prefix_recompute": False,
        "universe": (),
    }
    payload.update(overrides)
    return ProtocolSnapshot(**payload)  # type: ignore[arg-type]


def make_spec(**overrides: object) -> SpecSnapshot:
    payload = {
        "factor_id": "factor-1",
        "formula_kind": "function_ref",
        "function_module": "skills.compute.indicators",
        "function_name": "roc",
        "expression": None,
        "params": {"period": 2},
        "required_fields": ("close",),
        "window": 2,
        "lag": 0,
        "warmup": 2,
        "missing_policy": "keep_nan",
        "output_dtype": "float64",
        "expected_direction": "long_high",
        "content_hash": "a" * 64,
        "formula_fingerprint": "b" * 64,
    }
    payload.update(overrides)
    return SpecSnapshot(**payload)  # type: ignore[arg-type]
