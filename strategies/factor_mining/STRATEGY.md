---
name: factor-mining
description: Governed cross-sectional factor-mining workflow: screen candidates on research data, record independent reviews, build the factor pool one accepted factor at a time, freeze, and open the sealed split once.
---

# Factor mining workflow

This workspace runs governed cross-sectional factor research in six phases:

```
init -> screening -> per candidate: record two reviews -> compare -> record pool decision
     -> freeze -> final
```

Contracts, factor execution, and evaluation come from `skills/factor_mining` and
`skills/analyze`. A candidate names its factor function by module and name: a public
indicator of `skills.compute.indicators`, or a function in a
`strategies/<domain>/mined_factors/` package. The default candidate list is
`strategies.factor_mining.mined_factors.CANDIDATES`, nineteen baseline candidates built
from public indicators in three families (trend and momentum, mean reversion and price
structure, volume and liquidity).

## Brief

A `ResearchBrief` JSON fixes the research before any candidate is evaluated: a
unique `brief_id`, the universe, market fields, adjustment and `data_version`,
disjoint train, validation, and sealed windows, horizon and trading costs, the
candidate budget, acceptance rules, and the sealed-test thresholds.

`data_version` is the fingerprint of the research-window panel (everything up to
`validation.end`). Screening and the final preflight recompute it from local data
and stop when it differs, so a Brief is bound to one copy of the data. A new sealed
test needs a new Brief and sealed data nobody has looked at.

`init` writes the example Brief for the 18 asset-class ETFs
(`strategies.cross_sectional.asset_class_rotation`) with `data_version` taken from
local `data/market/1d_adj`. To write your own Brief, start from
`uv run qs factor-mining template ResearchBrief` and finish it with
`uv run qs factor-mining validate ResearchBrief --fill-hash`.

## Phases

Run from the repository root:

```bash
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase init
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase screening --jobs 8
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase record --object out/review.json
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase compare --factor <factor_id>
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase record --object out/pool_decision.json
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase freeze --approve <factor_id,...>
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase final --write
```

Each phase prints one JSON summary. `--data-root` selects another data root and
`--output-dir` another summary folder; the default is
`reports/factor_mining/<brief_id>/`. Formal objects are written under
`data/factors/<namespace>/artifacts/<kind>/`.

| Phase | Reads | Writes |
|-------|-------|--------|
| `init` | Research-window bars | The example Brief at `--brief` (`--overwrite` replaces it) |
| `screening` | Research-window bars only | `research_brief`, `factor_spec`, `factor_execution_result`, `evaluation_report` (preflight, train, validation); `screening_index.json`, `screening_results.csv` |
| `compare` | One candidate's validation values and the pool members' | One `evaluation_report` per candidate and pool size, written once; `compare.<factor_id>.p<N>.json` |
| `record` | The object at `--object` and what it cites | One `review_report` or `pool_decision`, written once; an accepting decision also appends a `pool_member` |
| `freeze` | Screening index, pool members, reviews, pool decisions | `human_gate_1`, `freeze_manifest`, `freeze_batch`, all written once; `freeze_index.json` |
| `final` | Frozen batch, research window, then the sealed split | `unblind_started`, sealed `factor_execution_result` and `evaluation_report`, `unblind_completed` or `unblind_failed`; `final_summary.json` |

## Screening

`screening` evaluates every candidate of the list on the train and validation
windows. `--candidates <module>` reads the `CANDIDATES` list of another module, for
example one a Generator role wrote; without it the baseline list is used.
`screening_results.csv` has one line per candidate with its Rank IC mean, ICIR,
HAC t-statistic, positive ratio, and sample count on each window.

A candidate already in the screening index is kept as it is, so an interrupted run
resumes where it stopped and a later run can add candidates as long as the total
stays within `budget.max_candidates`. Reviews and pool decisions bind to the stored
reports, so those are never recomputed. Changing a screened candidate is refused: a
revision is a new candidate with a new `factor_id`.

Most of the time goes into the prefix-recompute causality check, which reruns the
factor on every prefix of the window. One candidate takes two to three minutes on
the 18 ETFs; `--jobs N` screens N candidates at once in separate processes.

