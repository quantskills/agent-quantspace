---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - Futures DeepView
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# 期货 DeepView

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 期货 DeepView 数据

### get_broker_netmarg：获取席位净持仓保证金数据

数据范围 2015-01-05 ~ 至今；每日更新 22:30 ~ 23:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=67)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| broker | Optional[Union[string, List[string]]] | 否 | 席位名 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| underlying_symbol | string | 期货品种 |
| broker | string | 席位名 |
| net_margin | Int32 | 净持仓保证金额正表示净多负表示净空 |

示例：获取一定日期内某一品种的席位净持仓保证金

```python
import panda_data
result = panda_data.get_broker_netmarg (
    start_date="20250101",
    end_date="20250201",
    broker='',
    underlying_symbol='A',
)
print(result)
```

返回示例（前 3 行）：

| underlying_symbol | date | broker | net_margin |
|:---|:---|:---|:---|
| A | 20250102 | 渤海期货 | 0 |
| A | 20250102 | 长安期货 | -20066060 |
| A | 20250102 | 创元期货 | 100379620 |

### get_future_netposi_rank：获取期货商品净持仓多空榜单数据

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=63)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| max_rank | Optional[integer] | 否 | 最大排行，查询排名小于等于该值的数据 |
| type | Optional[string] | 否 | 多空方向，可填long或short |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| underlying_symbol | string | 期货品种 |
| broker_name | string | 席位名 |
| position_type | string | 多空方向 |
| exchange | string | 交易所代码 |
| rank | Int32 | 排名 |
| net_position | Int32 | 净持仓量 |
| net_position_change | Int32 | 净持仓增减，正表示增，负表示减 |

示例：获取一定日期内某一品种的净持仓多头前10

```python
import panda_data
result = panda_data.get_future_netposi_rank(
    start_date="20250101",
    end_date="20250201",
    underlying_symbol="A",
    max_rank=10,
    type="long"
)
print(result)
```

返回示例（前 3 行）：

| underlying_symbol | date | position_type | rank | broker_name | exchange | net_position | net_position_change |
|:---|:---|:---|:---|:---|:---|:---|:---|
| A | 20250102 | long | 1 | 银河期货 | DCE | 12438 | -11 |
| A | 20250102 | long | 2 | 新湖期货 | DCE | 8054 | 0 |
| A | 20250102 | long | 3 | 国泰君安 | DCE | 7393 | 396 |

### get_broker_netmarg_change：获取席位净持仓保证金变化数据

数据范围 2015-01-05 ~ 至今；每日更新 22:30 ~ 23:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=68)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| broker | Optional[Union[string, List[string]]] | 否 | 席位名 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| underlying_symbol | string | 期货品种 |
| broker | string | 席位名 |
| margin_change | Double | 净持仓保证金变化 |

示例：获取一定日期内某一品种的席位净持仓保证金变化

```python
import panda_data
result = panda_data.get_broker_netmarg_change (
    start_date="20250101",
    end_date="20250201",
    broker='',
    underlying_symbol='A',
)
print(result)
```

返回示例（前 3 行）：

| underlying_symbol | date | broker | margin_change |
|:---|:---|:---|:---|
| A | 20250102 | 渤海期货 | -23609040.0 |
| A | 20250102 | 长安期货 | 497720.0 |
| A | 20250102 | 创元期货 | -984500.0 |

### get_broker_grade：获取席位评级数据

数据范围 每日最新数据；每日更新 08:00 ~ 09:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=64)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| grade | Optional[string] | 否 | 席位评级，有A,B,C,D,E共5种 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| broker | string | 席位名 |
| grade | string | 评级 |

示例：获取评级A的席位

```python
import panda_data
result = panda_data.get_broker_grade(
    grade='A'
)
print(result)
```

返回示例（前 3 行）：

| broker | grade |
|:---|:---|
| 宝城期货 | A |
| 渤海期货 | A |
| 创元期货 | A |

### get_broker_totlmarg：获取席位总持仓保证金数据

