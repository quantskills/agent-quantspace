---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - Macro Data
extracted: 2026-11-21
generator: official API detail JSON (getApiTree / getApiDetail)
---

# 宏观数据

按官方文档原样整理。参数、字段和更新时间以官方页面为准；调用前确认账号已开通对应数据权限。

## 宏观指标基础信息

### get_macro_detail：宏观指标列表

数据范围 2015-01-01 ~ 至今；每日更新 季更；[官方页面](https://www.pandaaiquant.com/docs/api?id=142)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载（非空时将覆盖category的筛选进行查询） |
| category | Union[string, List[string]] | 是 | 指标分类代码（为指标代码的两位前缀） |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| name | string | 指标中文名 |
| en_name | string | 指标英文名 |
| is_list | integer | 是否为列表 |
| frequency | string | 数据频率 |
| unit | string | 单位 |
| stat_type | string | 统计类型 |
| accuracy | float | 数据精度 |
| region | string | 地区 |
| country | string | 国家 |
| currency | string | 货币 |
| importance | string | 重要性 |
| info_source | string | 指标发布来源 |
| note_text | string | 备注文本 |
| begin_date | string | 指标起始日期 |
| end_date | string | 指标截止日期 |
| is_update | string | 是否仍在更新 |
| api_name | string | API名称 |

示例：获取全部交通运输指标

```python
import panda_data
result = panda_data.get_macro_detail(
    symbol=[""],
    category=["TR"],
    fields=[""],
)
print(result)
```

返回示例（前 3 行）：

| symbol | name | en_name | is_list | frequency | unit | stat_type | accuracy | region | country | currency | importance | info_source | note_text | begin_date | end_date | is_update | api_name |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| TR0000001 | 中国物流业景气指数(LPI):季调 | China Logistics Prosperity Index (LPI):Seasonal Adjustment | 0 | 月 | % | 季调 | 2.0 | 全国 | 中国 | None | 不重要 | 中国物流与采购联合会 | 考虑到物流行业特点,自2014年4月起,取消综合指数的发布,以业务总量指数反映物流业的总体变化 | 20111231 | 20260331 | 1 | get_macro_tr |
| TR0000002 | 中国物流业景气指数(LPI):业务总量:季调 | China Logistics Prosperity Index(LPI):Total Business Volume: Seasonal Adjustment | 0 | 月 | % | 季调 | 2.0 | 全国 | 中国 | None | 不重要 | 中国物流与采购联合会 | None | 20111231 | 20260331 | 1 | get_macro_tr |
| TR0000003 | 中国物流业景气指数(LPI):新订单:季调 | China Logistics Prosperity Index(LPI):New Orders: Seasonal Adjustment | 0 | 月 | % | 季调 | 2.0 | 全国 | 中国 | None | 不重要 | 中国物流与采购联合会 | None | 20111231 | 20260228 | 1 | get_macro_tr |

## 中国宏观指标

### get_macro_na：中国宏观-国民经济核算

数据范围 1997-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=170)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-国民经济核算数据

```python
import panda_data
result = panda_data.get_macro_na(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| NA0004858 | 20220131 | 236.9 |
| NA0005500 | 20220131 | 3097.0 |
| NA0005501 | 20220131 | 17.3 |

### get_macro_in：中国宏观-工业

数据范围 2000-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=171)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-工业数据

```python
import panda_data
result = panda_data.get_macro_in(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| IN0000003 | 20220131 | 0.22 |
| IN0015523 | 20220131 | 236.90 |
| IN0000003 | 20220228 | 0.38 |

### get_macro_ci：中国宏观-景气指数

数据范围 2015-01-01 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=172)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-景气指数数据

