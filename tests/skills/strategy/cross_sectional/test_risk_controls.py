from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from skills.strategy.cross_sectional.risk_controls import apply_risk_controls, universe_vol_exposure


def _close_frame() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=8, name="eob")
    return pd.DataFrame(
        {
            "AAA": [100.0, 100.2, 100.4, 100.6, 90.0, 110.0, 95.0, 120.0],
            "BBB": [50.0, 50.1, 50.2, 50.3, 45.0, 55.0, 47.5, 60.0],
        },
        index=index,
    )


def test_universe_vol_exposure_scales_active_dates_to_target_gross() -> None:
    close = _close_frame()
    weights = pd.DataFrame(1.0, index=close.index, columns=close.columns).div(2.0)

    adjusted, diagnostics = universe_vol_exposure(
        weights,
        close,
        {
            "window": 2,
            "threshold_quantile": 0.5,
            "threshold_window": 3,
            "min_threshold_obs": 1,
            "target_gross": 0.75,
            "released_budget": "cash",
        },
    )

    active = diagnostics["risk_control_active"].fillna(False)
    assert active.any()
    pd.testing.assert_series_equal(
        adjusted.sum(axis=1).loc[active],
        pd.Series(0.75, index=adjusted.index[active]),
        check_names=False,
    )
    assert {
        "universe_vol",
        "threshold",
        "target_gross_before",
        "target_gross_after",
    }.issubset(diagnostics)


def test_universe_vol_exposure_uses_absolute_gross_for_long_short_weights() -> None:
    close = _close_frame()
    weights = pd.DataFrame(
        {"AAA": 0.75, "BBB": -0.25},
        index=close.index,
    )

    adjusted, diagnostics = universe_vol_exposure(
        weights,
        close,
        {
            "window": 2,
            "threshold_quantile": 0.5,
            "threshold_window": 3,
            "min_threshold_obs": 1,
            "target_gross": 0.75,
            "released_budget": "cash",
        },
    )

    active = diagnostics["risk_control_active"].fillna(False)
    assert active.any()
    pd.testing.assert_series_equal(
        adjusted.abs().sum(axis=1).loc[active],
        pd.Series(0.75, index=adjusted.index[active]),
        check_names=False,
    )


@dataclass
class _RiskControl:
    name: str
    fn: str
    args: dict


def test_apply_risk_controls_accepts_dataclass_configs_and_prefixes_diagnostics() -> None:
    close = _close_frame()
    weights = pd.DataFrame(0.5, index=close.index, columns=close.columns)

    _, diagnostics = apply_risk_controls(
        weights,
        close,
        [
            _RiskControl(
                name="universe_guard",
                fn="universe_vol_exposure",
                args={"window": 2, "threshold_window": 3, "min_threshold_obs": 1},
            )
        ],
    )

    assert all(column.startswith("universe_guard__") for column in diagnostics)


def test_risk_controls_reject_invalid_configuration() -> None:
    close = _close_frame()
    weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns).fillna(0.5)

    with pytest.raises(ValueError, match="unknown_control"):
        apply_risk_controls(weights, close, [{"fn": "unknown_control"}])
    with pytest.raises(ValueError, match="released_budget"):
        universe_vol_exposure(weights, close, {"released_budget": "gold"})
