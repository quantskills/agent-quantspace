---
name: compute
description: Compute technical indicators and factor values on OHLCV panels, build log-difference features and forward-return or triple-barrier labels, resample one-minute bars to five minutes, and forward-adjust stored bars with `uv run qs compute ...`.
---

# Compute

Use the `uv run qs compute` commands below; research tasks do not require
reading `skills/compute/` source. Each command prints one JSON envelope on
stdout (`ok`, `data`, `artifacts`, `warnings`, or `error` with a `hint`).
Exact options: `uv run qs compute <command> --help` or
`uv run qs schema compute.<command>`.

## When to use

- Find an indicator and its default parameters.
- Compute one indicator for every symbol of a panel.
- Build model features or supervised-learning labels for one symbol.
- Resample A-share one-minute bars to five-minute bars.
- Write adjusted bars from raw bars and stored adjustment factors.

## Workflow

```bash
uv run qs compute indicators list
uv run qs compute indicators show roc
uv run qs compute factor --panel out/panel.parquet --indicator roc -p period=10 \
  --output out/roc10_long.parquet
uv run qs compute factor --panel out/panel.parquet --indicator roc -p period=10 \
  --layout wide --output out/mom.parquet
uv run qs compute factor --panel out/panel.parquet --indicator roc -p period=10 \
  --keep-na --output out/roc10_values.parquet
uv run qs compute features --panel out/one_symbol.parquet --lookback 3 --lags 1 \
  --output out/features.parquet
uv run qs compute labels forward-return --bars data/market/1d/510300.SH.parquet \
  --horizon 5 --output out/labels.parquet
uv run qs compute labels triple-barrier --bars data/market/1d/510300.SH.parquet \
  --output out/barrier_labels.parquet
uv run qs compute resample --input out/minute.parquet --output out/5m.parquet
uv run qs compute adjust --symbols 600000.SH --frequency 1d --write
```

## Files

- `--panel` is a `(symbol, eob)` OHLCV table from `qs store read`.
- `factor` writes a long table (`symbol`, `eob`, `value`) by default and a wide
  date by symbol table with `--layout wide`. Warm-up rows are dropped unless
  `--keep-na` is given; `qs analyze evaluate` needs `--keep-na`.
- `--bars` is one symbol's OHLCV file with an `eob` index.
- `adjust` reads `data/market/<frequency>/` and `data/adj_factor/` and, with
  `--write`, writes `data/market/<frequency>_adj/`; without it the command is a
  dry run.

## Rules

- An indicator is a function of one symbol's bars that returns a series on the
  same index. Values at a date must not depend on later rows.
- Strategy-specific factors live in `strategies/<domain>/`, not here. New
  factor functions written during factor mining go to
  `strategies/<domain>/mined_factors/` and need no registration.
- `resample` keeps the A-share sessions `09:31-11:30` and `13:01-15:00` and
  never aggregates across the lunch break.

## References

- [references/python-api.md](references/python-api.md): indicator list by
  category, the `Factor` wrapper contract, feature and label builders, math
  utilities. Read it when changing this Skill or writing strategy code.

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Before using a command, run it with `--help` to see its options and defaults. `uv run qs schema <skill>.<command>` shows its input and output fields; add `--file-field FIELD` for the structure of an option that takes a JSON file.

| Command | What it does | Side effects |
|---|---|---|
| `uv run qs compute indicators list` | List public indicators with signatures. | read-only |
| `uv run qs compute indicators show` | Show one indicator's signature, defaults, and docstring. | read-only |
| `uv run qs compute factor` | Calculate an indicator or module:name factor on a panel. | writes-output |
| `uv run qs compute features` | Build model-ready OHLC log-difference features for a panel. | writes-output |
| `uv run qs compute labels forward-return` | Create forward-return threshold labels for one symbol. | writes-output |
| `uv run qs compute labels triple-barrier` | Create triple-barrier labels for one symbol. | writes-output |
| `uv run qs compute resample` | Resample A-share one-minute bars to five-minute bars. | writes-output |
| `uv run qs compute adjust` | Forward-adjust stored raw bars with adj_factor events. | writes-output, writes-store |

<!-- END GENERATED: qs commands -->
