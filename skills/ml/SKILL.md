---
name: ml
description: Use when tasks need optional PyCaret model training, ML factor generation, inference wrappers, feature importance, or sparse LASSO weight generation.
---

# ML

ML contains reusable model training, prediction, ML factor, and sparse fitting
helpers. It should produce predictions, ranks, labels, or weight matrices; return
accounting belongs in `skills.backtest`.

Install model dependencies with `uv sync --extra ml`.

## Public API

```python
from skills.ml.ml_engine import MLEngine, ModelPredictor
from skills.ml.ml_factor import MLFactorEngine, make_precomputed_factor
from skills.ml.lasso_tracker import lasso_track
from skills.ml.pca_fold import fit_fold_transform, make_regressor
from skills.ml.walk_forward import date_level_mask, expanding_purged_folds
```

## Components

| Module | Purpose |
|--------|---------|
| `skills.ml.ml_engine` | Lazy PyCaret classification/regression engine and inference wrapper |
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

**PyCaret classification**

```python
from skills.ml.ml_engine import MLEngine

engine = MLEngine(task="classification", model_name="xgboost")
model, metrics = engine.setup_and_train(train_df, target="label")
preds = engine.predict(test_df)
```

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Transport: `--input-json FILE|-`, `--preview N`, and `--log-level LEVEL`; flags override JSON. Use `--print-template [FIELD]` for fillable templates.

### Shared parameter groups

#### `PanelSource`

| Option | Type / default | Description |
|---|---|---|
| `--panel` | `path?` / `null` | Parquet/CSV panel, mutually exclusive with symbols or symbols-file. |
| `--symbols` | `list[string]` / `factory` | QuantSpace symbols such as SHSE.510300; repeat flag or comma-separate. |
| `--symbols-file` | `path?` / `null` | Text lines or JSON list of QuantSpace symbols. |
| `--frequency` | `string` / `1d` | Market store directory under data/market, for example 1d or 1d_adj. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |
| `--start` | `string?` / `null` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string?` / `null` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |
| `--fields` | `list[string]` / `factory` | Optional panel field subset. |

#### `OutputOptions`

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path?` / `null` | Explicit output path outside managed store namespaces. |
| `--overwrite` | `boolean` / `false` | Allow replacing an existing output artifact. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |

### `uv run qs ml factor-rank`

Train MLFactorEngine on factor features and write cross-sectional ranks.

Priority: P1. Side effects: writes-output.

Shared parameters: `PanelSource`, `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination rank table (date by symbol, values in [0, 1]). |
| `--factors` | `list[MLFactorItem]` / `required` | Feature factors, each called per symbol. |
| `--model` | `string` / `xgboost` | PyCaret regression model id, e.g. xgboost or rf. |
| `--target-forward` | `integer` / `1` | Forward return horizon of the label. |
| `--train-mode` | `fixed\|rolling` / `rolling` | fixed: one split; rolling: expanding retraining. |
| `--train-ratio` | `number` / `0.7` | fixed mode training fraction. |
| `--train-window` | `integer` / `120` | rolling mode initial training days. |
| `--retrain-freq` | `integer` / `20` | rolling mode retraining interval in days. |
| `--n-folds` | `integer` / `5` | PyCaret cross-validation folds. |
| `--pycaret-kwargs` | `object` / `factory` | Extra keyword arguments for PyCaret setup(). |
| `--importance-output` | `path?` / `null` | Optional feature importance table. |

Output data fields: `rows`, `columns`, `oos_start_date`, `evaluation`.

Inspect schemas: `uv run qs schema ml.factor-rank` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ml lasso-track`

Rolling LASSO index-tracking weights.

Priority: P1. Side effects: writes-output.

