# Private Extension Pattern

Use QuantSpace as the public core. Keep proprietary strategy domains and
research assets in a separate private repository.

## Recommended Layout

```text
workspace/
  quantspace/
  quantspace-private/
```

The private repository can depend on the public one by path during local
development or by package/version in deployed environments.

## Extension Points

- Add private strategy domains under the private repository.
- Add private data adapters outside `skills.ingest`.
- Store private research reports and notebooks only in the private repository.
- Reuse public `skills/` modules instead of copying them.

## Sync Discipline

- Promote generic improvements from private work into QuantSpace.
- Keep private alpha logic, parameter searches, and report artifacts out of the
  public repository.
- Run the public test suite and safety scan before publishing.
