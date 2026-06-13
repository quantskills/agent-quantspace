---
source: https://www.pandaai.online/knowledge-base/?pageUrl=/coreFeatrue&id=%E4%BA%94%E6%95%B0%E6%8D%AEapi
title: PandaAI Data API - Minute Market Data
extracted: 2026-05-06
source_lines: 706-985
---

**2. 获取分钟级数据**

**2.1. 方法名：get_market_min_data**

**2.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| start_date | str | 开始日期,eg:"20250702" | 必填 |
| end_date | str | 结束日期,eg:"20250702" | 必填 |
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段 | 非必填 |
| symbol_type | Optional\[str\] | 产品类型，包含："stock" ,"future" ,"index" | 非必填 |
| time_zone | Optional\[tuple\] | 时间段过滤,格式为("HH:MM", "HH:MM")，例如("10:00", "23:00") | 非必填 |
| frequency | Optional\[str\] | 频率, 支持 "1m", "5m", "15m", "60m",默认为"1m"（指数仅支持1m） | 非必填 |

关于参数限制：每种类型的数据返回量以下表中的入参示例得到的数据量为上限，按照频率区分，调整参数时请相应地估计是否会超出限制

| 字段 | 频率1m | 频率5m | 频率15m | 频率60m |
|:---|:---|:---|:---|:---|
| start_date | 20250101 | 20250101 | 20250101 | 20210101 |
| end_date | 20250131 | 20250630 | 20260101 | 20251231 |
| symbol（stock类型共约5500支股票，index类型共约1150个指数，future类型共约860个期货） | None | None | None | None |
| time_zone（以实际覆盖交易时间段的比例计算，期货以全部symbol均含夜盘计算） | None | None | None | None |

**2.3. 响应参数**

股票:

| 字段       | 类型   | 描述               |
|:-----------|:-------|:-------------------|
| date       | str    | 日期               |
| minute     | str    | 时间（精确至分钟） |
| symbol     | str    | 股票代码           |
| name       | str    | 股票名称           |
| open       | double | 当日开盘价         |
| close      | double | 当日收盘价         |
| high       | double | 当日最高价         |
| low        | double | 当日最低价         |
| volume     | double | 当日成交量         |
| amount     | double | 当日成交额         |
| num_trades | double | 成交笔数           |

指数:

| 字段         | 类型   | 描述               |
|:-------------|:-------|:-------------------|
| symbol       | str    | 指数代码           |
| date         | str    | 日期               |
| minute       | str    | 时间（精确至分钟） |
| open         | double | 开盘价             |
| close        | double | 收盘价             |
| high         | double | 最高价             |
| low          | double | 最低价             |
| volume       | double | 成交量             |
| amount       | double | 成交额             |
| trading_date | str    | 交易日期           |

期货:

| 字段              | 类型   | 描述                                  |
|:------------------|:-------|:--------------------------------------|
| date              | str    | 日期                                  |
| minute            | str    | 时间（精确至分钟）                    |
| datetime          | str    | 日期和时间(格式为YYYY-MM-DD hh:mm:ss) |
| symbol            | str    | 期货代码                              |
| dominant_id       | str    | 主力合约代码                          |
| exchange          | str    | 交易所                                |
| trading_code      | str    | 交易代码                              |
| underlying_symbol | str    | 期货品种                              |
| trading_date      | str    | 交易日期                              |
| open              | double | 当日开盘价                            |
| close             | double | 当日收盘价                            |
| high              | double | 当日最高价                            |
| low               | double | 当日最低价                            |
| volume            | double | 当日成交量                            |
| open_interest     | double | 累计持仓量                            |
| amount            | double | 当日成交额                            |
| turnover          | double | 换手率                                |

**2.4. 使用示例**

**2.4.1. 获取单支股票的1分钟线数据并使用fields**

