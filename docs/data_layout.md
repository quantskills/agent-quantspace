# Data Layout

QuantSpace stores local research data under `data/` by default. Set
`QUANTSPACE_DATA_ROOT` to use another location.

## Market Data

Single-symbol OHLCV files live at:

```text
data/market/{frequency}/{symbol}.parquet
```

Each file is indexed by `eob` and uses columns:

```text
open, high, low, close, volume
```

## Pools

Pools live at:

```text
data/pools/{pool_id}.json
```

The schema is:

```json
{
  "pool_id": "sample_etf_rotation",
  "description": "ETF-style pool for public examples",
  "frequency": "1d",
  "symbols": ["SHSE.510300", "SHSE.510500"]
}
```

`DataManager.load_pool_data(pool_id)` loads a MultiIndex panel indexed by
`(symbol, eob)`.

## Generated Artifacts

The following directories are local outputs and are not meant for source
control:

- `data/factors/`
- `data/factor_test/`
- `data/correlation/`
- `data/backtest/`
- `data/models/`
- `data/export/`
- `reports/`
