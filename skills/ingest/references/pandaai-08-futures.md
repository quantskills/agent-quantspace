---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - Futures Bars, Contracts and Dominant Contracts
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# 期货行情、合约与主力

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 期货行情数据

### get_future_daily：获取期货日线

数据范围 2000-01-01 ~ 至今；每日更新 16:12 ~ 16:52；[官方页面](https://www.pandaaiquant.com/docs/api?id=158)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期,eg:"20250702"，与开始日期间不超过5年 |
| symbol | Optional[Union[string, List[string]]] | 否 | 期货代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 期货代码 |
| dominant_id | string | 主力合约代码 |
| exchange | string | 交易所 |
| trading_code | string | 交易代码 |
| underlying_symbol | string | 期货品种 |
| open | float | 当日开盘价 |
| close | float | 当日收盘价 |
| high | float | 当日最高价 |
| low | float | 当日最低价 |
| volume | float | 当日成交量 |
| day_session_open | float | 日盘开盘价 |
| limit_up | float | 当日涨停价 |
| limit_down | float | 当日跌停价 |
| amount | float | 当日成交额 |
| open_interest | float | 累计持仓量 |
| settlement | float | 结算价 |
| pre_settlement | float | 昨日结算价 |

示例：获取单个期货的日线

```python
import panda_data
result = panda_data.get_future_daily(
    symbol=["A_DOMINANT.DCE"],
    start_date="20250101",
    end_date="20250131",
    fields=[],
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | close | day_session_open | dominant_id | exchange | high | limit_down | limit_up | low | open | open_interest | pre_settlement | settlement | trading_code | underlying_symbol | volume | amount |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| A_DOMINANT.DCE | 20250102 | 3931.0 | 3929.0 | A2505 | DCE | 3962.0 | 3703.0 | 4175.0 | 3920.0 | 3929.0 | 183331.0 | 3939.0 | 3938.0 | a2505 | A | 86643.0 | 3412603470.0 |
| A_DOMINANT.DCE | 20250103 | 3917.0 | 3935.0 | A2505 | DCE | 3944.0 | 3702.0 | 4174.0 | 3909.0 | 3942.0 | 180381.0 | 3938.0 | 3928.0 | a2505 | A | 104354.0 | 4099406950.0 |
| A_DOMINANT.DCE | 20250106 | 3892.0 | 3885.0 | A2505 | DCE | 3919.0 | 3693.0 | 4163.0 | 3873.0 | 3910.0 | 176065.0 | 3928.0 | 3895.0 | a2505 | A | 152269.0 | 5931398210.0 |

### get_future_min：获取期货分钟线

数据范围 2010-01-01 ~ 至今；每日更新 16:41 ~ 17:01；[官方页面](https://www.pandaaiquant.com/docs/api?id=161)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 指数代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| time_zone | Optional[tuple] | 否 | 时间段过滤,格式为("HH:MM", "HH:MM")，例如("10:00", "23:00") |
| frequency | Optional[string] | 否 | 频率, 支持 "1m", "5m", "15m", "60m",默认为"1m" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| minute | string | 时间（精确至分钟） |
| datetime | string | 日期和时间(格式为YYYY-MM-DD hh:mm:ss) |
| symbol | string | 期货代码 |
| dominant_id | string | 主力合约代码 |
| exchange | string | 交易所 |
| trading_code | string | 交易代码 |
| underlying_symbol | string | 期货品种 |
| trading_date | string | 交易日期 |
| open | float | 当日开盘价 |
| close | float | 当日收盘价 |
| high | float | 当日最高价 |
| low | float | 当日最低价 |
| volume | float | 当日成交量 |
| open_interest | float | 累计持仓量 |
| amount | float | 当日成交额 |
| turnover | float | 换手率 |

示例：获取单个期货的1分钟线数据并使用fields

```python
import panda_data
result = panda_data.get_future_min(
    symbol="A2501.DCE",
    start_date="20250101",
    end_date="20250131",
    fields=["symbol", "date",  "amount", "volume"],
    frequency="1m",
    time_zone=("10:00", "11:00")
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | datetime | minute | trading_date | amount | volume |
|:---|:---|:---|:---|:---|:---|:---|
| A2501.DCE | 20250102 | 2025-01-02 10:00:00 | 100000 | 20250102 | 383000.0 | 10.0 |
| A2501.DCE | 20250102 | 2025-01-02 10:01:00 | 100100 | 20250102 | 0.0 | 0.0 |
| A2501.DCE | 20250102 | 2025-01-02 10:02:00 | 100200 | 20250102 | 191500.0 | 5.0 |

### get_future_daily_post：获取期货后复权数据

数据范围 2010-01-04 ~ 至今；每日更新 16:17 ~ 16:37；[官方页面](https://www.pandaaiquant.com/docs/api?id=29)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 品种编码，如 "A"；可传单个或列表，为空则不按品种过滤 |
| start_date | string | 是 | 开始日期，eg:"20260601" |
| end_date | string | 是 | 结束日期，eg:"20260610" |
| method | string | 否 | 复权方法，默认 "close_pcs"；可选 close_pcs（前一日收盘价价差复权）；close_os（当日开盘价价差复权）；close_pcr（前一日收盘价比例复权）；close_or（当日开盘价比例复权） |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段子集，自动补齐 symbol,date,dominant_id |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 合约代码（如 A_DOMINANT.DCE） |
| date | string | 交易日期 YYYYMMDD |
| underlying_symbol | string | 品种编码 |
| exchange | string | 交易所（3 位代码） |
| dominant_id | string | 主力合约代码（如 CF509.CZC） |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| open_interest | float | 持仓量 |
| amount | float | 成交额 |
| settlement | float | 结算价 |
| pre_settlement | float | 昨结算价 |
| limit_up | float | 涨停价 |
| limit_down | float | 跌停价 |
| day_session_open | float | 日盘开盘价 |
| method | string | 复权方法，分别为close_pcs（前一日收盘价价差复权）；close_os（当日开盘价价差复权）；close_pcr（前一日收盘价比例复权）；close_or（当日开盘价比例复权） |

示例：按品种编码获取期货主力连续合约后复权日线行情

```python
import panda_data
result = panda_data.get_future_daily_post(
    underlying_symbol="CF",
    start_date="20150901",
    end_date="20150910",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | dominant_id | underlying_symbol | exchange | open | high | low | close | volume | open_interest | amount | settlement | pre_settlement | limit_up | limit_down | day_session_open | method |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| CF_DOMINANT.CZC | 20150910 | CF601.CZC | CF | CZC | 6955.0 | 7015.0 | 6905.0 | 6990.0 | 102724.0 | 346364.0 | 0 | 6965.0 | 6945.0 | 7450.0 | 6440.0 | 6930.0 | close_pcs |
| CF_DOMINANT.CZC | 20150909 | CF601.CZC | CF | CZC | 6905.0 | 6990.0 | 6890.0 | 6945.0 | 121288.0 | 344630.0 | 0 | 6945.0 | 6870.0 | 7370.0 | 6370.0 | 6960.0 | close_pcs |
| CF_DOMINANT.CZC | 20150908 | CF601.CZC | CF | CZC | 6920.0 | 6920.0 | 6825.0 | 6880.0 | 65476.0 | 340754.0 | 0 | 6870.0 | 6920.0 | 7425.0 | 6415.0 | 6885.0 | close_pcs |

示例：指定复权方法查询某品种的期货主力连续合约后复权收盘价

```python
import panda_data
result = panda_data.get_future_daily_post(
    underlying_symbol="A",
    start_date="20260601",
    end_date="20260610",
    method="close_os",
    fields=["close", "method"],
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | dominant_id | close | method |
|:---|:---|:---|:---|:---|
| A_DOMINANT.DCE | 20260610 | A2607.DCE | 5649.0 | close_os |
| A_DOMINANT.DCE | 20260609 | A2607.DCE | 5582.0 | close_os |
| A_DOMINANT.DCE | 20260608 | A2607.DCE | 5655.0 | close_os |

### WsTickFuture：ws订阅期货逐笔数据（包含上海期货交易所、广州期货交易所、上海国际能源交易中心、大连商品交易所、郑州商品交易所、	中国金融期货交易所）

数据范围 实时；[官方页面](https://www.pandaaiquant.com/docs/api?id=295)

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| exchange | string | 交易所，SHF / DCE / CZC / CFE / INE / GFE |
| underlyingSymbol | string | 品种代码，如 RB、SA、IF |
| open | float | 今开 |
| high | float | 最高价 |
| low | float | 最低价 |
| lastPrice | float | 最新价 |
| volume | float | 成交量 |
| amount | float | 成交额 |
| preClose | float | 昨收 |
| openInterest | float | 持仓量 |
| priceDifference | float | 涨跌额 |
| priceChangeRatio | float | 涨跌幅 |
| preSettlement | float | 昨结 |
| tickTime | string | 行情时间，毫秒时间戳 |
| ask1 | float | 卖一价 |
| askVol1 | float | 卖一量 |
| bid1 | float | 买一价 |
| bidVol1 | float | 买一量 |
| highLimited | float | 涨停价 |
| lowLimited | float | 跌停价 |

示例：示例1

```python
import time
import panda_data
from panda_data import TickStreamClient

panda_data.init_token(username="你的账号", password="你的密码")

# 期货 market=FUTURE，订阅键 tick_FUT_RB2701.SHF，只有一档买卖盘
# 交易所后缀 SHF / DCE / CZC / CFE / INE / GFE；郑商所合约写 4 位年月，如 SA2609.CZC
# 夜盘没开时，一般只有订阅成功，不会有新 Tick
client = TickStreamClient(market="FUTURE")
client.subscribe_tick("tick_FUT_RB2701.SHF")
# 多只时传列表：client.subscribe_tick(["tick_FUT_RB2701.SHF", "tick_FUT_SA2609.CZC", "tick_FUT_IF2609.CFE"])
# 一次最多订阅 3000 只
# 关闭订阅：client.unsubscribe_tick("tick_FUT_RB2701.SHF")

def on_tick(tick):
    print(tick)

client.listen(handler=on_tick)
time.sleep(30)
client.close()
```

返回示例（前 3 行）：

| {"action": | "subscribed", | "symbols": | ["tick_FUT_RB2701.SHF"]} |
|:---|:---|:---|:---|
| {"code": "RB2701.SHF", "exchange": "SHF", "underlyingSymbol": "RB", "open": 3200.0, "high": 3221.0, "low": 3195.0, "lastPrice": 3210.0, "volume": 123456, "amount": 3950000000.0, "preClose": 3205.0, "openInterest": 890123, "priceDifference": 5.0, "priceChangeRatio": 0.00156, "preSettlement": 3208.0, "tickTime": "1754352000123", "ask1": 3211.0, "askVol1": 12, "bid1": 3210.0, "bidVol1": 20, "highLimited": 3525.0, "lowLimited": 2885.0} |

## 期货基本信息

### get_future_detail：获取期货基本信息

数据范围 1999-01-04 ~ 至今；每日更新 08:34 ~ 08:54；[官方页面](https://www.pandaaiquant.com/docs/api?id=357)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期货代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| exchange | Optional[Union[string, List[string]]] | 否 | 期货交易所后缀 |
| date | Optional[string] | 否 | 查询日期，支持YYYYMMDD为空时返回最新可交易期货列表；传入历史日期时返回该日可交易的合约 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 期货代码 |
| underlying_symbol | string | 合约标的名称 |
| market_tplus | float | 交易制度 |
| name | string | 合约简称 |
| margin_rate | float | 最低保证金率 |
| maturity_date | string | 到期日期 |
| type | string | 合约类型 |
| trading_code | string | 交易代码 |
| exchange | string | 交易所 |
| product | string | 合约种类 |
| contract_multiplier | float | 合约乘数 |
| round_lot | float | 合约单位 |
| trading_hours | string | 交易时间 |
| listed_date | string | 上市日期 |
| industry_name | string | 行业分类名称 |
| de_listed_date | string | 退市日期 |
| start_delivery_date | string | 开始交割日期 |
| end_delivery_date | string | 结束交割日期 |
| is_trading | integer | 是否可交易 |

示例：查询历史日期的可交易期货列表

```python
import panda_data
result = panda_data.get_future_detail(
        symbol=["A2401.DCE", "ZN_DOMINANT.SHF"],
        fields=[""],
        date="20240601"
    )
print(result)
```

返回示例（前 3 行）：

| symbol | underlying_symbol | market_tplus | name | margin_rate | maturity_date | type | trading_code | exchange | product | contract_multiplier | round_lot | trading_hours | listed_date | industry_name | de_listed_date | start_delivery_date | end_delivery_date | is_trading |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| ZN_DOMINANT.SHF | ZN | 0.0 | zn主力连续 | 0.09 | 0000-00-00 | Future | ZN2611 | SHF | Commodity | 5.0 | 1.0 | 21:01-01:00,09:01-10:15,10:31-11:30,13:31-15:00 | 0000-00-00 | 有色 | 0000-00-00 | 0000-00-00 | 0000-00-00 | 1 |

### get_future_detail_all：获取期货基本信息

数据范围 1999-01-04 ~ 至今；每日更新 08:34 ~ 08:54；[官方页面](https://www.pandaaiquant.com/docs/api?id=28)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期货代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| exchange | Optional[Union[string, List[string]]] | 否 | 期货交易所后缀 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 期货代码 |
| underlying_symbol | string | 合约标的名称 |
| market_tplus | float | 交易制度 |
| name | string | 合约简称 |
| margin_rate | float | 最低保证金率 |
| maturity_date | string | 到期日期 |
| type | string | 合约类型 |
| trading_code | string | 交易代码 |
| exchange | string | 交易所 |
| product | string | 合约种类 |
| contract_multiplier | float | 合约乘数 |
| round_lot | float | 合约单位 |
| trading_hours | string | 交易时间 |
| listed_date | string | 上市日期 |
| industry_name | string | 行业分类名称 |
| de_listed_date | string | 退市日期 |
| start_delivery_date | string | 开始交割日期 |
| end_delivery_date | string | 结束交割日期 |
| is_trading | integer | 是否可交易 |

示例：查询全状态最新期货列表

```python
import panda_data
result = panda_data.get_future_detail_all(
        symbol=["A2401.DCE", "ZN_DOMINANT.SHF"],
        fields=[""]
    )
print(result)
```

返回示例（前 3 行）：

| symbol | underlying_symbol | market_tplus | name | margin_rate | maturity_date | type | trading_code | exchange | product | contract_multiplier | round_lot | trading_hours | listed_date | industry_name | de_listed_date | start_delivery_date | end_delivery_date | is_trading |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| A2401.DCE | A | 0.0 | 豆一2401 | 0.20 | 2024-01-15 | Future | a2401 | DCE | Commodity | 10.0 | 1.0 | 21:01-23:00,09:01-10:15,10:31-11:30,13:31-15:00 | 2023-01-17 | 油脂 | 2024-01-15 | 2024-01-18 | 2024-01-18 | 0 |
| ZN_DOMINANT.SHF | ZN | 0.0 | zn主力连续 | 0.09 | 0000-00-00 | Future | ZN2611 | SHF | Commodity | 5.0 | 1.0 | 21:01-01:00,09:01-10:15,10:31-11:30,13:31-15:00 | 0000-00-00 | 有色 | 0000-00-00 | 0000-00-00 | 0000-00-00 | 1 |

## 期货主力合约信息

### get_future_dominant：获取期货主力合约数据

数据范围 2000-01-05 ~ 至今；每日更新 17:35 ~ 17:55；[官方页面](https://www.pandaaiquant.com/docs/api?id=58)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| underlying_symbol | string | 期货品种 |
| symbol | string | 主力合约代码 |
| trading_code | string | 主力合约期货交易代码 |

示例：获取一定日期内某些品种的主力合约

```python
import panda_data
result = panda_data.get_future_dominant(
    underlying_symbol=["A","AG"],
    start_date="20250701",
    end_date="20250710"
)
print(result)
```

返回示例（前 3 行）：

| underlying_symbol | date | symbol | trading_code |
|:---|:---|:---|:---|
| A | 20250701 | A2509.DCE | a2509 |
| A | 20250702 | A2509.DCE | a2509 |
| A | 20250703 | A2509.DCE | a2509 |
