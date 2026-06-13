---
source: https://www.pandaai.online/knowledge-base/?pageUrl=/coreFeatrue&id=%E4%BA%94%E6%95%B0%E6%8D%AEapi
title: PandaAI Data API - Concept, Industry, Index Indicators, and Weights
extracted: 2026-05-06
source_lines: 1502-1986
---

**3. 获取概念列表**

**3.1. 方法名：get_concept_list**

**3.2. 入参**

| 字段       | 类型                                  | 描述     | 是否必填 |
|:-----------|:--------------------------------------|:---------|:---------|
| concept    | Optional\[Union\[str, List\[str\]\]\] | 概念名称 | 非必填   |
| start_date | Optional\[str\]                       | 开始时间 | 非必填   |
| end_date   | Optional\[str\]                       | 结束时间 | 非必填   |

**3.3. 响应参数**

| 字段 | 类型 | 描述         |
|:-----|:-----|:-------------|
| name | str  | 概念名称     |
| date | str  | 概念纳入日期 |

**3.4. 使用示例**

**3.4.1. 获取一定日期内某个概念的列表**

```python
import panda_data
result = panda_data.get_concept_list(
    start_date="20250101",
    end_date="20250131",
    concept="英伟达概念"
)
print(result)
```

```text
name date
0 英伟达概念 20250117
```

**4. 获取概念成分股**

**4.1. 方法名：get_concept_constituents**

**4.2. 入参**

| 字段          | 类型                                  | 描述     | 是否必填 |
|:--------------|:--------------------------------------|:---------|:---------|
| concept       | Optional\[Union\[str, List\[str\]\]\] | 概念名称 | 非必填   |
| concept_stock | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填   |
| start_date    | Optional\[str\]                       | 开始时间 | 非必填   |
| end_date      | Optional\[str\]                       | 结束时间 | 非必填   |
| fields        | Optional\[Union\[str, List\[str\]\]\] | 返回字段 | 非必填   |

**4.3. 响应参数**

| 字段          | 类型 | 描述             |
|:--------------|:-----|:-----------------|
| concept       | str  | 概念名称         |
| concept_stock | str  | 概念成分股       |
| date          | str  | 股票纳入概念日期 |

**4.4. 使用示例**

**4.4.1. 获取一定日期内某个概念成分股**

```python
import panda_data
result = panda_data.get_concept_constituents(
    start_date="20250101",
    end_date="20250131",
    concept="英伟达概念",
    concept_stock="001339.SZ",
    fields=["concept", "concept_stock", "date"]
)
print(result)
```

```text
concept_stock date concept
0 001339.SZ 20250117 英伟达概念
```

**5. 获取行业基本信息数据**

**5.1. 方法名：get_industry_detail**

**5.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |
| level | Optional\[Union\[str, List\[str\]\]\] | 行业级别，可选值："L1"(一级)、"L2"(二级)、"L3"(三级) | 非必填 |

**5.3. 响应参数**

| 字段名        | 类型 | 描述         |
|:--------------|:-----|:-------------|
| symbol        | str  | 指数代码     |
| industry_code | str  | 行业代码     |
| industry_name | str  | 行业名称     |
| level         | str  | 行业级别     |
| parent_code   | str  | 上级行业代码 |

**5.4. 使用示例**

**5.4.1. 获取所有行业基本信息（一级）**

```python
import panda_data
result = panda_data.get_industry_detail(
    level="L1",
    fields=[]
)
print(result)
```

```text
symbol industry_code industry_name level parent_code
0 801010 110000 农林牧渔 L1 0
1 801030 220000 基础化工 L1 0
2 801040 230000 钢铁 L1 0
3 801050 240000 有色金属 L1 0
4 801080 270000 电子 L1 0
5 801880 280000 汽车 L1 0
6 801110 330000 家用电器 L1 0
7 801120 340000 食品饮料 L1 0
8 801130 350000 纺织服饰 L1 0
9 801140 360000 轻工制造 L1 0
10 801150 370000 医药生物 L1 0
11 801160 410000 公用事业 L1 0
12 801170 420000 交通运输 L1 0
13 801180 430000 房地产 L1 0
14 801200 450000 商贸零售 L1 0
15 801210 460000 社会服务 L1 0
16 801780 480000 银行 L1 0
17 801790 490000 非银金融 L1 0
18 801230 510000 综合 L1 0
19 801710 610000 建筑材料 L1 0
20 801720 620000 建筑装饰 L1 0
21 801730 630000 电力设备 L1 0
22 801890 640000 机械设备 L1 0
23 801740 650000 国防军工 L1 0
24 801750 710000 计算机 L1 0
25 801760 720000 传媒 L1 0
26 801770 730000 通信 L1 0
27 801950 740000 煤炭 L1 0
28 801960 750000 石油石化 L1 0
29 801970 760000 环保 L1 0
30 801980 770000 美容护理 L1 0
```

**5.4.2. 获取所有行业基本信息且使用fields （一级）**

