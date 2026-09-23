# content-service-python 执行检查点

- 任务：阅读到创作 MVP 的 Python 内容业务内核
- 分支：`codex/content-service-python/reading-mvp`
- 基线：`origin/main@7a6a6641ce0559fa5e7bf2edc176b2d27cabe639`，已合入共享 RPC 契约 `6627324`
- 独占路径：`services/content-service/**`
- 当前步骤：实现 typed DTO、PostgreSQL 五表仓储、业务服务和 gRPC Host。
- 边界：不修改共享 RPC、根配置、M 端、Runtime、部署；不访问现有业务数据库。
- 验证目标：Ruff、strict mypy、单元测试、隔离 PostgreSQL 集成测试、真实 gRPC smoke、`git diff --check`。