```python
import panda_data
result = panda_data.get_market_min_data(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250131",
    symbol_type="stock",
    fields=["symbol", "date", "num_trades", "amount", "volume"],
    frequency="1m",
    time_zone=("10:00", "11:00")
)
print(result)
```

**响应示例**

```text
symbol num_trades volume amount date minute
0 000001.SZ 95.0 193500.0 2221669.0 20250127 110000
1 000001.SZ 194.0 140400.0 1613212.0 20250127 105900
2 000001.SZ 364.0 338200.0 3886710.0 20250127 105800
3 000001.SZ 160.0 172658.0 1984536.0 20250127 105700
4 000001.SZ 400.0 285300.0 3278079.0 20250127 105600
... ... ... ... ... ... ...
1093 000001.SZ 464.0 927900.0 10830718.0 20250102 100400
1094 000001.SZ 242.0 500200.0 5841058.0 20250102 100300
1095 000001.SZ 729.0 1581800.0 18469542.0 20250102 100200
1096 000001.SZ 296.0 363902.0 4252891.0 20250102 100100
1097 000001.SZ 190.0 232100.0 2714037.0 20250102 100000
```

**2.4.2. 获取多支股票的15分钟线数据**

```python
import panda_data
result = panda_data.get_market_min_data(
    symbol=["000001.SZ","000002.SZ"],
    start_date="20250101",
    end_date="20250131",
    symbol_type="stock",
    fields=[],
    frequency="15m",
    time_zone=("10:00", "11:00")
)
print(result)
```

**响应示例**

```text
symbol close high low ... volume amount date minute
0 000001.SZ 11.49 11.50 11.48 ... 3156758.0 36284095.0 20250127 110000
1 000001.SZ 11.50 11.51 11.48 ... 3728400.0 42863418.0 20250127 104500
2 000001.SZ 11.48 11.51 11.48 ... 5857200.0 67340712.0 20250127 103000
3 000001.SZ 11.51 11.52 11.49 ... 5972082.0 68728285.0 20250127 101500
4 000001.SZ 11.50 11.52 11.48 ... 9531000.0 109656164.0 20250127 100000
.. ... ... ... ... ... ... ... ... ...
175 000002.SZ 7.27 7.28 7.25 ... 4502120.0 32724361.0 20250102 110000
176 000002.SZ 7.26 7.31 7.25 ... 8070200.0 58747814.0 20250102 104500
177 000002.SZ 7.31 7.32 7.30 ... 4246800.0 31031117.0 20250102 103000
178 000002.SZ 7.31 7.33 7.29 ... 6696700.0 48973297.0 20250102 101500
179 000002.SZ 7.29 7.36 7.29 ... 11701900.0 85782493.0 20250102 100000
```

**2.4.3. 获取单个指数的1分钟线数据并使用fields**

```python
import panda_data
result = panda_data.get_market_min_data(
    symbol="000001.SH",
    start_date="20250101",
    end_date="20250131",
    symbol_type="index",
    fields=["symbol", "date", "amount", "volume"],
    frequency="1m",
    time_zone=("10:00", "11:00")
)
print(result)
```

**响应示例**

```text
symbol amount volume date minute
0 000001.SH 9.364504e+08 78038400.0 20250127 110000
1 000001.SH 1.002671e+09 85079600.0 20250127 105900
2 000001.SH 1.084810e+09 95052300.0 20250127 105800
3 000001.SH 1.383025e+09 109437300.0 20250127 105700
4 000001.SH 1.576401e+09 162083900.0 20250127 105600
... ... ... ... ... ...
1093 000001.SH 4.029659e+09 364572800.0 20250102 100400
1094 000001.SH 3.241950e+09 273959000.0 20250102 100300
1095 000001.SH 3.287943e+09 266980600.0 20250102 100200
1096 000001.SH 3.650173e+09 341037500.0 20250102 100100
1097 000001.SH 3.121190e+09 285190800.0 20250102 100000
```

**2.4.4. 获取多个指数的1分钟线数据**