## The factor pool

The pool holds the factors accepted under this Brief, in the order they were
accepted. It starts empty and grows one factor at a time:

1. Record both reviews of the candidate.
2. Run `compare --factor <factor_id>`. It compares the candidate's validation values
   with every current pool member (correlation with the pool, residual Rank IC after
   the pool, change in joint R2) and stores the result as
   `compare.<factor_id>.p<N>`, where N is the pool size it was compared with.
3. Record a `PoolDecision`. An accepting decision must cite evidence from the
   comparison against the pool as it is now. If another factor entered the pool in
   the meantime, the comparison is out of date and `record` asks for `compare` again.

The first factor has nothing to be compared with, so its comparison reports
`POOL_UNAVAILABLE`. A Brief may set `freeze_criteria.require_pool_incremental=false`
to let it in: both reviews must pass, and the accepting `PoolDecision` cites that
`POOL_UNAVAILABLE` check as its only incremental evidence and lists
`POOL_INCREMENTAL_UNAVAILABLE` in `residual_risks`. The decision records that
incremental value was not tested; it does not establish it. Every later factor needs
real incremental evidence. With `require_pool_incremental=true` the pool can never
start.

The order of acceptance matters: a factor is judged against the factors accepted
before it, not against the ones that come later.

## Recording reviews and the pool decision

`record` takes a JSON file `{"object_type": ..., "payload": ...}` where
`object_type` is `ReviewReport` or `PoolDecision` and `payload` is the object with
its `content_hash` filled in (`uv run qs factor-mining validate <type> --fill-hash`).
The workflow refuses an object whose identity or references do not match:

| Object | Required identity | Must reference |
|--------|-------------------|----------------|
| `ReviewReport` | `role_id` is `methodology_critic` or `leakage_and_code_reviewer`; `report_id` is `rev.<factor_id>.<role_id>` | The candidate's `FactorSpec` and its validation `EvaluationReport` (`eval-eval.<factor_id>__validation`) |
| `PoolDecision` | `role_id` is `pool_synthesizer`; `decision_id` is `pool.<factor_id>` | The candidate's `FactorSpec`; an accepting decision cites evidence from `eval-compare.<factor_id>.p<N>` for the current pool size N |

Provenance must carry the Brief's namespace and `data_version`. Every evidence
reference is checked against the stored report it names, so a review cannot cite a
number the evaluation did not produce. Each object can be recorded once.

## Freeze

`freeze --approve <factor_id,...>` is the human gate. The list must be the first
factors of the pool, in pool order: each member was compared with the members before
it, so a leading part of the pool is a self-contained set and any other selection is
not. For every approved factor it rechecks the clean preflight and evaluations, both
reviews, the accepting `PoolDecision`, and the comparison it was accepted on, then
writes a `FreezeManifest` that fixes the factor, its parameters, the evaluation
protocol, the pool members it was compared with, and the sealed-test thresholds
taken from `oos_criteria`. After the freeze, screening for this Brief is closed.

## Final: the sealed split opens once

`final --write` first works on research data only: it verifies the frozen batch,
checks that the candidate code still has the frozen fingerprint, and reruns the
validation evaluation in a scratch directory to confirm it reproduces the frozen
values. Any failure here leaves the sealed split unopened.

It then creates the `unblind_started` artifact with `put_if_absent`, which creates a
file at most once even across processes, and only afterwards loads sealed rows. A
second `final` for the same Brief stops with `sealed OOS already started for this
Brief`. A failure after that point writes `unblind_failed` and still uses up the
Brief's one sealed test. `final_summary.json` lists each frozen metric, its
threshold, and whether it passed.

## What this workflow does not do

It is a file-based workflow, not a multi-agent runtime. The host agent hands out
role tasks as described in `skills/factor_mining/SKILL.md`; the workflow checks
what comes back. It keeps no task queue, budget ledger, or replayable event log:
the candidate budget is checked as the number of screened candidates against
`budget.max_candidates`, and the audit trail is the set of write-once artifacts above.
