---
name: factor_mining
description: Use when tasks need AI multi-agent factor mining research boundaries, versioned ResearchBrief/FactorSpec contracts, evaluation/review/decision objects, or cross-platform role task protocols without implementing compute/analyze algorithms here.
---

# Factor Mining

`skills/factor_mining` is the Agent collaboration and research-governance boundary
for market-panel factor mining. It owns versioned research objects, abstract
ports, and this role/task protocol. It does **not** implement factor math, IC /
turnover / cost statistics, static leakage checks, backtests, platform SDKs, or
strategy-domain logic.

Generator roles may create arbitrary Python factor implementations in the
appropriate `strategies/<domain>/mined_factors/` package. A `FactorSpec` points
to the generated callable by importable module/name; factor execution is not
restricted to `skills.compute.indicators`. Generated functions may reuse
`skills.compute`, pandas/numpy, or implement completely new formulas.

## Dependency direction

```text
factor_mining -> compute / analyze / store / report
analyze -> backtest
skills/* must never import strategies/*
```

Adapters that implement ports live on the `factor_mining` side and call outward.
`compute`, `analyze`, `store`, and `report` must not depend on a Controller or
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
    AgentTaskView,
    TaskLease,
    AgentTaskResult,
    ResearchDecision,
    FreezeManifest,
    OOSAuthorization,
    OOSAttempt,
    OOSResult,
    FactorExecutionPort,
    AnalyzePort,
    ArtifactStorePort,
    ReportPort,
    ResearchController,
    CommandRequest,
    ResearchRunStatus,
    CandidateStatus,
)
```

Phase 01 freezes contracts and ports. Phase 02 adds deterministic adapters under
`skills.factor_mining.adapters` that implement `FactorExecutionPort` and
`ArtifactStorePort` against `skills.compute` / `skills.store` without changing
the Phase 01 envelope names. Phase 03 adds `AnalyzeAdapter`, a thin mapper over
`skills.analyze.AnalyzeFacade` that implements `AnalyzePort` and translates
analyze-native findings/metrics into `EvaluationReport` / `MetricFact` /
`RuleCheck` / `EvidenceRef` without changing Phase 01 shapes or `FailureCode`
members. Phase 04 adds `ResearchController` plus pure `state` / `budget` /
`policies` / `isolation` / `snapshots` modules: explicit commands, optimistic
versions, idempotency, atomic budget leases, sealed fail-closed task views,
append-only hash-chained events, and Human Gate-1 → `FreezeManifest`. Phase 06
adds a narrow trusted path: `authorize_oos` → `complete_oos` →
`record_gate2_approval` → `promote` / `reject_run`. The Controller derives the
one-shot key from frozen run/candidate/manifest/sealed-split lineage, writes a
sealed append-only `started` attempt before calling either port, and never
retries that key after a crash or terminal failure. OOS request construction is
an injected trusted factory and must exact-bind the manifest; callers cannot
supply split, threshold, compute, or evaluation settings. OOS results, attempt
ledgers, Gate-2 approvals, and release knowledge are sealed reference closures:
they never become task inputs, generator/reviewer context, or revision inputs.
The manifest freezes the trusted evaluation `protocol_id` independently from
the Analyze engine version and records each threshold's official Analyze fact
and comparison operator (`rank_ic_ir`, `coverage_worst`, or
`group_turnover_mean`). OOS evidence and native artifacts remain separate typed
reference collections.
`ResearchController.build_release_report_request(...)` is the separate trusted
`ReportPort` hand-off: it closes over the Brief, FactorSpec, manifest,
authorization, optional OOSResult/evidence, both approvals, attempt ledger, and
terminal knowledge refs, without serializing panel values into a task or log.

## Schema migration 1.4.0

Version 1.4.0 is a deliberate breaking contract upgrade; there are no legacy
imports, compatibility wrappers, or permissive replay fallbacks. It adds exact
request lineage to `EvaluationReport`, parent/input-hash hand-off bindings to
the task protocol, independently frozen `evaluation_protocol_id` and canonical
`oos_metric_selectors` to `FreezeManifest`, content-addressed `OOSAttempt`, and
separate evidence/artifact collections on `OOSResult`. Persisted pre-1.4.0
objects and event chains must be migrated explicitly outside the Controller or
continued as a new versioned run; runtime replay fails closed on the old shape.

## Ports

| Port | Caller | Responsibility |
|------|--------|----------------|
| `FactorExecutionPort` | Controller | Execute a compute-compatible `FactorSpec` |
| `AnalyzePort` | Controller | `preflight` / `evaluate` / `compare_to_pool` |
| `ArtifactStorePort` | Controller | Persist research artifacts under caller namespace |
| `ReportPort` | Release/report flow | Render reports from formal refs and facts |

### Phase 04 controller

`ResearchController.handle(CommandRequest)` is the only mutation entrypoint.
It orchestrates `AnalyzePort.preflight` → `FactorExecutionPort.execute` →
`AnalyzePort.evaluate` → `AnalyzePort.compare_to_pool` and fail-fast rejects on
hard failures. It does not compute IC/robustness/backtests. State lives in
namespaced snapshot cache + append-only `controller_event` artifacts (hash
chain is authoritative). Concurrent commands CAS on expected next-version
slots via `put_if_absent`; port-bearing commands claim started/idempotency
before external calls and persist `RecoveryRequired` without auto-recompute.
`DataManagerArtifactStore.put_if_absent` / `envelope_hash` provide
cross-process append-only semantics. Sealed capability is judged from trusted
store meta plus namespace/hash checks; Gate-1 requires an injected verifier.
Replay is fail-closed: each command's complete input/output-ref lists must
exact-match its reconstructed state transition. Controller replay additionally
revalidates task-authorized refs and re-derives Gate-1 / `FreezeManifest`
authority from trusted storage, so recomputing an event-chain hash cannot
authorize a fresh ref, lease, approval, or manifest.
Budget reserve/settle/release is atomic per command; duplicate
`(run_id, aggregate_id, idempotency_key)` replays the prior result without
re-calling ports.

### Phase 02 / 03 adapters

| Adapter | Port | Notes |
|---------|------|-------|
| `FactorExecutionAdapter` | `FactorExecutionPort` | Requires an injected `ArtifactStorePort`. Normalizes two-level panels, resolves any importable Python `function_ref` or structured expression, fingerprints the referenced implementation, runs `Factor(..., dropna=False)`, applies `lag`, restores index semantics, then persists values/mask and returns real `ArtifactRef`s |
| `DataManagerArtifactStore` | `ArtifactStorePort` | JSON artifacts under `data/factors/<namespace>/artifacts/` with path-traversal guards; optional wide pivots via public `DataManager.factor_filename` / `save_factor` |
| `AnalyzeAdapter` | `AnalyzePort` | Requires injected `ResolveProtocol(protocol_id) -> ProtocolSnapshot` (no guessed defaults). Validates brief/factor/execution identity and protocol↔brief/spec consistency. Calls `AnalyzeFacade`; maps native findings to Phase 01 checks via a table-driven `FailureCode` map. Evidence hashes are recomputed from Phase01-visible fields; native extras need injected `persist_artifact` or surface as `ADAPTER_MAPPING_LOSS`. Skipped cascade findings never mask the root hard failure. |

`skills.compute.wrappers.Factor` never writes artifacts. The execution adapter does write through the configured store when producing a successful `FactorExecutionResult`. Successful results carry first-class `brief_ref`, `data_version`, `split_id`, and immutable `values_content_hash` / `valid_mask_content_hash` (canonical `series_to_payload` digests) inside the envelope identity. Failed results set those content hashes to `None`. Compute/store adapters must not statically depend on a particular `strategies` module or import `skills.analyze`; the formula resolver dynamically imports the caller-selected `FunctionRef`. The analyze mapping adapter may import `skills.analyze` only. Phase 02 supports `missing_policy=keep_nan`, `output_dtype=float64`, and `index_restore_policy=restore_original_names_and_order` only.

`AnalyzeAdapter.preflight` runs before Phase 02 execution and uses the official
`build_prefix_recompute_capability(factor=spec)` compile path (no execution yet).
Evaluate additionally passes the verified execution for fingerprint exact-match.
Pool members are `TypedPoolMember(execution, values)` — values content must
exact-match `execution.values_content_hash`; `execution.brief_ref` must
exact-equal `request.brief_ref` (all ObjectRef fields); provenance must
exact-include `execution.brief_ref` and `execution.factor_ref` (not type
placeholders). Pool `factor_ref` may differ from the candidate factor.
`compare_to_pool` also rehashes candidate `load_series` values against
`execution.values_content_hash` before calling the facade.

**Trust boundary.** Production resolvers (`resolve_brief` / `resolve_factor` /
`resolve_execution`) and artifact loaders are trusted ports. `ArtifactRef`
content hashes must be validated by a store-backed loader. In-process
malicious reflection is outside the security boundary; private capability
issuers only prevent public-API misuse.

## Contract invariants

- Every versioned object carries `schema_version`, content hash semantics, and
  explicit caller `namespace`.
- `EvaluationReport` stores deterministic `MetricFact` / `RuleCheck` / failure
  only. Agent rationale and accept/reject decisions live in `ReviewReport`,
  `PoolDecision`, and `ResearchDecision`.
- `FactorSpec` formulas are an unrestricted importable Python `function_ref` or
  a structured `expression` plus JSON params. Generated Python source belongs
  in `strategies/` and is referenced by module/name instead of embedded text.
- Role fields are ordinary `role_id` strings. Python must not copy the role
  catalog below as an enum, registry, or platform whitelist.

## Cross-platform capability protocol

Product names in README / AGENTS.md are compatibility declarations and examples,
not a runtime whitelist. This file selects behavior by capability only:

1. **Native sub-agent**: create isolated role contexts, dispatch, wait, collect.
2. **Equivalent isolated tasks**: independent input/output contexts with the same
   structured contracts.
3. **Sequential single-agent fallback**: run roles in order while rebuilding the
   minimal authorized context for each role and keeping generation separate from
   review.

Do not encode vendor tool names, vendor parameters, SDKs, or `if platform`
branches in Python or in this protocol. Default: sub-agents do not recursively
spawn further agents. Sealed OOS data and results never enter generation, review,
or debate contexts. All modes must return the same contracts and record
role_id, parent task, input versions/hashes, output refs, and status.

### Phase 05 host execution protocol

The host main agent is the Supervisor. It reads the role blocks below and first
discovers only these semantic capabilities: isolated-context creation,
parallel dispatch, wait/collect, and cancellation. Select exactly one mode:

1. **Native sub-agent mode** when isolated contexts, parallel dispatch, and
   wait/collect are all available.
2. **Equivalent isolated-task mode** when isolated contexts and collection are
   available but native dispatch semantics are not.
3. **Sequential fallback** otherwise, rebuilding the same minimum authorized
   view before each role step.

This is capability discovery, not an instruction to implement an agent runtime
inside Python. In every mode, preserve the SKILL declaration order for stable
task ids, collection order, audit keys, and summaries; completion timing must
never affect candidate ordering, budget use, or the resulting contracts.

For an active Brief, hand the four `FactorSpec` roles logically independent
Brief projections. The host may execute them concurrently only after the
Controller has issued their leases. Every submitted result must exact-match its
Controller-issued task view: task/run/parent/role ids, expected output type,
input-ref hashes, and a budget consumption no greater than the lease. The
Controller and trusted store remain the authority for state transition,
idempotency, object existence, and content-hash verification.

After deterministic evaluation, the two `ReviewReport` roles receive the same
formal FactorSpec/EvaluationReport snapshot but never each other's draft. The
`PoolDecision` role begins only after both independent reviews return accepted
formal results. A failed, timed-out, cancelled, or duplicate return is reported
through the corresponding Controller command; it never triggers a second lease
or direct state write. A child task must not delegate or recursively spawn.

Do not debate a hard safety, leakage, data-availability, or threshold failure.
For a high-value conflict only, reuse the original involved roles and follow
Claim → Evidence → Objection → Falsification Test → Response → Decision. There
are at most two rounds and at most one revision. A revision is a new candidate
that consumes the Controller lease and completes the full preflight → compute
→ evaluate → independent-review path before synthesis.

## Shared task template envelope

Every spawned task must include:

- goal
- immutable input refs and content hashes
- budget lease
- required checks
- forbidden actions
- exactly one expected output contract / schema version

Every structured return must include envelope ids, status, one structured output
or failure, evidence/artifact refs, budget consumption, and handoff target.
When a Generator creates Python source, the structured output remains the
`FactorSpec`; the generated module/test files are source artifacts referenced by
the spec's `function_ref` and reported in the task's artifact refs.

---

## Roles

This section is the **only** authoritative catalog of the eight logical roles.

### Role: supervisor

```text
role_id: supervisor
purpose: Coordinate research under a fixed Research Brief; allocate budgets; decide continue/revise/stop/freeze without replacing reviewers or inventing metrics.
spawn_when: A valid ResearchBrief is active and research coordination is required. Usually performed by the host main agent; do not spawn a second supervisor by default.
do_not_spawn_when: Sealed OOS is open; no Brief is fixed; a freeze/OOS deterministic path is already running without coordination needs.
task_template: |
  Goal: discover current agent capabilities, allocate remaining budget, and emit a ResearchDecision and/or task list.
  Inputs: ResearchBrief ref+hash; authorized candidate/status refs only.
  Must check: Brief hash validity; budget remaining; whether generation, review, synthesis, debate, or stop is appropriate.
  Forbidden: computing metrics; accepting candidates in place of reviewers; reading sealed OOS; inventing EvaluationReport facts.
  Output: ResearchDecision (and optional task list refs).
