---
name: factor_mining
description: Discover, template, and validate versioned factor-mining contracts (ResearchBrief, FactorSpec, ReviewReport, PoolDecision, and more) and check generated factor functions with `uv run qs factor-mining ...`; defines the multi-agent research role protocol. Use for AI factor mining research.
---

# Factor Mining

Use the `uv run qs factor-mining` commands below; data and research tasks do not
require reading `skills/factor_mining/` source. Each command prints one JSON envelope
on stdout (`ok`, `data`, `artifacts`, `warnings`, or `error` with a `hint`).
Exact options: `uv run qs factor-mining <command> --help` or
`uv run qs schema factor-mining.<command>`.

`skills/factor_mining` is the Agent collaboration and research-governance boundary
for market-panel factor mining: versioned research objects and the role/task
protocol below. Deterministic execution and evaluation run through the strategy
workflow `strategies/factor_mining/workflows/run_factor_mining.py`.

## Workflow

```bash
uv run qs factor-mining types
uv run qs factor-mining schema FactorSpec
uv run qs factor-mining template FactorSpec --output out/spec.json
# Generator roles write the factor under strategies/<domain>/mined_factors/ and fill spec.json
uv run qs factor-mining check-function \
  --function strategies.<domain>.mined_factors.<module>:<name> --panel out/small_panel.parquet
uv run qs factor-mining validate FactorSpec --file out/spec.json --fill-hash \
  --output out/spec.final.json
```

Generator roles may create arbitrary Python factor implementations in
`strategies/<domain>/mined_factors/` and matching tests under
`tests/strategies/<domain>/`. A `FactorSpec` points to the generated function
by importable `module:name`; the function takes one symbol's bars and returns a
Series on the same index (the `skills.compute.wrappers.Factor` contract), and
factor execution is not restricted to `skills.compute.indicators`. Use
`--fill-hash` only when `content_hash` is blank.

The governed run itself (screening, recording reviews, freezing, and the one
sealed test) is the strategy workflow; see
[strategies/factor_mining/STRATEGY.md](../../strategies/factor_mining/STRATEGY.md):

```bash
uv run python -m strategies.factor_mining.workflows.run_factor_mining \
  --brief out/brief.json --phase init
uv run python -m strategies.factor_mining.workflows.run_factor_mining \
  --brief out/brief.json --phase screening
```

## Contract invariants

- Every versioned object carries `schema_version`, content hash semantics, and
  explicit caller `namespace`. `SCHEMA_VERSION` is `1.4.0`.
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
branches in Python or in this protocol. Default: sub-agents do not recursively spawn
further agents. Sealed OOS data and results never enter generation, review,
or debate contexts. All modes must return the same
contracts and record role_id, parent task, input versions/hashes, output refs,
and status.

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
Supervisor has allocated candidate budget from Brief `budget` (候选额度).
Every submitted result must exact-match its assigned task view: task/run/parent
/role ids, expected output type, input-ref hashes, and a budget consumption no
greater than the allocated 候选额度. The strategy workflow remains the authority
for deterministic preflight → compute → evaluate, object existence, and
content-hash verification.

After deterministic evaluation, the two `ReviewReport` roles receive the same
formal FactorSpec/EvaluationReport snapshot but never each other's draft. The
`PoolDecision` role begins only after both independent reviews return accepted
formal results. A failed, timed-out, cancelled, or duplicate return is reported
through the corresponding workflow step; it never triggers a second budget
allocation or direct state write. A child task must not recursively spawn.

For the first candidate in an empty pool, `POOL_UNAVAILABLE` is an explicit
absence of incremental evidence, not a failed calculation to conceal. If the
Brief sets `freeze_criteria.require_pool_incremental=false`, both independent
reviews pass, and the comparison has no pool refs and exactly this soft-fail
condition, `pool_synthesizer` may recommend a one-factor bootstrap for Human
Gate-1. Its `PoolDecision` must cite the `POOL_UNAVAILABLE` check as its sole
`incremental_evidence`, include `POOL_INCREMENTAL_UNAVAILABLE` in
`residual_risks`, and state that incremental value is untested. This decision
authorizes only the frozen OOS test, never claims pool improvement or alpha
promotion. Any other partial or failed pool section remains ineligible.

