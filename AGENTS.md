---
name: agent-quantspace
description: "AI-native quantitative research framework with reusable skills, strategy domains, and thin orchestration scripts. Use when a coding agent needs to build, test, or review quantitative research workflows, strategy examples, backtests, reports, or reusable quant modules inside QuantSpace."
quantSkills:
  organization: QuantSkills
  organization_url: https://github.com/quantskills
  repository: quantskills/agent-quantspace
  repository_url: https://github.com/quantskills/agent-quantspace
  project_type: agent
  collection: quant-research-frameworks
  license: GPL-3.0
  category: workflow-agent
  tags: [quant-research, strategy-research, backtesting, pandadata]
  platforms: [codex, claude-code, cursor, codebuddy, qoder, trae, opencode, openclaw, kimi-code]
  language: zh-en
  status: active
  validation_level: runnable
  maintainer_type: official
  requires: []
  summary_zh: 面向 AI 编码代理的量化研究框架，组织数据、技能、策略、回测和报告工作流。
  summary_en: AI-native quantitative research framework for reusable skills, strategy workflows, backtests, and reports.
---

```json qsh-form
{
  "version": 1,
  "task": {
    "placeholder": "描述要在 QuantSpace 中构建、测试或审查的量化研究工作流、策略、回测、报告或模块",
    "required": true
  },
  "prompt_template": "{{#task}}任务与材料：\n{{task}}\n\n{{/task}}{{#attachments}}用户上传的材料（已放入工作区）：\n{{attachments}}\n\n{{/attachments}}遵循 QuantSpace 的模块边界、数据约定、uv 命令和测试目录规范，优先复用现有 skills 与 strategies，完成所述构建、测试或审查任务并说明验证结果，输出中文报告。"
}
```

# AGENTS.md - QuantSpace

QuantSpace is an AI-native quantitative research framework.
It combines reusable skills, strategy domains, and thin orchestration scripts so
AI agents can turn research ideas into tested strategy code inside the project.

## Agent Protocol

1. Read this file before working in the repository.
2. For quant research tasks, check `skills/` before writing new code.
3. Each `skills/<name>/SKILL.md` documents one reusable capability.
4. Keep changes small and reviewable.
5. Use `uv run` for Python commands.
6. New quant code must reuse existing `skills/` and `strategies/` modules first.
7. Put reusable storage, compute, strategy types, analysis, backtesting, ML, and reporting code in `skills/`.
8. Put strategy-specific rules, features, labels-to-weights, and domain workflows in `strategies/`.
9. Keep `scripts/` as thin orchestration only; small script-local parsing/date/file helpers are acceptable, but reusable research logic belongs in `skills/` or `strategies/`.
10. When adding reusable modules, update the relevant `SKILL.md`, README/docs, and tests in the same change.
11. Refactors do not need compatibility wrappers, old imports, or fallback behavior unless the user explicitly asks for them.
12. Put tests under the matching source boundary: `tests/skills/<skill>/`, `tests/strategies/<domain>/`, `tests/scripts/`, `tests/integration/`, `tests/contracts/`, `tests/regression/`, `tests/docs/`, or `tests/policy/`.
13. Do not add root-level `tests/test_*.py`; layout policy tests enforce this.

## Directory Layout

| Path | Purpose |
|------|---------|
| `skills/` | Reusable capabilities and strategy-neutral target-weight types: ingest, store, compute, strategy, analyze, backtest, ml, research, report, factor_mining |
| `strategies/` | Concrete public factors, features, rules, ML behavior, and runnable workflows |
| `scripts/` | Global data import, report, and maintenance entrypoints; strategy demos live in `strategies/*/workflows/` |
| `data/` | Local data root; market files and research artifacts stay local |
| `reports/` | Local generated research outputs; `strategy_examples/` is the public report exception |
| `tests/` | Public pytest suite |
| `docs/` | Minimal supplemental docs; avoid duplicating README, AGENTS, or SKILL.md |

## Skill Registry

