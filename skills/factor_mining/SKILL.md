---
name: factor-mining
description: Run governed AI factor mining: template and validate versioned research contracts (ResearchBrief, FactorSpec, ReviewReport, PoolDecision), check generated factor functions with `uv run qs factor-mining ...`, and follow the multi-agent role protocol for generating, reviewing, and pooling factors.
---

# Factor Mining

Use the `uv run qs factor-mining` commands below; research tasks do not require
reading `skills/factor_mining/` source. Each command prints one JSON envelope on
stdout (`ok`, `data`, `artifacts`, `warnings`, or `error` with a `hint`). Exact
options: `uv run qs factor-mining <command> --help` or
`uv run qs schema factor-mining.<command>`.

This Skill owns the research contracts and the role protocol. The governed run
(screening, reviews, the factor pool, freeze, and the one sealed test) is the
strategy workflow described in
[strategies/factor_mining/STRATEGY.md](../../strategies/factor_mining/STRATEGY.md).

## When to use

- Mine cross-sectional factors under a fixed Research Brief with separate
  generation, review, and pool-decision roles.
- Write or validate a `ResearchBrief`, `FactorSpec`, `ReviewReport`, or
  `PoolDecision`.
- Check that a generated factor function reads only its declared fields and
  does not use future rows.

A one-off factor test needs none of this: use `qs compute factor` and
`qs analyze factor-ic`.

## Workflow

Contracts and generated functions:

```bash
uv run qs factor-mining types
uv run qs factor-mining schema FactorSpec
uv run qs factor-mining template FactorSpec --output out/spec.json
# A Generator role writes the function under strategies/<domain>/mined_factors/ and fills spec.json
uv run qs factor-mining check-function \
  --function strategies.<domain>.mined_factors.<module>:<name> --panel out/panel.parquet \
  --required-fields close
uv run qs factor-mining validate FactorSpec --file out/spec.json --fill-hash \
  --output out/spec.final.json
```

The governed run, one phase per command:

```bash
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase init
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase screening --jobs 8
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase draft --factor <factor_id> --role methodology_critic
uv run qs factor-mining validate ReviewReport --file <draft> --fill-hash --output out/review.json
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase record --object out/review.json
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase compare --factor <factor_id>
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase draft --factor <factor_id> --role pool_synthesizer
uv run qs factor-mining validate PoolDecision --file <draft> --fill-hash --output out/pool_decision.json
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase record --object out/pool_decision.json
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase freeze --approve <factor_id,...>
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase final --write
```

`init` writes the example Brief; `screening` runs preflight and evaluation for
every candidate; `draft` writes a review or pool-decision skeleton with its
identifiers and references set, plus the list of evidence it may cite; the role
fills in its judgement and `validate --fill-hash` completes it; `record` is run
once per reviewer role and once for the pool decision; `compare` compares a candidate with the current pool; `freeze` is the
human gate; `final` opens the sealed split, once per Brief.

## Files

- A contract file is one JSON object with `schema_version`, a `namespace`, and a
  `content_hash`. `validate --fill-hash` fills a blank hash; a filled hash that
  does not match is an error.
- A `FactorSpec` names its function as importable `module:name`. The function
  takes one symbol's bars and returns a series on the same index. It may be an
  indicator of `skills.compute.indicators` or new code under
  `strategies/<domain>/mined_factors/`, with tests under
  `tests/strategies/<domain>/`.
- `record --object` takes the validated contract file. `draft` sets these
  identifiers and references; the workflow refuses anything else:

  | Object | Identifier | Must reference |
  |--------|------------|----------------|
  | `ReviewReport` | `report_id` = `rev.<factor_id>.<role_id>` | The `FactorSpec` and its validation report `eval-eval.<factor_id>__validation` |
  | `PoolDecision` | `decision_id` = `pool.<factor_id>` | The `FactorSpec`; an accepting decision cites evidence from `eval-compare.<factor_id>.p<N>`, N being the current pool size |

- Formal objects are stored once under
  `data/factors/<namespace>/artifacts/<kind>/`; summaries go to
  `reports/factor_mining/<brief_id>/`.

## Rules

