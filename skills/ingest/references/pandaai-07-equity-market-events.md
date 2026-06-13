---
source: https://www.pandaai.online/knowledge-base/?pageUrl=/coreFeatrue&id=%E4%BA%94%E6%95%B0%E6%8D%AEapi
title: PandaAI Data API - LHB, Repurchase, Margin, and Northbound Holdings
extracted: 2026-05-06
source_lines: 1987-2478
---

**10. 获取股票龙虎榜数据**

**10.1. 方法名：get_lhb_list**

**10.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码，如 "000001.SZ" | 非必填 |
| type | Optional\[Union\[str, List\[str\]\]\] | 龙虎榜类型 | 非必填 |
| start_date | Optional\[str\] | 开始日期，格式 "YYYYMMDD" | 非必填 |
| end_date | Optional\[str\] | 结束日期，格式 "YYYYMMDD" | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 需要返回的字段列表 | 非必填 |

**10.3. 响应参数**

| 字段        | 类型   | 描述               |
|:------------|:-------|:-------------------|
| symbol      | str    | 股票代码           |
| date        | str    | 龙虎榜日期         |
| type        | str    | 龙虎榜类型(见下表) |
| reason      | str    | 龙虎榜原因         |
| amount      | double | 龙虎榜金额         |
| volume      | double | 龙虎榜数量         |
| amplitude   | double | 龙虎榜振幅         |
| change_rate | double | 龙虎榜涨跌幅       |
| deviation   | double | 龙虎榜涨跌幅偏离值 |
| turnover    | double | 龙虎榜换手率       |
| start_date  | double | 异动开始日期       |
| end_date    | str    | 异动结束日期       |

龙虎榜类型:

|  |  |
|:---|:---|
| 类型代码 | 描述 |
| AP015 | 日价格振幅达15% |
| AP030 | 日价格振幅达30% |
| AP040 | 日价格振幅达40% |
| CL000 | 无价格涨跌幅限制 |
| CP000 | 日涨跌幅达到20% |
| CS000 | 当日无价格涨跌幅限制的A股，出现异常波动停牌的 |
| C0000 | 涨跌幅 |
| CBB30 | 连续2个交易日触及涨跌幅限制,同营业部净买入占当日总成交量30%以上,且未公告 |
| CMB30 | 连续2个交易日触及涨跌幅限制,同营业部净卖出占当日总成交量30%以上,且未公告 |
| CTC00 | 连续三日触及价格涨跌幅限制 |
| CAC00 | 连续三日达到价格涨跌幅限制 |
| CCCC0 | 最近3个有成交的交易日以内收盘价涨跌幅累计达到+120%(-60%) |
| CCC2X | 最近3个有成交的交易日以内收盘价涨跌幅累计达到+200%(-70%) |
| DCC40 | 最近3个有成交的交易日以内收盘价涨跌幅偏离值累计达到+40%(-40%) |
| D0000 | 涨跌幅偏离值 |
| D0C00 | 三日涨跌幅偏离值 |
| DSC00 | 三日涨跌幅偏离值(ST) |
| F0000 | 新股首日交易信息 |
| Q0000 | 退市整理 |
| S0000 | 实施特别停牌 |
| VB050 | 当日融资买入数量达到当日该证券总交易量的50％以上 |
| VM050 | 当日融券卖数量达到当日该证券总交易量的50％以上 |
| N0J03 | 连续10个交易日内3次出现负向异常波动情形的证券 |
| N0A03 | 严重异常期间3次出现负向异常波动情形的证券 |
| N0J04 | 连续10个交易日内4次出现负向异常波动情形的证券 |
| P0J03 | 连续10个交易日内3次出现正向异常波动情形的证券 |
| P0A03 | 严重异常期间3次出现正向异常波动情形的证券 |
| P0J04 | 连续10个交易日内4次出现正向异常波动情形的证券 |
| O0000 | 其它异常波动的证券 |
| R0000 | 风险警示期交易 |
| T0020 | 日换手率达20% |
| T0C20 | 连续三个交易日内的日均换手率与前五个交易日日均换手率的比值到达30倍,并且该股票封闭式基金连续三个交易日内累计换手率达到20% |
| T0030 | 日换手率达30% |
| T0010 | 日换手率达10% |
| TR030 | 风险警示股票盘中换手率达到或超过30% |
| G0007 | 日涨幅偏离值达7% |
| GC015 | 日收盘价涨幅达15% |
| GCC12 | 连续三个交易日内，收盘价涨幅偏离值累计达到12%的ST证券、\*ST证券 |
| G0C20 | 连续三个交易日内，涨幅偏离值累计达20% |
| GCC30 | 连续3个交易日内日收盘价格涨幅偏离值累计达30% |
| G0C15 | 连续三个交易日内，涨幅偏离值累计达到15%（沪）或12%（深）的ST证券、\*ST证券和未完成股改证券 |
| GCJ1X | 连续10个交易日内收盘价格涨幅偏离值累计达到100%的证券 |
| GCZ2X | 连续30个交易日内收盘价格涨幅偏离值累计达到200%的证券 |
| GCA1X | 严重异常期间日收盘价格涨幅偏离值累计达到100%的证券 |
| GCA2X | 严重异常期间日收盘价格涨幅偏离值累计达到200%的证券 |
| L0007 | 日跌幅偏离值达7% |
| LC015 | 日收盘价跌幅达15% |
| LCA50 | 严重异常期间日收盘价格跌幅偏离值累计达到50%的证券 |
| LCA70 | 严重异常期间日收盘价格跌幅偏离值累计达到70%的证券 |
| LCC12 | 连续三个交易日内，收盘价跌幅偏离值累计达到12%的ST证券、\*ST证券 |
| L0C20 | 连续三个交易日内，跌幅偏离值累计达20% |
| LCC30 | 连续3个交易日内日收盘价格跌幅偏离值累计达30% |
| L0C15 | 连续三个交易日内，跌幅偏离值累计达到15%（沪）或12%（深）的ST证券、\*ST证券和未完成股改证券 |
| LCJ50 | 连续10个交易日内收盘价格跌幅偏离值累计达到-50%的证券 |
| LCZ70 | 连续30个交易日内收盘价格跌幅偏离值累计达到-70%的证券 |

