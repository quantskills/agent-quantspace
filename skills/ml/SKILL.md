---
name: ml
description: Rank factors with a walk-forward model, plan purged walk-forward folds, fit train-only PCA regressors, track an index with sparse LASSO weights, and train or apply registered PyCaret models with `uv run qs ml ...`.
---

# ML

Use the `uv run qs ml` commands below; research tasks do not require reading
`skills/ml/` source. Each command prints one JSON envelope on stdout (`ok`,
`data`, `artifacts`, `warnings`, or `error` with a `hint`). Exact options:
`uv run qs ml <command> --help` or `uv run qs schema ml.<command>`. Model
dependencies need `uv sync --extra ml`.

## When to use

- Combine several indicators into one model-ranked cross-sectional factor.
- Lay out expanding walk-forward folds with a label purge before training.
- Predict with PCA components fitted on the training rows only.
- Build sparse index-tracking weights with rolling LASSO.
- Train a classifier or regressor into the model registry and predict with it.

## Workflow

```bash
uv run qs ml folds --panel out/panel.parquet --min-train 250 --retrain-step 100 --purge 20
uv run qs ml factor-rank --panel out/panel.parquet \
  --factors '[{"indicator": "roc", "params": {"period": 5}, "name": "roc5"},
              {"indicator": "rsi", "params": {"period": 14}, "name": "rsi"}]' \
  --output out/factor_rank.parquet
uv run qs ml pca-predict --train out/train.parquet --predict out/predict.parquet \
  --target-col forward_return --model ols --n-pca 5 --output out/predictions.parquet
uv run qs ml lasso-track --panel out/panel.parquet --index-symbol SHSE.000300 \
  --lookback 120 --min-periods 60 --output out/lasso_weights.parquet
uv run qs ml train --train out/train.parquet --target state --model-name lr --namespace demo
uv run qs ml train --train out/train.parquet --target state --model-name lr --namespace demo --write
uv run qs ml predict --data out/predict.parquet --namespace demo --model-id <model_id> \
  --output out/ml_predictions.parquet
```

## Files

- `--panel` is a `(symbol, eob)` OHLCV table from `qs store read`.
- `--train`, `--predict`, and `--data` are feature tables with one row per
  date; `--train` also holds the target column. Build them from
  `qs compute features` joined with `qs compute labels`.
- `factor-rank` writes a wide date by symbol rank table, the `--scores` input
  of `qs strategy top-n`.
- `train --write` stores the model under `data/models/<namespace>/`; without
  `--write` it only reports the plan.

## Rules

- This Skill outputs predictions, ranks, labels, or weights. Return accounting
  belongs to the backtest Skill.
- Split by time, never at random, and purge at least the label horizon between
  the training and prediction dates.
- Fit PCA and any other transform on the training rows of each fold only.

## References

- [references/python-api.md](references/python-api.md): `MLFactorEngine`,
  walk-forward folds, PCA fold transforms, LASSO tracking, and the PyCaret
  engine. Read it when changing this Skill or writing strategy code.

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Before using a command, run it with `--help` to see its options and defaults. `uv run qs schema <skill>.<command>` shows its input and output fields; add `--file-field FIELD` for the structure of an option that takes a JSON file.

| Command | What it does | Side effects |
|---|---|---|
| `uv run qs ml factor-rank` | Train MLFactorEngine on factor features and write cross-sectional ranks. | writes-output |
| `uv run qs ml lasso-track` | Rolling LASSO index-tracking weights. | writes-output |
| `uv run qs ml folds` | Expanding walk-forward folds with label purge. | read-only |
| `uv run qs ml pca-predict` | Fit train-only PCA and a frozen regressor, then predict rows. | writes-output |
| `uv run qs ml train` | Train a PyCaret MLEngine model and save it to the model registry. | writes-store |
| `uv run qs ml predict` | Predict with a registry model. | writes-output |

<!-- END GENERATED: qs commands -->