required_inputs: ResearchBrief; optional authorized candidate and report refs
allowed_tools: ArtifactStorePort read of authorized refs; Controller task-ready queries when available
forbidden_actions: metric calculation; sealed OOS access; silent standard changes; recursive role spawning unless a future protocol explicitly authorizes it
output_contract: ResearchDecision
stop_conditions: budget exhausted; stop/freeze/reject decision issued; Brief invalidated
handoff_to: Controller state; Generator/Reviewer/Synthesizer tasks as decided
```

### Role: trend_momentum_generator

```text
role_id: trend_momentum_generator
purpose: Propose a limited number of Trend/Momentum FactorSpec candidates with economic hypotheses.
spawn_when: ResearchBrief is fixed; trend/momentum-relevant fields are available; candidate budget remains; research is not in sealed/frozen OOS.
do_not_spawn_when: budget exhausted; required fields missing; sealed OOS stage; freeze already completed for the run.
task_template: |
  Goal: generate a finite set of FactorSpec objects in the trend/momentum family only.
  Inputs: ResearchBrief projection; authorized success/failure knowledge refs for this family.
  Must check: required fields present; generate a new Python factor when the hypothesis is not covered by existing code; function follows the Factor single-symbol input/output contract; params are JSON-serializable.
  Forbidden: other families; metric invention; sealed OOS; modifying Brief standards.
  Output: one or more FactorSpec objects within budget.
