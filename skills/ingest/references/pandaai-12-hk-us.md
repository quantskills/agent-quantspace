---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - HK and US Markets
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# 港美股

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 行情数据

### get_hk_daily：获取港股日线数据

数据范围 1980-01-02 ~ 至今；每日更新 18:00 ~ 19:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=56)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期,eg:"20250702"，与开始日期间不超过5年 |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 交易日 |
| symbol | string | 股票代码 |
| open | string | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| pre_close | float | 昨收价 |
| name | string | 股票名称 |
| trade_status | float | 交易状态代码 |
| alt_close | float | 调整收盘价（剔除派息、送股、拆合股等公司行为影响） |
| amount | float | 成交额 |
| bid | float | 买盘价（收盘前最后一笔） |
| ask | float | 卖盘价（收盘前最后一笔） |
| vwap | float | 成交量加权平均价 |
| vwap_vol | float | 计算VWAP的成交量 |
| opn_aucvol | float | 开市竞价时段成交量 |
| opn_auc | float | 开市竞价时段价格 |
| lmt_refpr2 | float | 限价参考价 |
| lolimit | float | 价格下限（是盘中触发“冷静期”时的临时限价 “±10%～20%”） |
| uplimit | float | 价格上限（是盘中触发“冷静期”时的临时限价 “±10%～20%”） |
| lolimit_2 | float | 二级价格下限（是开盘前和收盘竞价时的限价 “开市±15%、收市±5%”） |
| uplimit_2 | float | 二级价格上限（是开盘前和收盘竞价时的限价 “开市±15%、收市±5%”） |
| num_moves | float | 成交笔数 |
| uplimit_3 | float | 三级价格上限（仅开盘竞价时段专用的独立限价，方便与收盘竞价区分） |
| lolimit_3 | float | 三级价格下限（仅开盘竞价时段专用的独立限价，方便与收盘竞价区分） |
| cls_aucvol | float | 收市竞价时段成交量 |

示例：获取一定日期内所有港股的日线数据

```python
import panda_data
result = panda_data.get_hk_daily(
    symbol=[],
    start_date="20250101",
    end_date="20250131",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | alt_close | amount | ask | bid | close | cls_aucvol | high | lmt_refpr2 | lolimit | lolimit_2 | lolimit_3 | low | name | num_moves | open | opn_auc | opn_aucvol | pre_close | trade_status | uplimit | uplimit_2 | uplimit_3 | volume | vwap | vwap_vol |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 0 | 0001.HK | 20250102 | 41.05 | 170658280.0 | 41.1 40.95 | 41.05 | 577000 | 41.5 | 40.95 | 0 | 38.95 | 0 | 40.7 | CK HUTCHISON HOLDINGS LIMITED | 2432 | 41.3 | 41.3 | 18000 | 41.5 | 0 | 0 | 42.95 | 0 | 4164402.0 40.9803 | 4158500.0 |
| 1 | 0001.HK | 20250103 | 41.15 | 108033904.0 41.15 | 41.1 | 41.15 | 328500 41.55 | 41.15 | 0 | 39.1 | 0 | 40.9 | CK HUTCHISON HOLDINGS LIMITED | 1840 | 41.4 | 41.4 | 122000 | 41.05 | 0 | 0 | 43.2 | 0 | 2627730.0 | 41.113 | 2612000.0 |
| 2 | 0001.HK | 20250106 | 41.3 | 160524878.0 | 41.3 41.15 | 41.3 | 589500 | 41.8 | 41.15 | 0 | 39.1 | 0 40.95 | CK HUTCHISON HOLDINGS LIMITED | 2342 41.45 | 41.45 | 96000 | 41.15 | 0 | 0 | 43.2 | 0 | 3892729.0 41.2474 | 3670000.0 |

### get_hk_daily_post：获取港股后复权日线数据

数据范围 2015-01-01 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=283)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 港股代码，如 "0700.HK"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD"，与开始日期间不超过5年 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 港股代码，如 0700.HK |
| date | str | 交易日期，格式为 "YYYYMMDD" |
| open | double | 开盘价 |
| high | double | 最高价 |
| low | double | 最低价 |
| close | double | 收盘价 |
| vwap | double | 成交量加权平均价 |
| pre_close | double | 前收盘价 |
| change | double | 涨跌额 |
| change_rate | double | 涨跌幅（%） |
| volume | double | 成交量 |
| amount | double | 成交额 |
| turnover | double | 换手率（%） |

示例：获取腾讯控股近期后复权日线

```python
import panda_data
result = panda_data.get_hk_daily_post(
    symbol="0700.HK",
    start_date="20260101",
    end_date="20260131",
    fields=["symbol","date","open","close","volume"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | close | volume |
|:---|:---|:---|:---|:---|
| 0700.HK | 20260102 | 600.5 | 623.0 | 16200058.0 |
| 0700.HK | 20260105 | 624.0 | 624.5 | 19947025.0 |
| 0700.HK | 20260106 | 627.0 | 632.5 | 24168431.0 |

### get_hk_daily_pre：获取港股前复权日线数据

数据范围 2015-01-01 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=282)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 港股代码，如 "0700.HK"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD"，与开始日期间不超过5年 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 港股代码，如 0700.HK |
| date | str | 交易日期，格式为 "YYYYMMDD" |
| open | double | 开盘价 |
| high | double | 最高价 |
| low | double | 最低价 |
| close | double | 收盘价 |
| vwap | double | 成交量加权平均价 |
| pre_close | double | 前收盘价 |
| change | double | 涨跌额 |
| change_rate | double | 涨跌幅（%） |
| volume | double | 成交量 |
| amount | double | 成交额 |
| turnover | double | 换手率（%） |

示例：获取腾讯控股近期前复权日线

```python
import panda_data
result = panda_data.get_hk_daily_pre(
    symbol="0700.HK",
    start_date="20260101",
    end_date="20260131",
    fields=["symbol","date","open","close","volume"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | close | volume |
|:---|:---|:---|:---|:---|
| 0700.HK | 20260102 | 593.584203 | 615.825076 | 16200058.0 |
| 0700.HK | 20260105 | 616.813559 | 617.307801 | 19947025.0 |
| 0700.HK | 20260106 | 619.779009 | 625.215667 | 24168431.0 |

### get_us_daily：获取美股日线数据

数据范围 2014-03-07 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=57)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"，与结束日期间不超过5年 |
| end_date | string | 是 | 结束日期,eg:"20250702"，与开始日期间不超过5年 |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 交易日 |
| symbol | string | 股票代码 |
| open | string | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| pre_close | float | 昨收价 |
| name | string | 股票名称 |
| trade_status | float | 交易状态代码 |
| blkcount | float | 大宗交易笔数 |
| blkvolum | float | 大宗交易量数 |
| bid | float | 买盘价（收盘前最后一笔） |
| ask | float | 卖盘价（收盘前最后一笔） |
| vwap | float | 成交量加权平均价 |
| num_moves | float | 成交笔数 |

示例：获取一定日期内所有美股的日线数据

```python
import panda_data
result = panda_data.get_us_daily(
    symbol=[],
    start_date="20250101",
    end_date="20250131",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | num_moves | vwap | volume | high | pre_close | low | blkvolum | trade_status | ask | name | bid | blkcount | close | open |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| A | 20250131 | 18061.0 | 152.4235 | 1886605.0 | 153.8400 | 151.3800 | 150.5000 | 99406.0 | 0.0 | 151.6400 | AGILENT TECHNOLOGIES, INC. | 151.4600 | 22.0 | 151.5200 | 150.9600 |
| A | 20250130 | 16703.0 | 151.3413 | 1496057.0 | 152.4800 | 147.0900 | 147.6500 | 89679.0 | 0.0 | 151.4700 | AGILENT TECHNOLOGIES, INC. | 151.3400 | 32.0 | 151.3800 | 148.9500 |
| A | 20250129 | 19102.0 | 147.6937 | 1583243.0 | 149.9000 | 150.3400 | 146.5500 | 174876.0 | 0.0 | 147.2200 | AGILENT TECHNOLOGIES, INC. | 147.0400 | 34.0 | 147.0900 | 148.9900 |

### get_us_daily_post：美股后复权日线

数据范围 2015-01-01 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=341)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 美股代码，如 "AAPL"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD"，与开始日期间不超过5年 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 美股代码，如 AAPL |
| date | str | 交易日期，格式为 "YYYYMMDD" |
| open | double | 开盘价 |
| high | double | 最高价 |
| low | double | 最低价 |
| close | double | 收盘价 |
| vwap | double | 成交量加权平均价 |
| pre_close | double | 前收盘价 |
| change | double | 涨跌额 |
| change_rate | double | 涨跌幅（%） |
| volume | double | 成交量 |
| amount | double | 成交额 |
| turnover | double | 换手率（%） |

示例：获取苹果公司近期后复权日线

```python
import panda_data
result = panda_data.get_us_daily_post(
    symbol="AAPL",
    start_date="20260101",
    end_date="20260131",
    fields=["symbol","date","open","close","volume"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | close | volume |
|:---|:---|:---|:---|:---|
| AAPL | 20260102 | 272.255 | 271.01 | 37838054.0 |
| AAPL | 20260105 | 270.640 | 267.26 | 45647190.0 |
| AAPL | 20260106 | 267.000 | 262.36 | 52352090.0 |

### get_us_daily_pre：美股前复权日线

数据范围 2015-01-01 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=340)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 美股代码，如 "AAPL"，可以是单个字符串或字符串列表 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD"，与开始日期间不超过5年 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 美股代码，如 AAPL |
| date | str | 交易日期，格式为 "YYYYMMDD" |
| open | double | 开盘价 |
| high | double | 最高价 |
| low | double | 最低价 |
| close | double | 收盘价 |
| vwap | double | 成交量加权平均价 |
| pre_close | double | 前收盘价 |
| change | double | 涨跌额 |
| change_rate | double | 涨跌幅（%） |
| volume | double | 成交量 |
| amount | double | 成交额 |
| turnover | double | 换手率（%） |

示例：获取苹果公司近期前复权日线

```python
import panda_data
result = panda_data.get_us_daily_pre(
    symbol="AAPL",
    start_date="20260101",
    end_date="20260131",
    fields=["symbol","date","open","close","volume"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | close | volume |
|:---|:---|:---|:---|:---|
| AAPL | 20260102 | 271.515937 | 270.274317 | 37838054.0 |
| AAPL | 20260105 | 269.905321 | 266.534497 | 45647190.0 |
| AAPL | 20260106 | 266.275202 | 261.647798 | 52352090.0 |

## 港股股票基础信息

### get_hk_detail：获取港股的基本信息

数据范围 1921-01-01 ~ 至今；每日更新 18:00 ~ 19:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=154)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| status | Optional[integer] | 否 | 是否在市，1 -在市，0 -退市，-1 -未知 |
| date | Optional[string] | 否 | 交易日期,eg:"20250702"；为空时返回最新交易日 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| cn_name | string | 中文名 |
| local_name | string | 当地股票名称 |
| status | integer | 股票状态 |
| isin_code | string | 国际证券识别编码 |
| abbrev_symbol | string | 股票的名称缩写 |
| min_order_amount | string | 一手对应多少股 |
| trading_code | string | 交易代码 |
| rcs_asset_category_name | string | 资产类别名称 |
| business_sector | string | 业务领域名称（如“Banking & Investment Services”） |
| economic_sector | string | 经济领域名称（如“Financials”） |
| industry_group | string | 行业组名称（如“Banking Services”） |
| incorp_date | string | 公司成立日期 |
| office_address | string | 公司总部地址 |
| office_city | string | 总部城市 |
| office_country | string | 总部所在国家 |
| office_region | string | 总部所在地区 |
| postal_code | string | 总部邮政编码 |
| website | string | 公司网站 |
| listed_date | string | 上市日期 |
| board_type | string | 板块类别 |
| delisted_date | string | 退市日期 |

示例：示例1

```python
import panda_data
result = panda_data.get_hk_detail(
        symbol=["0001.HK","0002.HK","0003.HK"],
        fields=[""],
        date="20260902"
    )
print(result)
```

返回示例（前 3 行）：

| date | symbol | abbrev_symbol | board_type | business_sector | cn_name | delisted_date | economic_sector | incorp_date | industry_group | isin_code | listed_date | local_name | min_order_amount | name | office_address | office_city | office_country | office_region | postal_code | rcs_asset_category_name | status | trading_code | website |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 20260902 | 0001.HK | CKHUH | MAIN | Retailers | 長和 | None | Consumer Cyclicals | 2014-12-11 | Specialty Retailers | KYG217651051 | 1972-11-01 | CK HUTCHISON HOLDINGS LIMITED | 500.0 | CK HUTCHISON HOLDINGS LIMITED | 48th Floor, Cheung Kong Center, 2 Queen's Road Central, Central | None | Hong Kong | Asia | None | Equity\Ordinary Share | 1 | 0001 | https://www.ckh.com.hk/ |
| 20260902 | 0002.HK | CLPHL | MAIN | Utilities | 中電控股 | None | Utilities | 1997-10-24 | Electric Utilities & IPPs | HK0002007356 | 1980-01-02 | 中電控股有限公司 | 500.0 | Zhong Dian Kong Gu You Xian Gong Si | 8 Laguna Verde Avenue, Hung Hom, Kowloon | None | Hong Kong | Asia | None | Equity\Ordinary Share | 1 | 0002 | https://www.clpgroup.com/ |
| 20260902 | 0003.HK | HKCNG | MAIN | Utilities | 香港中華煤氣 | None | Utilities | 1982-10-14 | Natural Gas Utilities | HK0003000038 | 1960-04-11 | The Hong Kong & China Gas Co Ltd | 1000.0 | The Hong Kong & China Gas Co Ltd | 23/F 363 Java Road North Point | None | Hong Kong | Asia | 999077 | Equity\Ordinary Share | 1 | 0003\|864603 | https://www.towngas.com/ |

### get_hk_detail_all：港股symbol获取接口可获取退市数据

数据范围 2000-01-01 ~ 至今；每日更新 16:00 ~ 17:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=338)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| status | Optional[integer] | 否 | 是否在市，1 -在市，0 -退市，-1 -未知 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| name | string | 股票名称 |
| cn_name | string | 中文名 |
| local_name | string | 当地股票名称 |
| status | integer | 股票状态 |
| isin_code | string | 国际证券识别编码 |
| abbrev_symbol | string | 股票的名称缩写 |
| min_order_amount | string | 一手对应多少股 |
| trading_code | string | 交易代码 |
| rcs_asset_category_name | string | 资产类别名称 |
| business_sector | string | 业务领域名称（如“Banking & Investment Services”） |
| economic_sector | string | 经济领域名称（如“Financials”） |
| industry_group | string | 行业组名称（如“Banking Services”） |
| incorp_date | string | 公司成立日期 |
| office_address | string | 公司总部地址 |
| office_city | string | 总部城市 |
| office_country | string | 总部所在国家 |
| office_region | string | 总部所在地区 |
| postal_code | string | 总部邮政编码 |
| website | string | 公司网站 |
| listed_date | string | 上市日期 |
| board_type | string | 板块类别 |
| delisted_date | string | 退市日期 |

示例：示例1

```python
import panda_data
result = panda_data.get_hk_detail_all(
        symbol=["0001.HK","0002.HK","0003.HK"],
        fields=[""]
    )
print(result)
```

返回示例（前 3 行）：

| symbol | abbrev_symbol | board_type | business_sector | cn_name | delisted_date | economic_sector | incorp_date | industry_group | isin_code | listed_date | local_name | min_order_amount | name | office_address | office_city | office_country | office_region | postal_code | rcs_asset_category_name | status | trading_code | website |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 0001.HK | CKHUH | MAIN | Retailers | 長和 | None | Consumer Cyclicals | 2014-12-11 | Specialty Retailers | KYG217651051 | 1972-11-01 | CK HUTCHISON HOLDINGS LIMITED | 500.0 | CK HUTCHISON HOLDINGS LIMITED | 48th Floor, Cheung Kong Center, 2 Queen's Road Central, Central | None | Hong Kong | Asia | None | Equity\Ordinary Share | 1 | 0001 | https://www.ckh.com.hk/ |
| 0002.HK | CLPHL | MAIN | Utilities | 中電控股 | None | Utilities | 1997-10-24 | Electric Utilities & IPPs | HK0002007356 | 1980-01-02 | 中電控股有限公司 | 500.0 | Zhong Dian Kong Gu You Xian Gong Si | 8 Laguna Verde Avenue, Hung Hom, Kowloon | None | Hong Kong | Asia | None | Equity\Ordinary Share | 1 | 0002 | https://www.clpgroup.com/ |
| 0003.HK | HKCNG | MAIN | Utilities | 香港中華煤氣 | None | Utilities | 1982-10-14 | Natural Gas Utilities | HK0003000038 | 1960-04-11 | The Hong Kong & China Gas Co Ltd | 1000.0 | The Hong Kong & China Gas Co Ltd | 23/F 363 Java Road North Point | None | Hong Kong | Asia | 999077 | Equity\Ordinary Share | 1 | 0003\|864603 | https://www.towngas.com/ |

## 美股股票基础信息

### get_us_detail：获取美股的基本信息

数据范围 1753-01-01 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=155)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| status | Optional[integer] | 否 | 是否在市，1 -在市，0 -退市，-1 -未知 |
| date | Optional[string] | 否 | 交易日期,eg:"20250702"；为空时返回最新交易日 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| listed_date | string | 上市日期 |
| local_name | string | 当地股票名称 |
| exchange_name | string | 交易所名称 |
| status | integer | 股票状态 |
| isin_code | string | 国际证券识别编码 |
| abbrev_symbol | string | 股票的名称缩写 |
| min_order_amount | string | 一手对应多少股 |
| trading_code | string | 交易代码 |
| rcs_asset_category_name | string | 资产类别名称 |
| business_sector | string | 业务领域名称（如“Banking & Investment Services”） |
| economic_sector | string | 经济领域名称（如“Financials”） |
| industry_group | string | 行业组名称（如“Banking Services”） |
| incorp_date | string | 公司成立日期 |
| office_address | string | 公司总部地址 |
| office_city | string | 总部城市 |
| office_country | string | 总部所在国家 |
| office_region | string | 总部所在地区 |
| postal_code | string | 总部邮政编码 |
| website | string | 公司网站 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_detail(
    symbol=["AAPL", "TELA"],
    fields=[""],
    date="20260902"
)
print(result)
```

返回示例（前 3 行）：

| date | symbol | abbrev_symbol | business_sector | economic_sector | exchange_name | incorp_date | industry_group | isin_code | listed_date | local_name | min_order_amount | name | office_address | office_city | office_country | office_region | postal_code | rcs_asset_category_name | status | trading_code | website |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 20260902 | AAPL | AAPL | Technology Equipment | Technology | NASDAQ BASIC - NASDAQ | 1977-01-03 | Computers, Phones & Household Electronics | US0378331005 | 1980-12-12 | APPLE INC. | 40.0 | APPLE INC. | One Apple Park Way | CUPERTINO | United States of America | Americas | 95014 | Equity\Ordinary Share | 1 | 865985 | https://www.apple.com/ |
| 20260902 | TELA | TELAX | Healthcare Services & Equipment | Healthcare | NASDAQ BASIC - NASDAQ | 2012-04-17 | Healthcare Equipment & Supplies | US8723811084 | 2019-11-08 | TELA BIO, INC. | 100.0 | TELA BIO, INC. | 1 Great Valley Parkway, Suite 24 | MALVERN | United States of America | Americas | 19355 | Equity\Ordinary Share | 1 | NaN | https://www.telabio.com/ |

### get_us_detail_all：美股symbol获取接口可获取退市数据

数据范围 2000-01-01 ~ 至今；每日更新 16:00 ~ 17:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=339)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| status | Optional[integer] | 否 | 是否在市，1 -在市，0 -退市，-1 -未知 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| name | string | 股票名称 |
| listed_date | string | 上市日期 |
| local_name | string | 当地股票名称 |
| exchange_name | string | 交易所名称 |
| status | integer | 股票状态 |
| isin_code | string | 国际证券识别编码 |
| abbrev_symbol | string | 股票的名称缩写 |
| min_order_amount | string | 一手对应多少股 |
| trading_code | string | 交易代码 |
| rcs_asset_category_name | string | 资产类别名称 |
| business_sector | string | 业务领域名称（如“Banking & Investment Services”） |
| economic_sector | string | 经济领域名称（如“Financials”） |
| industry_group | string | 行业组名称（如“Banking Services”） |
| incorp_date | string | 公司成立日期 |
| office_address | string | 公司总部地址 |
| office_city | string | 总部城市 |
| office_country | string | 总部所在国家 |
| office_region | string | 总部所在地区 |
| postal_code | string | 总部邮政编码 |
| website | string | 公司网站 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_detail_all(
    symbol=["AAPL", "TELA"],
    fields=[""]
)
print(result)
```

返回示例（前 3 行）：

| symbol | abbrev_symbol | business_sector | economic_sector | exchange_name | incorp_date | industry_group | isin_code | listed_date | local_name | min_order_amount | name | office_address | office_city | office_country | office_region | postal_code | rcs_asset_category_name | status | trading_code | website |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| AAPL | AAPL | Technology Equipment | Technology | NASDAQ BASIC - NASDAQ | 1977-01-03 | Computers, Phones & Household Electronics | US0378331005 | 1980-12-12 | APPLE INC. | 40.0 | APPLE INC. | One Apple Park Way | CUPERTINO | United States of America | Americas | 95014 | Equity\Ordinary Share | 1 | 865985 | https://www.apple.com/ |
| TELA | TELAX | Healthcare Services & Equipment | Healthcare | NASDAQ BASIC - NASDAQ | 2012-04-17 | Healthcare Equipment & Supplies | US8723811084 | 2019-11-08 | TELA BIO, INC. | 100.0 | TELA BIO, INC. | 1 Great Valley Parkway, Suite 24 | MALVERN | United States of America | Americas | 19355 | Equity\Ordinary Share | 1 | NaN | https://www.telabio.com/ |

## 港股公司事件

### get_stock_dividend_event：获取股票分红相关的事件

数据范围 2000-01-03 ~ 至今；每日更新 18:00 ~ 19:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=220)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| publish_date | string | 事件公告发布日期（日期筛选依据） |
| symbol | string | 股票代码 |
| excute_date | string | 事件执行日期 |
| event_type | string | 事件类型：ExDividends（除息），SpecialDividendsCash（现金特别股息），RegularDividendCashWithAlternative（常规现金股息，可选择股票股息），RegularDividendStockWithAlternative（常规股票股息，可选择现金股息），SpecialDividendsStock（股票特别股息），StockSplits（股票拆分），SpecialDividendCashWithAlternative（特别现金股息，可选择股票股息），RegularDividendsStock（常规股票股息），SpecialDividendStockWithAlternative（特别股票股息，可选择现金股息） |
| number | string | 每股金额 |
| currency | string | 交易币种 |
| event | string | 事件 |

示例：获取一定时间内某个港股分红相关的事件

```python
import panda_data
result = panda_data.get_stock_dividend_event(
    symbol="9999.HK",
    fields=[],
    start_date="20250101",
    end_date="20260501",
)
print(result)
```

返回示例（前 3 行）：