**10.4. 使用示例**

**10.4.1. 获取一定日期内某一类型所有股票龙虎榜数据**

```python
import panda_data
result = panda_data.get_lhb_list(
    start_date="20250101",
    end_date="20250131",
    type="G0007",
    symbol="",
    fields=[]
)
print(result)
```

```text
date symbol type ... start_date turnover volume
0 20250116 000016.SZ G0007 ... 20250116 None 390440000.0
1 20250109 000063.SZ G0007 ... 20250109 None 391500000.0
2 20250103 000533.SZ G0007 ... 20250103 None 240090000.0
3 20250110 000573.SZ G0007 ... 20250110 None 265010000.0
4 20250122 000627.SZ G0007 ... 20250122 None 284190000.0
.. ... ... ... ... ... ... ...
170 20250123 605277.SH G0007 ... 20250123 None 3568019.0
171 20250122 605389.SH G0007 ... 20250122 None 4272238.0
172 20250127 605398.SH G0007 ... 20250127 None 1348103.0
173 20250123 605398.SH G0007 ... 20250123 None 18684754.0
174 20250122 605398.SH G0007 ... 20250122 None 10629766.0
```

**10.4.2. 获取一定日期内某一股票所有龙虎榜数据且使用fields**

```python
import panda_data
result = panda_data.get_lhb_list(
    symbol="001314.SZ",
    start_date="20250101",
    end_date="20250131",
    fields=["type", "deviation","start_date"],
    type=""
)
print(result)
```

```text
symbol date type deviation start_date
0 001314.SZ 20250107 T0020 NaN 20250107
1 001314.SZ 20250103 T0020 NaN 20250103
2 001314.SZ 20250102 T0020 NaN 20250102
3 001314.SZ 20250102 G0007 0.1258 20250102
```

**11. 获取股票龙虎榜明细数据**

**11.1. 方法名：get_lhb_detail**

