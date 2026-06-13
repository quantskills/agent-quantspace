---
source: https://www.pandaai.online/knowledge-base/?pageUrl=/coreFeatrue&id=%E4%BA%94%E6%95%B0%E6%8D%AEapi
title: PandaAI Data API - Stock and Index Reference
extracted: 2026-05-06
source_lines: 1223-1501
---

## 市场参考数据

**1. 获取股票基本信息**

**1.1. 方法名：get_stock_detail**

**1.2. 入参**

| **字段** | **类型** | **描述** | **是否必填** |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段 | 非必填 |
| market | Optional\[str\] | 市场，支持cn,hk,us，默认cn | 非必填 |
| status | Optional\[int\] | 是否在市，1 -在市，0 -退市，-1 -未知 | 非必填 |

**1.3. 响应参数**

| 字段             | 类型   | 描述                         |
|:-----------------|:-------|:-----------------------------|
| symbol           | str    | 股票代码                     |
| industry_code    | str    | 行业代码                     |
| market_tplus     | int    | 交易制度                     |
| name             | str    | 股票名称                     |
| special_type     | str    | 特别处理状态                 |
| exchange         | str    | 交易所                       |
| status           | int    | 股票状态                     |
| type             | str    | 产品类型                     |
| de_listed_date   | str    | 退市日期                     |
| listed_date      | str    | 上市日期                     |
| sector_code_name | str    | 以当地语言为标准的板块代码名 |
| abbrev_symbol    | str    | 股票的名称缩写               |
| sector_code      | str    | 板块缩写代码                 |
| min_order_amount | double | 一手对应多少股               |
| trading_hours    | str    | 产品最新交易时间             |
| board_type       | str    | 板块类别                     |
| industry_name    | str    | 国民经济行业分类名称         |
| issue_price      | double | 该证券发行价                 |
| trading_code     | str    | 交易代码                     |
| office_address   | str    | 公司地址                     |
| province         | str    | 省份                         |
| purchasedate     | str    | 申购日期                     |

**1.4. 使用示例**

**1.4.1. fields字段为空且status字段为空**

```python
import panda_data
result = panda_data.get_stock_detail(
    symbol=["000001.SZ","000002.SZ","000003.SZ"],
    market="cn",
    fields=[""],
    status=None
)
print(result)
```

```text
symbol abbrev_symbol ... trading_code trading_hours
0 000001.SZ PAYH ... 000001 09:31-11:30,13:01-15:00
1 000002.SZ WKA ... 000002 09:31-11:30,13:01-15:00
2 000003.SZ PTJTA ... 000003 09:31-11:30,13:01-15:00
```

**1.4.2. 指定fields且指定status字段**

```python
import panda_data
result = panda_data.get_stock_detail(
    symbol=["000001.SZ","000002.SZ","000003.SZ"],
    fields=["symbol", "name", "province", "office_address", "trading_code"],
    market="cn",
    status=1
)
print(result)
```

```text
symbol name ... status trading_code
0 000001.SZ 平安银行 ... 1 000001
1 000002.SZ 万科A ... 1 000002
```

**1.4.3. 港股**

```python
import panda_data
result = panda_data.get_stock_detail(
    symbol=["0001.HK","0002.HK","0003.HK"],
    market="hk",
    fields=[""],
    status=None
)
print(result)
```

```text
symbol abbrev_symbol ... status trading_code
0 0001.HK CKHUH ... 1 0001
1 0002.HK CLPHL ... 1 0002
2 0003.HK HKCNG ... 1 0003|864603
```

**1.4.4. 美股**

```python
import panda_data
result = panda_data.get_stock_detail(
    symbol=["0013.NB", "005490.NB", "ZYXIQ.NB"],
    market="us",
    fields=[""],
    status=None
)
print(result)
```

```text
symbol abbrev_symbol ... status trading_code
0 0013.NB None ... 1 None
1 005490.NB POSCO ... 1 893094
2 ZYXIQ.NB ZYXIQ ... 0 None
```

