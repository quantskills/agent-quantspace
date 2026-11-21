---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - A-Share and Index Bars
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# A股与指数行情

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 沪深股票行情数据

### get_stock_daily：获取A股日线数据

数据范围 2000-01-01 ~ 至今；每日更新 16:15 ~ 16:35；[官方页面](https://www.pandaaiquant.com/docs/api?id=156)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期，格式YYYYMMDD，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期，格式YYYYMMDD，与开始日期间不超过5年 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| indicator | Optional[string] | 否 | 股票池，默认为空表示查询所有 |
| st | Optional[boolean] | 否 | 是否包含ST股，默认True表示包含 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 日期 |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| amount | float | 成交额 |
| pre_close | float | 前收盘价 |
| limit_up | float | 涨停价 |
| limit_down | float | 跌停价 |
| name | string | 股票名称 |
| trade_status | integer | 交易状态 |

示例：查询日线行情

```python
import panda_data
result = panda_data.get_stock_daily(
        symbol=["000001.SZ"],
        start_date="20260907",
        end_date="20260911",
        fields=[""]
    )
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | high | low | close | volume | amount | pre_close | limit_up | limit_down | name | trade_status |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20260907 | 11.87 | 11.88 | 11.65 | 11.70 | 108727552.0 | 1.275606e+09 | 11.89 | 13.08 | 10.70 | 平安银行 | 0 |
| 000001.SZ | 20260908 | 11.66 | 11.81 | 11.65 | 11.78 | 74051597.0 | 8.703611e+08 | 11.70 | 12.87 | 10.53 | 平安银行 | 0 |
| 000001.SZ | 20260909 | 11.76 | 11.79 | 11.69 | 11.70 | 58230598.0 | 6.829468e+08 | 11.78 | 12.96 | 10.60 | 平安银行 | 0 |

### get_stock_daily_pre：获取A股前复权日线数据

数据范围 2000-01-04 ~ 至今；每日更新 16:12 ~ 16:52；[官方页面](https://www.pandaaiquant.com/docs/api?id=153)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期,eg:"20250702"，与开始日期间不超过5年 |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| indicator | Optional[string] | 否 | 股票池，参考本文档数据概述部分中的股票池说明，默认为空表示查询所有 |
| st | Optional[bool] | 否 | 是否包含ST股，默认True表示包含。仅在type为stock时有效 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| open | float | 当日开盘价 |
| close | float | 当日收盘价 |
| high | float | 当日最高价 |
| low | float | 当日最低价 |
| volume | float | 当日成交量 |
| pre_close | float | 昨收价 |
| limit_up | float | 当日涨停价 |
| limit_down | float | 当日跌停价 |
| trade_status | integer | 当日是否停牌（0表示当日不停牌） |

示例：获取单支股票的前复权日线

```python
import panda_data
result = panda_data.get_stock_daily_pre(
    symbol=["000001.SZ"],
    start_date="20250101",
    end_date="20250131",
    fields=[],
    indicator="000300",
    st=True
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | high | low | close | volume | pre_close | limit_up | limit_down | name | trade_status |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20250127 | 10.807304 | 10.968749 | 10.807304 | 10.892775 | 115193471.0 | 11.34 | 11.842450 | 9.696184 | 平安银行 | 0 |
| 000001.SZ | 20250124 | 10.750323 | 10.816801 | 10.655356 | 10.769317 | 94494421.0 | 11.32 | 11.823456 | 9.677190 | 平安银行 | 0 |
| 000001.SZ | 20250123 | 10.607872 | 10.826297 | 10.607872 | 10.750323 | 151492027.0 | 11.09 | 11.586038 | 9.477759 | 平安银行 | 0 |

### get_stock_daily_post：获取A股后复权日线数据

数据范围 2000-01-04 ~ 至今；每日更新 16:15 ~ 16:55；[官方页面](https://www.pandaaiquant.com/docs/api?id=152)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期,eg:"20250702"，与开始日期间不超过5年 |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| indicator | Optional[string] | 否 | 股票池，参考本文档数据概述部分中的股票池说明，默认为空表示查询所有 |
| st | Optional[bool] | 否 | 是否包含ST股，默认True表示包含。仅在type为stock时有效 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| open | float | 当日开盘价 |
| close | float | 当日收盘价 |
| high | float | 当日最高价 |
| low | float | 当日最低价 |
| volume | float | 当日成交量 |
| pre_close | float | 昨收价 |
| limit_up | float | 当日涨停价 |
| limit_down | float | 当日跌停价 |
| trade_status | integer | 当日是否停牌（0表示当日不停牌） |

示例：获取单支股票的后复权日线

```python
import panda_data
result = panda_data.get_stock_daily_post(
    symbol=["000001.SZ"],
    start_date="20250101",
    end_date="20250131",
    fields=[],
    indicator="000300",
    st=True
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | high | low | close | volume | pre_close | limit_up | limit_down | name | trade_status |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20250127 | 1923.31104 | 1952.04240 | 1923.31104 | 1938.52176 | 1.388812e+06 | 11.34 | 2107.52976 | 1725.57168 | 平安银行 | 0 |
| 000001.SZ | 20250124 | 1913.17056 | 1925.00112 | 1896.26976 | 1916.55072 | 1.139257e+06 | 11.32 | 2104.14960 | 1722.19152 | 平安银行 | 0 |
| 000001.SZ | 20250123 | 1887.81936 | 1926.69120 | 1887.81936 | 1913.17056 | 1.826439e+06 | 11.09 | 2061.89760 | 1686.69984 | 平安银行 | 0 |

### get_stock_weekly：获取股票周线

数据范围 2000-01-01 ~ 至今；每日更新 周频率更新；[官方页面](https://www.pandaaiquant.com/docs/api?id=352)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期，格式YYYYMMDD，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期，格式YYYYMMDD，与开始日期间不超过5年 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| indicator | Optional[string] | 否 | 股票池，默认为空表示查询所有 |
| st | Optional[boolean] | 否 | 是否包含ST股，默认True表示包含 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 日期，周线为每周最后交易日，月线为每月最后交易日 |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| amount | float | 成交额 |
| pre_close | float | 前收盘价 |
| limit_up | float | 涨停价 |
| limit_down | float | 跌停价 |
| name | string | 股票名称 |
| trade_status | integer | 交易状态 |

示例：查询周线行情

```python
import panda_data
result = panda_data.get_stock_weekly(
        symbol=["000001.SZ"],
        start_date="20260801",
        end_date="20260911",
        fields=[""]
    )
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | open | high | low | close | volume | amount | pre_close | limit_up | limit_down | trade_status |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20260807 | 平安银行 | 11.54 | 11.66 | 11.10 | 11.19 | 572281029.0 | 6.491881e+09 | 11.63 | 0.0 | 0.0 | 0 |
| 000001.SZ | 20260814 | 平安银行 | 11.18 | 11.40 | 11.11 | 11.11 | 377369548.0 | 4.244348e+09 | 11.19 | 0.0 | 0.0 | 0 |
| 000001.SZ | 20260821 | 平安银行 | 11.20 | 11.46 | 11.03 | 11.41 | 521717458.0 | 5.853922e+09 | 11.11 | 0.0 | 0.0 | 0 |

### get_stock_monthly：获取股票月线

数据范围 2000-01-01 ~ 至今；每日更新 月频率更新；[官方页面](https://www.pandaaiquant.com/docs/api?id=353)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期，格式YYYYMMDD，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期，格式YYYYMMDD，与开始日期间不超过5年 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| indicator | Optional[string] | 否 | 股票池，默认为空表示查询所有 |
| st | Optional[boolean] | 否 | 是否包含ST股，默认True表示包含 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 日期，周线为每周最后交易日，月线为每月最后交易日 |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| amount | float | 成交额 |
| pre_close | float | 前收盘价 |
| limit_up | float | 涨停价 |
| limit_down | float | 跌停价 |
| name | string | 股票名称 |
| trade_status | integer | 交易状态 |

示例：查询月线行情

```python
import panda_data
result = panda_data.get_stock_monthly(
        symbol=["000001.SZ"],
        start_date="20260601",
        end_date="20260831",
        fields=[""]
    )
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | open | high | low | close | volume | amount | pre_close | limit_up | limit_down | trade_status |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20260630 | 平安银行 | 10.90 | 11.39 | 10.02 | 10.05 | 2.452489e+09 | 2.655362e+10 | 10.93 | 12.45 | 9.21 | 0 |
| 000001.SZ | 20260731 | 平安银行 | 10.05 | 11.63 | 9.99 | 11.63 | 2.719314e+09 | 2.959919e+10 | 10.05 | 12.77 | 9.05 | 0 |
| 000001.SZ | 20260831 | 平安银行 | 11.54 | 11.77 | 11.03 | 11.72 | 2.079756e+09 | 2.365629e+10 | 11.63 | 12.90 | 9.95 | 0 |

### get_stock_min：获取A股分钟线

数据范围 2000-01-01 ~ 至今；每日更新 15:57 ~ 16:17；[官方页面](https://www.pandaaiquant.com/docs/api?id=159)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| time_zone | Optional[tuple] | 否 | 时间段过滤,格式为("HH:MM", "HH:MM")，例如("10:00", "23:00") |
| frequency | Optional[string] | 否 | 频率, 支持 "1m", "5m", "15m", "60m",默认为"1m" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| minute | string | 时间（精确至分钟） |
| symbol | string | 股票代码 |
| open | float | 当日开盘价 |
| close | float | 当日收盘价 |
| high | float | 当日最高价 |
| low | float | 当日最低价 |
| volume | float | 当日成交量 |
| amount | float | 当日成交额 |
| num_trades | float | 成交笔数 |
| datetime | string | 日期和时间(格式为YYYY-MM-DD hh:mm:ss) |

示例：获取单支股票的1分钟线数据并使用fields

```python
import panda_data
result = panda_data.get_stock_min(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250131",
    fields=["symbol", "date", "num_trades", "amount", "volume"],
    frequency="1m",
    time_zone=("10:00", "11:00")
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | datetime | minute | num_trades | amount | volume |
|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20250102 | 2025-01-02 10:00:00 | 100000 | 190.0 | 2714037.0 | 232100.0 |
| 000001.SZ | 20250102 | 2025-01-02 10:01:00 | 100100 | 296.0 | 4252891.0 | 363902.0 |
| 000001.SZ | 20250102 | 2025-01-02 10:02:00 | 100200 | 729.0 | 18469542.0 | 1581800.0 |

### get_stock_min_pre：获取股票前复权分钟线

数据范围 2016-01-01 ~ 至今；每日更新 16:00 ~ 17:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=351)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期，格式YYYYMMDD |
| end_date | string | 是 | 结束日期，格式YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| time_zone | Optional[Tuple[string, string]] | 否 | 时间段过滤，格式如("09:31", "15:00") |
| frequency | Optional[string] | 否 | 频率，支持"1m"、"5m"、"15m"、"60m"，默认"1m" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 日期，格式YYYYMMDD |
| datetime | string | 时间戳 |
| minute | string | 分钟 |
| open | float | 前复权开盘价 |
| high | float | 前复权最高价 |
| low | float | 前复权最低价 |
| close | float | 前复权收盘价 |
| volume | float | 成交量 |
| amount | float | 成交额 |
| num_trades | float | 成交笔数 |

示例：查询前复权15分钟线

```python
import panda_data
result = panda_data.get_stock_min_pre(
        symbol="000001.SZ",
        start_date="20260911",
        end_date="20260911",
        frequency="15m"
    )
print(result)
```

返回示例（前 3 行）：

| symbol | date | datetime | minute | open | high | low | close | volume | amount | num_trades |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20260911 | 2026-09-11 09:45:00 | 094500 | 11.82 | 11.86 | 11.73 | 11.75 | 16797300.0 | 197822901.0 | 13063.0 |
| 000001.SZ | 20260911 | 2026-09-11 10:00:00 | 100000 | 11.75 | 11.78 | 11.73 | 11.77 | 7579828.0 | 89087912.0 | 8098.0 |
| 000001.SZ | 20260911 | 2026-09-11 10:15:00 | 101500 | 11.77 | 11.81 | 11.76 | 11.78 | 5088305.0 | 59958989.0 | 6429.0 |

### get_stock_min_post：获取股票后复权分钟线

数据范围 2000-01-01 ~ 至今；每日更新 16:27 ~ 16:47；[官方页面](https://www.pandaaiquant.com/docs/api?id=333)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| time_zone | Optional[tuple] | 否 | 时间段过滤,格式为("HH:MM", "HH:MM")，例如("10:00", "23:00") |
| frequency | Optional[string] | 否 | 频率, 支持 "1m", "5m", "15m", "60m",默认为"1m" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| minute | string | 时间（精确至分钟） |
| symbol | string | 股票代码 |
| open | float | 当日开盘价 |
| close | float | 当日收盘价 |
| high | float | 当日最高价 |
| low | float | 当日最低价 |
| volume | float | 当日成交量 |
| amount | float | 当日成交额 |
| num_trades | float | 成交笔数 |
| datetime | string | 日期和时间(格式为YYYY-MM-DD hh:mm:ss) |

示例：示例调用

```python
import panda_data
result = panda_data.get_stock_min_post(
    symbol="000001.SZ",
    start_date="20260701",
    end_date="20260731",
    fields=["symbol", "date", "open", "high", "low", "close", "volume", "amount", "num_trades", "datetime", "minute"],
    time_zone=("09:30", "09:31"),
    frequency="1m"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | high | low | close | volume | amount | num_trades | datetime | minute |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20260701 | 1847.3910 | 1849.2292 | 1840.0382 | 1840.0382 | 38825.0292 | 32298494.0 | 1679.0 | 2026-07-01 09:31:00 | 093100 |
| 000001.SZ | 20260702 | 1874.9640 | 1891.5078 | 1869.4494 | 1884.1550 | 86377.6423 | 73234935.0 | 2982.0 | 2026-07-02 09:31:00 | 093100 |
| 000001.SZ | 20260703 | 1891.5078 | 1900.6988 | 1885.9932 | 1889.6696 | 48648.7634 | 41547318.0 | 1553.0 | 2026-07-03 09:31:00 | 093100 |

### WsTickCN：ws订阅A股逐笔数据（仅包含上交所与深交所数据）

数据范围 实时；[官方页面](https://www.pandaaiquant.com/docs/api?id=294)

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| exchange | string | 交易所，SZ 或 SH |
| open | float | 今开 |
| high | float | 最高价 |
| low | float | 最低价 |
| lastPrice | float | 最新价 |
| volume | float | 成交量 |
| amount | float | 成交额 |
| preClose | float | 昨收 |
| tickTime | string | 行情时间，毫秒时间戳 |
| ask1 ~ ask5 | float | 卖一到卖五价 |
| askVol1 ~ askVol5 | float | 卖一到卖五量 |
| bid1 ~ bid5 | float | 买一到买五价 |
| bidVol1 ~ bidVol5 | float | 买一到买五量 |
| highLimited | float | 涨停价 |
| lowLimited | float | 跌停价 |
| numBrades | integer | 成交笔数 |

示例：示例1

```python
import time
import panda_data
from panda_data import TickStreamClient

panda_data.init_token(username="你的账号", password="你的密码")

# A 股 market=CN，订阅键 tick_CN_000001.SZ，推 Level1 五档
# 盘后、集合竞价外一般只有订阅成功，不会有新 Tick
client = TickStreamClient(market="CN")
client.subscribe_tick("tick_CN_000001.SZ")
# 多只时传列表：client.subscribe_tick(["tick_CN_000001.SZ", "tick_CN_600000.SH"])
# 一次最多订阅 3000 只
# 关闭订阅：client.unsubscribe_tick("tick_CN_000001.SZ")

def on_tick(tick):
    print(tick)

client.listen(handler=on_tick)
time.sleep(30)
client.close()
```

返回示例（前 3 行）：

| {"action": | "subscribed", | "symbols": | ["tick_CN_000001.SZ"]} |
|:---|:---|:---|:---|
| {"code": "000001.SZ", "exchange": "SZ", "open": 11.8, "high": 11.84, "low": 11.57, "lastPrice": 11.7, "volume": 94962632, "amount": 1106652939, "preClose": 11.82, "tickTime": "1789542000000", "ask1": 11.7, "ask2": 11.71, "ask3": 11.72, "ask4": 11.73, "ask5": 11.74, "askVol1": 183500, "askVol2": 131800, "askVol3": 236400, "askVol4": 249900, "askVol5": 345400, "bid1": 11.69, "bid2": 11.68, "bid3": 11.67, "bid4": 11.66, "bid5": 11.65, "bidVol1": 6800, "bidVol2": 166805, "bidVol3": 191631, "bidVol4": 238700, "bidVol5": 289500, "highLimited": 13, "lowLimited": 10.64, "numBrades": 101725} |

## 指数行情（上交所&深交所）

### get_index_daily：获取指数日线

数据范围 2010-01-01 ~ 至今；每日更新 16:12 ~ 16:52；[官方页面](https://www.pandaaiquant.com/docs/api?id=157)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期,eg:"20250702"，与开始日期间不超过5年 |
| symbol | string | 否 | 指数代码 |
| fields | string | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指数代码 |
| date | string | 日期 |
| open | float | 开盘价 |
| close | float | 收盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| volume | float | 成交量 |
| pre_close | float | 昨日结算价 |
| amount | float | 成交额 |

示例：获取单个指数的日线

```python
import panda_data
result = panda_data.get_index_daily(
    symbol=["000001.SH"],
    start_date="20250101",
    end_date="20250131",
    fields=[],
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | amount | close | high | low | open | pre_close | volume |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SH | 20250102 | 603340526739.800049 | 3262.5607 | 3351.722 | 3242.0865 | 3347.9392 | 3351.763 | 56137519900.0 |
| 000001.SH | 20250103 | 523159754706.599976 | 3211.4299 | 3273.5656 | 3205.7755 | 3267.0766 | 3262.5607 | 51759201400.0 |
| 000001.SH | 20250106 | 444188212831.099976 | 3206.9228 | 3219.4877 | 3185.4631 | 3209.7832 | 3211.4299 | 43097840300.0 |

### get_index_min：获取指数分钟线

数据范围 2004-01-01 ~ 至今；每日更新 16:04 ~ 16:24；[官方页面](https://www.pandaaiquant.com/docs/api?id=160)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 指数代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| time_zone | Optional[tuple] | 否 | 时间段过滤,格式为("HH:MM", "HH:MM")，例如("10:00", "23:00") |
| frequency | Optional[string] | 否 | 频率, 支持 "1m", 默认为"1m" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指数代码 |
| date | string | 日期 |
| minute | string | 时间（精确至分钟） |
| open | float | 开盘价 |
| close | float | 收盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| volume | float | 成交量 |
| amount | float | 成交额 |
| trading_date | string | 交易日期 |
| datetime | string | 日期和时间(格式为YYYY-MM-DD hh:mm:ss) |

示例：获取单个指数的1分钟线数据并使用fields

```python
import panda_data
result = panda_data.get_index_min(
    symbol="000001.SH",
    start_date="20250101",
    end_date="20250131",
    fields=["symbol", "date", "amount", "volume"],
    frequency="1m",
    time_zone=("10:00", "11:00")
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | datetime | minute | amount | volume |
|:---|:---|:---|:---|:---|:---|
| 000001.SH | 20250102 | 2025-01-02 10:00:00 | 100000 | 3121189966.799988 | 285190800.0 |
| 000001.SH | 20250102 | 2025-01-02 10:01:00 | 100100 | 3650173236.799988 | 341037500.0 |
| 000001.SH | 20250102 | 2025-01-02 10:02:00 | 100200 | 3287942559.0 | 266980600.0 |
