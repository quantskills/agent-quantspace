---
name: report
description: Write complete HTML research reports (nine fixed sections plus a catalog), render PNG charts from result tables, and list existing studies with `uv run qs report ...`.
---

# Report

Use the `uv run qs report` commands below; reporting tasks do not require
reading `skills/report/` source. Each command prints one JSON envelope on
stdout (`ok`, `data`, `artifacts`, `warnings`, or `error` with a `hint`).
Exact options: `uv run qs report <command> --help` or
`uv run qs schema report.<command>`. Install with `uv sync --extra report`.

## When to use

- Archive a finished study as a self-contained HTML report.
- Render an equity curve, factor ranking, IC heatmap, or IC term-structure chart.
- List the studies under the reports directory or rebuild the catalog page.

## Workflow

```bash
uv run qs report chart --kind equity-curve --table out/run/result.parquet \
  --column return --output out/equity.png
uv run qs report bundle --print-template          # the fields of study.json
uv run qs report bundle --input-json study.json --catalog
uv run qs report list
uv run qs report catalog
```

`study.json` holds the report fields (namespace, slug, title, question,
hypothesis, execution, metrics, figures, caveats, and so on).
`uv run qs schema report.bundle` describes each one.

## Files

Reports go under `QUANTSPACE_REPORTS_ROOT`, otherwise the workspace `reports/`
directory:

```text
reports/<namespace>/<slug>/index.html
reports/<namespace>/<slug>/params.json
reports/<namespace>/<slug>/artifacts/metrics.csv   # only when metrics is non-empty
reports/catalog.html
reports/catalog.json
```

`index.html` is the nine-section report: 研究问题, 数据与样本, 假设与方法,
执行约定, 证据与指标, 图表, 对照与稳健性, 限制与下一步, 复现与产物. Without
comparison or robustness evidence, section 7 still renders `本报告未做`.
`params.json` is the catalog sidecar; `list` only counts folders that hold both
files. `bundle` updates the catalog only with `--catalog`.

## Rules

Complete research archives are HTML only: no Markdown, PDF, or database. Other
Skills return objects or tables and never write HTML.

`bundle` only renders the fields it is given. Before filling them, read the
strategy implementation, the data, and the actual backtest results:

- State a testable `question`. Write a distinct `hypothesis`: why the signal
  might work, what it predicts, and how positions are opened, sized, and
  closed. Implementation details go to `method_notes`.
- Interpret the actual metrics against their sample and trading activity. Name
  specific weaknesses, missing comparisons, and possible confounders in
  `caveats`; put concrete tests that could challenge the explanation in
  `next_steps`. Do not present a hypothesized mechanism as a proven source of
  return.
- Keep the regeneration command in `reproduce_command` only.
- If a saved report came from an older strategy version, interpret its recorded
  method and results, and reconcile the version difference before claiming
  that current code reproduces the numbers.

Hard rules:

- Fill `metrics` from a backtest result (`metrics.json`), CSV, or JSON. Never
  invent a number. `metrics_source` is required.
- `namespace` and `slug` are safe path segments only.
- `visibility` is `private` unless publishing a public example; do not git-add
  private studies. Public examples use `namespace="strategy_examples"`,
  `visibility="public_example"`, and `kind="public_example"`.

## References

- [references/python-api.md](references/python-api.md): `ResearchReport` and
  `write_research_bundle`, the dashboard renderer, the chart functions, CJK
  fonts, Windows path rules, and template conventions. Read it when changing
  this Skill or building a report from Python.

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Before using a command, run it with `--help` to see its options and defaults. `uv run qs schema <skill>.<command>` shows its input and output fields; add `--file-field FIELD` for the structure of an option that takes a JSON file.

| Command | What it does | Side effects |
|---|---|---|
| `uv run qs report list` | List research studies that have index.html and params.json. | read-only |
| `uv run qs report bundle` | Write a nine-section HTML research archive with write_research_bundle. | writes-output |
| `uv run qs report catalog` | Rewrite catalog.html and catalog.json under the reports root. | writes-output |
| `uv run qs report chart` | Render one skills.report.charts PNG from a table. | writes-output |

<!-- END GENERATED: qs commands -->