Do not debate a hard safety, leakage, data-availability, or threshold failure.
For a high-value conflict only, reuse the original involved roles and follow
Claim → Evidence → Objection → Falsification Test → Response → Decision. There
are at most two rounds and at most one revision. A revision is a new candidate
that consumes Supervisor-allocated candidate budget and completes the
full preflight → compute → evaluate → independent-review path before synthesis.

## Shared task template envelope

Every spawned task must include:

- goal
- immutable input refs and content hashes
- allocated candidate budget from Brief `budget`
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
allowed_tools: ArtifactStorePort read of authorized refs; strategy workflow status queries when available
forbidden_actions: metric calculation; sealed OOS access; silent standard changes; recursive role spawning unless a future protocol explicitly authorizes it
output_contract: ResearchDecision
stop_conditions: budget exhausted; stop/freeze/reject decision issued; Brief invalidated
handoff_to: strategy workflow; Generator/Reviewer/Synthesizer tasks as decided
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
allowed_tools: authorized knowledge/artifact refs; workspace read/write for strategies/<domain>/mined_factors/ and tests/strategies/<domain>/
forbidden_actions: review decisions; pool acceptance; metric calculation; sealed OOS access
output_contract: FactorSpec
stop_conditions: family budget exhausted; no new non-duplicate hypothesis; required fields unavailable
handoff_to: strategy workflow for deterministic preflight → compute → evaluate
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
allowed_tools: authorized knowledge/artifact refs; workspace read/write for strategies/<domain>/mined_factors/ and tests/strategies/<domain>/
forbidden_actions: review decisions; pool acceptance; metric calculation; sealed OOS access
output_contract: FactorSpec
stop_conditions: family budget exhausted; no new hypothesis family; fields unavailable
handoff_to: strategy workflow for deterministic preflight → compute → evaluate
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
allowed_tools: authorized knowledge/artifact refs; workspace read/write for strategies/<domain>/mined_factors/ and tests/strategies/<domain>/
forbidden_actions: review decisions; pool acceptance; metric calculation; sealed OOS access
output_contract: FactorSpec
stop_conditions: family budget exhausted; no new hypothesis family; fields unavailable
handoff_to: strategy workflow for deterministic preflight → compute → evaluate
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
allowed_tools: authorized knowledge/artifact refs; workspace read/write for strategies/<domain>/mined_factors/ and tests/strategies/<domain>/
forbidden_actions: review decisions; pool acceptance; metric calculation; sealed OOS access
output_contract: FactorSpec
stop_conditions: family budget exhausted; no new hypothesis family; fields unavailable
handoff_to: strategy workflow for deterministic preflight → compute → evaluate
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
stop_conditions: review complete; hard methodological failure recorded; budget expired
handoff_to: Supervisor / strategy workflow; optional debate reuse
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
stop_conditions: hard-fail issued; review complete; budget expired
handoff_to: Supervisor / strategy workflow; optional debate reuse
```

### Role: pool_synthesizer

```text
role_id: pool_synthesizer
purpose: Decide accept/watch/reject from portfolio incremental value, or document an explicitly waived empty-pool bootstrap; never create or edit factors.
spawn_when: Both reviews pass and pool-incremental evidence is complete, or the Brief explicitly waives pool incrementality and the comparison shows only POOL_UNAVAILABLE with no pool refs.
do_not_spawn_when: Missing or non-pass review; any other incomplete pool-incremental section; sealed OOS stage for research revision.
task_template: |
  Goal: emit a PoolDecision using formal incremental evidence and residual risks, or explicitly label the first empty-pool candidate as untested for incremental value.
  Inputs: FactorSpec; EvaluationReport pool_incremental facts/checks; both ReviewReport refs; existing pool baseline refs if available.
  Must check: correlation/residual value; regime complementarity; turnover/cost/risk impact; Pareto trade-offs when available. For an empty pool, cite POOL_UNAVAILABLE, record POOL_INCREMENTAL_UNAVAILABLE, and assess standalone evidence and review risks before recommending one candidate for Human Gate-1.
  Forbidden: creating/modifying FactorSpec; inventing metrics; sealed OOS; overriding hard-fail reviews.
  Output: PoolDecision.
