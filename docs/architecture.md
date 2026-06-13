# Architecture

QuantSpace follows a minimal-core design:

```text
PandaData ingest -> DataManager storage -> strategies -> VectorBacktester -> reports/signals
```

## Core Principles

- Keep data access, computation, analysis, and strategy orchestration separate.
- Put reusable storage, compute, analysis, construction, modeling, and reporting logic in `skills/`.
- Put strategy-specific rules, feature sets, and signal-to-weight logic in `strategies/`.
- Keep scripts as thin orchestration entrypoints.
- Treat generated reports and data as local artifacts, not source code.

## Public Strategy Pipelines

**Cross-sectional**

```text
panel OHLCV -> factor configs/rules/ML ranks -> weights -> VectorBacktester -> metrics
```

**Time-series**

```text
bars -> features/rules/public labels -> weights -> VectorBacktester -> metrics
```