```python
import panda_data
result = panda_data.get_macro_ci(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| CI0003528 | 20220103 | -0.934424 |
| CI0003528 | 20220104 | -1.608125 |
| CI0003528 | 20220105 | -1.722521 |

### get_macro_pi：中国宏观-价格指数

数据范围 2011-06-30 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=173)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-价格指数数据

```python
import panda_data
result = panda_data.get_macro_pi(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| PI0006548 | 20220101 | -0.30000 |
| PI0006581 | 20220101 | -0.90000 |
| PI0006582 | 20220101 | -1.10000 |

### get_macro_fa：中国宏观-固定资产投资

数据范围 2001-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=174)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-固定资产投资数据

```python
import panda_data
result = panda_data.get_macro_fa(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| FA0005374 | 20220101 | 401.0000 |
| FA0005375 | 20220101 | 98.0000 |
| FA0005376 | 20220101 | 30.0000 |

### get_macro_fi：中国宏观-财政

数据范围 2000-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=175)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-财政数据

```python
import panda_data
result = panda_data.get_macro_fi(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| FI0001803 | 20220131 | 308.20600 |
| FI0001804 | 20220131 | 139.79440 |
| FI0001805 | 20220131 | 75.45302 |

### get_macro_mb：中国宏观-货币与银行

数据范围 2002-03-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=176)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-货币与银行数据

```python
import panda_data
result = panda_data.get_macro_mb(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| MB0003831 | 20220101 | 800.0000 |
| MB0003831 | 20220102 | 800.0000 |
| MB0003831 | 20220103 | 800.0000 |

### get_macro_ir：中国宏观-利率汇率

数据范围 2000-05-29 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=177)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-利率汇率数据

```python
import panda_data
result = panda_data.get_macro_ir(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| IR0000034 | 20260101 | 6.9785 |
| IR0000035 | 20260101 | 8.1821 |
| IR0000036 | 20260101 | 4.4433 |

### get_macro_fe：中国宏观-对外经济

数据范围 2000-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=178)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-对外经济数据

```python
import panda_data
result = panda_data.get_macro_fe(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| FE0000001 | 20260131 | 3709.936424 |
| FE0000002 | 20260131 | 3353.122002 |
| FE0000003 | 20260131 | 356.814422 |

### get_macro_dt：中国宏观-国内贸易

数据范围 2000-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=179)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-国内贸易数据

```python
import panda_data
result = panda_data.get_macro_dt(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| DT0000012 | 20260131 | 0.31 |
| DT0000012 | 20260228 | 0.49 |
| DT0000018 | 20260228 | 86078.90 |

### get_macro_ew：中国宏观-就业与工资

数据范围 2004-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=180)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-就业与工资数据

```python
import panda_data
result = panda_data.get_macro_ew(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| EW0009279 | 20260101 | 1213.0 |
| EW0009280 | 20260101 | 2617.0 |
| EW0009281 | 20260101 | 121.0 |

### get_macro_li：中国宏观-人民生活

数据范围 2000-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=181)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-人民生活数据

```python
import panda_data
result = panda_data.get_macro_li(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| LI0000422 | 20260131 | 54434.00 |
| LI0000423 | 20260131 | 52824.00 |
| LI0000425 | 20260131 | 24783.00 |

### get_macro_pr：中国宏观-人口与资源

数据范围 2000-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=182)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-人口与资源数据

```python
import panda_data
result = panda_data.get_macro_pr(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| PR0001093 | 20260101 | 2.00 |
| PR0001094 | 20260101 | -10.00 |
| PR0001095 | 20260101 | 3.00 |

### get_macro_se：中国宏观-科教体卫

数据范围 2000-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=183)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-科教体卫数据

```python
import panda_data
result = panda_data.get_macro_se(
    start_date="20260401",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| SE0000273 | 20260131 | 64671.0 |
| SE0000274 | 20260131 | 100.0 |
| SE0000275 | 20260131 | 114458.0 |

### get_macro_sm：中国宏观-证券市场

数据范围 2000-01-04 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=184)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-证券市场数据

