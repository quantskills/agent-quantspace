---
name: analyze
description: Measure returns (performance metrics, drawdowns, overfitting tests), screen factors by IC, grouped returns, horizon and lag IC surfaces, and factor correlation, run deterministic factor preflight and evaluation, and test stationarity with `uv run qs analyze ...`.
---

# Analyze

Use the `uv run qs analyze` commands below; research tasks do not require
reading `skills/analyze/` source. Each command prints one JSON envelope on
stdout (`ok`, `data`, `artifacts`, `warnings`, or `error` with a `hint`).
Exact options: `uv run qs analyze <command> --help` or
`uv run qs schema analyze.<command>`. Plotting and parallel analysis need
`uv sync --extra analyze`.

## When to use

- Performance metrics or drawdown episodes of a backtest result or return series.
- Quick factor screening with IC statistics and grouped returns.
- Horizon and lag IC surfaces, or rank correlation and Top-N overlap between factors.
- Contract-checked factor evaluation with an explicit protocol.
- Multiple-testing and overfitting diagnostics across candidate return streams.
- Hurst, ADF, and KPSS stationarity checks.

Strategy execution and portfolio construction belong to the backtest Skill.

## Workflow

```bash
uv run qs analyze perf --returns out/run/result.parquet
uv run qs analyze drawdowns --returns out/run/result.parquet --top-n 5
uv run qs analyze factor-ic --panel out/panel.parquet --factor out/roc10_long.parquet \
  --horizon 5 --groups 5 --out-dir out/ic
uv run qs analyze ic-surface --panel out/panel.parquet \
  --factors mom=out/mom.parquet --factors rsi=out/rsi.parquet \
  --directions '{"mom": 1, "rsi": -1}' --horizons 1,5,20 --lags 0,1,2 \
  --signal-lag 1 --out-dir out/surface
uv run qs analyze factor-correlation --factors mom=out/mom.parquet --factors rsi=out/rsi.parquet \
  --directions '{"mom": 1, "rsi": -1}' --window 60 --min-periods 30 --top-n 3 \
  --out-dir out/correlation
uv run qs analyze evaluate --print-template protocol_json      # also spec_json
uv run qs analyze preflight --panel out/panel.parquet --spec-json spec.json \
  --protocol-json protocol.json
uv run qs analyze evaluate --panel out/panel.parquet --spec-json spec.json \
  --protocol-json protocol.json --values out/roc10_values.parquet --output out/eval.json
uv run qs analyze overfit --candidates out/candidates.parquet --tests dsr,pbo --n-splits 4
uv run qs analyze stationarity --series out/one_symbol.parquet --column close --windows 60,120
```

## Files

- `--factor` and `--values` are long tables with `symbol`, `eob`, and `value`
  (the default `qs compute factor` output); compute `--values` with `--keep-na`.
- `--factors NAME=PATH` takes wide tables, one column per symbol
  (`qs compute factor --layout wide`).
- `--returns` is a dated table with a return column (`--column`, default
  `return`), for example `result.parquet` from `qs backtest run`.
- `--candidates` is an `eob` by candidate table of periodic returns.
- `spec.json` and `protocol.json` are analyze-native `SpecSnapshot` and
  `ProtocolSnapshot` objects; `--print-template` and
  `uv run qs schema analyze.evaluate --file-field protocol_json` show their fields.

## Rules

- `factor-ic` is quick screening; `evaluate` is the execution-aligned Rank-IC
  evaluation. Their numbers are not interchangeable.
- `preflight` and `evaluate` fail fast on hard panel, alignment, or causality
  failures before any return is evaluated.
- Predictive IC and group returns use one label: forward
  `P[t+L+H]/P[t+L]-1` on `protocol.trade_at` prices, with `signal_lag=L` and
  `horizon_bars=H`. `trade_at` and `return_mode` must be set on the protocol;
  they are never inferred.
- With `horizon_bars > 1` the ordinary IC t-test is unavailable because the
  forward windows overlap; read the Newey-West (HAC) statistics instead.
- In `factor-ic`, grouped returns are one-bar returns regrouped every
  `--horizon` bars, so they compound into a valid NAV; IC uses the
  `--horizon`-bar forward return.
- `skills.analyze` does not import `skills.factor_mining`, `strategies`,
  report rendering, or LLM SDKs.

## References

- [references/python-api.md](references/python-api.md): Python entry points,
  `AnalyzeFacade` trust boundaries, pool comparison, and recipes. Read it when
  changing this Skill or writing strategy code.

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Before using a command, run it with `--help` to see its options and defaults. `uv run qs schema <skill>.<command>` shows its input and output fields; add `--file-field FIELD` for the structure of an option that takes a JSON file.

| Command | What it does | Side effects |
|---|---|---|
| `uv run qs analyze factor-ic` | IC statistics and grouped returns with full_stat. | read-only, writes-output |
| `uv run qs analyze ic-surface` | Execution-aligned factor x horizon x lag rank-IC surface with HAC summaries. | read-only, writes-output |
| `uv run qs analyze factor-correlation` | Factor rank-correlation, Top-N overlap and rolling correlation history. | read-only, writes-output |
| `uv run qs analyze perf` | Scalar performance metrics of a return stream. | read-only |
| `uv run qs analyze drawdowns` | List peak-to-trough drawdown episodes. | read-only |
| `uv run qs analyze overfit` | Deflated Sharpe, PBO, Reality Check/SPA, bootstrap and rolling diagnostics. | read-only |
| `uv run qs analyze stationarity` | Hurst, ADF and KPSS over trailing windows. | read-only |
| `uv run qs analyze preflight` | AnalyzeFacade hard checks of panel, spec and protocol. | read-only |
| `uv run qs analyze evaluate` | Deterministic AnalyzeFacade evaluation of precomputed factor values. | read-only, writes-output |

<!-- END GENERATED: qs commands -->
