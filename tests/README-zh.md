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
tests/fixtures/        确定性 fixture builder
```

测试覆盖导入边界、工作区结构、PandaData 符号转换、离线 tick ingest helper、公开标签生成器、本地存储、generic 因子示例，以及两个公开策略路径。

## 运行

```bash
uv run python -m pytest tests/
uv run python -m pytest tests/skills tests/strategies -q
uv run python -m pytest tests/contracts tests/regression tests/docs -q
```

不要新增根目录级 `tests/test_*.py` 文件。新增测试应放到匹配的源码边界目录下。

## 范围

测试应使用合成数据或内存数据。不要添加依赖私有数据、凭证、私有策略域或外部服务的测试。