```python
import panda_data
result = panda_data.get_macro_sm(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| SM0000005 | 20260401 | 934.538025 |
| SM0000006 | 20260401 | 936.206522 |
| SM0000007 | 20260401 | 13164.474092 |

### get_macro_pm：中国宏观-区域宏观

数据范围 1978-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=185)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取中国宏观-区域宏观数据

```python
import panda_data
result = panda_data.get_macro_pm(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| PM0257343 | 20260101 | 2540.00 |
| PM0257344 | 20260101 | 27.70 |
| PM0257345 | 20260101 | 2510.00 |

## 国际宏观指标

### get_macro_gb：宏观行业-国际宏观

数据范围 2000-01-01 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=169)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取国际宏观数据

```python
import panda_data
result = panda_data.get_macro_gb(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| DE0002104 | 20260101 | 2.210000e+00 |
| DE0002106 | 20260101 | 1.973000e+00 |
| EU0013242 | 20260101 | 3.670700e+04 |

## 宏观行业数据

### get_macro_ag：宏观行业-农林牧渔

数据范围 2014-12-01 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=186)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-农林牧渔数据

```python
import panda_data
result = panda_data.get_macro_ag(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| AG0009608 | 20260101 | 129.310 |
| AG0009609 | 20260101 | 132.040 |
| AG0049148 | 20260101 | 1.222 |

### get_macro_en：宏观行业-能源

数据范围 2014-12-01 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=187)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-能源数据

```python
import panda_data
result = panda_data.get_macro_en(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| EN0002966 | 20260101 | 60.842 |
| EN0002967 | 20260101 | 57.420 |
| EN0054964 | 20260101 | 1264.000 |

### get_macro_ch：宏观行业-化工

数据范围 2014-12-01 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=188)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-化工数据

```python
import panda_data
result = panda_data.get_macro_ch(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| CH0008744 | 20260101 | 46300.00 |
| CH0104779 | 20260101 | 51.58 |
| CH0104780 | 20260101 | 5800.00 |

### get_macro_st：宏观行业-钢铁

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=189)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-钢铁数据

```python
import panda_data
result = panda_data.get_macro_st(
    start_date="20150101",
    end_date="20200101",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| ST0002343 | 20150101 | 2977.0 |
| ST0002345 | 20150101 | 2977.0 |
| ST0002348 | 20150101 | 3908.0 |

### get_macro_nf：宏观行业-有色金属

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=190)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-有色金属数据

```python
import panda_data
result = panda_data.get_macro_nf(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| NF0001335 | 20260101 | 569.40 |
| NF0001338 | 20260101 | 4332.10 |
| NF0001874 | 20260101 | 38.00 |

### get_macro_bm：宏观行业-建材

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=191)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-建材数据

```python
import panda_data
result = panda_data.get_macro_bm(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| BM0021965 | 20260104 | 351.60 |
| BM0021966 | 20260104 | 314.00 |
| BM0032339 | 20260104 | 115.38 |

### get_macro_au：宏观行业-汽车

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=192)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-汽车数据

```python
import panda_data
result = panda_data.get_macro_au(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| AU0036626 | 20260102 | 5.84651 |
| AU0036627 | 20260102 | 6.71537 |
| AU0036628 | 20260102 | 7.31107 |

### get_macro_me：宏观行业-机械设备

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=193)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-机械设备数据

```python
import panda_data
result = panda_data.get_macro_me(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| ME0039129 | 20260109 | 117.12 |
| ME0039130 | 20260109 | 114.23 |
| ME0039131 | 20260109 | 128.35 |

### get_macro_ee：宏观行业-电子电器

数据范围 2014-12-01 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=194)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-电子电器数据

```python
import panda_data
result = panda_data.get_macro_ee(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| EE0001106 | 20260102 | 7.367500e+03 |
| EE0001409 | 20260102 | 1.768500e+03 |
| EE0001410 | 20260102 | 9.388000e+02 |

### get_macro_tm：宏观行业-TMT

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=195)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-TMT数据

