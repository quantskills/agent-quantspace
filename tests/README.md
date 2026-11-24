# Tests

[中文说明](README-zh.md)

This directory contains the public pytest suite for QuantSpace.

The test tree mirrors the source boundaries so changes land near the code they
protect.

```text
tests/skills/          unit tests for skills/
tests/strategies/      unit tests for strategies/
tests/scripts/         script entrypoint tests
tests/integration/     local end-to-end flows
tests/contracts/       public API and data contract tests
tests/regression/      deterministic behavior regression tests
tests/docs/            documentation example smoke tests
tests/policy/          test layout and workspace policy tests
tests/smoke/           opt-in qs smoke tests on real local data (see Smoke tests)
tests/live/            opt-in live_trade checks during trading hours (see Live checks)
tests/fixtures/        deterministic fixture builders
```

Skill tests use the current public skill set:

```text
tests/skills/analyze/
tests/skills/backtest/
tests/skills/compute/
tests/skills/ingest/
tests/skills/ml/
tests/skills/report/
tests/skills/store/
tests/skills/strategy/
```

There are no `tests/skills/construct/` or `tests/skills/model/` directories;
portfolio construction is covered under `backtest`, and model helpers are
covered under `ml`. Reusable cross-sectional and time-series strategy types are
covered under `strategy`; concrete behavior remains under `tests/strategies/`.

## Run

```bash
uv run python -m pytest tests/
uv run python -m pytest tests/skills tests/strategies -q
uv run python -m pytest tests/contracts tests/regression tests/docs -q
```

## Smoke tests

`tests/smoke/` drives the installed `qs` script, as a subprocess, over every
non-network command on real local market data. It is opt-in: the default run
reports these tests as skipped, and any `-m` expression that mentions `smoke`
turns them on.

```bash
uv run python -m pytest -m smoke -rs -q                    # everything, about 20 minutes
uv run python -m pytest -m "smoke and not research" -rs -q # qs commands only, about 2 minutes
```

- They need the real local data root (`QUANTSPACE_DATA_ROOT`, otherwise the
  repository `data/`) with the ETF bars named in `tests/smoke/runner.py`; when
  a file is missing they skip and list it.
- They never write to the real data root. A session fixture copies a trimmed
  slice of the needed files into a temporary directory and every command runs
  against that copy; a check compares the source files (path, size, mtime)
  before and after.
- Assertions are sanity checks (exit status, non-empty artifacts, finite
  numbers, weights within budget), not equality pins against real data.
- The course and research reproduction scripts (lesson 06 and 07, the prompt
  tests, the MA-cross report, the ETF18 factor-mining scripts) run unchanged at
  their defaults in `tests/smoke/test_research_scripts.py`, marked `research`.
  They need the full `1d_adj` history of the 18 asset-class ETFs (copied
  untrimmed to the temporary root), run as `python -m <module>` from a temporary
  directory with temporary data and reports roots, and a second guard fails the
  run if the repository `reports/` tree changes. They take almost all of the
  smoke run's 12 to 24 minutes (depending on machine load); the factor-mining
  workflow (screening 19 candidates, then pooling, freezing, and sealed-testing two) takes the longest. The terminal summary lists each script's
  seconds.
- Commands with no suitable local input are listed with a reason in
  `tests/smoke/coverage.py`. A default-suite guard fails when a non-network
  command is neither exercised by a smoke step nor listed there. A command
  that needs an optional dependency (`store query` needs `duckdb`) keeps its
  smoke step and is listed in `OPTIONAL_DEPENDENCY`; the step skips only where
  the module cannot be imported.
- The tests find the `qs` script next to the interpreter (`qs`, or `qs.exe`
  on Windows) and run children with UTF-8 output (`PYTHONUTF8=1`), see
  `tests/fixtures/console.py`.

## Live checks

`tests/live/` runs `live_trade` against the real sources during trading hours:
Sina bars, PandaData, the 14:50 daily path, the minute feeds and workflows, and the
PandaAI client CLI. Like the smoke tests it is skipped unless the `-m` expression
mentions `live`:

```bash
uv run python -m pytest -m live -rs -q        # about 2 minutes
```

Each check skips outside its session (stocks and funds 09:36–11:30 and
13:06–15:00, rebar also 21:06–23:00, today's ETF rotation run 14:51–15:00), without
PandaData credentials, or without the client. Everything runs on a temporary data
root and only previews: nothing is pushed to IM or written to `data/`. Orders go
out only with `QS_LIVE_ORDERS_ACCOUNT=<SimNow account code>`: one hot-rolled coil
contract is opened and closed twice (the order step, then the daily path), which leaves
a rebar strategy on the same account alone.

## Scope

Tests should use synthetic or in-memory data, except the opt-in smoke and live tests. Do not add tests that depend on
private data, credentials, private strategy domains, or external services.

Do not add root-level `tests/test_*.py` files. Add tests under the matching
source boundary instead.
