---
source: https://www.pandaai.online/knowledge-base/?pageUrl=/coreFeatrue&id=%E4%BA%94%E6%95%B0%E6%8D%AEapi
title: PandaAI Data API - Trading Calendar and Trading Tools
extracted: 2026-05-06
source_lines: 4221-4565
---

## 交易工具

**1. 获取交易日历**

**1.1. 方法名：get_trade_cal**

**1.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| start_date | Optional\[str\] | 开始日期，格式为 YYYYMMDD | 非必填 |
| end_date | Optional\[str\] | 结束日期，格式为 YYYYMMDD | 非必填 |
| exchange | Optional\[str\] | 交易所代码，默认为 "SH"，目前支持"SH"，"HK"和"US" | 非必填 |
| is_trading_day | Optional\[int\] | 是否为交易日，1=交易日，0=非交易日，None=全部 | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 需要返回的字段列表 | 非必填 |

**1.3. 响应参数**

| 字段            | 类型 | 描述                                     |
|:----------------|:-----|:-----------------------------------------|
| nature_date     | int  | 日期，格式为YYYYMMDD                     |
| exchange        | str  | 交易所代码                               |
| is_trade        | int  | 是否为交易日，1表示交易日，0表示非交易日 |
| pretrade_date   | str  | 当前日期前一个交易日                     |
| next_trade_date | str  | 当前日期后一个交易日                     |

**1.4. 使用示例**

**1.4.1. 获取一段时间内上交所交易日历**

```python
import panda_data
result = panda_data.get_trade_cal(
    start_date="20250101",
    end_date="20250115",
    exchange="SH",
    is_trading_day=None,
    fields=[]
)
print(result)
```

```text
exchange is_trade nature_date pretrade_date next_trade_date
0 SH 0 20250101 20241231 20250102
1 SH 1 20250102 20241231 20250103
2 SH 1 20250103 20250102 20250106
3 SH 0 20250104 20250103 20250106
4 SH 0 20250105 20250103 20250106
5 SH 1 20250106 20250103 20250107
6 SH 1 20250107 20250106 20250108
7 SH 1 20250108 20250107 20250109
8 SH 1 20250109 20250108 20250110
9 SH 1 20250110 20250109 20250113
10 SH 0 20250111 20250110 20250113
11 SH 0 20250112 20250110 20250113
12 SH 1 20250113 20250110 20250114
13 SH 1 20250114 20250113 20250115
14 SH 1 20250115 20250114 20250116
```

**1.4.2. 获取一段时间内港交所非交易日且使用fields**

```python
import panda_data
result = panda_data.get_trade_cal(
    start_date="20241215",
    end_date="20250110",
    exchange="HK",
    is_trading_day=1,
    fields=["nature_date", "is_trade", "next_trade_date", "pretrade_date"]
)
print(result)
```

```text
nature_date is_trade next_trade_date pretrade_date
0 20241216 1 20241217 20241213
1 20241217 1 20241218 20241216
2 20241218 1 20241219 20241217
3 20241219 1 20241220 20241218
4 20241220 1 20241223 20241219
5 20241223 1 20241224 20241220
6 20241224 1 20241227 20241223
7 20241227 1 20241230 20241224
8 20241230 1 20241231 20241227
9 20241231 1 20250102 20241230
10 20250102 1 20250103 20241231
11 20250103 1 20250106 20250102
12 20250106 1 20250107 20250103
13 20250107 1 20250108 20250106
14 20250108 1 20250109 20250107
15 20250109 1 20250110 20250108
16 20250110 1 20250113 20250109
```

**1.4.3. 获取一段时间内上交所交易日**

```python
import panda_data
result = panda_data.get_trade_cal(
    start_date="20250101",
    end_date="20250120",
    exchange="SH",
    is_trading_day=1,
    fields=[]
)
print(result)
```

```text
exchange is_trade nature_date pretrade_date next_trade_date
0 SH 1 20250102 20241231 20250103
1 SH 1 20250103 20250102 20250106
2 SH 1 20250106 20250103 20250107
3 SH 1 20250107 20250106 20250108
4 SH 1 20250108 20250107 20250109
5 SH 1 20250109 20250108 20250110
6 SH 1 20250110 20250109 20250113
7 SH 1 20250113 20250110 20250114
8 SH 1 20250114 20250113 20250115
9 SH 1 20250115 20250114 20250116
10 SH 1 20250116 20250115 20250117
11 SH 1 20250117 20250116 20250120
12 SH 1 20250120 20250117 20250121
```

**2. 获取某一日期前第n个交易日**

**2.1. 方法名：get_prev_trade_date**

**2.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| date | str | 基准日期，格式为 "YYYYMMDD" | 必填 |
| exchange | Optional\[str\] | 交易所代码，默认为 "SH"，目前支持"SH"，"HK"和"US" | 非必填 |
| n | Optional\[int\] | 前第n个交易日，默认为1 | 非必填 |

**2.3. 响应参数**

| 字段 | 类型 | 描述                                               |
|:-----|:-----|:---------------------------------------------------|
| date | str  | 第前n个交易日，格式 "YYYYMMDD"，如果没有则返回None |

