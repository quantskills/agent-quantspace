---
source: https://www.pandaai.online/knowledge-base/?pageUrl=/coreFeatrue&id=%E4%BA%94%E6%95%B0%E6%8D%AEapi
title: PandaAI Data API - Investor Activity, Restrictions, Holders, Blocks, and Share Float
extracted: 2026-05-06
source_lines: 2479-2937
---

**15. 获取A股合约投资者关系活动**

**15.1. 方法名：get_investor_activity**

**15.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_date | str | 开始日期,eg:"20250702" | 必填 |
| end_date | str | 结束日期,eg:"20250702" | 必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |

**15.3. 响应参数**

| 字段                       | 类型 | 描述         |
|:---------------------------|:-----|:-------------|
| date                       | str  | 公告发布日   |
| symbol                     | str  | 股票代码     |
| participant                | str  | 参与人员     |
| investor_or_analyst_detail | str  | 与会人员详情 |
| institute                  | str  | 参与机构     |

**15.4. 使用示例**

**15.4.1. 获取一定日期内某只股票合约投资者关系活动数据**

```python
import panda_data
result = panda_data.get_investor_activity(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250131",
    fields=[]
)
print(result)
```

```text
participant institute investor_or_analyst_detail symbol date
0 None None 境内投资者 000001.SZ 20250117
```

**15.4.2. 获取一定日期内某只股票合约投资者关系活动数据且使用fields**

```python
import panda_data
result = panda_data.get_investor_activity(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250131",
    fields=["symbol", "date", "participant", "investor_or_analyst_detail"]
)
print(result)
```

```text
participant investor_or_analyst_detail symbol date
0 None 境内投资者 000001.SZ 20250117
```

**16. 获取股票限售解禁明细数据**

**16.1. 方法名：get_restricted_list**

**16.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_date | str | 开始日期,eg:"20250702" | 非必填 |
| end_date | str | 结束日期,eg:"20250702" | 必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |
| market | Optional\[str\] | 市场,默认'cn'为中国内地市场 | 非必填 |

**16.3. 响应参数**

| 字段                  | 类型   | 描述                 |
|:----------------------|:-------|:---------------------|
| symbol                | str    | 合约代码             |
| date                  | str    | 限售解禁信息发布日期 |
| relieve_date          | str    | 解禁日期             |
| shareholder           | str    | 股东名               |
| shareholder_type      | str    | 股东类型             |
| relieve_shares        | double | 解除限售股份数量(股) |
| actual_relieve_shares | double | 实际上市流通数量(股) |
| relieve_reason        | str    | 解禁原因             |

**16.4. 使用示例**

**16.4.1. 获取一定日期内某只股票的股票限售解禁明细数据**

```python
import panda_data
result = panda_data.get_restricted_list(
    symbol="001256.SZ",
    start_date="20251201",
    end_date="20251231",
    fields=[]
)
print(result)
```

```text
date relieve_date ... relieve_reason shareholder_type
0 20251211 20251212 ... 发行前股份限售流通 企业
1 20251211 20251212 ... 发行前股份限售流通 自然人
2 20251211 20251212 ... 发行前股份限售流通 自然人
3 20251211 20251212 ... 发行前股份限售流通 企业
4 20251211 20251212 ... 发行前股份限售流通 自然人
```

**16.4.2. 获取一定日期内某只股票的股票限售解禁明细数据且使用fields**

```python
import panda_data
result = panda_data.get_restricted_list(
    symbol="001256.SZ",
    start_date="20251201",
    end_date="20251231",
    fields=["symbol", "date", "shareholder", "relieve_shares"]
)
print(result)
```

```text
date relieve_shares symbol shareholder
0 20251211 45758500.0 001256.SZ 浙江承炜股权投资有限公司
1 20251211 37280000.0 001256.SZ 周炳松
2 20251211 10320000.0 001256.SZ 李玉荷
3 20251211 3017825.0 001256.SZ 平阳炜仕股权投资合伙企业(有限合伙)
4 20251211 4000000.0 001256.SZ 於金华
```

**17. 获取股东数量**

**17.1. 方法名：get_holder_count**

**17.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_date | Optional\[str\] | 开始日期,eg:"20250702" | 非必填 |
| end_date | Optional\[str\] | 结束日期,eg:"20250702" | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |

**17.3. 响应参数**

| 字段                    | 类型   | 描述                    |
|:------------------------|:-------|:------------------------|
| symbol                  | str    | 股票代码                |
| date                    | str    | 公告日期                |
| end_date                | str    | 截止日期                |
| a_holders               | str    | A股股东户数             |
| avg_a_holders           | str    | A股股东户均持股数       |
| avg_circulation_holders | double | 无限售A股股东户均持股数 |
| avg_holders             | double | 户均持股数              |
| holders                 | str    | 股东户数                |

**17.4. 使用示例**

**17.4.1. 获取一定日期内某只股票的股东数量**

