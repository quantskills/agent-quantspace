---
name: model
description: Use when tasks need optional PyCaret model training, ML factor generation, inference wrappers, feature importance, or LASSO index tracking.
---

## Description

Use **`MLFactorEngine`** to compress many base factors into a single ML-ranked signal for cross-sectional backtests (`make_precomputed_factor`), or **`lasso_track` / `backtest_lasso_tracker`** to replicate an index with a sparse ETF basket via rolling LASSO.

## Prerequisites

- **Python**: `pandas`, `numpy`, `scipy`; **PyCaret** and a supported regression backend (e.g. XGBoost) for `MLFactorEngine`.
- **Data**: MultiIndex OHLCV `(symbol, eob)` with at least `close` for features and labels.
- **LASSO**: `sklearn.linear_model.Lasso`.

## API Reference

### Bridge to backtester (`skills.model.ml_factor`)

```python
from skills.model.ml_factor import make_precomputed_factor

def make_precomputed_factor(pivot_df: pd.DataFrame, name: str = "ml_prediction") -> Callable
```

Returns a callable compatible with group-apply backtest wiring: `(group_df, **kwargs) -> pd.Series`, reading from a date × symbol pivot.

### `MLFactorEngine` (`skills.model.ml_factor`)

```python
from skills.model.ml_factor import MLFactorEngine
```

- `__init__(data, factor_configs, model_type="xgboost", target_forward=1, train_mode="rolling", train_ratio=0.7, train_window=120, retrain_freq=20, n_folds=5, pycaret_kwargs=None)`
- `generate() -> pd.DataFrame` — sets `prediction_rank_pivot`, `eval_df`, `feature_importance_df`, CV/holdout metrics, `oos_start_date`, etc.
- `get_feature_importance() -> pd.DataFrame`
- `get_eval_summary() -> Dict` — IC in/out of sample and PyCaret metrics when available.

`factor_configs`: list of `{'func', 'kwargs', 'name'}` matching the cross-sectional engine.  
`train_mode`: `'fixed'` or `'rolling'`.

### LASSO index tracking (`skills.model.lasso_tracker`)

```python
from skills.model.lasso_tracker import lasso_track, backtest_lasso_tracker
```

- `lasso_track(etf_returns, index_returns, lookback=120, alpha=1e-6, min_periods=60, rebalance_freq="M", max_weight=0.3) -> pd.DataFrame` — weights, date × symbol.
- `backtest_lasso_tracker(etf_data, index_data, lookback=120, alpha=1e-6, rebalance_freq="M", commission=0.0002, start_date=None) -> Dict` — keys `result_df`, `weights_df`, `metrics` (e.g. `total_return`, `tracking_error`, `information_ratio`, `avg_turnover`).

## Recipes

**1. ML rank factor for `ModularBacktester`**

```python
from skills.model.ml_factor import MLFactorEngine, make_precomputed_factor
from skills.compute import indicators as I

engine = MLFactorEngine(
    data=panel_df,
    factor_configs=[
        {"func": I.trend_score_v2, "kwargs": {"period": 24}, "name": "trend"},
        {"func": I.cci, "kwargs": {"period": 48}, "name": "cci"},
    ],
    model_type="xgboost",
    train_mode="rolling",
    train_window=120,
    retrain_freq=20,
)
rank_pivot = engine.generate()
summary = engine.get_eval_summary()
importance = engine.get_feature_importance()

ml_factor_fn = make_precomputed_factor(rank_pivot, name="ml_rank")
# Add ml_factor_fn to factor_configs like any other factor callable.
```

**2. Index replication**

```python
from skills.model.lasso_tracker import backtest_lasso_tracker

bt_lasso = backtest_lasso_tracker(
    etf_data=etf_panel_multiindex,
    index_data=index_close_series,
    lookback=120,
    alpha=1e-5,
    rebalance_freq="M",
    commission=0.0002,
)
```

Use `lasso_track` when you only need the weight series; use `backtest_lasso_tracker` for turnover-aware performance.

### `MLEngine` (`skills.model.ml_engine`)

```python
from skills.model.ml_engine import MLEngine, ModelPredictor
```

Unified PyCaret interface for both classification and regression tasks (lazy PyCaret import).

- `MLEngine(task='classification'|'regression', model_name='xgboost', normalize='zscore')`
- `setup_and_train(train_data, target, pca_components, ...) -> (model, cv_metrics)`
- `predict(data) -> pd.DataFrame`
- `save(path)` / `load(path)`
- `save_to_registry(pool_id, ...)` — 将模型与元数据写入 `data/models/{pool_id}/`
- `load_from_registry(pool_id, model_id)` — 从注册表加载模型
- `list_models(pool_id)` — 列出已保存模型（`@staticmethod`）
- `batch_train(train_data, pca_range=...)` — 扫描 PCA 维度，返回指标 `DataFrame`

### `ModelPredictor` (`skills.model.ml_engine`)

Inference-only wrapper with PCA alignment (3-segment concatenation trick).

- `ModelPredictor(model_path, train_features, task='classification')`
- `predict(test_features) -> pd.DataFrame` (columns: prediction_label, prediction_score)

**3. Time-series ML classification**

```python
from skills.model.ml_engine import MLEngine

engine = MLEngine(task="classification", model_name="xgboost")
model, metrics = engine.setup_and_train(train_df, target="label", pca_components=10)
preds = engine.predict(test_df)
engine.save("models/xgb_model")
```
