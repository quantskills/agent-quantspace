---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - A-Share Corporate Actions and Holders
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# A股公司行为与股东

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 公司行为

### get_investor_activity：获取A股合约投资者关系活动

数据范围 2012-07-09 ~ 至今；每日更新 00:21 ~ 00:41；[官方页面](https://www.pandaaiquant.com/docs/api?id=42)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 公告发布日 |
| symbol | string | 股票代码 |
| participant | string | 参与人员 |
| investor_or_analyst_detail | string | 与会人员详情 |
| institute | string | 参与机构 |

示例：获取一定日期内某只股票合约投资者关系活动数据

```python
import panda_data
result = panda_data.get_investor_activity(
        symbol="000001.SZ",
        start_date="20250101",
        end_date="20250131",
        fields=[]
)
print(result)
```

返回示例（前 3 行）：

| participant | institute | investor_or_analyst_detail | symbol | date |
|:---|:---|:---|:---|:---|
| None | None | 境内投资者 | 000001.SZ | 20250117 |

### get_restricted_list：获取股票限售解禁明细数据

数据范围 2005-08-09 ~ 2026-08-31；每日更新 停更；[官方页面](https://www.pandaaiquant.com/docs/api?id=43)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| market | Optional[string] | 否 | 市场,默认'cn'为中国内地市场 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 合约代码 |
| date | string | 限售解禁信息发布日期 |
| relieve_date | string | 解禁日期 |
| shareholder | string | 股东名 |
| shareholder_type | string | 股东类型 |
| relieve_shares | float | 解除限售股份数量(股) |
| actual_relieve_shares | float | 实际上市流通数量(股) |
| relieve_reason | string | 解禁原因 |

示例：获取一定日期内某只股票的股票限售解禁明细数据

```python
import panda_data
result = panda_data.get_restricted_list(
        symbol="001256.SZ",
        start_date="20251201",
        end_date="20251231",
        fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | relieve_date | relieve_shares | shareholder | actual_relieve_shares | relieve_reason | shareholder_type |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 001256.SZ | 20251211 | 20251212 | 45758500.0 | 浙江承炜股权投资有限公司 | 45758500.0 | 发行前股份限售流通 | 企业 |
| 001256.SZ | 20251211 | 20251212 | 37280000.0 | 周炳松 | 9320000.0 | 发行前股份限售流通 | 自然人 |
| 001256.SZ | 20251211 | 20251212 | 10320000.0 | 李玉荷 | 2580000.0 | 发行前股份限售流通 | 自然人 |

### get_repurchase：获取回购数据

数据范围 2010-03-19 ~ 至今；每日更新 20:54 ~ 21:14；[官方页面](https://www.pandaaiquant.com/docs/api?id=16)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 日期，格式 "YYYYMMDD" |
| end_date | string | 是 | 日期，格式 "YYYYMMDD" |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 日期，格式 "YYYYMMDD" |
| seller | string | 股份被回购方 |
| procedure | string | 事件进程 |
| share_type | string | 股份类别 |
| announcement_dt | datetime | 公告发布当天的日期时间戳，格式 "YYYY-MM-DD HH:MM:SS.sss" |
| buy_back_start_date | string | 回购期限起始日，格式 "YYYYMMDD" |
| buy_back_end_date | string | 回购期限结束日，格式 "YYYYMMDD" |
| write_off_date | string | 回购注销公告日，格式 "YYYYMMDD" |
| maturity_desc | string | 股份回购期限说明 |
| buy_back_volume | float | 回购股数（股）（份） |
| volume_ceiling | float | 回购数量上限（股）（份） |
| volume_floor | float | 回购数量下限（股）（份） |
| buy_back_value | float | 回购总金额（元） |
| buy_back_price | float | 回购价格（元/股）（元/份） |
| price_ceiling | float | 回购价格上限（元） |
| price_floor | float | 回购价格下限（元） |
| currency | float | 货币单位 |
| purpose | string | 回购目的 |
| buy_back_percent | float | 占总股本比例 |
| value_floor | float | 拟回购资金总额下限（元） |
| value_ceiling | float | 拟回购资金总额上限（元） |
| buy_back_mode | string | 股份回购方式 |

示例：获取一定日期内某只股票的回购数据

```python
import panda_data
result = panda_data.get_repurchase(
    symbol="002011.SZ",
    start_date="20250101",
    end_date="20251231",
    fields=["symbol", "seller", "date", "procedure"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | procedure | seller |
|:---|:---|:---|:---|
| 002011.SZ | 20250730 | 实施完成 | 激励对象 |
| 002011.SZ | 20251127 | 预案 | 8名激励对象 |
| 002011.SZ | 20251127 | 决案 | 8名激励对象 |

### get_holder_count：获取股东数量

数据范围 2024-01-01 ~ 至今；每日更新 09:00 ~ 09:20；[官方页面](https://www.pandaaiquant.com/docs/api?id=44)

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
| date | string | 公告日期 |
| end_date | string | 截止日期 |
| a_holders | string | A股股东户数 |
| avg_a_holders | string | A股股东户均持股数 |
| avg_circulation_holders | float | 无限售A股股东户均持股数 |
| avg_holders | float | 户均持股数 |
| holders | string | 股东户数 |

示例：获取一定日期内某只股票的股东数量

```python
import panda_data
result = panda_data.get_holder_count(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250531",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | end_date | a_holders | avg_a_holders | avg_circulation_holders | avg_holders | holders |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20250315 | 20241231 | 486258.0 | 39908.69 | 39907.0 | 39908.69 | 486258.0 |
| 000001.SZ | 20250315 | 20250228 | 479969.0 | 40431.61 | 40430.0 | 40431.61 | 479969.0 |
| 000001.SZ | 20250419 | 20250331 | 504267.0 | 38483.42 | 38482.0 | 38483.42 | 504267.0 |

### get_top_holders：获取A股股东信息

数据范围 2020-01-02 ~ 至今；每日更新 05:58 ~ 06:18；[官方页面](https://www.pandaaiquant.com/docs/api?id=45)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| market | Optional[string] | 否 | 市场,默认"cn"为中国内地市场 |
| start_rank | Optional[integer] | 否 | 排名开始值 |
| end_rank | Optional[integer] | 否 | 排名结束值 |
| stock_type | Optional[string] | 否 | 股票种类, flow基于持有A股流通股;total基于所有发行出的A股 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 信息发布日期 |
| stock_type | string | 股票类型 |
| rank | integer | 排名 |
| symbol | string | 股票代码 |
| end_date | string | 截止日期 |
| freeze | float | 股权冻结涉及股数（股） |
| hold_percent_float | float | 占流通A股比例（%） |
| hold_percent_total | float | 占股比例(%) |
| holder_attr | string | 股东属性 |
| holder_kind | string | 股东性质 |
| holder_name | string | 股东名称 |
| holder_type | float | 股东类别 |
| pledge | float | 股权质押涉及股数 |

示例：获取一定日期内某只股票的股东信息

```python
import panda_data
result = panda_data.get_top_holders(
        symbol="000001.SZ",
        start_date="20250101",
        end_date="20250531",
        start_rank=1,
        end_rank=5,
        stock_type="flow",
        market="cn",
        fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | rank | stock_type | end_date | freeze | hold_percent_float | hold_percent_total | holder_attr | holder_kind | holder_name | holder_type | pledge |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20250315 | 1.0 | flow | 20241231 | None | 49.565869 | 49.564984 | 企业 | 金融机构—保险公司 | 中国平安保险(集团)股份有限公司-集团本级-自有资金 | None | None |
| 000001.SZ | 20250315 | 2.0 | flow | 20241231 | None | 6.112165 | 6.112055 | 企业 | 金融机构—保险公司 | 中国平安人寿保险股份有限公司-自有资金 | None | None |
| 000001.SZ | 20250315 | 3.0 | flow | 20241231 | None | 3.8488 | 3.848732 | 企业 | 一般企业 | 香港中央结算有限公司 | None | None |

### get_block_trade：获取A股大宗交易信息

数据范围 2005-01-04 ~ 至今；每日更新 04:25 ~ 04:45；[官方页面](https://www.pandaaiquant.com/docs/api?id=47)

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
| date | string | 交易日期 |
| price | float | 成交价 |
| volume | float | 成交量 |
| amount | float | 成交额 |
| buyer | string | 买方营业部 |
| seller | string | 卖方营业部 |

示例：获取一定日期内某只股票的大宗交易信息

```python
import panda_data
result = panda_data.get_block_trade(
        symbol="000001.SZ",
        start_date="20250101",
        end_date="20250831",
        fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | price | buyer | seller | volume | amount |
|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20250217 | 11.78 | 机构专用 | 中信证券股份有限公司上海分公司 | 171000.0 | 2014400.0 |
| 000001.SZ | 20250711 | 11.86 | 中信证券股份有限公司江苏分公司 | 中信证券股份有限公司江苏分公司 | 1024600.0 | 12151800.0 |

### get_share_float：获取股票股本数据

数据范围 1990-12-19 ~ 至今；每日更新 19:03 ~ 19:23；[官方页面](https://www.pandaaiquant.com/docs/api?id=48)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 信息发布日期 |
| circulation_a | string | 流通A股 |
| free_circulation | string | 自由流通股本 |
| non_circulation_a | string | 非流通A股 |
| preferred_shares | string | 优先股 |
| total | string | 总股本 |
| total_a | string | A股总股本 |

示例：获取一定日期内某只股票的股本数据

```python
import panda_data
result = panda_data.get_share_float(
        symbol="000001.SZ",
        start_date="20250101",
        end_date="20250831",
        fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | circulation_a | free_circulation | non_circulation_a | preferred_shares | total | total_a |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20250102 | 19405617528.0 | 8160498090.0 | 300670.0 | 0.0 | 19405918198.0 | 19405918198.0 |
| 000001.SZ | 20250103 | 19405617528.0 | 8160498090.0 | 300670.0 | 0.0 | 19405918198.0 | 19405918198.0 |
| 000001.SZ | 20250106 | 19405617528.0 | 8160498090.0 | 300670.0 | 0.0 | 19405918198.0 | 19405918198.0 |

### get_stock_dividend：获取股票分红信息

数据范围 1991-02-26 ~ 至今；每日更新 08:35 ~ 08:55；[官方页面](https://www.pandaaiquant.com/docs/api?id=76)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| start_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| announcement_date | string | 公布日期 |
| effective_date | string | 常规分红：对应财政季度；特殊分红：股权登记日 |
| ex_date | string | 除权除息日 |
| div_type | string | 是否分红及分红形式 |

示例：获取一定日期范围内某只股票的分红信息

```python
import panda_data
result = panda_data.get_stock_dividend(
        symbol="688799.SH",
        start_date="20150529",
        end_date="20250529",
)
print(result)
```

返回示例（前 3 行）：

| symbol | announcement_date | effective_date | ex_date | div_type |
|:---|:---|:---|:---|:---|
| 688799.SH | 20220512 | 20211231 | 20220518 | cash only |
| 688799.SH | 20231013 | 20221231 | 20231019 | cash only |
| 688799.SH | 20241017 | 20231231 | 20241025 | cash only |

### get_stock_split：获取股票拆分数据

数据范围 1991-04-30 ~ 至今；每日更新 08:35 ~ 08:55；[官方页面](https://www.pandaaiquant.com/docs/api?id=77)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| start_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| record_date | string | 股权登记日 |
| payable_date | string | 送转股上市日 |
| ex_date | string | 除权除息日，该天股票的价格会因为拆分而进行调整 |
| split_factor_pre | float | 拆分因子（拆分前） |
| split_factor_post | float | 拆分因子（拆分后） |
| cum_adj_factor | float | 累计复权因子（拆分） |

示例：获取一定日期范围内某只股票的拆分数据

```python
import panda_data
result = panda_data.get_stock_split(
        symbol="688798.SH",
        start_date="20050419",
        end_date="20250419",
)
print(result)
```

返回示例（前 3 行）：

| symbol | ex_date | record_date | payable_date | split_factor_pre | split_factor_post | cum_adj_factor |
|:---|:---|:---|:---|:---|:---|:---|
| 688798.SH | 20230616 | 20230615 | 20230616 | 10.0 | 14.0 | 1.4 |

### get_stock_cash_dividend：获取股票现金分红数据

数据范围 1991-04-30 ~ 至今；每日更新 08:25 ~ 08:45；[官方页面](https://www.pandaaiquant.com/docs/api?id=75)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| start_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| announcement_date | string | 分红预案公告日期 |
| div_cash_gross | float | 税前每股现金分红 |
| record_date | string | 股权登记日 |
| ex_date | string | 除权除息日 |
| payment_date | string | 派息日 |
| round_lot | float | 分红基准单位 |
| meeting_date | string | 股东大会日期 |
| quarter | string | 对应财报期 |

示例：获取一定日期范围内某只股票的分红总额数据

```python
import panda_data
result = panda_data.get_stock_cash_dividend(
    symbol="688819.SH",
    start_date="20140613",
    end_date="20240613",
)
print(result)
```

返回示例（前 3 行）：

| symbol | announcement_date | div_cash_gross | record_date | ex_date | payment_date | round_lot | meeting_date | quarter |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 688819.SH | 20210515 | 6.0000 | 20210520 | 20210521 | 20210521 | 10.0 | 20210327 | 2020q4 |
| 688819.SH | 20220611 | 6.0000 | 20220617 | 20220620 | 20220620 | 10.0 | 20220331 | 2021q4 |
| 688819.SH | 20230515 | 6.0000 | 20230518 | 20230519 | 20230519 | 10.0 | 20230325 | 2022q4 |

### get_stock_dividend_amount：获取股票分红总额数据

数据范围 1991-03-03 ~ 至今；每日更新 08:40 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=78)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| start_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| announcement_date | string | 公告日期 |
| event_stage | string | 事项阶段（如董事会预案等） |
| total_div_amount | float | 分红总额 |
| quarter | string | 对应财报期 |

示例：获取一定日期范围内某只股票的分红信息

```python
import panda_data
result = panda_data.get_stock_dividend_amount(
    symbol="000001.SZ",
    start_date="19910626",
    end_date="20260326",
)
print(result)
```

返回示例（前 3 行）：

| symbol | announcement_date | event_stage | total_div_amount | quarter |
|:---|:---|:---|:---|:---|
| 000001.SZ | 19920314 | 方案实施 | 1.795033e+07 | 1991q4 |
| 000001.SZ | 19920314 | 预案 | 1.795033e+07 | 1991q4 |
| 000001.SZ | 19930227 | 预案 | 4.040899e+07 | 1992q4 |

### get_stock_private_placement：获取股票定向增发数据

数据范围 1998-07-27 ~ 至今；每日更新 20:25 ~ 20:45；[官方页面](https://www.pandaaiquant.com/docs/api?id=79)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| start_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| announcement_date | string | 信息发布日期 |
| issue_type | string | 发行类型 |
| issue_status | string | 发行进度/状态 |
| listed_date | string | 上市日期 |
| issued_shares | float | 发行股数 |
| issue_price | float | 发行价 |
| approval_date | string | 证监会核准日 |

示例：获取一定日期范围内某只股票的定向增发信息

```python
import panda_data
result = panda_data.get_stock_private_placement(
    symbol="000001.SZ",
    start_date="19910626",
    end_date="20260326",
)
print(result)
```

返回示例（前 3 行）：

| symbol | announcement_date | issue_type | issue_status | listed_date | issued_shares | issue_price | approval_date |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20090613 | 非公开发行 | 实施完成 | 20100917 | 3.795800e+08 | 18.26 | 20100629 |
| 000001.SZ | 20100902 | 非公开发行 | 实施完成 | 20110805 | 1.638337e+09 | 17.75 | 20110629 |
| 000001.SZ | 20130909 | 非公开发行 | 实施完成 | 20140109 | 1.323385e+09 | 11.17 | 20131231 |

### get_stock_allotment：获取股票配股信息

数据范围 1991-03-06 ~ 至今；每日更新 20:45 ~ 21:05；[官方页面](https://www.pandaaiquant.com/docs/api?id=80)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| start_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 信息发布日期，格式为 "YYYYMMDD" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| announcement_date | string | 信息发布日期 |
| planned_ratio | float | 计划配股比例 |
| actual_ratio | float | 实际配股比例 |
| actual_shares | float | 实际配售股数 |
| allotment_price | float | 配股价 |
| record_date | string | 股权登记日 |
| ex_date | string | 除权日 |

示例：获取一定日期范围内某只股票的配股信息

```python
import panda_data
result = panda_data.get_stock_allotment(
    symbol="000001.SZ",
    start_date="19910626",
    end_date="20260326",
)
print(result)
```

返回示例（前 3 行）：

| symbol | announcement_date | planned_ratio | actual_ratio | actual_shares | allotment_price | record_date | ex_date |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 19910728 | 0.3 | 0.30000 | 20370000.0 | 12.0 | 19910802 | 19910817 |
| 000001.SZ | 19930227 | 0.1 | 0.08108 | 20205000.0 | 16.0 | 19930521 | 19930524 |
| 000001.SZ | 19940329 | 0.1 | 0.10000 | 26941789.0 | 5.0 | 19940708 | 19940711 |

### get_stock_disclosure_date：获取上市A股定期报告预披露数据

数据范围 2007-06-30 ~ 至今；每日更新 22:30 ~ 23:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=145)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 证券简称 |
| expected_disclosure_date | string | 预计披露日 |
| end_date | string | 报告期 |
| actual_disclosure_date | string | 实际披露日 |
| first_change_date | string | 第一次变更日期 |
| second_change_date | string | 第二次变更日期 |
| third_change_date | integer | 第三次变更日期 |
| first_publish_date | integer | 首次发布日期 |
| latest_predisclosure_date | integer | 最新预披露日期 |

示例：获取一定日期范围内上市 A 股定期报告预披露数据

```python
import panda_data
result = panda_data.get_stock_disclosure_date(
    start_date='20250101',
    end_date='20260430',

)
print(result.iloc[:2])
```

返回示例（前 3 行）：

| symbol | end_date | name | expected_disclosure_date | actual_disclosure_date | first_change_date | second_change_date | third_change_date | first_publish_date | latest_predisclosure_date |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20241231 | 平安银行 | 20250315 | 20250315 | None | None | None | 20241231 | 20241231 |
| 000001.SZ | 20250331 | 平安银行 | 20250419 | 20250419 | None | None | None | 20250331 | 20250331 |

### get_stock_over_allotment：获取超额配售权实施情况数据

数据范围 2006-11-17 ~ 至今；每日更新 22:30 ~ 23:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=146)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 证券简称 |
| info_date | string | 公告日期 |
| end_date | string | 最后行使日期 |
| vwap | float | 行权中竞价交易购买股票均价 |
| volume | float | 行权中竞价交易购买股票数量 |
| over_allotment_shares | float | 超额发行股份数 |
| over_allotment_rate | float | 超额配售率 |
| full_subscription_flag | integer | 是否全额(0：否，1：是，2：未获知，3:不排除) |
| additional_raised_funds | float | 增加的募集资金 |
| additional_raised_fee | float | 增加的募集资金费用 |
| total_proceeds_exercise | float | 行权后募集资金总额人民币 |
| net_proceeds_exercise | float | 行权后募集资金净额人民币 |
| foreign_total_proceeds_exercise | float | 行权后募集资金总额外币 |
| foreign_net_proceeds_exercise | float | 行权后募集资金净额外币 |
| currency_symbol | string | 外币币种( HKD：港元，USD：美元) |

示例：获取一定日期范围超额配售权实施情况数据

```python
import panda_data
result = panda_data.get_stock_over_allotment(
    start_date='20250101',
    end_date='20260430',

)
print(result.iloc[:2])
```

返回示例（前 3 行）：

| symbol | info_date | name | end_date | vwap | volume | over_allotment_shares | over_allotment_rate | full_subscription_flag | additional_raised_funds | additional_raised_fee | total_proceeds_exercise | net_proceeds_exercise | foreign_total_proceeds_exercise | foreign_net_proceeds_exercise | currency_symbol |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 001391.SZ | 20250207 | 国货航 | None | None | None | 198176500.0 | 15.0 | 1 | 455806000.0 | 4096000.0 | 3494514200 | 3437295600 | None | None | None |
| 600930.SH | 20250816 | 华电新能 | None | None | None | 745341500.0 | 15.0 | 1 | 2370186000 | 17657600 | 18171428600 | 17944401500 | None | None | None |

### get_stock_litigation_arbitration：获取上市公司诉讼仲裁数据

数据范围 2003-07-30 ~ 至今；每日更新 22:30 ~ 23:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=147)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| lawsuit_type | Optional[Union[string,List[string]] | 否 | 诉讼类型 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 证券代码 |
| name | string | 证券简称 |
| info_date | string | 公告日期 |
| lawsuit_type | string | 诉讼类型(CI:民事诉讼,AD:行政诉讼,CR:刑事诉讼,AR:仲裁) |
| filing_date | string | 起诉日期 |
| case_summary | string | 案件摘要 |
| case_intro | string | 案件简介 |
| case_progress | string | 案件进展 |
| involved_amount | float | 涉案金额(元) |
| currency_code | string | 货币代码 |
| plaintiff | string | 原告方 |
| defendant | string | 被告方 |
| first_court | string | 一审受理法院 |
| first_judgment_date | string | 一审判决日期 |
| is_appeal_flg | integer | 是否上诉(1:是，0:否，2:不排除) |
| appellant_type | string | 上诉方(P:原告，D:被告，TP:其他) |
| second_court | string | 二审受理法院 |
| second_judgment_date | string | 二审判决日期 |
| judgment_content | string | 判决/仲裁内容 |
| remark | string | 备注 |

示例：获取一定日期范围内上市公司诉讼仲裁数据

```python
import panda_data
result = panda_data.get_stock_litigation_arbitration (
    start_date='20250101',
    end_date='20260430',

)
print(result.iloc[:2])
```

返回示例（前 3 行）：

| symbol | appellant_type | case_intro | case_progress | case_summary | currency_code | defendant | filing_date | first_court | first_judgment_date | info_date | involved_amount | is_appeal_flg | judgment_content | lawsuit_type | name | plaintiff | remark | second_court | second_judgment_date |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000776.SZ | None | 案号：\n(2023)粤03民初5772号\n诉讼当事人：\n原告：陈卫福等合计12名自然人投资者\n被告：王迎燕、徐晶、美尚生态、广发证券、东兴证券股份有限公司、天衡会计师事务所(特殊普通合伙)、中天运会计师事务所(特殊普通合伙)、上海市锦天城律师事务所、北京金诚同达律师事务所、钱仁勇、吴运娣、季斌、周芳蓉、惠峰、龙俊、石成华、江仁利、陈晓龙、俞啸军、许中华\n案由：\n证券虚假陈述责任纠纷\n诉讼请求：\n(1)判令被告一王迎燕赔偿各原告损失暂计人民币949,602.89元；(2)判令被告一王迎燕按照每名原告50元的标准向原告代表人赔偿通知费，该项诉讼请求暂计人民币600元；(3)判令其他被告对上述诉讼请求承担连带赔偿责任；(4)本案的受理费、公告费等诉讼费用由被告共同承担。 | 20241217：近日，公司收到了广东省深圳市中级人民法院于2024年12月13日出具的《民事裁定书》。\n20241221：今日，公司关注到中证中小投资者服务中心发布《投资者服务中心密切关注美尚生态案诉讼进展的公告》。\n20241231：2024年12月28日，广东省高级人民法院作出（2024）粤民终7076号复议裁定，驳回上述申请人的复议申请，维持（2023）粤03民初5772号民事裁定。广东省深圳市中级人民法院发布《广东省深圳市中级人民法院普通代表人诉讼权利登记公告》；中证中小投资者服务中心有限责任公司发布了《关于公开征集美尚生态案投资者授权委托的公告》。\n20250101：2024年12月31日，广东省深圳市中级人民法院发布《广东省深圳市中级人民法院特别代表人诉讼权利登记公告》，深圳中院将适用特别代表人诉讼程序审理本案。 | 证券虚假陈述责任纠纷 | CNY | 王迎燕,徐晶,美尚生态景观股份有限公司,广发证券股份有限公司,东兴证券股份有限公司,天衡会计师事务所(特殊普通合伙),中天运会计师事务所(特殊普通合伙),上海市锦天城律师事务所,北京金诚同达律师事务所,钱仁勇,吴运娣,季斌,周芳蓉,惠峰,龙俊,石成华,江仁利,陈晓龙,俞啸军,许中华 | None | 广东省深圳市中级人民法院 | None | 20250101 | 950202.89 | None | None | CI | 广发证券 | 陈卫福等合计12名自然人投资者 | None | None | None |
| 300266.SZ | None | 合同纠纷 | 20250101：公司于近日收到了最高人民法院送达的《民事裁定书》<(2023)最高法民申3374号>,最高人民法院受理公司及杭州中艺的再审申请后，依法组成合议庭进行了审查，现已审查终结。再审法院裁定驳回公司、杭州中艺的再审申请。公司、杭州中艺将在证据完整后采取合适的法律途径，维护公司合法权益。 | 合同纠纷 | CNY | 吴劼,双兴棋,杭州立阳投资管理合伙企业(有限合伙),王森,盛国祥,吕勤,黄斌 | None | 最高人民法院 | None | 20250101 | 188891000.0 | None | None | CI | 兴源环境 | 兴源环境科技股份有限公司,杭州中艺生态环境工程有限公司 | None | None | None |

### get_stock_csrc_approval：获取证监会批文数据

数据范围 1994-03-03 ~ 至今；每日更新 22:30 ~ 23:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=148)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| announcement_level | Optional[Union[integer, List[integer]]] | 否 | 公告级别 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| publish_date | string | 发文日期 |
| publish_institution | string | 发布机构 |
| announcement_category | string | 公告类别（公告类别对应表） |
| announcement_level | integer | 公告级别(分为01级、02级、03级) |
| announcement_title | string | 公告名称 |
| announcement_number | string | 公告文号 |
| announcement_content | string | 公告正文 |
| attachment_link | string | 附件链接 |
| announcement_link | string | 公告链接 |

示例：获取一定日期范围内证监会批文数据

```python
import panda_data
result = panda_data.get_stock_csrc_approval (
    start_date='20250101',
    end_date='20260430',

)
print(result.iloc[:2])
```

返回示例（前 3 行）：

| publish_date | publish_institution | announcement_category | announcement_level | announcement_title | announcement_number | announcement_content | attachment_link | announcement_link |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 0 | 20250102 | 证监会 | 15 | 01 | 关于同意上海期货交易所铅、镍、锡和氧化铝期权注册的批复 | 无 | 上海期货交易所：你所《关于申请铅、镍、锡和氧化铝期权注册的请示》（上期发〔2024〕279号）收悉。根据《中华人民共和国期货和衍生品法》的有关规定，按照《期货期权品种注册管理暂行规定》（证监发〔2022〕85号），现批复如下：一、同意你所铅、镍、锡和氧化铝期权注册。二、请你所做好各项准备工作，确保铅、镍、锡和氧化铝期权平稳运行和健康发展。三、本批复自作出之日起一年内有效。中国证监会2024年8月22日 | http://www.csrc.gov.cn/csrc/c101903/c7530169/content.shtml |
| 1 | 20250102 | 证监会 | 15 | 01 | 关于同意大连商品交易所原木期货和期权注册的批复 | 无 | 大连商品交易所：你所《关于申请原木期货和期权注册的请示》（大商所发〔2023〕410号）收悉。根据《中华人民共和国期货和衍生品法》的有关规定，按照《期货期权品种注册管理暂行规定》（证监发〔2022〕85号），现批复如下：一、同意你所原木期货和期权注册。二、请你所做好各项准备工作，确保原木期货和期权平稳运行和健康发展。三、本批复自作出之日起一年内有效。中国证监会2024年10月24日 | http://www.csrc.gov.cn/csrc/c101903/c7530171/content.shtml |

### get_stock_competitor：获取竞争企业信息数据

数据范围 2019-03-22 ~ 至今；每日更新 22:30 ~ 23:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=149)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 证券代码 |
| info_date | string | 公告日期 |
| name | string | 证券简称 |
| competitor_name | string | 竞争公司名称 |
| competitor_intro | string | 竞争公司机构介绍 |
| competitor_stock_code | string | 竞争公司股票代码 |
| competition_fields | string | 竞争领域（有多个时，以“,”分割） |

示例：获取一定日期范围内股票竞争企业信息数据

```python
import panda_data
result = panda_data.get_stock_competitor_information (
    start_date='20250101',
    end_date='20260430',
    symbol=['001220.SZ']
)
print(result.iloc[:2])
```

返回示例（前 3 行）：

| symbol | info_date | name | competitor_name | competitor_intro | competitor_stock_code | competition_fields |
|:---|:---|:---|:---|:---|:---|:---|
| 001220.SZ | 20251121 | 世盟股份 | 上海畅联国际物流股份有限公司 | 上海畅联国际物流股份有限公司成立于 2001 年 5 月 22 日，公司专注于为国际跨国企业提供精益供应链管理服务，主要在企业供应链中的采购、生产、销售等环节提供供应链综合管理方案的设计与实施，并提供与之配套的口岸通关、仓储管理、货物配送等一体化综合物流服务。 | 603648 | 综合性物流服务 |
| 001220.SZ | 20251121 | 世盟股份 | 密尔克卫智能供应链服务集团股份有限公司 | 密尔克卫化工供应链服务股份有限公司成立于 1997 年 3 月 28 日，公司是一家专业化工供应链服务商，提供以货运代理、仓储和运输为核心的一站式综合物流服务，以及化工品交易服务。 | 603713 | 综合性物流服务 |

### get_stock_intermediary：获取中介情况信息表数据

数据范围 1984-11-18 ~ 至今；每日更新 22:30 ~ 23:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=150)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| event_type | Optional[Union[string, List[string]]] | 否 | 事件类型 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 证券简称 |
| equity_event_code | string | 权益融资事件代码 |
| event_type | string | 事件类型（PIPE:定向增发；FO:公开增发；IPO:首发；RI:配股；PREF:优先股；PRE:定期报告） |
| issue_start_date | string | 发行起始日 |
| intermediary_category | string | 中介机构类别（见中介机构类别对应表） |
| intermediary_name | string | 中介机构名称 |
| intermediary_handler | string | 中介机构经办人姓名 |

示例：获取一定日期范围内股票中介情况信息表数据

```python
import panda_data
result = panda_data.get_stock_intermediary (
    start_date='20240101',
    end_date='20260430',
    symbol=['000002.SZ']
)
print(result.iloc[:2])
```

返回示例（前 3 行）：

| symbol | issue_start_date | name | equity_event_code | event_type | intermediary_category | intermediary_name | intermediary_handler |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 000002.SZ | 20241231 | 万科A | 60202401 | PRE | 03 | 毕马威华振会计师事务所(特殊普通合伙) | 周永明、李瑶 |
| 000002.SZ | 20251231 | 万科A | 60202501 | PRE | 03 | 德勤华永会计师事务所(特殊普通合伙) | 杨誉民、许湘照 |

### get_stock_related_party：上市公司关联交易

数据范围 2000-01-08 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=93)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票名 |
| info_date | string | 公告日期 |
| introduction | string | 首次公告日期 |
| relation | string | 关联关系 |
| party_name | string | 关联方名称 |
| is_control | string | 是否存在控制关系 |
| amount | float | 交易金额(万元) |
| currency | string | 币种 |
| pricing_basis | string | 定价依据 |
| trading_method | string | 交易方式 |
| pay_type | string | 支付方式 |
| begin_date | string | 交易起始日 |
| end_date | string | 交易截止日 |

示例：获取一段时间内的某股票相关上市公司关联交易数据

```python
import panda_data
result = panda_data.get_stock_related_party(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20260101",
    fields=[""]
)
print(result)
```

返回示例（前 3 行）：

| symbol | info_date | name | introduction | relation | party_name | is_control | amount | currency | pricing_basis | trading_method | pay_type | begin_date | end_date |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20250222 | 平安银行 | 平安银行股份有限公司(以下简称“平安银行”、“本行”)第十二届董事会第三十五次会议审议通过了《关于与陆金所控股有限公司关联交易的议案》,同意与陆金所控股有限公司(以下简称“陆金所”)进行离岸人民币定期存款业务和离岸协定存款业务合作,其中:离岸人民币定期存款业务本金金额合计不超过人民币45亿元,利息合计不超过人民币0.29亿元;离岸协定存款业务本金金额不超过等值人民币21.84亿元,利息不超过人民币0.18亿元。 | 同一关键人员,公司其它关联方 | 陆金所控股有限公司 | 否 | None | CNY | 前述关联交易的定价按照商业原则进行,定价以不优于对非关联方同类交易的条件进行。 | 金融服务,物业租赁 | 现金 | None | None |
| 000001.SZ | 20250222 | 平安银行 | 平安银行股份有限公司(以下简称“平安银行”、“本行”)第十二届董事会第三十五次会议审议通过了《关于与安科技术有限公司关联交易的议案》,同意与安科技术有限公司(以下简称“安科技术”)进行美元定期存款业务合作,本金金额不超过等值人民币36亿元,利息不超过等值人民币0.44亿元。 | 同一母公司 | 安科技术有限公司 | 否 | None | CNY | 前述关联交易的定价按照商业原则进行,定价以不优于对非关联方同类交易的条件进行。 | 美元定期存款 | 现金 | None | None |
| 000001.SZ | 20250222 | 平安银行 | 平安银行股份有限公司(以下简称“平安银行”、“本行”)第十二届董事会第三十五次会议审议通过了《关于与平安证券股份有限公司关联交易的议案》,同意给予平安证券股份有限公司(以下简称“平安证券”)原额续做同业综合授信额度人民币45亿元,额度期限至2025年10月24日。 | 同一控股公司 | 平安证券股份有限公司 | 否 | 450000.0 | CNY | 前述关联交易定价按照商业原则进行,定价以不优于对非关联方同类交易的条件进行。 | 同业授信 | 现金 | None | None |

### get_cumu_guarantee：获取累计担保信息

数据范围 2009-01-23 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=90)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票名 |
| info_date | string | 公告日期 |
| end_date | string | 截止日期 |
| currency | string | 币种 |
| amount | float | 担保额度（万元） |
| ex_amount | float | 对外担保额度（万元） |
| sub_amount | float | 对子公司担保额度（万元） |
| occur_amount | float | 担保发生额（万元） |
| ex_occur_amount | float | 对外担保发生额（万元） |
| sub_occur_amount | float | 对子公司担保发生额（万元） |
| total_amount | float | 担保总额（万元） |
| ex_balance | float | 对外担保余额（万元） |
| sub_balance | float | 对子公司担保余额（万元） |
| total_amount_ratio | float | 担保总额占净资产比例（%） |
| high_debt_ratio_amount | float | 直接或间接为资产负债率超过70%的被担保对象提供的债务担保金额（万元） |
| related_amount | float | 为股东、实际控制人及其关联方提供担保的金额（万元） |
| excess_amount | float | 担保总额超过净资产50%部分的金额（万元） |

示例：获取一段时间内的所有上市公司担保累计数据

```python
import panda_data
result = panda_data.get_cumu_guarantee(
    symbol="",
    start_date="20250101",
    end_date="20260101",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | info_date | end_date | name | currency | amount | ex_amount | sub_amount | occur_amount | ex_occur_amount | sub_occur_amount | total_amount | ex_balance | sub_balance | total_amount_ratio | high_debt_ratio_amount | related_amount | excess_amount |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000002.SZ | 20250401 | 20241231 | 万科A | CNY | 9640958.26 | 243337.59 | 9397620.67 | 5015893.11 | 173180.42 | 4842712.69 | 7424999.26 | 184286.57 | 7240712.69 | 36.62 | 4989736.45 | None | None |
| 000002.SZ | 20250823 | 20250630 | 万科A | CNY | 10430848.57 | 321350.98 | 10109497.59 | 2375233.77 | 85052.39 | 2290181.38 | 8632172.11 | 258510.43 | 8373661.68 | 42.59 | 5409448.13 | None | None |
| 000006.SZ | 20250426 | 20241231 | 深振业A | CNY | 246700.0 | 0.0 | 246700.0 | 26415.46 | 0.0 | 26415.46 | 102958.33 | 0.0 | 102958.33 | 19.05 | 102958.33 | 0.0 | 0.0 |

### get_stock_material_contract：获取上市公司重大合同数据

数据范围 2009-01-16 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=162)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期(公告日期)，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期(公告日期)，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 证券简称 |
| info_date | string | 公告日期 |
| info_id | string | 公告id |
| project_progress | string | 项目进度 |
| contract_party_a | string | 甲方 |
| contract_party_b | string | 乙方 |
| party_b_relation | string | 上市公司与乙方关系 |
| project_name | string | 项目名称 |
| contract_title | string | 合同名称 |
| max_contract_amount | float | 合同金额上限 |
| min_contract_amount | float | 合同金额下限 |
| currency | string | 币种 |
| has_affiliation | string | 是否存在关联关系(0:否,1:是,2:未获知) |
| is_related_party_transaction | string | 是否构成关联交易(0:否,1:是,2:未获知) |
| contract_term | string | 合同期限 |
| effective_date | string | 合同生效日期 |
| expiration_date | string | 合同截止日期 |
| operation_mode | string | 运作模式 |
| bid_amount | float | 中标金额/上年度营业收入 |
| consortium_members | string | 联合体成员 |

示例：查询一段时间内的数据

```python
import panda_data
result = panda_data.get_stock_material_contract(
    start_date='20250430',
    end_date='20260430',
)
print(result)
```

返回示例（前 3 行）：

| info_date | symbol | bid_amount | consortium_members | contract_party_a | contract_party_b | contract_term | contract_title | currency | effective_date | expiration_date | has_affiliation | info_id | is_related_party_transaction | max_contract_amount | min_contract_amount | name | operation_mode | party_b_relation | project_name | project_progress |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 20250430 | 002973.SZ | 1.455 | None | 浦北县综合行政执法局 | 侨银城市管理股份有限公司 | 96 | None | CNY | None | None | 0 | 45458701 | 0 | 56955126.69 | 56955126.69 | 侨银股份 | None | 本公司 | 浦北县城区环卫保洁和绿化养护一体化服务项目 | 2 |
| 20250430 | 300355.SZ | 9.5212 | 阿拉善左旗蓝马园林生态建设有限责任公司,阿拉善盟城投建设工程有限责任公司 | 阿拉善左旗科学技术和林业草原局 | 蒙草生态环境(集团)股份有限公司 | None | None | CNY | None | None | 0 | 45462371 | 0 | 204281144.6 | 204281144.6 | 蒙草生态 | None | 本公司 | 内蒙古自治区阿拉善盟阿拉善左旗-三北六期蒙甘边境防沙治沙沙漠锁边项目(施工) | 2 |
| 20250430 | 300355.SZ | 11.722 | 中铁四局集团有限公司,通辽市城镇建设发展有限责任公司 | 扎鲁特旗林业和草原局 | 蒙草生态环境(集团)股份有限公司 | 16.2 | None | CNY | 20250501 | 20260830 | 0 | 45471565 | 0 | 251500592.51 | 251500592.51 | 蒙草生态 | None | 本公司 | "内蒙古自治区通辽市2024年度扎鲁特旗'三北'工程林草湿荒一体化保护修复项目(退化草原修复... | 1 |

### get_investor_brief_detail：获取投资者简报详情

数据范围 2021-04-01 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=136)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 日期 |
| begin_time | string | 会议开始时间（精确至秒） |
| title | string | 会议名称 |
| name | string | 股票名 |

示例：获取一定日期范围内业绩说明会详情数据

```python
import panda_data
result = panda_data.get_investor_brief_detail(
    symbol="",
    start_date="20250101",
    end_date="20260101",
    fields=[""]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | begin_time | title | name |
|:---|:---|:---|:---|:---|
| 000011.SZ | 20250421 | 2025-04-21 15:00:00 | 深物业A（000011）、深物业B（200011）2024年度业绩说明会 | 深物业A |
| 000017.SZ | 20250515 | 2025-05-15 15:00:00 | 深中华A（000017）2024年度网上业绩说明会 | 深中华A |
| 000019.SZ | 20250520 | 2025-05-20 15:30:00 | 深粮控股（000019）2024年度网上业绩说明会 | 深粮控股 |

### get_investor_brief_qa：获取投资者简报问答

数据范围 2021-04-01 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=138)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| ask_time | string | 提问时间（精确至秒） |
| date | string | 提问日期（查询筛选依据） |
| ask_user | string | 提问用户 |
| ask_content | string | 提问内容 |
| ans_time | string | 回答时间（精确至秒） |
| ans_member | string | 回答人员 |
| ans_content | string | 回答内容 |
| ans_interval | integer | 问答间隔（秒） |
| is_question | integer | 是否为问题（1为是，0为否） |

示例：获取一定日期范围内业绩说明会提问数据

```python
import panda_data
result = panda_data.get_investor_brief_qa(
    start_date="20250101",
    end_date="20260101",
    fields=["ask_time","date","ask_user","ask_content"]
)
print(result)
```

返回示例（前 3 行）：

| ask_time | date | ask_user | ask_content |
|:---|:---|:---|:---|
| 2025-01-01 05:52:11 | 20250101 | 提问人698436 | 持续2年8个月的重组闹剧，给二级市场投资者造成了伤害，公司会采取哪些手段消除大家的反感？ |
| 2025-01-03 09:15:33 | 20250103 | 提问人652871 | 宜昌市熊书记讲话对旅游业提振全市经济抱有很高的期待，请问在新的一年里作为宜昌国有文旅龙头企业有什么具体举措？一个月后新的项目会不会向市场融资？目前三峡旅游已经具备了水陆运营能力，何时进军国家倡导的低空飞行领域，完善水陆空的布局？三峡旅游股价连续低迷数年，希望在王董事长的带领下能让广大中长线投资者获得实实在在的收益。 |
| 2025-01-03 09:52:49 | 20250103 | 提问人660274 | 您好！请问一下新闻报导说宜昌要建成世界性的旅游名城。贵公司是宜昌唯一的上市公司，有没有什么具体的参与和实施方案?公司未来的发展是以文化旅游为主还是风景旅游为主？ |

### get_stock_equity_illegal：获取股权违规信息

数据范围 1994-04-22 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=265)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| start_date | string | 是 | 查询起始日期（公告日期），格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期（公告日期），格式为 "YYYYMMDD" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票简称 |
| info_date | string | 公告日期 |
| illegal_type | string | 违规类型 |
| illegal_subject | string | 违规主体 |
| punish_subject | string | 处罚对象 |
| punish_relation | string | 处罚对象关系 |
| illegal_event | string | 违规行为 |
| punish_type | string | 处分类型 |
| punish_action | string | 处分措施 |
| executor | string | 处理单位 |
| punish_amount | float | 处罚金额（万） |
| related_laws | string | 相关法律 |

示例：获取一定日期范围内全部上市公司违规情况的部分字段信息

```python
import panda_data
result = panda_data.get_stock_equity_illegal(
    symbol="",
    start_date="20240101",
    end_date="20240131",
    fields=["symbol","info_date","name","illegal_type",
            "illegal_subject","punish_subject","punish_relation","punish_amount"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | info_date | name | illegal_type | illegal_subject | punish_subject | punish_relation | punish_amount |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 000409.SZ | 20240127 | 云鼎科技 | 未依法履行其他职责 | 公司 | 云鼎科技股份有限公司 | 公司本身 | None |
| 000415.SZ | 20240105 | 渤海租赁 | 未依法履行其他职责,未及时披露公司重大事项 | 公司 | 天津通万投资合伙企业(有限合伙) | 公司股东 | None |
| 000415.SZ | 20240106 | 渤海租赁 | 未依法履行其他职责 | 公司 | 天津通万投资合伙企业(有限合伙) | 公司股东 | None |

## 股东行为

### get_stock_pledge：获取A股公司股权质押

数据范围 2021-03-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=91)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票名 |
| publish_date | string | 公告发布日期 |
| shareholder_name | string | 股东名称 |
| shareholder_type | string | 股东类型 |
| pledgor | string | 质押方 |
| pledged_shares | float | 质押股数(万股) |
| pledge_ratio | float | 本次质押占其所持股份比例(%) |
| share_type | string | 质押股份类型 |
| is_pledged_repo | int32 | 是否质押式回购(0表示否，1表示是) |
| hold_shares | float | 持股总数(万股) |
| hold_ratio | float | 持股占总股本比例(%) |
| acc_pledged_shares | float | 累计质押股数(万股) |
| acc_pledged_hold_ratio | float | 累计质押占所持股份比例(%) |
| acc_pledge_total_ratio | float | 累计质押占公司总股本比例(%) |
| pledge_begin_date | string | 质押起始日期 |
| release_date | string | 解押日期 |
| is_released | int32 | 是否解押(0表示否，1表示是) |
| note | string | 相关说明 |
| pledge_end_date | string | 质押截止日期 |

示例：获取所有股票一段时间内的公司股权质押情况并使用fields

```python
import panda_data
result = panda_data.get_stock_pledge(
    symbol="",
    start_date="20250101",
    end_date="20260101",
    fields=["hold_shares","hold_ratio"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | publish_date | hold_shares | hold_ratio |
|:---|:---|:---|:---|
| 000009.SZ | 20250121 | 41315.0033 | 16.02 |
| 000009.SZ | 20250212 | 41315.0033 | 16.02 |
| 000009.SZ | 20250530 | 12616.3313 | 29.27 |

### get_stock_pledge_stat：获取股票质押信息统计

数据范围 2021-03-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=92)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| data_source | string | 数据来源 |
| pledge_begin_date | string | 起始日期 |
| pledge_end_date | string | 结束日期 |
| unrestricted_avg_pledge_ratio | float | 无限售条件股份平均质押率 |
| restricted_avg_pledge_ratio | float | 有限售条件股份平均质押率 |
| pledge_number | float | 质押笔数 |
| pledge_volume | float | 质押数量 |
| init_amount | float | 初始交易金额 |
| repurchase_amount | float | 购回交易金额 |

示例：获取一段时间内股票质押信息统计

```python
import panda_data
result = panda_data.get_stock_pledge_stat(
    start_date="20250101",
    end_date="20260101",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| pledge_begin_date | pledge_end_date | data_source | unrestricted_avg_pledge_ratio | restricted_avg_pledge_ratio | pledge_number | pledge_volume | init_amount | repurchase_amount |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 20250102 | 20250102 | 中国证券登记结算有限责任公司 | None | None | None | None | 0.0 | 94082605.78 |
| 20250102 | 20250102 | 深交所 | None | None | None | None | 430000000.0 | 37000000.0 |
| 20250103 | 20250103 | 中国证券登记结算有限责任公司 | None | None | None | None | 50000000.0 | 189347494.14 |

### get_stock_shareholder_change：获取股东增减持计划

数据范围 2021-01-30 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=94)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票名 |
| info_date | string | 公告日期 |
| first_info_date | string | 首次公告日期 |
| progress | string | 进度 |
| begin_date | string | 增减持计划起始日期 |
| end_date | string | 增减持计划截止日期 |
| shareholder_name | string | 股东名称 |
| shareholder_type | string | 股东类型 |
| direction | string | 变动方向 |
| before_hold | float | 变动前持股数 |
| change_up_limit | float | 变动数量上限 |
| ratio_up_limit | float | 占总股本比例上限 |
| reason | string | 变动原因 |
| value_up_limit | float | 预计金额上限 |
| value_down_limit | float | 预计金额下限 |
| ratio_down_limit | float | 占总股本比例下限 |
| change_down_limit | float | 变动数量下限 |
| price_down_limit | float | 价格下限 |
| price_up_limit | float | 价格上限 |
| trigger_condition | string | 触发条件说明 |
| trigger_price | float | 触发价格 |
| trigger_days | float | 连续天数 |

示例：获取所有股票一段时间内的股东增减持计划

```python
import panda_data
result = panda_data.get_stock_shareholder_change(
    symbol="",
    start_date="20250101",
    end_date="20260101",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | info_date | name | first_info_date | progress | begin_date | end_date | shareholder_name | shareholder_type | direction | before_hold | change_up_limit | ratio_up_limit | reason | value_up_limit | value_down_limit | ratio_down_limit | change_down_limit | price_down_limit | price_up_limit | trigger_condition | trigger_price | trigger_days |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000009.SZ | 20250214 | 中国宝安 | 20241104 | 已完成 | 20241125 | 20250224 | 深圳市富安控股有限公司 | 股东 | 减持 | 133485316.0 | 25792139.0 | 1.0 | 经营发展资金需求 | None | None | None | None | None | None | None | None | None |
| 000021.SZ | 20250221 | 深科技 | 20241102 | 已完成 | 20241125 | 20250222 | 博旭(香港)有限公司 | 股东 | 减持 | 87387217.0 | 10924100.0 | 0.7 | 资金需求 | None | None | None | None | None | None | None | None | None |
| 000021.SZ | 20251230 | 深科技 | 20251205 | 已完成 | 20251227 | 20260326 | 钟彦 | 高管 | 减持 | 89100.0 | 22000.0 | 0.0014 | 个人资金需求 | None | None | None | None | None | None | None | None | None |

### get_stock_equity_placard：获取被举牌公司明细

数据范围 2013-01-09 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=266)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| start_date | string | 是 | 查询起始日期（公告日期），格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期（公告日期），格式为 "YYYYMMDD" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票简称 |
| info_date | string | 公告日期 |
| shareholder_name | string | 股东名称 |
| shareholder_type | string | 股东类型 |
| actual_controller | string | 股东实际控制人 |
| begin_date | string | 变动起始日期 |
| end_date | string | 变动截止日期 |
| increase_num | integer | 本次增持数量 |
| total_share_ratio | float | 占总股本比例(%) |
| average_price | float | 本次交易均价 |
| price_note | string | 本次交易均价说明 |
| share_holding | long | 变动后持股总数 |
| share_holding_ratio | float | 变动后持股比例(%) |
| increase_plan | string | 未来12个月内是否拟继续增持 |

示例：获取一定日期范围内所有被举牌公司明细的部分字段数据

```python
import panda_data
result = panda_data.get_stock_equity_placard(
    symbol="",
    start_date="20240101",
    end_date="20240131",
    fields=["symbol","info_date","name","shareholder_name","increase_num","total_share_ratio","average_price"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | info_date | name | shareholder_name | increase_num | total_share_ratio | average_price |
|:---|:---|:---|:---|:---|:---|:---|
| 000812.SZ | 20240131 | 陕西金叶 | 陈启来 | 8660000 | 1.1266 | 5.6 |
| 001267.SZ | 20240103 | 汇绿生态 | 李晓伟 | 50000 | 0.0064 | 5.2 |
| 002117.SZ | 20240125 | 东港股份 | 费占军,张靖华,费战武,刘秀敏,白江涛,新天科技股份有限公司 | 5404957 | 0.9906 | 7.3 |

## 股东结构

### get_stock_equity_nature：获取个股企业性质

数据范围 1990-12-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=267)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票简称 |
| full_name | string | 股票全称 |
| company_nature | string | 公司性质 |
| introduction | string | 公司介绍 |

示例：获取一定日期范围内全部个股企业性质的部分字段信息

```python
import panda_data
result = panda_data.get_stock_equity_nature(
    symbol="",
    fields=["symbol","name","full_name","company_nature"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | name | full_name | company_nature |
|:---|:---|:---|:---|
| 000001.SZ | 平安银行 | 平安银行股份有限公司 | 公众企业 |
| 000002.SZ | 万科A | 万科企业股份有限公司 | 公众企业 |
| 000003.SZ | PT金田A | 金田实业(集团)股份有限公司 | 公众企业 |