| symbol | publish_date | excute_date | event_type | number | currency | event |
|:---|:---|:---|:---|:---|:---|:---|
| 9999.HK | 20250305 | 20250317 | ExDividends | 0.24405 | USD | 9999.HK Final Cash Dividend of gross USD 0.244... |
| 9999.HK | 20250529 | 20250610 | ExDividends | 0.135 | USD | 9999.HK Interim Cash Dividend of gross USD 0.1... |
| 9999.HK | 20250827 | 20250908 | ExDividends | 0.114 | USD | 9999.HK Interim Cash Dividend of gross USD 0.1... |

### get_stock_market_event：获取市场活动相关的事件

数据范围 2021-03-29 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=221)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| info_date | string | 公告日期（日期筛选依据） |
| symbol | string | 股票代码 |
| start_date | string | 事件执行日期 |
| end_date | string | 事件完成日期 |
| is_estimated | integer | 事件是否被预计（0表示否，1表示是） |
| event_type | string | 事件类型：IpoLockupExpirations（IPO锁定期到期），SecondaryFilings（二次发行备案），SecondaryPricings（二次发行定价），SecondaryWithdrawals（二次发行撤销），IpoPricings（IPO定价），IpoFilings（IPO备案） |
| fiscal_quarter | string | 财年季度（若事件不涉及财年季度则此列为空） |
| event | string | 事件 |

示例：获取一定时间内全部港股市场活动相关的事件

```python
import panda_data
result = panda_data.get_stock_market_event(
    symbol="",
    fields=[],
    start_date="20250101",
    end_date="20260401",
)
print(result)
```

返回示例（前 3 行）：

| symbol | start_date | end_date | event | is_estimated | info_date | event_type | fiscal_quarter |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 0020.HK | 20260329 | 20260329 | SenseTime Group Inc Prices US$405M Follow-On | 0 | 20251230 | IpoLockupExpirations | None |
| 0092.HK | 20260203 | 20260203 | Champion Tech Hldg Ltd Prices US$3M Follow-On | 0 | 20260205 | SecondaryPricings | None |
| 0139.HK | 20260122 | 20260122 | Smart Fish Wealthlink Hldg Ltd Announces US$5M Follow-On | 0 | 20260309 | SecondaryFilings | None |

### get_stock_meeting_event：获取公司会议相关的事件

数据范围 2001-04-05 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=222)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| info_date | string | 公告日期（日期筛选依据） |
| symbol | string | 股票代码 |
| start_date | string | 事件执行日期 |
| end_date | string | 事件完成日期 |
| is_estimated | integer | 事件是否被预计（0表示否，1表示是） |
| event_type | string | 事件类型：ShareholderAndAnnualMeetings（股东及年度会议），ExtraordinaryShareholdersMeeting（特别股东大会），M&APresentation（并购演示），CorporateSalesRelease（公司销售发布），CorporatePresentation（公司演示），OtherCorporate（其他公司事件） |
| fiscal_quarter | string | 财年季度（若事件不涉及财年季度则此列为空） |
| event | string | 事件 |

示例：获取一定时间内全部港股公司会议相关的事件

```python
import panda_data
result = panda_data.get_stock_meeting_event(
    symbol="",
    fields=[],
    start_date="20250101",
    end_date="20260401",
)
print(result)
```

返回示例（前 3 行）：

| symbol | start_date | end_date | event | is_estimated | info_date | event_type | fiscal_quarter |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 0001.HK | 20250522 | 20250522 | CK Hutchison Holdings Ltd Annual Shareholders ... | 0 | 20250527 | ShareholderAndAnnualMeetings | None |
| 0002.HK | 20250509 | 20250509 | CLP Holdings Ltd Annual Shareholders Meeting | 0 | 20250515 | ShareholderAndAnnualMeetings | None |
| 0002.HK | 20220506 | 20220506 | CLP Holdings Ltd Annual Shareholders Meeting | 0 | 20250915 | ShareholderAndAnnualMeetings | None |

### get_stock_financial_event：获取财务披露相关的事件

数据范围 2000-01-13 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=223)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| info_date | string | 公告日期（日期筛选依据） |
| symbol | string | 股票代码 |
| start_date | string | 事件执行日期 |
| end_date | string | 事件完成日期 |
| is_estimated | integer | 事件是否被预计（0表示否，1表示是） |
| event_type | string | 事件类型：EarningsPresentation（财报演示），EarningsReleases（财报发布），EarningsCallsAndPresentations（财报电话会议及演示），GuidanceCallsAndPresentations（业绩指引电话会议及演示），InterimManagementStatementRelease（中期管理层声明发布），InterimManagementStatementCall（中期管理层声明电话会议），EarningsPressConference（财报新闻发布会），GuidancePresentation（业绩指引演示） |
| fiscal_quarter | string | 财年季度（若事件不涉及财年季度则此列为空） |
| event | string | 事件 |

示例：获取一定时间内全部港股财务披露相关的事件

```python
import panda_data
result = panda_data.get_stock_financial_event(
    symbol="",
    fields=[],
    start_date="20250101",
    end_date="20260401",
)
print(result)
```

返回示例（前 3 行）：

| symbol | start_date | end_date | event | is_estimated | info_date | event_type | fiscal_quarter |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 0001.HK | 20250320 | 20250320 | Full Year 2024 CK Hutchison Holdings Ltd Earni... | 0 | 20250430 | EarningsReleases | 2024q4 |
| 0001.HK | 20250814 | 20250814 | Half Year 2025 CK Hutchison Holdings Ltd Earni... | 0 | 20250731 | EarningsReleases | 2025q2 |
| 0001.HK | 20250814 | 20250814 | Half Year 2025 CK Hutchison Holdings Ltd Earni... | 0 | 20250815 | EarningsPresentation | 2025q2 |

### get_stock_ir_event：获取投资者关系活动相关的事件

数据范围 2000-01-13 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=224)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| info_date | string | 公告日期（日期筛选依据） |
| symbol | string | 股票代码 |
| start_date | string | 事件执行日期 |
| end_date | string | 事件完成日期 |
| is_estimated | integer | 事件是否被预计（0表示否，1表示是） |
| event_type | string | 事件类型：CorporateAnalystMeetings（公司分析师会议），ConferencePresentations（会议演示），CorporateCallsAndPresentations（公司电话会议及演示），BrokerageAnalystCalls（券商分析师电话会议），CorporateInvestorRoadshow（公司投资者路演），Conferences（会议），SalesConferenceCall（销售电话会议），SyndicateRoadshows（银团路演），BrokerageAnalystMeetings（券商分析师会议），CompanyVisits（公司实地考察），SalesPresentation（销售演示），IndustrySpecificCall（行业特定电话会议），IndustrySpecificPresentation（行业特定演示），SalesAndTradingStatementCallsAndPresentations（销售与交易声明电话会议及演示） |
| fiscal_quarter | string | 财年季度（若事件不涉及财年季度则此列为空） |
| event | string | 事件 |

示例：获取一定时间内全部港股财务批量相关的事件

```python
import panda_data
result = panda_data.get_stock_ir_event(
    symbol="",
    fields=[],
    start_date="20250101",
    end_date="20260401",
)
print(result)
```

返回示例（前 3 行）：

| symbol | start_date | end_date | event | is_estimated | info_date | event_type | fiscal_quarter |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 0002.HK | 20250225 | 20250226 | CLP Holdings Ltd Non-Deal Roadshow - Hong Kong | 0 | 20250303 | CorporateInvestorRoadshow | None |
| 0002.HK | 20250227 | 20250227 | CLP Holdings Ltd Non-Deal Roadshow - Japan | 0 | 20250306 | CorporateInvestorRoadshow | None |
| 0002.HK | 20250303 | 20250307 | CLP Holdings Ltd Non-Deal Roadshow - US & Canada | 0 | 20250311 | CorporateInvestorRoadshow | None |

## 美股公司事件

### get_stock_dividend_activity：获取股票分红相关的事件

数据范围 2000-01-06 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=225)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| publish_date | string | 事件公告发布日期（日期筛选依据） |
| symbol | string | 股票代码 |
| excute_date | string | 事件执行日期 |
| event_type | string | 事件类型：ExDividends（除息），SpecialDividendsCash（现金特别股息），StockSplits（股票拆分），CapitalGainsCash（资本收益现金分配），RegularDividendCashWithAlternative（常规现金股息，可选择股票股息），RegularDividendStockWithAlternative（常规股票股息，可选择现金股息），RegularDividendsStock（常规股票股息），SpecialDividendCashWithAlternative（特别现金股息，可选择股票股息），OtherDividendsCash（其他现金股息），SpecialDividendsStock（股票特别股息），SpecialDividendStockWithAlternative（特别股票股息，可选择现金股息） |
| number | string | 每股金额 |
| currency | string | 交易币种 |
| event | string | 事件 |

示例：获取一定时间内某个美股分红相关的事件

```python
import panda_data
result = panda_data.get_stock_dividend_activity(
    symbol="AAPL",
    fields=[],
    start_date="20250101",
    end_date="20260501",
)
print(result)
```

返回示例（前 3 行）：

| symbol | publish_date | excute_date | event_type | number | currency | event |
|:---|:---|:---|:---|:---|:---|:---|
| AAPL | 20250210 | 20250213 | ExDividends | 0.25 | USD | AAPL.NB Interim Cash Dividend of gross USD 0.25 paid on Feb 13, 2025 going ex on Feb 10, 2025 |
| AAPL | 20250512 | 20250515 | ExDividends | 0.26 | USD | AAPL.NB Interim Cash Dividend of gross USD 0.26 paid on May 15, 2025 going ex on May 12, 2025 |
| AAPL | 20250811 | 20250814 | ExDividends | 0.26 | USD | AAPL.NB Final Cash Dividend of gross USD 0.26 paid on Aug 14, 2025 going ex on Aug 11, 2025 |

### get_stock_market_activity：获取市场活动相关的事件

数据范围 2025-02-23 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=226)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| info_date | string | 公告日期（日期筛选依据） |
| symbol | string | 股票代码 |
| start_date | string | 事件执行日期 |
| end_date | string | 事件完成日期 |
| is_estimated | integer | 事件是否被预计（0表示否，1表示是） |
| event_type | string | 事件类型：IpoPricings（IPO定价），IpoFilings（IPO备案），SecondaryFilings（二次发行备案），IpoLockupExpirations（IPO锁定期到期），SecondaryPricings（二次发行定价），SecondaryWithdrawals（二次发行撤销），IpoWithdrawals（IPO撤销） |
| fiscal_quarter | string | 财年季度（若事件不涉及财年季度则此列为空） |
| event | string | 事件 |

示例：获取一定时间内全部美股市场活动相关的事件

```python
import panda_data
result = panda_data.get_stock_market_activity(
    symbol="",
    fields=[],
    start_date="20250101",
    end_date="20260401",
)
print(result)
```

返回示例（前 3 行）：

| symbol | start_date | end_date | event | is_estimated | info_date | event_type | fiscal_quarter |
|:---|:---|:---|:---|:---|:---|:---|:---|
| AACI | 20260218 | 20260218 | Armada Acquisition Corp III Prices US$225M IPO | 0 | 20260226 | IpoPricings | None |
| AACIW | 20260218 | 20260218 | Armada Acquisition Corp III Prices US$225M IPO | 0 | 20260226 | IpoPricings | None |
| AACO | 20260219 | 20260219 | Abony Acq Corp I Prices US$200M IPO | 0 | 20260223 | IpoPricings | None |

### get_stock_meeting_activity：获取公司会议相关的事件

数据范围 2000-01-04 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=227)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| info_date | string | 公告日期（日期筛选依据） |
| symbol | string | 股票代码 |
| start_date | string | 事件执行日期 |
| end_date | string | 事件完成日期 |
| is_estimated | integer | 事件是否被预计（0表示否，1表示是） |
| event_type | string | 事件类型：ShareholderAndAnnualMeetings（股东及年度会议），ExtraordinaryShareholdersMeeting（特别股东大会），OtherCorporate（其他公司事件），CorporateSalesRelease（公司销售发布），CorporatePresentation（公司演示），M&APresentation（并购演示） |
| fiscal_quarter | string | 财年季度（若事件不涉及财年季度则此列为空） |
| event | string | 事件 |

示例：获取一定时间内全部美股公司会议相关的事件

```python
import panda_data
result = panda_data.get_stock_meeting_activity(
    symbol="",
    fields=[],
    start_date="20250101",
    end_date="20260401",
)
print(result)
```

返回示例（前 3 行）：

| symbol | start_date | end_date | event | is_estimated | info_date | event_type | fiscal_quarter |
|:---|:---|:---|:---|:---|:---|:---|:---|
| A | 20250313 | 20250313 | Agilent Technologies Inc Annual Shareholders M... | 0 | 20250313 | ShareholderAndAnnualMeetings | None |
| A | 20250515 | 20250515 | Agilent Technologies Inc Annual Shareholders M... | 0 | 20250521 | ShareholderAndAnnualMeetings | None |
| A | 20110301 | 20110301 | Agilent Technologies Inc. Annual Shareholders ... | 0 | 20260105 | ShareholderAndAnnualMeetings | None |

### get_stock_financial_activity：获取财务披露相关的事件

数据范围 2000-01-03 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=228)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| info_date | string | 公告日期（日期筛选依据） |
| symbol | string | 股票代码 |
| start_date | string | 事件执行日期 |
| end_date | string | 事件完成日期 |
| is_estimated | integer | 事件是否被预计（0表示否，1表示是） |
| event_type | string | 事件类型：EarningsReleases（财报发布），EarningsCallsAndPresentations（财报电话会议及演示），GuidanceCallsAndPresentations（业绩指引电话会议及演示），EarningsPresentation（财报演示），GuidancePresentation（业绩指引演示），EarningsPressConference（财报新闻发布会），InterimManagementStatementRelease（中期管理层声明发布），InterimManagementStatementCall（中期管理层声明电话会议），InterimManagementStatementPresentation（中期管理层声明演示） |
| fiscal_quarter | string | 财年季度（若事件不涉及财年季度则此列为空） |
| event | string | 事件 |

示例：获取一定时间内全部美股财务披露相关的事件

```python
import panda_data
result = panda_data.get_stock_financial_activity(
    symbol="",
    fields=[],
    start_date="20250101",
    end_date="20260401",
)
print(result)
```

返回示例（前 3 行）：

| symbol | start_date | end_date | event | is_estimated | info_date | event_type | fiscal_quarter |
|:---|:---|:---|:---|:---|:---|:---|:---|
| A | 20011115 | 20011115 | Q4 2001 Agilent Technologies Earnings Conferen... | 0 | 20251023 | EarningsCallsAndPresentations | None |
| A | 20130214 | 20130214 | Q1 2013 Agilent Technologies Inc. Earnings Con... | 0 | 20260105 | EarningsCallsAndPresentations | None |
| A | 20051114 | 20051114 | Q4 2005 Agilent Technologies Inc. Earnings Con... | 0 | 20260105 | EarningsCallsAndPresentations | None |

### get_stock_ir_activity：获取投资者关系活动相关的事件

数据范围 2000-01-04 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=229)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| info_date | string | 公告日期（日期筛选依据） |
| symbol | string | 股票代码 |
| start_date | string | 事件执行日期 |
| end_date | string | 事件完成日期 |
| is_estimated | integer | 事件是否被预计（0表示否，1表示是） |
| event_type | string | 事件类型：ConferencePresentations（会议演示），CorporateAnalystMeetings（公司分析师会议），CorporateCallsAndPresentations（公司电话会议及演示），BrokerageAnalystMeetings（券商分析师会议），CompanyVisits（公司实地考察），Conferences（会议），IndustrySpecificCall（行业特定电话会议），CorporateInvestorRoadshow（公司投资者路演），SyndicateRoadshows（银团路演），BrokerageAnalystCalls（券商分析师电话会议），SalesAndTradingStatementCallsAndPresentations（销售与交易声明电话会议及演示），IndustrySpecificPresentation（行业特定演示），SalesConferenceCall（销售电话会议），SalesPresentation（销售演示），TradingStatementPresentation（交易声明演示） |
| fiscal_quarter | string | 财年季度（若事件不涉及财年季度则此列为空） |
| event | string | 事件 |

示例：获取一定时间内全部美股财务批量相关的事件

```python
import panda_data
result = panda_data.get_stock_ir_activity(
    symbol="",
    fields=[],
    start_date="20250101",
    end_date="20260401",
)
print(result)
```

返回示例（前 3 行）：

| symbol | start_date | end_date | event | is_estimated | info_date | event_type | fiscal_quarter |
|:---|:---|:---|:---|:---|:---|:---|:---|
| A | 20250114 | 20250114 | Agilent Technologies Inc at JPMorgan Healthcar... | 0 | 20250130 | ConferencePresentations | None |
| A | 20250304 | 20250304 | Agilent Technologies Inc at TD Cowen Healthcar... | 0 | 20250305 | ConferencePresentations | None |
| A | 20250604 | 20250604 | Agilent Technologies Inc at Jefferies Global H... | 0 | 20250604 | ConferencePresentations | None |

## 港股股东与投资者

### get_stock_investor_concentration：获取公司投资者集中度

数据范围 每周最新数据；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=230)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 交易币种 |
| total_investors | integer | 总投资者数 |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| total_sharehold | float | 总持股 |
| total_holdings_value | float | 总持股市值 |

示例：获取全部港股公司投资者集中度数据

```python
import panda_data
result = panda_data.get_stock_investor_concentration(
    symbol="",
    fields=[],
)
print(result)
```

返回示例（前 3 行）：

| symbol | currency | total_investors | investor_outstanding_ratio | total_sharehold | total_holdings_value |
|:---|:---|:---|:---|:---|:---|
| 0001.HK | HKD | 417 | 54.3183 | 2080422653.0 | 15091482785.530001 |
| 0002.HK | HKD | 310 | 41.4884 | 1048171956.0 | 9523360898.450001 |
| 0003.HK | HKD | 296 | 54.592 | 10186793788.0 | 8869891395.65999 |

### get_stock_top20_concentration：获取公司前20投资者集中度

数据范围 每周最新数据；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=231)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 交易币种 |
| top_investors_num | integer | 前n个投资者数（对于此接口通常为20，不足20个投资者的会返回小于20） |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| sharehold | float | 前n个投资者总持股 |
| holdings_value | float | 前n个投资者总持股市值 |

示例：获取全部港股公司投资者集中度数据

```python
import panda_data
result = panda_data.get_stock_top20_concentration(
    symbol="",
    fields=[],
)
print(result)
```

返回示例（前 3 行）：

| symbol | currency | top_investors_num | investor_outstanding_ratio | sharehold | holdings_value |
|:---|:---|:---|:---|:---|:---|
| 0001.HK | HKD | 20 | 45.8003 | 1754173454.0 | 12644103686.75 |
| 0002.HK | HKD | 20 | 38.2151 | 965487535.0 | 8755126047.93 |
| 0003.HK | HKD | 20 | 51.6348 | 9634980585.0 | 8366519691.31 |

### get_stock_investor_ranking：获取公司投资者排行

数据范围 每周最新数据；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=232)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| max_rank | Optional[integer] | 否 | 最大返回排名（小于等于20的正整数），默认为空返回前20名 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| investor_name | string | 投资者名称 |
| investor_type | string | 投资者类型 |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| sharehold | float | 投资者持股 |
| sharehold_change | float | 投资者持股较上一次报告变化 |
| info_date | string | 此次报告日期 |
| turnover_rating | string | 换手率评级 |
| currency | string | 交易币种 |
| rank | integer | 排行 |

示例：获取全部港股公司前10投资者数据

```python
import panda_data
result = panda_data.get_stock_investor_ranking(
    symbol="",
    fields=[],
    max_rank=10
)
print(result)
```

返回示例（前 3 行）：

| symbol | investor_name | investor_type | investor_outstanding_ratio | sharehold | sharehold_change | info_date | turnover_rating | rank | currency |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 0001.HK | Li (Ka Shing) | Individual Investor | 30.3634 | 1162932010.0 | 0.0 | 20251231 | LOW | 1 | HKD |
| 0001.HK | BlackRock Institutional Trust Company, N.A. | Investment Advisor | 2.7546 | 105500988.0 | -474500.0 | 20260508 | LOW | 2 | HKD |
| 0001.HK | The Vanguard Group, Inc. | Investment Advisor | 2.2835 | 87460954.0 | 134000.0 | 20260331 | LOW | 3 | HKD |

### get_stock_insider_trade：获取公司内部人交易活动

数据范围 2016-01-01 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=233)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"（此接口查询消息日期） |
| end_date | string | 是 | 结束日期,eg:"20250702"（此接口查询消息日期） |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| investor_name | string | 投资者名称 |
| investor_type | string | 投资者类型 |
| info_date | string | 消息日期（日期筛选依据） |
| insider_role | string | 内部人身份 |
| is_main_role | integer | 是否为主要人物（若某次内部交易涉及多个内部人，则此字段为1的为主要人物） |
| insider_active_date | string | 成为内部人日期 |
| insider_inactive_date | string | 不再视为内部人日期 |
| transaction_date | string | 交易发生日期 |
| transaction_type | string | 交易类型 |
| acquisition_type | string | 处置行为类型 |
| adjusted_trade_shares | float | 调整后交易股数 |
| reported_trade_shares | float | 申报交易股数 |
| trade_outstanding_ratio | float | 交易股数占总流通股比例 |
| transaction_price | float | 交易价格 |
| filing_currency_price | float | 申报时货币的价格 |
| filing_type | string | 申报文件类型 |
| transaction_holding_type | string | 交易持有方式 |
| adjusted_sharehold | float | 调整后持有股数 |
| reported_sharehold | float | 申报持有股数 |
| adjusted_indirect_sharehold | float | 调整后间接持有股数 |
| reported_indirect_sharehold | float | 申报间接持有股数 |
| currency | string | 交易币种 |

示例：获取一定时间内某港股公司内部人交易活动

```python
import panda_data
result = panda_data.get_stock_insider_trade(
    symbol="0004.HK",
    fields=[],
    start_date="20250101",
    end_date="20251231",
)
print(result)
```

返回示例（前 3 行）：

| symbol | investor_name | info_date | investor_type | insider_role | is_main_role | insider_active_date | insider_inactive_date | transaction_date | transaction_type | acquisition_type | adjusted_trade_shares | reported_trade_shares | trade_outstanding_ratio | transaction_price | filing_currency_price | filing_type | transaction_holding_type | adjusted_sharehold | reported_sharehold | adjusted_indirect_sharehold | reported_indirect_sharehold | currency |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 0004.HK | Fang (Kang Vincent) | 20250425 | Individual Investor | None | None | None | None | 20250425 | Sale of shares | Other | -100000.0 | -100000.0 | -0.0033 | 2.41 | 18.69 | Hong Kong Insider | DIR | 528000.0 | 528000.0 | None | None | HKD |
| 0004.HK | Fang (Kang Vincent) | 20250428 | Individual Investor | None | None | None | None | 20250428 | Sale of shares | Other | -100000.0 | -100000.0 | -0.0033 | 2.41 | 18.75 | Hong Kong Insider | DIR | 428000.0 | 428000.0 | None | None | HKD |
| 0004.HK | Fang (Kang Vincent) | 20250429 | Individual Investor | None | None | None | None | 20250429 | Sale of shares | Other | -100000.0 | -100000.0 | -0.0033 | 2.48 | 19.25 | Hong Kong Insider | DIR | 328000.0 | 328000.0 | None | None | HKD |

### get_stock_shareholder_holding：获取公司股东持股报告

