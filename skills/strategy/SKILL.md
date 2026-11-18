---
name: strategy
description: Turn scores or signals into date-by-symbol target weights (Top-N selection, single-asset signal weights, holding calendars), combine factors by rank, vote, IC, or ICIR, and run a factor-voting cross-sectional backtest with `uv run qs strategy ...`.
---

# Strategy

Use the `uv run qs strategy` commands below; research tasks do not require
reading `skills/strategy/` source. Each command prints one JSON envelope on
stdout (`ok`, `data`, `artifacts`, `warnings`, or `error` with a `hint`).
Exact options: `uv run qs strategy <command> --help` or
`uv run qs schema strategy.<command>`.

## When to use

- Select the Top-N symbols of a score table as equal target weights.
- Convert one instrument's signal into a weight column.
- Hold signal-day weights across the full trading calendar.
- Combine several factors into one score and Top-N weights.
- Run a quick factor-voting cross-sectional strategy end to end.

## Workflow

```bash
uv run qs compute factor --panel out/panel.parquet --indicator roc -p period=10 \
  --layout wide --output out/mom.parquet
uv run qs strategy top-n --scores out/mom.parquet --top-n 3 --output out/targets.parquet
uv run qs strategy hold-calendar --panel out/panel.parquet --weights out/targets.parquet \
  --output out/held.parquet
uv run qs strategy signal-weights --signal out/signal.parquet --column value \
  --symbol SHSE.510300 --output out/signal_weights.parquet
uv run qs strategy combine --factors mom=out/mom.parquet --factors rsi=out/rsi.parquet \
  --directions '{"mom": 1, "rsi": -1}' --method equal_rank --top-n 3 --out-dir out/combined
uv run qs strategy cs-run --panel out/panel.parquet \
  --factors '[{"indicator": "roc", "params": {"period": 10}, "name": "mom"},
              {"indicator": "rsi", "params": {"period": 14}, "name": "rsi", "direction": -1}]' \
  --slippage-bp 1 --top-pct 0.4 --rebalance-freq W --out-dir out/cs_run
uv run qs backtest run --panel out/panel.parquet --weights out/targets.parquet \
  --commission 0.0002 --slippage-bp 2 --out-dir out/run
```

## Files

- `--scores` and `--factors NAME=PATH` are wide date by symbol tables
  (`qs compute factor --layout wide`, or the rank table of `qs ml factor-rank`).
- `--signal` is one instrument's long factor table; `--column` names the value.
- Outputs are date by symbol target weights, the `--weights` input of
  `qs backtest run`. `combine --out-dir` also writes the factor-level weights.

## Rules

- `combine` applies factor direction and daily cross-sectional normalization
  itself; do not pre-normalize inputs.
- `combine` methods are equal rank, equal vote, rolling IC, rolling ICIR, and
  correlation-aware maximum IC or ICIR. The rolling methods need IC history
  (and the maximum methods a correlation history) from `qs analyze ic-surface`
  and `qs analyze factor-correlation`; `equal_rank` needs none.
- Factor weights (each factor's voice in the composite score) and target
  weights (the asset allocation after Top-N selection) are different tables.
- Published results pass target weights to `qs backtest run`; this Skill keeps
  no second return engine. Concrete factors, rules, and workflows belong in
  `strategies/`.

## References

- [references/python-api.md](references/python-api.md): strategy contracts,
  cross-sectional selection types, `combine_factor_scores`, and the
  time-series helper. Read it when changing this Skill or writing strategy code.

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Before using a command, run it with `--help` to see its options and defaults. `uv run qs schema <skill>.<command>` shows its input and output fields; add `--file-field FIELD` for the structure of an option that takes a JSON file.

| Command | What it does | Side effects |
|---|---|---|
| `uv run qs strategy top-n` | Equal-weight the top N scores on each date. | writes-output |
| `uv run qs strategy signal-weights` | Turn a single-asset signal into target weights. | writes-output |
| `uv run qs strategy hold-calendar` | Forward-hold signal-day weights across a panel's trading calendar. | writes-output |
| `uv run qs strategy combine` | Combine raw factors into composite scores and Top-N weights. | writes-output |
| `uv run qs strategy cs-run` | Run a factor-voting Top-pct cross-sectional strategy with ModularBacktester. | writes-output |

<!-- END GENERATED: qs commands -->
