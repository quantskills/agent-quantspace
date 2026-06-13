# QuantSpace

[English README](README.md)

QuantSpace 是一个以 PandaData 为优先数据源的量化研究工作台。它采用
“轻核心 + 可复用 skills + 示例策略域”的结构，既可以由 AI coding agent 组合使用，
也可以由研究员直接通过 Python 脚本调用。

这个仓库定位为干净的开源核心：数据接入、本地 Parquet 存储、特征与标签生成、
因子分析、组合构建、报告生成和示例回测。

## 包含什么

- 通过 `skills.ingest` 接入 PandaData/PandaAI。
- 通过 `skills.store.data_manager.DataManager` 管理本地数据和研究产物。
- 通用 OHLCV 指标、数学工具、时间序列特征和公开标签生成器。
- 横截面和时间序列研究可用的 generic 因子示例。
- 分析、构建、研究筛选、模型和报告相关 skills。
- 两个公开策略域：
  - `strategies.cross_sectional`：ETF 风格横截面轮动示例。
  - `strategies.time_series`：使用三重屏障标签的单品种 ML 示例。
- 用于 smoke test 的确定性 fixture 数据生成器，以及可直接运行的 demo 脚本。

## 不包含什么

- 私有策略研究、专有 alpha 逻辑、私有 notebooks 或真实研究报告。
- 私有市场数据、账号凭证或本机绝对路径。
- PandaData 之外的数据商 adapter 或远程执行工具。
- 生产交易、券商接入或实盘下单管理。
- 私有标签实验。

## 项目结构

```text
quantspace/
  skills/                 可复用能力
    ingest/               PandaData 客户端和符号转换
    store/                本地 Parquet 存储和产物管理
    compute/              指标、特征、标签、generic 因子示例
    analyze/              因子分析、指标、归因、tearsheet
    construct/            权重、过滤器、策略组合
    model/                ML 辅助模块和可选模型引擎
    research/             因子筛选、参数扫描、策略比较
    report/               HTML/Markdown 报告渲染和图表工具
  strategies/
    cross_sectional/      generic 横截面轮动
    time_series/          单品种时间序列 ML workflow
  scripts/                样本数据、demo、PandaData 导入脚本
  data/                   本地数据根目录；只提交 sample pool
  reports/                本地生成报告目录
  docs/                   架构、数据布局、示例、边界说明
  tests/                  公开 pytest 测试
```

## 快速开始

环境要求：

- Python `>=3.10`
- `uv`

安装默认环境。为了做自包含的 smoke test，可以先生成一份小型 fixture 数据，再运行 demo：

```bash
uv sync
uv run python scripts/generate_sample_data.py
uv run python scripts/run_cross_sectional_demo.py
uv run python scripts/run_time_series_demo.py
uv run python -m pytest tests/
```

fixture 数据是确定性的合成 OHLCV，会写入 `data/market/`，可以随时重新生成。
真实研究运行时，应使用 PandaData 导入或自行放入真实日线 Parquet 覆盖这批 fixture。

可选 extras：

```bash
uv sync --extra panda_data  # PandaData SDK
uv sync --extra ml          # 可选 PyCaret ML 辅助模块
uv sync --extra ts          # 可选时间序列特征依赖
uv sync --extra query       # 可选 DuckDB 查询能力
```

## PandaData 设置

安装可选的 PandaData SDK 依赖：

```bash
uv sync --extra panda_data
cp .env.example .env
```

在 `.env` 中填写：

```bash
PANDA_DATA_USERNAME=86xxxxxxxxxxx
PANDA_DATA_PASSWORD=your-password
```

运行导入示例：

```bash
uv run python scripts/import_panda_data_demo.py \
  --symbol SHSE.600000 \
  --start-date 20230101 \
  --end-date 20231231
```

QuantSpace 的符号格式是 `EXCHANGE.CODE`，例如 `SHSE.510300`。
PandaData 格式可以通过下面的 helper 转换：

```python
from skills.ingest import to_panda_data_symbol, to_quantspace_symbol

to_panda_data_symbol("SHSE.510300")  # "510300.SH"
to_quantspace_symbol("510300.SH")    # "SHSE.510300"
```

