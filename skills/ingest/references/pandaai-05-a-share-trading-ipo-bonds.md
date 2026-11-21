---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - A-Share Trading Flows, IPOs and Convertible Bonds
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# A股交易与资金、新股、可转债

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 市场交易与资金数据

### get_lhb_list：获取股票龙虎榜数据

数据范围 1997-02-26 ~ 至今；每日更新 18:54 ~ 19:14；[官方页面](https://www.pandaaiquant.com/docs/api?id=12)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，如 "000001.SZ" |
| type | Optional[Union[string, List[string]]] | 否 | 龙虎榜类型 |
| start_date | Optional[string] | 是 | 开始日期，格式 "YYYYMMDD" |
| end_date | Optional[string] | 是 | 结束日期，格式 "YYYYMMDD" |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 龙虎榜日期 |
| type | string | 龙虎榜类型（见下表） |
| reason | string | 龙虎榜原因 |
| amount | float | 龙虎榜金额 |
| volume | float | 龙虎榜数量 |
| amplitude | float | 龙虎榜振幅 |
| change_rate | float | 龙虎榜涨跌幅 |
| deviation | float | 龙虎榜涨跌幅偏离值 |
| turnover | float | 龙虎榜换手率 |
| start_date | string | 异动开始日期 |
| end_date | string | 异动结束日期 |

示例：获取一定日期内某一类型所有股票龙虎榜数据

```python
import panda_data
result = panda_data.get_lhb_list(
    start_date="20250101",
    end_date="20250131",
    type="G0007",
    symbol="",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | type | amount | amplitude | change_rate | deviation | end_date | reason | start_date | turnover | volume |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000016.SZ | 20250116 | G0007 | 2465160000.0 | None | None | 0.0956 | 20250116 | 日涨幅偏离值达7% | 20250116 | None | 390440000.0 |
| 000063.SZ | 20250109 | G0007 | 14480340000.0 | None | None | 0.097 | 20250109 | 日涨幅偏离值达7% | 20250109 | None | 391500000.0 |
| 000533.SZ | 20250103 | G0007 | 1713400000.0 | None | None | 0.1266 | 20250103 | 日涨幅偏离值达7% | 20250103 | None | 240090000.0 |

### get_lhb_detail：获取股票龙虎榜明细数据

数据范围 1997-02-26 ~ 至今；每日更新 18:57 ~ 19:17；[官方页面](https://www.pandaaiquant.com/docs/api?id=13)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，如 "000001.SZ" |
| type | Optional[Union[string, List[string]]] | 否 | 龙虎榜类型 |
| start_date | string | 是 | 开始日期，格式 "YYYYMMDD" |
| end_date | string | 是 | 结束日期，格式 "YYYYMMDD" |
| side | Optional[string] | 否 | 买卖方向，可选值为 "buy" 或 "sell" 或 "cum"，其中"cum"类型记录发生严重异常时的累计数据，与具体买卖方向无关 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 龙虎榜日期 |
| type | string | 龙虎榜类型(同前) |
| side | string | 买卖方向 |
| rank | integer | 龙虎榜排名 |
| agency | string | 营业部名称 |
| b_value | float | 买入金额 |
| s_value | float | 卖出金额 |
| reason | string | 龙虎榜原因 |

示例：获取某只股票卖方向龙虎榜明细

```python
import panda_data
result = panda_data.get_lhb_detail(
    symbol="001314.SZ",
    start_date="20250101",
    end_date="20250131",
    type="T0020",
    side="sell",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | side | rank | agency | b_value | reason | s_value | type |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 001314.SZ | 20250102 | sell | 1 | 机构专用 | 11812524.0 | 日换手率达20% | 26823835.0 | T0020 |
| 001314.SZ | 20250102 | sell | 2 | 华福证券有限责任公司晋江崇德路证券营业部 | 0.0 | 日换手率达20% | 22097296.0 | T0020 |
| 001314.SZ | 20250102 | sell | 3 | 招商证券股份有限公司深圳福民路证券营业部 | 634264.0 | 日换手率达20% | 21181533.0 | T0020 |

### get_margin：获取融资融券信息

数据范围 2010-03-31 ~ 至今；每日更新 09:08 ~ 09:28；[官方页面](https://www.pandaaiquant.com/docs/api?id=37)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| margin_type | Optional[string] | 否 | 买卖方向，"stock" 代表融券卖出，"cash" 代表融资买入 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| short_sell_quantity | float | 融券卖出量 |
| buy_on_margin_value | float | 融资买入额 |
| date | string | 日期 |
| margin_repayment | float | 融券偿还额 |
| short_balance | float | 融券余额 |
| margin_balance | float | 融资余额 |
| symbol | string | 股票代码 |
| short_balance_quantity | float | 融券余量 |
| short_repayment_quantity | float | 融券偿还量 |
| margin_type | string | 买卖方向，"stock" 代表融券卖出，"cash" 代表融资买入 |
| total_balance | float | 总余额 |

示例：获取一定日期内某只股票的融资融券信息

```python
import panda_data
result = panda_data.get_margin(
        symbol="000001.SZ",
        start_date="20250101",
        end_date="20250131",
        margin_type="stock",
        fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | short_balance | margin_balance | short_repayment_quantity | short_sell_quantity | total_balance | buy_on_margin_value | margin_type | margin_repayment | short_balance_quantity |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20250102 | 3665601.0 | 4659469716.0 | 176100.0 | 21000.0 | 4663135317.0 | 359418283.0 | stock | 280885137.0 | 320700.0 |
| 000001.SZ | 20250103 | 3304752.0 | 4669652607.0 | 53500.0 | 23200.0 | 4672957359.0 | 169639270.0 | stock | 159456379.0 | 290400.0 |
| 000001.SZ | 20250106 | 4452448.0 | 4669211757.0 | 21400.0 | 120200.0 | 4673664205.0 | 155556810.0 | stock | 155997660.0 | 389200.0 |

### get_hsgt_hold：获取沪深股通持股信息（北向资金）

数据范围 2017-03-17 ~ 至今；每日更新 08:41 ~ 09:01；[官方页面](https://www.pandaaiquant.com/docs/api?id=38)

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
| date | string | 日期 |
| shares_num | float | 持股数量 |
| symbol | string | 股票代码 |
| adjusted_holding_ratio | float | 调整后持股比例 |
| holding_ratio | float | 持股比例 |

示例：获取一定日期内某只股票的沪深股通持股信息

```python
import panda_data
result = panda_data.get_hsgt_hold(
    symbol="000001.SZ",
    start_date="20250601",
    end_date="20250630",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| adjusted_holding_ratio | symbol | date | holding_ratio | shares_num |
|:---|:---|:---|:---|:---|
| 4.2726 | 000001.SZ | 20250630 | 4.27 | 829114531.0 |

### get_stock_flow：获取资金流入流出数据

数据范围 2010-01-01 ~ 至今；每日更新 17:59 ~ 18:39；[官方页面](https://www.pandaaiquant.com/docs/api?id=311)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表，格式如 "000001.SZ"；列表内不允许重复 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD"，且不能晚于 end_date |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD"，且不能早于 start_date |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段，可以是单个字符串或字符串列表；列表内不允许重复，为 None、空列表或空字符串时返回全部字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 交易日期，格式为 YYYYMMDD |
| b_value | float | 买入金额 |
| b_volume | float | 买入数量 |
| s_value | float | 卖出金额 |
| s_volume | float | 卖出数量 |

示例：获取单只股票一定时间内的资金流数据

```python
import panda_data
result = panda_data.get_stock_flow(
    symbol="000001.SZ",
    start_date="20260101",
    end_date="20260301",
    fields=[""]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | b_value | b_volume | s_value | s_volume |
|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20260105 | 5.098307e+08 | 44473672.0 | 493648488.0 | 43075446.0 |
| 000001.SZ | 20260106 | 9.804963e+08 | 84545906.0 | 532415288.0 | 45918936.0 |
| 000001.SZ | 20260107 | 5.377515e+08 | 45921725.0 | 593414239.0 | 50701899.0 |

## 新股发行

### get_stock_ipo_first_day：获取IPO 上市首日表现数据

数据范围 2015-01-20 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=370)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，单个或列表，如 "688981.SH" |
| start_date | string | 是 | 查询起始日期（按上市日期），格式 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期（按上市日期），格式 "YYYYMMDD" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段子集；传空返回全部列，传子集时必返字段 symbol、date 仍会返回 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码，如 688981.SH |
| date | string | 上市日期 YYYYMMDD |
| name | string | 证券简称 |
| stock_type | string | 股票类型：A=A股，B=B股 |
| open | float | 上市首日开盘价（元） |
| high | float | 上市首日最高价（元） |
| low | float | 上市首日最低价（元） |
| close | float | 上市首日收盘价（元） |
| volume | float | 上市首日成交量（股） |
| amount | float | 上市首日成交额（元） |
| pe | float | 上市首日市盈率（约 71% 有值，缺失返回 None） |
| pb | float | 上市首日市净率（约 97% 有值，缺失返回 None） |
| turnover | float | 上市首日换手率（注意：是换手率，不是成交额） |

示例：获取一段时间内全市场 IPO 上市首日表现

```python
import panda_data
result = panda_data.get_stock_ipo_first_day(
        start_date="20250101",
        end_date="20250131",
        fields=['symbol','date','pe','pb','turnover']
    )
print(result)
```

返回示例（前 3 行）：

| symbol | date | pe | pb | turnover |
|:---|:---|:---|:---|:---|
| 001356.SZ | 20250123 | 63.3885 | 10.8345 | 0.8041 |
| 001395.SZ | 20250127 | 26.3672 | 6.424 | 0.7657 |
| 301458.SZ | 20250110 | 82.0182 | 10.1997 | 0.7592 |

### get_stock_ipo_listing：获取新股上市数据

数据范围 2015-01-20 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=371)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，单个或列表，如 "688981.SH" |
| start_date | string | 是 | 查询起始日期（按上市日期），格式 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期（按上市日期），格式 "YYYYMMDD" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段子集；传空返回全部列，传子集时必返字段 symbol、date 仍会返回 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码，如 688981.SH |
| date | string | 上市日期 YYYYMMDD |
| name | string | 证券简称 |
| issue_price | float | 发行价格（元） |
| board_type | string | 上市板块类别：主板 / 创业板 / 科创板 / 北交所 |

示例：获取一段时间内全市场新股上市数据

```python
import panda_data
result = panda_data.get_stock_ipo_listing(
    start_date="20250101",
    end_date="20250131",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | issue_price | board_type |
|:---|:---|:---|:---|:---|
| 001356.SZ | 20250123 | 富岭股份 | 5.3 | 主板 |
| 001395.SZ | 20250127 | 亚联机械 | 19.08 | 主板 |
| 301458.SZ | 20250110 | 钧崴电子 | 10.4 | 创业板 |

### get_stock_ipo_offline_bid：获取新股网下询价明细

数据范围 2015-01-09 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=369)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，单个或列表 |
| start_date | string | 是 | 查询起始日期（按询价结果公布日期），格式 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期（按询价结果公布日期），格式 "YYYYMMDD" |
| investor_name | Optional[Union[string, List[string]]] | 否 | 询价机构（配售对象管理人）名称过滤，单个或列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段子集；传空返回全部列，传子集时必返字段 symbol、date、investor_name、org_name 仍会返回（单只新股上万行，缺这两列无法定位到行） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 询价结果公布日期 YYYYMMDD |
| name | string | 证券简称 |
| investor_name | string | 询价机构名称（配售对象的管理人），如 易方达基金管理有限公司 |
| org_name | string | 配售对象名称（具体产品），如 易方达颐年配置混合型养老金产品 |
| bid_price | float | 申报价格（元） |
| bid_shares | float | 申报数量（股） |

示例：按 symbol 取指定新股的网下询价明细

```python
import panda_data
result = panda_data.get_stock_ipo_offline_bid(
    symbol="688411.SH",
    start_date="20250101",
    end_date="20250131",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | investor_name | org_name | bid_price | bid_shares |
|:---|:---|:---|:---|:---|:---|:---|
| 688411.SH | 20250115 | 海博思创 | 上海东方证券资产管理有限公司 | 东方红中国优势灵活配置混合型证券投资基金 | 19.59 | 13000000.0 |
| 688411.SH | 20250115 | 海博思创 | 上海东方证券资产管理有限公司 | 东方红中证东方红红利低波动指数证券投资基金 | 19.59 | 13000000.0 |
| 688411.SH | 20250115 | 海博思创 | 上海东方证券资产管理有限公司 | 东方红京东大数据灵活配置混合型证券投资基金 | 19.59 | 13000000.0 |

### get_stock_ipo_offline_stat：获取新股网下配售统计数据

数据范围 2015-01-14 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=368)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，单个或列表 |
| start_date | string | 是 | 查询起始日期（按配售结果公布日期），格式 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期（按配售结果公布日期），格式 "YYYYMMDD" |
| investor_type | Optional[Union[string, List[string]]] | 否 | 投资者类别过滤，如 "1"/"2"/"3"，单个或列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段子集；传空返回全部列，传子集时必返字段 symbol、date、investor_type 仍会返回 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 配售结果公布日期 YYYYMMDD |
| name | string | 证券简称 |
| investor_type | string | 投资者类别：1=A类投资者，2=B类投资者，3=C类投资者，4=D类投资者，5=F类投资者，6=I类投资者 |
| offline_apply_shares | float | 网下申购数量（股） |
| offline_issued_shares | float | 网下发行股数（股） |
| apply_ratio | float | 占有效申购数量比例 |
| initial_ratio | float | 初步配售比例（%） |
| offline_place_ratio | float | 占网下发行总量比例（%） |

示例：按 symbol 取指定新股的网下配售统计（按投资者类别拆）

```python
import panda_data
result = panda_data.get_stock_ipo_offline_stat(
    symbol="688411.SH",
    start_date="20250101",
    end_date="20250131",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | investor_type | offline_apply_shares | offline_issued_shares | apply_ratio | initial_ratio | offline_place_ratio |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 688411.SH | 20250120 | 海博思创 | 1 | 39783000000.0 | 17109528.0 | 73.54 | 0.043007 | 75.02 |
| 688411.SH | 20250120 | 海博思创 | 2 | 14316700000.0 | 5698026.0 | 26.46 | 0.0398 | 24.98 |

### get_stock_ipo_offline_placing：获取新股网下发行配售结果

数据范围 2015-01-14 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=367)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，单个或列表 |
| start_date | string | 是 | 查询起始日期（按网上发行日期），格式 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期（按网上发行日期），格式 "YYYYMMDD" |
| org_name | Optional[Union[string, List[string]]] | 否 | 配售对象名称过滤，单个或列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段子集；传空返回全部列，传子集时必返字段 symbol、date、org_name 仍会返回（单只新股上万行，配售对象名是唯一可读定位列） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 网上发行日期 YYYYMMDD |
| name | string | 证券简称 |
| org_name | string | 配售对象名称（具体产品/计划） |
| org_type | string | 配售对象类型：1=QFII机构，2=保险机构，3=财务公司，4=公募基金，5=企业年金，6=机构投资账户，7=基金，8=券商，9=个人投资者，10=社保账户，11=私募基金，12=信托公司，13=银行，15=资产管理计划；2011 年前上市的股票无此字段，返回 None |
| investor_type | string | 投资者类别：1=A类投资者，2=B类投资者（取值与 get_stock_ipo_offline_stat 同一套）；2011 年前上市的股票无此字段，返回 None |
| valid_apply_shares | float | 有效申购数量（股） |
| place_shares | float | 获配数量（股） |
| refund_amount | float | 退款金额；仅 2002-2011 年上市的股票有值，其余返回 None |
| limit_period | float | 锁定期限；仅 2002-2011 年上市的股票有值，其余返回 None |

示例：按 symbol 取指定新股的网下发行配售结果

```python
import panda_data
result = panda_data.get_stock_ipo_offline_placing(
    symbol="688411.SH",
    start_date="20250101",
    end_date="20250131",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | org_name | org_type | investor_type | valid_apply_shares | place_shares | refund_amount | limit_period |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 688411.SH | 20250120 | 海博思创 | 中国电力建设集团有限公司企业年金计划-中国建设银行股份有限公司 | 5 | 1 | 13000000.0 | 5591.0 | None | None |
| 688411.SH | 20250120 | 海博思创 | 招商沪深300增强策略交易型开放式指数证券投资基金 | 4 | 1 | 13000000.0 | 5591.0 | None | None |
| 688411.SH | 20250120 | 海博思创 | 财通科创主题3年封闭运作灵活配置混合型证券投资基金 | 4 | 1 | 11000000.0 | 4730.0 | None | None |

### get_stock_ipo_issuance：获取股票首次上市信息

数据范围 2015-01-20 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=366)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，单个或列表，如 "688981.SH" |
| start_date | string | 是 | 查询起始日期（按上市日期），格式 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期（按上市日期），格式 "YYYYMMDD" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段子集；传空返回全部列，传子集时必返字段 symbol、date 仍会返回 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码，如 688981.SH |
| date | string | 上市日期 YYYYMMDD |
| name | string | 证券简称 |
| announcement_date | string | 公告日期 YYYYMMDD |
| issue_status | string | 发行进度/状态：9=上市，10=撤销上市，11=正在发行，12=暂缓发行，13=发行结束待上市，1=董事会预案，2=股东大会通过，3=股东大会否决，4=证监会核准，5=证监会否决，6=方案实施，7=停止实施，8=延期实施，93=实施，94=预案预披露，95=董事会否决，96=方案中止，97=方案终止，98=中止/撤销发行，99=证监会中止，100=证监会终止，101=董事会无法表决 |
| online_issue_date | string | 网上发行日期 YYYYMMDD |
| issue_price | float | 发行价格（元） |
| currency | string | 货币单位 |
| issue_shares | float | 发行总股数（股） |
| online_issue_shares | float | 网上发行股数（股） |
| offline_issued_shares | float | 网下发行股数（股）；无网下发行环节的股票返回 None |
| new_issue_shares | float | 新股发行数量（股） |
| actual_raising_amount | float | 募集资金总额（元） |
| issue_pe | float | 发行市盈率（约 86% 有值，缺失返回 None） |
| online_issue_lotto_ratio | float | 网上发行中签率 |
| online_issue_code | string | 网上申购代码 |
| open | float | 上市首日开盘价（元） |
| close | float | 上市首日收盘价（元） |
| online_sub_max | float | 网上单账户申购上限（股） |
| online_sub_min | float | 网上单笔申购下限（股） |
| issue_shares_plan_max | float | 计划发行股数上限（股） |
| issue_mode | string | 发行方式代码，存在逗号分隔的复合值，如 "0102,0810" |
| offline_apply_min | float | 网下申购下限（股）；约 30% 有值，无网下发行环节的股票返回 None |
| offline_sub_min | float | 网下单笔申购下限（股）；同上 |
| offline_sub_max | float | 网下单笔申购上限（股）；同上 |

示例：获取一段时间内全市场股票首次上市信息

```python
import panda_data
result = panda_data.get_stock_ipo_issuance(
    start_date="20250101",
    end_date="20250131",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | announcement_date | issue_status | online_issue_date | issue_price | currency | issue_shares | online_issue_shares | offline_issued_shares | new_issue_shares | actual_raising_amount | issue_pe | online_issue_lotto_ratio | online_issue_code | open | close | online_sub_max | online_sub_min | issue_shares_plan_max | issue_mode | offline_apply_min | offline_sub_min | offline_sub_max |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 001356.SZ | 20250123 | 富岭股份 | 20250103 | 9 | 20250114 | 5.3 | CNY | 147330000.0 | 87661500.0 | 37569000.0 | 147330000.0 | 780849000.0 | 14.17 | 0.000417 | 001356 | 22.22 | 23.28 | 37500.0 | 500.0 | 147330000.0 | 0706 | 60000000.0 | 1000000.0 | 43000000.0 |
| 001395.SZ | 20250127 | 亚联机械 | 20250108 | 9 | 20250116 | 19.08 | CNY | 21810000.0 | 15726500.0 | 3960859.0 | 21810000.0 | 416134800.0 | 17.08 | 0.000204 | 001395 | 65.0 | 49.5 | 7500.0 | 500.0 | 21810000.0 | 0706 | 60000000.0 | 1000000.0 | 5000000.0 |
| 301458.SZ | 20250110 | 钧崴电子 | 20241220 | 9 | 20241230 | 10.4 | CNY | 66666700.0 | 29910500.0 | 34640816.0 | 66666700.0 | 693333680.0 | 32.82 | 0.000224 | 301458 | 41.01 | 36.1 | 17000.0 | 500.0 | 66666700.0 | 0706 | 60000000.0 | 1000000.0 | 20000000.0 |

示例：按 symbol 取指定新股的首次上市信息

```python
import panda_data
result = panda_data.get_stock_ipo_issuance(
    symbol="688411.SH",
    start_date="20250101",
    end_date="20250131",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | announcement_date | issue_status | online_issue_date | issue_price | currency | issue_shares | online_issue_shares | offline_issued_shares | new_issue_shares | actual_raising_amount | issue_pe | online_issue_lotto_ratio | online_issue_code | open | close | online_sub_max | online_sub_min | issue_shares_plan_max | issue_mode | offline_apply_min | offline_sub_min | offline_sub_max |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 688411.SH | 20250127 | 海博思创 | 20250108 | 9 | 20250116 | 19.38 | CNY | 44432537.0 | 15126000.0 | 22807554.0 | 44432537.0 | 861102567.06 | 6.14 | 0.000329 | 787411 | 73.6 | 63.8 | 11000.0 | 500.0 | 44432537.0 | 0706 | 60000000.0 | 1000000.0 | 13000000.0 |

## 可转债

### get_bond_conv_basic：获取可转债发行基本资料

数据范围 2021-11-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=372)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 转债代码，如 "123254.SZ"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期（按发行公告日），格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期（按发行公告日），格式为 "YYYYMMDD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段，传子集时仍返回 symbol、date |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 转债代码，如 123254.SZ |
| date | str | 发行公告日，格式为 "YYYYMMDD" |
| name | str | 证券简称 |
| exchange | str | 交易市场编码，如 XSHG、XSHE、XBEI |
| stock_symbol | str | 基础股票代码 |
| pre_place_code | str | 老股东优先配售代码 |
| pre_place_name | str | 老股东优先配售名称 |
| online_place_code | str | 网上申购代码 |
| online_place_name | str | 网上申购名称 |
| pre_place_amount | double | 老股东优先配售总额 |
| online_issue_size | double | 网上发行总额 |
| online_place_valid_amount | double | 网上发行有效申购张数 |
| offline_issue_size | double | 网下发行总额 |
| lead_underwrite_size | double | 主承销商包销总额 |
| total_issue_cost | double | 发行费用总额 |
| issue_announce_date | str | 发行公告日，格式为 "YYYYMMDD" |
| result_announce_date | str | 发行结果公告日，格式为 "YYYYMMDD" |
| listing_announce_date | str | 上市公告日，格式为 "YYYYMMDD" |
| pre_place_record_date | str | 老股东优先配售股权登记日，格式为 "YYYYMMDD" |
| pre_place_pay_start_date | str | 老股东优先配售缴款起始日，格式为 "YYYYMMDD" |
| pre_place_pay_end_date | str | 老股东优先配售缴款截止日，格式为 "YYYYMMDD" |
| pre_place_ratio | double | 老股东优先配售比例 |
| pre_place_unit | double | 老股东优先配售单位 |
| pre_place_valid_amount | double | 老股东优先配售有效申购张数 |
| pre_place_oversub | double | 老股东优先超额认购倍数 |
| pre_place_succ_ratio | double | 老股东优先配售中签率 |
| online_issue_date | str | 网上发行日期，格式为 "YYYYMMDD" |
| online_place_unit | double | 网上申购单位 |
| online_place_max | double | 网上申购上限 |
| online_place_min | double | 网上申购下限 |
| online_place_valid_num | double | 网上发行有效申购户数 |
| online_place_oversub | double | 网上发行超额认购倍数 |
| online_place_succ_rate | double | 网上发行中签率 |
| coupon_rate_description | str | 票面利率说明 |
| initial_conversion_price | double | 初始转股价格 |
| initial_conversion_price_description | str | 初始转股价确定条款 |
| redeem_interest_compensation | double | 到期利息补偿 |
| redeem_coupon_rate | double | 到期补偿利率 |
| redeem_interest_compensation_description | str | 利息补偿条款 |
| update_time | str | 更新时间 |

示例：获取志邦转债发行资料

```python
import panda_data
result = panda_data.get_bond_conv_basic(
    symbol="113693.SH",
    start_date="20250301",
    end_date="20250331",
    fields=["name","stock_symbol","initial_conversion_price","online_issue_date"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | stock_symbol | initial_conversion_price | online_issue_date |
|:---|:---|:---|:---|:---|:---|
| 113693.SH | 20250314 | 志邦转债 | 603801.SH | 12.12 | 20250318 |

### get_bond_coupon：获取可转债券票面利率

数据范围 1993-01-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=375)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 转债代码，如 "123254.SZ"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期（按本段计息起始日），格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期（按本段计息起始日），格式为 "YYYYMMDD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段，传子集时仍返回 symbol、date |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 转债代码，如 123254.SZ |
| date | str | 本段计息起始日，格式为 "YYYYMMDD" |
| value_date | str | 本段计息起始日，格式为 "YYYYMMDD" |
| exchange | str | 交易市场编码，如 XSHG、XSHE、XBEI |
| name | str | 债券简称 |
| vendor_bond_id | str | 债券ID |
| value_end_date | str | 本段计息截止日，格式为 "YYYYMMDD" |
| rate_reset_date | str | 浮动利率计息基准日，格式为 "YYYYMMDD" |
| coupon_rate | double | 票面年利率 |
| accrual_start_date | str | 本周期计息起始日，格式为 "YYYYMMDD" |
| accrual_end_date | str | 本周期计息截止日，格式为 "YYYYMMDD" |

示例：获取永贵转债各计息段票面利率

```python
import panda_data
result = panda_data.get_bond_coupon(
    symbol="123253.SZ",
    start_date="20200101",
    end_date="20311231",
    fields=["coupon_rate","value_end_date"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | coupon_rate | value_end_date |
|:---|:---|:---|:---|
| 123253.SZ | 20250313 | 0.2 | 20260312 |
| 123253.SZ | 20260313 | 0.4 | 20270312 |
| 123253.SZ | 20270313 | 0.8 | 20280312 |

### get_bond_daily：获取可转债日行情

数据范围 2021-11-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=380)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 转债代码，如 "123254.SZ"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期（按交易日），格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期（按交易日），格式为 "YYYYMMDD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段，传子集时仍返回 symbol、date |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 转债代码，如 123254.SZ |
| date | str | 交易日期，格式为 "YYYYMMDD" |
| name | str | 债券简称 |
| exchange | str | 交易市场编码，如 XSHG、XSHE、XBEI |
| pre_close | double | 昨收盘 |
| open | double | 今开盘 |
| high | double | 最高价 |
| low | double | 最低价 |
| close | double | 收盘价 |
| volume | double | 成交量 |
| amount | double | 成交金额 |
| num_trades | double | 成交笔数 |
| accrued_interest | double | 应计利息 |
| vwap | double | 加权平均价 |
| gross_close_price | double | 收盘价（全价） |
| net_close_price | double | 净价 |
| is_open | double | 是否开盘，1 为开盘，0 为未开盘 |

示例：获取永贵转债日行情

```python
import panda_data
result = panda_data.get_bond_daily(
    symbol="123253.SZ",
    start_date="20260105",
    end_date="20260109",
    fields=["close","volume","amount"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | close | volume | amount |
|:---|:---|:---|:---|:---|
| 123253.SZ | 20260105 | 139.9 | 1158038.0 | 162253249.593 |
| 123253.SZ | 20260106 | 141.305 | 1113296.0 | 157153376.33 |
| 123253.SZ | 20260107 | 140.96 | 504739.0 | 71347872.089 |

### get_bond_cash_flow：获取可转债现金流数据

数据范围 2021-11-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=376)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 转债代码，如 "123254.SZ"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期（按现金流日期），格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期（按现金流日期），格式为 "YYYYMMDD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段，传子集时仍返回 symbol、date、cash_flow_type |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 转债代码，如 123254.SZ |
| date | str | 现金流日期，格式为 "YYYYMMDD" |
| cash_flow_type | str | 现金流类型 |
| exchange | str | 交易市场编码，如 XSHG、XSHE、XBEI |
| name | str | 债券简称 |
| interest_period | double | 计息周期 |
| accrual_start_date | str | 本周期计息起始日，格式为 "YYYYMMDD" |
| accrual_end_date | str | 本周期计息截止日，格式为 "YYYYMMDD" |
| payment_date | str | 现金流日期，格式为 "YYYYMMDD" |
| record_date | str | 债权登记日，格式为 "YYYYMMDD" |
| ex_dividend_date | str | 除权除息日，格式为 "YYYYMMDD" |
| interest_per_100_face_value | double | 每百元面额付息 |
| principal_per_100_face_value | double | 每百元面额兑付本金 |
| total_issue_size | double | 债券总额 |

示例：获取苏银转债现金流

```python
import panda_data
result = panda_data.get_bond_cash_flow(
    symbol="110053.SH",
    start_date="20220101",
    end_date="20261231",
    fields=["cash_flow_type","interest_per_100_face_value","principal_per_100_face_value"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | cash_flow_type | interest_per_100_face_value | principal_per_100_face_value |
|:---|:---|:---|:---|:---|
| 110053.SH | 20231020 | CAPINTPAY | 2.109589 | 100.0 |

### get_bond_conv_term：获取可转债转股条款

数据范围 1993-06-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=373)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 转债代码，如 "123254.SZ"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期（按转股起始日），格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期（按转股起始日），格式为 "YYYYMMDD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段，传子集时仍返回 symbol、date |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 转债代码，如 123254.SZ |
| date | str | 转股起始日，格式为 "YYYYMMDD" |
| name | str | 证券简称 |
| exchange | str | 交易市场编码，如 XSHG、XSHE、XBEI |
| conversion_code | str | 转股代码 |
| conversion_name | str | 转股简称 |
| conversion_start_date | str | 转股起始日，格式为 "YYYYMMDD" |
| conversion_end_date | str | 转股截止日期，格式为 "YYYYMMDD" |
| conversion_stop_date | str | 停止转股日，格式为 "YYYYMMDD" |
| conversion_price_adjustment_clause | str | 转股价格调整条款 |
| forced_conversion_clause | str | 强制性转股条款 |
| conversion_dividend_clause | str | 转换年度股利归属条款 |
| update_time | str | 更新时间 |
| trading_stop_date | str | 停止交易日，格式为 "YYYYMMDD" |
| trading_stop_announce_date | str | 停止交易公告日，格式为 "YYYYMMDD" |
| conversion_last_date | str | 最后转股日，格式为 "YYYYMMDD" |
| last_trading_date | str | 最后交易日，格式为 "YYYYMMDD" |

示例：获取永贵转债转股期限

```python
import panda_data
result = panda_data.get_bond_conv_term(
    symbol="123253.SZ",
    start_date="20200101",
    end_date="20261231",
    fields=["name","conversion_start_date","conversion_end_date"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | name | conversion_start_date | conversion_end_date |
|:---|:---|:---|:---|:---|
| 123253.SZ | 20250919 | 永贵转债 | 20250919 | 20310312 |

### get_bond_option：获取可转债选择权数据

数据范围 2003-08-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=379)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 转债代码，如 "123254.SZ"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期（按行权日），格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期（按行权日），格式为 "YYYYMMDD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段，传子集时仍返回 symbol、date、exercise_type |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 转债代码，如 123254.SZ |
| date | str | 行权日，格式为 "YYYYMMDD" |
| exercise_type | str | 选择权类型 |
| exchange | str | 交易市场编码，如 XSHG、XSHE、XBEI |
| name | str | 债券简称 |
| publish_date | str | 公告日期，格式为 "YYYYMMDD" |
| exercise_date | str | 行权日，格式为 "YYYYMMDD" |
| strike_price | double | 行权价格 |
| price_includes_accrued_interest | double | 价格是否包含应计利息 |
| min_exercise_amount | double | 最低行权金额 |
| application_start_date | str | 行权申请起始日，格式为 "YYYYMMDD" |
| application_end_date | str | 行权申请截止日，格式为 "YYYYMMDD" |
| payment_date | str | 资金到帐日，格式为 "YYYYMMDD" |
| application_code | str | 回售/赎回代码 |
| application_name | str | 回售/赎回简称 |
| exercise_amount | double | 赎回/回售金额 |
| interest_amount | double | 利息 |
| update_time | str | 更新时间 |
| exercise_result_announce_date | str | 行权结果公告日，格式为 "YYYYMMDD" |

示例：获取九州转债选择权

```python
import panda_data
result = panda_data.get_bond_option(
    symbol="110034.SH",
    start_date="20220101",
    end_date="20221231",
    fields=["exercise_type","strike_price","exercise_date"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | exercise_type | strike_price | exercise_date |
|:---|:---|:---|:---|:---|
| 110034.SH | 20220114 | CALL | 108.0 | 20220114 |

### get_bond_conv_price_change：获取可转债转股价变动数据

数据范围 1993-01-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=374)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 转债代码，如 "123254.SZ"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期（按转股价生效日），格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期（按转股价生效日），格式为 "YYYYMMDD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段，传子集时仍返回 symbol、date、change_reason_type |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 转债代码，如 123254.SZ |
| date | str | 转股价变动生效日，格式为 "YYYYMMDD" |
| change_reason_type | str | 变动原因类型 |
| name | str | 债券简称 |
| vendor_equ_sec_id | str | 正股证券ID |
| underlying_symbol | str | 正股代码 |
| underlying_short_name | str | 正股简称 |
| conversion_code | str | 申报转股代码 |
| conversion_name | str | 申报转股简称 |
| conversion_price | double | 转股价 |
| conversion_effective_date | str | 转股价变动生效日，格式为 "YYYYMMDD" |
| publish_date | str | 公告日期，格式为 "YYYYMMDD" |
| change_reason_desc | str | 变动原因 |
| cash_dividend_per_share | double | 每股派息 |
| previous_conversion_price | double | 变更前价格 |
| stock_dividend_ratio | double | 送股率 |
| capital_reserve_transfer_ratio | double | 转增比例 |
| allotment_price | double | 配股价 |
| allotment_ratio | double | 配股率 |
| spo_issue_price | double | 增发新股价 |
| spo_issue_ratio | double | 增发新股率 |
| other_price | str | 其他价格 |
| other_adjust_ratio | str | 其他比例 |
| announcement_id | str | 公告ID |
| download_time | str | 公告下载时间 |
| update_time | str | 更新时间 |

示例：获取永贵转债转股价变动

```python
import panda_data
result = panda_data.get_bond_conv_price_change(
    symbol="123253.SZ",
    start_date="20250301",
    end_date="20261231",
    fields=["conversion_price","change_reason_type"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | change_reason_type | conversion_price |
|:---|:---|:---|:---|
| 123253.SZ | 20250313 | 0100 | 18.29 |
| 123253.SZ | 20250604 | 0202 | 18.23 |
| 123253.SZ | 20250621 | 0401 | 18.23 |

### get_bond_conv_call_progress：获取可转债赎回进展数据

数据范围 2021-11-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=377)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 转债代码，如 "123254.SZ"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期（按交易日），格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期（按交易日），格式为 "YYYYMMDD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段，传子集时仍返回 symbol、date |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 转债代码，如 123254.SZ |
| date | str | 交易日，格式为 "YYYYMMDD" |
| name | str | 债券名称 |
| exchange | str | 交易市场编码，如 XSHG、XSHE、XBEI |
| underlying_symbol | str | 正股代码 |
| call_trigger_start_date | str | 赎回起始日，格式为 "YYYYMMDD" |
| trigger_condition | str | 触发条件 |
| bond_close | double | 转债价格 |
| underlying_close | double | 正股价格 |
| conversion_price | double | 转股价 |
| call_trigger_price | double | 触发价 |
| trigger_is_price | str | 正股价格触发标识 |
| trigger_type | str | 触发类型 |
| trigger_cum_days | double | 周期内累计触发天数 |
| trigger_reach_days | double | 赎回条件满足天数 |
| trigger_process | str | 触发进度 |
| trigger_begin_date | str | 满足触发条件起始日，格式为 "YYYYMMDD" |
| trigger_end_date | str | 满足触发条件截止日，格式为 "YYYYMMDD" |
| trigger_date | str | 触发日期，格式为 "YYYYMMDD" |
| call_clause | str | 赎回条款 |
| update_time | str | 更新时间 |

示例：获取永贵转债赎回进展

```python
import panda_data
result = panda_data.get_bond_conv_call_progress(
    symbol="123253.SZ",
    start_date="20260105",
    end_date="20260109",
    fields=["bond_close","underlying_close","conversion_price","trigger_process"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | bond_close | underlying_close | conversion_price | trigger_process |
|:---|:---|:---|:---|:---|:---|
| 123253.SZ | 20260105 | 139.9 | 18.15 | 18.23 | 0/15 |
| 123253.SZ | 20260106 | 141.305 | 18.38 | 18.23 | 0/15 |
| 123253.SZ | 20260107 | 140.96 | 18.09 | 18.23 | 0/15 |

### get_bond_conv_call_exec：获取可转债赎回执行数据

数据范围 2021-11-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=378)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 转债代码，如 "123254.SZ"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期（按赎回公告日），格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期（按赎回公告日），格式为 "YYYYMMDD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段，传子集时仍返回 symbol、date、call_type |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 转债代码，如 123254.SZ |
| date | str | 赎回公告日，格式为 "YYYYMMDD" |
| call_type | str | 赎回类型 |
| name | str | 债券简称 |
| exchange | str | 交易市场编码，如 XSHG、XSHE、XBEI |
| publish_date | str | 赎回公告日，格式为 "YYYYMMDD" |
| call_result_announce_date | str | 赎回结果公告日，格式为 "YYYYMMDD" |
| call_record_date | str | 赎回登记日，格式为 "YYYYMMDD" |
| call_execution_date | str | 赎回执行日，格式为 "YYYYMMDD" |
| call_payment_date | str | 资金到帐日，格式为 "YYYYMMDD" |
| call_gross_price | double | 赎回全价 |
| call_net_price | double | 赎回净价 |
| call_reason | str | 赎回原因 |
| trigger_begin_date | str | 股价触发起始日，格式为 "YYYYMMDD" |
| trigger_end_date | str | 股价触发截止日，格式为 "YYYYMMDD" |
| download_time | str | 公告下载时间 |

示例：获取九州转债赎回执行

```python
import panda_data
result = panda_data.get_bond_conv_call_exec(
    symbol="110034.SH",
    start_date="20220101",
    end_date="20221231",
    fields=["call_type","call_gross_price","call_net_price"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | call_type | call_gross_price | call_net_price |
|:---|:---|:---|:---|:---|
| 110034.SH | 20220112 | 1 | 108.0 | 100.0 |
