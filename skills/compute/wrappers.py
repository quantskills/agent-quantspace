"""
因子包装器 (Factor Wrapper)

将因子计算函数包装为 Factor 对象，自动处理 GroupBy 逻辑。
"""

from collections.abc import Callable

import pandas as pd


class Factor:
    """
    因子类：将单标的因子函数包装为可处理 MultiIndex 数据的对象。

    用法:
        f = Factor(trend_score_v2, period=24)
        scores = f.calculate(data)  # data: MultiIndex (symbol, eob)
    """

    def __init__(self, func: Callable, **params):
        self.func = func
        self.params = params
        param_str = ",".join(f"{k}={v}" for k, v in params.items())
        self.name = f"{func.__name__}({param_str})" if param_str else func.__name__

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算因子值，返回 MultiIndex Series (symbol, eob)"""
        self._validate(data)
        result = data.groupby(level="symbol", group_keys=False).apply(
            lambda group: self.func(group, **self.params)
        )
        return result.dropna()

    def cal_df(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算并返回 DataFrame (eob, symbol) 格式"""
        return self.calculate(data).reorder_levels(["eob", "symbol"]).sort_index().to_frame()

    def _validate(self, df: pd.DataFrame) -> None:
        if not isinstance(df.index, pd.MultiIndex):
            raise ValueError("Input DataFrame must have a MultiIndex.")
        names = set(df.index.names)
        if not {"symbol", "eob"}.issubset(names):
            raise ValueError(f"MultiIndex must contain 'symbol' and 'eob'. Found: {df.index.names}")

    def __repr__(self):
        return f"<Factor: {self.name}>"