```python
import panda_data
result = panda_data.get_macro_tm(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| TM0025554 | 20260101 | 6.200000e+01 |
| TM0025561 | 20260101 | 8.100000e+01 |
| TM0025571 | 20260101 | 1.600000e+02 |

### get_macro_fb：宏观行业-食品饮料

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=196)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-食品饮料数据

```python
import panda_data
result = panda_data.get_macro_fb(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| FB0001743 | 20260101 | 1600.0 |
| FB0001744 | 20260101 | 1630.0 |
| FB0001745 | 20260101 | 1550.0 |

### get_macro_te：宏观行业-纺织服装

数据范围 2014-12-05 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=197)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-纺织服装数据

```python
import panda_data
result = panda_data.get_macro_te(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| TE0001894 | 20260102 | 105.41 |
| TE0001895 | 20260102 | 87.18 |
| TE0001896 | 20260102 | 110.98 |

### get_macro_pp：宏观行业-造纸印刷

数据范围 2014-12-12 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=198)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-造纸印刷数据

```python
import panda_data
result = panda_data.get_macro_pp(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| PP0004537 | 20260104 | 1700.00 |
| PP0004538 | 20260104 | 1630.00 |
| PP0004539 | 20260104 | 1630.00 |

### get_macro_ph：宏观行业-医药生物

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=199)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-医药生物数据

```python
import panda_data
result = panda_data.get_macro_ph(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| PH0003658 | 20260101 | 23.0 |
| PH0003661 | 20260101 | 19.0 |
| PH0003668 | 20260101 | 9.0 |

### get_macro_ut：宏观行业-公用事业

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=200)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-公用事业数据

```python
import panda_data
result = panda_data.get_macro_ut(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| UT0001592 | 20260101 | 30.0 |
| UT0001593 | 20260101 | 61.0 |
| UT0001594 | 20260101 | 52.0 |

### get_macro_tr：宏观行业-交通运输

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=201)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-交通运输数据

```python
import panda_data
result = panda_data.get_macro_tr(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| TR0031700 | 20260101 | 6.30 |
| TR0031701 | 20260101 | 40.00 |
| TR0031702 | 20260101 | 0.00 |

### get_macro_rc：宏观行业-房地产及建筑业

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=202)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-房地产及建筑业数据

```python
import panda_data
result = panda_data.get_macro_rc(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| RC0070277 | 20260101 | 0.0000 |
| RC0070278 | 20260101 | 0.0000 |
| RC0070279 | 20260101 | 0.0000 |

### get_macro_th：宏观行业-旅游酒店

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=203)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-旅游酒店数据

```python
import panda_data
result = panda_data.get_macro_th(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| TH0004096 | 20260104 | 111.65 |
| TH0004096 | 20260111 | 87.44 |
| TH0004096 | 20260118 | 103.71 |

### get_macro_ce：宏观行业-文教体娱及工艺品

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=204)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-旅游酒店数据

```python
import panda_data
result = panda_data.get_macro_ce(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| CE0005774 | 20260101 | 33827.00 |
| CE0005775 | 20260101 | 475167.00 |
| CE0005776 | 20260101 | 853.00 |

### get_macro_wr：宏观行业-批发零售业

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=205)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-批发零售业数据

```python
import panda_data
result = panda_data.get_macro_wr(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| WR0009591 | 20260107 | 102.270000 |
| WR0009593 | 20260107 | 102.700000 |
| WR0009594 | 20260107 | 96.130000 |

### get_macro_fs：宏观行业-金融保险业

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=206)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-金融保险业数据

```python
import panda_data
result = panda_data.get_macro_fs(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| FS0007548 | 20260101 | 4.000000 |
| FS0007552 | 20260101 | 0.000000 |
| FS0007629 | 20260101 | 4.000000 |

### get_macro_is：宏观行业-行业综合

数据范围 2015-01-02 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=207)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观行业-行业综合数据