数据范围 2023-03-27 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=234)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"（此接口查询持股报告日期） |
| end_date | string | 是 | 结束日期,eg:"20250702"（此接口查询持股报告日期） |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| investor_name | string | 投资者名称 |
| investor_category | string | 投资者大类 |
| investor_type | string | 投资者详细类别 |
| investment_activeness_orientation | string | 投资活动倾向 |
| turnover_rating | string | 换手率评级 |
| turnover_ratio | float | 换手率比例（相对于投资者总资产的交易活动量） |
| total_equity_assets | float | 总权益资产 |
| sharehold | float | 持有股数 |
| outstanding_ratio | float | 持股占总流通股比例 |
| hold_portfolio_ratio | float | 持仓占投资者投资组合比例 |
| sharehold_value | float | 持仓市值 |
| holding_date | string | 持股报告日期（日期筛选依据） |
| filing_type | string | 申报类型 |
| sharehold_change | float | 较上一次报告持股变动数量 |
| sharehold_value_change | float | 持仓市值变动 |
| outstanding_ratio_change | float | 占总流通股比例变动 |
| sharehold_change_ratio | float | 持股数变动百分比 |
| prev_sharehold | float | 上期持股数量 |
| prev_outstanding_ratio | float | 上期占总流通股比例 |
| prev_sharehold_value | float | 上期持仓市值 |
| prev_holding_date | string | 上期持股报告日期 |
| prev_filing_type | string | 上期申报类型 |
| currency | string | 交易币种 |

示例：获取一定时间内某港股公司股东持股报告

```python
import panda_data
result = panda_data.get_stock_shareholder_holding(
    symbol="8510.HK",
    fields=[],
    start_date="20250101",
    end_date="20251231",
)
print(result)
```

返回示例（前 3 行）：

| symbol | currency | investor_name | investor_category | investor_type | investment_activeness_orientation | turnover_rating | turnover_ratio | total_equity_assets | sharehold | outstanding_ratio | hold_portfolio_ratio | sharehold_value | holding_date | filing_type | sharehold_change | sharehold_value_change | outstanding_ratio_change | sharehold_change_ratio | prev_sharehold | prev_outstanding_ratio | prev_sharehold_value | prev_holding_date | prev_filing_type |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 8510.HK | HKD | Chuk (Stanley) | Strategic Entities | Individual Investor | None | LOW | 0.0 | 470731.86 | 46188800.0 | 19.3357 | 100.0 | 470731.86 | 20250630 | Hong Kong Insider | 0.0 | 0.0 | 100.0 | 0.0 | 46188800.0 | 19.3357 | 457944.91 | 20241231 | Hong Kong Insider |
| 8510.HK | HKD | Chuan (Hng Bok) | Strategic Entities | Individual Investor | None | LOW | 0.0 | 338128.58 | 33177600.0 | 13.8889 | 100.0 | 338128.58 | 20250630 | Shareholder Report | 0.0 | 0.0 | 100.0 | 0.0 | 33177600.0 | 13.8889 | 328943.66 | 20241231 | Shareholder Report |
| 8510.HK | HKD | Lau (Wing Kee) | Strategic Entities | Individual Investor | None | LOW | 0.0 | 234811.51 | 23040000.0 | 9.6451 | 100.0 | 234811.51 | 20250630 | Shareholder Report | 0.0 | 0.0 | 100.0 | 0.0 | 23040000.0 | 9.6451 | 228433.1 | 20241231 | Shareholder Report |

## 美股股东与投资者

### get_stock_investor_centralization：获取公司投资者集中度

数据范围 每周最新数据；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=235)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 交易币种 |
| total_investors | integer | 总投资者数 |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| total_sharehold | float | 总持股 |
| total_holdings_value | float | 总持股市值 |

示例：获取全部美股公司投资者集中度数据

```python
import panda_data
result = panda_data.get_stock_investor_centralization(
    symbol="",
    fields=[],
)
print(result)
```

返回示例（前 3 行）：

| symbol | currency | total_investors | investor_outstanding_ratio | total_sharehold | total_holdings_value |
|:---|:---|:---|:---|:---|:---|
| A | USD | 2179 | 94.8615 | 268087770.0 | 30796955988.750099 |
| AA | USD | 1357 | 85.0917 | 224548932.0 | 14511789922.24 |
| AACB | USD | 59 | 95.4638 | 21169172.0 | 218021501.65 |

### get_stock_top20_centralization：获取公司前20投资者集中度

数据范围 每周最新数据；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=236)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 交易币种 |
| top_investors_num | integer | 前n个投资者数（对于此接口通常为20，不足20个投资者的会返回小于20） |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| sharehold | float | 前n个投资者总持股 |
| holdings_value | float | 前n个投资者总持股市值 |

示例：获取全部美股公司投资者集中度数据

```python
import panda_data
result = panda_data.get_stock_top20_centralization(
    symbol="",
    fields=[],
)
print(result)
```

返回示例（前 3 行）：

| symbol | currency | top_investors_num | investor_outstanding_ratio | sharehold | holdings_value |
|:---|:---|:---|:---|:---|:---|
| A | USD | 20 | 47.6527 | 134667901.0 | 15438599260.389999 |
| AA | USD | 20 | 52.3056 | 138029578.0 | 8996013361.799999 |
| AACB | USD | 20 | 70.4783 | 15628560.0 | 160974168.0 |

### get_stock_investor_leaderboard：获取公司投资者排行

数据范围 每周最新数据；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=237)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| max_rank | Optional[integer] | 否 | 最大返回排名（小于等于20的正整数），默认为空返回前20名 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| investor_name | string | 投资者名称 |
| investor_type | string | 投资者类型 |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| sharehold | float | 投资者持股 |
| sharehold_change | float | 投资者持股较上一次报告变化 |
| info_date | string | 此次报告日期 |
| turnover_rating | string | 换手率评级 |
| currency | string | 交易币种 |
| rank | integer | 排行 |

示例：获取全部美股公司前10投资者数据

```python
import panda_data
result = panda_data.get_stock_investor_leaderboard(
    symbol="",
    fields=[],
    max_rank=10
)
print(result)
```

返回示例（前 3 行）：

| symbol | currency | investor_name | investor_type | investor_outstanding_ratio | sharehold | sharehold_change | info_date | turnover_rating | rank |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| A | USD | Vanguard Capital Management, LLC | Investment Advisor | 6.5042 | 18381030.0 | 18381030.0 | 20260331 | None | 1 |
| A | USD | BlackRock Institutional Trust Company, N.A. | Investment Advisor | 5.2327 | 14787598.0 | 89673.0 | 20260331 | LOW | 2 |
| A | USD | Vanguard Portfolio Management, LLC | Investment Advisor | 5.0788 | 14352682.0 | 14352682.0 | 20260331 | None | 3 |

### get_stock_insider_transaction：获取公司内部人交易活动

数据范围 2018-01-01 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=238)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"（此接口查询消息日期） |
| end_date | string | 是 | 结束日期,eg:"20250702"（此接口查询消息日期） |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| investor_name | string | 投资者名称 |
| investor_type | string | 投资者类型 |
| info_date | string | 消息日期（日期筛选依据） |
| insider_role | string | 内部人身份 |
| is_main_role | integer | 是否为主要人物（若某次内部交易涉及多个内部人，则此字段为1的为主要人物） |
| insider_active_date | string | 成为内部人日期 |
| insider_inactive_date | string | 不再视为内部人日期 |
| transaction_date | string | 交易发生日期 |
| transaction_type | string | 交易类型 |
| acquisition_type | string | 处置行为类型 |
| adjusted_trade_shares | float | 调整后交易股数 |
| reported_trade_shares | float | 申报交易股数 |
| trade_outstanding_ratio | float | 交易股数占总流通股比例 |
| transaction_price | float | 交易价格 |
| filing_currency_price | float | 申报时货币的价格 |
| filing_type | string | 申报文件类型 |
| transaction_holding_type | string | 交易持有方式 |
| adjusted_sharehold | float | 调整后持有股数 |
| reported_sharehold | float | 申报持有股数 |
| adjusted_indirect_sharehold | float | 调整后间接持有股数 |
| reported_indirect_sharehold | float | 申报间接持有股数 |
| currency | string | 交易币种 |

示例：获取一定时间内某美股公司内部人交易活动

```python
import panda_data
result = panda_data.get_stock_insider_transaction(
    symbol="AAPL",
    fields=[],
    start_date="20250101",
    end_date="20251231",
)
print(result)
```

返回示例（前 3 行）：

| symbol | investor_name | info_date | investor_type | insider_role | is_main_role | insider_active_date | insider_inactive_date | transaction_date | transaction_type | acquisition_type | adjusted_trade_shares | reported_trade_shares | trade_outstanding_ratio | transaction_price | filing_currency_price | filing_type | transaction_holding_type | adjusted_sharehold | reported_sharehold | adjusted_indirect_sharehold | reported_indirect_sharehold | currency |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| AAPL | Lozano (Monica Cecilia) | 20250201 | Individual Investor | None | 0.0 | None | None | 20250201 | Exercise or conversion of derivative security ... | Disposition | -1516.0 | -1516.0 | 0.0 | None | None | Form 4 | DIR | 0.0 | 0.0 | None | None | USD |
| AAPL | Sugar (Ronald D) | 20250201 | Individual Investor | None | 0.0 | None | None | 20250201 | Exercise or conversion of derivative security ... | Disposition | -1516.0 | -1516.0 | 0.0 | None | None | Form 4 | DIR | 0.0 | 0.0 | None | None | USD |
| AAPL | Jung (Andrea) | 20250201 | Individual Investor | None | 0.0 | None | None | 20250201 | Exercise or conversion of derivative security ... | Disposition | -1516.0 | -1516.0 | 0.0 | None | None | Form 4 | DIR | 0.0 | 0.0 | None | None | USD |

### get_stock_shareholder_report：获取公司股东持股报告

数据范围 2022-12-15 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=239)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期,eg:"20250702"（此接口查询持股报告日期） |
| end_date | string | 是 | 结束日期,eg:"20250702"（此接口查询持股报告日期） |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| investor_name | string | 投资者名称 |
| investor_category | string | 投资者大类 |
| investor_type | string | 投资者详细类别 |
| investment_activeness_orientation | string | 投资活动倾向 |
| turnover_rating | string | 换手率评级 |
| turnover_ratio | float | 换手率比例（相对于投资者总资产的交易活动量） |
| total_equity_assets | float | 总权益资产 |
| sharehold | float | 持有股数 |
| outstanding_ratio | float | 持股占总流通股比例 |
| hold_portfolio_ratio | float | 持仓占投资者投资组合比例 |
| sharehold_value | float | 持仓市值 |
| holding_date | string | 持股报告日期（日期筛选依据） |
| filing_type | string | 申报类型 |
| sharehold_change | float | 较上一次报告持股变动数量 |
| sharehold_value_change | float | 持仓市值变动 |
| outstanding_ratio_change | float | 占总流通股比例变动 |
| sharehold_change_ratio | float | 持股数变动百分比 |
| prev_sharehold | float | 上期持股数量 |
| prev_outstanding_ratio | float | 上期占总流通股比例 |
| prev_sharehold_value | float | 上期持仓市值 |
| prev_holding_date | string | 上期持股报告日期 |
| prev_filing_type | string | 上期申报类型 |
| currency | string | 交易币种 |

示例：获取一定时间内某美股公司股东持股报告

```python
import panda_data
result = panda_data.get_stock_shareholder_report(
    symbol="TSLA",
    fields=[],
    start_date="20250101",
    end_date="20251231",
)
print(result)
```

返回示例（前 3 行）：

| symbol | currency | investor_name | investor_category | investor_type | investment_activeness_orientation | turnover_rating | turnover_ratio | total_equity_assets | sharehold | outstanding_ratio | hold_portfolio_ratio | sharehold_value | holding_date | filing_type | sharehold_change | sharehold_value_change | outstanding_ratio_change | sharehold_change_ratio | prev_sharehold | prev_outstanding_ratio | prev_sharehold_value | prev_holding_date | prev_filing_type |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| TSLA | USD | Ehrenpreis (Ira Matthew) | Strategic Entities | Individual Investor | None | LOW | 26.4525 | 380410819.68 | 855394.0 | 0.0228 | 100.0 | 380410819.68 | 20250915 | Proxy | 0.0 | 0.0 | 100.0 | 0.0 | 855394.0 | 0.0228 | 296359805.24 | 20250527 | Insider Update |
| TSLA | USD | Murdoch (James Rupert) | Strategic Entities | Individual Investor | None | LOW | 33.7713 | 353243764.32 | 794306.0 | 0.0212 | 100.0 | 353243764.32 | 20250915 | Proxy | -180000.0 | -80049600.0 | 81.54 | -18.47 | 974306.0 | 0.026 | 300349310.62 | 20250711 | Insider Update |
| TSLA | USD | Denholm (Robyn M) | Strategic Entities | Individual Investor | None | LOW | 0.0 | 37801200.0 | 85000.0 | 0.0023 | 100.0 | 37801200.0 | 20250915 | Proxy | 0.0 | 0.0 | 100.0 | 0.0 | 85000.0 | 0.0023 | 29449100.0 | 20250506 | Insider Update |

## 港股核心数据

### get_stock_industry_median：获取公司最新行业中位统计数据

