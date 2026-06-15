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
| `2024_return` | 0.1866 |
| `2025_return` | 0.4572 |
| `2026_return` | 0.0419 |
| `active_day_ratio` | 1.0000 |
| `ann_return` | 0.2726 |
| `ann_volatility` | 0.1530 |
| `avg_daily_turnover` | 0.2514 |
| `calmar_ratio` | 2.1069 |
| `max_drawdown` | 0.1294 |
| `month_num` | 29.3022 |
| `sharpe_ratio` | 1.7816 |
| `sortino_ratio` | 2.8499 |
| `total_return` | 0.8015 |
| `total_transaction_cost` | 0.0592 |
| `trade_days` | 589.0000 |

## Notes

- Label is the percentile rank of 60-day forward return within the real futures pool.
- Features are generic public momentum, volatility, trend, and mean-reversion factors.
- Training uses rows before 2024-01-01; reports show the held-out period.
- Weights are run through the shared vectorized VectorBacktester with zero signal lag and forward close-to-close returns.

## Recent Result Rows

| Date | return | raw_return | cum_return | drawdown | turnover |
|---|---:|---:|---:|---:|---:|
| 2026-06-05 | -0.0246 | -0.0246 | 0.7855 | -0.0976 | 0.0020 |
| 2026-06-08 | 0.0074 | 0.0075 | 0.7988 | -0.0908 | 0.0040 |
| 2026-06-09 | -0.0153 | -0.0153 | 0.7712 | -0.1048 | 0.0001 |
| 2026-06-10 | 0.0025 | 0.0031 | 0.7756 | -0.1026 | 1.5541 |
| 2026-06-11 | 0.0146 | 0.0146 | 0.8015 | -0.0895 | 0.0041 |
