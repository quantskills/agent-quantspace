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
uv run python -m pytest -m smoke -rs -q
```

- 需要本地真实数据目录（`QUANTSPACE_DATA_ROOT`，否则为仓库 `data/`），并包含
  `tests/smoke/runner.py` 中列出的 ETF 行情；缺文件时跳过并列出缺失文件。
- 绝不写入真实数据目录。会话 fixture 把所需文件裁剪到最近若干行后复制到临时目录，所有命令都对副本运行；
  运行前后还会比对源文件的路径、大小和修改时间。
- 断言只做合理性检查（退出码、产物非空、关键数值有限、权重不超预算），不对真实数据做等值断言。
- 没有合适本地输入的命令在 `tests/smoke/coverage.py` 中写明跳过原因。默认测试里有一道守卫：
  某个不联网命令既没有冒烟步骤、也没有列入该清单时，默认测试会失败。

## 范围

测试应使用合成数据或内存数据（可选的冒烟测试除外）。不要添加依赖私有数据、凭证、私有策略域或外部服务的测试。
