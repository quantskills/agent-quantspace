---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - A-Share Reference Data
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# A股参考数据

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 概念基础数据

### get_concept_list：获取概念列表

数据范围 2019-01-17 ~ 至今；每日更新 23:30 ~ 23:50；[官方页面](https://www.pandaaiquant.com/docs/api?id=10)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| concept | Optional[Union[string, List[string]]] | 否 | 概念名称 |
| start_date | Optional[string] | 否 | 开始时间 |
| end_date | Optional[string] | 否 | 结束时间 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| name | string | 概念名称 |
| date | string | 概念纳入日期 |

示例：获取一定日期内某个概念的列表

```python
import panda_data
result = panda_data.get_concept_list(
    start_date="20250101",
    end_date="20250131",
    concept="英伟达概念"
)
print(result)
```

返回示例（前 3 行）：

| name | date |
|:---|:---|
| 英伟达概念 | 20250117 |

### get_concept_constituents：获取概念成分股

数据范围 2019-01-17 ~ 至今；每日更新 23:27 ~ 23:47；[官方页面](https://www.pandaaiquant.com/docs/api?id=11)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| concept | Optional[Union[string, List[string]]] | 否 | 概念名称 |
| concept_stock | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| date | Optional[string] | 否 | 日期，返回该日期前被纳入对应概念的股票 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| concept | string | 概念名称 |
| concept_stock | string | 概念成分股 |
| date | string | 股票纳入概念日期 |

示例：获取一定日期内某个概念成分股

```python
import panda_data
result = panda_data.get_concept_constituents(
    date="20250131",
    concept="英伟达概念",
    concept_stock="",
    fields=["concept", "concept_stock", "date"]
)
print(result)
```

返回示例（前 3 行）：

| concept_stock | date | concept |
|:---|:---|:---|
| 000034.SZ | 20250117 | 英伟达概念 |
| 000716.SZ | 20250117 | 英伟达概念 |
| 000938.SZ | 20250117 | 英伟达概念 |

## 市场参考数据

### get_stock_detail：获取A股基本信息

数据范围 1990-12-01 ~ 至今；每日更新 08:42 ~ 09:02；[官方页面](https://www.pandaaiquant.com/docs/api?id=355)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |
| date | Optional[string] | 否 | 查询日期，支持YYYYMMDD为空时返回最新在市股票列表；传入历史日期时返回该日在市的股票 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| market_tplus | integer | 交易制度 |
| name | string | 股票名称 |
| special_type | string | 特别处理状态 |
| status | integer | 股票状态 |
| de_listed_date | string | 退市日期 |
| listed_date | string | 上市日期 |
| sector_code_name | string | 以当地语言为标准的板块代码名 |
| abbrev_symbol | string | 股票的名称缩写 |
| sector_code | string | 板块缩写代码 |
| min_order_amount | float | 一手对应多少股 |
| trading_hours | string | 产品最新交易时间 |
| board_type | string | 板块类别 |
| issue_price | float | 该证券发行价 |
| trading_code | string | 交易代码 |
| office_address | string | 公司地址 |
| province | string | 省份 |
| purchasedate | string | 申购日期 |

示例：查询历史日期的在市股票列表

```python
import panda_data
result = panda_data.get_stock_detail(
        symbol=["000001.SZ","000002.SZ","000003.SZ"],
        fields=[""],
        date="20030101"
    )
print(result)
```

返回示例（前 3 行）：

| market_tplus | name | special_type | status | de_listed_date | listed_date | sector_code_name | abbrev_symbol | sector_code | min_order_amount | trading_hours | board_type | issue_price | trading_code | office_address | province | purchasedate | symbol |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 1 | 平安银行 | Normal | 1 | 0000-00-00 | 1991-04-03 | 金融 | PAYH | Financials | 100.0 | 09:31-11:30,13:01-15:00 | MainBoard | 40.0 | 000001 | 中国广东省深圳市罗湖区深南东路5047号;中国广东省深圳市福田区益田路5023号平安金融中心B座 | 广东省 | None | 000001.SZ |
| 1 | 万科A | Normal | 1 | 0000-00-00 | 1991-01-29 | 房地产 | WKA | RealEstate | 100.0 | 09:31-11:30,13:01-15:00 | MainBoard | 1.0 | 000002 | 中国广东省深圳市福田区梅林路63号万科大厦 | 广东省 | None | 000002.SZ |

### get_stock_detail_all：获取A股基本信息(全部股票包含退市)

数据范围 1990-12-01 ~ 至今；每日更新 08:42 ~ 09:02；[官方页面](https://www.pandaaiquant.com/docs/api?id=24)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 股票代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 股票代码 |
| market_tplus | integer | 交易制度 |
| name | string | 股票名称 |
| special_type | string | 特别处理状态 |
| status | integer | 股票状态 |
| de_listed_date | string | 退市日期 |
| listed_date | string | 上市日期 |
| sector_code_name | string | 以当地语言为标准的板块代码名 |
| abbrev_symbol | string | 股票的名称缩写 |
| sector_code | string | 板块缩写代码 |
| min_order_amount | float | 一手对应多少股 |
| trading_hours | string | 产品最新交易时间 |
| board_type | string | 板块类别 |
| issue_price | float | 该证券发行价 |
| trading_code | string | 交易代码 |
| office_address | string | 公司地址 |
| province | string | 省份 |
| purchasedate | string | 申购日期 |

示例：查询全状态最新股票列表

```python
import panda_data
result = panda_data.get_stock_detail_all(
        symbol=["000001.SZ","000002.SZ","000003.SZ"],
        fields=[""]
    )
print(result)
```

返回示例（前 3 行）：

| market_tplus | name | special_type | status | de_listed_date | listed_date | sector_code_name | abbrev_symbol | sector_code | min_order_amount | trading_hours | board_type | issue_price | trading_code | office_address | province | purchasedate | symbol |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 1 | 平安银行 | Normal | 1 | 0000-00-00 | 1991-04-03 | 金融 | PAYH | Financials | 100.0 | 09:31-11:30,13:01-15:00 | MainBoard | 40.0 | 000001 | 中国广东省深圳市罗湖区深南东路5047号;中国广东省深圳市福田区益田路5023号平安金融中心B座 | 广东省 | None | 000001.SZ |
| 1 | 万科A | Normal | 1 | 0000-00-00 | 1991-01-29 | 房地产 | WKA | RealEstate | 100.0 | 09:31-11:30,13:01-15:00 | MainBoard | 1.0 | 000002 | 中国广东省深圳市福田区梅林路63号万科大厦 | 广东省 | None | 000002.SZ |
| 1 | PT金田A | PT | 0 | 2002-06-14 | 1991-07-03 | 未知 | PTJTA | Unknown | 100.0 | 09:31-11:30,13:01-15:00 | MainBoard | 10.0 | 000003 | 深圳市罗湖区南湖街道和平社区和平路1161号泰山大厦3层301-303 | 广东省 | None | 000003.SZ |

### get_index_detail：获取指数基本信息

数据范围 1991-04-04 ~ 至今；每日更新 08:47 ~ 09:07；[官方页面](https://www.pandaaiquant.com/docs/api?id=356)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指数代码 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| date | Optional[string] | 否 | 查询日期，支持YYYYMMDD为空时返回最新在市指数列表；传入历史日期时返回该日在市的指数 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指数代码 |
| abbrev_symbol | string | 指数简称 |
| de_listed_date | string | 退市日期 |
| listed_date | string | 上市日期 |
| market_tplus | float | 交易制度 |
| min_order_amount | float | 最小下单量 |
| name | string | 指数名称 |
| status | integer | 指数状态 |
| trading_hours | string | 交易时间 |

示例：查询历史日期的在市指数列表

```python
import panda_data
result = panda_data.get_index_detail(
        symbol=["000001.SH", "000023.SH"],
        fields=[""],
        date="20160101"
    )
print(result)
```

返回示例（前 3 行）：

| symbol | abbrev_symbol | de_listed_date | listed_date | market_tplus | min_order_amount | name | status | trading_hours |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SH | SZZS | 0000-00-00 | 1991-07-15 | 0.0 | 1.0 | 上证指数 | 1 | 09:31-11:30,13:01-15:00 |

### get_index_detail_all：获取指数基本信息(全部指数包含退市)

数据范围 1991-04-04 ~ 至今；每日更新 08:47 ~ 09:07；[官方页面](https://www.pandaaiquant.com/docs/api?id=20)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指数代码 |
| status | Optional[integer] | 否 | 指数状态，1 -正常交易，0 -已退市，-1 -暂无信息；为空返回所有状态 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| date | Optional[string] | 否 | 查询日期，支持YYYYMMDD为空时返回最新指数列表；传入历史日期时仅保留当时已上市的指数 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指数代码 |
| abbrev_symbol | string | 指数简称 |
| de_listed_date | string | 退市日期 |
| listed_date | string | 上市日期 |
| market_tplus | float | 交易制度 |
| min_order_amount | float | 最小下单量 |
| name | string | 指数名称 |
| status | integer | 指数状态 |
| trading_hours | string | 交易时间 |

示例：查询全状态最新指数列表

```python
import panda_data
result = panda_data.get_index_detail_all(
        symbol=["000001.SH", "000023.SH"],
        fields=[""]
    )
print(result)
```

返回示例（前 3 行）：

| symbol | abbrev_symbol | de_listed_date | listed_date | market_tplus | min_order_amount | name | status | trading_hours |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 000001.SH | SZZS | 0000-00-00 | 1991-07-15 | 0.0 | 1.0 | 上证指数 | 1 | 09:31-11:30,13:01-15:00 |
| 000023.SH | HFLZ | 2015-08-28 | 2008-11-19 | 0.0 | 1.0 | 沪分离债 | 0 | 09:31-11:30,13:01-15:00 |

## 行业基础数据

### get_industry_constituents：获取行业成分股数据

数据范围 1989-11-01 ~ 至今；每日更新 08:50 ~ 09:10；[官方页面](https://www.pandaaiquant.com/docs/api?id=30)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| industry_code | Optional[Union[string, List[string]]] | 否 | 行业代码，如"801010" |
| stock_symbol | Optional[Union[string, List[string]]] | 否 | 股票代码，如"000001.SZ" |
| level | Optional[string] | 否 | 行业级别，可选值："L1"(一级)、"L2"(二级)、"L3"(三级) |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| reference | Optional[string] | 否 | 分类依据，可选值："sws_2021"（默认，申万2021行业分类）、"citics_2019"（中信行业分类） |
| date | Optional[string] | 否 | 查询日期，支持YYYYMMDD或YYYY-MM-DD；为空时使用今天 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| stock_symbol | string | 股票代码 |
| l1_code | string | 一级行业代码 |
| in_date | string | 纳入时间 |
| l1_name | string | 一级行业名称 |
| l2_code | string | 二级行业代码 |
| l2_name | string | 二级行业名称 |
| l3_code | string | 三级行业代码 |
| l3_name | string | 三级行业名称 |
| out_date | string | 剔除时间 |
| stock_name | string | 股票名称 |

示例：获取某个申万行业的成分股数据

```python
import panda_data
result = panda_data.get_industry_constituents(
            industry_code="801780",
            stock_symbol="000001.SZ",
            level="L1",
            fields=["stock_symbol", "l1_code", "l1_name", "in_date", "out_date"],
            reference="sws_2021",
            date="20251231"
)
print(result)
```

返回示例（前 3 行）：

| stock_symbol | l1_code | l1_name | in_date | out_date |
|:---|:---|:---|:---|:---|
| 000001.SZ | 801780 | 银行 | 20210730 | None |

### get_industry_detail：获取行业基本信息数据

数据范围 1989-11-01 ~ 至今；每日更新 08:58 ~ 09:18；[官方页面](https://www.pandaaiquant.com/docs/api?id=31)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| level | Optional[string] | 否 | 行业级别，可选值："L1"(一级)、"L2"(二级)、"L3"(三级) |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| reference | Optional[string] | 否 | 分类依据，可选值："sws_2021"（默认，申万2021行业分类）、"citics_2019"（中信行业分类） |
| date | Optional[string] | 否 | 查询日期，支持YYYYMMDD或YYYY-MM-DD；返回该日期或之前最近的行业快照 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| industry_code | string | 行业代码 |
| industry_name | string | 行业名称 |
| parent_code | string | 上级行业代码（仅L2支持） |
| parent_name | string | 上级行业名称（仅L2支持） |
| parent_l2_code | string | 上级二级行业代码（仅L3支持） |
| parent_l2_name | string | 上级二级行业名称（仅L3支持） |
| parent_l1_code | string | 上级一级行业代码（仅L3支持） |
| parent_l1_name | string | 上级一级行业名称（仅L3支持） |

示例：获取所有申万行业基本信息（一级）

```python
import panda_data
result = panda_data.get_industry_detail(
    level="L1",
    fields=["industry_code"],
    date="20251231",
    reference="sws_2021",
)
print(result)
```

返回示例（前 3 行）：

| industry_code |
|:---|
| 801010 |
| 801030 |
| 801040 |

### get_stock_industry：获取指定股票所属的行业信息

数据范围 1989-11-01 ~ 至今；每日更新 08:50 ~ 09:10；[官方页面](https://www.pandaaiquant.com/docs/api?id=32)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| stock_symbol | Union[string, List[string]] | 是 | 股票代码，如"000001.SZ"；也可传入股票代码列表，一次查询多个股票；不可为空 |
| level | Optional[string] | 否 | 行业级别，可选值："L1"(一级)、"L2"(二级)、"L3"(三级) |
| reference | Optional[string] | 否 | 分类依据，可选值："sws_2021"（默认，申万2021行业分类）、"citics_2019"（中信行业分类） |
| date | Optional[string] | 否 | 查询日期，支持YYYYMMDD或YYYY-MM-DD；为空时使用今天；按in_date/out_date判断有效记录后，每只股票返回不晚于该日期的最大in_date记录 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| stock_symbol | string | 股票代码 |
| industry_code | string | 行业代码 |
| industry_name | string | 行业名称 |
| parent_code | string | 上级行业代码（仅对于l2返回） |
| parent_name | string | 上级行业名称（仅对于l2返回） |
| parent_l2_code | string | 上级二级行业代码（仅对于l3返回） |
| parent_l2_name | string | 上级二级行业名称（仅对于l3返回） |
| parent_l1_code | string | 上级一级行业代码（仅对于l3返回） |
| parent_l1_name | string | 上级一级行业名称（仅对于l3返回） |

示例：获取指定股票所属的申万行业信息

```python
import panda_data
result = panda_data.get_stock_industry(
            stock_symbol="000001.SZ",
            level="L1",
            date="20251231",
            reference="sws_2021"
)
print(result)
```

返回示例（前 3 行）：

| stock_symbol | industry_code | industry_name |
|:---|:---|:---|
| 000001.SZ | 801780 | 银行 |

## 指数基础数据

### get_index_weights：获取指数权重信息数据

数据范围 2017-01-03 ~ 至今；每日更新 22:31 ~ 22:51；[官方页面](https://www.pandaaiquant.com/docs/api?id=22)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| index_symbol | Optional[Union[string, List[string]]] | 否 | 指数代码 |
| stock_symbol | Optional[Union[string, List[string]]] | 否 | 成分股代码 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| index_symbol | string | 指数代码 |
| date | string | 日期 |
| stock_symbol | string | 股票代码 |
| weight | float | 权重 |

示例：获取某一指数的成分股在一定日期范围的权重

```python
import panda_data
result = panda_data.get_index_weights(
    index_symbol="000006.SH",
    stock_symbol="",
    start_date="20250101",
    end_date="20250131",
    fields=["index_symbol", "stock_symbol", "date"]
)
print(result)
```

返回示例（前 3 行）：

| index_symbol | date | stock_symbol |
|:---|:---|:---|
| 000006.SH | 20250102 | 600048.SH |
| 000006.SH | 20250102 | 600162.SH |
| 000006.SH | 20250102 | 600322.SH |

### get_index_indicator：获取指数估值指标数据

数据范围 2024-01-02 ~ 至今；每日更新 23:22 ~ 23:42；[官方页面](https://www.pandaaiquant.com/docs/api?id=21)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指数代码 |
| start_date | Optional[string] | 否 | 开始日期,eg:"20250702" |
| end_date | Optional[string] | 否 | 结束日期,eg:"20250702" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 指数代码 |
| pb_lf | float | 市净率(LF) |
| pb_lyr | float | 市净率(LYR) |
| pb_ttm | float | 市净率(TTM) |
| pe_lyr | float | 市盈率(LYR) |
| pe_ttm | float | 市盈率(TTM) |

示例：获取所有指数一段时间内的估值指标

```python
import panda_data
result = panda_data.get_index_indicator(
    symbol="",
    start_date="20250101",
    end_date="20250131",
    fields=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | pb_lf | pb_lyr | pb_ttm | pe_lyr | pe_ttm |
|:---|:---|:---|:---|:---|:---|:---|
| 000001.SH | 20250102 | 1.216579 | 1.27133 | 1.24007 | 14.457312 | 14.25168 |
| 000001.SH | 20250103 | 1.199433 | 1.253411 | 1.222593 | 14.251285 | 14.05139 |
| 000001.SH | 20250106 | 1.196401 | 1.250243 | 1.219502 | 14.215262 | 14.015872 |
