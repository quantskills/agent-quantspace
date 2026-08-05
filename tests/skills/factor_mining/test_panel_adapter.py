"""Panel normalization / restoration tests for factor_mining Phase 02."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from skills.factor_mining.adapters.panel import (
    PanelAdapterError,
    normalize_panel,
    restore_series,
)
from skills.factor_mining.contracts import FailureCode
from tests.fixtures.market_data import make_panel


def _assert_panel_unchanged(before: pd.DataFrame, after: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(before, after)


@pytest.mark.parametrize(
    "datetime_name",
    ["eob", "datetime", "date", "timestamp", "trade_date", None],
)
def test_normalize_datetime_level_name_matrix(datetime_name) -> None:
    panel = make_panel(("AAA", "BBB"), periods=4)
    names = ["symbol", datetime_name]
    panel = panel.copy()
    panel.index = panel.index.set_names(names)
    before = panel.copy(deep=True)
    normalized = normalize_panel(panel, required_fields=("close",))
    _assert_panel_unchanged(before, panel)
    assert normalized.index_schema.datetime_level == datetime_name
    restored = restore_series(normalized.frame["close"].astype(float), normalized)
    assert restored.index.equals(panel.index)


def test_normalize_reversed_order_tz_dst_unsorted_and_identity() -> None:
    panel = make_panel(("BBB", "AAA"), periods=3).sort_index(ascending=False)
    swapped = panel.copy()
    swapped.index = swapped.index.reorder_levels(["eob", "symbol"]).set_names(
        ["date", "symbol"]
    )
    # Attach America/New_York wall times.
    ny = pd.DatetimeIndex(swapped.index.get_level_values(0), tz="America/New_York")
    swapped.index = pd.MultiIndex.from_arrays(
        [ny, swapped.index.get_level_values(1)],
        names=["date", "symbol"],
    )
    before = swapped.copy(deep=True)
    normalized = normalize_panel(swapped, required_fields=("close", "volume"))
    _assert_panel_unchanged(before, swapped)
    assert normalized.index_schema.level_order == (1, 0)
    assert normalized.index_schema.timezone == "America/New_York"
    values = pd.Series(
        np.linspace(0.0, 1.0, len(normalized.frame)),
        index=normalized.frame.index,
    )
    restored = restore_series(values, normalized)
    assert list(restored.index) == list(swapped.index)


@pytest.mark.parametrize(
    ("factory", "code"),
    [
        (lambda: "not-a-frame", FailureCode.INVALID_PANEL_TYPE),
        (lambda: pd.DataFrame({"close": [1.0]}), FailureCode.INVALID_INDEX_SCHEMA),
        (
            lambda: make_panel(("AAA",), periods=2).reset_index(drop=True),
            FailureCode.INVALID_INDEX_SCHEMA,
        ),
        (
            lambda: _three_level_panel(),
            FailureCode.INVALID_INDEX_SCHEMA,
        ),
        (
            lambda: _missing_symbol_panel(),
            FailureCode.INVALID_INDEX_SCHEMA,
        ),
        (
            lambda: _duplicate_symbol_level_panel(),
            FailureCode.INVALID_INDEX_SCHEMA,
        ),
        (
            lambda: _non_string_symbol_panel(),
            FailureCode.INVALID_INDEX_SCHEMA,
        ),
    ],
)
def test_normalize_rejects_invalid_shapes(factory, code) -> None:
    with pytest.raises(PanelAdapterError) as exc:
        normalize_panel(factory())
    assert exc.value.code is code


def test_normalize_rejects_duplicate_columns_keys_and_bad_fields() -> None:
    panel = make_panel(("AAA",), periods=2)
    dup_cols = panel.copy()
    dup_cols["close2"] = dup_cols["close"]
    dup_cols.columns = ["open", "high", "low", "close", "volume", "close"]
    with pytest.raises(PanelAdapterError) as exc:
        normalize_panel(dup_cols, required_fields=("close",))
    assert exc.value.code is FailureCode.INVALID_PANEL_TYPE

    dup = pd.concat([panel, panel])
    with pytest.raises(PanelAdapterError) as exc2:
        normalize_panel(dup, required_fields=("close",))
    assert exc2.value.code is FailureCode.DUPLICATE_LOGICAL_KEY

    bad = panel.copy()
    bad["close"] = ["x", "y"]
    with pytest.raises(PanelAdapterError) as exc3:
        normalize_panel(bad, required_fields=("close",))
    assert exc3.value.code is FailureCode.NON_NUMERIC_FIELD

    with pytest.raises(PanelAdapterError) as exc4:
        normalize_panel(panel, required_fields=("missing_col",))
    assert exc4.value.code is FailureCode.MISSING_REQUIRED_FIELD

    collide = panel.copy()
    # Force conversion collision via duplicate timestamps after normalization path:
    # replace datetime level with values that coerce to the same timestamp.
    symbols = collide.index.get_level_values(0)
    collide.index = pd.MultiIndex.from_arrays(
        [symbols, pd.Index(["2024-01-01", "2024-01-01 00:00:00"])],
        names=["symbol", "eob"],
    )
    with pytest.raises(PanelAdapterError) as exc5:
        normalize_panel(collide, required_fields=("close",))
    assert exc5.value.code in {
        FailureCode.TIME_COLLISION,
        FailureCode.DUPLICATE_LOGICAL_KEY,
        FailureCode.TIME_CONVERSION_FAILED,
    }


def _three_level_panel() -> pd.DataFrame:
    idx = pd.MultiIndex.from_product(
        [["AAA"], pd.date_range("2024-01-01", periods=2), ["x"]],
        names=["symbol", "eob", "extra"],
    )
    return pd.DataFrame({"close": [1.0, 2.0]}, index=idx)


def _missing_symbol_panel() -> pd.DataFrame:
    idx = pd.MultiIndex.from_product(
        [["AAA"], pd.date_range("2024-01-01", periods=2)],
        names=["ticker", "eob"],
    )
    return pd.DataFrame({"close": [1.0, 2.0]}, index=idx)


def _duplicate_symbol_level_panel() -> pd.DataFrame:
    idx = pd.MultiIndex.from_arrays(
        [
            pd.Index(["AAA", "BBB"], name="symbol"),
            pd.Index(["AAA", "BBB"], name="symbol"),
        ]
    )
    return pd.DataFrame({"close": [1.0, 2.0]}, index=idx)


def _non_string_symbol_panel() -> pd.DataFrame:
    idx = pd.MultiIndex.from_arrays(
        [
            pd.Index([1, 2], name="symbol"),
            pd.date_range("2024-01-01", periods=2, name="eob"),
        ]
    )
    return pd.DataFrame({"close": [1.0, 2.0]}, index=idx)
