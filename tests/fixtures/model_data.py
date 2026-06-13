from __future__ import annotations

import numpy as np
import pandas as pd


def make_classification_frame(rows: int = 24) -> pd.DataFrame:
    x = np.linspace(-1.0, 1.0, rows)
    return pd.DataFrame(
        {
            "feature_a": x,
            "feature_b": x**2,
            "label": (x > 0).astype(int),
        }
    )


def make_return_series(rows: int = 30) -> pd.Series:
    index = pd.date_range("2024-01-01", periods=rows, name="eob")
    return pd.Series(np.sin(np.arange(rows) / 5.0) / 100.0, index=index, name="return")
