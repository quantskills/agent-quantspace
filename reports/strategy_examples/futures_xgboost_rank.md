# Futures XGBoost Rank

## Summary

- Domain: `cross_sectional`
- Type: XGBoost futures
- Label: rank label

A real-data cross-sectional ML example. XGBoost predicts each future's forward-return rank label and allocates to the top two predicted ranks with risk-parity weights.

## Performance Chart

![Performance Chart](futures_xgboost_rank_performance.png)

## Metrics

| Metric | Value |
|---|---:|
| `2024_return` | 0.1995 |
| `2025_return` | 0.4118 |
| `2026_return` | 0.1406 |
| `active_day_ratio` | 0.9015 |
| `ann_return` | 0.3094 |
| `ann_volatility` | 0.1281 |
| `avg_daily_turnover` | 0.1918 |
| `calmar_ratio` | 3.3227 |
| `max_drawdown` | 0.0931 |
| `month_num` | 29.3032 |
| `sharpe_ratio` | 2.4163 |
| `sortino_ratio` | 4.2368 |
| `total_return` | 0.9315 |
| `total_transaction_cost` | 0.0452 |
| `trade_days` | 531.0000 |

## Notes

- Label is the percentile rank of 60-day forward return within the real futures pool.
- Features are generic public momentum, volatility, trend, and mean-reversion factors.
- Training uses rows before 2024-01-01; reports show the held-out period.
- Weights are run through the shared vectorized VectorBacktester.

## Recent Result Rows

| Date | return | raw_return | cum_return | drawdown | turnover |
|---|---:|---:|---:|---:|---:|
| 2026-06-08 | 0.0000 | 0.0000 | 0.9315 | -0.0244 | 0.0000 |
| 2026-06-09 | 0.0000 | 0.0000 | 0.9315 | -0.0244 | 0.0000 |
| 2026-06-10 | 0.0000 | 0.0000 | 0.9315 | -0.0244 | 0.0000 |
| 2026-06-11 | 0.0000 | 0.0000 | 0.9315 | -0.0244 | 0.0000 |
| 2026-06-12 | 0.0000 | 0.0000 | 0.9315 | -0.0244 | 0.0000 |