数据范围 2024-05-09 ~ 至今；每日更新 18:00 ~ 19:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=240)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 日期 |
| industry_name | string | 行业名称 |
| imed_rec_turnover_ttm | float | 应收账款周转率TTM |
| imed_asset_turnover_ttm | float | 总资产周转率TTM |
| imed_net_trade_cycle_days_ttm | float | 平均净营业周期TTM |
| imed_gross_div_yield_ttm | float | 当前股息率TTM |
| imed_net_div_yield_ttm | float | 当前净股息率TTM |
| imed_price_to_fcf_per_shr_ttm | float | 股价/每股自由现金流TTM |
| imed_retention_ratio_ttm | float | 盈利留存率TTM |
| imed_fa_turnover_ttm | float | 固定资产周转率TTM |
| imed_inv_turnover_ttm | float | 存货周转率TTM |
| imed_inv_ratio_ttm | float | 投资比率TTM |
| imed_net_debt_to_ebitda_ttm | float | 净债务/EBITDA TTM |
| imed_pretax_roa_ratio_ttm | float | 税前总资产收益率TTM |
| imed_pretax_roe_ratio_ttm | float | 税前净资产收益率TTM |
| imed_pe_excl_exord_ttm | float | 市盈率TTM |
| imed_price_to_fcf_net_div_ttm | float | 股价/每股FCFTTM |
| imed_price_to_cfo_per_shr_ttm | float | 股价/每股经营现金流TTM |
| imed_price_to_rev_per_shr_ttm | float | 股价/每股总收入TTM |
| imed_loan_loss_prov_to_loans_ratio_ttm | float | 贷款损失准备/净贷款TTM |
| imed_reinv_ratio_ttm | float | 再投资率TTM |
| imed_roe_avg_common_ttm | float | 平均普通股ROE TTM |
| imed_roic_ratio_ttm | float | 投入资本回报率TTM |
| imed_sales_per_emp_ttm | float | 人均销售额TTM |
| imed_sales_per_emp_ccy_ttm | string | 人均销售额-货币单位TTM |
| imed_wcap_to_rev_pct_chg_ttm | float | 营运资本/收入TTM |
| imed_pe_ttm | float | 当前市盈率TTM |
| imed_pb_ttm | float | 当前市净率TTM |
| imed_pcfo_ttm | float | 当前股价/经营现金流TTM |
| imed_ps_ttm | float | 当前市销率TTM |
| imed_core_tier1_ratio_fye_mid | float | 核心一级资本充足率 |
| imed_combined_ratio_insur_fye_mid | float | 综合比率-保险 |
| imed_curr_ratio_fye_mid | float | 流动比率 |
| imed_deposits_pct_chg_fye_mid | float | 存款环比变化 |
| imed_ebitda_margin_ratio_fye_mid | float | EBITDA利润率 |
| imed_efficiency_ratio_fye_mid | float | 效率比率 |
| imed_expense_ratio_insur_fye_mid | float | 费用率-保险 |
| imed_fee_rev_ratio_fye_mid | float | 手续费收入占比 |
| imed_gross_margin_ratio_fye_mid | float | 毛利率 |
| imed_net_income_margin_excl_exord_fye_mid | float | 普通股净利润率 |
| imed_tax_rate_ratio_fye_mid | float | 所得税率 |
| imed_insur_reserves_pct_chg_fye_mid | float | 保险准备金环比变化 |
| imed_int_coverage_ratio_fye_mid | float | 利息覆盖率 |
| imed_net_loans_pct_chg_fye_mid | float | 净贷款环比变化 |
| imed_nonperf_loans_to_gross_loans_ratio_fye_mid | float | 不良及减值贷款/总贷款 |
| imed_loans_to_deposits_ratio_fye_mid | float | 存贷比 |
| imed_loss_ratio_insur_fye_mid | float | 损失率-保险 |
| imed_lt_debt_to_tot_cap_ratio_fye_mid | float | 长期债务/总资本 |
| imed_cfo_abs_fye_mid | float | 经营活动现金流净额 |
| imed_cfo_ccy_fye_mid | string | 经营活动现金流-货币单位 |
| imed_nim_ratio_fye_mid | float | 净息差 |
| imed_net_margin_ratio_fye_mid | float | 净利润率 |
| imed_net_premiums_earned_diff_fye_mid | float | 已赚净保费 |
| imed_net_premiums_earned_diff_ccy_fye_mid | string | 已赚净保费-货币单位 |
| imed_nonint_inc_to_op_inc_ratio_fye_mid | float | 非利息收入/营业收入 |
| imed_op_lev_fye_mid | float | 经营杠杆 |
| imed_op_margin_ratio_fye_mid | float | 营业利润率 |
| imed_op_ratio_insur_fye_mid | float | 经营比率-保险 |
| imed_pb_fye_mid | float | 市净率 |
| imed_prov_doubtful_to_rec_ratio_fye_mid | float | 坏账准备/应收款项 |
| imed_quick_ratio_fye_mid | float | 速动比率 |
| imed_foreclosed_assets_to_loans_ratio_fye_mid | float | 法拍房地产/总贷款 |
| imed_securities_to_earn_assets_ratio_fye_mid | float | 证券/盈利资产 |
| imed_tax_complement_fye_mid | float | 税务互补率 |
| imed_assets_to_equity_ratio_fye_mid | float | 总资产/总权益 |
| imed_debt_to_equity_ratio_fye_mid | float | 总债务/普通股权益 |
| imed_rec_turnover_fye | float | 应收账款周转率 |
| imed_asset_turnover_fye | float | 总资产周转率 |
| imed_net_trade_cycle_days_fye | float | 平均净营业周期 |
| imed_core_tier1_ratio_fye | float | 核心一级资本充足率 |
| imed_combined_ratio_insur_fye | float | 综合比率-保险 |
| imed_curr_ratio_fye | float | 流动比率 |
| imed_deposits_pct_chg_fye | float | 存款环比变化 |
| imed_gross_div_yield_fye | float | 股息率 |
| imed_retention_ratio_fye | float | 盈利留存率 |
| imed_ebitda_margin_ratio_fye | float | EBITDA利润率 |
| imed_efficiency_ratio_fye | float | 效率比率 |
| imed_expense_ratio_insur_fye | float | 费用率-保险 |
| imed_fee_rev_ratio_fye | float | 手续费收入占比 |
| imed_fa_turnover_fye | float | 固定资产周转率 |
| imed_gross_margin_ratio_fye | float | 毛利率 |
| imed_net_income_margin_excl_exord_fye | float | 普通股净利润率 |
| imed_tax_rate_ratio_fye | float | 所得税率 |
| imed_insur_reserves_pct_chg_fye | float | 保险准备金环比变化 |
| imed_int_coverage_ratio_fye | float | 利息覆盖率 |
| imed_inv_turnover_fye | float | 存货周转率 |
| imed_inv_ratio_fye | float | 投资比率 |
| imed_net_loans_pct_chg_fye | float | 净贷款环比变化 |
| imed_nonperf_loans_to_gross_loans_ratio_fye | float | 不良贷款率 |
| imed_loans_to_deposits_ratio_fye | float | 存贷比 |
| imed_loss_ratio_insur_fye | float | 损失率-保险 |
| imed_lt_debt_to_tot_cap_ratio_fye | float | 长期债务/总资本 |
| imed_cfo_abs_fye | float | 经营现金流净额 |
| imed_cfo_ccy_fye | string | 经营现金流-货币单位 |
| imed_net_debt_to_ebitda_fye | float | 净债务/EBITDA |
| imed_nim_ratio_fye | float | 净息差 |
| imed_net_margin_ratio_fye | float | 净利润率 |
| imed_net_premiums_earned_diff_fye | float | 已赚净保费（环比变化），行业中位数 - 最近财年 |
| imed_net_premiums_earned_diff_ccy_fye | string | 已赚净保费（环比变化）- 货币单位，行业中位数 - 最近财年 |
| imed_nonint_inc_to_op_inc_ratio_fye | float | 非利息收入 / 营业收入，行业中位数 - 最近财年 |
| imed_op_lev_fye | float | 经营杠杆，行业中位数 - 最近财年 |
| imed_op_margin_ratio_fye | float | 营业利润率（%），行业中位数 - 最近财年 |
| imed_op_ratio_insur_fye | float | 经营比率 - 保险（%），行业中位数 - 最近财年 |
| imed_pretax_roa_ratio_fye | float | 税前总资产收益率（%），行业中位数 - 最近财年 |
| imed_pretax_roe_ratio_fye | float | 税前净资产收益率（%），行业中位数 - 最近财年 |
| imed_pb_fye | float | 股价 / 每股净资产，行业中位数 - 最近财年 |
| imed_pe_excl_exord_fye | float | 股价 / 稀释每股收益（不含非常项目），行业中位数 - 最近财年 |
| imed_price_to_fcf_net_div_fye | float | 股价 / 每股自由现金流（扣除股息），行业中位数 - 最近财年 |
| imed_price_to_cfo_per_shr_fye | float | 股价 / 每股经营活动现金流，行业中位数 - 最近财年 |
| imed_price_to_rev_per_shr_fye | float | 股价 / 每股总收入，行业中位数 - 最近财年 |
| imed_prov_doubtful_to_rec_ratio_fye | float | 坏账准备 / 应收款项净额（%），行业中位数 - 最近财年 |
| imed_loan_loss_prov_to_loans_ratio_fye | float | 贷款损失准备 / 净贷款总额（%），行业中位数 - 最近财年 |
| imed_quick_ratio_fye | float | 速动比率，行业中位数 - 最近财年 |
| imed_foreclosed_assets_to_loans_ratio_fye | float | 法拍房地产 / 总贷款总额（%），行业中位数 - 最近财年 |
| imed_reinv_ratio_fye | float | 再投资率（%），行业中位数 - 最近财年 |
| imed_roe_avg_common_fye | float | 平均普通股回报率（%），行业中位数 - 最近财年 |
| imed_roic_ratio_fye | float | 投入资本回报率（%），行业中位数 - 最近财年 |
| imed_sales_per_emp_fye | float | 人均销售额，行业中位数 - 最近财年 |
| imed_sales_per_emp_ccy_fye | string | 人均销售额 - 货币单位，行业中位数 - 最近财年 |
| imed_securities_to_earn_assets_ratio_fye | float | 证券占平均盈利资产比例（%），行业中位数 - 最近财年 |
| imed_tax_complement_fye | float | 税务互补率，行业中位数 - 最近财年 |
| imed_assets_to_equity_ratio_fye | float | 总资产 / 总权益，行业中位数 - 最近财年 |
| imed_debt_to_equity_ratio_fye | float | 总债务 / 普通股权益，行业中位数 - 最近财年 |
| imed_wcap_to_rev_pct_chg_fye | float | 营运资本占总收入百分比（环比变化），行业中位数 - 最近财年 |
| imed_rec_turnover_prev_fye | float | 应收账款周转率，行业中位数 - 上一财年 |
| imed_asset_turnover_prev_fye | float | 总资产周转率，行业中位数 - 上一财年 |
| imed_net_trade_cycle_days_prev_fye | float | 平均净营业周期（天），行业中位数 - 上一财年 |
| imed_core_tier1_ratio_prev_fye | float | 核心一级资本充足率（%），行业中位数 - 上一财年 |
| imed_combined_ratio_insur_prev_fye | float | 综合比率 - 保险（%），行业中位数 - 上一财年 |
| imed_curr_ratio_prev_fye | float | 流动比率，行业中位数 - 上一财年 |
| imed_deposits_pct_chg_prev_fye | float | 存款总额（环比%变化），行业中位数 - 上一财年 |
| imed_gross_div_yield_prev_fye | float | 股息率（普通股-毛率-%），行业中位数 - 上一财年 |
| imed_retention_ratio_prev_fye | float | 盈利留存率，行业中位数 - 上一财年 |
| imed_ebitda_margin_ratio_prev_fye | float | EBITDA 利润率（%），行业中位数 - 上一财年 |
| imed_efficiency_ratio_prev_fye | float | 效率比率（%），行业中位数 - 上一财年 |
| imed_expense_ratio_insur_prev_fye | float | 费用率 - 保险（%），行业中位数 - 上一财年 |
| imed_fee_rev_ratio_prev_fye | float | 手续费收入占比（%），行业中位数 - 上一财年 |
| imed_fa_turnover_prev_fye | float | 固定资产周转率，行业中位数 - 上一财年 |
| imed_gross_margin_ratio_prev_fye | float | 毛利率（%），行业中位数 - 上一财年 |
| imed_net_income_margin_excl_exord_prev_fye | float | 普通股可分配净利润率（不含非常项目，%），行业中位数 - 上一财年 |
| imed_tax_rate_ratio_prev_fye | float | 所得税率（%），行业中位数 - 上一财年 |
| imed_insur_reserves_pct_chg_prev_fye | float | 保险准备金总额（环比%变化），行业中位数 - 上一财年 |
| imed_int_coverage_ratio_prev_fye | float | 利息覆盖率，行业中位数 - 上一财年 |
| imed_inv_turnover_prev_fye | float | 存货周转率，行业中位数 - 上一财年 |
| imed_inv_ratio_prev_fye | float | 投资比率（%），行业中位数 - 上一财年 |
| imed_net_loans_pct_chg_prev_fye | float | 净贷款总额（环比%变化），行业中位数 - 上一财年 |
| imed_nonperf_loans_to_gross_loans_ratio_prev_fye | float | 不良及减值贷款 / 总贷款总额（%），行业中位数 - 上一财年 |
| imed_loans_to_deposits_ratio_prev_fye | float | 存贷比（期末），行业中位数 - 上一财年 |
| imed_loss_ratio_insur_prev_fye | float | 损失率 - 保险（%），行业中位数 - 上一财年 |
| imed_lt_debt_to_tot_cap_ratio_prev_fye | float | 长期债务占总资本比例（%），行业中位数 - 上一财年 |
| imed_cfo_abs_prev_fye | float | 经营活动现金流净额，行业中位数 - 上一财年 |
| imed_cfo_ccy_prev_fye | string | 经营活动现金流净额 - 货币单位，行业中位数 - 上一财年 |
| imed_net_debt_to_ebitda_prev_fye | float | 净债务 / EBITDA，行业中位数 - 上一财年 |
| imed_nim_ratio_prev_fye | float | 净息差（%），行业中位数 - 上一财年 |
| imed_net_margin_ratio_prev_fye | float | 净利润率（%），行业中位数 - 上一财年 |
| imed_net_premiums_earned_diff_prev_fye | float | 已赚净保费（环比变化），行业中位数 - 上一财年 |
| imed_net_premiums_earned_diff_ccy_prev_fye | string | 已赚净保费（环比变化）- 货币单位，行业中位数 - 上一财年 |
| imed_nonint_inc_to_op_inc_ratio_prev_fye | float | 非利息收入 / 营业收入，行业中位数 - 上一财年 |
| imed_op_lev_prev_fye | float | 经营杠杆，行业中位数 - 上一财年 |
| imed_op_margin_ratio_prev_fye | float | 营业利润率（%），行业中位数 - 上一财年 |
| imed_op_ratio_insur_prev_fye | float | 经营比率 - 保险（%），行业中位数 - 上一财年 |
| imed_pretax_roa_ratio_prev_fye | float | 税前总资产收益率（%），行业中位数 - 上一财年 |
| imed_pretax_roe_ratio_prev_fye | float | 税前净资产收益率（%），行业中位数 - 上一财年 |
| imed_pb_prev_fye | float | 股价 / 每股净资产，行业中位数 - 上一财年 |
| imed_pe_excl_exord_prev_fye | float | 股价 / 稀释每股收益（不含非常项目），行业中位数 - 上一财年 |
| imed_price_to_fcf_net_div_prev_fye | float | 股价 / 每股自由现金流（扣除股息），行业中位数 - 上一财年 |
| imed_price_to_cfo_per_shr_prev_fye | float | 股价 / 每股经营活动现金流，行业中位数 - 上一财年 |
| imed_price_to_rev_per_shr_prev_fye | float | 股价 / 每股总收入，行业中位数 - 上一财年 |
| imed_prov_doubtful_to_rec_ratio_prev_fye | float | 坏账准备 / 应收款项净额（%），行业中位数 - 上一财年 |
| imed_loan_loss_prov_to_loans_ratio_prev_fye | float | 贷款损失准备 / 净贷款总额（%），行业中位数 - 上一财年 |
| imed_quick_ratio_prev_fye | float | 速动比率，行业中位数 - 上一财年 |
| imed_foreclosed_assets_to_loans_ratio_prev_fye | float | 法拍房地产 / 总贷款总额（%），行业中位数 - 上一财年 |
| imed_reinv_ratio_prev_fye | float | 再投资率（%），行业中位数 - 上一财年 |
| imed_roe_avg_common_prev_fye | float | 平均普通股回报率（%），行业中位数 - 上一财年 |
| imed_roic_ratio_prev_fye | float | 投入资本回报率（%），行业中位数 - 上一财年 |
| imed_sales_per_emp_prev_fye | float | 人均销售额，行业中位数 - 上一财年 |
| imed_sales_per_emp_ccy_prev_fye | string | 人均销售额 - 货币单位，行业中位数 - 上一财年 |
| imed_securities_to_earn_assets_ratio_prev_fye | float | 证券占平均盈利资产比例（%），行业中位数 - 上一财年 |
| imed_tax_complement_prev_fye | float | 税务互补率，行业中位数 - 上一财年 |
| imed_assets_to_equity_ratio_prev_fye | float | 总资产 / 总权益，行业中位数 - 上一财年 |
| imed_debt_to_equity_ratio_prev_fye | float | 总债务 / 普通股权益，行业中位数 - 上一财年 |
| imed_wcap_to_rev_pct_chg_prev_fye | float | 营运资本占总收入百分比（环比变化），行业中位数 - 上一财年 |
| imed_dps_yield_cur_fye | float | 每股股息率（%），行业中位数 - 当前财年 |
| imed_fwd_ev_to_ebit_cur_fye | float | 前瞻企业价值 / EBIT，行业中位数 - 当前财年 |
| imed_fwd_ev_to_ebitda_cur_fye | float | 前瞻企业价值 / EBITDA，行业中位数 - 当前财年 |
| imed_fwd_ev_to_cfo_cur_fye | float | 前瞻企业价值 / 经营现金流，行业中位数 - 当前财年 |
| imed_fwd_ev_to_sales_cur_fye | float | 前瞻企业价值 / 销售额，行业中位数 - 当前财年 |
| imed_fwd_net_debt_to_ebitda_cur_fye | float | 前瞻净债务 / EBITDA，行业中位数 - 当前财年 |
| imed_fwd_pe_cur_fye | float | 前瞻市盈率（P/E），行业中位数 - 当前财年 |
| imed_fwd_peg_cur_fye | float | 前瞻市盈率相对盈利增长（P/E/G），行业中位数 - 当前财年 |
| imed_fwd_pb_cur_fye | float | 前瞻股价 / 每股净资产，行业中位数 - 当前财年 |
| imed_fwd_pcfo_cur_fye | float | 前瞻股价 / 每股现金流，行业中位数 - 当前财年 |
| imed_fwd_ps_cur_fye | float | 前瞻股价 / 每股销售额，行业中位数 - 当前财年 |
| imed_fwd_total_debt_to_ebitda_cur_fye | float | 前瞻总债务 / EBITDA，行业中位数 - 当前财年 |
| imed_dps_yield_ntm | float | 每股股息率（%），行业中位数 - 未来十二个月 |
| imed_fwd_ev_to_ebit_ntm | float | 前瞻企业价值 / EBIT，行业中位数 - 未来十二个月 |
| imed_fwd_ev_to_ebitda_ntm | float | 前瞻企业价值 / EBITDA，行业中位数 - 未来十二个月 |
| imed_fwd_ev_to_cfo_ntm | float | 前瞻企业价值 / 经营现金流，行业中位数 - 未来十二个月 |
| imed_fwd_ev_to_sales_ntm | float | 前瞻企业价值 / 销售额，行业中位数 - 未来十二个月 |
| imed_fwd_net_debt_to_ebitda_ntm | float | 前瞻净债务 / EBITDA，行业中位数 - 未来十二个月 |
| imed_fwd_pe_ntm | float | 前瞻市盈率（P/E），行业中位数 - 未来十二个月 |
| imed_fwd_peg_ntm | float | 前瞻市盈率相对盈利增长（P/E/G），行业中位数 - 未来十二个月 |
| imed_fwd_pcfo_ntm | float | 前瞻股价 / 每股现金流，行业中位数 - 未来十二个月 |
| imed_fwd_ps_ntm | float | 前瞻股价 / 每股销售额，行业中位数 - 未来十二个月 |
| imed_fwd_total_debt_to_ebitda_ntm | float | 前瞻总债务 / EBITDA，行业中位数 - 未来十二个月 |

示例：获取全部港股公司最新的部分行业中位统计数据

