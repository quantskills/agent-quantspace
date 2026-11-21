---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - Options
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# 期权

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 期权基本信息

### get_option_detail：获取期权基本信息

数据范围 2015-02-09 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=128)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期权代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| status | Optional[boolean] | 否 | 是否包含已退市和未上市的期权 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易市场(SH、SZ、SHF、DCE、GFE、CZC、INE、CFE) |
| option_type | Optional[Union[string, List[string]]] | 否 | 品种类别(商品期权、股指期权、ETF期权) |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 期权代码 |
| contract_symbol | string | 合约简称 |
| ticker_symbol | string | 通用交易代码 |
| underlying_simpol_name | string | 标的证券简称 |
| underlying_symbol | string | 标的交易代码 |
| exchange | string | 交易市场 |
| option_type | string | 品种类别(商品期权、股指期权、ETF期权) |
| currency_symbol | string | 货币代码 |
| call_put_code | string | 认购认沽编码（CO：认购期权，PO：认沽期权） |
| strike_price | float | 行权价格 |
| contract_size | integer | 合约单位 |
| status | string | 合约状态（DE：已退市，UN：未上市，L：上市） |
| listed_date | string | 挂牌日期 |
| expiration_date | string | 到期日期 |
| expiration_year | string | 到期年份 |
| expiration_month | string | 到期月份 |
| de_listed_date | string | 摘牌日期 |
| exercise_date | string | 行权日期 |
| settlement_date | string | 交收日期 |

示例：获取指定交易市场的期权合约

```python
import panda_data
result = panda_data.get_option_detail(
    exchange=['SH'],
    fields=['symbol','ticker_symbol','contract_symbol','exchange','call_put_code']
 )
print(result)
```

返回示例（前 3 行）：

| symbol | call_put_code | contract_symbol | exchange | ticker_symbol |
|:---|:---|:---|:---|:---|
| 10000001.SH | CO | 50ETF购3月2200 | SH | 510050C1503M02200 |
| 10000002.SH | CO | 50ETF购3月2250 | SH | 510050C1503M02250 |
| 10000003.SH | CO | 50ETF购3月2300 | SH | 510050C1503M02300 |

### get_option_underlying_detail：获取期权品种信息

数据范围 2015-02-09 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=129)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期权代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易所（SH、SZ、SHF、DCE、GFE、CZC、INE、CFE） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| underlying_ticker_symbol | string | 标的证券简称 |
| symbol | string | 标的交易代码 |
| exchange | string | 交易所 |
| call_put_code | string | 认购认沽编码 |
| listed_date | string | 挂牌日期 |
| exercise_style | string | 履约方式（A：美式，E：欧式） |
| contract_unit | string | 合约单位 |
| expiration_monthz_desc | string | 到期月份描述 |
| trade_time_desc | string | 交易时间描述 |
| exercise_time_desc | string | 行权日行权时间描述 |
| last_trade_date_desc | string | 最后交易日描述 |
| expiration_date_desc | string | 到期日描述 |
| exercise_date_desc | string | 行权日描述 |
| settlement_type | string | 交割方式（P：实物交割，C：现金结算） |
| commission | float | 交易手续费 |
| commission_unit | string | 交易手续费单位 |
| tick_size | float | 最小报价变动 |
| tick_size_unit | string | 最小报价变动单位 |
| board_lot | string | 申报单位 |

示例：指定品种查询

```python
import panda_data
result = panda_data.get_option_underlying_detail(
   symbol=['a','SC']
 )
print(result)
```

返回示例（前 3 行）：

