# Data

[中文说明](README-zh.md)

This directory is the default local data root for QuantSpace.

Only small source-controlled metadata should live here. Market data, computed
factors, model files, backtest outputs, and exports are local artifacts and are
ignored by Git.

## Committed Files

- `pools/*.json`: small sample pool definitions used by demos and tests.
- `README.md` and `README-zh.md`: data layout notes.

## Local Output Layout

```text
data/
  market/{frequency}/{symbol}.parquet
  adj_factor/{symbol}.parquet
  pools/{pool_id}.json
  factors/{pool_id}/
  factor_test/{pool_id}/
  correlation/
  backtest/
  models/
  export/
```

Use `QUANTSPACE_DATA_ROOT` to point `DataManager` at another data location.
