---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - Preferred Stock
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# 优先股

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 优先股数据

### get_stock_preferred_dividend：获取优先股分红

数据范围 2015-05-21 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=263)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期(最新公告日)，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期(最新公告日)，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 优先股代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| procedure | Optional[Union[string, List[string]]] | 否 | 事件进程(1:董事会通过;2:股东大会通过;3:实施;4:停止实施) |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 优先股代码 |
| exchange | string | 交易市场 |
| interest_start_date | string | 计息起始日 |
| interest_end_date | string | 计息截止日 |
| publish_date | string | 最新公告日 |
| plan_ann_date | string | 预案公告日 |
| meeting_date | string | 股东大会公告日 |
| dividend_date | string | 分红实施公告日 |
| procedure | string | 事件进程 |
| currency_code | string | 货币代码 |
| coupon_dividend_rate | float | 票面股息率(百分比) |
| dividend_pre_tax | float | 每股派现(税前,元) |
| dividend_after_tax | float | 每股派现(税后,元) |
| total_dividend_amount | float | 派息总额(万元) |
| last_trading_date | string | 最后交易日 |
| record_date | string | 股权登记日 |
| ex_date | string | 除息日 |
| payment_date | string | 派息日 |

示例：获取指定时间内的数据

```python
import panda_data
result = panda_data.get_stock_preferred_dividend(
    start_date="20200101",
    end_date="20260602",
)
print(result)
```

返回示例（前 3 行）：

| symbol | coupon_dividend_rate | dividend_date | ex_date | exchange | publish_date | total_dividend_amount |
|:---|:---|:---|:---|:---|:---|:---|
| 140001.SZ | 4.6 | 20201112 | 20201116 | SZ | 20201112 | 22310.0 |
| 140001.SZ | 4.68 | 20211110 | 20211116 | SZ | 20211110 | 22698.0 |
| 140001.SZ | 4.68 | 20221109 | 20221116 | SZ | 20221109 | 22698.0 |

### get_stock_preferred_trading：获取优先股成交统计信息

数据范围 2014-12-26 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=262)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期(交易日期)，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期(交易日期)，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 优先股代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 优先股代码 |
| exchange | string | 交易市场 |
| date | string | 交易日期 |
| price | string | 成交价(元) |
| volume | string | 成交量(股) |
| amount | string | 成交金额(元) |
| buyer_department | string | 买入营业部 |
| seller_department | string | 卖出营业部 |

示例：获取指定时间内的数据

