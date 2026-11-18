---
name: backtest
description: Run date-by-symbol target weights through the shared vectorized backtester, convert votes into weights (equal, risk parity, inverse variance), apply market overlays, blend strategy return streams, and price A-share trigger-time costs with `uv run qs backtest ...`.
---

# Backtest

Use the `uv run qs backtest` commands below; research tasks do not require
reading `skills/backtest/` source. Each command prints one JSON envelope on
stdout (`ok`, `data`, `artifacts`, `warnings`, or `error` with a `hint`).
Exact options: `uv run qs backtest <command> --help` or
`uv run qs schema backtest.<command>`.

## When to use

- Turn target weights into executed weights, returns, costs, and metrics.
- Convert selection votes into equal, risk-parity, or inverse-variance weights.
- Scale weights down with index-trend, market-breadth, or volatility overlays.
- Blend the return streams of several strategies.
- Estimate the cost of one A-share trade at a given trigger time.

## Workflow

```bash
uv run qs store read --symbols SHSE.510300,SZSE.159915,SHSE.518880 --frequency 1d_adj \
  --output out/panel.parquet
uv run qs backtest weigh --votes out/targets.parquet --panel out/panel.parquet \
  --method risk_parity --lookback 60 --min-periods 20 --output out/weights.parquet
uv run qs backtest overlay --weights out/weights.parquet --panel out/panel.parquet \
  --index-close out/index_close.parquet \
  --index-trend '{"scale_downtrend": 0.5, "ma_period": 60}' --output out/overlaid.parquet
uv run qs backtest run --panel out/panel.parquet --weights out/overlaid.parquet \
  --commission 0.0002 --slippage-bp 2 --out-dir out/run
uv run qs backtest combine --returns out/candidates.parquet --method equal \
  --output out/blend.parquet
uv run qs backtest cost --time "2026-03-02 14:50" --sell-price 4.12 --buyback-price 4.05
```

## Files

- `--weights` and `--votes` are date by symbol tables (`eob` index or column,
  one column per symbol).
- `--panel` is a `(symbol, eob)` OHLCV table from `qs store read`; `run` can
  read the store directly with `--symbols` and `--frequency` instead.
- `run --out-dir` holds `result.parquet` (per-bar returns, the input of
  `qs analyze perf`), `executed_weights.parquet`, and `metrics.json`.
- `--returns` for `combine` is an `eob` by strategy table of periodic returns.

## Rules

- `run` requires `--commission` and `--slippage-bp`; there is no default cost.
- A date's executed weight earns the next bar's return (`--signal-lag 1`), the
  safe convention for close-derived signals.
- `--start` and `--end` limit the result dates only; earlier bars still load.
  Trim the panel with `qs store read` to limit history.
- Strategy code produces weights; return accounting stays in this Skill.

## References

- [references/python-api.md](references/python-api.md): `VectorBacktester`,
  weighting, filters, cost model, and exit A/B helpers. Read it when changing
  this Skill or writing strategy code.

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Before using a command, run it with `--help` to see its options and defaults. `uv run qs schema <skill>.<command>` shows its input and output fields; add `--file-field FIELD` for the structure of an option that takes a JSON file.

| Command | What it does | Side effects |
|---|---|---|
| `uv run qs backtest run` | Execute target weights through VectorBacktester with costs and metrics. | writes-output |
| `uv run qs backtest weigh` | Convert a vote matrix into portfolio weights. | writes-output |
| `uv run qs backtest overlay` | Scale weights with market breadth, index trend, or volatility targeting. | writes-output |
| `uv run qs backtest combine` | Blend strategy return streams with StrategyCombiner. | writes-output |
| `uv run qs backtest cost` | Look up the A-share trigger-time cost layer and single T PnL. | read-only |

<!-- END GENERATED: qs commands -->