| symbol | board_lot | call_put_code | commission | commission_unit | contract_unit | exchange | exercise_date_desc | exercise_style | exercise_time_desc | expiration_date_desc | expiration_monthz_desc | last_trade_date_desc | listed_date | settlement_type | tick_size | tick_size_unit | trade_time_desc | underlying_ticker_symbol |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| A | 手 | CP | 0.5 | 元/手 | 10 | DCE | 买方可以在到期日之前任一交易日的交易时间，以及到期日15:30之前提出行权申请。 | A | 买方可以在到期日之前任一交易日的交易时间，以及到期日15:30之前提出行权申请。 | 标的期货合约交割月份前一个月的第5个交易日 | 1、3、5、7、9、11月 | 标的期货合约交割月份前一个月的第5个交易日 | 20220808 | P | 0.5 | 元/吨 | 每周一至周五上午9:00～11:30，下午13:30～15:00，以及交易所规定的其他时间 | 大商所黄大豆1号期货 |
| SC | 手 | CP | 10.0 | 元/手 | 1000 | INE | 买方可在到期日前任一交易日的交易时间提交行权申请；买方可在到期日15:30之前提交行权申请、放弃申请 | A | 买方可在到期日前任一交易日的交易时间提交行权申请；买方可在到期日15:30之前提交行权申请、放弃申请 | 标的期货合约交割月前第一月的倒数第13个交易日 | 最近两个连续月份合约，其后月份在标的期货合约结算后持仓量达到一定数值之后的第二个交易日挂盘 | 标的期货合约交割月前第一月的倒数第13个交易日 | 20210621 | P | 0.05 | 元/桶 | 上午9:00-11:30下午13:30-15:00及上海国际能源交易中心规定的其他时间 | 上能所原油期货 |

### get_option_exercise：获取期权行权交收信息（只包含沪深两市期权数据）

数据范围 2015-03-25 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=163)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 期权代码 |
| call_put_code | Optional[Union[string, List[string]]] | 否 | 认购认沽编码（CO:认购期权,PO:认沽期权;CP:认购、认沽期权） |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 期权代码 |
| date | string | 行权日 |
| call_put_code | string | 认购认沽编码(CO:认购期权,PO:认沽期权;CP:认购、认沽期权) |
| exercise_volume | integer | 行权数量 |

示例：获取指定时间的数据

```python
import panda_data
result = panda_data.get_option_exercise(
   start_date='20250310',
    end_date='20260310',
 )
print(result)
```

返回示例（前 3 行）：

| date | symbol | call_put_code | exercise_volume |
|:---|:---|:---|:---|
| 20250326 | 510050.SH | CO | 22738 |
| 20250326 | 510050.SH | PO | 23422 |
| 20250326 | 510300.SH | CO | 24009 |

### get_option_static：获取期权每日盘前静态数据（只包含沪深两市的期权数据）

