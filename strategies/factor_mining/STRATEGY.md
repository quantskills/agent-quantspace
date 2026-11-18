---
name: factor-mining
description: Governed cross-sectional factor-mining workflow: screen candidates on research data, record independent reviews, freeze approved factors, and open the sealed split once.
---

# Factor mining workflow

This workspace runs governed cross-sectional factor research in five phases:

```
init -> screening -> record (two reviews + pool decision) -> freeze -> final
```

Contracts, factor execution, and evaluation come from `skills/factor_mining` and
`skills/analyze`. Candidate functions live in a `strategies/<domain>/mined_factors/`
package; the default list is `strategies.factor_mining.mined_factors.CANDIDATES`.

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
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase screening
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase record --object out/review.json
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase freeze --approve <factor_id>
uv run python -m strategies.factor_mining.workflows.run_factor_mining --brief out/brief.json --phase final --write
```

Each phase prints one JSON summary. `--data-root` selects another data root and
`--output-dir` another summary folder; the default is
`reports/factor_mining/<brief_id>/`. Formal objects are written under
`data/factors/<namespace>/artifacts/<kind>/`.

| Phase | Reads | Writes |
|-------|-------|--------|
| `init` | Research-window bars | The example Brief at `--brief` (`--overwrite` replaces it) |
| `screening` | Research-window bars only | `research_brief`, `factor_spec`, `factor_execution_result`, `evaluation_report` (preflight, train, validation, pool comparison); `screening_index.json`, `screening_summary.json` |
| `record` | The object at `--object` and what it cites | One `review_report` or `pool_decision`, written once |
| `freeze` | Screening index, both reviews, the pool decision | `human_gate_1`, `freeze_manifest`, `freeze_batch`, all written once; `freeze_index.json` |
| `final` | Frozen batch, research window, then the sealed split | `unblind_started`, sealed `factor_execution_result` and `evaluation_report`, `unblind_completed` or `unblind_failed`; `final_summary.json` |

Screening can be rerun until the Brief is frozen. With the one example candidate
on 18 ETFs it takes about two minutes, most of it the prefix-recompute causality
check.

## Recording reviews and the pool decision

`record` takes a JSON file `{"object_type": ..., "payload": ...}` where
`object_type` is `ReviewReport` or `PoolDecision` and `payload` is the object with
its `content_hash` filled in (`uv run qs factor-mining validate <type> --fill-hash`).
The workflow refuses an object whose identity or references do not match:

| Object | Required identity | Must reference |
|--------|-------------------|----------------|
| `ReviewReport` | `role_id` is `methodology_critic` or `leakage_and_code_reviewer`; `report_id` is `rev.<factor_id>.<role_id>` | The candidate's `FactorSpec` and its validation `EvaluationReport` (`eval-eval.<factor_id>__validation`) |
| `PoolDecision` | `role_id` is `pool_synthesizer`; `decision_id` is `pool.<factor_id>` | The candidate's `FactorSpec`; `incremental_evidence` cites evidence that exists in a stored `EvaluationReport` |

Provenance must carry the Brief's namespace and `data_version`. Every evidence
reference is checked against the stored report it names, so a review cannot cite a
number the evaluation did not produce. Each object can be recorded once.

## Freeze

`freeze --approve <factor_id,...>` is the human gate. For every approved factor it
requires a clean preflight, clean train and validation evaluations, both reviews
without a hard failure, each bound to the validation report, and an accepting
`PoolDecision`. It then writes a `FreezeManifest` that fixes the factor, its
parameters, the evaluation protocol, and the sealed-test thresholds taken from
`oos_criteria`. After the freeze, screening for this Brief is closed.

The factor pool of this workflow starts empty, so the pool comparison reports
`POOL_UNAVAILABLE`. A Brief may set `freeze_criteria.require_pool_incremental=false`
to test its first candidate: both reviews must pass, and the accepting
`PoolDecision` cites that `POOL_UNAVAILABLE` check as its only incremental evidence
and lists `POOL_INCREMENTAL_UNAVAILABLE` in `residual_risks`. At most one candidate
can be frozen this way. The decision records that incremental value was not tested;
it does not establish it.

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
the candidate budget is checked as `len(candidates) <= budget.max_candidates`, and
the audit trail is the set of write-once artifacts above.
