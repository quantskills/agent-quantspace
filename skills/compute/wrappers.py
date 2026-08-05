"""
Factor wrapper: apply a single-symbol callable across a MultiIndex panel.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd


class Factor:
    """Wrap a single-symbol factor function for MultiIndex ``(symbol, eob)`` panels.

    Contract for ``func``:
    - first argument is a single-symbol ``DataFrame`` with a one-level datetime
      index named ``eob`` and the declared OHLCV columns;
    - returns a real-valued ``Series`` whose index equals the input frame index
      item-for-item and in order.
    """

    def __init__(self, func: Callable, **params):
        self.func = func
        self.params = params
        param_str = ",".join(f"{k}={v}" for k, v in params.items())
        self.name = f"{func.__name__}({param_str})" if param_str else func.__name__

    def calculate(self, data: pd.DataFrame, *, dropna: bool = True) -> pd.Series:
        """Compute factor values for every symbol.

        Parameters
        ----------
        data:
            MultiIndex panel with levels ``symbol`` and ``eob``.
        dropna:
            When True (legacy default), drop NaN rows after computation.
            Phase 02 factor-mining execution always passes ``dropna=False`` to
            preserve warm-up NaNs and full logical alignment.
        """
        self._validate(data)
        symbols = list(dict.fromkeys(data.index.get_level_values("symbol")))
        pieces: list[pd.Series] = []
        for symbol in symbols:
            group = data.xs(symbol, level="symbol", drop_level=True)
            if not isinstance(group.index, pd.DatetimeIndex):
                raise TypeError(
                    "single-symbol frame must use a DatetimeIndex named 'eob'"
                )
            if group.index.name != "eob":
                group = group.copy()
                group.index = group.index.rename("eob")
            if not group.index.is_monotonic_increasing:
                group = group.sort_index()
            raw = self.func(group, **self.params)
            series = self._coerce_output(raw, group.index, symbol=symbol)
            pieces.append(series)
        if not pieces:
            result = pd.Series(dtype="float64")
            result.index = pd.MultiIndex.from_arrays(
                [[], []], names=["symbol", "eob"]
            )
        else:
            result = pd.concat(pieces, keys=symbols, names=["symbol", "eob"])
        if dropna:
            return result.dropna()
        return result

    def cal_df(self, data: pd.DataFrame, *, dropna: bool = True) -> pd.DataFrame:
        """Compute and return a wide ``eob``-index × symbol-columns DataFrame."""
        series = self.calculate(data, dropna=dropna)
        if series.empty:
            return pd.DataFrame()
        wide = series.unstack("symbol")
        return wide.sort_index()

    def _coerce_output(
        self, raw: object, expected_index: pd.Index, *, symbol: object
    ) -> pd.Series:
        del symbol  # reserved for error context without leaking panel values
        if not isinstance(raw, pd.Series):
            raise TypeError(
                "factor function must return a pandas Series, "
                f"got {type(raw).__name__}"
            )
        if raw.index.hasnans:
            raise ValueError("factor output index must not contain NaT/NA")
        if len(raw) != len(expected_index) or not raw.index.equals(expected_index):
            raise ValueError(
                "factor output index must equal the single-symbol input index "
                "item-for-item and in order"
            )
        if pd.api.types.is_bool_dtype(raw.dtype):
            raise TypeError("factor output must not be boolean")
        if pd.api.types.is_complex_dtype(raw.dtype):
            raise TypeError("factor output must not be complex-valued")
        if not pd.api.types.is_numeric_dtype(raw.dtype):
            raise TypeError(
                "factor output must be a real numeric Series "
                f"(dtype={raw.dtype})"
            )
        out = raw.astype("float64", copy=False)
        out.index = expected_index
        return out

    def _validate(self, df: pd.DataFrame) -> None:
        if not isinstance(df.index, pd.MultiIndex):
            raise ValueError("Input DataFrame must have a MultiIndex.")
        names = set(df.index.names)
        if not {"symbol", "eob"}.issubset(names):
            raise ValueError(
                f"MultiIndex must contain 'symbol' and 'eob'. Found: {df.index.names}"
            )

    def __repr__(self) -> str:
        return f"<Factor: {self.name}>"
