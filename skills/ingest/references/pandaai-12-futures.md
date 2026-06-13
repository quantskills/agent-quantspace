---
source: https://www.pandaai.online/knowledge-base/?pageUrl=/coreFeatrue&id=%E4%BA%94%E6%95%B0%E6%8D%AEapi
title: PandaAI Data API - Futures Reference and Data
extracted: 2026-05-06
source_lines: 4566-4782
---

## 期货

**1. 获取期货基本信息**

**1.1. 方法名：get_future_detail**

**1.2. 入参**

| 字段       | 类型                                  | 描述         | 是否必填 |
|:-----------|:--------------------------------------|:-------------|:---------|
| symbol     | Optional\[Union\[str, List\[str\]\]\] | 期货代码     | 非必填   |
| fields     | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填   |
| is_trading | Optional\[int\]                       | 是否可交易   | 非必填   |

**1.3. 响应参数**

| 字段 | 类型 | 描述 |
|:---|:---|:---|
| symbol | str | 期货代码 |
| listed_date | str | 上市日期 |
| de_listed_date | str | 退市日期 |
| maturity_date | str | 到期日期 |
| start_delivery_date | str | 开始交割日期 |
| end_delivery_date | str | 结束交割日期 |
| contract_multiplier | double | 合约乘数 |
| exchange | str | 交易所 |
| industry_name | str | 行业分类名称 |
| margin_rate | double | 最低保证金率 |
| market_tplus | double | 交易制度，0表示T+0，以此类推 |
| name | str | 合约简称 |
| product | str | 合约种类，Commodity对应商品期货，Index对应股指期货，Government对应国债期货 |
| round_lot | double | 合约单位，均为1.0 |
| trading_code | str | 交易代码 |
| trading_hours | str | 交易时间 |
| type | str | 合约类型,均为Future |
| underlying_symbol | str | 合约标的名称 |
| is_trading | int | 是否可交易，1表示可交易，0表示不可交易 |

**1.4. 使用示例**

**1.4.1. 获取某些期货的基本信息**

```python
import panda_data
result = panda_data.get_future_detail(
    symbol=["A0303.DCE", "ZN_DOMINANT.SHF"],
    fields=[],
    is_trading=None
)
print(result)
```

```text
symbol contract_multiplier ... underlying_symbol is_trading
0 A0303.DCE 10.0 ... A 0
1 ZN_DOMINANT.SHF 5.0 ... ZN 1
```

**1.4.2. 获取一些期货中在交易的期货的基本信息且使用fields**

```python
import panda_data
result = panda_data.get_future_detail(
    symbol=["A0303.DCE","ZN_DOMINANT.SHF","AO_DOMINANT.SHF"],
    fields=["symbol", "listed_date", "contract_multiplier","product"],
    is_trading= 1
)
print(result)
```

```text
symbol contract_multiplier listed_date product is_trading
0 AO_DOMINANT.SHF 20.0 0000-00-00 Commodity 1
1 ZN_DOMINANT.SHF 5.0 0000-00-00 Commodity 1
```

**2. 获取期货后复权数据**

**2.1. 方法名：get_future_market_post**

**2.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 期货代码 | 非必填 |
| start_date | str | 开始日期,eg:"20250702" （查询上市日期） | 必填 |
| end_date | str | 结束日期,eg:"20250702" （查询上市日期） | 必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |

**2.3. 响应参数**

| 字段              | 类型   | 描述         |
|:------------------|:-------|:-------------|
| symbol            | str    | 期货代码     |
| date              | str    | 日期         |
| amount            | double | 成交额       |
| close             | double | 收盘价       |
| day_session_open  | double | 日盘开盘价   |
| dominant_id       | str    | 主力合约代码 |
| exchange          | str    | 交易所       |
| high              | double | 最高价       |
| limit_down        | double | 跌停价       |
| limit_up          | double | 涨停价       |
| low               | double | 最低价       |
| open              | double | 开盘价       |
| open_interest     | double | 累计持仓量   |
| pre_settlement    | double | 昨日结算价   |
| settlement        | double | 结算价       |
| trading_code      | str    | 交易代码     |
| underlying_symbol | str    | 合约标的代码 |
| volume            | double | 成交量       |