数据范围 2015-01-05 ~ 至今；每日更新 22:30 ~ 23:30；[官方页面](https://www.pandaaiquant.com/docs/api?id=69)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| broker | Optional[Union[string, List[string]]] | 否 | 席位名 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| underlying_symbol | string | 期货品种 |
| broker | string | 席位名 |
| total_margin | Int32 | 总持仓保证金额 |

示例：获取一定日期内某一品种的席位总持仓保证金

```python
import panda_data
result = panda_data.get_broker_totlmarg (
    start_date="20250101",
    end_date="20250201",
    broker='',
    underlying_symbol='A',
)
print(result)
```

返回示例（前 3 行）：

| underlying_symbol | date | broker | total_margin |
|:---|:---|:---|:---|
| A | 20250102 | 渤海期货 | 0 |
| A | 20250102 | 长安期货 | 112802060 |
| A | 20250102 | 创元期货 | 100379620 |

### get_future_basis：获取期货基差数据

数据范围 2015-01-05 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=70)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| underlying_symbol | string | 期货品种 |
| date | string | 日期 |
| basis | float | 基差(现货价-期货价) |
| basis_ratio | float | 基差率(基差/现货价) |
| spot_price | float | 现货价 |

示例：获取一定日期内某一品种的全部基差数据

```python
import panda_data
result = panda_data.get_future_basis (
    start_date="20250101",
    end_date="20250201",
    fields=[''],
    underlying_symbol='A',
)
print(result)
```

返回示例（前 3 行）：

| underlying_symbol | date | basis | basis_ratio | spot_price |
|:---|:---|:---|:---|:---|
| A | 20250102 | 9.0 | 0.228426 | 3940.0 |
| A | 20250103 | 23.0 | 0.583756 | 3940.0 |
| A | 20250106 | 48.0 | 1.218274 | 3940.0 |

### get_future_warehouse_receipt：获取期货仓单数据

数据范围 2015-01-05 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=71)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| underlying_symbol | string | 期货品种 |
| date | string | 日期 |
| wr_quantity | Int32 | 仓单数 |
| wr_change | Int32 | 仓单数变化量 |
| wr_lot_quantity | float | 仓单折盘面手数 |
| wr_lot_change | float | 仓单折盘面手数变化量 |

示例：获取一定日期内某一品种的全部仓单数据

```python
import panda_data
result = panda_data.get_future_warehouse_receipt (
    start_date="20250101",
    end_date="20250201",
    underlying_symbol='A',
)
print(result)
```

返回示例（前 3 行）：

| underlying_symbol | date | wr_change | wr_lot_change | wr_lot_quantity | wr_quantity |
|:---|:---|:---|:---|:---|:---|
| A | 20250102 | -50 | -50.0 | 31897.0 | 31897 |
| A | 20250103 | 1000 | 1000.0 | 32897.0 | 32897 |
| A | 20250106 | 2371 | 2371.0 | 35268.0 | 35268 |

### get_future_net_flow：获取期货净资金流列表

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=74)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| broker_name | string | 否 | 席位名称 |
| position_type | string | 否 | 多:"long"，空:"short" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| underlying_symbol | string | 期货品种 |
| date | string | 日期 |
| broker_name | string | 席位名称 |
| money_flow | Int32 | 流动资金 |
| position_type | string | 多空方向 |

示例：获取一定日期内某家券商的某一品种的净资金流

```python
import panda_data
result = panda_data.get_future_net_flow(
    start_date="20250101",
    end_date="20250201",
    underlying_symbol=["AG", "AU"],
    broker_name="海通期货",
    position_type="long",
)
print(result)
```

返回示例（前 3 行）：

| underlying_symbol | date | broker_name | money_flow | position_type |
|:---|:---|:---|:---|:---|
| AG | 20250102 | 海通期货 | 1.115451e+09 | long |