```python
import panda_data
result = panda_data.get_stock_preferred_trading(
    start_date="20200101",
    end_date="20260602",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | amount | buyer_department | exchange | price | seller_department | volume |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 140001.SZ | 20210910 | 8382000 | 机构专用 | SZ | 83.82 | 海通证券股份有限公司上海黄浦区福州路证券营业部 | 100000 |
| 140001.SZ | 20210915 | 9089000 | 机构专用 | SZ | 90.89 | 海通证券股份有限公司上海黄浦区福州路证券营业部 | 100000 |
| 140001.SZ | 20210922 | 9897000 | 机构专用 | SZ | 98.97 | 海通证券股份有限公司上海黄浦区福州路证券营业部 | 100000 |

### get_stock_issuer_credit_rating：获取优先股发行主体信用评级

数据范围 1995-03-02 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=261)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期(公告日期)，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期(公告日期)，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| rating_level | Optional[Union[string, List[string]]] | 否 | 级别(格式：“AA”) |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| full_name | string | 发行主体 |
| publish_date | string | 公告日期 |
| rating_date | string | 评级日期 |
| rating_level | string | 级别 |
| outlook | string | 展望 |
| rating_company | string | 评级公司 |
| previous_level | string | 上次级别 |
| previous_outlook | string | 上次展望 |

示例：获取指定时间内的数据

```python
import panda_data
result = panda_data.get_stock_issuer_credit_rating(
    start_date="20200101",
    end_date="20260602",
)
print(result)
```

返回示例（前 3 行）：

| symbol | full_name | name | outlook | previous_level | previous_outlook | publish_date | rating_company | rating_date | rating_level |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 平安银行股份有限公司 | 平安银行 | 2 | AAA | 2 | 20200218 | 中诚信国际信用评级有限责任公司 | 20200210 | AAA |
| 000001.SZ | 平安银行股份有限公司 | 平安银行 | 2 | None | None | 20200429 | 惠誉国际信用评级有限公司 | 20200429 | BB+ |
| 000001.SZ | 平安银行股份有限公司 | 平安银行 | 2 | AAA | 2 | 20200507 | 大公国际资信评估有限公司 | 20200507 | AAA |

### get_stock_preferred_rating：获取优先股评级情况

数据范围 2014-10-28 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=260)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期(公告日期)，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期(公告日期)，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 优先股代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| rating_level | Optional[Union[string, List[string]]] | 否 | 评级(格式：“AA”) |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 优先股代码 |
| exchange | string | 交易市场 |
| publish_date | string | 公告日 |
| rating_date | string | 评级日 |
| rating_level | string | 评级 |
| rating_agency | string | 评级机构简称 |

示例：获取指定时间内的数据

```python
import panda_data
result = panda_data.get_stock_preferred_rating(
    start_date="20200101",
    end_date="20260602",
)
print(result)
```

返回示例（前 3 行）：

| symbol | exchange | publish_date | rating_agency | rating_date | rating_level |
|:---|:---|:---|:---|:---|:---|
| 360038.SH | SH | 20200108 | 联合信用评级 | 20190412 | AA |
| 360042.SH | SH | 20201124 | 中诚信国际 | 20200708 | AA+ |
| 360043.SH | SH | 20201222 | 中诚信国际 | 20200708 | AA+ |

### get_stock_preferred_shares：获取优先股股本

数据范围 2014-11-25 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=259)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期(公告日期)，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期(公告日期)，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| exchange | string | 交易市场代码 |
| publish_date | string | 公告日期 |
| change_date | string | 变动日期 |
| change_reason | string | 变动原因 |
| issue_shares | float | 发行股份数量(万股) |

示例：获取指定时间内的数据

```python
import panda_data
result = panda_data.get_stock_preferred_shares(
    start_date="20200101",
    end_date="20260602",
)
print(result)
```

返回示例（前 3 行）：

| symbol | change_date | change_reason | exchange | issue_shares | publish_date |
|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20260310 | 优先股赎回 | SZ | 0 | 20260310 |
| 000488.SZ | 20210317 | 优先股赎回 | SZ | 2250 | 20210312 |
| 000488.SZ | 20210819 | 优先股赎回 | SZ | 1250 | 20210819 |

### get_stock_preferred_placement：获取优先股配售结果

数据范围 2014-11-28 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=258)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 优先股代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| target_type | Optional[Union[string, List[string]]] | 否 | 发行对象类型(见发行对象类型表) |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 优先股代码 |
| exchange | string | 交易市场 |
| issuer_target | string | 发行对象 |
| target_type | string | 发行对象类型 |
| subscription_volume | float | 认购数量(万股) |
| subscription_amount | float | 认购金额(万元) |
| is_related_party | integer | 是否为关联方(0:否,1:是;2:未获知) |
| has_recent_related_transaction | integer | 最近一年是否存在关联交易(0:否,1:是;2:未获知) |

示例：获取所有优先股的数据

```python
import panda_data
result = panda_data.get_stock_preferred_placement(
)
print(result)
```

返回示例（前 3 行）：

| symbol | exchange | has_recent_related_transaction | is_related_party | issuer_target | subscription_amount | subscription_volume | target_type |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 140001.SZ | SZ | 0 | 0 | 浦银安盛基金管理有限公司 | 50000 | 500.0 | 基金管理公司 |
| 140001.SZ | SZ | 0 | 0 | 中粮信托有限责任公司 | 114100 | 1141.0 | 信托公司 |
| 140001.SZ | SZ | 0 | 0 | 博时基金管理有限公司 | 77900 | 779.0 | 基金管理公司 |

### get_stock_preferred_detail：获取优先股基本资料

数据范围 2014-11-28 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=257)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 优先股代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场 |
| plan_progress | Optional[Union[string, List[string]]] | 否 | 方案进度(见方案进度表) |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 优先股代码 |
| exchange | string | 交易市场 |
| name | string | 优先股名称 |
| publish_date | string | 最新公告日 |
| issue_target | string | 发行对象 |
| face_value | float | 票面金额(元) |
| currency_code | string | 货币代码 |
| dividend_yield | float | 票面股息率(百分比) |
| dividend_yield_description | string | 股息率说明 |
| dividend_yield_type | string | 股息率类型 |
| issuance_method | string | 发行方式 |
| is_installment | integer | 是否分次对应(0:否,1:是;2:未获知) |
| subscription_method | string | 认购方式 |
| max_issue_volume | float | 发行数量上限(万股) |
| min_issue_volume | float | 发行数量下限(万股) |
| actual_issue_volume | float | 实际发行数量(万股) |
| offering_price | float | 发行价格 |
| plan_progress | string | 方案进度 |
| board_plan_date | string | 董事会预案公告日 |
| shareholder_meeting_date | string | 股东大会决议公告日 |
| cbrc_approval_date | string | 银监会批准公告日 |
| ipo_review_date | string | 发审委通过公告日 |
| csrc_approval_date | string | 证监会核准公告日 |
| registration_date | string | 登记日期 |
| issuance_ann_date | string | 发行公告日 |
| listing_ann_date | string | 挂牌转让公告日 |
| listed_date | string | 上市日期 |
| is_accumulated | integer | 股息是否累计对应(0:否,1:是;2:未获知) |
| is_convertible | integer | 是否可转换为普通股对应(0:否,1:是;2:未获知) |
| voting_restrictions | string | 表决限制条款 |
| voting_right_recovery | string | 表决权恢复条件 |
| is_forced_conversion | integer | 是否可强制转换为普通股对应(0:否,1:是;2:未获知) |
| forced_conversion_conditions | string | 强制转换为普通股条件 |
| annual_payment_count | float | 年付息次数 |
| first_interest_date | string | 首次起息日 |
| dividend_adjustment_period | float | 股息调整周期(年) |
| purchasedate | string | 申购日 |
| underwriting_method | string | 承销方式 |
| max_planned_raising | float | 预计募集资金上限 |
| min_planned_raising | float | 预计募集资金下限 |
| actual_raising_amount | float | 实际募集资金 |
| net_raising_amount | float | 募集资金净额 |
| fund_usage | string | 资金用途 |
| is_at_par | integer | 是否可强制转换为普通股对应(0:否,1:是;2:未获知) |
| put_provision | string | 回售条款 |
| forced_conversion_price | float | 强制转股价格(元/股) |
| fund_receipt_date | string | 募集资金到账日期 |
| fund_verification_date | string | 募集资金验资日期 |
| transfer_arrangement | string | 转让安排 |
| reference_date | string | 基准日 |
| reference_date_type | string | 基准日类型 |
| right_to_residual_profit | integer | 是否可强制转换为普通股对应(0:否,1:是;2:未获知) |

示例：获取所有优先股的数据

```python
import panda_data
result = panda_data.get_stock_preferred_detail(
)
print(result)
```

返回示例（前 3 行）：

| symbol | actual_issue_volume | actual_raising_amount | board_plan_date | dividend_yield | exchange | net_raising_amount |
|:---|:---|:---|:---|:---|:---|:---|
| 140001.SZ | 4850.0 | 485000.0 | 20141022 | 4.6 | SZ | 482575.0 |
| 140002.SZ | 20000.0 | 2000000.0 | 20140716 | 4.37 | SZ | 1995250.0 |
| 140003.SZ | 2250.0 | 225000.0 | 20141230 | 4.36 | SZ | 223875.0 |