```python
import panda_data
result = panda_data.get_macro_is(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| IS0001048 | 20260102 | 538.60 |
| IS0001049 | 20260102 | 472.18 |
| IS0001050 | 20260102 | 538.66 |

## 宏观特色数据

### get_macro_ec：宏观特色数据-线上电商数据

数据范围 2021-05-06 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=208)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-线上电商数据

```python
import panda_data
result = panda_data.get_macro_ec(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| EC0252098 | 20260104 | 837.0 |
| EC0252099 | 20260104 | 950.0 |
| EC0252100 | 20260104 | 475.0 |

### get_macro_md：宏观特色数据-医药数据

数据范围 2014-12-21 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=209)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-医药数据

```python
import panda_data
result = panda_data.get_macro_md(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| MD0006164 | 20260104 | 32.0 |
| MD0006165 | 20260104 | 36.0 |
| MD0006166 | 20260104 | 32.0 |

### get_macro_eh：宏观特色数据-能化数据

数据范围 2018-01-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=210)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-能化数据

```python
import panda_data
result = panda_data.get_macro_eh(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| EH0000092 | 20260101 | 3725.0 |
| EH0000093 | 20260101 | 3550.0 |
| EH0000094 | 20260101 | 3900.0 |

### get_macro_ad：宏观特色数据-汽车数据

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=211)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-汽车数据

```python
import panda_data
result = panda_data.get_macro_ad(
    start_date="20260101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| AD0024137 | 20260131 | 7.610000e+02 |
| AD0024138 | 20260131 | 1.800000e+02 |
| AD0024146 | 20260131 | 4.110000e+02 |

### get_macro_ha：宏观特色数据-家电数据

数据范围 2015-01-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=212)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-家电数据

```python
import panda_data
result = panda_data.get_macro_ha(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| HA0000008 | 20220131 | 657.9470 |
| HA0000009 | 20220131 | -8.7019 |
| HA0000010 | 20220131 | -8.2639 |

### get_macro_of：宏观特色数据-线下商超数据

数据范围 2021-05-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=213)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-线下商超数据

```python
import panda_data
result = panda_data.get_macro_of(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| OF0000001 | 20220131 | 8847.351547 |
| OF0000002 | 20220131 | 265.422570 |
| OF0000013 | 20220131 | 8847.351547 |

### get_macro_rb：宏观特色数据-招聘数据

数据范围 2021-05-02 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=214)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-招聘数据

```python
import panda_data
result = panda_data.get_macro_rb(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| RB0000001 | 20220102 | 55727.0000 |
| RB0000002 | 20220102 | 134697.0000 |
| RB0000003 | 20220102 | 155573.5439 |

### get_macro_re：宏观特色数据-房地产数据

数据范围 2014-12-18 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=215)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-房地产数据

```python
import panda_data
result = panda_data.get_macro_re(
    start_date="20150101",
    end_date="20200101",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| RE0000484 | 20150101 | 19840.0 |
| RE0000487 | 20150101 | 14458.0 |
| RE0000493 | 20150101 | 21985.0 |

### get_macro_ed：宏观特色数据-电子数据

数据范围 2014-12-06 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=216)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-电子数据

```python
import panda_data
result = panda_data.get_macro_ed(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| ED0000001 | 20220101 | 83.78482 |
| ED0000002 | 20220101 | 102.21254 |
| ED0000003 | 20220101 | 103.94813 |

### get_macro_ep：宏观特色数据-电新数据

数据范围 2015-01-01 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=217)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-电新数据

