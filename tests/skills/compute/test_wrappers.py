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


def test_factor_rejects_non_multiindex_input() -> None:
    with pytest.raises(ValueError, match="MultiIndex"):
        Factor(_close_return).calculate(pd.DataFrame({"close": [1.0, 2.0]}))
