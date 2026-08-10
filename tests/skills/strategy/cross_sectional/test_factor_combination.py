from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from skills.strategy.cross_sectional.factor_combination import (
    DynamicFactorWeightConfig,
    combine_factor_scores,
    estimate_factor_weights,
    normalize_factor_frames,
    orient_factor_frames,
)


def _factors(periods: int = 320) -> dict[str, pd.DataFrame]:
    dates = pd.bdate_range("2020-01-01", periods=periods)
    columns = [f"s{i}" for i in range(6)]
    base = pd.DataFrame(np.tile(np.arange(6), (periods, 1)), index=dates, columns=columns)
    return {"a": base, "b": base.iloc[:, ::-1].set_axis(columns, axis=1), "c": base * 0.5}


def _ic_history(dates: pd.Index) -> pd.DataFrame:
    x = np.arange(len(dates), dtype=float)
    return pd.DataFrame(
        {
            "a": 0.04 + np.sin(x / 11.0) * 0.01,
            "b": 0.02 + np.cos(x / 13.0) * 0.01,
            "c": 0.01 + np.sin(x / 17.0) * 0.005,
        },
        index=dates,
    )


def _correlation_history(dates: pd.Index, *, ab: float = 0.2) -> pd.DataFrame:
    rows = []
    for date in dates:
        rows.extend(
            [
                {"eob": date, "factor_a": "a", "factor_b": "b", "correlation": ab},
                {"eob": date, "factor_a": "a", "factor_b": "c", "correlation": 0.0},
                {"eob": date, "factor_a": "b", "factor_b": "c", "correlation": 0.0},
            ]
        )
    return pd.DataFrame(rows)


def _directions() -> dict[str, int]:
    return {"a": 1, "b": 1, "c": 1}


def test_direction_correction_makes_higher_mean_more_bullish() -> None:
    factors = _factors(periods=3)
    oriented = orient_factor_frames(factors, {"a": 1, "b": -1, "c": 1})
    pd.testing.assert_frame_equal(oriented["a"], factors["a"], check_dtype=False)
    pd.testing.assert_frame_equal(oriented["b"], -factors["b"], check_dtype=False)


def test_rank_normalization_is_daily_cross_sectional_percentile() -> None:
    factors = {"a": _factors(periods=2)["a"]}
    normalized = normalize_factor_frames(factors, method="rank")["a"]
    expected = factors["a"].rank(axis=1, pct=True, method="average")
    pd.testing.assert_frame_equal(normalized, expected)


def test_zscore_normalization_is_daily_cross_sectional_population_zscore() -> None:
    frame = _factors(periods=3)["a"].astype(float)
    frame.iloc[1] = 2.0
    frame.iloc[2, 0] = np.nan
    normalized = normalize_factor_frames({"a": frame}, method="zscore")["a"]
    assert normalized.iloc[0].mean() == pytest.approx(0.0)
    assert normalized.iloc[0].std(ddof=0) == pytest.approx(1.0)
    assert normalized.iloc[1].eq(0.0).all()
    assert np.isnan(normalized.iloc[2, 0])
    assert normalized.iloc[2].dropna().mean() == pytest.approx(0.0)
    assert normalized.iloc[2].dropna().std(ddof=0) == pytest.approx(1.0)


def test_normalization_rejects_unknown_method() -> None:
    with pytest.raises(ValueError, match="rank.*zscore"):
        normalize_factor_frames(_factors(periods=2), method="raw")  # type: ignore[arg-type]


@pytest.mark.parametrize("normalization", ["rank", "zscore"])
def test_public_combination_orients_and_normalizes_raw_factors(normalization: str) -> None:
    factors = _factors(periods=3)
    raw = {"a": factors["a"], "b": factors["b"] * 10_000.0}
    result = combine_factor_scores(
        raw,
        method="equal_rank",
        directions={"a": 1, "b": -1},
        normalization=normalization,  # type: ignore[arg-type]
        top_n=1,
    )
    assert result.target_weights["s5"].eq(1.0).all()