### get_future_contract_indicators：获取期货龙虎比、牛熊线

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=73)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期货合约:"AL2501.SHF" |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 期货品种:\`AU2506.SHF\` |
| date | string | 日期 |
| line | Double | 牛熊线 (Bull-Bear Line) |
| ratio | Double | 龙虎比 (Long-Hu Ratio) |

示例：获取一定日期内某些合约的龙虎比、牛熊线

```python
import panda_data
result = panda_data.get_future_contract_indicators(
    start_date="20250101",
    end_date="20250201",
    symbol=["AL2501.SHF", "AG2505.SHF"],
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | line | ratio |
|:---|:---|:---|:---|
| AL2501.SHF | 20250102 | -14.0 | -13.136 |
| AL2501.SHF | 20250103 | -14.0 | -14.267 |
| AL2501.SHF | 20250106 | -3.0 | -12.843 |

### get_broker_variety_profit：获取期货席位的商品盈亏数据

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=72)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |
| broker | Optional[Union[string, List[string]]] | 否 | 席位 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| underlying_symbol | string | 期货商品品种 |
| date | string | 日期 |
| broker | string | 席位名称 |
| profit | Int32 | 营收和亏损 |

示例：获取一定日期内某一席位的商品盈亏数据

```python
import panda_data
result = panda_data.get_broker_variety_profit(
    start_date="20250101",
    end_date="20250201",
    symbol=["M", "LH"],
    broker="创元期货",
)
print(result)
```

返回示例（前 3 行）：

| underlying_symbol | date | broker | profit |
|:---|:---|:---|:---|
| M | 20250102 | 创元期货 | -7653680 |
| LH | 20250102 | 创元期货 | -4614400 |
| M | 20250103 | 创元期货 | 419610 |

### get_future_variety_posi：获取期货商品持仓数据

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=66)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期货商品 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| position_type | string | 否 | 多:"long"，空:"short" |
| broker_name | string | 否 | 席位名称 |
| rank_max | integer | 否 | 排名 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| underlying_symbol | string | 期货品种 |
| date | string | 日期 |
| broker_name | string | 席位名称 |
| change_oi | Int32 | 增减仓 |
| open_interest | Int32 | 持仓量 |
| position_type | string | 多空方向 |
| rank_num | Int32 | 排名 |

示例：获取一定日期内某家券商在某一商品在某个方向的持仓量和增减仓排名前3的情况

```python
import panda_data
result = panda_data.get_future_variety_posi(
    start_date="20250101",
    end_date="20250201",
    symbol=["A"],
    position_type="long",
    broker_name="中信期货",
    rank_max=3,
)
print(result)
```

返回示例（前 3 行）：

| underlying_symbol | date | broker_name | change_oi | open_interest | position_type | rank_num |
|:---|:---|:---|:---|:---|:---|:---|
| A | 20250102 | 中信期货 | 156 | 22101 | long | 1 |
| A | 20250103 | 中信期货 | 54 | 22155 | long | 1 |
| A | 20250106 | 中信期货 | -900 | 21255 | long | 1 |

### get_future_symbol_posi：获取期货合约持仓数据

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=65)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| position_type | string | 否 | 多:"long"，空:"short" |
| broker_name | string | 否 | 席位名称 |
| rank_max | int32 | 否 | 排名 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段列表 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 期货合约 |
| date | string | 日期 |
| position_type | string | 多空方向 |
| broker_name | string | 席位名称 |
| change_oi | Int32 | 持仓增减 |
| open_interest | Int32 | 持仓量 |
| rank_num | Int32 | 排名 |

示例：获取一定日期内某家券商在某一合约在多空方向上的持仓增减和持仓量排名前n的情况

```python
import panda_data
result = panda_data.get_future_symbol_posi(
    start_date="20250101",
    end_date="20250201",
    symbol=["A2503.DCE"],
    position_type="long",
    broker_name="新湖期货",
    rank_max=3,
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | broker_name | change_oi | open_interest | position_type | rank_num |
|:---|:---|:---|:---|:---|:---|:---|
| A2503.DCE | 20250102 | 新湖期货 | 0 | 8054 | long | 1 |
| A2503.DCE | 20250103 | 新湖期货 | 0 | 8054 | long | 1 |
| A2503.DCE | 20250106 | 新湖期货 | -405 | 7649 | long | 1 |

### get_future_ls_ratio：获取期货合约多空比数据

数据范围 2015-01-05 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=81)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 期货合约 |
| ls_ratio | float | 合约多空比 |

示例：获取一定日期内所有合约的多空比

```python
import panda_data
result = panda_data.get_future_ls_ratio(
    symbol="",
    start_date="20260101",
    end_date="20260201"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | ls_ratio |
|:---|:---|:---|
| A2601.DCE | 20260105 | 50.0 |
| A2601.DCE | 20260106 | 50.0 |
| A2601.DCE | 20260107 | 50.0 |

### get_future_netcap_change：获取期货合约净持仓市值变化数据

数据范围 2015-01-05 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=83)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| broker | Optional[Union[string, List[string]]] | 否 | 席位 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 合约代码 |
| net_cap_value | float | 净持仓市值变化 |
| broker | string | 券商名称 |

