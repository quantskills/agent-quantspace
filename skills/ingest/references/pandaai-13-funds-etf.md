---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - Funds and ETFs
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# 基金与ETF

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 基金基础数据

### get_fund_detail：获取基金基本信息

数据范围 1998-04-07 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=269)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 基金代码 |
| exchange | Optional[Union[str, List[str]]] | 否 | 交易市场(SZ:深交所；SH:上交所；OF:场外基金) |
| type | Optional[Union[str, List[str]]] | 否 | 按投资对象分基金类型（E：股票型，H：混合型，B：债券型，SB：短期理财债券，M：货币型，O：其他） |
| operation_mode | Optional[Union[str, List[str]]] | 否 | 基金运作模式（O：开放式，C：封闭式） |
| etf_lof_type | Optional[Union[str, List[str]]] | 否 | ETF或LOF型基金（ETF、LOF、UN(非ETF或LOF型基金)） |
| is_class_fund | Optional[Union[int, List[int]]] | 否 | 是否分级基金（1：母基金，2：子基金A，3：子基金B，0：否。） |
| index_fund_type | Optional[Union[str, List[str]]] | 否 | 基金指数型属性（I：指数型，EI：指数增强型，UN：非指数型基金） |
| status | Optional[Union[str, List[str]]] | 否 | 上市状态（L：上市；S：暂停；DE：终止上市；UN：未上市） |
| fund_status | Optional[Union[str, List[str]]] | 否 | 基金状态(A:存续中，E:已到期，UN:未成立) |
| fields | Optional[Union[str, List[str]]] | 否 | 返回字段 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 基金代码 |
| name | str | 基金中文简称 |
| trade_name | str | 交易简称 |
| full_name | str | 基金中文全称 |
| exchange | str | 交易市场 |
| type | str | 按投资对象分基金类型（E：股票型，H：混合型，B：债券型，SB：短期理财债券，M：货币型，O：其他） |
| operation_mode | str | 基金运作模式（O：开放式，C：封闭式） |
| index_fund_type | str | 基金指数型属性（I：指数型，EI：指数增强型，UN：非指数基金） |
| etf_lof_type | str | ETF或LOF型基金（ETF、LOF、UN(非ETF或LOF型基金)） |
| status | str | 上市状态（L：上市；S：暂停；DE：终止上市；UN：未上市） |
| fund_status | str | 基金状态(A:存续中，E:已到期，UN:未成立) |
| is_qdii_fund | int | 是否为QDII基金（1：是，0：否） |
| is_fof_fund | int | 是否为FOF基金(1：是，0：否） |
| is_guaranteed_fund | int | 是否为保本基金(1：是，0：否） |
| guarantee_period | double | 保本周期(月) |
| guarantee_ratio | double | 保本比例(%) |
| found_date | str | 基金成立日期 |
| listed_date | str | 上市日期 |
| delisted_date | str | 终止上市日期 |
| due_date | str | 到期日 |
| management | str | 基金经理 |
| management_institution | str | 基金管理人中文全称 |
| custodian_institution | str | 基金托管人中文全称 |
| management_short_name | str | 基金管理人中文简称 |
| custodian_short_name | str | 基金托管人中文简称 |
| investment_field | str | 投资领域 |
| investment_objective | str | 投资目标 |
| strategy | str | 投资策略 |
| philosophy | str | 投资理念 |
| mode | str | 基金管理方式 |
| is_mom_fund | int | 是否MOM(1：是，0：否） |
| dividend_policy | str | 分红政策 |
| risk_return_profile | str | 风险收益特征 |
| benchmark | str | 业绩比较基准 |
| index_symbol | str | 指数代码 |
| index_name | str | 指数简称 |
| is_class_fund | int | 是否分级基金(1:母基金，2:子基金A，3:子基金B，0：否) |
| class_name | str | 分级名称 |
| primary_fund_symbol | str | 基金主代码 |
| subscription_redemption_symbol | str | 场内申赎代码 |
| exchange_short_name | str | 场内简称 |
| front_subscription_symbol | str | 前端申购代码 |
| back_subscription_symbol | str | 后端申购代码 |
| subscription_symbol | str | 认购代码 |
| circulating_shares | double | 最新流通份额 |
| clearing_speed | int | 清算速度 |
| market_tplus | str | 交易制度，“T+0”表示 T+0，“T+1”表示 T+1，往后顺推 |
| security_id | string | 内部证券ID |

示例：获取上市的基金

```python
import panda_data
result = panda_data.get_fund_detail(
    status="L",
    fields=['symbol','name','exchange','type','etf_lof_type']
)
print(result)
```

返回示例（前 3 行）：

| symbol | exchange | type | name | etf_lof_type |
|:---|:---|:---|:---|:---|
| 158000.SZ | SZ | E | 鹏华中证港股通内地金融ETF | ETF |
| 158003.SZ | SZ | E | 嘉实中证港股通医疗主题ETF | ETF |
| 158005.SZ | SZ | E | 博时中证工程机械主题ETF | ETF |

## 基金行情数据

### get_fund_daily：获取场内基金日行情数据（只有场内基金数据）

数据范围 2000-01-04 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=271)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期（交易日期），格式 YYYYMMDD |
| end_date | string | 是 | 结束日期（交易日期），格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| exchange | string | 交易市场 |
| date | string | 交易日期 |
| pre_close | float | 昨收盘 |
| open | float | 今开盘 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| change | float | 涨跌 |
| change_rate | float | 涨跌幅 |
| volume | float | 成交量 |
| amount | float | 成交金额 |
| discount | float | 贴水（净值-收盘价） |
| discount_rate | float | 贴水率（(净值-收盘)/净值） |
| shares | float | 流通份额 |
| cum_adj_factor | float | 累积后复权因子 |
| price_limit | float | 涨跌停限制 |
| limit_up | float | 涨停价 |
| limit_down | float | 跌停价 |
| actual_pre_close | float | 实际昨收盘 |
| exchange_shares | float | 场内份额 |
| floating_shares | float | 场内非限售份额 |
| restricted_shares | float | 场内限售份额 |
| security_id | string | 内部证券ID |

示例：获取指定日期的数据

```python
import panda_data
result = panda_data.get_fund_daily(
    start_date="20260610",
    end_date="20260610",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | amount | close | high | low | open | pre_close | volume |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 159001.SZ | 20260601 | 441974791.513 | 100.0 | 100.001 | 99.999 | 99.999 | 100.001 | 4419766 |
| 159003.SZ | 20260601 | 29051918.92 | 99.999 | 100.0 | 99.999 | 99.999 | 100.0 | 290520 |
| 159005.SZ | 20260601 | 12901091.089 | 100.001 | 100.001 | 99.999 | 100.0 | 100.001 | 129011 |

### get_fund_daily_post：获取场内基金后复权日行情数据（只有场内基金数据）

数据范围 1998-04-07 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=272)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期（交易日期），格式 YYYYMMDD |
| end_date | string | 是 | 结束日期（交易日期），格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| exchange | string | 交易市场 |
| date | string | 交易日期 |
| pre_close | float | 昨收盘 |
| open | float | 今开盘 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| amount | float | 成交金额 |
| security_id | string | 内部证券ID |

示例：获取指定日期的数据

```python
import panda_data
result = panda_data.get_fund_daily_post(
    start_date="20260601",
    end_date="20260601",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | amount | close | exchange | high | low | open | pre_close | volume |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 159001.SZ | 20260601 | 441974791.513 | 100.0 | SZ | 100.001 | 99.999 | 99.999 | 100.001 | 4419766 |
| 159003.SZ | 20260601 | 29051918.92 | 99.999 | SZ | 100.0 | 99.999 | 99.999 | 100.0 | 290520 |
| 159005.SZ | 20260601 | 12901091.089 | 100.001 | SZ | 100.001 | 99.999 | 100.0 | 100.001 | 129011 |

### get_fund_daily_pre：获取场内基金前复权日行情数据（只有场内基金数据）

数据范围 1998-04-07 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=273)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期（交易日期），格式 YYYYMMDD |
| end_date | string | 是 | 结束日期（交易日期），格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| exchange | string | 交易市场 |
| date | string | 交易日期 |
| pre_close | float | 昨收盘 |
| open | float | 今开盘 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| amount | float | 成交金额 |
| security_id | string | 内部证券ID |

示例：获取指定日期的数据

```python
import panda_data
result = panda_data.get_fund_daily_pre(
    start_date="20260601",
    end_date="20260601",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | amount | close | exchange | high | low | open | pre_close | volume |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 510050.SH | 20250603 | 1.377558e+09 | 2.6772 | SH | 2.6898 | 2.6635 | 2.6694 | 2.6781 | 501260254 |
| 510050.SH | 20250604 | 8.767604e+08 | 2.6840 | SH | 2.6927 | 2.6772 | 2.6801 | 2.6772 | 318023306 |
| 510050.SH | 20250605 | 1.146638e+09 | 2.6830 | SH | 2.6898 | 2.6742 | 2.6888 | 2.6840 | 416479500 |

返回示例（前 3 行）：

| symbol | date | close |
|:---|:---|:---|
| 159915.SZ | 20250102 | 2.019 |
| 159915.SZ | 20250103 | 1.978 |
| 159915.SZ | 20250106 | 1.976 |

### get_fund_min：获取ETF基金分钟线数据

数据范围 2000-01-01 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=354)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 基金代码 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| time_zone | Optional[tuple] | 否 | 时间段过滤，格式为 ("HH:MM", "HH:MM")，包含起止时间，且结束时间必须大于开始时间 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |
| frequency | Optional[str] | 否 | 数据频率，可选值为 "1m"、"5m"、"15m"、"60m"，默认为 "1m" |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 基金代码 |
| date | str | 日期 |
| minute | str | 时间，格式为 "HHMMSS" |
| datetime | str | 时间，格式为 "YYYY-MM-DD HH:mm:ss" |
| open | double | 开盘价 |
| high | double | 最高价 |
| low | double | 最低价 |
| close | double | 收盘价 |
| volume | double | 成交量 |
| amount | double | 成交金额 |
| vwap | double | 均价 |
| security_id | string | 内部证券ID |

示例：获取单只ETF在指定时间内的分钟线全字段

```python
import panda_data
result = panda_data.get_fund_min(
    symbol="510050.SH",
    start_date="20260901",
    end_date="20260901",
    time_zone=("10:00", "11:00")
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | datetime | minute | open | high | low | close | volume | amount | vwap |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 510050.SH | 20260901 | 2026-09-01 10:00:00 | 100000 | 3.047 | 3.048 | 3.046 | 3.047 | 3709500.0 | 11302878.0 | 3.047008 |
| 510050.SH | 20260901 | 2026-09-01 10:01:00 | 100100 | 3.047 | 3.048 | 3.046 | 3.047 | 4111000.0 | 12527047.0 | 3.047202 |
| 510050.SH | 20260901 | 2026-09-01 10:02:00 | 100200 | 3.048 | 3.048 | 3.047 | 3.047 | 8068900.0 | 24592004.0 | 3.047752 |

### WsTickCNETF：订阅A股ETF tick数据

数据范围 实时；[官方页面](https://www.pandaaiquant.com/docs/api?id=335)

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

# ETF market=CN_ETF，订阅键 tick_ETF_510050.SH，推 Level1 五档
# 盘后、集合竞价外一般只有订阅成功，不会有新 Tick
client = TickStreamClient(market="CN_ETF")
client.subscribe_tick("tick_ETF_510050.SH")
# 多只时传列表：client.subscribe_tick(["tick_ETF_510050.SH", "tick_ETF_159919.SZ"])
# 一次最多订阅 3000 只
# 关闭订阅：client.unsubscribe_tick("tick_ETF_510050.SH")

def on_tick(tick):
    print(tick)

client.listen(handler=on_tick)
time.sleep(30)
client.close()
```

返回示例（前 3 行）：

| {"action": | "subscribed", | "symbols": | ["tick_ETF_510050.SH"]} |
|:---|:---|:---|:---|
| {"code": "510050.SH", "exchange": "SH", "open": 2.812, "high": 2.818, "low": 2.798, "lastPrice": 2.806, "volume": 412356800, "amount": 1158234567.0, "preClose": 2.81, "tickTime": "1789542000000", "ask1": 2.806, "ask2": 2.807, "ask3": 2.808, "ask4": 2.809, "ask5": 2.81, "askVol1": 1850000, "askVol2": 2320000, "askVol3": 1680000, "askVol4": 940000, "askVol5": 1260000, "bid1": 2.805, "bid2": 2.804, "bid3": 2.803, "bid4": 2.802, "bid5": 2.801, "bidVol1": 960000, "bidVol2": 1540000, "bidVol3": 2110000, "bidVol4": 1780000, "bidVol5": 1320000, "highLimited": 3.091, "lowLimited": 2.529, "numBrades": 28641} |

## ETF数据

### get_fund_etf_dividend：获取ETF基金分红数据

数据范围 2000-01-01 ~ 至今；每日更新 22:00～23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=327)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 基金代码 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 基金代码 |
| name | str | 基金名称 |
| payable_date | str | 红利发放日 |
| record_date | str | 权益登记日 |
| date | str | 除息日 |
| dividend | double | 基金单位分红 |
| dividend_index | int | 当年分红序数 |
| security_id | string | 内部证券ID |

示例：获取ETF在指定时间内的分红记录

```python
import panda_data
result = panda_data.get_fund_etf_dividend(
    start_date="20260801",
    end_date="20260831"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | payable_date | record_date | dividend | dividend_index |
|:---|:---|:---|:---|:---|:---|:---|
| 159118.SZ | 20260812 | 华夏标普港股通低波红利ETF | 20260814 | 20260811 | 0.002 | 1 |
| 159119.SZ | 20260817 | 招商中证800自由现金流ETF | 20260819 | 20260814 | 0.003 | 7 |
| 159209.SZ | 20260817 | 招商中证全指红利质量ETF | 20260819 | 20260814 | 0.003 | 8 |

### get_fund_etf_split：获取ETF基金拆分、折算数据

数据范围 2000-01-01 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=328)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 基金代码 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| split_type | Optional[str] | 否 | 类型（拆分/折算） |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 基金代码 |
| name | str | 基金名称 |
| payable_date | str | 拆分折算日 |
| split_type | str | 类型（拆分/折算） |
| split_factor | double | 拆分折算比例 |
| pre_unit_nav | double | 前一交易日净值 |
| unit_nav | double | 拆分折算日净值 |
| date | str | 实施公告日期 |
| ex_date | str | 实施结果日期 |
| security_id | string | 内部证券ID |

示例：获取ETF在指定时间内的拆分折算记录

```python
import panda_data
result = panda_data.get_fund_etf_split(
    start_date="20260101",
    end_date="20261231",
    split_type="拆分"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | payable_date | split_type | split_factor | pre_unit_nav | unit_nav | ex_date |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 159246.SZ | 20260209 | 富国创业板人工智能ETF | 20260212 | 拆分 | 2.0 | 2.0783 | 1.081 | 20260213 |
| 159305.SZ | 20260513 | 广发国证新能源电池ETF | 20260520 | 拆分 | 2.0 | 2.1514 | 1.101 | 20260521 |
| 159320.SZ | 20260707 | 广发恒生A股电网设备ETF | 20260714 | 拆分 | 3.0 | 1.8915 | 0.643 | 20260715 |

### get_fund_etf_cr：获取ETF基金申赎清单数据

数据范围 2020-01-02 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=274)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期(交易日期)，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期(交易日期)，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 交易代码 |
| name | string | 基金简称 |
| date | string | 交易日期 |
| exchange | string | 交易市场 |
| index_symbol | string | 指数代码 |
| index_name | string | 指数简称 |
| cash_component | float | 现金差额(元，上一交易日) |
| estimated_cash_component | float | 预估现金差额(元) |
| cash_substitution_rate | float | 现金替代比例上限(%) |
| unit | integer | 最小申赎单位(份) |
| creation_unit | float | 最小申赎单位资产净值(元，上一交易日) |
| unit_nav | float | 单位净值（上一交易日） |
| publish_iopv_flag | integer | 是否需要公布IOPV(1:是，0:否) |
| purchase_allowed_flag | integer | 是否允许申购(1:是，0:否) |
| redemption_allowed_flag | integer | 是否允许赎回(1:是，0:否) |
| security_id | string | 内部证券ID |

示例：获取一段时间内的数据

```python
import panda_data
result = panda_data.get_fund_etf_cr(
    start_date='20230101',
    end_date='20231231',
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | cash_component | cash_substitution_rate | creation_unit | estimated_cash_component | exchange | index_name | index_symbol | name | publish_iopv_flag | purchase_allowed_flag | redemption_allowed_flag | unit | unit_nav |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 159001.SZ | 20230103 | 0.0 | 100 | 100.0 | 0.0 | SZ | None | None | 易方达保证金收益货币ETF-A | 0 | 1 | 1 | 1 | None |
| 159001.SZ | 20230104 | 0.0 | 100 | 100.0 | 0.0 | SZ | None | None | 易方达保证金收益货币ETF-A | 0 | 1 | 1 | 1 | None |
| 159001.SZ | 20230105 | 0.0 | 100 | 100.0 | 0.0 | SZ | None | None | 易方达保证金收益货币ETF-A | 0 | 1 | 1 | 1 | None |

### get_fund_etf_listing：ETF 上市

数据范围 2005-01-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=348)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | str | 是 | 查询起始日期（按上市日期），格式为 "YYYYMMDD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期（按上市日期），格式为 "YYYYMMDD"，与开始日期间不超过5年 |
| symbol | Optional[Union[str, List[str]]] | 否 | 基金代码，如 "510050.SH"，可以是单个字符串或字符串列表 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 基金代码，如 510050.SH |
| date | str | 基金上市日期，格式为 "YYYYMMDD" |
| name | str | 基金简称 |
| listed_shares | double | 上市交易份额（亿份） |
| security_id | string | 内部证券ID |

示例：获取2025年上半年新上市ETF

```python
import panda_data
result = panda_data.get_fund_etf_listing(
    start_date="20250101",
    end_date="20250630",
    fields=["symbol","date","name","listed_shares"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | listed_shares |
|:---|:---|:---|:---|
| 510040.SH | 20250106 | 鹏华上证180ETF | 6.804800 |
| 511160.SH | 20250106 | 国债ETF东财 | 0.513209 |
| 560190.SH | 20250106 | 鹏华中证全指公用事业ETF | 1.738340 |

### get_fund_etf_suspend：ETF 停复牌

数据范围 2005-01-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=349)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | str | 是 | 查询起始日期（按停牌日期），格式为 "YYYYMMDD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期（按停牌日期），格式为 "YYYYMMDD"，与开始日期间不超过5年 |
| symbol | Optional[Union[str, List[str]]] | 否 | 基金代码，如 "510050.SH"，可以是单个字符串或字符串列表 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 基金代码，如 510050.SH |
| date | str | 停牌日期，格式为 "YYYYMMDD" |
| name | str | 基金简称 |
| suspend_time | str | 停复牌时间 |
| suspend_reason | str | 停牌原因 |
| security_id | string | 内部证券ID |

示例：获取ETF停复牌记录

```python
import panda_data
result = panda_data.get_fund_etf_suspend(
    start_date="20250101",
    end_date="20260920",
    fields=["symbol","date","name","suspend_time","suspend_reason"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | suspend_time | suspend_reason |
|:---|:---|:---|:---|:---|
| 159100.SZ | 20260226 | 华夏布拉德斯科巴西伊博维斯帕ETF(QDII) | 2026-02-26 09:30:00~2026-02-26 10:30:00 | 重大事项 |
| 159100.SZ | 20260225 | 华夏布拉德斯科巴西伊博维斯帕ETF(QDII) | 2026-02-25 09:30:00~2026-02-25 10:30:00 | 重大事项 |
| 159100.SZ | 20260202 | 华夏布拉德斯科巴西伊博维斯帕ETF(QDII) | 2026-02-02 09:30:00~2026-02-02 10:30:00 | 重大事项 |

### get_fund_etf_constituents：获取ETF基金申赎清单成分券信息

数据范围 2006-04-01 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=275)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期(交易日期)，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期(交易日期)，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 交易代码 |
| name | string | 基金简称 |
| exchange | string | 证券市场 |
| date | string | 交易日期 |
| stock_symbol | string | 成分股代码 |
| quantity | integer | 股票数量(股,一篮子个股) |
| cash_substitution_flag | integer | 现金替代标志(1:允许，2:必须，3:禁止，4:退补) |
| cash_premium_rate | float | 现金替代溢价比例(%) |
| cash_discount_rate | float | 现金替代折价比例(%) |
| fixed_substitution_amount | float | 固定替代金额(元,一篮子个股) |
| redemption_cash_amount | float | 赎回替代金额(元,一篮子个股) |
| security_id | string | 内部证券ID |

示例：获取一段时间内的数据

```python
import panda_data
result = panda_data.get_fund_etf_constituents(
    start_date='20250501',
    end_date="20250508"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | cash_discount_rate | cash_premium_rate | cash_substitution_flag | exchange | fixed_substitution_amount | name | quantity | redemption_cash_amount | stock_symbol |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 159001.SZ | 20250506 | None | None | 2 | SZ | 100.0 | 易方达保证金收益货币ETF-A | 0.0 | None | 159900 |
| 159001.SZ | 20250507 | None | None | 2 | SZ | 100.0 | 易方达保证金收益货币ETF-A | 0.0 | None | 159900 |
| 159001.SZ | 20250508 | None | None | 2 | SZ | 100.0 | 易方达保证金收益货币ETF-A | 0.0 | None | 159900 |

### get_fund_etf_cr_net：获取ETF净申赎数据

数据范围 2005-02-23 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=276)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期(交易日期)，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期(交易日期)，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 交易代码 |
| exchange | string | 交易市场 |
| date | string | 交易日期 |
| shares | float | 份额 |
| shares_change | float | 份额变动 |
| size | float | 规模 |
| size_change | float | 规模变动 |
| net_redemption | float | 净申赎 |
| unit_nav | float | 单位净值 |
| reference_net | float | 参考净值 |
| close | float | 收盘价 |
| vwap | float | 成交均价 |
| market_cap | float | 市值 |
| net_inflow | float | 资金净流入 |
| net_inflow_avg | float | 资金净流入(成交均价) |
| split_rate | float | 拆分折算比例 |
| currency_symbol | string | 货币种类 |
| security_id | string | 内部证券ID |

示例：获取一段时间内的数据

```python
import panda_data
result = panda_data.get_fund_etf_cr_net(
    start_date='20250501',
    end_date="20250508"
)
print(result)
```

返回示例（前 3 行）：

| symbol | info_date | end_date | name | currency | amount | ex_amount | sub_amount | occur_amount | ex_occur_amount | sub_occur_amount | total_amount | ex_balance | sub_balance | total_amount_ratio | high_debt_ratio_amount | related_amount | excess_amount |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000002.SZ | 20250401 | 20241231 | 万科A | CNY | 9640958.26 | 243337.59 | 9397620.67 | 5015893.11 | 173180.42 | 4842712.69 | 7424999.26 | 184286.57 | 7240712.69 | 36.62 | 4989736.45 | None | None |
| 000002.SZ | 20250823 | 20250630 | 万科A | CNY | 10430848.57 | 321350.98 | 10109497.59 | 2375233.77 | 85052.39 | 2290181.38 | 8632172.11 | 258510.43 | 8373661.68 | 42.59 | 5409448.13 | None | None |
| 000006.SZ | 20250426 | 20241231 | 深振业A | CNY | 246700.0 | 0.0 | 246700.0 | 26415.46 | 0.0 | 26415.46 | 102958.33 | 0.0 | 102958.33 | 19.05 | 102958.33 | 0.0 | 0.0 |

### get_fund_etf_cr_limits：获取ETF申赎限制数据

数据范围 2008-04-21 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=277)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期(交易日期)，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期(交易日期)，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 交易代码 |
| date | string | 交易日期 |
| exchange | string | 交易市场 |
| nav | float | 基金份额净值（上一交易日） |
| min_cr_unit | integer | 最小申赎单位（份） |
| purchase_limit | integer | 申购上限 |
| redemption_limit | integer | 赎回上限 |
| net_purchase_limit | integer | 净申购上限 |
| net_redemption_limit | integer | 净赎回上限 |
| account_net_purchase | integer | 单账户净申购上限 |
| account_net_redemption | integer | 单账户净赎回上限 |
| account_purchase_limit | integer | 单账户申购上限 |
| account_redemption_limit | integer | 单账户赎回上限 |
| security_id | string | 内部证券ID |

示例：获取一段时间内的数据

```python
import panda_data
result = panda_data.get_fund_etf_cr_limits(
    start_date='20250501',
    end_date="20250508"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | exchange | min_cr_unit | nav | purchase_limit | redemption_limit | account_net_purchase | account_net_redemption | account_purchase_limit | account_redemption_limit | net_purchase_limit | net_redemption_limit |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 159001.SZ | 20250506 | SZ | 1 | 100.0 | None | None | 5000000.0 | None | None | None | 15000000.0 | 2000000.0 |
| 159003.SZ | 20250506 | SZ | 1 | 100.0 | None | None | 3000000.0 | None | None | None | 3000000.0 | 50000.0 |
| 159005.SZ | 20250506 | SZ | 1 | 100.0 | 2000000.0 | 2000000.0 | 200000.0 | 2000000.0 | 2000000.0 | 2000000.0 | 2000000.0 | 50000.0 |

## 基金持仓与配置

### get_fund_holding_detail：获取基金持仓明细

数据范围 2000-04-07 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=312)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| holding_type | Optional[string] | 否 | 持有证券类型（B-债券, E-股票, F-基金） |
| report_type | Optional[string] | 否 | 报告类型 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| date | string | 发布日期 |
| holding_type | string | 持有证券类型（B-债券, E-股票, F-基金） |
| holding_symbol | string | 持有证券交易代码 |
| holding_exchange | string | 持有证券交易所代码 |
| holding_name | string | 持有证券中文简称 |
| hold_volume | float | 持有数量 |
| market_value | float | 市值（元） |
| ratio | float | 占净资产比例（%） |
| info_date | string | 报告日期 |
| currency | string | 币种 |
| security_id | string | 内部证券ID |

示例：获取在日期范围内的持仓明细部分字段

```python
import panda_data
result = panda_data.get_fund_holding_detail(
        start_date="20150601",
        end_date="20151230",
        fields=["symbol", "date", "holding_symbol", "holding_name", "hold_volume", "market_value", "ratio"])
print(result)
```

返回示例（前 3 行）：

| symbol | date | holding_symbol | holding_name | hold_volume | market_value | ratio |
|:---|:---|:---|:---|:---|:---|:---|
| 000001.OF | 20150718 | 002051.SZ | 中工国际 | 4549709.0 | 1.354903e+08 | 1.72 |
| 000001.OF | 20150718 | 002279.SZ | 久其软件 | 5933739.0 | 3.174550e+08 | 4.04 |
| 000001.OF | 20150718 | 002326.SZ | 永太科技 | 6570694.0 | 1.760289e+08 | 2.24 |

### get_fund_asset_allocation：获取基金资产配置

数据范围 2005-02-17 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=313)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| date | string | 日期 |
| total_asset | float | 资产总值（元） |
| net_asset | float | 资产净值（元） |
| equity_market_value | float | 股票市值（元） |
| bond_market_value | float | 债券市值（元） |
| cash_market_value | float | 现金市值（元） |
| other_market_value | float | 其他资产市值（元） |
| equity_ratio | float | 股票占资产总值比例（%） |
| bond_ratio | float | 债券占资产总值比例（%） |
| cash_ratio | float | 货币占资产总值比例（%） |
| other_ratio | float | 其它资产占资产总值比例（%） |
| info_date | string | 报告日期 |
| currency | string | 币种 |
| security_id | string | 内部证券ID |

示例：获取指定时间内的资产配置

```python
import panda_data
result = panda_data.get_fund_asset_allocation(
    start_date="20160331",
    end_date="20160630"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | info_date | total_asset | net_asset | equity_market_value | bond_market_value | cash_market_value | other_market_value | equity_ratio | bond_ratio | cash_ratio | other_ratio | currency |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.OF | 20160420 | 20160331 | 5781129117.38 | 5137069524.23 | 3203328587.7 | 1538487720.5 | 494813932.97 | 544498876.21 | 55.4101 | 26.6122 | 8.5591 | 9.4186 | CNY |
| 000003.OF | 20160421 | 20160331 | 107417416.6 | 83685570.98 | 15751600.0 | 89915080.82 | 1449657.03 | 301078.75 | 14.6639 | 83.7062 | 1.3496 | 0.2803 | CNY |
| 000004.OF | 20160421 | 20160331 | 107417416.6 | 83685570.98 | 15751600.0 | 89915080.82 | 1449657.03 | 301078.75 | 14.6639 | 83.7062 | 1.3496 | 0.2803 | CNY |

### get_fund_stock_portfolio_change：获取基金股票投资组合变动

数据范围 2004-06-30 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=314)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| change_type | Optional[integer] | 否 | 变动类型（1：买入, 2：卖出） |
| stock_exchange | Optional[Union[string, List[string]]] | 否 | 买卖证券交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| info_date | string | 报告日期 |
| date | string | 日期 |
| change_type | integer | 变动类型（1:买入, 2:卖出） |
| stock_exchange | string | 买卖证券交易市场 |
| stock_symbol | string | 股票代码 |
| market_value | float | 累计卖出买入金额（元） |
| ratio | float | 占期初资产净值比例（%） |
| security_id | string | 内部证券ID |

示例：获取在指定时间内的股票投资组合变动

```python
import panda_data
result = panda_data.get_fund_stock_portfolio_change(
    start_date="20160101",
    end_date="20160630"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | info_date | stock_exchange | stock_symbol | market_value | ratio | change_type |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.OF | 20160630 | 20160630 | SZ | 000333.SZ | 73639567.45 | 1.21 | 1 |
| 000001.OF | 20160630 | 20160630 | SH | 601988.SH | 227368793.56 | 3.73 | 2 |
| 000001.OF | 20160630 | 20160630 | SZ | 000709.SZ | 75834321.69 | 1.24 | 2 |

### get_fund_industry_allocation：获取基金行业配置

数据范围 2002-03-21 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=315)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| exchange | Optional[string] | 否 | 基金交易市场 |
| invest_type | Optional[string] | 否 | 投资类型（积极投资、综合投资、境内投资、指数投资、港股通投资） |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| exchange | string | 基金交易市场 |
| info_date | string | 报告日期 |
| date | string | 日期 |
| invest_type | string | 投资类型（积极投资、综合投资、境内投资、指数投资、港股通投资） |
| industry_code | string | 行业代码（公告） |
| industry_standard | string | 行业划分标准 |
| industry_name | string | 行业类别名称 |
| market_value | float | 公允价值（元） |
| ratio | float | 占基金资产净值比例（%） |
| security_id | string | 内部证券ID |

示例：获取在指定时间内的行业配置

```python
import panda_data
result = panda_data.get_fund_industry_allocation(
    start_date="20160331",
    end_date="20160630"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | exchange | info_date | market_value | ratio | invest_type | industry_code | industry_standard | industry_name |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.OF | 20160420 | OF | 20160331 | 3203328587.7 | 0.6236 | 综合投资 | None | 证监会行业2012 | 行业投资合计 |
| 000001.OF | 20160420 | OF | 20160331 | 50555258.14 | 0.0098 | 综合投资 | A | 证监会行业2012 | 农、林、牧、渔业 |
| 000001.OF | 20160420 | OF | 20160331 | 160931554.9 | 0.0313 | 综合投资 | B | 证监会行业2012 | 采矿业 |

### get_fund_bond_distribution：获取基金债券券种分布

数据范围 2000-01-01 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=316)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| bond_type | Optional[string] | 否 | 债券类别（其它资产、券种分布合计、国债、央行票据、金融债券、企业债券、企业短期融资券、中期票据、可转换债券、其他债券、短期融资券、同业存单、地方政府债券、中小企业私募债、剩余存续期超过397天的浮动利率债券、公司债、政策性金融债券） |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| info_date | string | 报告日期 |
| date | string | 日期 |
| bond_type | string | 债券类别 |
| market_value | float | 公允价值（元） |
| ratio | float | 占基金资产净值比例（%） |
| security_id | string | 内部证券ID |

示例：获取在指定时间内的券种分布

```python
import panda_data
result = panda_data.get_fund_bond_distribution(
    start_date="20160331",
    end_date="20160630"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | info_date | market_value | ratio | bond_type |
|:---|:---|:---|:---|:---|:---|
| 000001.OF | 20160420 | 20160331 | 742409420.5 | 14.45 | 企业债券 |
| 000001.OF | 20160420 | 20160331 | 1538487720.5 | 29.95 | 券种分布合计 |
| 000001.OF | 20160420 | 20160331 | 30009000.0 | 0.58 | 国债 |

### get_fund_asset_allocation_detail：获取基金资产配置细分

数据范围 2009-04-20 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=320)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| report_type | Optional[string] | 否 | 报告类型（0101：第一季度报，0102：第二季度报，0103：第三季度报，0104：第四季度报） |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| fund_name | string | 基金全称 |
| info_date | string | 报告日期 |
| actual_date | string | 截止日期 |
| date | string | 日期 |
| report_type | string | 报告类型（0101：第一季度报，0102：第二季度报，0103：第三季度报，0104：第四季度报） |
| item_code | string | 科目名称 |
| market_value | float | 市值（元） |
| ratio_total | float | 占总资产比例（%） |
| ratio_in_net | float | 占净资产比例（%） |
| security_id | string | 内部证券ID |

示例：获取在指定时间内的资产配置细分

```python
import panda_data
result = panda_data.get_fund_asset_allocation_detail(
        start_date="20160331",
        end_date="20170630",
        fields=["info_date", "report_type", "market_value",'item_code']
    )
print(result)
```

返回示例（前 3 行）：

| symbol | date | info_date | report_type | market_value | item_code |
|:---|:---|:---|:---|:---|:---|
| 000001.OF | 20160420 | 20160331 | 0101 | 5.079008e+08 | 买入返售金融资产 |
| 000001.OF | 20160420 | 20160331 | 0101 | 1.538488e+09 | 债券 |
| 000001.OF | 20160420 | 20160331 | 0101 | 3.659806e+07 | 其它资产 |

### get_fund_category_changes：获取基金持仓分类变动数据

数据范围 2000-01-01 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=287)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | Optional[string] | 否 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | Optional[string] | 否 | 查询结束日期，格式为 "YYYYMMDD" |
| is_new | Optional[integer] | 否 | 是否最新（1：最新，0：历史） |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| start_date | string | 开始日期 |
| end_date | string | 结束日期 |
| asset_type | string | 资产类别 |
| type_name | string | 分类名称 |
| market | string | 国内市场 |
| foreign_market | string | 国外市场 |
| is_new | integer | 是否最新（1：是，0：否） |
| security_id | string | 内部证券ID |

示例：获取在一定时间内的持仓分类变动

```python
import panda_data
result = panda_data.get_fund_category_changes(
    start_date="20210101",
    end_date="20210630"
)
print(result)
```

返回示例（前 3 行）：

| symbol | start_date | end_date | asset_type | type_name | market | foreign_market | is_new |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 011032.OF | 20210201 | 20210630 | 混合型 | 灵活配置混合型 | A股市场 | None | 0 |
| 011871.OF | 20210325 | 20210630 | 混合型 | 灵活配置混合型 | A股市场 | None | 0 |

### get_fund_stock_trade：获取基金股票交易信息

数据范围 2004-09-01 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=318)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| report_type | Optional[string] | 否 | 报告类型（0106：年报，0105:年报） |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| exchange | string | 交易市场 |
| info_date | string | 报告日期 |
| date | string | 日期 |
| report_type | string | 报告类型（0106：年报，0105:年报） |
| buy_cost | float | 买入股票成本总额（元） |
| sell_income | float | 卖出股票收入总额（元） |
| balance | float | 买卖差额（元） |
| security_id | string | 内部证券ID |

示例：获取在指定时间内的股票交易信息

```python
import panda_data
result = panda_data.get_fund_stock_trade(
    start_date="20160101",
    end_date="20160630"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | buy_cost | balance | report_type | info_date | sell_income |
|:---|:---|:---|:---|:---|:---|:---|
| 000001.OF | 20160329 | 20996319310.529999 | -3175465998.24 | 0106 | 20151231 | 24171785308.77 |
| 000003.OF | 20160325 | 190318870.97 | -11780815.22 | 0106 | 20151231 | 202099686.19 |
| 000004.OF | 20160325 | 190318870.97 | -11780815.22 | 0106 | 20151231 | 202099686.19 |

## 基金风格与业绩

### get_fund_investment_style：获取基金投资风格

数据范围 2009-12-31 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=317)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| scale_style | Optional[Union[string, List[string]]] | 否 | 规模风格（small：小盘；mid：中盘；large：大盘） |
| style_label | Optional[Union[string, List[string]]] | 否 | 价值成长风格（value：价值；blend：平衡；growth：成长） |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| exchange | string | 交易市场 |
| date | string | 日期 |
| style_score | float | 风格评分 |
| scale_score | float | 规模评分 |
| scale_style | string | 规模风格（small：小盘；mid：中盘；large：大盘） |
| style_label | string | 价值成长风格（value：价值；blend：平衡；growth：成长） |
| security_id | string | 内部证券ID |

示例：获取在指定时间内的投资风格

```python
import panda_data
result = panda_data.get_fund_investment_style(
    start_date="20160601",
    end_date="20160630"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | exchange | style_score | scale_score | scale_style | style_label |
|:---|:---|:---|:---|:---|:---|:---|
| 000001.OF | 20160630 | OF | 169.939718 | 222.159347 | large | blend |
| 000008.OF | 20160630 | OF | 170.037612 | 210.456448 | large | blend |
| 000011.OF | 20160630 | OF | 186.942367 | 240.901605 | large | growth |

### get_fund_bond_style：获取偏债基金风格特征数据

数据范围 2013-03-29 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=285)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| is_new | Optional[integer] | 否 | 是否最新（1：最新，0：历史） |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 基金代码 |
| bond_position | string | 债券仓位 |
| bond_position_history | string | 历史债仓 |
| leverage_preference | string | 杠杆偏好 |
| leverage_preference_history | string | 历史杠杆 |
| bond_type | string | 券种特征 |
| bond_type_history | string | 历史券种 |
| duration_preference | string | 久期偏好 |
| duration_preference_history | string | 历史久期 |
| credit_feature | string | 信用特征 |
| credit_feature_history | string | 历史信用 |
| is_new | integer | 是否最新（1：是，0：否） |
| security_id | string | 内部证券ID |

示例：获取在指定时间内的债券风格特征

```python
import panda_data
result = panda_data.get_fund_bond_style(
     start_date="20210301",
    end_date="20210331"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | bond_position | bond_position_history | leverage_preference | leverage_preference_history | bond_type | bond_type_history | duration_preference | duration_preference_history | credit_feature | credit_feature_history | is_new |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000003.OF | 20210331 | 债券>100% | 债券仓位灵活 | 杠杆>140% | 杠杆灵活 | 可转债 | 券种稳定 | 久期0~1年 | 久期稳定 | AAA级 | 信用灵活 | 0 |
| 000004.OF | 20210331 | 债券>100% | 债券仓位灵活 | 杠杆>140% | 杠杆灵活 | 可转债 | 券种稳定 | 久期0~1年 | 久期稳定 | AAA级 | 信用灵活 | 0 |
| 000005.OF | 20210331 | 债券>100% | 债券仓位灵活 | 杠杆>140% | 杠杆稳定 | 信用债 | 券种灵活 | 久期1~3年 | 久期稳定 | AAA级 | 信用稳定 | 0 |

示例：获取在日期范围内的历史债券风格特征部分字段

```python
import panda_data
result = panda_data.get_fund_bond_style(
      start_date="20250801",
       end_date="20250830",
       fields=["symbol", "date", "bond_position", "duration_preference", "is_new"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | duration_preference | bond_position | is_new |
|:---|:---|:---|:---|:---|
| 000003.OF | 20250829 | 久期0~1年 | 债券80%~100% | 0 |
| 000004.OF | 20250829 | 久期0~1年 | 债券80%~100% | 0 |
| 000005.OF | 20250829 | 久期1~3年 | 债券>100% | 0 |

### get_fund_stock_style：获取偏股基金风格特征数据

数据范围 2013-03-29 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=286)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| is_new | Optional[integer] | 否 | 是否最新（1：最新，0：历史） |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 基金代码 |
| industry_feature | string | 行业特征 |
| stock_position | string | 股票仓位 |
| industry_feature_history | string | 历史行业 |
| style_preference | string | 风格偏好 |
| stock_position_history | string | 历史仓位 |
| is_new | integer | 是否最新（1：是，0：否） |
| security_id | string | 内部证券ID |

示例：获取在指定时间内的股票风格特征

```python
import panda_data
result = panda_data.get_fund_stock_style(
    start_date="20250801",
        end_date="20250830"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | industry_feature | stock_position | industry_feature_history | stock_position_history | style_preference | is_new |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.OF | 20250829 | 国防军工,电子,计算机 | 股票60%~80% | 行业配置稳定 | 股票仓位稳定 | 大盘成长 | 0 |
| 000006.OF | 20250829 | 行业均衡配置 | 股票80%~100% | 行业配置稳定 | 股票仓位稳定 | 中盘平衡 | 0 |
| 000011.OF | 20250829 | 行业均衡配置 | 股票80%~100% | 行业配置稳定 | 股票仓位稳定 | 大盘成长 | 0 |

### get_fund_nav_deviation：获取基金资产净值偏离情况

数据范围 2008-06-30 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=319)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| report_type | Optional[string] | 否 | 公告类型（0106：年报，0105:年报，0101：第一季度报，0102：第二季度报，0103：第三季度报，0104：第四季度报） |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| info_date | string | 报告日期 |
| date | string | 日期 |
| report_type | string | 公告类型（0106：年报，0105:年报，0101：第一季度报，0102：第二季度报，0103：第三季度报，0104：第四季度报） |
| deviation_count_band | integer | 偏离度0.25%-0.5%次数 |
| max_deviation | float | 偏离度最高值 |
| min_deviation | float | 偏离度最低值 |
| avg_abs_deviation | float | 偏离度绝对值简单平均值 |
| security_id | string | 内部证券ID |

示例：获取在指定时间内的净值偏离情况

```python
import panda_data
result = panda_data.get_fund_nav_deviation(
    start_date="20160101",
    end_date="20160630"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | info_date | report_type | deviation_count_band | max_deviation | min_deviation | avg_abs_deviation |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 000009.OF | 20160331 | 20160331 | 0101 | 0.0 | 0.1848 | 0.099 | 0.1203 |
| 000009.OF | 20160630 | 20160630 | 0105 | 0.0 | 0.1848 | 0.0662 | 0.104 |
| 000009.OF | 20160630 | 20160630 | 0102 | 0.0 | 0.1212 | 0.0662 | 0.088 |

### get_fund_nav：获取基金历史净值含收益率数据

数据范围 2000-01-07 ~ 至今；每日更新 17:00 ~18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=19)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| exchange | string | 交易市场 |
| date | string | 日期 |
| unit_nav | float | 单位净值（元） |
| publish_date | string | 公布日期 |
| accumulated_nav | float | 累计净值（元） |
| currency | string | 货币（CNY-人民币，HKD-港币，USD-美元） |
| adjusted_nav | float | 复权净值（元） |
| change | float | 涨跌 |
| change_rate | float | 涨跌幅 |
| return_rate | float | 最小区间净值增长率 |
| return_rate_week | float | 本周增长率 |
| return_rate_1week | float | 近周增长率 |
| return_rate_month | float | 本月增长率 |
| return_rate_1month | float | 近月增长率 |
| return_rate_3month | float | 三月增长率 |
| return_rate_6month | float | 六月增长率 |
| return_rate_year | float | 今年增长率 |
| return_rate_1year | float | 一年增长率 |
| return_rate_2year | float | 两年增长率 |
| return_rate_3year | float | 三年增长率 |
| return_rate_5year | float | 五年增长率 |
| return_rate_inception | float | 成立以来增长率 |
| is_year | integer | 年度业绩（1：是，0：否） |
| security_id | string | 内部证券ID |

示例：获取多只基金指定时间段的净值简略数据部分字段

```python
import panda_data
result = panda_data.get_fund_nav(
    start_date="20260601",
    end_date="20260630",
    fields=["symbol", "date", "unit_nav", "change_rate", "return_rate_1year", "return_rate_3year"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | change_rate | return_rate_3year | unit_nav | return_rate_1year |
|:---|:---|:---|:---|:---|:---|
| 000001.OF | 20260630 | 3.7389 | 76.1429 | 1.637 | 90.3477 |
| 000001.OF | 20260629 | 3.6113 | 72.5541 | 1.578 | 86.9344 |
| 000001.OF | 20260626 | -0.9753 | 70.042 | 1.523 | 81.2712 |

### get_fund_performance_metrics：获取基金业绩指标数据

数据范围 2000-01-07 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=289)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 基金代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| security_id | Optional[Union[string, List[string]]] | 否 | 内部证券ID（非必填） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| date | string | 日期 |
| max_drawdown_month | float | 近月回撤 |
| max_drawdown_3month | float | 三月回撤 |
| max_drawdown_6month | float | 六月回撤 |
| max_drawdown_1year | float | 一年回撤 |
| max_drawdown_2year | float | 两年回撤 |
| max_drawdown_3year | float | 三年回撤 |
| max_drawdown_5year | float | 五年回撤 |
| max_drawdown_year | float | 今年回撤 |
| max_drawdown_inception | float | 成立回撤 |
| sharpe_month | float | 近月夏普 |
| sharpe_3month | float | 三月夏普 |
| sharpe_6month | float | 六月夏普 |
| sharpe_1year | float | 一年夏普 |
| sharpe_2year | float | 两年夏普 |
| sharpe_3year | float | 三年夏普 |
| sharpe_5year | float | 五年夏普 |
| sharpe_year | float | 今年夏普 |
| sharpe_inception | float | 成立夏普 |
| beta_month | float | 近月Beta |
| beta_3month | float | 三月Beta |
| beta_6month | float | 六月Beta |
| beta_1year | float | 一年Beta |
| beta_2year | float | 两年Beta |
| beta_3year | float | 三年Beta |
| beta_5year | float | 五年Beta |
| beta_year | float | 今年Beta |
| beta_inception | float | 成立Beta |
| alpha_month | float | 近月Alpha |
| alpha_3month | float | 三月Alpha |
| alpha_6month | float | 六月Alpha |
| alpha_1year | float | 一年Alpha |
| alpha_2year | float | 两年Alpha |
| alpha_3year | float | 三年Alpha |
| alpha_5year | float | 五年Alpha |
| alpha_year | float | 今年Alpha |
| alpha_inception | float | 成立Alpha |
| standard_deviation_month | float | 近月标准差 |
| standard_deviation_3month | float | 三月标准差 |
| standard_deviation_6month | float | 六月标准差 |
| standard_deviation_1year | float | 一年标准差 |
| standard_deviation_2year | float | 两年标准差 |
| standard_deviation_3year | float | 三年标准差 |
| standard_deviation_5year | float | 五年标准差 |
| standard_deviation_year | float | 今年标准差 |
| standard_deviation_inception | float | 成立标准差 |
| volatility_month | float | 近月波动 |
| volatility_3month | float | 三月波动 |
| volatility_6month | float | 六月波动 |
| volatility_1year | float | 一年波动 |
| volatility_2year | float | 两年波动 |
| volatility_3year | float | 三年波动 |
| volatility_5year | float | 五年波动 |
| volatility_year | float | 今年波动 |
| volatility_inception | float | 成立波动 |
| security_id | string | 内部证券ID |

示例：获取某只基金在指定时间内的业绩指标

```python
import panda_data
result = panda_data.get_fund_performance_metrics(
     symbol="000001.OF",
     start_date="20200601",
     end_date="20210130",
    fields=["date","symbol" ,"max_drawdown_month","sharpe_month", "beta_month", "beta_inception","standard_deviation_month"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | sharpe_month | beta_inception | beta_month | max_drawdown_month | standard_deviation_month |
|:---|:---|:---|:---|:---|:---|:---|
| 000001.OF | 20210129 | 2.164611 | 1.115957 | 1.295074 | -5.092377 | 0.014926 |
| 000001.OF | 20210128 | 2.003082 | 1.116014 | 1.317730 | -5.092377 | 0.014913 |
| 000001.OF | 20210127 | 3.344931 | 1.115858 | 1.314743 | -4.460674 | 0.014235 |
