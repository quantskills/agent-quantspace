# Data

[中文说明](README-zh.md)

This directory is the default local data root for QuantSpace.

Market data, computed factors, model files, backtest outputs, and exports are
local artifacts and are ignored by Git.

Instrument universes do not live in the data directory; strategies and callers
pass explicit symbol lists.

## Local Output Layout

```text
data/
  market/{frequency}/{symbol}.parquet
  adj_factor/{symbol}.parquet
  factors/{namespace}/
  factor_test/{namespace}/
  correlation/
  backtest/
  models/
  export/
```

Use `QUANTSPACE_DATA_ROOT` to point `DataManager` at another data location.
