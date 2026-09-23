# 内容业务服务：隔离验收记录

日期：2026-09-23。全部数据为人工测试素材，不含真实用户内容。

## 范围

独立 Python 内容业务服务，12 个强类型 gRPC 方法、PostgreSQL 五张业务表、共用可信身份上下文。M 端配置、模型调用、Chat 卡片、Workflow 和公网部署不在本次通过范围。

## 验证分层

- Protobuf：6 项合同检查通过，确认 signed 64-bit userId、字段 presence、结构化正文和分页响应。
- 静态质量：内核及 RPC、独立探针联合 strict mypy（9 文件）、Ruff、git diff --check 通过。5 内核单测通过，wheel 清单包含迁移 SQL。
- PostgreSQL：专用临时 PostgreSQL 容器，无网络、128MiB 上限、最多 8 连接。真实创建项目、素材版本、观点、选题、稿件、确认和导出通过；失败确认回滚、重复请求、CAS、跨用户、跨项目与环境不匹配拒绝通过。
- 独立 RPC：`deploy/content_service/verify_rpc.py` 返回 `CONTENT_RPC_PASS: 12 methods, confirmations, replay, owner isolation, CAS, environment, export`。只允许明确开启隔离写入且目标为 loopback。
- 重启读取：停止并重新启动 Python host，读取先前落库的项目、当前确认与稿件；恢复了已修改选题和正文，返回 `CONTENT_RESTART_READ_PASS`。没有重启 PostgreSQL，因此不冒称数据库故障恢复验收。
- 联调修正：环境不匹配原为 409/ABORTED，改为 403/PERMISSION_DENIED 后完整 RPC 探针复验通过；没有放宽测试接受结果。

## 安全与发布边界

没有修改线上数据库或导入 M 资产，没有调用真实模型和第三方内容平台。服务启动只读检查表结构，迁移需显式执行。生产模式要求客户端证书；本次业务联调使用隔离 loopback，尚不能证明生产证书与部署组装已完成。

未进行浏览器验收，不能称为阅读创作产品已经上线。后续先完成 Python 通用执行层接入，再通过真实 M 页面建立并发布三组 Skill/Application/能力，最后验收独立 Chat 和三节点 Workflow。
