# Strategy Example Reports

These reports are generated from PandaData daily futures bars saved under `data/market/1d/`. They are compact public examples, not proof of long-term production robustness.

Run `uv run python scripts/run_strategy_reports.py` after refreshing local PandaData Parquet files.

| Strategy | Domain | Type | Start | Sharpe | Total Return | Max Drawdown |
|---|---|---|---:|---:|---:|---:|
| [Futures Cross-Sectional Reversal](futures_cross_sectional_reversal.md) | cross_sectional | Rule-based futures | 2024-01-02 | 1.8864 | 1.1018 | 0.1580 |
| [Futures XGBoost Rank](futures_xgboost_rank.md) | cross_sectional | XGBoost futures | 2024-01-02 | 1.7816 | 0.8015 | 0.1294 |
| [CSI 300 IF MA10 ATR Reversion](csi300_if_ma10_atr_reversion.md) | time_series | Rule-based futures | 2024-01-02 | 1.4765 | 0.7071 | 0.1485 |
| [CSI 300 IF XGBoost Triple-Barrier](csi300_if_xgboost_triple_barrier.md) | time_series | XGBoost futures | 2024-09-24 | 1.2352 | 0.1859 | 0.0372 |
