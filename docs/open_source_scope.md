# Open Source Scope

QuantSpace publishes the workbench architecture and reusable research
building blocks. It intentionally does not publish private strategy research.

## Included

- PandaData/PandaAI ingest wrappers and references.
- Parquet storage through `DataManager`.
- Generic indicators, features, public labels, and factor wrappers.
- Generic analysis, construction, reporting, and research skills.
- Public example strategy domains:
  - `cross_sectional`
  - `time_series`
- Synthetic sample data generation.

## Excluded

- Generated research reports.
- Private strategy domains.
- Private notebooks and research logs.
- Vendor-specific execution adapters outside PandaData.
- Private data caches, credentials, and absolute local paths.
- Private label experiments.

## Release Rule

When syncing code from a private repository, use a whitelist. Do not copy
`reports/`, private strategy domains, private notebooks, or experimental
scripts by default.