示例：获取一定日期内所有合约净持仓市值变化

```python
import panda_data
result = panda_data.get_future_netcap_change(
    symbol="",
    start_date="20260101",
    end_date="20260201",
    broker=[]
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | broker | net_cap_value |
|:---|:---|:---|:---|
| A2603.DCE | 20260105 | 银河期货 | -37413660.0 |
| A2603.DCE | 20260105 | 中金财富 | -25771980.0 |
| A2603.DCE | 20260105 | 渤海期货 | -24759660.0 |

### get_future_contract_rank：获取期货合约龙虎比、牛熊线排行

数据范围 2015-01-05 ~ 至今；每日更新 17:00 ~ 18:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=82)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种 |
| start_date | string | 是 | 开始日期,eg:"20250702" |
| end_date | string | 是 | 结束日期,eg:"20250802" |
| type | Optional[string] | 否 | 多空方向，可选long或short，为空时均返回 |
| max_rank | Optional[integer] | 否 | 最大排名 |
| rank_type | string | 是 | 排名依据，仅接受ratio或line，ratio将返回龙虎比及对应排名信息，line则返回牛熊线及对应排名信息 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 合约代码 |
| rank | integer | 排名 |
| position_type | string | 多空方向 |
| ratio | float | 龙虎比（当rank_type为ratio时） |
| line | integer | 牛熊线（当rank_type为line时） |
| underlying_symbol | string | 品种名 |

示例：获取一定日期内牛熊线排行数据

```python
import panda_data
result = panda_data.get_future_contract_rank(
    start_date="20260101",
    end_date="20260201",
    underlying_symbol="",
    symbol="",
    max_rank=None,
    type="",
    rank_type="line"
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | rank | position_type | line | underlying_symbol |
|:---|:---|:---|:---|:---|:---|
| AU2606.SHF | 20260105 | 1 | long | 49 | AU |
| RM2609.CZC | 20260105 | 2 | long | 43 | RM |
| AU2608.SHF | 20260105 | 3 | long | 38 | AU |

### get_future_term_structure：获取期货期限结构数据

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=85)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 合约代码：“SC2607.INE” |
| start_date | string | 是 | 开始日期：“YYYYMMDD” |
| end_date | string | 是 | 结束日期：“YYYYMMDD” |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| symbol | string | 合约代码 |
| close_price | float | 收盘价 |

示例：获取一定日期内某些合约的收盘价

