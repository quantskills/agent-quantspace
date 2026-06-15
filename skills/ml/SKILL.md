---
name: ml
description: Use when tasks need optional PyCaret model training, ML factor generation, inference wrappers, feature importance, or sparse LASSO weight generation.
---

# ML

ML contains reusable model training, prediction, ML factor, and sparse fitting
helpers. It should produce predictions, ranks, labels, or weight matrices; return
accounting belongs in `skills.backtest`.

## Public API

```python
from skills.ml.ml_engine import MLEngine, ModelPredictor
from skills.ml.ml_factor import MLFactorEngine, make_precomputed_factor
from skills.ml.lasso_tracker import lasso_track
```

## Components

| Module | Purpose |
|--------|---------|
| `skills.ml.ml_engine` | Lazy PyCaret classification/regression engine and inference wrapper |
| `skills.ml.ml_factor` | Compress factor configs into ML-ranked cross-sectional factor pivots |
| `skills.ml.lasso_tracker` | Rolling LASSO sparse index-tracking weight generation |

## Recipes

**ML rank factor for `ModularBacktester`**

```python
from skills.compute import indicators as I
from skills.ml.ml_factor import MLFactorEngine, make_precomputed_factor

engine = MLFactorEngine(
    data=panel_df,
    factor_configs=[
        {"func": I.trend_score_v2, "kwargs": {"period": 24}, "name": "trend"},
        {"func": I.cci, "kwargs": {"period": 48}, "name": "cci"},
    ],
    model_type="xgboost",
    train_mode="rolling",
)
rank_pivot = engine.generate()
ml_factor_fn = make_precomputed_factor(rank_pivot, name="ml_rank")
```

**Sparse index-tracking weights**

```python
from skills.ml.lasso_tracker import lasso_track

weights = lasso_track(
    etf_returns,
    index_returns,
    lookback=120,
    alpha=1e-5,
    rebalance_freq="M",
)
```

**PyCaret classification**

```python
from skills.ml.ml_engine import MLEngine

engine = MLEngine(task="classification", model_name="xgboost")
model, metrics = engine.setup_and_train(train_df, target="label")
preds = engine.predict(test_df)
```
