---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - Factors and Adjustment Factors
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# 量化因子与复权因子

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 回测因子

### get_factor：获取回测因子

数据范围 2000-01-04 ~ 至今；每日更新 05:27 ~ 05:47；[官方页面](https://www.pandaaiquant.com/docs/api?id=25)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| factors | Union[string, List[string]] | 是 | 因子列表，下述响应参数中列出的为基础因子，其余因子仅股票类型可用，详见下载文件 |
| type | Optional[string] | 否 | 产品类型，支持"stock" ,"future"，默认为"stock" |
| index_component | Optional[string] | 否 | 股票池，参考本文档概述部分部分中的股票池说明，默认为空表示查询所有 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 标的代码 |
| dominant_id | string | 主力合约代码（仅期货） |
| name | string | 股票名称（仅股票） |
| exchange | string | 交易所（仅期货） |
| trading_code | string | 交易代码（仅期货） |
| underlying_symbol | string | 期货品种（仅期货） |
| open | float | 开盘价 |
| day_session_open | float | 日盘开盘价（仅期货） |
| close | float | 收盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| volume | float | 成交量 |
| amount | float | 成交额 |
| market_cap | float | 市值（仅股票） |
| turnover | float | 换手率（仅股票） |
| limit_up | float | 涨停价（仅期货） |
| limit_down | float | 跌停价（仅期货） |
| open_interest | float | 累计持仓量（仅期货） |
| settlement | float | 结算价（仅期货） |
| pre_settlement | float | 昨日结算价（仅期货） |

示例：获取单支股票的部分回测因子

```python
import panda_data
result = panda_data.get_factor(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250131",
    factors=['open', 'close'],
    index_component="000300",
    type="stock"
)
print(result)
```

返回示例（前 3 行）：

| date | symbol | open | close |
|:---|:---|:---|:---|
| 20250127 | 000001.SZ | 1923.31104 | 1938.52176 |
| 20250124 | 000001.SZ | 1913.17056 | 1916.55072 |
| 20250123 | 000001.SZ | 1887.81936 | 1913.17056 |

## 复权因子

### get_adj_factor：获取复权因子

数据范围 1991-02-25 ~ 至今；每日更新 05:30 ~ 05:50；[官方页面](https://www.pandaaiquant.com/docs/api?id=36)

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
| ex_date | string | 除权除息日期 |
| ex_cum_factor | float | 前复权因子 |
| ex_factor | float | 后复权因子 |
| ex_end_date | string | 除权结束日期 |
| announcement_date | string | 公告日期 |

示例：获取一定日期内某只股票的复权因子

```python
import panda_data
result = panda_data.get_adj_factor(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250831",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | ex_date | announcement_date | ex_cum_factor | ex_end_date | ex_factor |
|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20250612 | 20250611 | 174.334 | NaN | 1.031513 |

## A 股 Barra 风格因子

### get_factor_exposure_style：获取A股风格暴露因子

数据范围 2014-01-01 ~ 至今；每日更新 06:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=330)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，可以是单个字符串或字符串列表 |
| start_date | string | 是 | 查询起始日期，格式为 `YYYYMMDD` |
| end_date | string | 是 | 查询结束日期，格式为 `YYYYMMDD` |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段，可以是单个字段名或字段名列表；传入空字符串或空列表时返回全部字段 |
| is_state_owned | Optional[boolean] | 否 | 所有制筛选：`True` 表示筛选央国企，`False` 表示筛选民营企业，为空时不筛选 |
| industry | Optional[Union[string, List[string]]] | 否 | 行业精确筛选。可选值：`agriculture`、`automobile`、`bank`、`basic_chemicals`、`beauty_care`、`building_materials`、`capital_equipment`、`coal`、`communications`、`commercial_retail`、`computer`、`construction`、`construction_decoration`、`defense`、`electrical_equipment`、`electronics`、`environmental_protection`、`finance`、`food_beverage`、`home_appliance`、`light_industry`、`media`、`metal`、`petroleum`、`pharmaceutical_biotech`、`real_estate`、`social_services`、`steel`、`textile_apparel`、`transportation`、`utility`；支持单个字符串或字符串列表，空值表示不筛选 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 交易日期，格式为 `YYYYMMDD` |
| analyst_sentiment | float | 分析师情绪因子 |
| beta | float | Beta 因子 |
| crowd | float | 拥挤度因子 |
| dividend_yield | float | 股息率因子 |
| earnings_quality | float | 盈利质量因子 |
| earnings_variability | float | 盈利波动因子 |
| growth | float | 成长因子 |
| industry_momentum | float | 行业动量因子 |
| investment_quality | float | 投资质量因子 |
| leverage | float | 杠杆因子 |
| liquidity | float | 流动性因子 |
| long_term_reversal | float | 长期反转因子 |
| mid_cap | float | 中盘因子 |
| ml_fac | float | 机器学习综合因子 |
| momentum | float | 动量因子 |
| profit | float | 盈利因子 |
| residual_volatility | float | 残差波动率因子 |
| seasonality | float | 季节性因子 |
| size | float | 规模因子 |
| short_term_reversal | float | 短期反转因子 |
| value | float | 价值因子 |
| market | float | 市场因子 |
| is_state_owned | boolean | 企业分类，`True` 表示央国企，`False` 表示民营企业 |
| industry | string | 行业字段名，多个行业以英文逗号分隔 |

示例：获取一定日期内所有银行业民营企业的风格暴露因子

```python
import panda_data
result = panda_data.get_factor_exposure_style(
    symbol="",
    start_date="20260101",
    end_date="20260131",
    fields=[""],
    is_state_owned=False,
    industry=["bank"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | analyst_sentiment | beta | crowd | dividend_yield | earnings_quality | earnings_variability | growth | industry_momentum | investment_quality | leverage | liquidity | long_term_reversal | mid_cap | ml_fac | momentum | profit | residual_volatility | seasonality | size | short_term_reversal | value | market | is_state_owned | industry |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SZ | 20260130 | -0.054838 | -1.434172 | -3.000000 | 2.379626 | -0.034659 | -2.585691 | -0.647810 | -1.361343 | 0.042603 | 2.543375 | -0.490004 | 0.427833 | -0.488412 | -0.132366 | -0.710657 | -1.028637 | -0.609190 | -0.269231 | 0.898817 | -0.031151 | 3.000000 | 1.0 | False | bank |
| 000001.SZ | 20260129 | -0.007645 | -1.437983 | -2.996301 | 2.146380 | -0.035688 | -2.581680 | -0.645767 | -1.210271 | 0.041426 | 2.543411 | -0.486385 | 0.444193 | -0.488426 | -0.243802 | -0.726425 | -1.028964 | -0.576880 | -0.508612 | 0.897155 | -0.097922 | 3.000000 | 1.0 | False | bank |
| 000001.SZ | 20260128 | -0.363455 | -1.454352 | -3.000000 | 2.232160 | -0.036164 | -2.597448 | -0.652187 | -1.088192 | 0.041989 | 2.548287 | -0.494090 | 0.420365 | -0.490051 | -0.183139 | -0.738655 | -1.025305 | -0.573511 | -0.268059 | 0.900545 | 0.055544 | 3.000000 | 1.0 | False | bank |

### get_factor_style_residual：获取风格因子残差风险与收益

数据范围 2014-01-01 ~ 至今；每日更新 06:00 ~ 08:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=358)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_date | str | 是 | 开始日期，格式YYYYMMDD |
| end_date | str | 是 | 结束日期，格式YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 股票代码 |
| residual_risk | float | 残差风险 |
| residual_return | float | 残差收益 |

示例：查询单只股票的残差风险与收益

```python
import panda_data
result = panda_data.get_factor_style_residual(
        symbol="000001.SZ",
        start_date="20260901",
        end_date="20260922"
    )
print(result)
```

返回示例（前 3 行）：

| date | symbol | residual_risk | residual_return |
|:---|:---|:---|:---|
| 20260922 | 000001.SZ | 11.831476 | -0.623841 |
| 20260921 | 000001.SZ | 11.883452 | -0.014426 |
| 20260918 | 000001.SZ | 11.979249 | 1.211533 |

### get_factor_style_covariance：获取风格因子相关性

数据范围 2015-04-03~ 至今；每日更新 06:30 ~ 08:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=360)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| factor_1 | string | 是 | 因子1代码，仅支持单个因子代码，不支持列表，可用因子代码见 get_factor_style_return |
| factor_2 | string | 是 | 因子2代码，仅支持单个因子代码，不支持列表，可用因子代码见 get_factor_style_return |
| start_date | str | 是 | 开始日期，格式YYYYMMDD |
| end_date | str | 是 | 结束日期，格式YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| factor_1 | string | 因子1代码 |
| factor_2 | string | 因子2代码 |
| covariance | float | 因子1与因子2的年化协方差，保留6位小数 |
| date | string | 日期 |

示例：查询BETA与MARKET因子的日度协方差序列

```python
import panda_data
result = panda_data.get_factor_style_covariance(
        factor_1="BETA",
        factor_2="MARKET",
        start_date="20260901",
        end_date="20260922"
    )
print(result)
```

返回示例（前 3 行）：

| factor_1 | factor_2 | covariance | date |
|:---|:---|:---|:---|
| BETA | MARKET | 75.247379 | 20260922 |
| BETA | MARKET | 79.164961 | 20260921 |
| BETA | MARKET | 75.844914 | 20260918 |

### get_factor_style_return：获取风格因子日度收益

数据范围 2014-01-02 ~ 至今；每日更新 06:30 ~ 08:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=359)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| factor | Optional[Union[string, List[string]]] | 否 | 因子代码，支持55个因子代码：AGR、BASCHEM、STEEL、METAL、ELECTRN、AUTO、HOMEAPP、FOODBEV、TEXTLAPP、LIGHTIND、PHARMBIO、BEAUTYCARE、UTILITY、TRANSPRT、REALEST、COMMERET、SOCIASER、BANK、FINAN、CONG、BUILDMAT、CONSTDEC、ELECEQP、CAPEQ、DEFENCE、COMPUTER、MEDIA、COMM、COAL、PETRO、ENVIRPRO、NE、ANLYSTSN、BETA、CROWD、DIVYILD、EARNQLTY、EARNVAR、GROWTH、INDMOM、INVSQLTY、LEVERAGE、LIQUIDITY、LTREVRSL、MIDCAP、MLFAC、MOMENTUM、OTHER、PROFIT、RESVOL、SEASONALITY、SIZE、STREVRSL、VALUE、MARKET，省略返回全部 |
| start_date | str | 是 | 开始日期，格式YYYYMMDD |
| end_date | str | 是 | 结束日期，格式YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| factor | string | 因子代码 |
| return | float | 因子日收益率 |

示例：查询全部因子两个交易日的日度收益

```python
import panda_data
result = panda_data.get_factor_style_return(
        start_date="20260921",
        end_date="20260922"
    )
print(result)
```

返回示例（前 3 行）：

| date | factor | return |
|:---|:---|:---|
| 20260922 | AGR | -0.004764 |
| 20260921 | AGR | 0.002046 |
| 20260922 | ANLYSTSN | 0.000691 |

### get_rf_rate：获取无风险利率

数据范围 2014-01-02 ~ 至今；每日更新 06:30 ~ 08:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=361)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| currency | Optional[Union[string, List[string]]] | 否 | 币种 |
| start_date | str | 是 | 开始日期，格式YYYYMMDD |
| end_date | str | 是 | 结束日期，格式YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| currency | string | 币种 |
| rf_rate | float | 无风险利率（单位：%） |

示例：查询全部币种的无风险利率

```python
import panda_data
result = panda_data.get_rf_rate(
        start_date="20260901",
        end_date="20260922"
    )
print(result)
```

返回示例（前 3 行）：

| date | currency | rf_rate |
|:---|:---|:---|
| 20260922 | CNY | 1.43 |
| 20260921 | CNY | 1.43 |
| 20260918 | CNY | 1.43 |
