# Time-Series Strategy Domain

[中文说明](README-zh.md)

This domain demonstrates a public single-instrument ML workflow.

```text
raw OHLCV bars -> features/rules/triple-barrier labels -> weights -> VectorBacktester
```

## Main Modules

- `features.py`: public price/volume feature helpers.
- `rules.py`: rule-based single-instrument weight helpers.
- `ml.py`: triple-barrier XGBoost signal-to-weight helpers.
- `signal_engine.py`: streaming signal generation from raw OHLCV bars and a
  trained classifier.
- `types.py`: default costs, delay, and position mapping.
- `STRATEGY.md`: domain guide and end-to-end example.

Execution and return accounting live in `skills.analyze.backtest.VectorBacktester`.

## Labeling

The public workflow uses `TripleBarrierLabelMaker` from `skills.compute`.
Private label experiments are outside the open-source boundary.

## Demo

```bash
uv run python scripts/run_time_series_demo.py
```
