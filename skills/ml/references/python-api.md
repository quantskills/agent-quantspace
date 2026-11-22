# ML Python API

Read this when changing the `ml` Skill or writing strategy code. For research tasks use the `uv run qs ml` commands in [../SKILL.md](../SKILL.md).

ML contains reusable model training, prediction, ML factor, and sparse fitting
helpers. It should produce predictions, ranks, labels, or weight matrices; return
accounting belongs in `skills.backtest`.

Install model dependencies with `uv sync --extra ml`.

## Public API

```python
from skills.ml.estimators import MODEL_IDS, make_estimator, make_pipeline
from skills.ml.ml_engine import MLEngine, ModelPredictor
from skills.ml.ml_factor import MLFactorEngine, make_precomputed_factor
from skills.ml.lasso_tracker import lasso_track
from skills.ml.pca_fold import fit_fold_transform, make_regressor
from skills.ml.walk_forward import date_level_mask, expanding_purged_folds
```

## Components

| Module | Purpose |
|--------|---------|
| `skills.ml.estimators` | Model ids with their default arguments, preprocessing pipelines (mean imputation, scaling, optional PCA), CV metric tables |
| `skills.ml.ml_engine` | Classification/regression engine with the model registry, and an inference wrapper |
| `skills.ml.ml_factor` | Compress factor configs into ML-ranked cross-sectional factor pivots |
| `skills.ml.lasso_tracker` | Rolling LASSO sparse index-tracking weight generation |
| `skills.ml.pca_fold` | Train-only PCA fold transforms (no StandardScaler) and frozen regressors |
| `skills.ml.walk_forward` | Expanding walk-forward folds with label purge, plus date row masks for `(symbol, eob)` panels |

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

**Expanding purged walk-forward folds**

```python
from skills.ml.walk_forward import date_level_mask, expanding_purged_folds

dates = panel.index.get_level_values("eob").unique()
folds = expanding_purged_folds(
    dates,
    min_train=250,
    retrain_step=370,
    purge=20,
)
for fold in folds:
    train_mask = date_level_mask(feature_panel.index, fold.train_dates)
    pred_mask = date_level_mask(feature_panel.index, fold.pred_dates)
```

**Train-only PCA fold transform**

```python
from skills.ml.pca_fold import fit_fold_transform, make_regressor

transform = fit_fold_transform(train_X, pred_X, n_pca=50, random_state=42)
model = make_regressor("lasso")  # or "ols" / "rf" / "xgboost"
model.fit(transform.train_X, train_y)
pred = model.predict(transform.pred_X)
```

**Cross-sectional expanding PCA model scores**

```python
from skills.compute.features import make_logdiff_panel_features
from strategies.cross_sectional.ml_rank import (
    expanding_pca_model_scores,
    expanding_pca_multi_model_scores,
)

features = make_logdiff_panel_features(panel)  # reuse across horizons
# Prefer multi-model so each fold's PCA is fit once:
results = expanding_pca_multi_model_scores(
    panel, models=("ols", "lasso", "rf", "xgboost"), horizon=20, features=features
)
# Or a single model:
result = expanding_pca_model_scores(panel, model="rf", horizon=20, features=features)
scores = result.scores
fold_metrics = result.fold_metrics
overall_metrics = result.overall_metrics
```

**Lesson 07 workflow (18 ETF, equal-weight Top 3)**

```bash
uv run python -m strategies.cross_sectional.workflows.run_lesson07_etf18_logdiff_pca_ml
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

**Registry classification model**

```python
from skills.ml.ml_engine import MLEngine

engine = MLEngine(task="classification", model_name="xgboost")  # ids: MODEL_IDS[task]
model, metrics = engine.setup_and_train(
    train_df, target="label", folds=10, model_params={"max_depth": 3}
)
preds = engine.predict(test_df)  # adds prediction_label and prediction_score
model_id = engine.save_to_registry("demo", train_data=train_df, target="label")
```

`setup_and_train` follows the PyCaret 3.3 defaults QuantSpace used before: a
shuffled 70/30 split seeded by `session_id` (stratified for classification),
unshuffled k-fold CV on the 70% part (`StratifiedKFold` or `KFold`), then a fit on
every row. `metrics` has rows `0..k-1`, `Mean`, `Std` and the columns Accuracy,
AUC, Recall, Prec., F1, Kappa, MCC (classification) or MAE, MSE, RMSE, R2, RMSLE,
MAPE (regression), rounded to four decimals. Two-class targets use binary
averaging with the larger label as the positive class; more classes use weighted
averaging and one-vs-rest AUC. `MLFactorEngine` uses the same pipeline with
`TimeSeriesSplit` CV in each training window.