**11.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] = None | 股票代码，如 "000001.SZ" | 非必填 |
| type | Optional\[Union\[str, List\[str\]\]\] | 龙虎榜类型 | 非必填 |
| start_date | str | 开始日期，格式 "YYYYMMDD" | 必填 |
| end_date | str | 结束日期，格式 "YYYYMMDD" | 必填 |
| side | Optional\[str\] | 买卖方向，可选值为 "buy" 或 "sell" 或 "cum"，其中"cum"类型记录发生严重异常时的累计数据，与具体买卖方向无关 | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 需要返回的字段列表 | 非必填 |

**11.3. 响应参数**

| 字段    | 类型   | 描述             |
|:--------|:-------|:-----------------|
| symbol  | str    | 股票代码         |
| date    | str    | 龙虎榜日期       |
| type    | str    | 龙虎榜类型(同前) |
| side    | str    | 买卖方向         |
| rank    | int    | 龙虎榜排名       |
| agency  | str    | 营业部名称       |
| b_value | double | 买入金额         |
| s_value | double | 卖出金额         |
| reason  | str    | 龙虎榜原因       |

**11.4. 使用示例**

**11.4.1. 获取某只股票卖方向龙虎榜明细**

```python
import panda_data
result = panda_data.get_lhb_detail(
    symbol="001314.SZ",
    start_date="20250101",
    end_date="20250131",
    type="T0020",
    side="sell",
    fields=[]
)
print(result)
```

```text
date rank side symbol ... b_value reason s_value type
0 20250107 1 sell 001314.SZ ... 9264.0 日换手率达20% 65335573.0 T0020
1 20250107 2 sell 001314.SZ ... 87986.0 日换手率达20% 40823242.0 T0020
2 20250107 3 sell 001314.SZ ... 33731705.0 日换手率达20% 12017622.0 T0020
3 20250107 4 sell 001314.SZ ... 883470.0 日换手率达20% 11191385.0 T0020
4 20250107 5 sell 001314.SZ ... 283895.0 日换手率达20% 9456590.0 T0020
5 20250103 1 sell 001314.SZ ... 11702.0 日换手率达20% 61308405.7 T0020
6 20250103 2 sell 001314.SZ ... 13133584.0 日换手率达20% 39695456.0 T0020
7 20250103 3 sell 001314.SZ ... 7232734.0 日换手率达20% 37405572.0 T0020
8 20250103 4 sell 001314.SZ ... 4726659.0 日换手率达20% 34687595.4 T0020
9 20250103 5 sell 001314.SZ ... 546472.0 日换手率达20% 25320659.0 T0020
```

**11.4.2. 获取某只股票买方向龙虎榜明细并使用fields**

```python
import panda_data
result = panda_data.get_lhb_detail(
    symbol="001314.SZ",
    start_date="20250101",
    end_date="20250131",
    type="T0020",
    side="buy",
    fields=["symbol", "date", "type", "s_value", "reason"]
)
print(result)
```

```text
date symbol reason s_value type
0 20250107 001314.SZ 日换手率达20% 2645439.12 T0020
1 20250107 001314.SZ 日换手率达20% 1135792.00 T0020
2 20250107 001314.SZ 日换手率达20% 0.00 T0020
3 20250107 001314.SZ 日换手率达20% 12017622.00 T0020
4 20250107 001314.SZ 日换手率达20% 0.00 T0020
5 20250103 001314.SZ 日换手率达20% 3272065.00 T0020
6 20250103 001314.SZ 日换手率达20% 6594875.00 T0020
7 20250103 001314.SZ 日换手率达20% 63272.00 T0020
8 20250103 001314.SZ 日换手率达20% 31370.00 T0020
9 20250103 001314.SZ 日换手率达20% 1564684.00 T0020
```

**12. 获取回购数据**

**12.1. 方法名：get_repurchase**

**12.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_date | Optional\[str\] | 日期，格式 "YYYYMMDD" | 非必填 |
| end_date | Optional\[str\] | 日期，格式 "YYYYMMDD" | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 需要返回的字段列表 | 非必填 |

**12.3. 响应参数**