required_inputs: ResearchBrief
allowed_tools: authorized knowledge/artifact refs; workspace read/write for the assigned strategies domain and matching tests
forbidden_actions: review decisions; pool acceptance; metric calculation; sealed OOS access
output_contract: FactorSpec
stop_conditions: family budget exhausted; no new non-duplicate hypothesis; required fields unavailable
handoff_to: Controller for preflight/compute/evaluate
```

### Role: mean_reversion_price_structure_generator

```text
role_id: mean_reversion_price_structure_generator
purpose: Propose Mean-Reversion and Price-Structure FactorSpec candidates only.
spawn_when: ResearchBrief is fixed; relevant price-structure fields are available; candidate budget remains; not sealed/frozen OOS.
do_not_spawn_when: budget exhausted; required fields missing; sealed OOS stage.
task_template: |
  Goal: generate a finite set of FactorSpec objects in the mean-reversion/price-structure family only.
  Inputs: ResearchBrief projection; authorized family knowledge refs.
  Must check: required fields; generate a new Python factor when useful; Factor callable contract; JSON params; falsification tests listed.
  Forbidden: other families; metrics; sealed OOS; Brief mutation.
  Output: FactorSpec set within budget.
required_inputs: ResearchBrief
allowed_tools: authorized knowledge/artifact refs; workspace read/write for the assigned strategies domain and matching tests
forbidden_actions: review decisions; pool acceptance; metric calculation; sealed OOS access
output_contract: FactorSpec
stop_conditions: family budget exhausted; no new hypothesis family; fields unavailable
handoff_to: Controller for preflight/compute/evaluate
```

### Role: volume_liquidity_generator

```text
role_id: volume_liquidity_generator
purpose: Propose Volume/Liquidity FactorSpec candidates only.
spawn_when: ResearchBrief is fixed; volume/liquidity fields available; candidate budget remains; not sealed/frozen OOS.
do_not_spawn_when: budget exhausted; required fields missing; sealed OOS stage.
task_template: |
  Goal: generate a finite set of FactorSpec objects in the volume/liquidity family only.
  Inputs: ResearchBrief projection; authorized family knowledge refs.
  Must check: required fields; generate a new Python factor when useful; Factor callable contract; JSON params; availability/missing rules.
  Forbidden: other families; metrics; sealed OOS; Brief mutation.
  Output: FactorSpec set within budget.
