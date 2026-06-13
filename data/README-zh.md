# Data

[English README](README.md)

这个目录是 QuantSpace 默认的本地数据根目录。

这里应该只提交小型元数据。市场数据、计算后的因子、模型文件、回测输出和导出文件都属于本地产物，默认会被 Git 忽略。

## 已提交内容

- `pools/*.json`：demo 和测试使用的小型 sample pool 定义。
- `README.md` 和 `README-zh.md`：数据布局说明。

## 本地产物布局

```text
data/
  market/{frequency}/{symbol}.parquet
  adj_factor/{symbol}.parquet
  pools/{pool_id}.json
  factors/{pool_id}/
  factor_test/{pool_id}/
  correlation/
  backtest/
  models/
  export/
```

如果希望把数据放到仓库之外，可以设置 `QUANTSPACE_DATA_ROOT`。
