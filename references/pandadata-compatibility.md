# Pandadata 1.0.6 compatibility / 兼容说明

This project targets `panda_data==1.0.6` (Python 3.10+). Keep the project's existing installation workflow and optional dependency profiles; use the root requirements file when one is supplied.

本项目的 Pandadata 调用以 1.0.6 为目标；来源、固定 commit 和方法清单见 `pandadata-compatibility.json`。共享 CI 检查方法、参数与版本声明；动态调用及业务字段仍由项目测试覆盖。未执行生产账号登录和线上取数，不能将离线通过视为数据权限或服务端可用性证明。

Read the exact method contract before changing queries. Use configured credentials and service URLs; never commit credentials. Preserve empty-data and failure status instead of substituting invented results. Existing research assumptions and investment-risk boundaries remain applicable.

Cursor、Claude Code、Codex、Hermes、OpenClaw 均从本项目的共享入口读取本说明；保留现有 runtime adapters 和支持文件。

升级记录维护：abgyjaguo。Canonical reference: https://github.com/quantskills/skill-pandadata-api