```python
import panda_data
result = panda_data.get_future_term_structure(
    symbol=["SC2607.INE","Y2703.DCE"],
    start_date="20260401",
    end_date="20260403",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | close_price |
|:---|:---|:---|
| SC2607.INE | 20260401 | 631.6 |
| Y2703.DCE | 20260401 | 8492.0 |

### get_future_inventory：获取期货库存数据

数据范围 2015-01-01 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=86)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 合约代码：“SC2607.INE” |
| start_date | string | 是 | 开始日期：“YYYYMMDD” |
| end_date | string | 是 | 结束日期：“YYYYMMDD” |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| inventory_qty | float | 库存数据量 |
| underlying_symbol | string | 品种名 |

示例：获取一定日期内某些品种的库存数据量

```python
import panda_data
result = panda_data.get_future_inventory(
    symbol=["RB","HC"],
    start_date="20260401",
    end_date="20260409",
)
print(result)
```

返回示例（前 3 行）：

| underlying_symbol | date | inventory_qty |
|:---|:---|:---|
| RB | 20260403 | 840.75 |
| HC | 20260403 | 439.22 |

### get_future_calendar_arbitrage：获取期货跨期套利数据

数据范围 2000-01-04 ~ 至今；每日更新 16:12 ~ 16:32；[官方页面](https://www.pandaaiquant.com/docs/api?id=87)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| contract_symbol_1 | string | 是 | 合约代码1 |
| contract_symbol_2 | string | 是 | 合约代码2 |
| date | string | 是 | 日期：“YYYYMMDD” |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| contract_symbol_1 | string | 合约代码1 |
| contract_symbol_2 | string | 合约代码2 |
| settlement_1 | float | 合约1的结算价 |
| settlement_2 | float | 合约2的结算价 |
| cross_term_arbitrage | float | 价差，合约1价格 - 合约2价格 |

示例：获取某天某个品种的两个合约的跨期套利数据

```python
import panda_data
result = panda_data.get_future_calendar_arbitrage(
    contract_symbol_1="RB1901.SHF",
    contract_symbol_2="RB1905.SHF",
    date="20180808",
)
print(result)
```

返回示例（前 3 行）：

| contract_symbol_1 | contract_symbol_2 | date | settlement_1 | settlement_2 | cross_term_arbitrage |
|:---|:---|:---|:---|:---|:---|
| RB1901.SHF | RB1905.SHF | 20180808 | 4109.0 | 3930.0 | 179.0 |

### get_future_free_spread：获取期货自由价差数据

数据范围 2000-01-04 ~ 至今；每日更新 16:12 ~ 16:32；[官方页面](https://www.pandaaiquant.com/docs/api?id=88)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| contract_symbol_1 | string | 是 | 合约代码1 |
| contract_symbol_2 | string | 是 | 合约代码2 |
| date | string | 是 | 日期：“YYYYMMDD” |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| contract_symbol_1 | string | 合约代码1 |
| contract_symbol_2 | string | 合约代码2 |
| close_1 | float | 合约1价格 |
| close_2 | float | 合约2价格 |
| free_spread | float | 价差，合约1价格 - 合约2价格 |

示例：获取某天两个合约之间的自由价差数据

```python
import panda_data
result = panda_data.get_future_free_spread(
    contract_symbol_1="RB1901.SHF",
    contract_symbol_2="HC1901.SHF",
    date="20180808",
)
print(result)
```

返回示例（前 3 行）：

| contract_symbol_1 | contract_symbol_2 | date | close_1 | close_2 | free_spread |
|:---|:---|:---|:---|:---|:---|
| RB1901.SHF | HC1901.SHF | 20180808 | 4094.0 | 4100.0 | -6.0 |

### get_future_free_ratio：获取期货自由价比数据

数据范围 2000-01-04 ~ 至今；每日更新 16:12 ~ 16:32；[官方页面](https://www.pandaaiquant.com/docs/api?id=89)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| contract_symbol_1 | string | 是 | 合约代码1 |
| contract_symbol_2 | string | 是 | 合约代码2 |
| date | string | 是 | 日期：“YYYYMMDD” |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| contract_symbol_1 | string | 合约代码1 |
| contract_symbol_2 | string | 合约代码2 |
| close_1 | float | 合约1价格 |
| close_2 | float | 合约2价格 |
| free_ratio | float | 价比，合约1价格 / 合约2价格 |

示例：获取某天两个合约之间的自由价比数据

```python
import panda_data
result = panda_data.get_future_free_ratio(
    contract_symbol_1="RB1901.SHF",
    contract_symbol_2="HC1901.SHF",
    date="20180808",
)
print(result)
```

返回示例（前 3 行）：

| contract_symbol_1 | contract_symbol_2 | date | close_1 | close_2 | free_ratio |
|:---|:---|:---|:---|:---|:---|
| RB1901.SHF | HC1901.SHF | 20180808 | 4094.0 | 4100.0 | 0.998537 |

### get_broker_oi_value：获取期货席位合约的总持仓市值

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=95)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 期货代码 |
| start_date | string | 是 | 开始日期，支持 YYYYMMDD |
| end_date | string | 是 | 结束日期，支持 YYYYMMDD |
| broker | string | 否 | 席位 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 合约代码，CTP 格式 |
| date | string | 交易日期，YYYYMMDD |
| broker | string | 席位名称 |
| oi_value | float | 总持仓市值（元） |

示例：获取一段日期内某合约的席位总持仓市值数据

```python
import panda_data
result = panda_data.get_broker_oi_value(
    symbol=["ZN2607.SHF", "A2605.DCE"],
    start_date="20260413",
    end_date="20260413",
    broker="",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | broker | oi_value |
|:---|:---|:---|:---|
| A2605.DCE | 20260413 | 一德期货 | 3.648220e+08 |
| A2605.DCE | 20260413 | 东吴期货 | 1.561865e+08 |
| A2605.DCE | 20260413 | 东方财富 | 7.101146e+07 |

### get_future_nonbroker_net：获取期货非期货公司净持仓

数据范围 2013-01-04 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=97)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | string | 否 | list\[str\] |
| start_date | string | 是 | 开始日期，支持 YYYYMMDD |
| end_date | string | 是 | 结束日期，支持 YYYYMMDD |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 品种代码 |
| date | string | 交易日期，YYYYMMDD |
| net_oi | float | 非期货公司净持仓 |

