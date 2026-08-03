"""Reusable position-level risk controls for cross-sectional portfolios."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

import numpy as np
import pandas as pd


def _control_to_dict(control: Any) -> dict[str, Any]:
    if isinstance(control, dict):
        return control
    if is_dataclass(control):
        return asdict(control)
    raise TypeError("risk control must be a dict or dataclass instance.")


def universe_vol_exposure(
    weights: pd.DataFrame,
    close: pd.DataFrame,
    args: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scale total exposure when the instrument universe volatility is elevated."""
    window = int(args.get("window", 20))
    threshold_quantile = float(args.get("threshold_quantile", 0.75))
    threshold_window = int(args.get("threshold_window", 252))
    min_threshold_obs = int(args.get("min_threshold_obs", min(20, threshold_window)))
    target_gross = float(args.get("target_gross", 0.75))
    released_budget = str(args.get("released_budget", "cash"))

    if window <= 0:
        raise ValueError("window must be positive.")
    if threshold_window <= 0:
        raise ValueError("threshold_window must be positive.")
    if min_threshold_obs <= 0:
        raise ValueError("min_threshold_obs must be positive.")
    if not 0.0 < threshold_quantile < 1.0:
        raise ValueError("threshold_quantile must be between 0 and 1.")
    if not 0.0 <= target_gross <= 1.0:
        raise ValueError("target_gross must be in [0, 1].")
    if released_budget != "cash":
        raise ValueError("released_budget currently only supports 'cash'.")

    aligned_close = close.reindex(index=weights.index, columns=weights.columns)
    returns = aligned_close.pct_change(fill_method=None)
    universe_vol = (
        returns.rolling(window, min_periods=window).std().mul(np.sqrt(252.0)).mean(axis=1)
    )
    threshold = (
        universe_vol.shift(1)
        .rolling(threshold_window, min_periods=min(min_threshold_obs, threshold_window))
        .quantile(threshold_quantile)
    )
    active = universe_vol.gt(threshold).fillna(False)

    clean_weights = weights.fillna(0.0).astype(float)
    before_gross = clean_weights.abs().sum(axis=1)
    scale = pd.Series(1.0, index=clean_weights.index)
    positive_gross = before_gross.gt(0.0)
    scale.loc[active & positive_gross] = (
        target_gross / before_gross.loc[active & positive_gross]
    ).clip(upper=1.0)
    adjusted = clean_weights.mul(scale, axis=0)
    after_gross = adjusted.abs().sum(axis=1)

    diagnostics = pd.DataFrame(
        {
            "risk_control_active": active,
            "universe_vol": universe_vol,
            "threshold": threshold,
            "target_gross_before": before_gross,
            "target_gross_after": after_gross,
        },
        index=weights.index,
    )
    return adjusted, diagnostics


RISK_CONTROL_REGISTRY = {
    "universe_vol_exposure": universe_vol_exposure,
}


def apply_risk_controls(
    weights: pd.DataFrame,
    close: pd.DataFrame,
    controls: list[Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply configured risk controls in order."""
    adjusted = weights.copy()
    diagnostics: list[pd.DataFrame] = []
    for control in controls:
        data = _control_to_dict(control)
        fn_name = data["fn"]
        if fn_name not in RISK_CONTROL_REGISTRY:
            raise ValueError(f"Unknown risk control function: {fn_name}")
        adjusted, diag = RISK_CONTROL_REGISTRY[fn_name](
            adjusted,
            close,
            dict(data.get("args", {})),
        )
        diag = diag.add_prefix(f"{data.get('name', fn_name)}__")
        diagnostics.append(diag)

    if diagnostics:
        return adjusted, pd.concat(diagnostics, axis=1)
    return adjusted, pd.DataFrame(index=weights.index)


__all__ = ["RISK_CONTROL_REGISTRY", "apply_risk_controls", "universe_vol_exposure"]