```python
import panda_data
result = panda_data.get_holder_count(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250531",
    fields=[]
)
print(result)
```

```text
end_date symbol ... avg_holders holders
0 20241231 000001.SZ ... 39908.69 486258.0
1 20250228 000001.SZ ... 40431.61 479969.0
2 20250331 000001.SZ ... 38483.42 504267.0
```

**17.4.2. 获取一定日期内全部股票的股东数量并使用fields**

```python
import panda_data
result = panda_data.get_holder_count(
    symbol="",
    start_date="20250101",
    end_date="20250131",
    fields=["symbol", "date", "holders", "avg_holders"]
)
print(result)
```

```text
date symbol avg_holders holders
0 20250103 000004.SZ 3021.42 43814.0
1 20250114 000004.SZ 3309.18 40004.0
2 20250122 000004.SZ 3295.5 40170.0
3 20250115 000008.SZ 19666.51 138122.0
4 20250106 000008.SZ 19181.02 141618.0
... ... ... ... ...
2259 20250103 688687.SH 19046.73 8975.0
2260 20250123 688687.SH 19902.72 8589.0
2261 20250107 688689.SH 17274.61 7462.0
2262 20250114 688689.SH 17721.08 7274.0
2263 20250109 688758.SH 14351.43 29019.0
```

**18. 获取A股股东信息**

**18.1. 方法名：get_top_holders**

**18.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_date | str | 开始日期,eg:"20250702" | 必填 |
| end_date | str | 结束日期,eg:"20250702" | 必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |
| market | Optional\[str\] | 市场,默认'cn'为中国内地市场 | 非必填 |
| start_rank | Optional\[int\] | 排名开始值 | 非必填 |
| end_rank | Optional\[int\] | 排名结束值 | 非必填 |
| stock_type | Optional\[str\] | 股票种类, flow基于持有A股流通股;total基于所有发行出的A股 | 非必填 |

**18.3. 响应参数**

| 字段               | 类型   | 描述                   |
|:-------------------|:-------|:-----------------------|
| date               | str    | 信息发布日期           |
| stock_type         | str    | 股票类型               |
| rank               | int    | 排名                   |
| symbol             | str    | 股票代码               |
| end_date           | str    | 截止日期               |
| freeze             | double | 股权冻结涉及股数（股） |
| hold_percent_float | double | 占流通A股比例（%）     |
| hold_percent_total | double | 占股比例(%)            |
| holder_attr        | str    | 股东属性               |
| holder_kind        | str    | 股东性质               |
| holder_name        | str    | 股东名称               |
| holder_type        | double | 股东类别               |
| pledge             | double | 股权质押涉及股数       |

**18.4. 使用示例**

**18.4.1. 获取一定日期内某只股票的股东信息**

```python
import panda_data
result = panda_data.get_top_holders(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250531",
    start_rank=1,
    end_rank=5,
    stock_type="flow",
    market="cn",
    fields=[]
)
print(result)
```

```text
holder_type date holder_kind ... hold_percent_total holder_attr pledge
0 NaN 20250315 金融机构—保险公司 ... 49.564984 企业 NaN
1 NaN 20250315 金融机构—保险公司 ... 6.112055 企业 NaN
2 NaN 20250315 一般企业 ... 3.848732 企业 NaN
3 NaN 20250315 保险投资组合 ... 2.269816 证券品种 NaN
4 NaN 20250315 金融机构—证券公司 ... 2.211865 企业 NaN
5 NaN 20250419 金融机构—保险公司 ... 49.564984 企业 NaN
6 NaN 20250419 金融机构—保险公司 ... 6.112055 企业 NaN
7 NaN 20250419 一般企业 ... 3.391309 企业 NaN
8 NaN 20250419 保险投资组合 ... 2.269816 证券品种 NaN
9 NaN 20250419 金融机构—证券公司 ... 2.211865 企业 NaN
```

**18.4.2. 获取一定日期内某只股票的股东信息据且使用fields**

```python
import panda_data
result = panda_data.get_top_holders(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250531",
    start_rank=1,
    end_rank=5,
    stock_type="flow",
    market="cn",
    fields=["symbol", "date", "holder_kind", "holder_name"]
)
print(result)
```

```text
date holder_kind rank symbol holder_name stock_type
0 20250315 金融机构—保险公司 1 000001.SZ 中国平安保险(集团)股份有限公司-集团本级-自有资金 flow
1 20250315 金融机构—保险公司 2 000001.SZ 中国平安人寿保险股份有限公司-自有资金 flow
2 20250315 一般企业 3 000001.SZ 香港中央结算有限公司 flow
3 20250315 保险投资组合 4 000001.SZ 中国平安人寿保险股份有限公司-传统-普通保险产品 flow
4 20250315 金融机构—证券公司 5 000001.SZ 中国证券金融股份有限公司 flow
5 20250419 金融机构—保险公司 1 000001.SZ 中国平安保险(集团)股份有限公司-集团本级-自有资金 flow
6 20250419 金融机构—保险公司 2 000001.SZ 中国平安人寿保险股份有限公司-自有资金 flow
7 20250419 一般企业 3 000001.SZ 香港中央结算有限公司 flow
8 20250419 保险投资组合 4 000001.SZ 中国平安人寿保险股份有限公司-传统-普通保险产品 flow
9 20250419 金融机构—证券公司 5 000001.SZ 中国证券金融股份有限公司 flow
```