示例：获取一段日期内某品种的非期货公司净持仓

```python
import panda_data
result = panda_data.get_future_nonbroker_net(
    symbol="AG",
    start_date="20180801",
    end_date="20180831",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | net_oi |
|:---|:---|:---|
| AG | 20180801 -74335.0 |
| AG | 20180802 -75281.0 |
| AG | 20180803 -75477.0 |

### get_broker_profit：获取期货席位盈亏数据

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=99)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，支持 YYYYMMDD |
| end_date | string | 是 | 结束日期，支持 YYYYMMDD |
| broker | string | 否 | 席位 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 交易日期（YYYYMMDD） |
| broker | string | 席位名称 |
| profit | float | 席位盈亏（元） |

示例：获取一段日期内某席位的盈亏数据

```python
import panda_data
result = panda_data.get_broker_profit(
    start_date="20260301",
    end_date="20260416",
    broker="齐盛期货",
)
print(result)
```

返回示例（前 3 行）：

| broker | date | profit |
|:---|:---|:---|
| 齐盛期货 | 20260302 -91133345.0 |
| 齐盛期货 | 20260303 -49577445.0 |
| 齐盛期货 | 20260304 | 76375735.0 |

### get_broker_flow_daily：获取期货席位每日大资金流动数据

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=100)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，支持 YYYYMMDD |
| end_date | string | 是 | 结束日期，支持 YYYYMMDD |
| broker | string | 否 | 席位 |
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 品种代码筛选（如 RB） |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 交易日期（YYYYMMDD） |
| broker | string | 席位名称 |
| underlying_symbol | string | 品种代码 |
| underlying_symbol_cn | string | 中文品种名 |
| margin_flow | float | 保证金流动（元） |

示例：获取一段日期内某席位的盈亏数据

```python
import panda_data
result = panda_data.get_broker_flow_daily(
    start_date="20260301",
    end_date="20260416",
    broker="",
    underlying_symbol=["RB","ZN"],
)
print(result)
```

返回示例（前 3 行）：

| broker | date | underlying_symbol | underlying_symbol_cn | margin_flow |
|:---|:---|:---|:---|:---|
| 一德期货 | 20260302 | RB | 螺纹钢 | -37186940.0 |
| 一德期货 | 20260302 | ZN | 沪锌 | 4910000.0 |
| 一德期货 | 20260303 | RB | 螺纹钢 | -34122000.0 |

### get_broker_ls_ratio：获取期货席位多空比数据

数据范围 2015-01-01 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=101)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| broker | string | 否 | 席位名称 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 交易日期 |
| broker | string | 席位名称 |
| ls_ratio | float | 多空比 |

示例：获取一段日期内某席位的多空比数据

```python
import panda_data
result = panda_data.get_broker_ls_ratio(
    start_date="20260301",
    end_date="20260416",
    broker=["齐盛期货","一德期货"],
)
print(result)
```

返回示例（前 3 行）：

| broker | date | ls_ratio |
|:---|:---|:---|
| 一德期货 | 20260301 | 50.000000 |
| 一德期货 | 20260302 | 42.149045 |
| 一德期货 | 20260303 | 38.097157 |

### get_broker_loss_rank：获取期货席位亏损排行数据

数据范围 2013-01-04 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=121)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| rank | integer | 排名 |
| broker | string | 券商名称 |
| profit | float | 亏损金额 |

示例：获取指定时间内的数据

```python
import panda_data
result = panda_data.get_broker_loss_rank(
    start_date='20260310',
    end_date='20260320',
 )
