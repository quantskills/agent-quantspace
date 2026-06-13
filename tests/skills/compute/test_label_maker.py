from __future__ import annotations

import pandas as pd

from skills.compute.label_maker import ForwardReturnLabelMaker, TripleBarrierLabelMaker


def _bars() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=40, freq="D", name="eob")
    close = pd.Series(range(100, 140), index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000,
        },
        index=index,
    )


def test_forward_return_label_maker_generates_state_and_return() -> None:
    labels = ForwardReturnLabelMaker(data=_bars(), horizon=2, up_threshold=0.001).generate_labels()

    assert {"state", "forward_return", "close", "sign_state_prob"}.issubset(labels.columns)
    assert labels["state"].iloc[0] == 1
    assert labels["forward_return"].iloc[-1] != labels["forward_return"].iloc[-1]


def test_triple_barrier_label_maker_generates_aligned_labels() -> None:
    bars = _bars()
    labels = TripleBarrierLabelMaker(data=bars, L=3, pt_sl=0.5, t_limit=5).generate_labels()

    assert labels.index.equals(bars.index)
    assert set(labels["state"].unique()).issubset({-1, 0, 1})
    assert {"open", "high", "low", "close"}.issubset(labels.columns)