**2.4. 使用示例**

**2.4.1. 获取上交所某一日期的前第5个交易日**

```python
import panda_data
result = panda_data.get_prev_trade_date(
    date="20250102",
    exchange="SH",
    n=5
)
print(result)
```

```text
20241225
```

**2.4.2. 获取港交所某一日期的前第5个交易日**

```python
import panda_data
result = panda_data.get_prev_trade_date(
    date="20250102",
    exchange="HK",
    n=5
)
print(result)
```

```text
20241223
```

**3. 获取最新交易日**

**3.1. 方法名：get_last_trade_date**

**3.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| exchange | Optional\[str\] | 交易所代码，默认为 "SH"，目前支持"SH"，"HK"和"US" | 非必填 |

**3.3. 响应参数**

| 字段 | 类型 | 描述                                            |
|:-----|:-----|:------------------------------------------------|
| date | str  | 最新交易日，格式 "YYYYMMDD"，如果没有则返回None |

**3.4. 使用示例**

**3.4.1. 获取上交所最新交易日**

```python
import panda_data
result = panda_data.get_last_trade_date(
    exchange="SH"
)
print(result)
```

```text
20251223
```

**3.4.2. 获取港交所最新交易日**

```python
import panda_data
result = panda_data.get_last_trade_date(
    exchange="HK"
)
print(result)
```

```text
20251223
```

**4. 获取合约特殊处理数据**

**4.1. 方法名：get_stock_status_change**

**4.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_date | Optional\[str\] | 开始日期,eg:"20250702" | 非必填 |
| end_date | Optional\[str\] | 结束日期,eg:"20250702" | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |

**4.3. 响应参数**

| 字段        | 类型 | 描述                       |
|:------------|:-----|:---------------------------|
| symbol      | str  | 股票代码                   |
| date        | str  | 信息发布日期               |
| change_date | str  | 特别处理（或撤销）实施日期 |
| description | str  | 特别处理（或撤销）事项描述 |
| name        | str  | 股票名称                   |
| type        | str  | 特别处理（或撤销）类别     |

**4.4. 使用示例**

**4.4.1. 获取一定日期内某只股票合约特殊处理数据**

```python
import panda_data
result = panda_data.get_stock_status_change(
    symbol="002217.SZ",
    start_date="20250101",
    end_date="20250131",
    fields=[]
)
print(result)
```

```text
date change_date symbol ... name type info_date
0 20250107 20250106 002217.SZ ... *ST合泰 撤销叠加*ST 20250107
```

**4.4.2. 获取一定日期内全部股票合约特殊处理数据并使用fields**

```python
import panda_data
result = panda_data.get_stock_status_change(
    symbol="",
    start_date="20250101",
    end_date="20250131",
    fields=["symbol", "date", "change_date", "name", "type"]
)
print(result)
```

```text
date change_date symbol name type
0 20250107 20250106 002217.SZ *ST合泰 撤销叠加*ST
1 20250109 20250109 002309.SZ *ST中利 撤销叠加*ST
2 20250103 20250102 002310.SZ *ST东园 撤销叠加*ST
3 20250111 20250114 002656.SZ *ST摩登 从ST变为*ST
4 20250110 20250110 300209.SZ *ST有树 撤销叠加*ST
5 20250110 20250113 300301.SZ *ST长方 叠加ST
6 20250105 20250107 300630.SZ *ST普利 *ST
7 20250123 20250207 600225.SH 退市卓朗 退市整理期
8 20250111 20250114 600289.SH *ST信通 叠加*ST
9 20250125 20250127 600360.SH ST华微 叠加ST
10 20250108 20250107 600375.SH *ST汉马 撤销叠加*ST
11 20250107 20250106 600715.SH *ST文投 撤销叠加*ST
12 20250113 20250114 603007.SH ST花王 撤消*ST并实行ST
13 20250109 20250108 603363.SH *ST傲农 撤销叠加*ST
14 20250109 20250108 603559.SH *ST通脉 撤销叠加*ST
```

**5. 获取指定日期的在售股票列表**

**5.1. 方法名：get_trade_list**

**5.2. 入参**

| 字段 | 类型                      | 描述               | 是否必填 |
|:-----|:--------------------------|:-------------------|:---------|
| date | Union\[str, List\[str\]\] | 日期,eg:"20250702" | 必填     |

**5.3. 响应参数**

| 字段   | 类型 | 描述     |
|:-------|:-----|:---------|
| symbol | str  | 股票代码 |
| date   | str  | 日期     |

**5.4. 使用示例**

**5.4.1. 获取指定日期的在售股票列表**

```python
import panda_data
result = panda_data.get_trade_list(
    date="20251211"
)
print(result)
```

```text
date symbol
0 20251211 000001.SZ
1 20251211 000002.SZ
2 20251211 000004.SZ
3 20251211 000006.SZ
4 20251211 000007.SZ
... ... ...
5151 20251211 688799.SH
5152 20251211 688800.SH
5153 20251211 688819.SH
5154 20251211 688981.SH
5155 20251211 689009.SH
```

