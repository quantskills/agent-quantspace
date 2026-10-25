from __future__ import annotations

import pandas as pd
import pytest

from skills.ml.ml_factor import MLFactorEngine, make_precomputed_factor


def test_make_precomputed_factor_reads_pivot_value_for_group_dates() -> None:
    dates = pd.date_range("2024-01-01", periods=2, name="eob")
    pivot = pd.DataFrame({"AAA": [0.2, 0.8]}, index=dates)
    factor = make_precomputed_factor(pivot, name="ml_rank")
    group = pd.DataFrame(
        {"close": [10.0, 11.0]},
        index=pd.MultiIndex.from_product([["AAA"], dates], names=["symbol", "eob"]),
    )

    result = factor(group)

    assert result.tolist() == [0.2, 0.8]
    assert factor.__name__ == "ml_rank"


def test_eval_summary_averages_pycaret_metrics_past_the_text_model_column() -> None:
    engine = MLFactorEngine.__new__(MLFactorEngine)
    engine.eval_df = pd.DataFrame({"ic": [0.1, 0.3], "period_type": ["out_of_sample"] * 2})
    engine.cv_metrics_list = [
        pd.DataFrame({"MAE": [0.1, 0.3], "R2": [0.2, 0.4]}, index=["Mean", "Std"]),
        pd.DataFrame({"MAE": [0.3, 0.1], "R2": [0.4, 0.2]}, index=["Mean", "Std"]),
    ]
    # PyCaret's predict_model metrics carry the estimator name as text.
    engine.holdout_metrics_list = [
        pd.DataFrame({"Model": ["Extreme Gradient Boosting"], "MAE": [0.1]}),
        pd.DataFrame({"Model": ["Extreme Gradient Boosting"], "MAE": [0.3]}),
    ]

    summary = engine.get_eval_summary()

    assert summary["holdout_metrics_mean"] == pytest.approx({"MAE": 0.2})
    assert summary["cv_metrics_mean"] == pytest.approx({"MAE": 0.2, "R2": 0.3})
    assert summary["out_of_sample"]["ic_mean"] == pytest.approx(0.2)
