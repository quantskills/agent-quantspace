from __future__ import annotations

import importlib.util

import pandas as pd
import pytest

import skills.strategy.cross_sectional as cross_sectional
import strategies.cross_sectional as concrete_domain


@pytest.mark.parametrize(
    "module_suffix",
    [
        "exits",
        "factor_frame",
        "io",
        "modular_backtester",
        "plotting",
        "signals_base",
        "signals_top_pct",
        "types",
    ],
)
def test_removed_cross_sectional_type_modules_are_not_discoverable(module_suffix: str) -> None:
    legacy_domain = ".".join(("strategies", "cross_sectional"))
    module_name = f"{legacy_domain}.{module_suffix}"
    assert importlib.util.find_spec(module_name) is None


def test_concrete_domain_does_not_reexport_generic_types() -> None:
    generic_names = {
        "BaseStrategy",
        "FactorFrameBuilder",
        "ModularBacktester",
        "TopPctStrategy",
    }

    assert generic_names.isdisjoint(vars(concrete_domain))
    assert concrete_domain.__all__ == []


def test_reusable_domain_exports_selection_exit_and_risk_types() -> None:
    expected = {
        "FactorFrameBuilder",
        "ModularBacktester",
        "TopPctStrategy",
        "apply_risk_controls",
        "drawdown_from_high_filter",
        "universe_vol_exposure",
        "top_n_weights",
    }

    assert expected.issubset(cross_sectional.__all__)
    assert all(hasattr(cross_sectional, name) for name in expected)


def test_cross_sectional_skill_does_not_export_etf_specific_nav_logic() -> None:
    from skills.strategy.cross_sectional import exits

    assert not hasattr(cross_sectional, "etf_premium_rate")
    assert not hasattr(exits, "etf_premium_rate")


def test_top_n_weights_selects_valid_highest_scores() -> None:
    scores = pd.DataFrame(
        {
            "AAA": [0.2, float("nan")],
            "BBB": [0.8, 0.4],
            "CCC": [0.5, float("nan")],
        },
        index=pd.date_range("2024-01-01", periods=2, name="eob"),
    )

    weights = cross_sectional.top_n_weights(scores, top_n=2, gross_exposure=0.8)

    assert weights.iloc[0].to_dict() == pytest.approx({"AAA": 0.0, "BBB": 0.4, "CCC": 0.4})
    assert weights.iloc[1].to_dict() == pytest.approx({"AAA": 0.0, "BBB": 0.8, "CCC": 0.0})


@pytest.mark.parametrize("top_n", [0, -1])
def test_top_n_weights_rejects_non_positive_selection_size(top_n: int) -> None:
    with pytest.raises(ValueError, match="top_n"):
        cross_sectional.top_n_weights(pd.DataFrame({"AAA": [1.0]}), top_n=top_n)


def test_exit_module_does_not_keep_compatibility_alias() -> None:
    from skills.strategy.cross_sectional import exits

    assert not hasattr(exits, "trailing_drawdown_stop")
