---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - Trading Tools
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# 交易工具

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 交易日历

### get_trade_cal：获取交易日历

数据范围 1980-01-01 ~ 至今；每日更新 00:20 ~ 00:40；[官方页面](https://www.pandaaiquant.com/docs/api?id=1)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | Optional[string] | 否 | 开始日期，格式为 YYYYMMDD |
| end_date | Optional[string] | 否 | 结束日期，格式为 YYYYMMDD |
| exchange | Optional[string] | 否 | 交易所代码，默认为 "SH"，目前支持"SH"，"HK"和"US" |
| is_trading_day | Optional[integer] | 否 | 是否为交易日，1=交易日，0=非交易日，None=全部 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| nature_date | integer | 日期，格式为YYYYMMDD |
| exchange | string | 交易所代码 |
| is_trade | integer | 是否为交易日，1表示交易日，0表示非交易日 |
| pretrade_date | string | 当前日期前一个交易日 |
| next_trade_date | string | 当前日期后一个交易日 |

示例：获取一段时间内上交所交易日历

```python
import panda_data
result = panda_data.get_trade_cal(
    start_date="20250101",
    end_date="20250115",
    exchange="SH",
    is_trading_day=None,
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| exchange | is_trade | nature_date | pretrade_date | next_trade_date |
|:---|:---|:---|:---|:---|
| SH | 0 | 20250101 | 20241231 | 20250102 |
| SH | 1 | 20250102 | 20241231 | 20250103 |
| SH | 1 | 20250103 | 20250102 | 20250106 |

## 某一日期前第 n 个交易日

### get_prev_trade_date：获取指定日期的前第n个交易日

数据范围 1980-01-01 ~ 至今；每日更新 00:20 ~ 00:40；[官方页面](https://www.pandaaiquant.com/docs/api?id=5)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| date | string | 是 | 基准日期，格式为 "YYYYMMDD" |
| exchange | Optional[string] | 否 | 交易所代码，默认为 "SH"，目前支持"SH"，"HK"和"US" |
| n | Optional[integer] | 否 | 前第n个交易日，默认为1 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 第前n个交易日，格式 "YYYYMMDD"，如果没有则返回None |

示例：获取上交所某一日期的前第5个交易日

```python
import panda_data
result = panda_data.get_prev_trade_date(
    date="20250102",
    exchange="SH",
    n=5
)
print(result)
```

返回示例（前 3 行）：

| date |
|:---|
| 20241225 |

## 最新交易日

### get_last_trade_date：获取最新交易日

数据范围 1980-01-01 ~ 至今；每日更新 00:20 ~ 00:40；[官方页面](https://www.pandaaiquant.com/docs/api?id=8)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| exchange | Optional[string] | 否 | 交易所代码，默认为 "SH"，目前支持"SH"，"HK"和"US" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 最新交易日，格式 "YYYYMMDD"，如果没有则返回None |

示例：获取上交所最新交易日

```python
import panda_data
result = panda_data.get_last_trade_date(
    exchange="SH"
)
print(result)
```

返回示例（前 3 行）：

| date |
|:---|
| 20251223 |

## 合约特殊处理数据

### get_stock_status_change：获取股票特殊处理数据

数据范围 1998-04-28 ~ 至今；每日更新 09:19 ~ 09:39；[官方页面](https://www.pandaaiquant.com/docs/api?id=46)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | Optional[string] | 否 | 开始日期,eg:"20250702" |
| end_date | Optional[string] | 否 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 信息发布日期 |
| change_date | string | 特别处理（或撤销）实施日期 |
| description | string | 特别处理（或撤销）事项描述 |
| name | string | 股票名称 |
| type | string | 特别处理（或撤销）类别 |

示例：获取一定日期内某只股票合约特殊处理数据

```python
import panda_data
result = panda_data.get_stock_status_change(
    symbol="002217.SZ",
    start_date="20250101",
    end_date="20250131",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | change_date | description | name | type |
|:---|:---|:---|:---|:---|:---|
| 002217.SZ | 20250107 | 20250106 | 公司因被法院裁定受理重整而触及的退市风险警示情形已经消除,公司按照《深圳证券交易所股票上市规则》第9.4.14条的相关规定,向深圳证券交易所申请撤销相应的退市风险警示。2025年1月6日,公司收到深交所通知,深交所同意公司撤销因重整而被实施退市风险警示的申请。 | *ST合泰 | 撤销叠加*ST |

### get_st_list：获取股票st信息

数据范围 2000-01-01 ~ 至今；每日更新 07:51 ~ 08:11；[官方页面](https://www.pandaaiquant.com/docs/api?id=332)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，支持 `000001.SZ` 格式；为空查询全部股票；列表按股票代码精确匹配并按 OR 逻辑查询 |
| start_date | string | 是 | 开始日期，格式为 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式为 YYYYMMDD |
| is_st | Optional[boolean] | 否 | 是否为 ST 股票；传入 True 仅返回 ST 股票，传入 False 仅返回非 ST 股票；为空返回全部状态记录 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 状态日期，格式 YYYYMMDD |
| is_st | boolean | 是否为 ST 股票 |

示例：示例调用

```python
import panda_data
result = panda_data.get_st_list(
    start_date="20260731",
    end_date="20260731",
    is_st=True
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | is_st |
|:---|:---|:---|
| 000010.SZ | 20260731 | True |
| 000016.SZ | 20260731 | True |
| 000056.SZ | 20260731 | True |

### get_suspended_list：获取股票停牌信息

数据范围 2000-01-01 ~ 至今；每日更新 09:29 ~ 09:49；[官方页面](https://www.pandaaiquant.com/docs/api?id=331)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，支持 `000001.SZ` 格式；为空查询全部股票；列表按股票代码精确匹配并按 OR 逻辑查询 |
| start_date | string | 是 | 开始日期，格式为 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式为 YYYYMMDD |
| is_suspended | Optional[boolean] | 否 | 是否停牌；传入 True 仅返回停牌股票，传入 False 仅返回未停牌股票；为空返回全部状态记录 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 状态日期，格式 YYYYMMDD |
| is_suspended | boolean | 是否停牌 |

示例：示例调用

```python
import panda_data
result = panda_data.get_suspended_list(
    start_date="20260731",
    end_date="20260731",
    is_suspended=True
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | is_suspended |
|:---|:---|:---|
| 002828.SZ | 20260731 | True |
| 300333.SZ | 20260731 | True |
| 300615.SZ | 20260731 | True |

## 指定日期的在售股票列表

### get_trade_list：获取指定日期的在售股票列表

数据范围 1980-01-02 ~ 至今；每日更新 16:15 ~ 16:35；[官方页面](https://www.pandaaiquant.com/docs/api?id=50)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| date | Union[string, List[string]] | 是 | 日期,eg:"20250702" |
| exchange | Optional[string] | 否 | 交易所代码，默认为 "SH"，目前支持"SH"，"HK"和"US" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 日期 |

示例：获取指定日期的在售股票列表

```python
import panda_data
result = panda_data.get_trade_list(
        date="20251211"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date |
|:---|:---|
| 000001.SZ | 20251211 |
| 000002.SZ | 20251211 |
| 000004.SZ | 20251211 |