```python
import panda_data
result = panda_data.get_stock_industry_median(
    symbol=[""],
    fields=["imed_net_trade_cycle_days_ttm","imed_pretax_roa_ratio_ttm"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | imed_net_trade_cycle_days_ttm | imed_pretax_roa_ratio_ttm |
|:---|:---|:---|:---|
| 0001.HK | 20240920 | 83.950094 | None |
| 0001.HK | 20260429 | None | 4.280742 |
| 0001.HK | 20260430 | None | 4.280742 |

### get_stock_pv_indicator：获取公司最新价量指标数据

数据范围 2018-10-30 ~ 至今；每日更新 18:00 ~ 19:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=241)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| pv_beta_5y | float | 5年贝塔值（股价波动相对于市场） |
| pv_return_mtd | float | 本月至今涨跌幅（%） |
| pv_market_cap | float | 市值（数值） |
| pv_market_cap_currency | string | 市值（货币单位） |
| pv_market_cap_date | string | 市值（计算日期） |
| pv_high_52w | float | 52周最高价 |
| pv_high_52w_date | string | 52周最高价发生日期 |
| pv_low_52w | float | 52周最低价 |
| pv_low_52w_date | string | 52周最低价发生日期 |
| pv_rel_return_4w | float | 相对基准4周涨跌幅（%） |
| pv_return_13w | float | 13周涨跌幅（%） |
| pv_rel_return_13w | float | 相对基准13周涨跌幅（%） |
| pv_return_1d | float | 1日涨跌幅（%） |
| pv_return_26w | float | 26周涨跌幅（%） |
| pv_rel_return_26w | float | 相对基准26周涨跌幅（%） |
| pv_return_52w | float | 52周涨跌幅（%） |
| pv_rel_return_52w | float | 相对基准52周涨跌幅（%） |
| pv_return_5d | float | 5日涨跌幅（%） |
| pv_return_ytd | float | 年初至今涨跌幅（%） |
| pv_rel_return_ytd | float | 相对基准年初至今涨跌幅（%） |
| pv_avg_vol_10d | float | 10日平均成交量 |
| pv_avg_monthly_vol_13w | float | 13周平均月成交量 |
| pv_close | float | 最新收盘价 |
| pv_close_date | string | 最新收盘价日期 |
| pv_close_currency | string | 收盘价货币单位 |
| pv_avg_vol_90d | float | 90日平均成交量 |
| pv_avg_val_3m | float | 3个月平均日成交金额 |

示例：获取一定时间内某港股公司股东持股报告

```python
import panda_data
result = panda_data.get_stock_pv_indicator(
    symbol=[""],
    fields=["pv_beta_5y","pv_rel_return_26w"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | pv_beta_5y | pv_rel_return_26w |
|:---|:---|:---|
| 0001.HK | 0.593763 | 25.178635 |
| 0002.HK | 0.242764 | 15.211285 |
| 0003.HK | 0.430627 | 1.801169 |

## 美股核心数据

### get_stock_sector_median：获取公司最新行业中位统计数据

数据范围 2024-04-30 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=243)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 日期 |
| industry_name | string | 行业名称 |
| imed_rec_turnover_ttm | float | 应收账款周转率TTM |
| imed_asset_turnover_ttm | float | 总资产周转率TTM |
| imed_net_trade_cycle_days_ttm | float | 平均净营业周期TTM |
| imed_gross_div_yield_ttm | float | 当前股息率TTM |
| imed_net_div_yield_ttm | float | 当前净股息率TTM |
| imed_price_to_fcf_per_shr_ttm | float | 股价/每股自由现金流TTM |
| imed_retention_ratio_ttm | float | 盈利留存率TTM |
| imed_fa_turnover_ttm | float | 固定资产周转率TTM |
| imed_inv_turnover_ttm | float | 存货周转率TTM |
| imed_inv_ratio_ttm | float | 投资比率TTM |
| imed_net_debt_to_ebitda_ttm | float | 净债务/EBITDA TTM |
| imed_pretax_roa_ratio_ttm | float | 税前总资产收益率TTM |
| imed_pretax_roe_ratio_ttm | float | 税前净资产收益率TTM |
| imed_pe_excl_exord_ttm | float | 市盈率TTM |
| imed_price_to_fcf_net_div_ttm | float | 股价/每股FCFTTM |
| imed_price_to_cfo_per_shr_ttm | float | 股价/每股经营现金流TTM |
| imed_price_to_rev_per_shr_ttm | float | 股价/每股总收入TTM |
| imed_loan_loss_prov_to_loans_ratio_ttm | float | 贷款损失准备/净贷款TTM |
| imed_reinv_ratio_ttm | float | 再投资率TTM |
| imed_roe_avg_common_ttm | float | 平均普通股ROE TTM |
| imed_roic_ratio_ttm | float | 投入资本回报率TTM |
| imed_sales_per_emp_ttm | float | 人均销售额TTM |
| imed_sales_per_emp_ccy_ttm | string | 人均销售额-货币单位TTM |
| imed_wcap_to_rev_pct_chg_ttm | float | 营运资本/收入TTM |
| imed_pe_ttm | float | 当前市盈率TTM |
| imed_pb_ttm | float | 当前市净率TTM |
| imed_pcfo_ttm | float | 当前股价/经营现金流TTM |
| imed_ps_ttm | float | 当前市销率TTM |
| imed_core_tier1_ratio_fye_mid | float | 核心一级资本充足率 |
| imed_combined_ratio_insur_fye_mid | float | 综合比率-保险 |
| imed_curr_ratio_fye_mid | float | 流动比率 |
| imed_deposits_pct_chg_fye_mid | float | 存款环比变化 |
| imed_ebitda_margin_ratio_fye_mid | float | EBITDA利润率 |
| imed_efficiency_ratio_fye_mid | float | 效率比率 |
| imed_expense_ratio_insur_fye_mid | float | 费用率-保险 |
| imed_fee_rev_ratio_fye_mid | float | 手续费收入占比 |
| imed_gross_margin_ratio_fye_mid | float | 毛利率 |
| imed_net_income_margin_excl_exord_fye_mid | float | 普通股净利润率 |
| imed_tax_rate_ratio_fye_mid | float | 所得税率 |
| imed_insur_reserves_pct_chg_fye_mid | float | 保险准备金环比变化 |
| imed_int_coverage_ratio_fye_mid | float | 利息覆盖率 |
| imed_net_loans_pct_chg_fye_mid | float | 净贷款环比变化 |
| imed_nonperf_loans_to_gross_loans_ratio_fye_mid | float | 不良及减值贷款/总贷款 |
| imed_loans_to_deposits_ratio_fye_mid | float | 存贷比 |
| imed_loss_ratio_insur_fye_mid | float | 损失率-保险 |
| imed_lt_debt_to_tot_cap_ratio_fye_mid | float | 长期债务/总资本 |
| imed_cfo_abs_fye_mid | float | 经营活动现金流净额 |
| imed_cfo_ccy_fye_mid | string | 经营活动现金流-货币单位 |
| imed_nim_ratio_fye_mid | float | 净息差 |
| imed_net_margin_ratio_fye_mid | float | 净利润率 |
| imed_net_premiums_earned_diff_fye_mid | float | 已赚净保费 |
| imed_net_premiums_earned_diff_ccy_fye_mid | string | 已赚净保费-货币单位 |
| imed_nonint_inc_to_op_inc_ratio_fye_mid | float | 非利息收入/营业收入 |
| imed_op_lev_fye_mid | float | 经营杠杆 |
| imed_op_margin_ratio_fye_mid | float | 营业利润率 |
| imed_op_ratio_insur_fye_mid | float | 经营比率-保险 |
| imed_pb_fye_mid | float | 市净率 |
| imed_prov_doubtful_to_rec_ratio_fye_mid | float | 坏账准备/应收款项 |
| imed_quick_ratio_fye_mid | float | 速动比率 |
| imed_foreclosed_assets_to_loans_ratio_fye_mid | float | 法拍房地产/总贷款 |
| imed_securities_to_earn_assets_ratio_fye_mid | float | 证券/盈利资产 |
| imed_tax_complement_fye_mid | float | 税务互补率 |
| imed_assets_to_equity_ratio_fye_mid | float | 总资产/总权益 |
| imed_debt_to_equity_ratio_fye_mid | float | 总债务/普通股权益 |
| imed_rec_turnover_fye | float | 应收账款周转率 |
| imed_asset_turnover_fye | float | 总资产周转率 |
| imed_net_trade_cycle_days_fye | float | 平均净营业周期 |
| imed_core_tier1_ratio_fye | float | 核心一级资本充足率 |
| imed_combined_ratio_insur_fye | float | 综合比率-保险 |
| imed_curr_ratio_fye | float | 流动比率 |
| imed_deposits_pct_chg_fye | float | 存款环比变化 |
| imed_gross_div_yield_fye | float | 股息率 |
| imed_retention_ratio_fye | float | 盈利留存率 |
| imed_ebitda_margin_ratio_fye | float | EBITDA利润率 |
| imed_efficiency_ratio_fye | float | 效率比率 |
| imed_expense_ratio_insur_fye | float | 费用率-保险 |
| imed_fee_rev_ratio_fye | float | 手续费收入占比 |
| imed_fa_turnover_fye | float | 固定资产周转率 |
| imed_gross_margin_ratio_fye | float | 毛利率 |
| imed_net_income_margin_excl_exord_fye | float | 普通股净利润率 |
| imed_tax_rate_ratio_fye | float | 所得税率 |
| imed_insur_reserves_pct_chg_fye | float | 保险准备金环比变化 |
| imed_int_coverage_ratio_fye | float | 利息覆盖率 |
| imed_inv_turnover_fye | float | 存货周转率 |
| imed_inv_ratio_fye | float | 投资比率 |
| imed_net_loans_pct_chg_fye | float | 净贷款环比变化 |
| imed_nonperf_loans_to_gross_loans_ratio_fye | float | 不良贷款率 |
| imed_loans_to_deposits_ratio_fye | float | 存贷比 |
| imed_loss_ratio_insur_fye | float | 损失率-保险 |
| imed_lt_debt_to_tot_cap_ratio_fye | float | 长期债务/总资本 |
| imed_cfo_abs_fye | float | 经营现金流净额 |
| imed_cfo_ccy_fye | string | 经营现金流-货币单位 |
| imed_net_debt_to_ebitda_fye | float | 净债务/EBITDA |
| imed_nim_ratio_fye | float | 净息差 |
| imed_net_margin_ratio_fye | float | 净利润率 |
| imed_net_premiums_earned_diff_fye | float | 已赚净保费（环比变化），行业中位数 - 最近财年 |
| imed_net_premiums_earned_diff_ccy_fye | string | 已赚净保费（环比变化）- 货币单位，行业中位数 - 最近财年 |
| imed_nonint_inc_to_op_inc_ratio_fye | float | 非利息收入 / 营业收入，行业中位数 - 最近财年 |
| imed_op_lev_fye | float | 经营杠杆，行业中位数 - 最近财年 |
| imed_op_margin_ratio_fye | float | 营业利润率（%），行业中位数 - 最近财年 |
| imed_op_ratio_insur_fye | float | 经营比率 - 保险（%），行业中位数 - 最近财年 |
| imed_pretax_roa_ratio_fye | float | 税前总资产收益率（%），行业中位数 - 最近财年 |
| imed_pretax_roe_ratio_fye | float | 税前净资产收益率（%），行业中位数 - 最近财年 |
| imed_pb_fye | float | 股价 / 每股净资产，行业中位数 - 最近财年 |
| imed_pe_excl_exord_fye | float | 股价 / 稀释每股收益（不含非常项目），行业中位数 - 最近财年 |
| imed_price_to_fcf_net_div_fye | float | 股价 / 每股自由现金流（扣除股息），行业中位数 - 最近财年 |
| imed_price_to_cfo_per_shr_fye | float | 股价 / 每股经营活动现金流，行业中位数 - 最近财年 |
| imed_price_to_rev_per_shr_fye | float | 股价 / 每股总收入，行业中位数 - 最近财年 |
| imed_prov_doubtful_to_rec_ratio_fye | float | 坏账准备 / 应收款项净额（%），行业中位数 - 最近财年 |
| imed_loan_loss_prov_to_loans_ratio_fye | float | 贷款损失准备 / 净贷款总额（%），行业中位数 - 最近财年 |
| imed_quick_ratio_fye | float | 速动比率，行业中位数 - 最近财年 |
| imed_foreclosed_assets_to_loans_ratio_fye | float | 法拍房地产 / 总贷款总额（%），行业中位数 - 最近财年 |
| imed_reinv_ratio_fye | float | 再投资率（%），行业中位数 - 最近财年 |
| imed_roe_avg_common_fye | float | 平均普通股回报率（%），行业中位数 - 最近财年 |
| imed_roic_ratio_fye | float | 投入资本回报率（%），行业中位数 - 最近财年 |
| imed_sales_per_emp_fye | float | 人均销售额，行业中位数 - 最近财年 |
| imed_sales_per_emp_ccy_fye | string | 人均销售额 - 货币单位，行业中位数 - 最近财年 |
| imed_securities_to_earn_assets_ratio_fye | float | 证券占平均盈利资产比例（%），行业中位数 - 最近财年 |
| imed_tax_complement_fye | float | 税务互补率，行业中位数 - 最近财年 |
| imed_assets_to_equity_ratio_fye | float | 总资产 / 总权益，行业中位数 - 最近财年 |
| imed_debt_to_equity_ratio_fye | float | 总债务 / 普通股权益，行业中位数 - 最近财年 |
| imed_wcap_to_rev_pct_chg_fye | float | 营运资本占总收入百分比（环比变化），行业中位数 - 最近财年 |
| imed_rec_turnover_prev_fye | float | 应收账款周转率，行业中位数 - 上一财年 |
| imed_asset_turnover_prev_fye | float | 总资产周转率，行业中位数 - 上一财年 |
| imed_net_trade_cycle_days_prev_fye | float | 平均净营业周期（天），行业中位数 - 上一财年 |
| imed_core_tier1_ratio_prev_fye | float | 核心一级资本充足率（%），行业中位数 - 上一财年 |
| imed_combined_ratio_insur_prev_fye | float | 综合比率 - 保险（%），行业中位数 - 上一财年 |
| imed_curr_ratio_prev_fye | float | 流动比率，行业中位数 - 上一财年 |
| imed_deposits_pct_chg_prev_fye | float | 存款总额（环比%变化），行业中位数 - 上一财年 |
| imed_gross_div_yield_prev_fye | float | 股息率（普通股-毛率-%），行业中位数 - 上一财年 |
| imed_retention_ratio_prev_fye | float | 盈利留存率，行业中位数 - 上一财年 |
| imed_ebitda_margin_ratio_prev_fye | float | EBITDA 利润率（%），行业中位数 - 上一财年 |
| imed_efficiency_ratio_prev_fye | float | 效率比率（%），行业中位数 - 上一财年 |
| imed_expense_ratio_insur_prev_fye | float | 费用率 - 保险（%），行业中位数 - 上一财年 |
| imed_fee_rev_ratio_prev_fye | float | 手续费收入占比（%），行业中位数 - 上一财年 |
| imed_fa_turnover_prev_fye | float | 固定资产周转率，行业中位数 - 上一财年 |
| imed_gross_margin_ratio_prev_fye | float | 毛利率（%），行业中位数 - 上一财年 |
| imed_net_income_margin_excl_exord_prev_fye | float | 普通股可分配净利润率（不含非常项目，%），行业中位数 - 上一财年 |
| imed_tax_rate_ratio_prev_fye | float | 所得税率（%），行业中位数 - 上一财年 |
| imed_insur_reserves_pct_chg_prev_fye | float | 保险准备金总额（环比%变化），行业中位数 - 上一财年 |
| imed_int_coverage_ratio_prev_fye | float | 利息覆盖率，行业中位数 - 上一财年 |
| imed_inv_turnover_prev_fye | float | 存货周转率，行业中位数 - 上一财年 |
| imed_inv_ratio_prev_fye | float | 投资比率（%），行业中位数 - 上一财年 |
| imed_net_loans_pct_chg_prev_fye | float | 净贷款总额（环比%变化），行业中位数 - 上一财年 |
| imed_nonperf_loans_to_gross_loans_ratio_prev_fye | float | 不良及减值贷款 / 总贷款总额（%），行业中位数 - 上一财年 |
| imed_loans_to_deposits_ratio_prev_fye | float | 存贷比（期末），行业中位数 - 上一财年 |
| imed_loss_ratio_insur_prev_fye | float | 损失率 - 保险（%），行业中位数 - 上一财年 |
| imed_lt_debt_to_tot_cap_ratio_prev_fye | float | 长期债务占总资本比例（%），行业中位数 - 上一财年 |
| imed_cfo_abs_prev_fye | float | 经营活动现金流净额，行业中位数 - 上一财年 |
| imed_cfo_ccy_prev_fye | string | 经营活动现金流净额 - 货币单位，行业中位数 - 上一财年 |
| imed_net_debt_to_ebitda_prev_fye | float | 净债务 / EBITDA，行业中位数 - 上一财年 |
| imed_nim_ratio_prev_fye | float | 净息差（%），行业中位数 - 上一财年 |
| imed_net_margin_ratio_prev_fye | float | 净利润率（%），行业中位数 - 上一财年 |
| imed_net_premiums_earned_diff_prev_fye | float | 已赚净保费（环比变化），行业中位数 - 上一财年 |
| imed_net_premiums_earned_diff_ccy_prev_fye | string | 已赚净保费（环比变化）- 货币单位，行业中位数 - 上一财年 |
| imed_nonint_inc_to_op_inc_ratio_prev_fye | float | 非利息收入 / 营业收入，行业中位数 - 上一财年 |
| imed_op_lev_prev_fye | float | 经营杠杆，行业中位数 - 上一财年 |
| imed_op_margin_ratio_prev_fye | float | 营业利润率（%），行业中位数 - 上一财年 |
| imed_op_ratio_insur_prev_fye | float | 经营比率 - 保险（%），行业中位数 - 上一财年 |
| imed_pretax_roa_ratio_prev_fye | float | 税前总资产收益率（%），行业中位数 - 上一财年 |
| imed_pretax_roe_ratio_prev_fye | float | 税前净资产收益率（%），行业中位数 - 上一财年 |
| imed_pb_prev_fye | float | 股价 / 每股净资产，行业中位数 - 上一财年 |
| imed_pe_excl_exord_prev_fye | float | 股价 / 稀释每股收益（不含非常项目），行业中位数 - 上一财年 |
| imed_price_to_fcf_net_div_prev_fye | float | 股价 / 每股自由现金流（扣除股息），行业中位数 - 上一财年 |
| imed_price_to_cfo_per_shr_prev_fye | float | 股价 / 每股经营活动现金流，行业中位数 - 上一财年 |
| imed_price_to_rev_per_shr_prev_fye | float | 股价 / 每股总收入，行业中位数 - 上一财年 |
| imed_prov_doubtful_to_rec_ratio_prev_fye | float | 坏账准备 / 应收款项净额（%），行业中位数 - 上一财年 |
| imed_loan_loss_prov_to_loans_ratio_prev_fye | float | 贷款损失准备 / 净贷款总额（%），行业中位数 - 上一财年 |
| imed_quick_ratio_prev_fye | float | 速动比率，行业中位数 - 上一财年 |
| imed_foreclosed_assets_to_loans_ratio_prev_fye | float | 法拍房地产 / 总贷款总额（%），行业中位数 - 上一财年 |
| imed_reinv_ratio_prev_fye | float | 再投资率（%），行业中位数 - 上一财年 |
| imed_roe_avg_common_prev_fye | float | 平均普通股回报率（%），行业中位数 - 上一财年 |
| imed_roic_ratio_prev_fye | float | 投入资本回报率（%），行业中位数 - 上一财年 |
| imed_sales_per_emp_prev_fye | float | 人均销售额，行业中位数 - 上一财年 |
| imed_sales_per_emp_ccy_prev_fye | string | 人均销售额 - 货币单位，行业中位数 - 上一财年 |
| imed_securities_to_earn_assets_ratio_prev_fye | float | 证券占平均盈利资产比例（%），行业中位数 - 上一财年 |
| imed_tax_complement_prev_fye | float | 税务互补率，行业中位数 - 上一财年 |
| imed_assets_to_equity_ratio_prev_fye | float | 总资产 / 总权益，行业中位数 - 上一财年 |
| imed_debt_to_equity_ratio_prev_fye | float | 总债务 / 普通股权益，行业中位数 - 上一财年 |
| imed_wcap_to_rev_pct_chg_prev_fye | float | 营运资本占总收入百分比（环比变化），行业中位数 - 上一财年 |
| imed_dps_yield_cur_fye | float | 每股股息率（%），行业中位数 - 当前财年 |
| imed_fwd_ev_to_ebit_cur_fye | float | 前瞻企业价值 / EBIT，行业中位数 - 当前财年 |
| imed_fwd_ev_to_ebitda_cur_fye | float | 前瞻企业价值 / EBITDA，行业中位数 - 当前财年 |
| imed_fwd_ev_to_cfo_cur_fye | float | 前瞻企业价值 / 经营现金流，行业中位数 - 当前财年 |
| imed_fwd_ev_to_sales_cur_fye | float | 前瞻企业价值 / 销售额，行业中位数 - 当前财年 |
| imed_fwd_net_debt_to_ebitda_cur_fye | float | 前瞻净债务 / EBITDA，行业中位数 - 当前财年 |
| imed_fwd_pe_cur_fye | float | 前瞻市盈率（P/E），行业中位数 - 当前财年 |
| imed_fwd_peg_cur_fye | float | 前瞻市盈率相对盈利增长（P/E/G），行业中位数 - 当前财年 |
| imed_fwd_pb_cur_fye | float | 前瞻股价 / 每股净资产，行业中位数 - 当前财年 |
| imed_fwd_pcfo_cur_fye | float | 前瞻股价 / 每股现金流，行业中位数 - 当前财年 |
| imed_fwd_ps_cur_fye | float | 前瞻股价 / 每股销售额，行业中位数 - 当前财年 |
| imed_fwd_total_debt_to_ebitda_cur_fye | float | 前瞻总债务 / EBITDA，行业中位数 - 当前财年 |
| imed_dps_yield_ntm | float | 每股股息率（%），行业中位数 - 未来十二个月 |
| imed_fwd_ev_to_ebit_ntm | float | 前瞻企业价值 / EBIT，行业中位数 - 未来十二个月 |
| imed_fwd_ev_to_ebitda_ntm | float | 前瞻企业价值 / EBITDA，行业中位数 - 未来十二个月 |
| imed_fwd_ev_to_cfo_ntm | float | 前瞻企业价值 / 经营现金流，行业中位数 - 未来十二个月 |
| imed_fwd_ev_to_sales_ntm | float | 前瞻企业价值 / 销售额，行业中位数 - 未来十二个月 |
| imed_fwd_net_debt_to_ebitda_ntm | float | 前瞻净债务 / EBITDA，行业中位数 - 未来十二个月 |
| imed_fwd_pe_ntm | float | 前瞻市盈率（P/E），行业中位数 - 未来十二个月 |
| imed_fwd_peg_ntm | float | 前瞻市盈率相对盈利增长（P/E/G），行业中位数 - 未来十二个月 |
| imed_fwd_pcfo_ntm | float | 前瞻股价 / 每股现金流，行业中位数 - 未来十二个月 |
| imed_fwd_ps_ntm | float | 前瞻股价 / 每股销售额，行业中位数 - 未来十二个月 |
| imed_fwd_total_debt_to_ebitda_ntm | float | 前瞻总债务 / EBITDA，行业中位数 - 未来十二个月 |

示例：获取全部美股公司最新的部分行业中位统计数据

```python
import panda_data
result = panda_data.get_stock_sector_median(
    symbol=[""],
    fields=["imed_net_trade_cycle_days_ttm","imed_pretax_roa_ratio_ttm"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | imed_net_trade_cycle_days_ttm | imed_pretax_roa_ratio_ttm |
|:---|:---|:---|:---|
| A | 20240920 | 138.845993 | None |
| A | 20260429 | None | -18.764229 |
| A | 20260430 | None | -18.784645 |

### get_stock_pv_metric：获取公司最新价量指标数据

数据范围 2019-02-08 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=244)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| pv_beta_5y | float | 5年贝塔值（股价波动相对于市场） |
| pv_return_mtd | float | 本月至今涨跌幅（%） |
| pv_market_cap | float | 市值（数值） |
| pv_market_cap_currency | string | 市值（货币单位） |
| pv_market_cap_date | string | 市值（计算日期） |
| pv_high_52w | float | 52周最高价 |
| pv_high_52w_date | string | 52周最高价发生日期 |
| pv_low_52w | float | 52周最低价 |
| pv_low_52w_date | string | 52周最低价发生日期 |
| pv_rel_return_4w | float | 相对基准4周涨跌幅（%） |
| pv_return_13w | float | 13周涨跌幅（%） |
| pv_rel_return_13w | float | 相对基准13周涨跌幅（%） |
| pv_return_1d | float | 1日涨跌幅（%） |
| pv_return_26w | float | 26周涨跌幅（%） |
| pv_rel_return_26w | float | 相对基准26周涨跌幅（%） |
| pv_return_52w | float | 52周涨跌幅（%） |
| pv_rel_return_52w | float | 相对基准52周涨跌幅（%） |
| pv_return_5d | float | 5日涨跌幅（%） |
| pv_return_ytd | float | 年初至今涨跌幅（%） |
| pv_rel_return_ytd | float | 相对基准年初至今涨跌幅（%） |
| pv_avg_vol_10d | float | 10日平均成交量 |
| pv_avg_monthly_vol_13w | float | 13周平均月成交量 |
| pv_close | float | 最新收盘价 |
| pv_close_date | string | 最新收盘价日期 |
| pv_close_currency | string | 收盘价货币单位 |
| pv_avg_vol_90d | float | 90日平均成交量 |
| pv_avg_val_3m | float | 3个月平均日成交金额 |

示例：获取一定时间内某港股公司股东持股报告

```python
import panda_data
result = panda_data.get_stock_pv_metric(
    symbol=[""],
    fields=["pv_beta_5y","pv_rel_return_26w"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | pv_beta_5y | pv_rel_return_26w |
|:---|:---|:---|
| A | 1.210382 | -32.021662 |
| AA | 1.536871 | 59.407666 |
| AACBR | None | -26.94445 |

### get_us_short_interest：获取美股空头（Short Interest）数据

数据范围 2026-06-15 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=365)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| start_month | string | 是 | 开始月份，格式 YYYYMM，eg:"202608" |
| end_month | string | 是 | 结束月份，格式 YYYYMM，eg:"202608" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 结算日期 |
| symbol | string | 股票代码 |
| si_change_pct | float | 空头变动 |
| si_shares | float | 空头股数（百万股） |
| si_share_pct | float | 空头占股本比 |
| si_float_pct | float | 空头占流通比 |
| si_cover_days | float | 回补天数 |
| si_daily_vol | float | 日均量（百万股） |

示例：示例1

```python
import panda_data
result = panda_data.get_us_short_interest(
    symbol=["AAPL"],
    start_month="202605",
    end_month="202608",
    fields=[""]
)
print(result)
```

返回示例（前 3 行）：

| date | symbol | si_change_pct | si_shares | si_share_pct | si_float_pct | si_cover_days | si_daily_vol |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 20260529 | AAPL | None | 155.88602 | 1.06136 | 1.07907 | 3.38411 | 46.06415 |
| 20260630 | AAPL | -9.853161 | 140.52632 | 0.95678 | 0.97281 | 1.73230 | 81.12131 |
| 20260731 | AAPL | 0.768425 | 141.60616 | 0.97029 | 0.98664 | 2.42472 | 58.40098 |

## 港股一致预期数据

### get_stock_ncycl_consensus：获取非周期性指标一致预期

数据范围 每周最新数据；每日更新 18:00 ~ 19:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=246)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 货币单位 |
| indicator | string | 指标名:LTGROWTH为未来3\~5年长期增长，TP为未来1年目标价 |
| mean | float | 预测均值，另注：对于除symbol，currency，indicator外的参数默认是最新日期的预测，且有历史维度衍生字段，衍生后缀有week，1month~12month对每个字段构成共十三个衍生字段，表示对应字段在一周，一个月~十二个月前的预测值，例如mean_week表示一周前的预测均值，std_6month表示6个月前的预测标准差 |
| median | float | 预测中位数 |
| high | float | 预测最高值 |
| low | float | 预测最低值 |
| std | float | 预测标准差 |
| estimates_num | float | 预测数 |
| included_estimates_num | float | 纳入统计的预测数 |

示例：获取全部港股非周期性指标的部分一致预期

```python
import panda_data
result = panda_data.get_stock_ncycl_consensus(
    symbol=[""],
    fields=["indicator","mean","std_6month","high_week"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | indicator | mean | std_6month | high_week |
|:---|:---|:---|:---|:---|
| 0001.HK | LTGROWTH | 4.6 | None | 4.6 |
| 0001.HK | TP | 76.24286 | 1.75729 | 84.6 |
| 0002.HK | LTGROWTH | 2.7 | 0.0 | 2.7 |

### get_stock_recommendation_consensus：获取买卖建议一致预期

数据范围 每周最新数据；每日更新 18:00 ~ 19:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=247)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 货币单位 |
| mean | float | 预期均值，另注：对于除symbol，currency外的参数默认是最新日期的预测，且有历史维度衍生字段，衍生后缀有week，1month~12month对每个字段构成共十三个衍生字段，表示对应字段在一周，一个月~十二个月前的预测值，例如mean_week表示一周前的预测均值 |
| median | float | 预期中位数 |
| high | float | 预期最高值 |
| low | float | 预期最低值 |
| strong_buy_num | float | 强买建议数 |
| buy_num | float | 买入建议数 |
| hold | float | 持仓建议数 |
| sell_num | float | 卖出建议数 |
| strong_sell_num | float | 强卖建议数 |
| no_opinion_num | float | 无意见数 |
| recommendations_num | float | 推荐总数 |

示例：获取全部港股买卖建议的部分一致预期

```python
import panda_data
result = panda_data.get_stock_recommendation_consensus(
    symbol=[""],
    fields=["strong_buy_num","buy_num_week"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | strong_buy_num | buy_num_week |
|:---|:---|:---|
| 0001.HK | 2.0 | 4.0 |
| 0002.HK | 1.0 | 2.0 |
| 0003.HK | 1.0 | 2.0 |

## 美股一致预期数据

### get_stock_ncycl_estimate：获取非周期性指标一致预期

数据范围 每周最新数据；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=248)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 货币单位 |
| indicator | string | 指标名:LTGROWTH为未来3\~5年长期增长，TP为未来1年目标价 |
| mean | float | 预测均值，另注：对于除symbol，currency，indicator外的参数默认是最新日期的预测，且有历史维度衍生字段，衍生后缀有week，1month~12month对每个字段构成共十三个衍生字段，表示对应字段在一周，一个月~十二个月前的预测值，例如mean_week表示一周前的预测均值，std_6month表示6个月前的预测标准差 |
| median | float | 预测中位数 |
| high | float | 预测最高值 |
| low | float | 预测最低值 |
| std | float | 预测标准差 |
| estimates_num | float | 预测数 |
| included_estimates_num | float | 纳入统计的预测数 |

示例：获取全部美股非周期性指标的部分一致预期

```python
import panda_data
result = panda_data.get_stock_ncycl_estimate(
    symbol=[""],
    fields=["indicator","mean","std_6month","high_week"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | indicator | mean | std_6month | high_week |
|:---|:---|:---|:---|:---|
| A | LTGROWTH | None | 1.26579 | 9.0 |
| A | TP | None | 10.66618 | 185.0 |
| AA | TP | 76.04167 | 3.22052 | 92.0 |

### get_stock_recommendation_estimate：获取买卖建议一致预期

数据范围 每周最新数据；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=249)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 货币单位 |
| mean | float | 预期均值，另注：对于除symbol，currency外的参数默认是最新日期的预测，且有历史维度衍生字段，衍生后缀有week，1month~12month对每个字段构成共十三个衍生字段，表示对应字段在一周，一个月~十二个月前的预测值，例如mean_week表示一周前的预测均值 |
| median | float | 预期中位数 |
| high | float | 预期最高值 |
| low | float | 预期最低值 |
| strong_buy_num | float | 强买建议数 |
| buy_num | float | 买入建议数 |
| hold | float | 持仓建议数 |
| sell_num | float | 卖出建议数 |
| strong_sell_num | float | 强卖建议数 |
| no_opinion_num | float | 无意见数 |
| recommendations_num | float | 推荐总数 |

示例：获取全部美股买卖建议的部分一致预期

```python
import panda_data
result = panda_data.get_stock_recommendation_estimate(
    symbol=[""],
    fields=["strong_buy_num","buy_num_week"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | indicator | mean | std_6month | high_week |
|:---|:---|:---|:---|:---|
| A | LTGROWTH | None | 1.26579 | 9.0 |
| A | TP | None | 10.66618 | 185.0 |
| AA | TP | 76.04167 | 3.22052 | 92.0 |

## 港股财务数据

### get_stock_operating_indicator：获取公司标准化营运指标

数据范围 2007-12-31 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=250)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_year | string | 是 | 开始财年,eg:"2025" |
| end_year | string | 是 | 结束财年,eg:"2025" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| is_final | integer | 是否是最终报告 |
| financial_year | string | 财年 |
| financial_period_end_date | string | 财报截止日期 |
| report_type | string | 报告类型（原始/重述） |
| data_type | string | 数据类型 |
| consol_basis | string | 数据合并基础 |
| report_source | string | 报告来源 |
| item_name | string | 指标名称 |
| is_pershare_item | string | 是否为每股指标 |
| is_percent_item | string | 是否为百分比指标 |
| item_unit | string | 指标单位缩放 |
| item_currency | string | 指标货币单位 |
| item_num | float | 指标值 |

示例：获取一定财年内全部港股公司标准化营运指标

```python
import panda_data
result = panda_data.get_stock_operating_indicator(
    symbol=[""],
    fields=[""],
    start_year="2023",
    end_year="2025",
)
print(result)
```

返回示例（前 3 行）：

| symbol | financial_year | is_final | financial_period_end_date | report_type | data_type | consol_basis | report_source | item_name | is_pershare_item | is_percent_item | item_unit | item_currency | item_num |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 0004.HK | 2023 | 1 | 20231231 | Original To Original | Original | Consolidated Only | HKG ARS | Net Asset Value (NAV) - Total (REIT/Real Estate) | False | False | Units | HKD | 142989.0 |
| 0004.HK | 2023 | 1 | 20231231 | Original To Original | Original | Consolidated Only | HKG ARS | Net Asset Value - Per Share - Basic - Total | True | False | No scaling | HKD | 0.000047 |
| 0004.HK | 2023 | 1 | 20231231 | Recent To Recent | Original | Consolidated Only | HKG ARS | Net Asset Value (NAV) - Total (REIT/Real Estate) | False | False | Units | HKD | 142989.0 |

### get_stock_mktfin_indicator：获取公司最新市场财务统计指标

数据范围 2015-12-31 ~ 至今；每日更新 18:00 ~ 19:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=251)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 数据日期 |
| period_end_date | string | 财报截止日期 |
| curr_ebitda_to_ev_ratio | float | EBITDA占企业价值比重 |
| curr_ebitda_to_ev_ratio_ttm | float | EBITDA占企业价值比重（TTM） |
| curr_ev_to_ebitda | float | 企业价值/EBITDA |
| curr_ev_to_ebitda_ttm | float | 企业价值/EBITDA（TTM） |
| curr_ev_to_fcf | float | 企业价值/自由现金流 |
| curr_ev_to_fcf_ttm | float | 企业价值/自由现金流（TTM） |
| curr_ev_to_fcf | float | 企业价值/自由现金流 |
| curr_ev_to_fcf_ttm | float | 企业价值/自由现金流（TTM） |
| curr_ev_to_ocf | float | 企业价值/经营现金流 |
| curr_ev_to_ocf_ttm | float | 企业价值/经营现金流（TTM） |
| curr_ev_to_rev | float | 企业价值/营业收入 |
| curr_ev_to_rev_ttm | float | 企业价值/营业收入（TTM） |
| curr_fcf_to_ev_ratio | float | 自由现金流占企业价值比重 |
| curr_fcf_to_ev_ratio_ttm | float | 自由现金流占企业价值比重（TTM） |
| curr_rev_to_ev_ratio | float | 营业收入占企业价值比重 |
| curr_rev_to_ev_ratio_ttm | float | 营业收入占企业价值比重（TTM） |
| curr_ev_to_fcf | float | 企业价值/自由现金流 |
| curr_ev_to_fcf_ttm | float | 企业价值/自由现金流（TTM） |
| curr_ev_to_ebit | float | 企业价值/息税前利润 |
| curr_ev_to_ebit_ttm | float | 企业价值/息税前利润（TTM） |
| curr_price_to_fcf_pershr | float | 股价/每股自由现金流 |
| curr_price_to_fcf_pershr_ttm | float | 股价/每股自由现金流（TTM） |
| curr_price_to_fcf_pershr_issue | float | 股价/每股自由现金流（发行特定） |
| curr_price_to_fcf_pershr_issue_ttm | float | 股价/每股自由现金流（发行特定，TTM） |
| curr_fcf_to_ev_ratio | float | 自由现金流占企业价值比重 |
| curr_fcf_to_ev_ratio_ttm | float | 自由现金流占企业价值比重（TTM） |
| curr_div_yld_issue_ratio | float | 股息率-普通股净额（发行特定） |
| curr_div_yld_gross_issue_ratio | float | 股息率-普通股毛额（发行特定） |
| curr_div_yld_issue_ratio_ann | float | 股息率-普通股净额（年化，发行特定） |
| curr_div_yld_gross_issue_ratio_ann | float | 股息率-普通股毛额（年化，发行特定） |
| curr_div_yld_issue_ratio_ttm | float | 股息率-普通股净额（TTM，发行特定） |
| curr_div_yld_gross_issue_ratio_ttm | float | 股息率-普通股毛额（TTM，发行特定） |
| curr_cash_to_mcap_ratio | float | 现金及短期投资占市值比重 |
| curr_price_to_cf_pershr | float | 股价/每股现金流 |
| curr_price_to_cf_pershr_ttm | float | 股价/每股现金流（TTM） |
| curr_price_to_cf_pershr_ann | float | 股价/每股现金流（年化） |
| curr_price_to_cf_pershr_issue | float | 股价/每股现金流（发行特定） |
| curr_price_to_cf_pershr_issue_ttm | float | 股价/每股现金流（发行特定，TTM） |
| curr_price_to_fcf_pershr_issue | float | 股价/每股自由现金流（发行特定） |
| curr_price_to_fcf_pershr_issue_ttm | float | 股价/每股自由现金流（发行特定，TTM） |
| curr_price_to_ocf_pershr | float | 股价/每股经营现金流 |
| curr_price_to_ocf_pershr_ttm | float | 股价/每股经营现金流（TTM） |
| curr_price_to_ocf_pershr_issue | float | 股价/每股经营现金流（发行特定） |
| curr_price_to_ocf_pershr_issue_ttm | float | 股价/每股经营现金流（发行特定，TTM） |
| curr_price_to_rev_pershr | float | 股价/每股营业收入 |
| curr_price_to_rev_pershr_ann | float | 股价/每股营业收入（年化） |
| curr_price_to_rev_pershr_ttm | float | 股价/每股营业收入（TTM） |
| curr_price_to_rev_pershr_issue | float | 股价/每股营业收入（发行特定） |
| curr_price_to_rev_pershr_issue_ttm | float | 股价/每股营业收入（发行特定，TTM） |
| curr_price_to_fcf_pershr_issue | float | 股价/每股自由现金流（发行特定） |
| curr_price_to_fcf_pershr_issue_ttm | float | 股价/每股自由现金流（发行特定，TTM） |
| curr_price_to_dps_issue | float | 股价/每股股息-普通股净额（发行特定） |
| curr_price_to_dps_gross_issue | float | 股价/每股股息-普通股毛额（发行特定） |
| curr_price_to_dps_issue_ttm | float | 股价/每股股息-普通股净额（TTM，发行特定） |
| curr_price_to_dps_gross_issue_ttm | float | 股价/每股股息-普通股毛额（TTM，发行特定） |
| curr_pe_dil_excl_issue | float | 市盈率-稀释扣非（发行特定） |
| curr_pe_dil_excl_issue_ttm | float | 市盈率-稀释扣非（TTM，发行特定） |
| curr_pe_dil_excl | float | 市盈率-稀释扣非 |
| curr_pe_dil_excl_ttm | float | 市盈率-稀释扣非（TTM） |
| curr_pe_dil_norm_issue | float | 市盈率-稀释扣非标准化（发行特定） |
| curr_pe_dil_norm_issue_ttm | float | 市盈率-稀释扣非标准化（TTM，发行特定） |
| curr_pe_dil_norm | float | 市盈率-稀释扣非标准化 |
| curr_pe_dil_norm_ttm | float | 市盈率-稀释扣非标准化（TTM） |
| curr_pe_dil_incl_issue | float | 市盈率-稀释含非常项目（发行特定） |
| curr_pe_dil_incl_issue_ttm | float | 市盈率-稀释含非常项目（TTM，发行特定） |
| curr_pe_dil_incl | float | 市盈率-稀释含非常项目 |
| curr_pe_dil_incl_ttm | float | 市盈率-稀释含非常项目（TTM） |
| curr_price_to_ebitda_pershr_issue | float | 股价/每股EBITDA（发行特定） |
| curr_price_to_ebitda_pershr_issue_ttm | float | 股价/每股EBITDA（TTM，发行特定） |
| curr_price_to_ebitda_pershr | float | 股价/每股EBITDA |
| curr_price_to_ebitda_pershr_ttm | float | 股价/每股EBITDA（TTM） |
| curr_pe_basic_excl_issue | float | 市盈率-基本扣非（发行特定） |
| curr_pe_basic_excl_issue_ttm | float | 市盈率-基本扣非（TTM，发行特定） |
| curr_pe_basic_excl | float | 市盈率-基本扣非 |
| curr_pe_basic_excl_ttm | float | 市盈率-基本扣非（TTM） |
| curr_pe_basic_incl_issue | float | 市盈率-基本含非常项目（发行特定） |
| curr_pe_basic_incl_issue_ttm | float | 市盈率-基本含非常项目（TTM，发行特定） |
| curr_pe_basic_incl | float | 市盈率-基本含非常项目 |
| curr_pe_basic_incl_ttm | float | 市盈率-基本含非常项目（TTM） |
| curr_earn_yld_basic_excl_issue_ratio | float | 每股基本收益（扣非）占股价比重（发行特定） |
| curr_earn_yld_basic_excl_issue_ratio_ttm | float | 每股基本收益（扣非）占股价比重（TTM，发行特定） |
| curr_earn_yld_basic_excl_ratio | float | 每股基本收益（扣非）占股价比重 |
| curr_earn_yld_basic_excl_ratio_ttm | float | 每股基本收益（扣非）占股价比重（TTM） |
| curr_earn_yld_basic_incl_issue_ratio | float | 每股基本收益（含非常）占股价比重（发行特定） |
| curr_earn_yld_basic_incl_issue_ratio_ttm | float | 每股基本收益（含非常）占股价比重（TTM，发行特定） |
| curr_earn_yld_basic_incl_ratio | float | 每股基本收益（含非常）占股价比重 |
| curr_earn_yld_basic_incl_ratio_ttm | float | 每股基本收益（含非常）占股价比重（TTM） |
| curr_earn_yld_dil_excl_issue_ratio | float | 每股稀释收益（扣非）占股价比重（发行特定） |
| curr_earn_yld_dil_excl_issue_ratio_ttm | float | 每股稀释收益（扣非）占股价比重（TTM，发行特定） |
| curr_earn_yld_dil_excl_ratio | float | 每股稀释收益（扣非）占股价比重 |
| curr_earn_yld_dil_excl_ratio_ttm | float | 每股稀释收益（扣非）占股价比重（TTM） |
| curr_earn_yld_dil_incl_issue_ratio | float | 每股稀释收益（含非常）占股价比重（发行特定） |
| curr_earn_yld_dil_incl_issue_ratio_ttm | float | 每股稀释收益（含非常）占股价比重（TTM，发行特定） |
| curr_earn_yld_dil_incl_ratio | float | 每股稀释收益（含非常）占股价比重 |
| curr_earn_yld_dil_incl_ratio_ttm | float | 每股稀释收益（含非常）占股价比重（TTM） |
| curr_rel_pe_dil_excl_issue_ratio | float | 相对市盈率分位数（发行特定） |
| curr_rel_pe_dil_excl_ratio | float | 相对市盈率分位数 |
| curr_peg | float | 市盈率相对盈利增长比率 |
| curr_peg_issue | float | 市盈率相对盈利增长比率（发行特定） |
| curr_peg_ttm | float | 市盈率相对盈利增长比率（TTM） |
| curr_peg_issue_ttm | float | 市盈率相对盈利增长比率（TTM，发行特定） |
| curr_pegy_issue | float | 市盈率相对盈利增长及股息比率（发行特定） |
| curr_pegy_issue_ttm | float | 市盈率相对盈利增长及股息比率（TTM，发行特定） |
| curr_pe_dil_excl_ttm_incl_neg | float | 市盈率-稀释扣非（TTM，含负值） |
| curr_pe_dil_excl_issue_ttm_incl_neg | float | 市盈率-稀释扣非（TTM，发行特定，含负值） |
| curr_sales_per_emp_ann | float | 人均销售额（年化） |
| curr_sales_per_emp_currency_ann | string | 人均销售额-货币单位（年化） |
| curr_sales_per_emp_ttm | float | 人均销售额（TTM） |
| curr_sales_per_emp_currency_ttm | string | 人均销售额-货币单位（TTM） |
| curr_net_inc_per_emp_ann | float | 人均税后净利润（年化） |
| curr_net_inc_per_emp_currency_ann | string | 人均税后净利润-货币单位（年化） |
| curr_net_inc_per_emp_ttm | float | 人均税后净利润（TTM） |
| curr_net_inc_per_emp_currency_ttm | string | 人均税后净利润-货币单位（TTM） |
| curr_ev | float | 企业价值 |
| curr_ev_currency | string | 企业价值-货币单位 |
| curr_pb | float | 市净率 |
| curr_pb_issue | float | 市净率（发行特定） |
| curr_ptb | float | 市净率-有形 |
| curr_ptb_issue | float | 市净率-有形（发行特定） |
| curr_ev_excl_lt_inv | float | 企业价值（扣除长期投资） |
| curr_ev_excl_lt_inv_currency | string | 企业价值-货币单位（扣除长期投资） |
| curr_cash_to_mcap_ratio_lfy | float | 现金及短期投资占市值比重（上一财年） |
| curr_pb_lfy | float | 市净率（上一财年） |
| curr_pb_issue_lfy | float | 市净率（上一财年，发行特定） |
| curr_ptb_lfy | float | 市净率-有形（上一财年） |
| curr_ptb_issue_lfy | float | 市净率-有形（上一财年，发行特定） |
| curr_ev_out | float | 企业价值（基于流通股本） |
| curr_ev_out_currency | string | 企业价值-货币单位（基于流通股本） |
| curr_net_debt_to_ev_ratio | float | 净债务占企业价值比重 |
| curr_price_to_fcf_pershr | float | 股价/每股自由现金流 |
| curr_price_to_fcf_pershr_ttm | float | 股价/每股自由现金流（TTM） |
| curr_price_to_fcf_pershr | float | 股价/每股自由现金流 |
| curr_price_to_fcf_pershr_ttm | float | 股价/每股自由现金流（TTM） |
| curr_high_to_pe_dil_excl_ttm | float | 52周最高价/每股收益（TTM） |
| curr_high_to_pe_dil_excl_issue_ttm | float | 52周最高价/每股收益（TTM，发行特定） |
| curr_low_to_pe_dil_excl_ttm | float | 52周最低价/每股收益（TTM） |
| curr_low_to_pe_dil_excl_issue_ttm | float | 52周最低价/每股收益（TTM，发行特定） |
| curr_earn_yld_dil_excl_issue_to_high_ratio_ttm | float | 每股收益占52周最高价比重（发行特定，TTM） |
| curr_earn_yld_dil_excl_to_high_ratio_ttm | float | 每股收益占52周最高价比重（TTM） |
| curr_earn_yld_dil_excl_issue_to_low_ratio_ttm | float | 每股收益占52周最低价比重（发行特定，TTM） |
| curr_earn_yld_dil_excl_to_low_ratio_ttm | float | 每股收益占52周最低价比重（TTM） |
| curr_high_to_pb | float | 52周最高价/每股账面价值 |
| curr_high_to_pb_issue | float | 52周最高价/每股账面价值（发行特定） |
| curr_low_to_pb | float | 52周最低价/每股账面价值 |
| curr_low_to_pb_issue | float | 52周最低价/每股账面价值（发行特定） |

示例：获取全部港股公司最新的部分市场财务统计指标

```python
import panda_data
result = panda_data.get_stock_mktfin_indicator(
    symbol=[""] ,
    fields=["curr_price_to_dps_issue_ttm", "curr_ev_to_rev"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | curr_price_to_dps_issue_ttm | curr_ev_to_rev |
|:---|:---|:---|:---|
| 0001.HK | 20251231 | None | None |
| 0001.HK | 20260428 | None | 2.017103 |
| 0001.HK | 20260429 | None | 2.032147 |

### get_fina_statement：获取财务季度报告

数据范围 2008-09-25 ~ 至今；每日更新 18:00 ~ 19:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=252)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, list]] | 否 | 股票名称 |
| start_quarter | string | 是 | 起始季度，格式为 "YYYYqN"（start_quarter与end_quarter间隔不能超5年） |
| end_quarter | string | 是 | 结束季度，格式为 "YYYYqN"（start_quarter与end_quarter间隔不能超5年） |
| date | Optional[string] | 否 | 公告日期,返回该日期及之前的数据 |
| is_latest | Optional[bool] | 否 | True：返回最新披露数据，False：返回全部。默认为True |
| fields | Optional[Union[string, list]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| fields | float | 需要返回的财务字段(见下载文件) |
| fy_period | string | 财务年时间段 |

示例：获取一定季度内某只股票的最新财务季度报告且使用fields

```python
import panda_data
result = panda_data.get_fina_statement(
        symbol="0700.HK",
        start_quarter="2022q1",
        end_quarter="2026q4",
        date="20241014",
        is_latest=True,
        fields=["symbol", "bs_asset_accruals"],
        )
print(result)
```

返回示例（前 3 行）：

| symbol | fy_period | date | bs_asset_accruals |
|:---|:---|:---|:---|
| 0700.HK | FY2024Q2 | 20240827 | 1.497963e+12 |

## 美股财务数据

### get_stock_operating_metric：获取公司标准化营运指标

数据范围 2004-12-31 ~ 至今；每日更新 每周六11:00 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=253)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_year | string | 是 | 开始财年,eg:"2025" |
| end_year | string | 是 | 结束财年,eg:"2025" |
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| is_final | integer | 是否是最终报告 |
| financial_year | string | 财年 |
| financial_period_end_date | string | 财报截止日期 |
| report_type | string | 报告类型（原始/重述） |
| data_type | string | 数据类型 |
| consol_basis | string | 数据合并基础 |
| report_source | string | 报告来源 |
| item_name | string | 指标名称 |
| is_pershare_item | string | 是否为每股指标 |
| is_percent_item | string | 是否为百分比指标 |
| item_unit | string | 指标单位缩放 |
| item_currency | string | 指标货币单位 |
| item_num | float | 指标值 |

示例：获取一定财年内全部美股公司标准化营运指标

```python
import panda_data
result = panda_data.get_stock_operating_metric(
    symbol=[""],
    fields=[""],
    start_year="2023",
    end_year="2025",
)
print(result)
```

返回示例（前 3 行）：

| symbol | financial_year | is_final | financial_period_end_date | report_type | data_type | consol_basis | report_source | item_name | is_pershare_item | is_percent_item | item_unit | item_currency | item_num |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| AAL | 2023 | 1 | 20231231 | Original To Original | Original | Consolidated Only | 10-K | Seat Miles/Kilometers - Available (ASM/ASK) - ... | False | False | Units | None | 446951.843712 |
| AAL | 2023 | 1 | 20231231 | Original To Original | Original | Consolidated Only | 10-K | Operating Revenue - Airlines Operating Metrics... | False | False | Units | USD | 52788.0 |
| AAL | 2023 | 1 | 20231231 | Original To Original | Original | Consolidated Only | 10-K | Passenger Revenue - Total | False | False | Units | USD | 48512.0 |

### get_stock_mktfin_metric：获取公司最新市场财务统计指标

数据范围 2004-12-31 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=254)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| date | string | 数据日期 |
| period_end_date | string | 财报截止日期 |
| curr_ebitda_to_ev_ratio | float | EBITDA占企业价值比重 |
| curr_ebitda_to_ev_ratio_ttm | float | EBITDA占企业价值比重（TTM） |
| curr_ev_to_ebitda | float | 企业价值/EBITDA |
| curr_ev_to_ebitda_ttm | float | 企业价值/EBITDA（TTM） |
| curr_ev_to_fcf | float | 企业价值/自由现金流 |
| curr_ev_to_fcf_ttm | float | 企业价值/自由现金流（TTM） |
| curr_ev_to_fcf | float | 企业价值/自由现金流 |
| curr_ev_to_fcf_ttm | float | 企业价值/自由现金流（TTM） |
| curr_ev_to_ocf | float | 企业价值/经营现金流 |
| curr_ev_to_ocf_ttm | float | 企业价值/经营现金流（TTM） |
| curr_ev_to_rev | float | 企业价值/营业收入 |
| curr_ev_to_rev_ttm | float | 企业价值/营业收入（TTM） |
| curr_fcf_to_ev_ratio | float | 自由现金流占企业价值比重 |
| curr_fcf_to_ev_ratio_ttm | float | 自由现金流占企业价值比重（TTM） |
| curr_rev_to_ev_ratio | float | 营业收入占企业价值比重 |
| curr_rev_to_ev_ratio_ttm | float | 营业收入占企业价值比重（TTM） |
| curr_ev_to_fcf | float | 企业价值/自由现金流 |
| curr_ev_to_fcf_ttm | float | 企业价值/自由现金流（TTM） |
| curr_ev_to_ebit | float | 企业价值/息税前利润 |
| curr_ev_to_ebit_ttm | float | 企业价值/息税前利润（TTM） |
| curr_price_to_fcf_pershr | float | 股价/每股自由现金流 |
| curr_price_to_fcf_pershr_ttm | float | 股价/每股自由现金流（TTM） |
| curr_price_to_fcf_pershr_issue | float | 股价/每股自由现金流（发行特定） |
| curr_price_to_fcf_pershr_issue_ttm | float | 股价/每股自由现金流（发行特定，TTM） |
| curr_fcf_to_ev_ratio | float | 自由现金流占企业价值比重 |
| curr_fcf_to_ev_ratio_ttm | float | 自由现金流占企业价值比重（TTM） |
| curr_div_yld_issue_ratio | float | 股息率-普通股净额（发行特定） |
| curr_div_yld_gross_issue_ratio | float | 股息率-普通股毛额（发行特定） |
| curr_div_yld_issue_ratio_ann | float | 股息率-普通股净额（年化，发行特定） |
| curr_div_yld_gross_issue_ratio_ann | float | 股息率-普通股毛额（年化，发行特定） |
| curr_div_yld_issue_ratio_ttm | float | 股息率-普通股净额（TTM，发行特定） |
| curr_div_yld_gross_issue_ratio_ttm | float | 股息率-普通股毛额（TTM，发行特定） |
| curr_cash_to_mcap_ratio | float | 现金及短期投资占市值比重 |
| curr_price_to_cf_pershr | float | 股价/每股现金流 |
| curr_price_to_cf_pershr_ttm | float | 股价/每股现金流（TTM） |
| curr_price_to_cf_pershr_ann | float | 股价/每股现金流（年化） |
| curr_price_to_cf_pershr_issue | float | 股价/每股现金流（发行特定） |
| curr_price_to_cf_pershr_issue_ttm | float | 股价/每股现金流（发行特定，TTM） |
| curr_price_to_fcf_pershr_issue | float | 股价/每股自由现金流（发行特定） |
| curr_price_to_fcf_pershr_issue_ttm | float | 股价/每股自由现金流（发行特定，TTM） |
| curr_price_to_ocf_pershr | float | 股价/每股经营现金流 |
| curr_price_to_ocf_pershr_ttm | float | 股价/每股经营现金流（TTM） |
| curr_price_to_ocf_pershr_issue | float | 股价/每股经营现金流（发行特定） |
| curr_price_to_ocf_pershr_issue_ttm | float | 股价/每股经营现金流（发行特定，TTM） |
| curr_price_to_rev_pershr | float | 股价/每股营业收入 |
| curr_price_to_rev_pershr_ann | float | 股价/每股营业收入（年化） |
| curr_price_to_rev_pershr_ttm | float | 股价/每股营业收入（TTM） |
| curr_price_to_rev_pershr_issue | float | 股价/每股营业收入（发行特定） |
| curr_price_to_rev_pershr_issue_ttm | float | 股价/每股营业收入（发行特定，TTM） |
| curr_price_to_fcf_pershr_issue | float | 股价/每股自由现金流（发行特定） |
| curr_price_to_fcf_pershr_issue_ttm | float | 股价/每股自由现金流（发行特定，TTM） |
| curr_price_to_dps_issue | float | 股价/每股股息-普通股净额（发行特定） |
| curr_price_to_dps_gross_issue | float | 股价/每股股息-普通股毛额（发行特定） |
| curr_price_to_dps_issue_ttm | float | 股价/每股股息-普通股净额（TTM，发行特定） |
| curr_price_to_dps_gross_issue_ttm | float | 股价/每股股息-普通股毛额（TTM，发行特定） |
| curr_pe_dil_excl_issue | float | 市盈率-稀释扣非（发行特定） |
| curr_pe_dil_excl_issue_ttm | float | 市盈率-稀释扣非（TTM，发行特定） |
| curr_pe_dil_excl | float | 市盈率-稀释扣非 |
| curr_pe_dil_excl_ttm | float | 市盈率-稀释扣非（TTM） |
| curr_pe_dil_norm_issue | float | 市盈率-稀释扣非标准化（发行特定） |
| curr_pe_dil_norm_issue_ttm | float | 市盈率-稀释扣非标准化（TTM，发行特定） |
| curr_pe_dil_norm | float | 市盈率-稀释扣非标准化 |
| curr_pe_dil_norm_ttm | float | 市盈率-稀释扣非标准化（TTM） |
| curr_pe_dil_incl_issue | float | 市盈率-稀释含非常项目（发行特定） |
| curr_pe_dil_incl_issue_ttm | float | 市盈率-稀释含非常项目（TTM，发行特定） |
| curr_pe_dil_incl | float | 市盈率-稀释含非常项目 |
| curr_pe_dil_incl_ttm | float | 市盈率-稀释含非常项目（TTM） |
| curr_price_to_ebitda_pershr_issue | float | 股价/每股EBITDA（发行特定） |
| curr_price_to_ebitda_pershr_issue_ttm | float | 股价/每股EBITDA（TTM，发行特定） |
| curr_price_to_ebitda_pershr | float | 股价/每股EBITDA |
| curr_price_to_ebitda_pershr_ttm | float | 股价/每股EBITDA（TTM） |
| curr_pe_basic_excl_issue | float | 市盈率-基本扣非（发行特定） |
| curr_pe_basic_excl_issue_ttm | float | 市盈率-基本扣非（TTM，发行特定） |
| curr_pe_basic_excl | float | 市盈率-基本扣非 |
| curr_pe_basic_excl_ttm | float | 市盈率-基本扣非（TTM） |
| curr_pe_basic_incl_issue | float | 市盈率-基本含非常项目（发行特定） |
| curr_pe_basic_incl_issue_ttm | float | 市盈率-基本含非常项目（TTM，发行特定） |
| curr_pe_basic_incl | float | 市盈率-基本含非常项目 |
| curr_pe_basic_incl_ttm | float | 市盈率-基本含非常项目（TTM） |
| curr_earn_yld_basic_excl_issue_ratio | float | 每股基本收益（扣非）占股价比重（发行特定） |
| curr_earn_yld_basic_excl_issue_ratio_ttm | float | 每股基本收益（扣非）占股价比重（TTM，发行特定） |
| curr_earn_yld_basic_excl_ratio | float | 每股基本收益（扣非）占股价比重 |
| curr_earn_yld_basic_excl_ratio_ttm | float | 每股基本收益（扣非）占股价比重（TTM） |
| curr_earn_yld_basic_incl_issue_ratio | float | 每股基本收益（含非常）占股价比重（发行特定） |
| curr_earn_yld_basic_incl_issue_ratio_ttm | float | 每股基本收益（含非常）占股价比重（TTM，发行特定） |
| curr_earn_yld_basic_incl_ratio | float | 每股基本收益（含非常）占股价比重 |
| curr_earn_yld_basic_incl_ratio_ttm | float | 每股基本收益（含非常）占股价比重（TTM） |
| curr_earn_yld_dil_excl_issue_ratio | float | 每股稀释收益（扣非）占股价比重（发行特定） |
| curr_earn_yld_dil_excl_issue_ratio_ttm | float | 每股稀释收益（扣非）占股价比重（TTM，发行特定） |
| curr_earn_yld_dil_excl_ratio | float | 每股稀释收益（扣非）占股价比重 |
| curr_earn_yld_dil_excl_ratio_ttm | float | 每股稀释收益（扣非）占股价比重（TTM） |
| curr_earn_yld_dil_incl_issue_ratio | float | 每股稀释收益（含非常）占股价比重（发行特定） |
| curr_earn_yld_dil_incl_issue_ratio_ttm | float | 每股稀释收益（含非常）占股价比重（TTM，发行特定） |
| curr_earn_yld_dil_incl_ratio | float | 每股稀释收益（含非常）占股价比重 |
| curr_earn_yld_dil_incl_ratio_ttm | float | 每股稀释收益（含非常）占股价比重（TTM） |
| curr_rel_pe_dil_excl_issue_ratio | float | 相对市盈率分位数（发行特定） |
| curr_rel_pe_dil_excl_ratio | float | 相对市盈率分位数 |
| curr_peg | float | 市盈率相对盈利增长比率 |
| curr_peg_issue | float | 市盈率相对盈利增长比率（发行特定） |
| curr_peg_ttm | float | 市盈率相对盈利增长比率（TTM） |
| curr_peg_issue_ttm | float | 市盈率相对盈利增长比率（TTM，发行特定） |
| curr_pegy_issue | float | 市盈率相对盈利增长及股息比率（发行特定） |
| curr_pegy_issue_ttm | float | 市盈率相对盈利增长及股息比率（TTM，发行特定） |
| curr_pe_dil_excl_ttm_incl_neg | float | 市盈率-稀释扣非（TTM，含负值） |
| curr_pe_dil_excl_issue_ttm_incl_neg | float | 市盈率-稀释扣非（TTM，发行特定，含负值） |
| curr_sales_per_emp_ann | float | 人均销售额（年化） |
| curr_sales_per_emp_currency_ann | string | 人均销售额-货币单位（年化） |
| curr_sales_per_emp_ttm | float | 人均销售额（TTM） |
| curr_sales_per_emp_currency_ttm | string | 人均销售额-货币单位（TTM） |
| curr_net_inc_per_emp_ann | float | 人均税后净利润（年化） |
| curr_net_inc_per_emp_currency_ann | string | 人均税后净利润-货币单位（年化） |
| curr_net_inc_per_emp_ttm | float | 人均税后净利润（TTM） |
| curr_net_inc_per_emp_currency_ttm | string | 人均税后净利润-货币单位（TTM） |
| curr_ev | float | 企业价值 |
| curr_ev_currency | string | 企业价值-货币单位 |
| curr_pb | float | 市净率 |
| curr_pb_issue | float | 市净率（发行特定） |
| curr_ptb | float | 市净率-有形 |
| curr_ptb_issue | float | 市净率-有形（发行特定） |
| curr_ev_excl_lt_inv | float | 企业价值（扣除长期投资） |
| curr_ev_excl_lt_inv_currency | string | 企业价值-货币单位（扣除长期投资） |
| curr_cash_to_mcap_ratio_lfy | float | 现金及短期投资占市值比重（上一财年） |
| curr_pb_lfy | float | 市净率（上一财年） |
| curr_pb_issue_lfy | float | 市净率（上一财年，发行特定） |
| curr_ptb_lfy | float | 市净率-有形（上一财年） |
| curr_ptb_issue_lfy | float | 市净率-有形（上一财年，发行特定） |
| curr_ev_out | float | 企业价值（基于流通股本） |
| curr_ev_out_currency | string | 企业价值-货币单位（基于流通股本） |
| curr_net_debt_to_ev_ratio | float | 净债务占企业价值比重 |
| curr_price_to_fcf_pershr | float | 股价/每股自由现金流 |
| curr_price_to_fcf_pershr_ttm | float | 股价/每股自由现金流（TTM） |
| curr_price_to_fcf_pershr | float | 股价/每股自由现金流 |
| curr_price_to_fcf_pershr_ttm | float | 股价/每股自由现金流（TTM） |
| curr_high_to_pe_dil_excl_ttm | float | 52周最高价/每股收益（TTM） |
| curr_high_to_pe_dil_excl_issue_ttm | float | 52周最高价/每股收益（TTM，发行特定） |
| curr_low_to_pe_dil_excl_ttm | float | 52周最低价/每股收益（TTM） |
| curr_low_to_pe_dil_excl_issue_ttm | float | 52周最低价/每股收益（TTM，发行特定） |
| curr_earn_yld_dil_excl_issue_to_high_ratio_ttm | float | 每股收益占52周最高价比重（发行特定，TTM） |
| curr_earn_yld_dil_excl_to_high_ratio_ttm | float | 每股收益占52周最高价比重（TTM） |
| curr_earn_yld_dil_excl_issue_to_low_ratio_ttm | float | 每股收益占52周最低价比重（发行特定，TTM） |
| curr_earn_yld_dil_excl_to_low_ratio_ttm | float | 每股收益占52周最低价比重（TTM） |
| curr_high_to_pb | float | 52周最高价/每股账面价值 |
| curr_high_to_pb_issue | float | 52周最高价/每股账面价值（发行特定） |
| curr_low_to_pb | float | 52周最低价/每股账面价值 |
| curr_low_to_pb_issue | float | 52周最低价/每股账面价值（发行特定） |

示例：获取全部美股公司最新的部分市场财务统计指标

```python
import panda_data
result = panda_data.get_stock_mktfin_metric(
    symbol=[""],
    fields=["curr_price_to_dps_issue_ttm", "curr_ev_to_rev"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | curr_price_to_dps_issue_ttm | curr_ev_to_rev |
|:---|:---|:---|:---|
| A | 20260131 | None | None |
| A | 20260428 | None | 4.901918 |
| A | 20260429 | None | 4.756712 |

### get_fina_ex：获取财务季度报告

数据范围 2017-11-16 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=255)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, list]] | 否 | 股票名称 |
| start_quarter | string | 是 | 起始季度，格式为 "YYYYqN"（start_quarter与end_quarter间隔不能超5年） |
| end_quarter | string | 是 | 结束季度，格式为 "YYYYqN"（start_quarter与end_quarter间隔不能超5年） |
| date | Optional[string] | 否 | 公告日期,返回该日期及之前的数据 |
| is_latest | Optional[bool] | 否 | True：返回最新披露数据，False：返回全部。默认为True |
| fields | Optional[Union[string, list]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| fields | float | 需要返回的财务字段(见下载文件) |
| fy_period | string | 财务年时间段 |

示例：获取一定季度内某只股票的最新财务季度报告且使用fields

```python
import panda_data
result = panda_data.get_fina_ex(
        symbol="AAPL",
        start_quarter="2022q1",
        end_quarter="2026q4",
        date="20241014",
        is_latest=True,
        fields=["symbol","bs_asset_accruals"],
        )
print(result)
```

返回示例（前 3 行）：

| symbol | fy_period | date | bs_asset_accruals |
|:---|:---|:---|:---|
| AAPL | FY2024Q3 | 20240802 | 3.060470e+11 |

## 港股ETF数据

### get_hk_etf_detail：获取港股ETF基本信息(每日快照)

数据范围 2000-01-01 ~ 至今；每日更新 19:00～20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=435)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| date | str | 否 | 快照交易日，格式 "YYYYMMDD" 或 "YYYY-MM-DD"，返回该交易日全部 symbol 快照 |
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 快照交易日 |
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| status | int | 股票状态 |
| isin_code | string | 国际证券识别编码 |
| trading_code | string | 交易代码 |
| rcs_asset_category_name | string | 资产类别名称 |
| asset_state | string | 资产状态 |
| incorp_date | string | 公司成立日期 |
| office_country | string | 总部所在国家 |
| office_region | string | 总部所在地区 |
| website | string | 公司网站 |

示例：示例1

```python
import panda_data
result = panda_data.get_hk_etf_detail(
        date="20260902",
        fields=["symbol","name","status","trading_code"],
    )
print(result)
```

返回示例（前 3 行）：

| symbol | name | status | trading_code |
|:---|:---|:---|:---|
| 2800.HK | TRACKER FUND OF HK LTD | 1 | 2800 |

### get_hk_etf_detail_all：获取港股ETF基本信息

每日更新 19:00～20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=436)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，如 "02800.HK"，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |
| status | Optional[int] | 否 | 是否在市，1 - 在市，0 - 退市，-1 - 未知 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| status | int | 股票状态 |
| isin_code | string | 国际证券识别编码 |
| trading_code | string | 交易代码 |
| rcs_asset_category_name | string | 资产类别名称 |
| incorp_date | string | 公司成立日期 |
| office_country | string | 总部所在国家 |
| office_region | string | 总部所在地区 |
| website | string | 公司网站 |

