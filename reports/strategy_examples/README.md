# Strategy Example Reports

These reports are generated from PandaData daily listed-fund and futures bars saved under `data/market/1d/`. They are compact public examples, not proof of long-term production robustness.

Run `uv run python -m scripts.run_strategy_reports` after refreshing local PandaData Parquet files.

| Strategy | Domain | Type | Start | Sharpe | Total Return | Max Drawdown |
|---|---|---|---:|---:|---:|---:|
| [Futures Cross-Sectional Reversal](futures_cross_sectional_reversal.md) | cross_sectional | Rule-based futures | 2024-01-02 | 1.9735 | 1.1722 | 0.1659 |
| [Futures XGBoost Rank](futures_xgboost_rank.md) | cross_sectional | XGBoost futures | 2024-01-02 | 1.9847 | 1.0539 | 0.1461 |
| [Global Asset ETF Top 3 Momentum Rotation](global_asset_etf_top3.md) | cross_sectional | Rule-based listed-fund rotation | 2021-01-04 | 0.2832 | 0.3208 | 0.2352 |
| [CSI 300 IF MA10 ATR Reversion](csi300_if_ma10_atr_reversion.md) | time_series | Rule-based futures | 2024-01-02 | 1.3671 | 0.6477 | 0.1631 |
| [CSI 300 IF XGBoost Triple-Barrier](csi300_if_xgboost_triple_barrier.md) | time_series | XGBoost futures | 2024-09-13 | 0.3083 | 0.0541 | 0.1037 |
