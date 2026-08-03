# Data

[English README](README.md)

这个目录是 QuantSpace 默认的本地数据根目录。

市场数据、计算后的因子、模型文件、回测输出和导出文件都属于本地产物，默认会被 Git 忽略。

品种集合不存放在数据目录中；策略或调用方应显式传递 symbol 列表。

## 本地产物布局

```text
data/
  market/{frequency}/{symbol}.parquet
  adj_factor/{symbol}.parquet
  factors/{namespace}/
  factor_test/{namespace}/
  correlation/
  backtest/
  models/
  export/
```

如果希望把数据放到仓库之外，可以设置 `QUANTSPACE_DATA_ROOT`。
