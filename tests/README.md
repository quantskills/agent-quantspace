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
tests/skills/research/
tests/skills/store/
```

There are no `tests/skills/construct/` or `tests/skills/model/` directories;
portfolio construction is covered under `backtest`, and model helpers are
covered under `ml`.

## Run

```bash
uv run python -m pytest tests/
uv run python -m pytest tests/skills tests/strategies -q
uv run python -m pytest tests/contracts tests/regression tests/docs -q
```

## Scope

Tests should use synthetic or in-memory data. Do not add tests that depend on
private data, credentials, private strategy domains, or external services.

Do not add root-level `tests/test_*.py` files. Add tests under the matching
source boundary instead.
