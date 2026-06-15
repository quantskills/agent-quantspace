# Strategies

[中文说明](README-zh.md)

This directory contains public strategy domains. A strategy domain is a focused
example workflow that composes reusable skills into a complete research path.

## Public Domains

- `cross_sectional/`: cross-sectional rotation using generic factors, rule
  weights, XGBoost rank weights, and the shared vectorized backtester.
- `time_series/`: single-instrument workflow using raw OHLCV bars, public
  features, triple-barrier labels, rule/ML weights, and the shared vectorized backtester.

## Boundary

Strategy domains should contain strategy-specific rules, feature sets,
signal-to-weight mapping, and data contracts. Reusable storage, analysis,
backtesting, ML, and reporting belongs in `skills/`.

Private strategy domains should live in a separate private repository.
