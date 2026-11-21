---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - A-Share Financial Reports
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# A股财务

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 业绩预告

### get_fina_forecast：获取业绩预告数据

数据范围 1999-01-08 ~ 至今；每日更新 08:21 ~ 08:41；[官方页面](https://www.pandaaiquant.com/docs/api?id=33)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| info_date | Optional[string] | 否 | 信息发布日期，格式为 "YYYYMMDD" |
| end_quarter | Optional[string] | 否 | 报告季度，格式为 "YYYYqN" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| info_date | string | 信息发布日期 |
| end_date | string | 报告日期 |
| forecast_type | string | 整体业绩预期 |
| forecast_description | string | 业绩预期时间段描述 |
| forecast_growth_rate_floor | float | 最小预期增长幅度 |
| forecast_growth_rate_ceiling | float | 最大预期增长幅度 |
| forecast_earning_floor | float | 最小预期收入 |
| forecast_earning_ceiling | float | 最大预期收入 |
| forecast_np_floor | float | 最小预期净利润 |
| forecast_np_ceiling | float | 最大预期净利润 |
| forecast_eps_floor | float | 最小预期每股 |
| forecast_eps_ceiling | float | 最大预期每股收益 |
| net_profit_yoy_const_forecast | float | 一致预期净利润增幅 |
| forecast_ne_ceiling | float | 最小预测归母股东权益 |
| forecast_ne_floor | float | 最大预测归母股东权益 |

示例：获取一定日期后某只股票的业绩预告数据

```python
import panda_data
result = panda_data.get_fina_forecast(
    symbol="688795.SH",
    info_date="20251128",
    end_quarter="2025q4",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | info_date | end_date | forecast_description | forecast_earning_ceiling | forecast_earning_floor | forecast_eps_ceiling | forecast_eps_floor | forecast_growth_rate_ceiling | forecast_growth_rate_floor | forecast_np_ceiling | forecast_np_floor | forecast_type | net_profit_yoy_const_forecast | forecast_ne_ceiling | forecast_ne_floor |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 688795.SH | 20251128 | 20251231 | 累计利润 | None | None | None | None | 54.89 | 27.82 | -730000000.0 | -1168000000.0 | 减亏 | None | None | None |

## 财务三表、财务快报

### get_fina_performance：获取财务快报数据

数据范围 2004-02-19 ~ 至今；每日更新 08:23 ~ 08:43；[官方页面](https://www.pandaaiquant.com/docs/api?id=34)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |
| info_date | Optional[string] | 否 | 信息发布日期，格式为 "YYYYMMDD" |
| end_quarter | Optional[string] | 否 | 报告季度，格式为 "YYYYqN" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| info_date | string | 信息发布日期 |
| end_date | string | 报告日期 |
| operating_revenue | float | 营业收入或主营业务收入(元) |
| gross_profit | float | 主营业务利润(元) |
| operating_profit | float | 营业利润(元) |
| total_profit | float | 利润总额(元) |
| net_profit_parent | float | 归属母公司净利润(元) |
| net_profit_excluding_nonrecurring | float | 扣除非经常性损益后净利润(元) |
| net_cash_flow_operating | float | 经营活动现金流量净额(元) |
| total_assets | float | 总资产(元) |
| equity_parent_common | float | 归属母公司普通股东权益(元) |
| equity_parent | float | 归属母公司股东权益(元) |
| total_shares | float | 总股本(股) |
| basic_eps | float | 基本每股收益 |
| eps_weighted | float | 每股收益(加权)(元) |
| eps_excluding_nonrecurring | float | 每股收益(扣除)(元) |
| eps_excluding_nonrecurring_weighted | float | 每股收益(扣除加权)(元) |
| roe_diluted | float | 净资产收益率(摊薄)(%) |
| roe_weighted | float | 净资产收益率(加权)(%) |
| roe_excluding_nonrecurring_diluted | float | 净资产收益率(扣除摊薄)(%) |
| roe_excluding_nonrecurring_weighted | float | 净资产收益率(扣除加权)(%) |
| cf_operating_per_share | float | 每股经营活动现金流量净额(元) |
| bvps | float | 每股净资产(元) |
| operating_revenue_yoy | float | 主营业务收入同比(%) |
| gross_profit_yoy | float | 主营业务利润同比(%) |
| operating_profit_yoy | float | 营业利润同比(%) |
| total_profit_yoy | float | 利润总额同比(%) |
| net_profit_parent_yoy | float | 归属母公司净利润同比(%) |
| net_profit_excluding_nonrecurring_yoy | float | 扣除非经常性损益后净利润同比(%) |
| net_cash_flow_operating_yoy | float | 经营活动现金流量净额同比(%) |
| total_assets_growth_rate | float | 总资产较期初比(%) |
| equity_parent_growth_rate | float | 归属母公司股东权益较期初比(%) |
| basic_eps_yoy | float | 每股收益(摊薄) 同比(%) |
| eps_weighted_yoy | float | 每股收益(加权) 同比(%) |
| eps_excluding_nonrecurring_yoy | float | 每股收益(扣除) 同比(%) |
| eps_excluding_nonrecurring_weighted_yoy | float | 每股收益(扣除加权) 同比(%) |
| roe_diluted_yoy | float | 净资产收益率(摊薄) 同比(%) |
| roe_weighted_yoy | float | 净资产收益率(加权) 同比(%) |
| roe_excluding_nonrecurring_diluted_yoy | float | 净资产收益率(扣除摊薄) 同比(%) |
| roe_excluding_nonrecurring_weighted_yoy | float | 净资产收益率(扣除加权) 同比(%) |
| cf_operating_per_share_yoy | float | 每股经营活动现金流量净额同比(%) |
| bvps_growth_rate | float | 每股净资产较期初比(%) |

示例：获取一定日期内某只股票的财务快报数据且使用fields

```python
import panda_data
result = panda_data.get_fina_performance(
        info_date="20251107",
        symbol="688235.SH",
        end_quarter="2025q4",
        fields=["symbol", "info_date", "end_date", "basic_eps", "eps_excluding_nonrecurring",
                "net_profit_excluding_nonrecurring_yoy", "net_profit_parent"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | info_date | basic_eps | end_date | net_profit_parent | eps_excluding_nonrecurring | net_profit_excluding_nonrecurring_yoy |
|:---|:---|:---|:---|:---|:---|:---|
| 688235.SH | 20251107 | 0.81 | 20250930 | 1138596000.0 | 0.6292 | 124.295951 |

### get_fina_reports：获取财务季度报告

数据范围 2000-08-25 ~ 至今；每日更新 04:31 ~ 04:51；[官方页面](https://www.pandaaiquant.com/docs/api?id=35)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票名称 |
| start_quarter | string | 是 | 起始季度，格式为 "YYYYqN" |
| end_quarter | string | 是 | 结束季度，格式为 "YYYYqN" |
| date | Optional[string] | 否 | 公告日期,返回该日期及之前的数据 |
| is_latest | Optional[boolean] | 否 | True：返回最新披露数据，False：返回全部。默认为True |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| fields | float | 财务字段，详见下载文件 |
| quarter | string | 季度 |
| if_adjusted | integer | 是否为当期财报数据，0为当期，1为非当期 |

示例：获取一定季度内某只股票的财务季度报告且使用fields

```python
import panda_data
result = panda_data.get_fina_reports(
    symbol="688795.SH",
    date="20251114",
    start_quarter="2024q1",
    end_quarter="2026q1",
    is_latest=False,
    fields=["symbol", "date", "quarter", "bs_acct_payable", "is_adj_credit_impair",
            "cfs_cash_inflow_operating", "cfs_cash_oth_operating"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | quarter | date | bs_acct_payable | is_adj_credit_impair | cfs_cash_inflow_operating | cfs_cash_oth_operating |
|:---|:---|:---|:---|:---|:---|:---|
| 688795.SH | 2024q2 | 20251114 | None | None | None | None |
| 688795.SH | 2024q2 | 20251114 | None | None | None | None |
| 688795.SH | 2024q2 | 20251114 | None | None | None | None |

### get_audit_opinion：获取财务报告审计意见

数据范围 2023-04-07 ~ 2025-12-31；每日更新 停更；[官方页面](https://www.pandaaiquant.com/docs/api?id=41)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_quarter | Optional[string] | 否 | 开始季度,eg:"2025q1" |
| end_quarter | Optional[string] | 否 | 结束季度,eg:"2025q3" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| market | Optional[string] | 否 | 市场,默认"cn"为中国内地市场 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 公告发布日 |
| symbol | string | 股票代码 |
| quarter | string | 报告季度 |
| audit_type | string | 审计报告类型 |
| agency | string | 会计师事务所 |
| opinion | string | 审计意见 |

示例：获取一定报告期内某只股票的财务报告审计意见数据

```python
import panda_data
result = panda_data.get_audit_opinion(
    symbol="000001.SZ",
    start_quarter="2024q1",
    end_quarter="2025q3",
    market="cn",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | quarter | date | agency | audit_type | opinion |
|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 2024q1 | 20240420 | None | financial_statements | no_audit_performed |
| 000001.SZ | 2024q2 | 20240816 | None | financial_statements | no_audit_performed |
| 000001.SZ | 2024q3 | 20241019 | None | financial_statements | no_audit_performed |