required_inputs: ResearchBrief
allowed_tools: authorized knowledge/artifact refs; workspace read/write for the assigned strategies domain and matching tests
forbidden_actions: review decisions; pool acceptance; metric calculation; sealed OOS access
output_contract: FactorSpec
stop_conditions: family budget exhausted; no new hypothesis family; fields unavailable
handoff_to: Controller for preflight/compute/evaluate
```

### Role: volatility_risk_regime_generator

```text
role_id: volatility_risk_regime_generator
purpose: Propose Volatility/Risk/Regime FactorSpec candidates only, including regime-conditioned hypotheses.
spawn_when: ResearchBrief is fixed; volatility/risk fields available; candidate budget remains; not sealed/frozen OOS.
do_not_spawn_when: budget exhausted; required fields missing; sealed OOS stage.
task_template: |
  Goal: generate a finite set of FactorSpec objects in the volatility/risk/regime family only.
  Inputs: ResearchBrief projection; authorized family knowledge refs.
  Must check: required fields; generate a new Python factor when useful; Factor callable contract; regime applicability; falsification tests.
  Forbidden: other families; metrics; sealed OOS; Brief mutation.
  Output: FactorSpec set within budget.
required_inputs: ResearchBrief
allowed_tools: authorized knowledge/artifact refs; workspace read/write for the assigned strategies domain and matching tests
forbidden_actions: review decisions; pool acceptance; metric calculation; sealed OOS access
output_contract: FactorSpec
stop_conditions: family budget exhausted; no new hypothesis family; fields unavailable
handoff_to: Controller for preflight/compute/evaluate
```

### Role: methodology_critic

```text
role_id: methodology_critic
purpose: Independently review economic mechanism, overfitting risk, robustness, and propose executable falsification tests.
spawn_when: A FactorSpec has a formal EvaluationReport on authorized splits.
do_not_spawn_when: No EvaluationReport; only informal notes exist; sealed OOS context; candidate already hard-failed on safety/leakage.
task_template: |
  Goal: produce a ReviewReport using only formal EvaluationReport evidence.
  Inputs: FactorSpec ref+hash; EvaluationReport ref+hash; Brief acceptance criteria.
  Must check: mechanism plausibility; complexity vs known factors; subsample/regime fragility; multiple-testing load; propose executable falsification tests.
  Forbidden: inventing metrics; accepting/promoting candidates; sealed OOS; modifying FactorSpec in place.
  Output: ReviewReport.