| Skill | Import | Purpose |
|-------|--------|---------|
| ingest | `from skills.ingest import PandaDataClient` | PandaData data access and symbol conversion |
| store | `from skills.store.data_manager import DataManager` | Parquet data and research artifact storage |
| compute | `from skills.compute.indicators import trend_score` | Strategy-neutral OHLCV indicators, labels, utilities, and the `Factor` wrapper |
| strategy | `from skills.strategy import StrategyResult` | Reusable strategy contracts, selection types, and cross-sectional/time-series target-weight helpers |
| analyze | `from skills.analyze.factor_analysis import IC_stat` | Factor diagnostics, attribution, robustness, and time-series checks |
| backtest | `from skills.backtest import VectorBacktester` | Vectorized execution, portfolio weights, filters, costs, and metrics |
| ml | `from skills.ml.ml_engine import MLEngine` | Optional ML model training, inference, ML factors, and sparse fitting |
| research | `from skills.research import screen_all_indicators` | Screening and parameter sweeps |
| report | `from skills.report import ReportRenderer, write_research_bundle` | HTML research reports, public Markdown cards, and chart helpers |
| factor_mining | `from skills.factor_mining import ResearchBrief, FactorSpec, ResearchController` | AI factor-mining contracts, ports, Phase 02/03 adapters, Phase 04 Research Controller, and cross-platform role protocol |

Coding-agent compatibility is declared here and in README/README.en.md
(ChatGPT Codex, Claude Code, Cursor, CodeBuddy, Qoder, TRAE, OpenCode, OpenClaw, Kimi Code).
Runtime collaboration follows `skills/factor_mining/SKILL.md` capability discovery;
names are declarations, not a product whitelist.

## Strategy Domains

| Domain | Import | Purpose |
|--------|--------|---------|
| cross_sectional | `from strategies.cross_sectional.rules import ma_gap_reversal_weights` | Concrete cross-sectional factors, rules, rank ML, and workflows |
| time_series | `from strategies.time_series.ml import xgboost_triple_barrier_weights` | Single-instrument rules, features, triple-barrier ML, and weight generation |

## Data Conventions

- Symbol format: exchange prefix plus code, such as `SHSE.510300`.
- Time column/index: `eob`, timezone-naive.
- OHLCV columns: `open`, `high`, `low`, `close`, `volume`.
- Panel format: MultiIndex `(symbol, eob)`.
- Market files: `data/market/{frequency}/{symbol}.parquet`; adjustment factors: `data/adj_factor/{symbol}.parquet`.
- Strategy weights: date × symbol `DataFrame`, passed directly to `VectorBacktester`.
- Strategy universes are explicit symbol lists owned by the caller; factor, backtest, and model folders use caller-provided artifact namespaces.
- Resolve workspace paths through `skills.store.workspace.resolve_workspace_paths`; use `QUANTSPACE_WORKSPACE_ROOT`, `QUANTSPACE_DATA_ROOT`, or `QUANTSPACE_REPORTS_ROOT` when the defaults need overriding.
- Reusable selection, signal-to-weight, and strategy-type logic belongs in `skills.strategy`; concrete behavior belongs in `strategies`.
- `skills/` must never import `strategies/`.

## Strategy Examples

- `uv run python -m scripts.run_strategy_reports` reads existing PandaData daily Parquet files from `data/market/1d/` and accepts `--data-root` for another local data root.
- Reports are written below the resolved reports root as `strategy_examples/` Markdown plus PNG performance charts.
- The five public examples are: time-series rule, time-series XGBoost triple-barrier ML, cross-sectional futures rule, cross-sectional XGBoost rank ML, and global-asset ETF/LOF Top-3 momentum rotation.
- Strategy report scripts should call `DataManager.read_symbols`, concrete strategy modules, `VectorBacktester`, and `skills.report.strategy_markdown`; do not add reusable research implementations to scripts.

## Python Environment

- Package manager: `uv`.
- Run tests: `uv run python -m pytest tests/`.
- Run lint: `uv run ruff check .`.
- Optional PandaData SDK: `uv sync --extra panda_data`.
- Optional capability profiles: `analyze`, `ml`, `query`, `report`, and `panda_data`.

## Open Source Boundary

This repository does not include private strategy research, non-public generated reports,
private data, or vendor-specific execution adapters outside PandaData. The
sanitized Markdown and PNG files under `reports/strategy_examples/` are the
only generated report artifacts intended for source control.