print(result)
```

返回示例（前 3 行）：

| rank | date | broker | profit |
|:---|:---|:---|:---|
| 0 | 1 | 20260310 | 中信期货 -1462298703 |
| 1 | 20260317 | 国泰君安 | -581299320 |

### get_broker_profit_rank：获取期货席位盈利排行数据

数据范围 2013-01-04 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=122)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| rank | integer | 排名 |
| broker | string | 券商名称 |
| profit | float | 亏损金额 |

示例：获取指定时间内的数据

```python
import panda_data
result = panda_data.get_broker_profit_rank(
    start_date='20260310',
    end_date='20260320',
 )
print(result)
```

返回示例（前 3 行）：

| rank | date | broker | profit |
|:---|:---|:---|:---|
| 1 | 20260310 | 浙商期货 | 781159755 |
| 1 | 20260320 | 金瑞期货 | 389575505 |

### get_broker_build_process：获取期货席位建仓过程数据

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=123)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| broker | string | 是 | 券商名称 |
| symbol | Optional[Union[string, List[string]]] | 否 | 期货名称 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | string | 日期 |
| broker | string | 券商名称 |
| long | integer | 多头持仓 |
| short | integer | 空头持仓 |
| symbol | string | 合约代码 |
| profit | float | 当日盈亏金额 |
| net_hold | integer | 净持仓 |
| total_profit | float | 累计盈亏金额 |
| cost | float | 估算盈亏平衡价格 |

示例：获取指定时间内指定期货券商的数据

```python
import panda_data
result = panda_data.get_broker_build_process(
    start_date='20260310',
    end_date='20260320',
    broker="浙商期货"
 )
print(result)
```

返回示例（前 3 行）：

| date | broker | symbol | long | short | profit | net_hold | total_profit | cost |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 20260310 | 浙商期货 | A2605.DCE | 6436 | 4058 | -2084490 | 2378 | 8754330 | 4394.86 |
| 20260310 | 浙商期货 | A2607.DCE | 0 | 4499 | 2655400 | -4499 | -13470580 | 4483.59 |
| 20260310 | 浙商期货 | A2611.DCE | 665 | 0 | -243800 | 665 | 388430 | 4727.59 |

### get_future_trader_quote：获取期货现货贸易商报价数据

数据范围 2019-02-11 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=124)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种名称 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| underlying_symbol | string | 期货品种 |
| date | string | 日期 |
| name | string | 期货品种名称 |
| price | float | 贸易商报价 |
| band | string | 品牌 |
| model | string | 型号、规格 |
| unit | string | 单位 |
| trader_name | string | 贸易商 |

示例：获取指定时间内的数据

```python
import panda_data
result = panda_data.get_future_trader_quote(
    start_date='20240810',
    end_date='20240920',
 )
print(result)
```

返回示例（前 3 行）：

| date | underlying_symbol | name | price | band | model | unit | trader_name |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 20240810 | BZ | 纯苯 | 9300.0 | 京博石化 | 石油苯;99.9% min | 元/吨 | 山东宏洋化学有限公司VIP |
| 20240810 | BZ | 纯苯 | 8700.0 | 齐鲁石化 | 石油苯;99.9% min | 元/吨 | 山东铭宇供应链管理有限公司VIP |
| 20240810 | BZ | 纯苯 | 7200.0 | 国产 | 99.9% | 元/吨 | 济南佳星化工有限公司VIP |

### get_future_virtual_ratio：获取期货虚实盘比数据

数据范围 2013-01-04 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=125)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | Optional[Union[string, List[string]]] | 否 | 期货合约名称 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 合约代码 |
| date | string | 日期 |
| virtual_volume | float | 虚盘量 |
| real_volume | float | 实盘量 |
| ratio | float | 虚实盘比 |

示例：获取指定时间内的数据

```python
import panda_data
result = panda_data.get_future_virtual_ratio(
    start_date='20240810',
    end_date='20240920',
 )
