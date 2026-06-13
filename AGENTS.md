# AGENTS.md - QuantSpace

QuantSpace is a PandaData-first quantitative research workbench.
It combines a small core, reusable skills, and example strategy domains.

## Agent Protocol

1. Read this file before working in the repository.
2. For quant research tasks, check `skills/` before writing new code.
3. Each `skills/<name>/SKILL.md` documents one reusable capability.
4. Keep changes small and reviewable.
5. Use `uv run` for Python commands.
6. New quant code must reuse existing `skills/` and `strategies/` modules first.
7. Put reusable storage, compute, analysis, construction, modeling, and reporting code in `skills/`.
8. Put strategy-specific rules, features, labels-to-weights, and domain workflows in `strategies/`.
9. Keep `scripts/` as thin orchestration only; do not duplicate reusable research logic there.
10. When adding reusable modules, update the relevant `SKILL.md`, README/docs, and tests in the same change.
11. Refactors do not need compatibility wrappers, old imports, or fallback behavior unless the user explicitly asks for them.
12. Put tests under the matching source boundary: `tests/skills/<skill>/`, `tests/strategies/<domain>/`, `tests/scripts/`, `tests/integration/`, `tests/contracts/`, `tests/regression/`, `tests/docs/`, or `tests/policy/`.
13. Do not add root-level `tests/test_*.py`; layout policy tests enforce this.

## Directory Layout

| Path | Purpose |
|------|---------|
| `skills/` | Reusable capabilities: ingest, store, compute, analyze, construct, model, research, report |
| `strategies/` | Public example strategy domains |
| `scripts/` | Thin demo, report, and import entrypoints |
| `data/` | Local data root; only sample pools are committed |
| `reports/` | Local generated research outputs; report artifacts are not committed |
| `tests/` | Public pytest suite |
| `docs/` | Architecture, data layout, examples, and extension notes |

## Skill Registry

| Skill | Import | Purpose |
|-------|--------|---------|
| ingest | `from skills.ingest import PandaDataClient` | PandaData/PandaAI data access and symbol conversion |
| store | `from skills.store.data_manager import DataManager` | Parquet data and research artifact storage |
| compute | `from skills.compute.indicators import trend_score` | Indicators, features, labels, utilities |
| analyze | `from skills.analyze.backtest import VectorBacktester` | Vectorized backtests, IC, grouped returns, metrics, tearsheets |
| construct | `from skills.construct.weighting import WEIGHT_METHODS` | Portfolio weighting and filters |
| model | `from skills.model.ml_engine import MLEngine` | Optional ML model training and registry helpers |
| research | `from skills.research import screen_all_indicators` | Screening, parameter sweeps, strategy comparison |
| report | `from skills.report import ReportRenderer` | HTML/Markdown report rendering and chart helpers |

## Strategy Domains

| Domain | Import | Purpose |
|--------|--------|---------|
| cross_sectional | `from strategies.cross_sectional.modular_backtester import ModularBacktester` | Cross-sectional factors, rules, rank ML, and weight generation |
| time_series | `from strategies.time_series.ml import xgboost_triple_barrier_weights` | Single-instrument rules, features, triple-barrier ML, and weight generation |

## Data Conventions

- Symbol format: exchange prefix plus code, such as `SHSE.510300`.
- Time column/index: `eob`, timezone-naive.
- OHLCV columns: `open`, `high`, `low`, `close`, `volume`.
- Panel format: MultiIndex `(symbol, eob)`.
- Strategy weights: date × symbol `DataFrame`, passed directly to `VectorBacktester`.

## Strategy Examples

- `scripts/run_strategy_reports.py` reads existing PandaData daily Parquet files from `data/market/1d/`.
- Reports are written to `reports/strategy_examples/` as Markdown plus PNG performance charts.
- The four public examples are: time-series rule, time-series XGBoost triple-barrier ML, cross-sectional rule, and cross-sectional XGBoost rank ML.
- Strategy report scripts should call `DataManager.read_symbols`, strategy modules, `VectorBacktester`, and `skills.report.strategy_markdown`; do not add private helper implementations to scripts.

## Python Environment

- Package manager: `uv`.
- Run tests: `uv run python -m pytest tests/`.
- Optional PandaData SDK: `uv sync --extra panda_data`.

## Open Source Boundary

This repository does not include private strategy research, generated reports,
private data, or vendor-specific execution adapters outside PandaData.