数据范围 2015-02-09 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=166)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 交易代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易所（SH、SZ） |
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 标的交易代码 |
| status | Optional[Union[string, List[string]]] | 否 | 合约状态（上交所：20191115前是5位字符串，之后该字段6位字符串，从左起每位表示特定的含义，无定义则填空格。第1位：'0'表示可开仓，'1'表示限制卖出开仓（不包括备兑开仓）和买入开仓。第2位：'0'表示未连续停牌，'1'表示连续停牌。第3位：'0'表示未临近到期日，'1'表示距离到期日不足 5 个交易日。第4位：'0'表示近期未做调整，'1'表示最近 5 个交易日内合约发生过调整。第5位：'A'表示当日新挂牌的合约，'E'表示存续的合约。第6位：'1'表示合约只能进行跨式和宽跨式的组合策略，'0'表示可以进行所有的组合策略。深交所：6代表上市首日，13代表合约调整） |
| call_put_code | Optional[Union[string, List[string]]] | 否 | 认购认沽编码(CO：认购期权,PO：认沽期权) |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 交易日期 |
| name | string | 合约简称 |
| symbol | string | 交易代码 |
| exchange | string | 交易所 |
| underlying_symbol_name | string | 标的证券简称 |
| underlying_symbol | string | 标的交易代码 |
| underlying_type | string | 标的证券类型(ETF：期权) |
| exercise_style | string | 履约方式编码(E：欧式) |
| call_put_code | string | 认购认沽编码(CO：认购期权,PO：认沽期权) |
| contract_size | integer | 合约单位(经过除权除息调整) |
| strike_price | float | 行权价格(经过除权除息调整) |
| listed_date | string | 挂牌日期 |
| last_date | string | 最后交易日 |
| exercise_date | string | 行权日期 |
| settlement_date | string | 交收日期 |
| delisted_date | string | 合约到期日 |
| contract_version | string | 合约版本号 |
| open_interest | integer | 昨持仓量 |
| pre_close | float | 昨收价 |
| pre_settlement | float | 前结算价 |
| underlying_pre_close | float | 标的证券昨收价 |
| limit_type | string | 涨跌幅限类型(N：有涨跌幅限制) |
| limit_up | float | 涨幅上限价格 |
| limit_down | float | 跌幅下限价格 |
| margin | float | 单位保证金(当日持有一张合约所需要的保证金数量，精确到分) |
| margin_ratio1 | float | 交易所保证金计算比例参数一 |
| margin_ratio2 | float | 交易所保证金计算比例参数二 |
| lot_size | integer | 整手数(一手对应的合约数) |
| limit_down_volume | integer | 单笔限价申报张数下限 |
| limit_up_volume | integer | 单笔限价申报张数上限 |
| market_down_volume | integer | 单笔市价申报张数下限 |
| market_up_volume | integer | 单笔市价申报张数上限 |
| tick_size | float | 最小报价变动数值 |
| status | string | 合约状态 |

示例：获取指定时间指定状态的数据

```python
import panda_data
result = panda_data.get_option_static(
    start_date="20250130",
    end_date="20260430",
    status=['0000E0']
)
print(result)
```

返回示例（前 3 行）：

| date | symbol | call_put_code | contract_size | contract_version | delisted_date | exchange | exercise_date | exercise_style | last_date | limit_down | limit_down_volume | limit_type | limit_up | limit_up_volume | listed_date | lot_size | margin | margin_ratio1 | margin_ratio2 | market_down_volume | market_up_volume | name | open_interest | pre_close | pre_settlement | settlement_date | status | strike_price | tick_size | underlying_pre_close | underlying_symbol | underlying_symbol_name | underlying_type |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 20250205 | 10007595.SH | CO | 10205 | 0 | 20250326 | SH | 20250326 | E | 20250326 | 0.1737 | 1 | N | 0.7023 | 50 | 20240725 | 1 | 7706.41 | 12 | 7 | 1 | 10 | 50ETF购3月2205A | 673 | 0.4366 | 0.438 | 20250327 | 0000E0 | 2.205 | 0.0001 | 2.643 | 510050.SH | 50ETF | F |
| 20250205 | 10007596.SH | CO | 10205 | 0 | 20250326 | SH | 20250326 | E | 20250326 | 0.1247 | 1 | N | 0.6533 | 50 | 20240725 | 1 | 7206.36 | 12 | 7 | 1 | 10 | 50ETF购3月2254A | 845 | 0.3928 | 0.389 | 20250327 | 0000E0 | 2.254 | 0.0001 | 2.643 | 510050.SH | 50ETF | F |

## 期权日线行情

### get_option_daily：获取期权日线数据

数据范围 2015-02-09 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=130)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期,eg:"20250702"，与开始日期间不超过5年 |
| symbol | Optional[Union[string, List[string]]] | 否 | 期权代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 期权代码 |
| ticker_symbol | string | 证券简称 |
| exchange | string | 交易所 |
| pre_settlement | float | 前结算价 |
| pre_close | float | 昨收价 |
| open | float | 当日开盘价 |
| high | float | 当日最高价 |
| low | float | 当日最低价 |
| close | float | 当日收盘价 |
| settlement | float | 当日结算价 |
| volume | float | 当日成交量 |
| amount | float | 当日成交金额 |
| open_interest | integer | 持仓量 |

示例：查询指定时间段的数据