def test_equal_vote_all_missing_cross_section_holds_cash() -> None:
    dates = pd.DatetimeIndex(["2024-01-02"], name="eob")
    columns = ["ETF_A", "ETF_B", "ETF_C", "ETF_D"]
    missing = pd.DataFrame(np.nan, index=dates, columns=columns)
    result = combine_factor_scores(
        {"a": missing, "b": missing.copy()},
        method="equal_vote",
        directions={"a": 1, "b": 1},
        top_n=3,
    )
    assert result.composite_scores.iloc[0].isna().all()
    assert result.target_weights.iloc[0].eq(0.0).all()


def test_equal_vote_excludes_asset_with_no_available_factors() -> None:
    dates = pd.DatetimeIndex(["2024-01-02"], name="eob")
    factors = {
        "a": pd.DataFrame([[np.nan, 3.0, 1.0]], index=dates, columns=["A", "B", "C"]),
        "b": pd.DataFrame([[np.nan, 1.0, 3.0]], index=dates, columns=["A", "B", "C"]),
    }
    result = combine_factor_scores(
        factors,
        method="equal_vote",
        directions={"a": 1, "b": 1},
        top_n=3,
    )
    assert np.isnan(result.composite_scores.loc[dates[0], "A"])
    assert result.target_weights.loc[dates[0], "A"] == 0.0
    assert result.target_weights.loc[dates[0], ["B", "C"]].to_numpy() == pytest.approx(
        [0.5, 0.5]
    )


def test_equal_vote_tie_break_uses_available_factors_only() -> None:
    dates = pd.DatetimeIndex(["2024-01-02"], name="eob")
    factors = {
        "a": pd.DataFrame([[3.0, 2.0, 1.0]], index=dates, columns=["A", "B", "C"]),
        "b": pd.DataFrame([[np.nan, 1.0, 3.0]], index=dates, columns=["A", "B", "C"]),
    }
    result = combine_factor_scores(
        factors,
        method="equal_vote",
        directions={"a": 1, "b": 1},
        top_n=1,
    )
    assert result.target_weights.loc[dates[0], "A"] == 1.0
    assert result.target_weights.loc[dates[0], ["B", "C"]].eq(0.0).all()


@pytest.mark.parametrize("normalization", ["rank", "zscore"])
def test_equal_vote_missing_policy_is_consistent_across_normalizations(
    normalization: str,
) -> None:
    dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03"], name="eob")
    factors = {
        "a": pd.DataFrame(
            [[np.nan, np.nan, np.nan], [3.0, 2.0, 1.0]],
            index=dates,
            columns=["A", "B", "C"],
        ),
        "b": pd.DataFrame(
            [[np.nan, np.nan, np.nan], [1.0, 2.0, 3.0]],
            index=dates,
            columns=["A", "B", "C"],
        ),
    }
    result = combine_factor_scores(
        factors,
        method="equal_vote",
        directions={"a": 1, "b": 1},
        normalization=normalization,  # type: ignore[arg-type]
        top_n=2,
    )
    assert result.target_weights.loc[dates[0]].eq(0.0).all()
    assert result.target_weights.loc[dates[1]].sum() == pytest.approx(1.0)
    assert result.target_weights.loc[dates[1]].gt(0.0).sum() == 2


@pytest.mark.parametrize(
    "method", ["equal_rank", "equal_vote", "rolling_ic", "rolling_icir", "max_icir"]
)
def test_five_methods_produce_valid_weights(method: str) -> None:
    factors = _factors()
    dates = next(iter(factors.values())).index
    kwargs = {}
    if not method.startswith("equal"):
        kwargs = {
            "ic_history": _ic_history(dates),
            "dynamic_config": DynamicFactorWeightConfig(availability_delay=6),
        }
        if method == "max_icir":
            kwargs["correlation_history"] = _correlation_history(dates)
    result = combine_factor_scores(
        factors, method=method, directions=_directions(), normalization="rank", top_n=3, **kwargs
    )
    assert (result.factor_weights >= 0).all().all()
    assert result.factor_weights.max().max() <= 0.5 + 1e-12
    assert np.allclose(result.factor_weights.sum(axis=1), 1.0)
    assert (result.target_weights.gt(0).sum(axis=1) <= 3).all()
    assert np.allclose(result.target_weights.sum(axis=1), 1.0)


