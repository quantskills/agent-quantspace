---
source: user-provided PandaData interface documentation
title: PandaData API - Funds and ETFs
extracted: 2026-07-24
sdk_minimum: 0.0.12
---

# 基金与 ETF 数据

场内 ETF、LOF 属于基金数据。行情必须使用 `get_fund_daily*`，不能使用
`get_stock_daily`、`get_factor`，也不能按
`get_market_data(..., type="stock")` 处理。

## 基金基础信息

### `get_fund_detail`

查询场内和场外基金基础信息。

主要入参：

| 参数 | 类型 | 说明 |
|---|---|---|
| `symbol` | `str \| list[str] \| None` | 基金代码，如 `510300.SH`、`159915.SZ`、`000001.OF` |
| `exchange` | `str \| list[str] \| None` | `SH`、`SZ` 或 `OF` |
| `type` | `str \| list[str] \| None` | 投资对象类型：`E/H/B/SB/M/O` |
| `operation_mode` | `str \| list[str] \| None` | `O` 开放式、`C` 封闭式 |
| `etf_lof_type` | `str \| list[str] \| None` | `ETF`、`LOF` 或 `UN` |
| `is_class_fund` | `int \| list[int] \| None` | 分级基金标志 |
| `index_fund_type` | `str \| list[str] \| None` | `I`、`EI` 或 `UN` |
| `status` | `str \| list[str] \| None` | 上市状态 |
| `fund_status` | `str \| list[str] \| None` | 基金状态 |
| `fields` | `str \| list[str] \| None` | 返回字段子集 |

常用返回字段包括 `symbol`、`name`、`exchange`、`etf_lof_type`、
`status`、`fund_status`、管理人、托管人、跟踪指数和成立/上市日期。

查询全部上市 ETF：

```python
funds = client.get_fund_detail(
    etf_lof_type="ETF",
    status="L",
    fields=["name", "exchange", "management_short_name", "index_symbol"],
)
```

## 场内基金日行情

三个接口共享以下入参：

| 参数 | 类型 | 说明 |
|---|---|---|
| `start_date` | `str` | 必填，`YYYYMMDD` |
| `end_date` | `str` | 必填，`YYYYMMDD` |
| `symbol` | `str \| list[str] \| None` | 场内基金代码 |
| `exchange` | `str \| list[str] \| None` | `SH`、`SZ` |
| `fields` | `str \| list[str] \| None` | 返回字段子集 |

### `get_fund_daily`

未复权场内基金行情。主要字段：

- `symbol`、`date`、`exchange`
- `pre_close`、`open`、`high`、`low`、`close`
- `volume`、`amount`、`change`、`change_rate`
- `discount`、`discount_rate`、`cum_adj_factor`
- `price_limit`、`limit_up`、`limit_down`
- 基金份额相关字段

```python
bars = client.get_fund_daily(
    "20250610",
    "20250613",
    symbol="SHSE.510300",
    fields=["open", "high", "low", "close", "volume", "amount"],
)
```

### `get_fund_daily_pre`

前复权场内基金行情，返回复权后的 OHLC、成交量和成交额。

### `get_fund_daily_post`

后复权场内基金行情，返回复权后的 OHLC、成交量和成交额。

复权接口只调整价格；研究代码应根据策略定义显式选择未复权、前复权或后复权数据。

在 QuantSpace 中，`PandaDataClient` 会把超过 365 个自然日（含首尾）的
`get_fund_daily*` 请求自动切成连续、非重叠的区间，并按请求顺序合并结果。
该保护仅覆盖三类基金日线接口，不适用于以下 ETF 申赎接口。

## ETF 申赎数据

以下接口共享日区间、基金代码、交易所和返回字段参数：

| 接口 | 用途 | 主要返回内容 |
|---|---|---|
| `get_fund_etf_cr_limits` | 申赎限制 | 净值、最小申赎单位、账户及总量限制 |
| `get_fund_etf_cr_net` | 净申赎与资金流 | 份额、规模、净申赎、净流入、净值、收盘价 |
| `get_fund_etf_constituents` | 申赎篮子成分券 | `stock_symbol`、数量、现金替代标志和金额 |
| `get_fund_etf_cr` | 申赎清单 | 跟踪指数、现金差额、最小申赎单位、申赎许可标志 |

这些接口描述 ETF 申购赎回机制，不代替 `get_fund_daily*` 行情接口。

## QuantSpace 数据边界

`PandaDataClient` 只获取数据并转换 `symbol`。持久化前由调用方把 `date`
转换为 timezone-naive `eob`，保留标准 OHLCV 列，然后交给
`skills.store.data_manager.DataManager`。

## SDK 兼容性与实测

- `panda-data==0.0.9` 尚未导出上述基金接口。
- `panda-data==0.0.12` 已导出全部八个接口。
- 使用 `0.0.12` 实测 `510300.SH` 在 `20250610` 至 `20250613` 的
  `get_fund_daily`、`get_fund_daily_pre`、`get_fund_daily_post`，三个接口
  均返回 4 个交易日。
- `get_fund_daily(fields=[...])` 实测自动补齐 `symbol`、`date`，但不补齐
  `exchange`；不指定 `fields` 时返回 `exchange`。调用方不应假定筛选字段后
  一定包含 `exchange`。