```python
import panda_data
result = panda_data.get_market_min_data(
    symbol=["000001.SH","000002.SH"],
    start_date="20250101",
    end_date="20250110",
    symbol_type="index",
    fields=[],
    frequency="1m",
    time_zone=("10:00", "11:00")
)
print(result)
```

**响应示例**

```text
symbol amount close ... volume date minute
0 000001.SH 1.246789e+09 3202.1239 ... 90331600.0 20250110 110000
1 000001.SH 1.591083e+09 3201.5813 ... 133511900.0 20250110 105900
2 000001.SH 1.201811e+09 3203.3221 ... 89499400.0 20250110 105800
3 000001.SH 1.246054e+09 3203.0991 ... 100101400.0 20250110 105700
4 000001.SH 1.566827e+09 3204.4015 ... 133112700.0 20250110 105600
.. ... ... ... ... ... ... ...
849 000002.SH 4.027991e+09 3483.7672 ... 364440700.0 20250102 100400
850 000002.SH 3.240003e+09 3487.5959 ... 273823500.0 20250102 100300
851 000002.SH 3.286036e+09 3490.9403 ... 266886000.0 20250102 100200
852 000002.SH 3.643868e+09 3491.3390 ... 340761000.0 20250102 100100
853 000002.SH 3.115685e+09 3492.2591 ... 284954000.0 20250102 100000
```

**2.4.5. 获取单个期货的1分钟线数据并使用fields**

```python
import panda_data
result = panda_data.get_market_min_data(
    symbol="A2501.DCE",
    start_date="20250101",
    end_date="20250131",
    symbol_type="future",
    fields=["symbol", "date", "amount", "volume"],
    frequency="1m",
    time_zone=("10:00", "11:00")
)
print(result)
```

**响应示例**

```text
symbol volume amount date minute
0 A2501.DCE 0.0 0.0 20250115 110000
1 A2501.DCE 0.0 0.0 20250115 105900
2 A2501.DCE 0.0 0.0 20250115 105800
3 A2501.DCE 0.0 0.0 20250115 105700
4 A2501.DCE 0.0 0.0 20250115 105600
.. ... ... ... ... ...
455 A2501.DCE 10.0 383000.0 20250102 100400
456 A2501.DCE 0.0 0.0 20250102 100300
457 A2501.DCE 5.0 191500.0 20250102 100200
458 A2501.DCE 0.0 0.0 20250102 100100
459 A2501.DCE 10.0 383000.0 20250102 100000
```

**2.4.6. 获取多个期货的15分钟线数据**

```python
import panda_data
result = panda_data.get_market_min_data(
    symbol=["A2501.DCE", "ZN_DOMINANT.SHF"],
    start_date="20250101",
    end_date="20250130",
    symbol_type="future",
    fields=[],
    frequency="15m",
    time_zone=("10:00", "11:00")
)
print(result)
```

**响应示例**

```text
symbol close dominant_id ... volume date minute
0 A2501.DCE 3880.0 A2501 ... 0.0 20250115 110000
1 A2501.DCE 3880.0 A2501 ... 0.0 20250115 104500
2 A2501.DCE 3880.0 A2501 ... 0.0 20250115 101500
3 A2501.DCE 3880.0 A2501 ... 0.0 20250115 100000
4 A2501.DCE 3821.0 A2501 ... 0.0 20250114 110000
.. ... ... ... ... ... ... ...
107 ZN_DOMINANT.SHF 24605.0 ZN2502 ... 6483.0 20250103 100000
108 ZN_DOMINANT.SHF 25265.0 ZN2502 ... 3201.0 20250102 110000
109 ZN_DOMINANT.SHF 25215.0 ZN2502 ... 5810.0 20250102 104500
110 ZN_DOMINANT.SHF 25205.0 ZN2502 ... 7043.0 20250102 101500
111 ZN_DOMINANT.SHF 25145.0 ZN2502 ... 11750.0 20250102 100000
```