示例：示例1

```python
import panda_data
result = panda_data.get_hk_etf_detail_all(
        symbol=["2800.HK", "2801.HK"],
        fields=["incorp_date","trading_code","status"],
        status=None,
    )
print(result)
```

返回示例（前 3 行）：

| incorp_date | status | symbol | trading_code |
|:---|:---|:---|:---|
| 1999-09-03 | 1 | 2800.HK | 2800 |
| None | 1 | 2801.HK | 2801 |

### get_hk_etf_daily：获取港股ETF日线

数据范围 2000-01-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=437)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD"，与开始日期间不超过5年 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 交易日 |
| symbol | string | 股票代码 |
| open | string | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| pre_close | float | 昨收价 |
| name | string | 股票名称 |
| trade_status | float | 交易状态代码 |
| alt_close | float | 调整收盘价（剔除派息、送股、拆合股等公司行为影响） |
| amount | float | 成交额 |
| bid | float | 买盘价（收盘前最后一笔） |
| ask | float | 卖盘价（收盘前最后一笔） |
| vwap | float | 成交量加权平均价 |
| vwap_vol | float | 计算VWAP的成交量 |
| opn_aucvol | float | 开市竞价时段成交量 |
| opn_auc | float | 开市竞价时段价格 |
| lmt_refpr2 | float | 限价参考价 |
| lolimit | float | 价格下限（是盘中触发"冷静期"时的临时限价 "±10%～20%"） |
| uplimit | float | 价格上限（是盘中触发"冷静期"时的临时限价 "±10%～20%"） |
| lolimit_2 | float | 二级价格下限（是开盘前和收盘竞价时的限价 "开市±15%、收市±5%"） |
| uplimit_2 | float | 二级价格上限（是开盘前和收盘竞价时的限价 "开市±15%、收市±5%"） |
| num_moves | float | 成交笔数 |
| uplimit_3 | float | 三级价格上限（仅开盘竞价时段专用的独立限价，方便与收盘竞价区分） |
| lolimit_3 | float | 三级价格下限（仅开盘竞价时段专用的独立限价，方便与收盘竞价区分） |
| cls_aucvol | float | 收市竞价时段成交量 |