print(result)
```

返回示例（前 3 行）：

| date | symbol | ratio | real_volume | virtual_volume |
|:---|:---|:---|:---|:---|
| 20240812 | A2409.DCE | 3.453528 | 9737.0 | 33627.0 |
| 20240812 | A2411.DCE | 1.024751 | 9737.0 | 9978.0 |

### get_future_spot_profit：获取期货利润数据

数据范围 2010-01-04 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=126)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种名称 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| underlying_symbol | string | 期货品种 |
| date | string | 日期 |
| name | string | 数据名称 |
| unit | string | 数据单位 |
| updateRate | string | 更新频率 |
| profit | float | 利润 |

示例：获取指定时间内的数据

```python
import panda_data
result = panda_data.get_future_spot_profit(
    start_date='20240810',
    end_date='20240920',
 )
print(result)
```

返回示例（前 3 行）：

| date | underlying_symbol | name | profit | unit | updateRate |
|:---|:---|:---|:---|:---|:---|
| 0 | 20240810 | CF | 棉花加工利润 -2167.00 | 元/吨 | 日 |
| 20240810 | LH | 生猪外购利润 | 697.67 | 元/头 | 日 |

### get_future_variety_mcap：获取期货品种持仓市值数据

数据范围 2013-01-04 ~ 至今；每日更新 20:00 ~ 21:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=127)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 期货品种名称 |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| underlying_symbol | string | 期货品种 |
| date | string | 日期 |
| margin_deposits_change | string | 品种沉淀资金变化 |

示例：获取指定时间内的数据

```python
import panda_data
result = panda_data.get_future_variety_mcap(
    start_date='20240810',
    end_date='20240920',
 )
print(result)
```

返回示例（前 3 行）：

| date | margin_deposits_change | underlying_symbol |
|:---|:---|:---|
| 20240812 | -137866600 | A |
| 20240812 | -341963910 | AG |

### get_future_dominant_corr：获取期货主力合约涨跌幅相关性

数据范围 2000-01-04 ~ 至今；每日更新 16:12 ~ 16:52；[官方页面](https://www.pandaaiquant.com/docs/api?id=144)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| start_date | string | 是 | 开始日期，格式 YYYYMMDD |
| end_date | string | 是 | 结束日期，格式 YYYYMMDD |
| symbol | List[string] | 是 | 期货品种名称 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol_a:symbol_b | string | a、b两个商品 主力合约在指定时间点的涨跌幅相关性 |

示例：获取某商品主力合约在指定时间点的涨跌幅相关性

```python
import panda_data
result = panda_data.get_future_dominant_corr(
    symbol=["RB", "JM", "A"],
    start_date="20250108",
    end_date="20260427",
)
print(result)
```

返回示例（前 3 行）：

| data |
|:---|
| {'RB:RB': 1.0, 'RB:JM': 0.67, 'RB:A': 0.1, 'JM:RB': 0.67, 'JM:JM': 1.0, 'JM:A': 0.07, 'A:RB': 0.1, 'A:JM': 0.07, 'A:A': 1.0} |

### get_future_contract_pool：获取期货多头空头合约池

数据范围 2015-01-05 ~ 至今；每日更新 21:00 ~ 22:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=137)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 合约代码（CTP） |
| underlying_symbol | Optional[Union[string, List[string]]] | 否 | 品种代码 |
| start_date | string | 是 | 开始日期 |
| end_date | string | 是 | 结束日期 |
| position_direction | Optional[Union[string, List[string]]] | 否 | long / short |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 合约代码（CTP） |
| date | string | 交易日（YYYYMMDD） |
| underlying_symbol | string | 品种代码 |
| position_direction | string | 多空方向 |

示例：获取指定时间段内的某品种在多头合约池的合约代码

```python
import panda_data
result = panda_data.get_future_contract_pool(
    symbol=[""],
    underlying_symbol=["RB"],
    start_date="20260401",
    end_date="20260427",
    position_direction="long",
)
print(result)
```

返回示例（前 3 行）：

| symbol | date | position_direction | underlying_symbol |
|:---|:---|:---|:---|
| RB2607.SHF | 20260413 | long | RB |
| RB2607.SHF | 20260414 | long | RB |
| RB2607.SHF | 20260415 | long | RB |