```python
import panda_data
result = panda_data.get_industry_detail(
    level="L1",
    fields=["industry_name"]
)
print(result)
```

```text
industry_name
0 农林牧渔
1 基础化工
2 钢铁
3 有色金属
4 电子
5 家用电器
6 食品饮料
7 纺织服饰
8 轻工制造
9 医药生物
10 公用事业
11 交通运输
12 房地产
13 商贸零售
14 社会服务
15 综合
16 建筑材料
17 建筑装饰
18 电力设备
19 国防军工
20 计算机
21 传媒
22 通信
23 银行
24 非银金融
25 汽车
26 机械设备
27 煤炭
28 石油石化
29 环保
30 美容护理
```

**6. 获取行业成分股数据**

**6.1. 方法名：get_industry_constituents**

**6.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| industry_code | Optional\[Union\[str, List\[str\]\]\] | 行业代码，如"801010" | 非必填 |
| stock_symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码，如"000001.SZ" | 非必填 |
| level | Optional\[str\] | 行业级别，可选值："L1"(一级)、"L2"(二级)、"L3"(三级) | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |

**6.3. 响应参数**

| 字段名       | 类型 | 描述         |
|:-------------|:-----|:-------------|
| stock_symbol | str  | 股票代码     |
| l1_code      | str  | 一级行业代码 |
| l2_code      | str  | 二级行业代码 |
| l3_code      | str  | 三级行业代码 |
| in_date      | str  | 纳入时间     |
| l1_name      | str  | 一级行业名称 |
| l2_name      | str  | 二级行业名称 |
| l3_name      | str  | 三级行业名称 |
| out_date     | str  | 剔除时间     |
| stock_name   | str  | 股票名称     |

**6.4. 使用示例**

**6.4.1. 获取某个行业的成分股数据**

```python
import panda_data
result = panda_data.get_industry_constituents(
    industry_code="801780",
    stock_symbol="000001.SZ",
    level="L1",
    fields=[]
)
print(result)
```

```text
l1_code l2_code stock_symbol l3_code ... l2_name l3_name out_date stock_name
0 801780 801783 000001.SZ 857831 ... 股份制银行Ⅱ 股份制银行Ⅲ None 平安银行
```

**6.4.2. 获取某个行业的成分股数据且使用fields**

```python
import panda_data
result = panda_data.get_industry_constituents(
    industry_code="801780",
    stock_symbol="000001.SZ",
    level="L1",
    fields=["stock_symbol", "industry_code", "l1_code", "stock_name"]
)
print(result)
```

```text
l1_code stock_symbol stock_name
0 801780 000001.SZ 平安银行
```

**7. 获取指定股票所属的行业信息**

**7.1. 方法名：get_stock_industry**

**7.2. 入参**

| **字段** | **类型** | **描述** | **是否必填** |
|:---|:---|:---|:---|
| stock_symbol | str | 股票代码，如"000001.SZ" | 必填 |
| level | Optional\[str\] | 行业级别，可选值："L1"(一级)、"L2"(二级)、"L3"(三级) | 非必填 |

**7.3. 响应参数**

| **字段**       | **类型** | **描述**     |
|:---------------|:---------|:-------------|
| stock_symbol   | str      | 股票代码     |
| industry_code  | str      | 行业代码     |
| industry_name  | str      | 行业名称     |
| parent_code    | str      | 上级行业代码 |
| parent_name    | str      | 上级行业名称 |
| parent_l1_code | str      | 一级行业名称 |
| parent_l1_name | str      | 一级行业名称 |
| parent_l2_code | str      | 二级行业名称 |
| parent_l2_name | str      | 二级行业名称 |

**7.4. 使用示例**

**7.4.1. 获取指定股票所属的行业信息**

```python
import panda_data
result = panda_data.get_stock_industry(
    stock_symbol="000001.SZ",
    level="L1"
)
print(result)
```

```text
stock_symbol industry_code industry_name
0 000001.SZ 801780 银行
```

**8. 获取指数估值指标**

**8.1. 方法名：get_index_indicator**

**8.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 指数代码 | 非必填 |
| start_date | Optional\[str\] | 开始日期,eg:"20250702" | 非必填 |
| end_date | Optional\[str\] | 结束日期,eg:"20250702" | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |

**8.3. 响应参数**

| 字段名 | 类型   | 描述        |
|:-------|:-------|:------------|
| date   | str    | 日期        |
| symbol | str    | 指数代码    |
| pb_lf  | double | 市净率(LF)  |
| pb_lyr | double | 市净率(LYR) |
| pb_ttm | double | 市净率(TTM) |
| pe_lyr | double | 市盈率(LYR) |
| pe_ttm | double | 市盈率(TTM) |

**8.4. 使用示例**

**8.4.1. 获取所有指数一段时间内的估值指标**

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

