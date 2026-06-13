# Futures Cross-Sectional Reversal

## Summary

- Domain: `cross_sectional`
- Type: Rule-based futures
- Label: none

A non-precious futures rotation example. It ranks stock-index, industrial, agricultural, and energy futures by 120-day moving-average gap reversal strength, then holds the two most stretched contracts with risk-parity weights.

## Performance Chart

![Performance Chart](futures_cross_sectional_reversal_performance.png)

## Metrics

| Metric | Value |
|---|---:|
| `2024_return` | 0.2927 |
| `2025_return` | 0.3453 |
| `2026_return` | 0.2096 |
| `active_day_ratio` | 0.3322 |
| `ann_return` | 0.3555 |
| `ann_volatility` | 0.1884 |
| `avg_daily_turnover` | 0.1992 |
| `calmar_ratio` | 2.2505 |
| `gold_return_corr` | 0.0969 |
| `max_drawdown` | 0.1580 |
| `month_num` | 29.3355 |
| `sharpe_ratio` | 1.8875 |
| `sortino_ratio` | 3.7082 |
| `total_return` | 1.1036 |
| `total_transaction_cost` | 0.0470 |
| `trade_days` | 196.0000 |

## Notes

- Uses PandaData dominant futures daily bars stored under data/market/1d/.
- Precious metals are excluded from the tradable pool so the result is not a disguised gold trend.
- Signal is the negative distance from the 120-day moving average; larger values are more mean-reversion stretched.
- The top two contracts are rebalanced every three trading days with 60-day risk-parity weights.
- Transaction cost assumptions are commission 2bp plus slippage 2bp.

## Recent Result Rows

| Date | return | raw_return | cum_return | drawdown | turnover |
|---|---:|---:|---:|---:|---:|
| 2026-06-08 | -0.0049 | -0.0049 | 1.0936 | -0.0396 | 0.0000 |
| 2026-06-09 | 0.0003 | 0.0003 | 1.0942 | -0.0393 | 0.0000 |
| 2026-06-10 | 0.0063 | 0.0068 | 1.1073 | -0.0333 | 1.2686 |
| 2026-06-11 | -0.0015 | -0.0015 | 1.1041 | -0.0347 | 0.0000 |
| 2026-06-12 | -0.0003 | -0.0003 | 1.1036 | -0.0350 | 0.0000 |
