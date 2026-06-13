from __future__ import annotations

import pandas as pd
import pytest

from skills.store.data_manager import DataManager
from tests.fixtures.market_data import make_ohlcv, write_symbol_parquet


def test_read_symbols_returns_standard_symbol_eob_panel(tmp_path) -> None:
    write_symbol_parquet(tmp_path, "AAA", make_ohlcv([1.0, 2.0]))
    write_symbol_parquet(tmp_path, "BBB", make_ohlcv([3.0, 4.0]))

    panel = DataManager(data_root=str(tmp_path)).read_symbols(["AAA", "BBB"])

    assert panel.index.names == ["symbol", "eob"]
    assert panel.index.is_monotonic_increasing
    assert panel.index.get_level_values("eob").dtype == "datetime64[ns]"
    assert {"open", "high", "low", "close", "volume"}.issubset(panel.columns)


def test_read_symbols_reports_all_missing_symbols(tmp_path) -> None:
    write_symbol_parquet(tmp_path, "AAA", make_ohlcv([1.0, 2.0]))

    with pytest.raises(FileNotFoundError, match="BBB.*CCC"):
        DataManager(data_root=str(tmp_path)).read_symbols(["AAA", "BBB", "CCC"])


def test_strategy_weight_contract_is_date_by_symbol_dataframe() -> None:
    weights = pd.DataFrame(
        {"AAA": [1.0, 0.0], "BBB": [0.0, 1.0]},
        index=pd.date_range("2024-01-01", periods=2, name="eob"),
    )

    assert isinstance(weights.index, pd.DatetimeIndex)
    assert weights.index.name == "eob"
    assert weights.columns.tolist() == ["AAA", "BBB"]
    assert weights.dtypes.eq(float).all()