- `EvaluationReport` holds deterministic facts, rule checks, and failures only.
  Rationale and accept or reject decisions live in `ReviewReport`,
  `PoolDecision`, and `ResearchDecision`. No role invents or recomputes a metric.
- Sealed data and sealed results never enter a generation, review, or debate
  context. `final` opens the sealed split once per Brief.
- A revised factor is a new candidate with a new `factor_id`. It uses candidate
  budget and goes through the full preflight → compute → evaluate →
  independent-review path again.
- The factor pool grows one factor at a time. Each accepting `PoolDecision`
  cites the comparison against the pool as it is at that moment.
- The first factor has no pool to be compared with, so its comparison reports
  `POOL_UNAVAILABLE`. If the Brief sets
  `freeze_criteria.require_pool_incremental=false` and both reviews pass, the
  `PoolDecision` may accept it by citing that check as its only
  `incremental_evidence` and listing `POOL_INCREMENTAL_UNAVAILABLE` in
  `residual_risks`. This records that incremental value is untested; it does
  not claim pool improvement.
- Role names are ordinary `role_id` strings. Python code must not copy the role
  catalog below as an enum, registry, or platform whitelist.

## Running the roles

The host main agent is the Supervisor. It selects one mode by the capabilities
it actually has, never by product name:

1. **Native sub-agent**: isolated role contexts with parallel dispatch, wait,
   and collect.
2. **Equivalent isolated tasks**: independent input and output contexts with
   the same structured contracts, when native dispatch is unavailable.
3. **Sequential single-agent fallback**: run the roles in order, rebuilding the
   minimum authorized context before each one and keeping generation separate
   from review.

All modes return the same contracts. Keep the role order of this file for
stable task ids, collection order, and summaries, so completion timing never
changes candidate order or budget use. Do not encode vendor tool names, SDKs,
or platform branches in Python or in this protocol. A child task must not
recursively spawn further agents.

Order of work for one Brief:

1. The Supervisor allocates candidate budget from the Brief's `budget` to the
   Generator roles and hands each an independent projection of the Brief. They
   may run concurrently.
2. The workflow screens the returned `FactorSpec` objects.
3. The two reviewer roles receive the same `FactorSpec` and `EvaluationReport`
   and never each other's draft.
4. After both reviews are recorded and the comparison with the pool has run,
   `pool_synthesizer` writes the `PoolDecision`.

A failed, timed-out, cancelled, or duplicate task is reported as such. It never
gets a second budget allocation.

Every task handed to a role states: the goal, immutable input refs with content
hashes, the allocated candidate budget, required checks, forbidden actions, and
exactly one expected output contract. Every return carries the task, parent,
and role ids, a status, one structured output or failure, evidence and artifact
refs, the budget used, and the handoff target. A Generator's output is the
`FactorSpec`; the Python module and test it wrote are listed as artifact refs.

## Debate

Do not debate a hard safety, leakage, data-availability, or threshold failure.
For a high-value conflict only, reuse the roles already involved (the original
Generator, both reviewers, and the Supervisor; no new role) and follow
Claim → Evidence → Objection → Falsification Test → Response → Decision. There
are at most two rounds and at most one revision.

---

## Roles

This section is the only authoritative catalog of the eight logical roles: the
Supervisor, four Generators, two reviewers, and the pool synthesizer.

### Role: supervisor