def test_dynamic_weights_are_causal_and_fallback_to_equal() -> None:
    factors = _factors()
    dates = next(iter(factors.values())).index
    ic = pd.DataFrame({"a": 0.04, "b": 0.02, "c": -0.01}, index=dates)
    config = DynamicFactorWeightConfig(availability_delay=6)
    before = combine_factor_scores(
        factors,
        method="rolling_ic",
        directions=_directions(),
        ic_history=ic,
        dynamic_config=config,
    )
    assert np.allclose(before.factor_weights.iloc[0], 1.0 / 3.0)
    mutated = ic.copy()
    mutated.loc[dates[250] :, "a"] = 100.0
    after = combine_factor_scores(
        factors,
        method="rolling_ic",
        directions=_directions(),
        ic_history=mutated,
        dynamic_config=config,
    )
    pd.testing.assert_frame_equal(
        before.factor_weights.loc[: dates[255]], after.factor_weights.loc[: dates[255]]
    )
    pd.testing.assert_frame_equal(
        before.target_weights.loc[: dates[255]], after.target_weights.loc[: dates[255]]
    )


def test_max_icir_requires_tidy_correlation_history() -> None:
    dates = _factors().get("a").index
    with pytest.raises(ValueError, match="correlation_history"):
        estimate_factor_weights(
            method="max_icir",
            factor_names=["a", "b", "c"],
            dates=dates,
            ic_history=_ic_history(dates),
            dynamic_config=DynamicFactorWeightConfig(availability_delay=6),
        )


def test_max_icir_reduces_duplicate_factor_exposure() -> None:
    dates = pd.bdate_range("2020-01-01", periods=80)
    x = np.arange(len(dates), dtype=float)
    ic = pd.DataFrame(
        {
            "a": 0.04 + np.sin(x / 5.0) * 0.01,
            "b": 0.04 + np.sin(x / 5.0) * 0.01,
            "c": 0.02 + np.sin(x / 7.0) * 0.005,
        },
        index=dates,
    )
    config = DynamicFactorWeightConfig(
        availability_delay=1, lookback=20, min_periods=10, max_weight=0.8
    )
    plain = estimate_factor_weights(
        method="rolling_icir",
        factor_names=["a", "b", "c"],
        dates=dates,
        ic_history=ic,
        dynamic_config=config,
    )
    adjusted = estimate_factor_weights(
        method="max_icir",
        factor_names=["a", "b", "c"],
        dates=dates,
        ic_history=ic,
        correlation_history=_correlation_history(dates, ab=0.99),
        dynamic_config=config,
    )
    assert adjusted.iloc[-1]["c"] > plain.iloc[-1]["c"]


def test_future_correlation_mutation_does_not_change_available_weights() -> None:
    dates = pd.bdate_range("2020-01-01", periods=80)
    config = DynamicFactorWeightConfig(
        availability_delay=6, lookback=20, min_periods=10, max_weight=0.8
    )
    history = _correlation_history(dates)
    before = estimate_factor_weights(
        method="max_icir",
        factor_names=["a", "b", "c"],
        dates=dates,
        ic_history=_ic_history(dates),
        correlation_history=history,
        dynamic_config=config,
    )
    mutated = history.copy()
    mutated.loc[mutated["eob"] >= dates[50], "correlation"] = 0.99
    after = estimate_factor_weights(
        method="max_icir",
        factor_names=["a", "b", "c"],
        dates=dates,
        ic_history=_ic_history(dates),
        correlation_history=mutated,
        dynamic_config=config,
    )
    pd.testing.assert_frame_equal(before.loc[: dates[55]], after.loc[: dates[55]])


def test_dynamic_weight_config_rejects_infeasible_cap() -> None:
    dates = pd.bdate_range("2020-01-01", periods=20)
    with pytest.raises(ValueError, match="infeasible"):
        estimate_factor_weights(
            method="rolling_ic",
            factor_names=["a", "b", "c"],
            dates=dates,
            ic_history=_ic_history(dates),
            dynamic_config=DynamicFactorWeightConfig(
                availability_delay=1, lookback=10, min_periods=5, max_weight=0.3
            ),
        )
