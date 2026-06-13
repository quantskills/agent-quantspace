# CSI 300 IF MA10 ATR Reversion

## Summary

- Domain: `time_series`
- Type: Rule-based futures
- Label: none

A single-instrument time-series rule example that holds CFFEX CSI 300 index futures when price is below its 10-day moving average, with an ATR trailing stop controlling exits.

## Performance Chart

![Performance Chart](csi300_if_ma10_atr_reversion_performance.png)

## Metrics

| Metric | Value |
|---|---:|
| `2024_return` | 0.2356 |
| `2025_return` | 0.3010 |
| `2026_return` | 0.0462 |
| `active_day_ratio` | 0.1390 |
| `ann_return` | 0.2369 |
| `ann_volatility` | 0.1660 |
| `avg_daily_turnover` | 0.1390 |
| `calmar_ratio` | 1.5957 |
| `max_drawdown` | 0.1485 |
| `month_num` | 29.3355 |
| `sharpe_ratio` | 1.4269 |
| `sortino_ratio` | 3.0420 |
| `total_return` | 0.6817 |
| `total_transaction_cost` | 0.0328 |
| `trade_days` | 82.0000 |

## Notes

- Uses PandaData CFFEX.IF99 dominant CSI 300 index futures daily bars stored under data/market/1d/.
- Report window starts on 2024-01-01, matching the local IF parameter sweep window.
- Entry rule: hold IF when close is below MA10.
- Exit rule: leave the position when close falls below the highest price since entry minus 2.0 times ATR(14).
- Transaction cost assumptions are commission 2bp plus slippage 2bp.

## Recent Result Rows

| Date | return | raw_return | cum_return | drawdown | turnover |
|---|---:|---:|---:|---:|---:|
| 2026-06-08 | -0.0004 | 0.0000 | 0.6516 | -0.0453 | 1.0000 |
| 2026-06-09 | 0.0126 | 0.0130 | 0.6725 | -0.0332 | 1.0000 |
| 2026-06-10 | -0.0047 | -0.0047 | 0.6646 | -0.0377 | 0.0000 |
| 2026-06-11 | -0.0059 | -0.0059 | 0.6548 | -0.0434 | 0.0000 |
| 2026-06-12 | 0.0163 | 0.0163 | 0.6817 | -0.0279 | 0.0000 |