```text
role_id: supervisor
purpose: Coordinate research under a fixed Research Brief; allocate budgets; decide continue/revise/stop/freeze without replacing reviewers or inventing metrics.
spawn_when: A valid ResearchBrief is active and research coordination is required. Usually performed by the host main agent; do not spawn a second supervisor by default.
do_not_spawn_when: Sealed OOS is open; no Brief is fixed; a freeze/OOS deterministic path is already running without coordination needs.
task_template: |
  Goal: discover current agent capabilities, allocate remaining candidate budget, and emit a ResearchDecision and/or task list.
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

### Role: generators

The four Generator roles share one definition. Replace `<family>` and
`<role_id>` with a row of this table.

| role_id | Family | Check in addition |
|---------|--------|-------------------|
| `trend_momentum_generator` | trend and momentum | the hypothesis is not already covered by existing code |
| `mean_reversion_price_structure_generator` | mean reversion and price structure | falsification tests are listed |
| `volume_liquidity_generator` | volume and liquidity | availability and missing-value rules for volume fields |
| `volatility_risk_regime_generator` | volatility, risk, and regime | the regimes the hypothesis applies to; falsification tests are listed |

```text
role_id: <role_id>
purpose: Propose a limited number of FactorSpec candidates in the <family> family, each with an economic hypothesis.
spawn_when: ResearchBrief is fixed; fields relevant to the family are available; candidate budget remains; research is not in the sealed or frozen stage.
do_not_spawn_when: budget exhausted; required fields missing; sealed OOS stage; freeze already completed for the run.
task_template: |
  Goal: generate a finite set of FactorSpec objects in the <family> family only.
  Inputs: ResearchBrief projection; authorized success/failure knowledge refs for this family.
  Must check: required fields present; write a new Python factor when existing code does not cover the hypothesis; the function follows the single-symbol input/output contract; params are JSON-serializable; the family's additional check in the table above.
  Forbidden: other families; metric invention; sealed OOS; modifying Brief standards.
  Output: one or more FactorSpec objects within budget.
required_inputs: ResearchBrief
allowed_tools: authorized knowledge/artifact refs; workspace read/write for strategies/<domain>/mined_factors/ and tests/strategies/<domain>/
forbidden_actions: review decisions; pool acceptance; metric calculation; sealed OOS access
output_contract: FactorSpec
stop_conditions: family budget exhausted; no new non-duplicate hypothesis; required fields unavailable
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
purpose: Decide accept/watch/reject from the candidate's incremental value over the current factor pool, or document the first factor of an empty pool as untested for incremental value; never create or edit factors.
spawn_when: Both reviews are recorded with a pass and the comparison against the current pool has run.
do_not_spawn_when: Missing or non-pass review; no comparison for the current pool size; an incomplete comparison other than POOL_UNAVAILABLE on an empty pool; sealed OOS stage.
task_template: |
  Goal: emit a PoolDecision using the comparison evidence and residual risks.
  Inputs: FactorSpec; the comparison report eval-compare.<factor_id>.p<N>; both ReviewReport refs; the current pool members.
  Must check: correlation with the pool; residual Rank IC after the pool; change in joint R2; regime complementarity; turnover/cost/risk impact. For an empty pool, cite POOL_UNAVAILABLE, record POOL_INCREMENTAL_UNAVAILABLE, and assess standalone evidence and review risks.
  Forbidden: creating/modifying FactorSpec; inventing metrics; sealed OOS; overriding hard-fail reviews.
  Output: PoolDecision.
required_inputs: FactorSpec; comparison EvaluationReport; ReviewReport x2; current pool members
allowed_tools: ArtifactStorePort get of authorized refs
forbidden_actions: factor creation/edit; metric calculation; sealed OOS access
output_contract: PoolDecision
stop_conditions: decision emitted; evidence incomplete and marked failed; budget expired
handoff_to: Supervisor / human freeze gate via strategy workflow
```

## References

- [strategies/factor_mining/STRATEGY.md](../../strategies/factor_mining/STRATEGY.md):
  the Brief, every workflow phase, the factor pool, freeze, and the sealed test.
- [references/python-api.md](references/python-api.md): contracts, ports, and
  adapters. Read it when changing this Skill or writing strategy code.

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Before using a command, run it with `--help` to see its options and defaults. `uv run qs schema <skill>.<command>` shows its input and output fields; add `--file-field FIELD` for the structure of an option that takes a JSON file.

| Command | What it does | Side effects |
|---|---|---|
| `uv run qs factor-mining types` | List factor-mining contract types. | read-only |
| `uv run qs factor-mining schema` | Show a contract JSON Schema. | read-only |
| `uv run qs factor-mining template` | Generate a fillable contract skeleton. | writes-output |
| `uv run qs factor-mining validate` | Validate a contract and its content hash. | read-only, writes-output |
| `uv run qs factor-mining check-function` | Check a factor function's required fields and prefix causality. | read-only |

<!-- END GENERATED: qs commands -->