required_inputs: FactorSpec; EvaluationReport; ReviewReport x2; pool baseline refs when available
allowed_tools: ArtifactStorePort get of authorized refs
forbidden_actions: factor creation/edit; metric calculation; sealed OOS access
output_contract: PoolDecision
stop_conditions: decision emitted; evidence incomplete and marked failed; budget expired
handoff_to: Supervisor / Human Gate-1 path via strategy workflow
```

## Debate reuse rule

High-value disputes reuse the original Generator, Methodology Critic, Leakage
and Code Reviewer, and Supervisor. Do **not** invent a ninth role. At most two
debate rounds and at most one revision, after which the candidate must fully
re-enter preflight → compute → evaluate → independent review.

## Python API

Only needed when changing `skills/factor_mining/` itself or writing strategy code that
imports it: [references/python-api.md](references/python-api.md).

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Transport: `--input-json FILE|-`, `--preview N`, and `--log-level LEVEL`; flags override JSON. Use `--print-template [FIELD]` for fillable templates.

### Shared parameter groups

#### `PanelSource`

| Option | Type / default | Description |
|---|---|---|
| `--panel` | `path?` / `null` | Parquet/CSV panel, mutually exclusive with symbols or symbols-file. |
| `--symbols` | `list[string]` / `factory` | QuantSpace symbols such as SHSE.510300; repeat flag or comma-separate. |
| `--symbols-file` | `path?` / `null` | Text lines or JSON list of QuantSpace symbols. |
| `--frequency` | `string` / `1d` | Market store directory under data/market, for example 1d or 1d_adj. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |
| `--start` | `string?` / `null` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string?` / `null` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |
| `--fields` | `list[string]` / `factory` | Optional panel field subset. |

### `uv run qs factor-mining types`

List factor-mining contract types.

Priority: P0. Side effects: read-only.

| Option | Type / default | Description |
|---|---|---|

Output data fields: `schema_version`, `types`.

Inspect schemas: `uv run qs schema factor-mining.types` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs factor-mining schema`

Show a contract JSON Schema.

Priority: P0. Side effects: read-only.

Positional: `type_name`.

| Option | Type / default | Description |
|---|---|---|
| `--type-name` | `string` / `required` | Exported factor-mining contract dataclass name. |

Output data fields: `type_name`, `json_schema`.

Inspect schemas: `uv run qs schema factor-mining.schema` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs factor-mining template`

Generate a fillable contract skeleton.

Priority: P0. Side effects: writes-output.

Positional: `type_name`.

| Option | Type / default | Description |
|---|---|---|
| `--type-name` | `string` / `required` | Exported factor-mining contract dataclass name. |
| `--output` | `path?` / `null` | Optional plain contract JSON output. |
| `--overwrite` | `boolean` / `false` | Replace an existing output file. |
| `--data-root` | `path?` / `null` | Optional output path guard root. |

Output data fields: `type_name`, `template`.

Inspect schemas: `uv run qs schema factor-mining.template` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs factor-mining validate`

Validate a contract and its content hash.

Priority: P0. Side effects: read-only, writes-output.

Positional: `type_name`.

| Option | Type / default | Description |
|---|---|---|
| `--type-name` | `string` / `required` | Exported factor-mining contract dataclass name. |
| `--file` | `path?` / `null` | JSON contract file; omit or use - for stdin. |
| `--fill-hash` | `boolean` / `false` | Fill an absent content_hash using the domain constructor. |
| `--output` | `path?` / `null` | Optional validated JSON output path. |
| `--overwrite` | `boolean` / `false` | Replace an existing output file. |
| `--data-root` | `path?` / `null` | Optional output path guard root. |

Output data fields: `type_name`, `value`, `content_hash`.

Inspect schemas: `uv run qs schema factor-mining.validate` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs factor-mining check-function`

Check a factor function's required fields and prefix causality.

Priority: P1. Side effects: read-only.

Shared parameters: `PanelSource`.

| Option | Type / default | Description |
|---|---|---|
| `--function` | `string` / `required` | Importable factor callable as module:name. |
| `--params` | `object` / `factory` | JSON keyword arguments passed to the factor. |
| `--required-fields` | `list[string]` / `factory` | Panel columns required by the factor. |

Output data fields: `function`, `rows`, `checked_prefixes`, `required_fields`.

Inspect schemas: `uv run qs schema factor-mining.check-function` (add `--part input|output` or `--file-field FIELD`).

<!-- END GENERATED: qs commands -->