```python
import panda_data
result = panda_data.get_option_daily(
   start_date='20260202',
    end_date='20260401'
 )
print(result)
```

返回示例（前 3 行）：

| date | symbol | ticker_symbol | exchange | pre_settlement | pre_close | open | high | low | close | settlement | volume | amount | open_interest |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 20260325 | 10009633.SH | 50ETF购3月2630A | SH | 0.27 | 0.2663 | 0.2719 | 0.3003 | 0.2719 | 0.2996 | 0.3 | 717 | 2178096.48 | 736 |
| 20260324 | 10009633.SH | 50ETF购3月2630A | SH | 0.2419 | 0.2418 | 0.2474 | 0.2688 | 0.2355 | 0.2663 | 0.27 | 642 | 1688998.99 | 747 |
| 20260323 | 10009633.SH | 50ETF购3月2630A | SH | 0.33 | 0.33 | 0.3106 | 0.3106 | 0.227 | 0.2418 | 0.2419 | 304 | 837654.8 | 893 |

### get_option_spot_market：获取期权现货日行情（只包含上海黄金交易所）

数据范围 2002-10-30 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=164)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 交易代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 交易代码 |
| name | string | 证券简称 |
| exchange | string | 交易所代码 |
| date | string | 交易日期 |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| change | float | 涨跌额 |
| change_rate | float | 涨跌幅 |
| vwap | float | 加权平均价 |
| volume | float | 成交量 |
| amount | float | 成交金额 |
| open_interest | float | 持仓量 |
| settlement_direction | integer | 交收方向(0:多支付空,1:空支付多) |
| settlement_volume | float | 交收数量 |

示例：获取指定时间的数据

```python
import panda_data
result = panda_data.get_option_spot_market(
    start_date="20250430",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| date | symbol | amount | change | change_rate | close | exchange | high | low | name | open | open_interest | settlement_direction | settlement_volume | volume | vwap |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 20250430 | AG(T+D) | 2.938140e+09 | -39.00 | -0.0048 | 8163.0 | SGEX | 8272.0 | 8150.00 | 白银(T+D) | 8210.00 | 3499912.0 | 1.0 | 54600.0 | 358256.0 | 8201.0 |
| 20250430 | AU(T+D) | 2.482539e+10 | -5.22 | -0.0067 | 779.5 | SGEX | 786.0 | 778.47 | 黄金(T+D) | 781.69 | 208794.0 | 2.0 | 25246.0 | 31770.0 | 781.4 |

示例：获取指定时间和指定品种的数据

```python
import panda_data
result = panda_data.get_option_spot_market(
    start_date="20250430",
    end_date="20260430",
    symbol=['Au99.99']
)
print(result)
```

返回示例（前 3 行）：

| date | symbol | amount | change | change_rate | close | exchange | high | low | name | open | open_interest | settlement_direction | settlement_volume | volume | vwap |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 20250430 | AU99.99 | 6.516399e+09 | 0.14 | 0.0002 | 780.19 | SGEX | 784.76 | 778.01 | 黄金9999 | 783.0 | None | None | None | 8343.96 | 780.97 |
| 20250506 | AU99.99 | 1.006130e+10 | 12.01 | 0.0154 | 792.20 | SGEX | 797.50 | 785.00 | 黄金9999 | 785.0 | None | None | None | 12694.96 | 792.54 |

## 期权波动率数据

### get_option_implied_volatility：获取期权隐含波动率

数据范围 2020-06-19 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=131)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期,eg:"20250702"，与开始日期间不超过5年 |
| symbol | Optional[Union[string, List[string]]] | 否 | 期权代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 期权代码 |
| implied_volatility | float | 隐含波动率 |

示例：获取指定时间段的数据

```python
import panda_data
result = panda_data.get_option_implied_volatility(
   start_date='20260310',
    end_date='20260310',
 )