required_inputs: FactorSpec; EvaluationReport
allowed_tools: AnalyzePort read-only evidence via authorized refs; ArtifactStorePort get
forbidden_actions: new metric calculation; pool acceptance; sealed OOS access; silent formula edits
output_contract: ReviewReport
stop_conditions: review complete; hard methodological failure recorded; budget/lease expired
handoff_to: Supervisor / Controller; optional debate reuse
```

### Role: leakage_and_code_reviewer

```text
role_id: leakage_and_code_reviewer
purpose: Independently check time boundaries, data lineage, and formula semantics; may hard-fail deterministic violations.
spawn_when: Factor formula materials and deterministic check artifacts/EvaluationReport sections are available.
do_not_spawn_when: No formula/check materials; sealed OOS context only; review already hard-failed with no new materials.
task_template: |
  Goal: produce a ReviewReport focused on leakage, lookahead, survivor bias, adjustment/missing handling, and formula-semantic mismatch.
  Inputs: FactorSpec; EvaluationReport / deterministic check evidence; Brief data rules.
  Must check: future function / bad shifts; universe survivor bias; adjustment and missing rules; cross-sectional normalization lookahead; label/feature/execution time borders; formula vs semantics.
  Forbidden: inventing metrics; debating away hard safety failures; sealed OOS; accepting candidates.
  Output: ReviewReport with explicit violation codes and evidence.