| 字段 | 类型 | 描述 |
|:---|:---|:---|
| symbol | str | 股票代码 |
| date | str | 日期，格式 "YYYYMMDD" |
| seller | str | 股份被回购方 |
| procedure | str | 事件进程 |
| share_type | str | 股份类别 |
| announcement_dt | datetime | 公告发布当天的日期时间戳，格式 "YYYY-MM-DD HH:MM:SS.sss" |
| buy_back_start_date | str | 回购期限起始日，格式 "YYYYMMDD" |
| buy_back_end_date | str | 回购期限结束日，格式 "YYYYMMDD" |
| write_off_date | str | 回购注销公告日，格式 "YYYYMMDD" |
| maturity_desc | str | 股份回购期限说明 |
| buy_back_volume | double | 回购股数(股)(份) |
| volume_ceiling | double | 回购数量上限(股)(份) |
| volume_floor | double | 回购数量下限(股)(份) |
| buy_back_value | double | 回购总金额(元) |
| buy_back_price | double | 回购价格(元/股)(元/份) |
| price_ceiling | double | 回购价格上限(元) |
| price_floor | double | 回购价格下限(元) |
| currency | double | 货币单位 |
| purpose | str | 回购目的 |
| buy_back_percent | double | 占总股本比例 |
| value_floor | double | 拟回购资金总额下限(元) |
| value_ceiling | double | 拟回购资金总额上限(元) |
| buy_back_mode | str | 股份回购方式 |

**12.4. 使用示例**

**12.4.1. 获取一定日期内某只股票的回购数据**

```python
import panda_data
result = panda_data.get_repurchase(
    symbol="002011.SZ",
    start_date="20250101",
    end_date="20251231",
    fields=[]
)
print(result)
```

```text
symbol date buy_back_value ... volume_floor buy_back_volume price_floor
0 002011.SZ 20250730 5630000.0 ... 834043.0 834043.0 6.61
1 002011.SZ 20251127 1350000.0 ... 199800.0 199800.0 6.61
2 002011.SZ 20251127 1350000.0 ... 199800.0 199800.0 6.61
```

**12.4.2. 获取一定日期内某只股票的回购数据且使用fields**

```python
import panda_data
result = panda_data.get_repurchase(
    symbol="002011.SZ",
    start_date="20250101",
    end_date="20251231",
    fields=["symbol", "seller", "date", "procedure"]
)
print(result)
```

```text
symbol date procedure seller
0 002011.SZ 20250730 实施完成 激励对象
1 002011.SZ 20251127 预案 8名激励对象
2 002011.SZ 20251127 决案 8名激励对象
```

**13. 获取融资融券信息**

**13.1. 方法名：get_margin**

**13.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_date | str | 开始日期,eg:"20250702" | 必填 |
| end_date | str | 结束日期,eg:"20250702" | 必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |
| margin_type | Optional\[str\] | 买卖方向，'stock' 代表融券卖出，'cash' 代表融资买入 | 非必填 |

**13.3. 响应参数**

| 字段名 | 类型 | 描述 |
|:---|:---|:---|
| short_sell_quantity | double | 融券卖出量 |
| buy_on_margin_value | double | 融资买入额 |
| date | str | 日期 |
| margin_repayment | double | 融券偿还额 |
| short_balance | double | 融券余额 |
| margin_balance | double | 融资余额 |
| symbol | str | 股票代码 |
| short_balance_quantity | double | 融券余量 |
| short_repayment_quantity | double | 融券偿还量 |
| margin_type | str | 买卖方向，'stock' 代表融券卖出，'cash' 代表融资买入 |
| total_balance | double | 总余额 |

**13.4. 使用示例**

**13.4.1. 获取一定日期内某只股票的融资融券信息**

```python
import panda_data
result = panda_data.get_margin(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250131",
    margin_type="stock",
    fields=[]
)
print(result)
```

```text
margin_repayment margin_type ... short_sell_quantity margin_balance
0 251279339.0 stock ... 9600.0 4.548699e+09
1 139809406.0 stock ... 27400.0 4.691464e+09
2 319125971.0 stock ... 73000.0 4.711227e+09
3 123876772.0 stock ... 51700.0 4.874748e+09
4 130980727.0 stock ... 30200.0 4.727470e+09
5 98068988.0 stock ... 18400.0 4.652860e+09
6 73332874.0 stock ... 138700.0 4.631203e+09
7 147096301.0 stock ... 115500.0 4.564706e+09
8 147931835.0 stock ... 60100.0 4.623174e+09
9 133426049.0 stock ... 106100.0 4.707604e+09
10 106573656.0 stock ... 30500.0 4.754935e+09
11 124881490.0 stock ... 8100.0 4.701712e+09
12 92421500.0 stock ... 80000.0 4.710915e+09
13 144223648.0 stock ... 104800.0 4.656706e+09
14 105752927.0 stock ... 118400.0 4.625191e+09
15 155997660.0 stock ... 120200.0 4.669212e+09
16 159456379.0 stock ... 23200.0 4.669653e+09
17 280885137.0 stock ... 21000.0 4.659470e+09
```

