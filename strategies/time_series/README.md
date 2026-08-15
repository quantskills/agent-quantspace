# Time-Series Strategy Domain

[中文说明](README-zh.md)

This domain demonstrates a public single-instrument ML workflow.

```text
raw OHLCV bars -> features/rules/triple-barrier labels -> weights -> VectorBacktester
```

## Main Modules

- `features.py`: public price/volume feature helpers.
- `rules.py`: rule-based single-instrument weight helpers, including MA/ATR reversion and MA golden/death-cross.
- `cashflow_total_return_mean_reversion.py`: bounded core-satellite mean-reversion rules.
- `ml.py`: triple-barrier XGBoost signal-to-weight helpers.
- `workflows/run_demo.py`: module-based public demo without path injection.
- `STRATEGY.md`: domain guide and end-to-end example.

Reusable signal-to-weight types live in `skills.strategy.time_series`.
Execution and return accounting live in `skills.backtest.VectorBacktester`.

## Labeling

The public workflow uses `TripleBarrierLabelMaker` from `skills.compute`.
Private label experiments are outside the open-source boundary.

## Demo

```bash
uv run python -m strategies.time_series.workflows.run_demo
uv run python -m strategies.time_series.workflows.run_ma_cross_report
uv run python -m strategies.time_series.workflows.run_cashflow_total_return_mean_reversion_is
uv run python -m strategies.time_series.workflows.run_cashflow_split_2014_2023
```
