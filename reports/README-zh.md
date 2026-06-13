# Reports

[English README](README.md)

这个目录用于存放本地生成的研究输出。

不要把私有报告、回测结果 dump、生成图表或研究日志提交到公开仓库。

`strategy_examples/` 子目录是例外：这里存放基于 `data/market/1d/` 下已有日线
Parquet 生成的脱敏公开 Markdown 报告和绩效 PNG。

## 用途

- `skills.report` 生成的 HTML/PDF 报告。
- 实验过程中生成的本地图表、表格和诊断文件。
- notebooks 或 scripts 的临时产物。
- `strategy_examples/` 下的公开示例策略 Markdown 报告和 PNG 图表。

公开提交时应保持该目录干净。如果某个输出确实需要作为测试 fixture 或文档素材，应放入对应的测试或文档目录，并使用小型、脱敏样本。