示例：示例1

```python
import panda_data
result = panda_data.get_hk_etf_daily(
        symbol=["2800.HK"],
        start_date="20260301",
        end_date="20260601",
        fields=["open",'high','low','close','pre_close'],
    )
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | high | low | close | pre_close |
|:---|:---|:---|:---|:---|:---|:---|
| 2800.HK | 20260601 | 25.40 | 25.76 | 25.40 | 25.68 | 25.40 |
| 2800.HK | 20260529 | 25.40 | 25.58 | 25.30 | 25.40 | 25.26 |
| 2800.HK | 20260528 | 25.46 | 25.48 | 24.98 | 25.26 | 25.56 |

### get_hk_etf_dividend_event：获取港股ETF分红相关事件

数据范围 2000-04-27 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=438)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD" |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| publish_date | string | 事件公告发布日期（日期筛选依据） |
| symbol | string | 股票代码 |
| excute_date | string | 事件执行日期 |
| event_type | string | 事件类型：ExDividends（除息），SpecialDividendsCash（现金特别股息），RegularDividendCashWithAlternative（常规现金股息，可选择股票股息），RegularDividendStockWithAlternative（常规股票股息，可选择现金股息），SpecialDividendsStock（股票特别股息），StockSplits（股票拆分），SpecialDividendCashWithAlternative（特别现金股息，可选择股票股息），RegularDividendsStock（常规股票股息），SpecialDividendStockWithAlternative（特别股票股息，可选择现金股息） |
| number | string | 每股金额 |
| currency | string | 交易币种 |
| event | string | 事件 |

示例：示例1

```python
import panda_data
result = panda_data.get_hk_etf_dividend_event(
        symbol=["2800.HK"],
        start_date="20200101",
        end_date="20260501",
        fields=["excute_date","publish_date","event_type",'event_type_flag'],
    )
print(result)
```

返回示例（前 3 行）：

| symbol | publish_date | excute_date | event_type | event_type_flag |
|:---|:---|:---|:---|:---|
| 2800.HK | 20200428 | 20200428 | ExDividends | EXDIV |
| 2800.HK | 20201030 | 20201030 | ExDividends | EXDIV |
| 2800.HK | 20210429 | 20210429 | ExDividends | EXDIV |

### get_hk_etf_investor_concentration：获取港股ETF投资者集中度

数据范围 2025-01-31 ~ 至今；每日更新 12:00 ~ 13:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=439)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 交易币种 |
| total_investors | int | 总投资者数 |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| total_sharehold | float | 总持股 |
| total_holdings_value | float | 总持股市值 |

示例：示例1

```python
import panda_data
result = panda_data.get_hk_etf_investor_concentration(
        symbol=["2800.HK"],
        fields=[],
    )
print(result)
```

返回示例（前 3 行）：

| symbol | currency | total_investors | investor_outstanding_ratio | total_sharehold | total_holdings_value |
|:---|:---|:---|:---|:---|:---|
| 2800.HK | HKD | 21 | 1.5134 | 79452062.0 | 2.407903e+08 |

### get_hk_etf_top20_concentration：获取港股ETF前20投资者集中度

每日更新 12:00 ~ 13:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=440)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 交易币种 |
| top_investors_num | int | 前n个投资者数（对于此接口通常为20，不足20个投资者的会返回小于20） |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| sharehold | float | 前n个投资者总持股 |
| holdings_value | float | 前n个投资者总持股市值 |

示例：示例1

```python
import panda_data
result = panda_data.get_hk_etf_top20_concentration(
    symbol=["2800.HK"],
    fields=[],
)
print(result)
```

返回示例（前 3 行）：

| symbol | currency | top_investors_num | investor_outstanding_ratio | sharehold | holdings_value |
|:---|:---|:---|:---|:---|:---|
| 2800.HK | HKD | 20 | 1.5134 | 79452062.0 | 2.407903e+08 |

### get_hk_etf_investor_ranking：获取港股ETF投资者排行

数据范围 2000-01-01 ~ 至今；每日更新 12:00 ~ 13:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=441)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |
| max_rank | Optional[int] | 否 | 最大返回排名（小于等于20的正整数），默认为空返回前20名 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| investor_name | string | 投资者名称 |
| investor_type | string | 投资者类型 |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| sharehold | float | 投资者持股 |
| sharehold_change | float | 投资者持股较上一次报告变化 |
| info_date | string | 此次报告日期 |
| turnover_rating | string | 换手率评级 |
| currency | string | 交易币种 |
| rank | int | 排行 |

示例：示例1

```python
import panda_data
result = panda_data.get_hk_etf_investor_ranking(
        symbol=["2800.HK"],
        fields=["investor_type","investor_outstanding_ratio","sharehold",'sharehold_change',"info_date"],
        max_rank=10,
    )
print(result)
```

返回示例（前 3 行）：

| investor_type | investor_outstanding_ratio | sharehold | sharehold_change | info_date | symbol |
|:---|:---|:---|:---|:---|:---|
| Investment Advisor | 1.1877 | 62355249.0 | -339982333.0 | 20260630 | 2800.HK |
| Investment Advisor/Hedge Fund | 0.1371 | 7200000.0 | 7200000.0 | 20260331 | 2800.HK |
| Investment Advisor | 0.0614 | 3222775.0 | 2956775.0 | 20251231 | 2800.HK |

## 美股ETF数据

### get_us_etf_detail：获取美股ETF基本信息(每日快照)

数据范围 2014-03-10 ~ 至今；每日更新 10:30 ~ 11:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=405)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| date | str | 否 | 快照交易日，格式 "YYYYMMDD" 或 "YYYY-MM-DD"，返回该交易日全部 symbol 快照 |
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 快照交易日 |
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| listed_date | string | 上市日期 |
| local_name | string | 当地股票名称 |
| exchange_name | string | 交易所名称 |
| status | int | 股票状态 |
| isin_code | string | 国际证券识别编码 |
| abbrev_symbol | string | 股票的名称缩写 |
| trading_code | string | 交易代码 |
| rcs_asset_category_name | string | 资产类别名称 |
| business_sector | string | 业务领域名称（如"Banking & Investment Services"） |
| economic_sector | string | 经济领域名称（如"Financials"） |
| industry_group | string | 行业组名称（如"Banking Services"） |
| incorp_date | string | 公司成立日期 |
| office_address | string | 公司总部地址 |
| office_city | string | 总部城市 |
| office_country | string | 总部所在国家 |
| office_region | string | 总部所在地区 |
| postal_code | string | 总部邮政编码 |
| website | string | 公司网站 |
| asset_state | string | 资产状态 |
| original_symbol | string | LSEG 原始 symbol |

示例：示例1

```python
import panda_data
result = panda_data.get_us_etf_detail(
        date="20260902",
        fields=["symbol","name","status","isin_code"],
    )
print(result)
```

返回示例（前 3 行）：

| symbol | name | status | isin_code |
|:---|:---|:---|:---|
| SPY | SPDR S&P 500... | 1.0 | US78462F1030 |

### get_us_etf_detail_all：获取美股ETF基本信息

每日更新 10:30 ~ 11:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=429)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |
| status | Optional[int] | 否 | 是否在市，1 - 在市，0 - 退市，-1 - 未知 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| listed_date | string | 上市日期 |
| local_name | string | 当地股票名称 |
| exchange_name | string | 交易所名称 |
| status | int | 股票状态 |
| isin_code | string | 国际证券识别编码 |
| abbrev_symbol | string | 股票的名称缩写 |
| trading_code | string | 交易代码 |
| rcs_asset_category_name | string | 资产类别名称 |
| business_sector | string | 业务领域名称（如"Banking & Investment Services"） |
| economic_sector | string | 经济领域名称（如"Financials"） |
| industry_group | string | 行业组名称（如"Banking Services"） |
| incorp_date | string | 公司成立日期 |
| office_address | string | 公司总部地址 |
| office_city | string | 总部城市 |
| office_country | string | 总部所在国家 |
| office_region | string | 总部所在地区 |
| postal_code | string | 总部邮政编码 |
| website | string | 公司网站 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_etf_detail_all(
        symbol=["SPY", "QQQ"],
        fields=["isin_code","status",""],
        status=None,
    )
print(result)
```

返回示例（前 3 行）：

| isin_code | status | symbol |
|:---|:---|:---|
| US78462F1030 | 1.0 | SPY |
| US46090E1038 | 1.0 | QQQ |

### get_us_etf_daily：获取美股ETF日线

数据范围 2014-03-10 ~ 至今；每日更新 09:30 ~ 10:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=430)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD"，与开始日期间不超过5年 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 交易日 |
| symbol | string | 股票代码 |
| open | string | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| pre_close | float | 昨收价 |
| name | string | 股票名称 |
| trade_status | float | 交易状态代码 |
| blkcount | float | 大宗交易笔数 |
| blkvolum | float | 大宗交易量数 |
| bid | float | 买盘价（收盘前最后一笔） |
| ask | float | 卖盘价（收盘前最后一笔） |
| vwap | float | 成交量加权平均价 |
| num_moves | float | 成交笔数 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_etf_daily(
        symbol=["SPY"],
        start_date="20260301",
        end_date="20260401",
        fields=["open",'high','low','close','pre_close'],
    )
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | high | low | close | pre_close |
|:---|:---|:---|:---|:---|:---|:---|
| SPY | 20260401 | 653.90 | 658.520 | 653.000 | 655.24 | 650.34 |
| SPY | 20260331 | 638.94 | 651.540 | 637.980 | 650.34 | 631.97 |
| SPY | 20260330 | 640.11 | 640.370 | 629.280 | 631.97 | 634.09 |

### get_us_etf_dividend_activity：获取美股ETF分红相关事件

数据范围 2000-09-15 ~ 至今；每日更新 11:00 ~ 11:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=431)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD" |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD" |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| publish_date | string | 事件公告发布日期（日期筛选依据） |
| symbol | string | 股票代码 |
| excute_date | string | 事件执行日期 |
| event_type | string | 事件类型：ExDividends（除息），SpecialDividendsCash（现金特别股息），StockSplits（股票拆分），CapitalGainsCash（资本收益现金分配），RegularDividendCashWithAlternative（常规现金股息，可选择股票股息），RegularDividendStockWithAlternative（常规股票股息，可选择现金股息），RegularDividendsStock（常规股票股息），SpecialDividendCashWithAlternative（特别现金股息，可选择股票股息），OtherDividendsCash（其他现金股息），SpecialDividendsStock（股票特别股息），SpecialDividendStockWithAlternative（特别股票股息，可选择现金股息） |
| number | string | 每股金额 |
| currency | string | 交易币种 |
| event | string | 事件 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_etf_dividend_activity(
        symbol=["SPY"],
        fields=["publish_date","excute_date","number"],
        start_date="20200101",
        end_date="20260501",
    )