**2.4. 使用示例**

**2.4.1. 获取一定日期内某些期货的后复权数据**

```python
import panda_data
result = panda_data.get_future_market_post(
    symbol=["A2511.DCE", "P2607.DCE","A_DOMINANT.DCE"],
    start_date="20251101",
    end_date="20251105",
    fields=[]
)
print(result)
```

```text
date symbol close ... volume pre_settlement amount
0 20251105 A2511.DCE 4048.0 ... 12.0 4053.0 4.861100e+05
1 20251104 A2511.DCE 4044.0 ... 351.0 4090.0 1.422784e+07
2 20251103 A2511.DCE 4076.0 ... 75.0 4082.0 3.067820e+06
3 20251105 A_DOMINANT.DCE 4123.0 ... 217199.0 4076.0 8.857064e+09
4 20251104 A_DOMINANT.DCE 4055.0 ... 135914.0 4092.0 5.539860e+09
5 20251103 A_DOMINANT.DCE 4076.0 ... 155379.0 4095.0 6.358720e+09
6 20251105 P2607.DCE 8650.0 ... 36.0 8686.0 3.120200e+06
7 20251104 P2607.DCE 8644.0 ... 41.0 8670.0 3.561680e+06
8 20251103 P2607.DCE 8658.0 ... 32.0 8738.0 2.774500e+06
```

**2.4.2. 获取一定日期内某些期货的后复权数据且使用fields**

```python
import panda_data
result = panda_data.get_future_market_post(
    symbol=["A2511.DCE","P2607.DCE"],
    start_date="20251101",
    end_date="20251105",
    fields=["symbol", "amount", "close","high"],
)
print(result)
```

```text
date symbol close high amount
0 20251105 A2511.DCE 4048.0 4052.0 486110.0
1 20251104 A2511.DCE 4044.0 4084.0 14227840.0
2 20251103 A2511.DCE 4076.0 4098.0 3067820.0
3 20251105 P2607.DCE 8650.0 8692.0 3120200.0
4 20251104 P2607.DCE 8644.0 8732.0 3561680.0
5 20251103 P2607.DCE 8658.0 8712.0 2774500.0
```

**3. 获取期货主力合约数据**

**3.1. 方法名：get_future_dominant**

**3.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| underlying_symbol | Optional\[Union\[str, List\[str\]\]\] | 期货品种 | 非必填 |
| start_date | str | 开始日期,eg:"20250702" | 必填 |
| end_date | str | 结束日期,eg:"20250802" | 必填 |

**3.3. 响应参数**

| 字段              | 类型 | 描述                 |
|:------------------|:-----|:---------------------|
| date              | str  | 日期                 |
| underlying_symbol | str  | 期货品种             |
| symbol            | str  | 主力合约代码         |
| symbol_code       | str  | 主力合约期货代码     |
| trading_code      | str  | 主力合约期货交易代码 |

**3.4. 使用示例**

**3.4.1. 获取一定日期内某些品种的主力合约**

```python
import panda_data
result = panda_data.get_future_dominant(
    underlying_symbol=["A","AG"],
    start_date="20250701",
    end_date="20250710"
)
print(result)
```

```text
underlying_symbol date symbol trading_code
0 A 20250701 A2509.DCE a2509
1 A 20250702 A2509.DCE a2509
2 A 20250703 A2509.DCE a2509
3 A 20250704 A2509.DCE a2509
4 A 20250707 A2509.DCE a2509
5 A 20250708 A2509.DCE a2509
6 A 20250709 A2509.DCE a2509
7 A 20250710 A2509.DCE a2509
8 AG 20250701 AG2508.SHF ag2508
9 AG 20250702 AG2508.SHF ag2508
10 AG 20250703 AG2508.SHF ag2508
11 AG 20250704 AG2508.SHF ag2508
12 AG 20250707 AG2510.SHF ag2510
13 AG 20250708 AG2510.SHF ag2510
14 AG 20250709 AG2510.SHF ag2510
15 AG 20250710 AG2510.SHF ag2510