required_inputs: FactorSpec; EvaluationReport or deterministic check evidence
allowed_tools: AnalyzePort evidence refs; ArtifactStorePort get
forbidden_actions: metric invention; pool acceptance; sealed OOS access
output_contract: ReviewReport
stop_conditions: hard-fail issued; review complete; lease expired
handoff_to: Supervisor / Controller; optional debate reuse
```

### Role: pool_synthesizer

```text
role_id: pool_synthesizer
purpose: Decide accept/watch/reject from portfolio incremental value; never create or edit factors.
spawn_when: Methodology and leakage reviews are complete and pool-incremental EvaluationReport section is available.
do_not_spawn_when: Missing either review; pool-incremental section not complete; sealed OOS stage for research revision.
task_template: |
  Goal: emit a PoolDecision using formal incremental evidence and residual risks.
  Inputs: FactorSpec; EvaluationReport pool_incremental facts; both ReviewReport refs; existing pool baseline refs.
  Must check: correlation/residual value; regime complementarity; turnover/cost/risk impact; Pareto trade-offs.
  Forbidden: creating/modifying FactorSpec; inventing metrics; sealed OOS; overriding hard-fail reviews.
  Output: PoolDecision.
required_inputs: FactorSpec; EvaluationReport; ReviewReport x2; pool baseline refs
allowed_tools: ArtifactStorePort get of authorized refs
forbidden_actions: factor creation/edit; metric calculation; sealed OOS access
output_contract: PoolDecision
stop_conditions: decision emitted; evidence incomplete and marked failed; lease expired
handoff_to: Supervisor / Human Gate-1 path via Controller
```

## Debate reuse rule

High-value disputes reuse the original Generator, Methodology Critic, Leakage
and Code Reviewer, and Supervisor. Do **not** invent a ninth role. At most two
debate rounds and at most one revision, after which the candidate must fully
re-enter preflight → compute → evaluate → independent review.

## Boundary checklist

- No IC, grouped return, turnover, cost, or robustness calculations in this skill.
- No static/leakage/data-quality checker implementations in this skill.
- No vendor Agent SDK, product whitelist, or platform command adapter.
- No second experiment directory and no static dependency on a specific
  `strategies/` module; `FunctionRef` resolves caller-selected import paths at runtime.
- Role definitions above are authoritative; Python carries `role_id` strings only.
