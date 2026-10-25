# Tests

[English README](README.md)

这个目录存放 QuantSpace 的公开 pytest 测试。

测试目录应镜像源码边界，方便大型项目中按模块维护测试：

```text
tests/skills/          skills/ 的单元测试
tests/strategies/      strategies/ 的单元测试
tests/scripts/         脚本入口测试
tests/integration/     本地端到端流程
tests/contracts/       public API 和数据契约测试
tests/regression/      确定性行为回归测试
tests/docs/            文档示例 smoke test
tests/policy/          测试目录和工作区规则测试
tests/smoke/           基于本地真实数据的 qs 冒烟测试（可选，见“冒烟测试”）
tests/fixtures/        确定性 fixture builder
```

Skill 测试使用当前公开 skill 集：

```text
tests/skills/analyze/
tests/skills/backtest/
tests/skills/compute/
tests/skills/ingest/
tests/skills/ml/
tests/skills/report/
tests/skills/store/
tests/skills/strategy/
```

当前没有 `tests/skills/construct/` 或 `tests/skills/model/` 目录；组合构建在
`backtest` 下测试，模型 helper 在 `ml` 下测试。可复用横截面/时序策略类型在
`strategy` 下测试，具体策略行为仍放在 `tests/strategies/`。

测试覆盖导入边界、工作区结构、PandaData 符号转换、离线 tick ingest helper、公开标签生成器、本地存储、generic 因子示例，以及两个公开策略路径。

## 运行

```bash
uv run python -m pytest tests/
uv run python -m pytest tests/skills tests/strategies -q
uv run python -m pytest tests/contracts tests/regression tests/docs -q
```

不要新增根目录级 `tests/test_*.py` 文件。新增测试应放到匹配的源码边界目录下。

## 冒烟测试

`tests/smoke/` 以子进程方式运行已安装的 `qs` 脚本，在本地真实行情数据上覆盖全部不联网命令。
它默认不运行：默认测试会把它们报告为 skipped，只有 `-m` 表达式包含 `smoke` 才会启用。

```bash
uv run python -m pytest -m smoke -rs -q                    # 全部，约 20 分钟
uv run python -m pytest -m "smoke and not research" -rs -q # 只跑 qs 命令，约 2 分钟
```

- 需要本地真实数据目录（`QUANTSPACE_DATA_ROOT`，否则为仓库 `data/`），并包含
  `tests/smoke/runner.py` 中列出的 ETF 行情；缺文件时跳过并列出缺失文件。
- 绝不写入真实数据目录。会话 fixture 把所需文件裁剪到最近若干行后复制到临时目录，所有命令都对副本运行；
  运行前后还会比对源文件的路径、大小和修改时间。
- 断言只做合理性检查（退出码、产物非空、关键数值有限、权重不超预算），不对真实数据做等值断言。
- 课程与研究复现脚本（lesson 06/07、prompt 测试、均线交叉报告、ETF18 因子挖掘等）在
  `tests/smoke/test_research_scripts.py` 中按默认参数原样运行，带 `research` 标记。它们需要
  18 只大类资产 ETF 的完整 `1d_adj` 历史（不裁剪，复制到临时目录），以 `python -m <module>`
  方式在临时工作目录运行，使用临时数据根和临时 reports 根；另有一道守卫，仓库 `reports/`
  目录一旦变化就让测试失败。冒烟测试的 12 到 24 分钟（取决于机器负载）几乎都花在这些脚本上，
  其中 governed 因子挖掘的 final 阶段一项就要 8 到 14 分钟；终端汇总会列出每个脚本的耗时。
- 没有合适本地输入的命令在 `tests/smoke/coverage.py` 中写明跳过原因。默认测试里有一道守卫：
  某个不联网命令既没有冒烟步骤、也没有列入该清单时，默认测试会失败。依赖可选包的命令
  （`store query` 需要 `duckdb`）保留冒烟步骤并列入 `OPTIONAL_DEPENDENCY`，只有模块无法导入时
  该步骤才跳过。
- 测试在解释器旁查找 `qs` 脚本（Windows 上是 `qs.exe`），并让子进程以 UTF-8 输出
  （`PYTHONUTF8=1`），见 `tests/fixtures/console.py`。

## 范围

测试应使用合成数据或内存数据（可选的冒烟测试除外）。不要添加依赖私有数据、凭证、私有策略域或外部服务的测试。