**19. 获取A股大宗交易信息**

**19.1. 方法名：get_block_trade**

**19.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_date | Optional\[str\] | 开始日期,eg:"20250702" | 非必填 |
| end_date | Optional\[str\] | 结束日期,eg:"20250702" | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |

**19.3. 响应参数**

| 字段        | 类型   | 描述       |
|:------------|:-------|:-----------|
| symbol      | str    | 股票代码   |
| date        | str    | 交易日期   |
| price       | double | 成交价     |
| volume      | double | 成交量     |
| amount      | double | 成交额     |
| buyer       | str    | 买方营业部 |
| seller      | str    | 卖方营业部 |
| sequence_id | int    | 序列号     |

**19.4. 使用示例**

**19.4.1. 获取一定日期内某只股票的大宗交易信息**

```python
import panda_data
result = panda_data.get_block_trade(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250831",
    fields=[]
)
print(result)
```

```text
symbol date price buyer seller volume amount
0 000001.SZ 20250217 11.78 机构专用 中信证券股份有限公司上海分公司 171000.0 2014400.0
1 000001.SZ 20250711 11.86 中信证券股份有限公司江苏分公司 中信证券股份有限公司江苏分公司 1024600.0 12151800.0
```

**19.4.2. 获取一定日期内某只股票的大宗交易信息且使用fields**

```python
import panda_data
result = panda_data.get_block_trade(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250831",
    fields=["symbol", "date", "buyer", "amount", "price"]
)
print(result)
```

```text
symbol date price buyer amount
0 000001.SZ 20250217 11.78 机构专用 2014400.0
1 000001.SZ 20250711 11.86 中信证券股份有限公司江苏分公司 12151800.0
```

**20. 获取股票股本数据**

**20.1. 方法名：get_share_float**

**20.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_date | str | 开始日期,eg:"20250702" | 必填 |
| end_date | str | 结束日期,eg:"20250702" | 必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |

**20.3. 响应参数**

| 字段              | 类型 | 描述         |
|:------------------|:-----|:-------------|
| symbol            | str  | 股票代码     |
| date              | str  | 信息发布日期 |
| circulation_a     | str  | 流通A股      |
| free_circulation  | str  | 自由流通股本 |
| non_circulation_a | str  | 非流通A股    |
| preferred_shares  | str  | 优先股       |
| total             | str  | 总股本       |
| total_a           | str  | A股总股本    |

**20.4. 使用示例**

**20.4.1. 获取一定日期内某只股票的股本数据**

```python
import panda_data
result = panda_data.get_share_float(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250831",
    fields=[]
)
print(result)
```

```text
symbol date ... total total_a
0 000001.SZ 20250102 ... 1.940592e+10 1.940592e+10
1 000001.SZ 20250103 ... 1.940592e+10 1.940592e+10
2 000001.SZ 20250106 ... 1.940592e+10 1.940592e+10
3 000001.SZ 20250107 ... 1.940592e+10 1.940592e+10
4 000001.SZ 20250108 ... 1.940592e+10 1.940592e+10
.. ... ... ... ... ...
150 000001.SZ 20250825 ... 1.940592e+10 1.940592e+10
151 000001.SZ 20250826 ... 1.940592e+10 1.940592e+10
152 000001.SZ 20250827 ... 1.940592e+10 1.940592e+10
153 000001.SZ 20250828 ... 1.940592e+10 1.940592e+10
154 000001.SZ 20250829 ... 1.940592e+10 1.940592e+10
```

**20.4.2. 获取一定日期内某只股票的股本数据且使用fields**

```python
import panda_data
result = panda_data.get_share_float(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250831",
    fields=["symbol", "date", "circulation_a", "free_circulation"]
)
print(result)
```

```text
symbol date circulation_a free_circulation
0 000001.SZ 20250102 1.940562e+10 8.160498e+09
1 000001.SZ 20250103 1.940562e+10 8.160498e+09
2 000001.SZ 20250106 1.940562e+10 8.160498e+09
3 000001.SZ 20250107 1.940562e+10 8.160498e+09
4 000001.SZ 20250108 1.940562e+10 8.160498e+09
.. ... ... ... ...
150 000001.SZ 20250825 1.940560e+10 8.160481e+09
151 000001.SZ 20250826 1.940560e+10 8.160481e+09
152 000001.SZ 20250827 1.940560e+10 8.160481e+09
153 000001.SZ 20250828 1.940560e+10 8.160481e+09
154 000001.SZ 20250829 1.940560e+10 8.160481e+09
```