print(result)
```

返回示例（前 3 行）：

| date | implied_volatility | symbol |
|:---|:---|:---|
| 20260310 | 37.53 | AP605C10000.CZC |
| 20260310 | 37.17 | AP605C10200.CZC |

### get_option_underlying_volatility：获取期权标的历史波动率（只包含沪市交易所期权标的数据）

数据范围 2005-03-02 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=132)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期,eg:"20250702"，与开始日期间不超过5年 |
| symbol | Optional[Union[string, List[string]]] | 否 | 期权标的代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易所（SH、SZ、SHF、DCE、GFE、CZC、INE、CFE） |
| period | integer | 否 | 历史波动率期限（5、10、30、60、90、120、180、250、500） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 期权标的代码 |
| ticker_symbol | float | 期权标的简称 |
| exchange | string | 交易所 |
| is_adj | integer | 是否为复权数据 |
| close | float | 收盘价 |
| period | integer | 历史波动率期限（单位：日） |
| historical_volatility | float | 历史波动率 |

示例：获取指定时间的数据且指定 period=10

```python
import panda_data
result = panda_data.get_option_underlying_volatility(
   start_date='20260310',
    end_date='20260310',
    period=10
 )
print(result)
```

返回示例（前 3 行）：

| date | symbol | close | exchange | historical_volatility | is_adj | period | ticker_symbol |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 20260310 | 159901.SZ | 3.5 | SZ | 0.209137 | 0 | 10 | 易方达深证100ETF |
| 20260310 | 159915.SZ | 3.296 | SZ | 0.258342 | 0 | 10 | 易方达创业板ETF |
| 20260310 | 159919.SZ | 4.879 | SZ | 0.135725 | 0 | 10 | 嘉实沪深300ETF |

### get_option_risk_indicators：获取期权风险指标

数据范围 2015-02-09 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=165)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 交易代码 |
| exchange | Optional[Union[string, List[string]]] | 否 | 交易所（SH、SZ、SHF、DCE、GFE、CZC、INE、CFE） |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 交易代码 |
| name | string | 合约简称 |
| exchange | string | 交易所 |
| date | string | 交易日期 |
| delta | float | DELTA，期权价格对标的价格的敏感度 |
| theta | float | THETA，期权价格对到期时间的敏感度 |
| gamma | float | GAMMA，DELTA对标的价格的敏感度 |
| vega | float | VEGA，期权价格对隐含波动率的敏感度 |
| rho | float | RHO，期权价格对无风险利率的敏感度 |

示例：获取指定时间的数据

```python
import panda_data
result = panda_data.get_option_risk_indicators(
    start_date="20250430",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| date | symbol | delta | exchange | gamma | name | rho | theta | vega |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 20250506 | A2507-C-3400.DCE | 1.0 | DCE | None | 豆一购7月3400 | None | None | None |
| 20250506 | A2507-C-3500.DCE | 1.0 | DCE | None | 豆一购7月3500 | None | None | None |

## 期权交易统计

### get_option_trade_rank：获取期权期货公司交易排名

数据范围 2015-02-09 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=321)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期权标的交易代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| exchange | Optional[string] | 否 | 交易市场编码 |
| stats_type | Optional[string] | 否 | 统计项目类型(0101:认购合约成交量;0102:认沽合约成交量;0201:认购合约持仓量;0202:认沽合约持仓量) |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 期权标的交易代码 |
| date | string | 交易日期 |
| exchange | string | 交易市场编码 |
| name | string | 证券简称 |
| rank | integer | 排名 |
| volume | float | 成交量或持仓量，根据stats_type区分含义 |
| party_name | string | 经营机构简称 |
| stats_type | string | 统计项目类型(0101:认购合约成交量;0102:认沽合约成交量;0201:认购合约持仓量;0202:认沽合约持仓量) |

示例：获取某只期权标的在指定时间内的交易排名

```python
import panda_data
result = panda_data.get_option_trade_rank(
    symbol="510050.SH",
    start_date="20260701",
    end_date="20260722"
)
print(result)
```