print(result)
```

返回示例（前 3 行）：

| symbol | publish_date | excute_date | number |
|:---|:---|:---|:---|
| SPY | 20200320 | 20200320 | 1.405559 |
| SPY | 20200619 | 20200619 | 1.3662 |
| SPY | 20200918 | 20200918 | 1.339224 |

### get_us_etf_investor_centralization：获取美股ETF投资者集中度

每日更新 12:00 ~ 13:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=432)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 交易币种 |
| total_investors | int | 总投资者数 |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| total_sharehold | float | 总持股 |
| total_holdings_value | float | 总持股市值 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_etf_investor_centralization(
    symbol=["SPY"],
    fields=[],
)
print(result)
```

返回示例（前 3 行）：

| symbol | currency | total_investors | investor_outstanding_ratio | total_sharehold | total_holdings_value |
|:---|:---|:---|:---|:---|:---|
| SPY | None | 5785 | 59.747 | 620649848.0 | 4.618000e+11 |

### get_us_etf_top20_centralization：获取美股ETF前20投资者集中度

每日更新 12:00 ~ 13:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=433)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 交易币种 |
| top_investors_num | int | 前n个投资者数（对于此接口通常为20，不足20个投资者的会返回小于20） |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| sharehold | float | 前n个投资者总持股 |
| holdings_value | float | 前n个投资者总持股市值 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_etf_top20_centralization(
    symbol=["SPY"],
    fields=[],
)
print(result)
```

返回示例（前 3 行）：

| symbol | currency | top_investors_num | investor_outstanding_ratio | sharehold | holdings_value |
|:---|:---|:---|:---|:---|:---|
| SPY | None | 20 | 26.9869 | 280294920.0 | 2.093158e+11 |

### get_us_etf_investor_leaderboard：获取美股ETF投资者排行

数据范围 2025-01-15 ~ 至今；每日更新 14:00 ~ 16:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=434)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | ETF代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |
| max_rank | Optional[int] | 否 | 最大返回排名（小于等于20的正整数），默认为空返回前20名 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| investor_name | string | 投资者名称 |
| investor_type | string | 投资者类型 |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| sharehold | float | 投资者持股 |
| sharehold_change | float | 投资者持股较上一次报告变化 |
| info_date | string | 此次报告日期 |
| turnover_rating | string | 换手率评级 |
| currency | string | 交易币种 |
| rank | int | 排行 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_etf_investor_leaderboard(
        symbol=["SPY"],
        fields=["investor_type","investor_outstanding_ratio","info_date"],
        max_rank=10,
    )
print(result)
```

返回示例（前 3 行）：

| investor_type | investor_outstanding_ratio | info_date | symbol |
|:---|:---|:---|:---|
| Research Firm | 4.1500 | 20260630 | SPY |
| Bank and Trust | 3.2512 | 20260630 | SPY |
| Research Firm | 2.4181 | 20260630 | SPY |

## 港股指数数据

### get_hk_index_detail：提供港股指数代码的基本信息，覆盖宽基及市值规模指数（恒生指数、恒生综合指数）、行业指数（金融、资讯科技、医疗保健）、主题指数（恒生科技、港交所科技100、恒生生物科技）、互联互通及跨市场指数（港股通、大湾区、港韩系列）、因子与 ESG 指数（高股息、低波动、低碳），以及杠杆、短仓、期货和波幅等策略及衍生指数。

数据范围 1964-12-30 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=344)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 指数代码，保留后缀，如 "HSI.HK"，可以是单个字符串或字符串列表 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |
| date | Optional[str] | 否 | 查询日期，支持 YYYYMMDD 或 YYYY-MM-DD；为空时返回最新在市指数列表；传入历史日期时仅保留当时已上市且在市的指数 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 指数代码，如 HSI.HK |
| abbrev_symbol | str | 指数简称 |
| name | str | 指数全称 |
| listed_date | str | 启用日期，格式为 "YYYYMMDD" |
| de_listed_date | str | 摘牌日期，格式为 "YYYYMMDD" |
| nation | str | 所属国家 |
| currency | str | 交易币种 |
| latest_trade_date | str | 最新交易日期，格式为 "YYYYMMDD" |
| earliest_trade_date | str | 最早交易日期，格式为 "YYYYMMDD" |

示例：获取恒生指数基本信息

```python
import panda_data
result = panda_data.get_hk_index_detail(
    symbol="HSI.HK",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | abbrev_symbol | currency | de_listed_date | earliest_trade_date | latest_trade_date | listed_date | name | nation |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| HSI.HK | 恒生指数 | HKD | None | 19640731 | 20260911 | 19691124 | 香港恒生指数 | 中国香港 |

### get_hk_index_daily：提供港股指数代码的日度行情，覆盖宽基及市值规模指数（恒生指数、恒生综合指数）、行业指数（金融、资讯科技、医疗保健）、主题指数（恒生科技、港交所科技100、恒生生物科技）、互联互通及跨市场指数（港股通、大湾区、港韩系列）、因子与 ESG 指数（高股息、低波动、低碳），以及杠杆、短仓、期货和波幅等策略及衍生指数。

数据范围 2020-01-01 ~ 至今；每日更新 19:00 ~ 20:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=342)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD"，与开始日期间不超过5年 |
| symbol | Optional[Union[str, List[str]]] | 否 | 指数代码，保留后缀，如 "HSI.HK"，可以是单个字符串或字符串列表 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 指数代码，如 HSI.HK |
| date | str | 交易日期，格式为 "YYYYMMDD" |
| open | double | 开盘价 |
| high | double | 最高价 |
| low | double | 最低价 |
| close | double | 收盘价 |
| volume | double | 成交量 |
| turnover | double | 换手率（%） |
| pre_close | double | 前收盘价 |
| change | double | 涨跌额 |

示例：获取恒生指数近期日线

```python
import panda_data
result = panda_data.get_hk_index_daily(
    start_date="20260101",
    end_date="20260131",
    symbol="HSI.HK",
    fields=["symbol","date","open","close","change",'high','low','volume','turnover','pre_close'],
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | close | change | high | low | volume | turnover | pre_close |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 0 | HSI.HK | 20260130 | 27785.98 | 27387.11 -580.98 | 27887.24 | 27384.02 | 2.050780e+10 | 0.422892 | 27968.09 |
| HSI.HK | 20260129 | 27627.11 | 27968.09 | 141.18 | 28056.10 | 27611.90 | 2.983050e+10 | 0.420421 | 27826.91 |
| HSI.HK | 20260128 | 27325.89 | 27826.91 | 699.96 | 27826.91 | 27258.10 | 2.106191e+10 | 0.482287 | 27126.95 |

### get_hk_index_constituents：提供港股指数指定交易日的成分证券代码。覆盖宽基及市值规模指数（恒生指数、恒生综合指数）、行业指数（金融、资讯科技、医疗保健）、主题指数（恒生科技、港交所科技100、恒生生物科技）、互联互通及跨市场指数（港股通、大湾区、港韩系列）、因子与 ESG 指数（高股息、低波动、低碳），以及杠杆、短仓、期货和波幅等策略及衍生指数。

数据范围 2026-09-01 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=346)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD"，与开始日期间不超过5年 |
| index_symbol | Optional[Union[str, List[str]]] | 否 | 指数代码，如 "HSI.HK"，可以是单个字符串或字符串列表 |
| stock_symbol | Optional[Union[str, List[str]]] | 否 | 成分股代码，如 "00700.HK"，可以是单个字符串或字符串列表 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| index_symbol | str | 指数代码，如 HSI.HK |
| stock_symbol | str | 成分股代码，如 00700.HK |
| date | str | 交易日期，格式为 "YYYYMMDD" |
| name | str | 成分股简称 |

示例：获取恒生指数指定日期成分股

```python
import panda_data
result = panda_data.get_hk_index_constituents(
    start_date="20260914",
    end_date="20260914",
    index_symbol="",
    fields=["index_symbol","stock_symbol","date","name"]
)
print(result)
```

返回示例（前 3 行）：

| index_symbol | stock_symbol | date | name |
|:---|:---|:---|:---|
| HKEXT100.HKI | 00013.HK | 20260914 | 和黄医药 |
| HKEXT100.HKI | 00020.HK | 20260914 | 商汤-W |
| HKEXT100.HKI | 00100.HK | 20260914 | MINIMAX-W |

## 美股指数数据

### get_us_index_detail：提供 23 个美股指数代码的基本信息。覆盖标普500（SPX）、道琼斯工业平均指数（DJI）、纳斯达克综合指数（IXIC、@CCO）、纽约证交所综合指数（NYA）、美国证交所综合指数（XAX）、纳斯达克全球综合指数（NQGM）、纳斯达克全球精选综合指数（NQGS）、纳斯达克100指数（NDX）、纳斯达克100等权重指数（NDXE）、纳斯达克100总收益指数（XNDX）、纳斯达克100波动率指数（VOLNDX）、纳斯达克科技市值加权指数（NDXTMC）、费城半导体行业指数（SOX）、纳斯达克金融100指数（IXF）、纳斯达克计算机指数（IXCO）、纳斯达克电信股指数（IXTC）、纳斯达克生物技术指数（NBI）、纳斯达克互联网指数（QNET）、纳斯达克清洁绿能指数（CELS）、纳斯达克清洁绿能总回报指数（CEXX）、纳斯达克中国金龙指数（HXC）和纳斯达克中国金龙总回报指数（HXCX）。

数据范围 1927-12-30 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=345)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | 指数代码，去后缀，如 "DJI"，可以是单个字符串或字符串列表 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |
| date | Optional[str] | 否 | 查询日期，支持 YYYYMMDD 或 YYYY-MM-DD；为空时返回最新在市指数列表；传入历史日期时仅保留当时已上市且在市的指数 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 指数代码，如 DJI |
| abbrev_symbol | str | 指数简称 |
| name | str | 指数全称 |
| listed_date | str | 启用日期，格式为 "YYYYMMDD" |
| de_listed_date | str | 摘牌日期，格式为 "YYYYMMDD" |
| nation | str | 所属国家 |
| currency | str | 交易币种 |
| latest_trade_date | str | 最新交易日期，格式为 "YYYYMMDD" |
| earliest_trade_date | str | 最早交易日期，格式为 "YYYYMMDD" |

示例：获取道琼斯工业指数基本信息

```python
import panda_data
result = panda_data.get_us_index_detail(
    symbol="DJI",
    fields=["symbol","name","listed_date","currency"]
)
print(result)
```

返回示例（前 3 行）：

| symbol | abbrev_symbol | currency | de_listed_date | earliest_trade_date | latest_trade_date | listed_date | name | nation |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| DJI | 道琼斯工业平均 | USD | None | 18960526 | 20260910 | 18960526 | 道琼斯工业平均指数 | 美国 |

### get_us_index_daily：提供 23 个美股指数代码的日度行情。覆盖标普500（SPX）、道琼斯工业平均指数（DJI）、纳斯达克综合指数（IXIC、@CCO）、纽约证交所综合指数（NYA）、美国证交所综合指数（XAX）、纳斯达克全球综合指数（NQGM）、纳斯达克全球精选综合指数（NQGS）、纳斯达克100指数（NDX）、纳斯达克100等权重指数（NDXE）、纳斯达克100总收益指数（XNDX）、纳斯达克100波动率指数（VOLNDX）、纳斯达克科技市值加权指数（NDXTMC）、费城半导体行业指数（SOX）、纳斯达克金融100指数（IXF）、纳斯达克计算机指数（IXCO）、纳斯达克电信股指数（IXTC）、纳斯达克生物技术指数（NBI）、纳斯达克互联网指数（QNET）、纳斯达克清洁绿能指数（CELS）、纳斯达克清洁绿能总回报指数（CEXX）、纳斯达克中国金龙指数（HXC）和纳斯达克中国金龙总回报指数（HXCX）。

数据范围 2020-01-01 ~ 至今；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=343)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD"，与开始日期间不超过5年 |
| symbol | Optional[Union[str, List[str]]] | 否 | 指数代码，如 "DJI"，可以是单个字符串或字符串列表 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | str | 指数代码，如 DJI |
| date | str | 交易日期，格式为 "YYYYMMDD" |
| open | double | 开盘价 |
| high | double | 最高价 |
| low | double | 最低价 |
| close | double | 收盘价 |
| volume | double | 成交量 |
| turnover | double | 换手率（%） |
| pre_close | double | 前收盘价 |
| change | double | 涨跌额 |

示例：获取道琼斯工业指数近期日线

```python
import panda_data
result = panda_data.get_us_index_daily(
    start_date="20260101",
    end_date="20260131",
    symbol="DJI",
    fields=["symbol","date","open","close","change",'high','low','volume','turnover','pre_close'],
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | close | change | high | low | volume | turnover | pre_close |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 0 | DJI | 20260130 | 48991.62 | 48892.47 -179.09 | 49047.68 | 48459.88 | 761991990.0 | 0.743303 | 49071.56 |
| DJI | 20260129 | 48938.27 | 49071.56 | 55.96 | 49292.81 | 48597.22 | 693044490.0 | 0.681384 | 49015.60 |
| DJI | 20260128 | 49024.68 | 49015.60 | 12.19 | 49150.34 | 48901.49 | 470999440.0 | 0.466846 | 49003.41 |

### get_us_index_constituents：提供 23 个美股指数指定交易日的成分证券代码。覆盖标普500（SPX）、道琼斯工业平均指数（DJI）、纳斯达克综合指数（IXIC、@CCO）、纽约证交所综合指数（NYA）、美国证交所综合指数（XAX）、纳斯达克全球综合指数（NQGM）、纳斯达克全球精选综合指数（NQGS）、纳斯达克100指数（NDX）、纳斯达克100等权重指数（NDXE）、纳斯达克100总收益指数（XNDX）、纳斯达克100波动率指数（VOLNDX）、纳斯达克科技市值加权指数（NDXTMC）、费城半导体行业指数（SOX）、纳斯达克金融100指数（IXF）、纳斯达克计算机指数（IXCO）、纳斯达克电信股指数（IXTC）、纳斯达克生物技术指数（NBI）、纳斯达克互联网指数（QNET）、纳斯达克清洁绿能指数（CELS）、纳斯达克清洁绿能总回报指数（CEXX）、纳斯达克中国金龙指数（HXC）和纳斯达克中国金龙总回报指数（HXCX）。

数据范围 2026-01-01 ~ 至今；每日更新 22:00 ~ 23:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=347)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD"，与开始日期间不超过5年 |
| index_symbol | Optional[Union[str, List[str]]] | 否 | 指数代码，如 "DJI"，可以是单个字符串或字符串列表 |
| stock_symbol | Optional[Union[str, List[str]]] | 否 | 成分股代码，如 "AAPL"，可以是单个字符串或字符串列表 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表，传空返回全部公开字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| index_symbol | str | 指数代码，如 DJI |
| stock_symbol | str | 成分股代码，如 AAPL |
| date | str | 交易日期，格式为 "YYYYMMDD" |
| name | str | 成分股简称 |

示例：获取道琼斯工业指数指定日期成分股

```python
import panda_data
result = panda_data.get_us_index_constituents(
    start_date="20260911",
    end_date="20260911",
    index_symbol="DJI",
    fields=["index_symbol","stock_symbol","date","name"]
)
print(result)
```

返回示例（前 3 行）：

| index_symbol | stock_symbol | date | name |
|:---|:---|:---|:---|
| DJI | AAPL | 20260911 | 苹果 |

## 美股轮证数据

### get_us_warrant_detail：获取美股warrant基本信息(每日快照)

数据范围 2014-05-09 ~ 至今；每日更新 11:30 ~ 12:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=385)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| date | str | 否 | 快照交易日，格式 "YYYYMMDD" 或 "YYYY-MM-DD"，返回该交易日全部 symbol 快照 |
| symbol | Optional[Union[str, List[str]]] | 否 | warrant代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 快照交易日 |
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| listed_date | string | 上市日期 |
| local_name | string | 当地股票名称 |
| exchange_name | string | 交易所名称 |
| status | int | 股票状态 |
| isin_code | string | 国际证券识别编码 |
| abbrev_symbol | string | 股票的名称缩写 |
| rcs_asset_category_name | string | 资产类别名称 |
| business_sector | string | 业务领域名称（如"Banking & Investment Services"） |
| economic_sector | string | 经济领域名称（如"Financials"） |
| industry_group | string | 行业组名称（如"Banking Services"） |
| incorp_date | string | 公司成立日期 |
| office_address | string | 公司总部地址 |
| office_city | string | 总部城市 |
| office_country | string | 总部所在国家 |
| office_region | string | 总部所在地区 |
| postal_code | string | 总部邮政编码 |
| website | string | 公司网站 |
| asset_state | string | 资产状态 |
| original_symbol | string | LSEG 原始 symbol |
| strike_price | double | 行权价格 |
| exercise_date | string | 行权日期 |
| underlying_symbol | string | 标的 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_warrant_detail(
        date="20260901",
        fields=["symbol","name","status","underlying_symbol"],
    )
print(result)
```

返回示例（前 3 行）：

| symbol | name | status | underlying_symbol |
|:---|:---|:---|:---|
| AACIW | None | 1.0 | AACI.O |

### get_us_warrant_detail_all：获取美股warrant基本信息

每日更新 10:30 ~ 11:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=424)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | warrant代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |
| status | Optional[int] | 否 | 是否在市，1 - 在市，0 - 退市，-1 - 未知 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| name | string | 股票名称 |
| listed_date | string | 上市日期 |
| local_name | string | 当地股票名称 |
| exchange_name | string | 交易所名称 |
| status | int | 股票状态 |
| isin_code | string | 国际证券识别编码 |
| abbrev_symbol | string | 股票的名称缩写 |
| rcs_asset_category_name | string | 资产类别名称 |
| business_sector | string | 业务领域名称（如"Banking & Investment Services"） |
| economic_sector | string | 经济领域名称（如"Financials"） |
| industry_group | string | 行业组名称（如"Banking Services"） |
| incorp_date | string | 公司成立日期 |
| office_address | string | 公司总部地址 |
| office_city | string | 总部城市 |
| office_country | string | 总部所在国家 |
| office_region | string | 总部所在地区 |
| postal_code | string | 总部邮政编码 |
| website | string | 公司网站 |
| strike_price | double | 行权价格 |
| exercise_date | string | 行权日期 |
| underlying_symbol | string | 标的 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_warrant_detail_all(
        symbol=["AACIW","AACOW"],
        fields=["underlying_symbol","strike_price","status"],
        status=None,
    )
print(result)
```

返回示例（前 3 行）：

| status | strike_price | symbol | underlying_symbol |
|:---|:---|:---|:---|
| 1.0 | 11.5 | AACIW | AACI.O |
| 1.0 | 11.5 | AACOW | AACO.O |

### get_us_warrant_daily：获取美股warrant日线

数据范围 2014-05-09 ~ 至今；每日更新 11:00 ~ 11:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=425)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | warrant代码，可传单个或列表，为空返回全部 |
| start_date | str | 是 | 查询起始日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD"，与结束日期间不超过5年 |
| end_date | str | 是 | 查询结束日期，格式为 "YYYYMMDD" 或 "YYYY-MM-DD"，与开始日期间不超过5年 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 交易日 |
| symbol | string | 股票代码 |
| open | string | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| pre_close | float | 昨收价 |
| name | string | 股票名称 |
| trade_status | float | 交易状态代码 |
| blkcount | float | 大宗交易笔数 |
| blkvolum | float | 大宗交易量数 |
| bid | float | 买盘价（收盘前最后一笔） |
| ask | float | 卖盘价（收盘前最后一笔） |
| vwap | float | 成交量加权平均价 |
| num_moves | float | 成交笔数 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_warrant_daily(
        symbol=['ABLVW'],
        start_date="20260306",
        end_date="20260310",
        fields=["open",'high','low','close','pre_close'],
    )
print(result)
```

返回示例（前 3 行）：

| symbol | date | open | high | low | close | pre_close |
|:---|:---|:---|:---|:---|:---|:---|
| ABLVW | 20260310 | 0.0198 | 0.0198 | 0.0182 | 0.0198 | 0.0169 |
| ABLVW | 20260309 | 0.0163 | 0.0198 | 0.0163 | 0.0169 | 0.0217 |
| ABLVW | 20260306 | 0.0217 | 0.0217 | 0.0217 | 0.0217 | 0.0173 |

### get_us_warrant_investor_centralization：获取美股warrant投资者集中度

每日更新 12:00 ~ 13:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=426)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | warrant代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 交易币种 |
| total_investors | int | 总投资者数 |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| total_sharehold | float | 总持股 |
| total_holdings_value | float | 总持股市值 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_warrant_investor_centralization(
        fields=["total_investors","total_sharehold"],
    )
print(result)
```

返回示例（前 3 行）：

| total_investors | total_sharehold | symbol |
|:---|:---|:---|
| 41 | 7341750.0 | ACHR_t |
| 10 | 190431.0 | ACONW |
| 24 | 1563441.0 | ADSEW |

### get_us_warrant_top20_centralization：获取美股warrant前20投资者集中度

每日更新 12:00 ~ 13:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=427)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | warrant代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| currency | string | 交易币种 |
| top_investors_num | int | 前n个投资者数（对于此接口通常为20，不足20个投资者的会返回小于20） |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| sharehold | float | 前n个投资者总持股 |
| holdings_value | float | 前n个投资者总持股市值 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_warrant_top20_centralization(
        symbol=["ACONW"],
        fields=["top_investors_num","sharehold"],
    )
print(result)
```

返回示例（前 3 行）：

| top_investors_num | sharehold | symbol |
|:---|:---|:---|
| 10 | 190431.0 | ACONW |

### get_us_warrant_investor_leaderboard：获取美股warrant投资者排行

数据范围 2025-02-18 ~ 至今；每日更新 12:00 ~ 13:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=428)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[str, List[str]]] | 否 | warrant代码，可传单个或列表，为空返回全部 |
| fields | Optional[Union[str, List[str]]] | 否 | 需要返回的字段列表 |
| max_rank | Optional[int] | 否 | 最大返回排名（小于等于20的正整数），默认为空返回前20名 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| investor_name | string | 投资者名称 |
| investor_type | string | 投资者类型 |
| investor_outstanding_ratio | float | 投资者持有占总流通股比例 |
| sharehold | float | 投资者持股 |
| sharehold_change | float | 投资者持股较上一次报告变化 |
| info_date | string | 此次报告日期 |
| turnover_rating | string | 换手率评级 |
| currency | string | 交易币种 |
| rank | int | 排行 |

示例：示例1

```python
import panda_data
result = panda_data.get_us_warrant_investor_leaderboard(
        symbol=["ACONW"],
        fields=["investor_name","investor_type","sharehold",'sharehold_change',"info_date"],
        max_rank=10,
    )
print(result)
```

返回示例（前 3 行）：

| investor_name | investor_type | sharehold | sharehold_change | info_date | symbol |
|:---|:---|:---|:---|:---|:---|
| CAPTRUST Financial Advisors | Investment Advisor | 78400.0 | 0.0 | 20260630 | ACONW |
| Clear Street LLC | Research Firm | 47123.0 | 0.0 | 20250630 | ACONW |
| Clear Street Group Inc | Investment Advisor | 47023.0 | 0.0 | 20260630 | ACONW |
