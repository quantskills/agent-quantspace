---
source: https://www.pandaaiquant.com/docs/api
title: PandaAI Data API - Overview and SDK Setup
extracted: 2026-11-21
---

# 数据概述与 SDK 安装

按官方“数据概述”和“数据调取文档”两页整理。

## 覆盖范围

- 中国 A 股：只含上交所、深交所的股票和指数。
- 中国期货：代码后缀用 CTP 标准的三位交易所代码：`CFE`（中金所）、`SHF`（上期所）、`DCE`（大商所）、
  `CZC`（郑商所）、`INE`（上海国际能源交易中心）、`GFE`（广期所）。例如 `RB2701.SHF`、主力连续 `RB_DOMINANT.SHF`。
- 港股：代码加 `.HK` 后缀（如 `0700.HK`）。美股：代码加 `.NB` 后缀（如 `AAPL.NB`）。
- 股票池（`get_stock_daily` 等的 `indicator` 参数）：`000300` 沪深300、`000905` 中证500、`000906` 中证800、
  `000852` 中证1000、`000016` 上证50、`399006` 创业板指、`000688` 科创50 等。

## 安装与升级

需要 Python 3.10+，并已在 PandaAI 官网注册、购买 PandaData 数据服务。

```bash
pip install panda_data
pip install panda_data -i https://pypi.tuna.tsinghua.edu.cn/simple   # 网络超时时用国内源
pip install panda_data --upgrade
pip show panda_data
```

本仓库用 `uv sync --extra panda_data` 安装，版本下限见 `pyproject.toml`（当前 `panda_data>=1.0.7`）。
旧版 SDK（0.0.x）缺少 `get_stock_min_post`、`get_fund_min`、`TickStreamClient` 等接口。

## 认证

账号是 86 加官网注册手机号（如 `8617777777777`），密码与官网一致。

```python
import panda_data

panda_data.init_token(username="你的86开头手机号", password="你的官网密码")
result = panda_data.get_stock_daily(
    symbol=["000001.SZ"],
    start_date="20250101",
    end_date="20250131",
    fields=["open", "high", "low", "close", "volume"],
)
```

本仓库不在代码里写账号：`PandaDataClient` 从环境变量或 `.env` 的 `PANDA_DATA_USERNAME`、
`PANDA_DATA_PASSWORD` 读取，并在第一次调用时执行 `init_token`。

## 按数据类型用专门的接口

官方文档为每类数据提供专门的函数，不再列出通用的 `get_market_data`、`get_market_min_data`。
通用接口请求期货数据时会报 200103“API访问权限不足”，即使账号已开通期货权限。

| 数据 | 日线 | 分钟线（1m/5m/15m/60m） | 实时 |
|:---|:---|:---|:---|
| A 股股票 | `get_stock_daily`、`_pre`、`_post` | `get_stock_min`、`_pre`、`_post` | `WsTickCN` |
| 指数 | `get_index_daily` | `get_index_min`（只有 1m） | — |
| 期货 | `get_future_daily`（含结算价）、`get_future_daily_post`（主力后复权） | `get_future_min` | `WsTickFuture` |
| 场内基金（ETF、LOF） | `get_fund_daily`、`_pre`、`_post` | `get_fund_min` | `WsTickCNETF` |
| 港股、美股 | `get_hk_daily*`、`get_us_daily*` | — | — |

日线和分钟线都在收盘后批量更新，每个接口页面写了“每日更新”时间（例如股票分钟线 15:57–16:17、
期货分钟线 16:41–17:01、ETF 分钟线 22:00–23:00），盘中拿不到当天的 K 线。盘中数据只有 `WsTick*` 实时订阅，
需要单独开通。

## 本目录的文件

| 文件 | 内容 |
|:---|:---|
| `pandaai-02-trading-tools.md` | 交易日历、前 n 个交易日、ST、停牌、在售股票列表 |
| `pandaai-03-a-share-market.md` | A 股日线、周线、月线、分钟线（含复权）、实时订阅；指数日线、分钟线 |
| `pandaai-04-a-share-reference.md` | 股票、指数基本信息；行业、概念；指数权重、估值 |
| `pandaai-05-a-share-trading-ipo-bonds.md` | 龙虎榜、融资融券、沪深股通、资金流；新股；可转债 |
| `pandaai-06-a-share-corporate.md` | 公司行为、股东行为、股东结构 |
| `pandaai-07-a-share-financials.md` | 业绩预告、财务快报、财务报告、审计意见 |
| `pandaai-08-futures.md` | 期货日线、分钟线、主力后复权、实时订阅；合约信息；主力合约 |
| `pandaai-09-futures-deepview.md` | 席位、持仓、基差、仓单、库存、期限结构等 |
| `pandaai-10-options.md` | 期权基本信息、日线、波动率、交易统计 |
| `pandaai-11-factors-adjustment.md` | 回测因子、复权因子、Barra 风格因子、无风险利率 |
| `pandaai-12-hk-us.md` | 港美股行情、基本信息、公司事件、股东、财务、ETF、指数、轮证 |
| `pandaai-13-funds-etf.md` | 基金基本信息、日线、分钟线、ETF 申赎与分红、持仓与业绩 |
| `pandaai-14-macro.md` | 中国与国际宏观指标、行业宏观、特色数据、经济日历 |
| `pandaai-15-preferred-stock.md` | 优先股 |