返回示例（前 3 行）：

| date | symbol | exchange | name | party_name | rank | stats_type | volume |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 20260701 | 510050.SH | SH | 华夏上证50ETF | 东方证券 | 1 | 0101 | 200462 |
| 20260701 | 510050.SH | SH | 华夏上证50ETF | 中信期货 | 2 | 0101 | 158378 |
| 20260701 | 510050.SH | SH | 华夏上证50ETF | 华泰证券 | 3 | 0101 | 129617 |

### get_option_margin：获取期权保证金

数据范围 2018-09-21 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=322)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期权交易代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| exchange | Optional[string] | 否 | 交易市场 |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 期权交易代码 |
| date | string | 交易日期 |
| exchange | string | 交易市场 |
| name | string | 证券简称 |
| margin | float | 交易保证金 |

示例：获取某只期权合约在指定时间内的保证金信息

```python
import panda_data
result = panda_data.get_option_margin(
        symbol="UR407P2440.CZC",
        start_date="20240501",
        end_date="20240601"
    )
print(result)
```

返回示例（前 3 行）：

| date | symbol | name | exchange | margin |
|:---|:---|:---|:---|:---|
| 20240531 | UR407P2440.CZC | 尿素沽7月2440 | CZC | 7543.6 |
| 20240530 | UR407P2440.CZC | 尿素沽7月2440 | CZC | 7217.2 |
| 20240529 | UR407P2440.CZC | 尿素沽7月2440 | CZC | 7476.4 |

### get_option_underlying_exercise：获取期权标的行权信息

数据范围 2015-03-25 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=324)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期权标的交易代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| contract_type | Optional[string] | 否 | 期权合约类型（CO：认购期权，PO：认沽期权） |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 期权标的交易代码 |
| exercise_date | string | 行权日期（合约到期月份的第四个星期三，遇法定节假日顺延） |
| contract_type | string | 期权合约类型（CO：认购期权，PO：认沽期权） |
| exercise_volume | integer | 有效行权张数 |

示例：获取某只期权标的在指定时间内的行权信息

```python
import panda_data
result = panda_data.get_option_underlying_exercise(
        symbol="510050.SH",
        start_date="20260722",
        end_date="20260722"
    )
print(result)
```

返回示例（前 3 行）：

| exercise_date | symbol | contract_type | exercise_volume |
|:---|:---|:---|:---|
| 20260722 | 510050.SH | CO | 7214 |
| 20260722 | 510050.SH | PO | 10090 |

### get_option_trade_stats：获取期权交易信息

