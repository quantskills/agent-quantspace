from __future__ import annotations

import pandas as pd
import pytest

from skills.compute.wrappers import Factor
from tests.fixtures.market_data import make_panel


def _close_return(group: pd.DataFrame, lookback: int = 1) -> pd.Series:
    return group["close"].pct_change(lookback)


def test_factor_calculate_applies_function_by_symbol() -> None:
    panel = make_panel(("AAA", "BBB"), periods=4)

    result = Factor(_close_return, lookback=1).calculate(panel)

    assert result.index.names == ["symbol", "eob"]
    assert set(result.index.get_level_values("symbol")) == {"AAA", "BBB"}


def test_factor_calculate_can_preserve_warmup_nans() -> None:
    panel = make_panel(("AAA",), periods=5)
    dropped = Factor(_close_return, lookback=2).calculate(panel, dropna=True)
    kept = Factor(_close_return, lookback=2).calculate(panel, dropna=False)
    assert dropped.isna().sum() == 0
    assert kept.isna().sum() == 2
    assert kept.index.equals(panel.index)


def test_factor_cal_df_returns_wide_eob_by_symbol() -> None:
    panel = make_panel(("AAA", "BBB"), periods=5)
    wide_drop = Factor(_close_return, lookback=2).cal_df(panel, dropna=True)
    wide_keep = Factor(_close_return, lookback=2).cal_df(panel, dropna=False)
    assert list(wide_drop.columns) == ["AAA", "BBB"]
    assert wide_drop.index.name == "eob"
    assert not isinstance(wide_drop.index, pd.MultiIndex)
    assert wide_drop.isna().sum().sum() == 0
    assert wide_keep.shape == (5, 2)
    assert wide_keep.isna().sum().sum() == 4


def test_factor_rejects_invalid_output_shapes_and_dtypes() -> None:
    panel = make_panel(("AAA",), periods=4)

    def bad_index(group: pd.DataFrame) -> pd.Series:
        return group["close"].iloc[1:]

    def bad_scalar(group: pd.DataFrame) -> float:
        return 1.0

    def bad_frame(group: pd.DataFrame) -> pd.DataFrame:
        return group[["close"]]

    def bad_bool(group: pd.DataFrame) -> pd.Series:
        return group["close"] > 0

    def bad_complex(group: pd.DataFrame) -> pd.Series:
        return pd.Series([1 + 0j] * len(group), index=group.index)

    def bad_reorder(group: pd.DataFrame) -> pd.Series:
        return group["close"].iloc[::-1]

    with pytest.raises(ValueError, match="index"):
        Factor(bad_index).calculate(panel, dropna=False)
    with pytest.raises(TypeError, match="Series"):
        Factor(bad_scalar).calculate(panel, dropna=False)
    with pytest.raises(TypeError, match="Series"):
        Factor(bad_frame).calculate(panel, dropna=False)
    with pytest.raises(TypeError, match="boolean"):
        Factor(bad_bool).calculate(panel, dropna=False)
    with pytest.raises(TypeError, match="complex"):
        Factor(bad_complex).calculate(panel, dropna=False)
    with pytest.raises(ValueError, match="index"):
        Factor(bad_reorder).calculate(panel, dropna=False)


def test_factor_rejects_non_multiindex_input() -> None:
    with pytest.raises(ValueError, match="MultiIndex"):
        Factor(_close_return).calculate(pd.DataFrame({"close": [1.0, 2.0]}))