## 数据模型

市场数据按单 symbol 存成 Parquet：

```text
data/market/{frequency}/{symbol}.parquet
```

每个 OHLCV frame 以 `eob` 为索引，列为：

```text
open, high, low, close, volume
```

Pool 定义放在 `data/pools/`：

```json
{
  "pool_id": "sample_etf_rotation",
  "description": "ETF-style pool for public examples",
  "frequency": "1d",
  "symbols": ["SHSE.510300", "SHSE.510500"]
}
```

`DataManager.load_pool_data(pool_id)` 会返回 MultiIndex 为 `(symbol, eob)` 的 panel。

如果希望把数据放到仓库之外，可以设置 `QUANTSPACE_DATA_ROOT`。

## 策略示例

### 横截面轮动

流程：

```text
panel OHLCV -> generic factors -> top-percent selection -> execution -> metrics
```

运行：

```bash
uv run python scripts/run_cross_sectional_demo.py
```

该示例通过 `strategies.cross_sectional.ModularBacktester` 组合简单动量和低波动因子，
数据来自配置好的 sample pool 对应的 `data/market/1d/` 日线 Parquet。

### Time-Series ML

流程：

```text
raw OHLCV bars -> feature engineering -> triple-barrier labels -> model -> backtest
```

运行：

```bash
uv run python scripts/run_time_series_demo.py
```

该示例使用 `strategies.time_series.features.make_price_volume_features`、
`TripleBarrierLabelMaker`、一个小型 scikit-learn 分类器、date × symbol 权重矩阵和
`skills.analyze.backtest.VectorBacktester`，数据来自已有单品种日线 Parquet。

### 示例策略报告

```bash
uv run python scripts/run_strategy_reports.py
```

该薄编排脚本会读取 `data/market/1d/` 下已有的 PandaData 日线 Parquet，并在
`reports/strategy_examples/` 下写出 4 份公开策略报告和绩效图。横截面和时序两个域各包含一个规则类策略和一个 XGBoost 机器学习策略。策略逻辑放在 `strategies/`，存储、回测指标、权重和报告 helper 放在 `skills/`。

## 公开 Skills

| Skill | 主要导入 | 用途 |
|---|---|---|
| `ingest` | `from skills.ingest import PandaDataClient` | PandaData 接入和符号转换 |
| `store` | `from skills.store.data_manager import DataManager` | 市场数据、pool、因子、回测、元数据 |
| `compute` | `from skills.compute.indicators import trend_score` | 指标、特征、标签、generic 因子示例 |
| `analyze` | `from skills.analyze.backtest import VectorBacktester` | 向量化回测、IC、分组收益、指标、tearsheet |
| `construct` | `from skills.construct.weighting import WEIGHT_METHODS` | 权重方法和组合过滤器 |
| `model` | `from skills.model.ml_engine import MLEngine` | 可选 ML 辅助模块 |
| `research` | `from skills.research import screen_all_indicators` | 因子筛选和参数扫描 |
| `report` | `from skills.report import ReportRenderer` | HTML/Markdown 报告渲染和图表工具 |

每个 skill 目录都有自己的 `SKILL.md` 使用说明。

## 文档索引

- [架构](docs/architecture.md)
- [数据布局](docs/data_layout.md)
- [示例](docs/examples.md)
- [PandaData 接入](docs/panda_data_ingest.md)
- [开源边界](docs/open_source_scope.md)
- [私有扩展方式](docs/private_extension_pattern.md)

## 开发与验证

运行公开测试：

```bash
uv run python -m pytest tests/
```

发布前建议运行测试套件，并执行 release safety scan，检查私有路径、凭证、
私有策略名称和已经移除的研究型模块是否误入仓库。

生成的数据和报告应留在本地。开源仓库只应提交代码、文档、测试、sample pool 定义和小型模板。

## 私有扩展方式

建议把私有研究放在单独仓库：

```text
workspace/
  quantspace/
  quantspace-private/
```

通用能力可以从私有仓库沉淀回本仓库；专有策略域、私有数据 adapter、alpha 研究、
notebooks 和生成报告不要进入开源仓库。

## License

正式发布到公开代码托管平台或包索引前，请补充项目许可证。