**1.4.5. 获取全部A股股票代码**

```python
import panda_data
result = panda_data.get_stock_detail(
    symbol="",
    fields=["symbol"],
    market="cn",
    status=None
)
print(result)
```

```text
symbol
0 000001.SZ
1 000002.SZ
2 000003.SZ
3 000004.SZ
4 000005.SZ
... ...
5512 688809.SH
5513 688819.SH
5514 688981.SH
5515 689009.SH
5516 990018.SH
```

**1.4.6. 获取全部港股股票代码**

```python
import panda_data
result = panda_data.get_stock_detail(
    symbol="",
    fields=["symbol"],
    market="hk",
    status=None
)
print(result)
```

```text
symbol
0 000002.SZ
1 000039.SZ
2 000063.SZ
3 0001.HK
4 000157.SZ
... ...
2916 XMUS.DE
2917 XNIF.DE
2918 YACHT.MI
2919 YAL.AX
2920 YUMC.K
```

**1.4.7. 获取全部美股股票代码**

```python
import panda_data
result = panda_data.get_stock_detail(
    symbol="",
    fields=["symbol"],
    market="us",
    status=None
)
print(result)
```

```text
symbol
0 0013.NB
1 005490.NB
2 015760.NB
3 017670.NB
4 01D7.NB
... ...
13408 ZXTY.NB
13409 ZYBT.NB
13410 ZYME.NB
13411 ZYRX.NB
13412 ZYXIQ.NB
```

**2. 获取指数基本信息**

**2.1. 方法名：get_index_detail**

**2.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 指数代码 | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |
| status | Optional\[str\] | 指数状态(1：正常交易，0：已退市，-1：暂无信息) | 非必填 |

**2.3.响应参数**

| 字段名           | 类型   | 描述         |
|:-----------------|:-------|:-------------|
| symbol           | str    | 指数代码     |
| abbrev_symbol    | str    | 指数简称     |
| de_listed_date   | str    | 退市日期     |
| listed_date      | str    | 上市日期     |
| market_tplus     | double | 交易制度     |
| min_order_amount | double | 最小交易单位 |
| name             | str    | 指数名称     |
| status           | int    | 指数状态     |
| trading_hours    | str    | 交易时间     |

**2.4. 使用示例**

**2.4.1. 获取所有指数基本信息**

```python
import panda_data
result = panda_data.get_index_detail(
    symbol="",
    status=None,
    fields=[]
)
print(result)
```

```text
symbol abbrev_symbol ... status trading_hours
0 000001.SH SZZS ... 1 09:31-11:30,13:01-15:00
1 000002.SH AGZS ... 1 09:31-11:30,13:01-15:00
2 000003.SH BGZS ... 1 09:31-11:30,13:01-15:00
3 000004.SH GYZS ... 1 09:31-11:30,13:01-15:00
4 000005.SH SYZS ... 1 09:31-11:30,13:01-15:00
... ... ... ... ... ...
1375 H50065.SH SHBK2 ... 1 09:31-11:30,13:01-15:00
1376 H50066.SH HGAHYJ ... 1 09:31-11:30,13:01-15:00
1377 H50067.SH 180ERC ... 1 09:31-11:30,13:01-15:00
1378 H50068.SH 380ERC ... 1 09:31-11:30,13:01-15:00
1379 H50069.SH GGT ... 1 09:31-11:30,13:01-15:00
```

**2.4.2. 获取单个指数基本信息并使用fields**

```python
import panda_data
result = panda_data.get_index_detail(
    symbol="000001.SH",
    status=1,
    fields=["symbol", "abbrev_symbol", "name", "trading_hours"]
)
print(result)
```

```text
symbol abbrev_symbol name status trading_hours
0 000001.SH SZZS 上证指数 1 09:31-11:30,13:01-15:00
```

