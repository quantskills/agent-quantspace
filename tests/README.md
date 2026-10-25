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
uv run python -m pytest -m smoke -rs -q
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
- Commands with no suitable local input are listed with a reason in
  `tests/smoke/coverage.py`. A default-suite guard fails when a non-network
  command is neither exercised by a smoke step nor listed there.

## Scope

Tests should use synthetic or in-memory data, except the opt-in smoke tests. Do not add tests that depend on
private data, credentials, private strategy domains, or external services.

Do not add root-level `tests/test_*.py` files. Add tests under the matching
source boundary instead.
