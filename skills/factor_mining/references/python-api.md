# Factor Mining Python API

Read this file only when changing `skills/factor_mining/` or writing strategy code that
imports it. Agent tasks should use the `uv run qs factor-mining ...` commands described
in [SKILL.md](../SKILL.md).

## Dependency direction

```text
factor_mining -> compute / analyze / store
analyze -> backtest
skills/* must never import strategies/*
```

Adapters that implement ports live on the `factor_mining` side and call outward.
`compute`, `analyze`, and `store` must not depend on a research workflow or
Agent runtime.

## Public Python API

```python
from skills.factor_mining import (
    ResearchBrief,
    FactorSpec,
    FactorComputeRequest,
    FactorExecutionResult,
    FactorExecutionAdapter,
    DataManagerArtifactStore,
    EvaluationRequest,
    EvaluationReport,
    ReviewReport,
    PoolDecision,
    ResearchDecision,
    FreezeManifest,
    FactorExecutionPort,
    AnalyzePort,
    ArtifactStorePort,
)
```

## Ports

| Port | Caller | Responsibility |
|------|--------|----------------|
| `FactorExecutionPort` | strategy workflow | Execute a compute-compatible `FactorSpec` |
| `AnalyzePort` | strategy workflow | `preflight` / `evaluate` / `compare_to_pool` |
| `ArtifactStorePort` | strategy workflow | Persist research artifacts under caller namespace (`put`, `put_if_absent`, `get`, `get_by_identity`) |

## Adapters

| Adapter | Port | Notes |
|---------|------|-------|
| `FactorExecutionAdapter` | `FactorExecutionPort` | Requires an injected `ArtifactStorePort`. Normalizes two-level panels, resolves any importable Python `function_ref` or structured expression, fingerprints the referenced implementation, runs `Factor(func).calculate(panel, dropna=False)`, applies `lag`, restores index semantics, then persists values/mask and returns real `ArtifactRef`s. Supports `missing_policy=keep_nan`, `output_dtype=float64`, and `index_restore_policy=restore_original_names_and_order` only |
| `DataManagerArtifactStore` | `ArtifactStorePort` | JSON artifacts under `data/factors/<namespace>/artifacts/` with path-traversal guards. Key parts are percent-escaped into file names valid on every platform (`exec-1:values` is stored as `exec-1%3Avalues.json`; legacy raw names stay readable). `put_if_absent` creates a file at most once across processes; the workflow uses it for frozen objects and for the record that the sealed test has started. Optional wide pivots via public `DataManager.factor_filename` / `save_factor` |
| `AnalyzeAdapter` | `AnalyzePort` | Requires injected `ResolveProtocol(protocol_id) -> ProtocolSnapshot` (no guessed defaults). Validates brief/factor/execution identity and protocol↔brief/spec consistency. Calls `AnalyzeFacade`; maps native findings to `FailureCode` via a table-driven map. Skipped cascade findings never mask the root hard failure. |

`skills.compute.wrappers.Factor` never writes artifacts. The execution adapter
does write through the configured store when producing a successful
`FactorExecutionResult`. Successful results carry first-class `brief_ref`,
`data_version`, `split_id`, and immutable `values_content_hash` /
`valid_mask_content_hash` inside the envelope identity. Failed results set
those content hashes to `None`. Compute/store adapters must not statically
depend on a particular `strategies` module or import `skills.analyze`; the
formula resolver dynamically imports the caller-selected `FunctionRef`. The
analyze mapping adapter may import `skills.analyze` only.

`AnalyzeAdapter.preflight` runs before execution and uses
`build_prefix_recompute_capability(factor=spec)` (no execution yet). Evaluate
additionally passes the verified execution for fingerprint exact-match. Pool
members are `TypedPoolMember(execution, values)`.

**Trust boundary.** Production resolvers (`resolve_brief` / `resolve_factor` /
`resolve_execution`) and artifact loaders are trusted ports. `ArtifactRef`
content hashes must be validated by a store-backed loader. In-process
malicious reflection is outside the security boundary; private capability
issuers only prevent public-API misuse.

## Boundary checklist

- No IC, grouped return, turnover, cost, or robustness calculations in this skill.
- No static/leakage/data-quality checker implementations in this skill.
- No vendor Agent SDK, product whitelist, or platform command adapter.
- No second experiment directory and no static dependency on a specific
  `strategies/` module; `FunctionRef` resolves caller-selected import paths at runtime.
- Role definitions in SKILL.md are authoritative; Python carries `role_id` strings only.