```python
import panda_data
result = panda_data.get_macro_ep(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| EP0000002 | 20220103 | 1.329 |
| EP0000003 | 20220103 | 0.058 |
| EP0000004 | 20220103 | 0.135 |

### get_macro_ar：宏观特色数据-农业数据

数据范围 2014-12-31 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=218)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-农业数据

```python
import panda_data
result = panda_data.get_macro_ar(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| AR0000524 | 20220101 | 8.65 |
| AR0000525 | 20220101 | 8.40 |
| AR0000526 | 20220101 | 8.00 |

### get_macro_cm：宏观特色数据-大宗数据

数据范围 2021-05-01 ~ 至今；每日更新 23:00 ~ 次日00:00；[官方页面](https://www.pandaaiquant.com/docs/api?id=219)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| symbol | Optional[Union[string, List[string]]] | 否 | 指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |
| fields | Optional[Union[string, List[string]]] | 否 | 返回字段 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| symbol | string | 指标代码 |
| period_date | string | 数据期 |
| data_value | float | 指标数值 |

示例：获取宏观特色数据-大宗数据

```python
import panda_data
result = panda_data.get_macro_cm(
    start_date="20220101",
    end_date="20260430",
)
print(result)
```

返回示例（前 3 行）：

| symbol | period_date | data_value |
|:---|:---|:---|
| CM0000001 | 20220101 | 1101.00 |
| CM0000002 | 20220101 | 1143.00 |
| CM0000004 | 20220101 | 992.00 |

## 宏观经济日历

### get_macro_cal：宏观经济日历

数据范围 2015-01-02 ~ 至今；每日更新 季更；[官方页面](https://www.pandaaiquant.com/docs/api?id=133)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| event_code | Optional[Union[string, List[string]]] | 否 | 日历指标代码，完整指标码表见文件下载 |
| start_date | string | 是 | 开始日期 YYYYMMDD |
| end_date | string | 是 | 结束日期 YYYYMMDD |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| event_code | string | 日历指标ID |
| pub_date_bj | string | 过滤主日期列 |
| event_name_cn | string | 事件中文名 |
| indicator_name_cn | string | 指标中文名 |
| indicator_name_en | string | 指标英文名 |
| pub_date / | string | 当地发布日、时间 |
| pub_time | string | 当地发布时间 |
| pub_time_bj | string | 北京时间 |
| report_period | string | 报告期 / 指标期数 |
| actual_value | float | 当期公布值 |
| consensus_value | float | 预期公布值 |
| previous_value | float | 上期值 |
| last_year_value | float | 上年同期值 |
| importance | integer | 重要性等 |
| unit_cn / unit_en | string | 单位 |
| frequency_cn | string | 频率(中) |
| frequency_en | string | 频率(英) |
| remark_cn | string | 备注(中) |
| remark_en | string | 备注(英) |
| description_cn | string | 描述(中) |
| description_en | string | 描述(英) |
| display_order | integer | 展示顺序 |
| country_code | string | 国家 |
| country_name_cn | string | 地区(中) |
| country_name_en | string | 地区(英) |
| category_cn | string | 分类(中) |
| category_en | string | 分类(英) |
| source_cn | string | 数据源(中) |
| source_en | string | 数据源(英) |

示例：获取经济日历

```python
import panda_data
result = panda_data.get_macro_cal(
    event_code="CHN.001",
    start_date="20260101",
    end_date="20260401",
)
print(result)
```

返回示例（前 3 行）：

| event_code | pub_date_bj | event_name_cn | indicator_name_cn | indicator_name_en | pub_date | pub_time | pub_time_bj | report_period | actual_value | consensus_value | previous_value | last_year_value | importance | unit_cn | unit_en | frequency_cn | frequency_en | remark_cn | remark_en | description_cn | description_en | display_order | country_code | country_name_cn | country_name_en | category_cn | category_en | source_cn | source_en | month |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| CHN.001 | 20160101 | 官方制造业PMI | 制造业PMI | Manufacturing PMI | 20160101 | 09:00:00 | 09:00:00 | 20151231 | 49.7 | NaN | 49.6 | 50.1 | 3 | % | % | 月 | M | None | None | PMI是一个综合指数，由5个扩散指数（分类指数）加权计算而成。具体包括：新订单指数，权数为30%；生产指数，权数为25%；从业人员指数，权数为20%；供应商配送时间指数，权数为15%；原材料库存指数，权数为10%。其中，供应商配送时间指数为逆指数，在合成PMI综合指数时进行反向运算。PMI通常以50%作为经济强弱的分界点，PMI高于50%时，反映制造业经济扩张；低于50%，则反映制造业经济收缩。 | None | 1 | CHN | 中国 | China | 景气指标 | Sentiment indicators | 国家统计局 | National Bureau of Statistics | 201601 |
| CHN.001 | 20160101 | 官方制造业PMI | 制造业PMI:新订单 | Manufacturing PMI: New Orders | 20160101 | 09:00:00 | 09:00:00 | 20151231 | 50.2 | NaN | 49.8 | 50.4 | 3 | % | % | 月 | M | None | None | None | None | 2 | CHN | 中国 | China | 景气指标 | Sentiment indicators | 国家统计局 | National Bureau of Statistics | 201601 |
| CHN.001 | 20160101 | 官方制造业PMI | 制造业PMI:新出口订单 | Manufacturing PMI: New Export Orders | 20160101 | 09:00:00 | 09:00:00 | 20151231 | 47.5 | NaN | 46.4 | 49.1 | 3 | % | % | 月 | M | None | None | None | None | 3 | CHN | 中国 | China | 景气指标 | Sentiment indicators | 国家统计局 | National Bureau of Statistics | 201601 |

## 宏观经济日历信息

### get_macro_cal_info：宏观经济日历信息

数据范围 2015-01-05 ~ 至今；每日更新 季更；[官方页面](https://www.pandaaiquant.com/docs/api?id=135)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| event_code | Optional[Union[string, List[string]]] | 否 | 日历指标代码，完整指标码表见文件下载 |
| start_date | string/None | 是 | 开始日期 YYYYMMDD |
| end_date | string/None | 是 | 结束日期 YYYYMMDD |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| pub_date_bj | string | 北京发布日期 |
| pub_time_bj | string | 北京发布时间 |
| datadate | string | 指标期数 |
| event_code | string | 日历指标代码 |
| indic_name | string | 指标名称 |
| country_code | string | 国家/地区代码 |
| pub_date | string | 当地发布日期 |
| pub_time | string | 当地发布时间 |
| pub_datetime | string | 当地发布日期时间 |
| pub_datetime_bj | string | 当地发布日期时间 |

示例：获取经济日历信息

```python
import panda_data
result = panda_data.get_macro_cal_info(
    event_code="CHN.001",
    start_date="20150101",
    end_date="20260401",
)
print(result)
```

返回示例（前 3 行）：

| event_code | pub_date_bj | indic_name | datadate | country_code | pub_date | pub_time | pub_datetime | pub_time_bj | pub_datetime_bj |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| CHN.001 | 20160101 | 官方制造业PMI | 20151231 | CHN | 20160101 | 090000 | 2016-01-01 09:00:00 | 090000 | 2016-01-01 09:00:00 |
| CHN.001 | 20160201 | 官方制造业PMI | 20160131 | CHN | 20160201 | 090000 | 2016-02-01 09:00:00 | 090000 | 2016-02-01 09:00:00 |
| CHN.001 | 20160301 | 官方制造业PMI | 20160229 | CHN | 20160301 | 090000 | 2016-03-01 09:00:00 | 090000 | 2016-03-01 09:00:00 |

## 宏观经济日历配置

### get_macro_cal_config：宏观经济日历配置

数据范围 2015-01-02 ~ 至今；每日更新 季更；[官方页面](https://www.pandaaiquant.com/docs/api?id=134)

入参：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| event_code | Optional[Union[string, List[string]]] | 是 | 日历指标代码，完整指标码表见文件下载 |

返回字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| event_code | string | 日历指标代码 |
| indic_name | string | 日历事件名称 |
| region_code | string | 国家代码 |
| eco_name_cn | string | 指标中文名 |

示例：获取经济日历配置

```python
import panda_data
result = panda_data.get_macro_cal_config(
    event_code="CHN.001",
)
print(result)
```

返回示例（前 3 行）：

| event_code | indic_name | region_code | eco_name_cn |
|:---|:---|:---|:---|
| CHN.001 | 官方制造业PMI | CHN | 制造业PMI |
| CHN.001 | 官方制造业PMI | CHN | 制造业PMI:新订单 |
| CHN.001 | 官方制造业PMI | CHN | 制造业PMI:新出口订单 |