数据范围 2015-02-09 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=323)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期权交易代码 |
| start_date | string | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | string | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| exchange | Optional[string] | 否 | 交易市场编码 |
| stats_interval | Optional[integer] | 否 | 数据统计区间（1：年，2：月，3：周，4：日） |
| fields | Optional[Union[string, List[string]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 期权交易代码 |
| date | string | 交易日期 |
| exchange | string | 交易市场编码 |
| name | string | 证券简称 |
| stats_interval | integer | 数据统计区间（1：年，2：月，3：周，4：日） |
| turnover_volume | integer | 总成交量 |
| call_volume | integer | 认购成交量 |
| put_volume | integer | 认沽成交量 |
| put_call_ratio | float | 认沽认购比 |
| open_interest | integer | 未平仓合约总张数 |
| call_open_interest | integer | 未平仓认购合约张数 |
| put_open_interest | integer | 未平仓认沽合约张数 |

示例：获取某只期权在指定时间内的交易统计信息

```python
import panda_data
result = panda_data.get_option_trade_stats(
        symbol="510050.SH",
        start_date="20260701",
        end_date="20260722",
        fields=['date','open_interest']
    )
print(result)
```

返回示例（前 3 行）：

| date | symbol | open_interest |
|:---|:---|:---|
| 20260701 | 510050.SH | 1514602 |
| 20260702 | 510050.SH | 1619111 |
| 20260703 | 510050.SH | 1635148 |

### get_option_variety_rank：获取期权品种成交排名

数据范围 2017-04-19 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=326)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| underlying_name | Optional[str] | 否 | 品种名称（如"苹果"），中文原样匹配 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| exchange | Optional[str] | 否 | 交易市场代码（如 "CZC"），内部转大写匹配 |
| underlying_type | Optional[str] | 否 | 期权合约类型：CO（看涨）、PO（看跌） |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表；传单个字符串也可。未包含 underlying_name、date 时会自动补齐 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | str | 交易日期 |
| underlying_name | str | 品种名称（如"苹果"） |
| underlying_type | str | 期权合约类型：CO（看涨）、PO（看跌） |
| exchange | str | 交易市场代码 |
| party_name | str | 会员简称 |
| rank_trade | float | 成交量排名名次 |
| rank_buy | float | 持买仓量排名名次 |
| rank_sell | float | 持卖仓量排名名次 |
| position_trade | float | 成交量 |
| position_buy | float | 持买仓量 |
| position_sell | float | 持卖仓量 |
| change_trade | float | 成交量较上一交易日的变动量 |
| change_buy | float | 持买仓量较上一交易日的变动量 |
| change_sell | float | 持卖仓量较上一交易日的变动量 |

示例：获取某个期权品种在指定时间内的持买仓量

```python
import panda_data
result = panda_data.get_option_variety_rank(
        underlying_name="苹果",
        start_date="20260701",
        end_date="20260702",
        fields=['date','underlying_name',"party_name","position_buy"]
    )
print(result)
```

返回示例（前 3 行）：

| date | underlying_name | party_name | position_buy |
|:---|:---|:---|:---|
| 20260701 | 苹果 | 海通期货(代客) | 1166.0 |
| 20260701 | 苹果 | 国泰君安(代客) | 541.0 |
| 20260701 | 苹果 | 光大期货(代客) | 226.0 |

### get_option_commodity_rank：获取商品期权持仓排名

数据范围 2017-03-31 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=325)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 期权标的交易代码（如 "m2509.DCE"），内部转大写匹配，可传单个字符串或列表 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD" |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD" |
| exchange | Optional[str] | 否 | 交易市场编码（如 "DCE"），内部转大写匹配 |
| contract_type | Optional[str] | 否 | 期权合约类型：CO（看涨）、PO（看跌），内部转大写匹配 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表；传单个字符串也可。未包含 symbol、date 时会自动补齐 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | str | 交易日期 |
| symbol | str | 期权标的交易代码（已转大写，如 "M2509.DCE"） |
| name | str | 标的合约证券简称 |
| contract_type | str | 期权合约类型：CO（看涨）、PO（看跌） |
| party_name | str | 期货公司会员简称 |
| exchange | str | 交易市场编码 |
| rank_trade | float | 成交量排名名次 |
| rank_buy | float | 持买仓量排名名次 |
| rank_sell | float | 持卖仓量排名名次 |
| position_trade | float | 成交量 |
| position_buy | float | 持买仓量 |
| position_sell | float | 持卖仓量 |
| change_trade | float | 成交量较上一交易日的变动量 |
| change_buy | float | 持买仓量较上一交易日的变动量 |
| change_sell | float | 持卖仓量较上一交易日的变动量 |

示例：获取某只商品期权在指定时间内的持仓排名

```python
import panda_data
result = panda_data.get_option_commodity_rank(
        symbol="m2509.DCE",
        start_date="20250701",
        end_date="20250702",
        fields=['date','symbol','party_name',"position_buy"]
    )
print(result)
```

返回示例（前 3 行）：

| date | symbol | party_name | position_buy |
|:---|:---|:---|:---|
| 20250702 | M2509.DCE | 国信期货(代客) | NaN |
| 20250702 | M2509.DCE | 华安期货(代客) | NaN |
| 20250702 | M2509.DCE | 新湖期货(代客) | NaN |