```text
date symbol pb_lf pb_lyr pb_ttm pe_lyr pe_ttm
0 20250127 000001.SH 1.212212 1.266905 1.235656 14.403007 14.201434
1 20250124 000001.SH 1.210876 1.265509 1.234295 14.387140 14.185789
2 20250123 000001.SH 1.204265 1.258580 1.227551 14.308799 14.108210
3 20250122 000001.SH 1.196207 1.250158 1.219337 14.213050 14.013804
4 20250121 000001.SH 1.206637 1.261058 1.229969 14.336975 14.135992
... ... ... ... ... ... ... ...
2173 20250108 H30318.SH 4.288753 4.423812 4.350295 65.563513 52.513664
2174 20250107 H30318.SH 4.310324 4.446062 4.372176 65.893282 52.777795
2175 20250106 H30318.SH 4.136498 4.266762 4.195856 63.235948 50.649381
2176 20250103 H30318.SH 4.161322 4.292368 4.221036 63.615437 50.953336
2177 20250102 H30318.SH 4.256468 4.390510 4.317547 65.069969 52.118355
```

**8.4.2. 获取单个指数一段时间内的估值指标并使用fields**

```python
import panda_data
result = panda_data.get_index_indicator(
    symbol="000001.SH",
    start_date="20250101",
    end_date="20250131",
    fields=["symbol", "date", "pb_lf", "pb_lyr"]
)
print(result)
```

```text
date symbol pb_lf pb_lyr
0 20250127 000001.SH 1.212212 1.266905
1 20250124 000001.SH 1.210876 1.265509
2 20250123 000001.SH 1.204265 1.258580
3 20250122 000001.SH 1.196207 1.250158
4 20250121 000001.SH 1.206637 1.261058
5 20250120 000001.SH 1.208519 1.263025
6 20250117 000001.SH 1.209137 1.263617
7 20250116 000001.SH 1.207780 1.262187
8 20250115 000001.SH 1.203056 1.257250
9 20250114 000001.SH 1.207666 1.262068
10 20250113 000001.SH 1.180195 1.233359
11 20250110 000001.SH 1.183430 1.236716
12 20250109 000001.SH 1.199218 1.253187
13 20250108 000001.SH 1.207044 1.261365
14 20250107 000001.SH 1.205343 1.259588
15 20250106 000001.SH 1.196401 1.250243
16 20250103 000001.SH 1.199433 1.253411
17 20250102 000001.SH 1.216579 1.271330
```

**9. 获取指数权重信息**

**9.1. 方法名：get_index_weights**

**9.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| index_symbol | Optional\[Union\[str, List\[str\]\]\] | 指数代码 | 非必填 |
| stock_symbol | Optional\[Union\[str, List\[str\]\]\] | 成分股代码 | 非必填 |
| start_date | str | 开始日期,eg:"20250702" | 必填 |
| end_date | str | 结束日期,eg:"20250702" | 必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |

**9.3. 响应参数**

| 字段名       | 类型   | 描述     |
|:-------------|:-------|:---------|
| index_symbol | str    | 指数代码 |
| date         | str    | 日期     |
| stock_symbol | str    | 股票代码 |
| weight       | double | 权重     |

**9.4. 使用示例**

**9.4.1. 获取某一指数的成分股在一定日期范围的权重**

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

```text
index_symbol date stock_symbol
0 000006.SH 20250127 600048.SH
1 000006.SH 20250124 600048.SH
2 000006.SH 20250123 600048.SH
3 000006.SH 20250122 600048.SH
4 000006.SH 20250121 600048.SH
.. ... ... ...
355 000006.SH 20250108 603506.SH
356 000006.SH 20250107 603506.SH
357 000006.SH 20250106 603506.SH
358 000006.SH 20250103 603506.SH
359 000006.SH 20250102 603506.SH
```

**9.4.2. 获取某一指数的单个成分股在一定日期范围的权重**

```python
import panda_data
result = panda_data.get_index_weights(
    index_symbol="000006.SH",
    stock_symbol="600048.SH",
    start_date="20250101",
    end_date="20250131",
    fields=["index_symbol", "stock_symbol", "date"]
)
print(result)
```

```text
index_symbol date stock_symbol
0 000006.SH 20250127 600048.SH
1 000006.SH 20250124 600048.SH
2 000006.SH 20250123 600048.SH
3 000006.SH 20250122 600048.SH
4 000006.SH 20250121 600048.SH
5 000006.SH 20250120 600048.SH
6 000006.SH 20250117 600048.SH
7 000006.SH 20250116 600048.SH
8 000006.SH 20250115 600048.SH
9 000006.SH 20250114 600048.SH
10 000006.SH 20250113 600048.SH
11 000006.SH 20250110 600048.SH
12 000006.SH 20250109 600048.SH
13 000006.SH 20250108 600048.SH
14 000006.SH 20250107 600048.SH
15 000006.SH 20250106 600048.SH
16 000006.SH 20250103 600048.SH
17 000006.SH 20250102 600048.SH
```