**13.4.2. 获取一定日期内某只股票的融资融券信息且使用fields**

```python
import panda_data
result = panda_data.get_margin(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250131",
    margin_type="stock",
    fields=["symbol", "date", "margin_type", "margin_repayment", "margin_balance"]
)
print(result)
```

```text
margin_repayment margin_type symbol date margin_balance
0 251279339.0 stock 000001.SZ 20250127 4.548699e+09
1 139809406.0 stock 000001.SZ 20250124 4.691464e+09
2 319125971.0 stock 000001.SZ 20250123 4.711227e+09
3 123876772.0 stock 000001.SZ 20250122 4.874748e+09
4 130980727.0 stock 000001.SZ 20250121 4.727470e+09
5 98068988.0 stock 000001.SZ 20250120 4.652860e+09
6 73332874.0 stock 000001.SZ 20250117 4.631203e+09
7 147096301.0 stock 000001.SZ 20250116 4.564706e+09
8 147931835.0 stock 000001.SZ 20250115 4.623174e+09
9 133426049.0 stock 000001.SZ 20250114 4.707604e+09
10 106573656.0 stock 000001.SZ 20250113 4.754935e+09
11 124881490.0 stock 000001.SZ 20250110 4.701712e+09
12 92421500.0 stock 000001.SZ 20250109 4.710915e+09
13 144223648.0 stock 000001.SZ 20250108 4.656706e+09
14 105752927.0 stock 000001.SZ 20250107 4.625191e+09
15 155997660.0 stock 000001.SZ 20250106 4.669212e+09
16 159456379.0 stock 000001.SZ 20250103 4.669653e+09
17 280885137.0 stock 000001.SZ 20250102 4.659470e+09
```

**14. 获取沪深股通持股信息**

**14.1. 方法名：get_hsgt_hold**

**14.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_date | str | 开始日期,eg:"20250702" | 必填 |
| end_date | str | 结束日期,eg:"20250702" | 必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |

**14.3. 响应参数**

| 字段名                 | 类型   | 描述           |
|:-----------------------|:-------|:---------------|
| date                   | str    | 日期           |
| shares_num             | double | 持股数量       |
| symbol                 | str    | 股票代码       |
| adjusted_holding_ratio | double | 调整后持股比例 |
| holding_ratio          | double | 持股比例       |

**14.4. 使用示例**

**14.4.1. 获取一定日期内某只股票的沪深股通持股信息**

```python
import panda_data
result = panda_data.get_hsgt_hold(
    symbol="000001.SZ",
    start_date="20250601",
    end_date="20250630",
    fields=[]
)
print(result)
```

```text
adjusted_holding_ratio symbol date holding_ratio shares_num
0 4.2726 000001.SZ 20250630 4.27 829114531.0
```

**14.4.2. 获取一定日期内所有股票的沪深股通持股信息并使用fields**

```python
import panda_data
result = panda_data.get_hsgt_hold(
    symbol="",
    start_date="20250601",
    end_date="20250630",
    fields=["symbol", "date", "shares_num"]
)
print(result)
```

```text
symbol date shares_num
0 000001.SZ 20250630 829114531.0
1 000002.SZ 20250630 154885054.0
2 000006.SZ 20250630 5247502.0
3 000008.SZ 20250630 41832884.0
4 000009.SZ 20250630 34424977.0
... ... ... ...
3783 688789.SH 20250630 9339644.0
3784 688798.SH 20250630 3096762.0
3785 688800.SH 20250630 1576539.0
3786 688819.SH 20250630 2334385.0
3787 688981.SH 20250630 63499339.0
```