Shared parameters: `PanelSource`, `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination tracking weights (date by symbol). |
| `--returns` | `path?` / `null` | Candidate daily returns (date by symbol); otherwise close-to-close returns of the panel source. |
| `--index-symbol` | `string?` / `null` | Target index symbol read from the same store and frequency. |
| `--index-returns` | `path?` / `null` | Dated table holding the target index returns. |
| `--index-column` | `string` / `return` | Return column of index_returns. |
| `--lookback` | `integer` / `120` | Training window in trading days. |
| `--alpha` | `number` / `1e-06` | LASSO strength; larger is sparser. |
| `--min-periods` | `integer` / `60` | Minimum samples before weights. |
| `--rebalance-freq` | `D\|W\|M` / `M` | Refit frequency. |
| `--max-weight` | `number` / `0.3` | Cap per candidate. |

Output data fields: `rows`, `columns`, `start`, `end`, `preview`.

Inspect schemas: `uv run qs schema ml.lasso-track` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ml folds`

Expanding walk-forward folds with label purge.

Priority: P1. Side effects: read-only.

Shared parameters: `PanelSource`.

| Option | Type / default | Description |
|---|---|---|
| `--table` | `path?` / `null` | Dated table whose eob dates define the calendar; otherwise the panel source. |
| `--min-train` | `integer` / `250` | Dates before the first retrain. |
| `--retrain-step` | `integer` / `126` | Dates predicted per fold. |
| `--purge` | `integer` / `20` | Training dates removed before each fold. |

Output data fields: `dates`, `folds`.

Inspect schemas: `uv run qs schema ml.folds` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ml pca-predict`

Fit train-only PCA and a frozen regressor, then predict rows.

Priority: P1. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination predictions table with a prediction column. |
| `--train` | `path` / `required` | Training table with feature columns and the target. |
| `--predict` | `path` / `required` | Table of rows to predict, holding the same features. |
| `--target-col` | `string` / `required` | Target column of the training table. |
| `--feature-cols` | `list[string]` / `factory` | Ordered feature columns; defaults to every training column except the target. |
| `--model` | `ols\|lasso\|rf\|xgboost` / `required` | make_regressor model with its frozen defaults. |
| `--n-pca` | `integer` / `50` | Maximum PCA components fit on train only. |
| `--random-state` | `integer` / `42` | PCA and model random seed. |
| `--rf-n-jobs` | `integer?` / `null` | Random forest workers; defaults to all cores. |

Output data fields: `rows`, `features`, `components`, `pca_explained_variance_sum`.

Inspect schemas: `uv run qs schema ml.pca-predict` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ml train`

Train a PyCaret MLEngine model and save it to the model registry.

Priority: P2. Side effects: writes-store.

| Option | Type / default | Description |
|---|---|---|
| `--train` | `path` / `required` | Training table with feature columns and the target. |
| `--target` | `string` / `label` | Target column. |
| `--task` | `classification\|regression` / `classification` | MLEngine task. |
| `--model-name` | `string` / `xgboost` | PyCaret model id, e.g. xgboost or lr. |
| `--normalize` | `string` / `zscore` | PyCaret normalize method. |
| `--pca-components` | `integer?` / `null` | PyCaret PCA components; omitted disables PCA. |
| `--session-id` | `integer` / `369` | PyCaret random seed. |
| `--n-jobs` | `integer` / `1` | PyCaret parallel jobs. |
| `--create-kwargs` | `object` / `factory` | Extra create_model arguments; omitted uses MLEngine's deterministic defaults. |
| `--namespace` | `string` / `required` | Registry namespace under data/models. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |
| `--write` | `boolean` / `false` | Train and save to the registry; otherwise return a plan. |

Output data fields: `dry_run`, `namespace`, `registry_dir`, `model_id`, `rows`, `features`, `cv_metrics_mean`.

Inspect schemas: `uv run qs schema ml.train` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ml predict`

Predict with a registry model.

Priority: P2. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination predictions table. |
| `--data` | `path` / `required` | Table of feature rows to predict. |
| `--namespace` | `string` / `required` | Registry namespace under data/models. |
| `--model-id` | `string` / `required` | Model id from `qs store list --kind models --namespace <namespace>`. |

Output data fields: `rows`, `task`, `columns`.

Inspect schemas: `uv run qs schema ml.predict` (add `--part input|output` or `--file-field FIELD`).

<!-- END GENERATED: qs commands -->
