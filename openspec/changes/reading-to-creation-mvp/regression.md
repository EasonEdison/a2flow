# 内容业务服务：隔离验收记录

## 2026-09-24：Python 通用能力执行内核增量

`services/capability-execution` 的类型合同、参数校验/绑定、执行器与注册 Protobuf 传输已联合验证：20 项测试通过，strict mypy（5 个模块）及 Ruff 通过。组合测试实际经过执行器映射与 loopback gRPC，验证 userId 精确传输及请求/响应拒绝边界；额外修复已有 null 值被嵌套路径静默覆盖的问题。

这里的 gRPC 下游为测试 ContentService，不是数据库内容服务或真实模型。没有入站 host、发布库 resolver、引擎切流、线上写库和浏览器验收；不要将本批解释为“全链已迁到 Python”。迁移边界详见 python-execution.md。本次测试端口在测试结束时自动关闭，无持久容器或外部业务请求。

日期：2026-09-23。全部数据为人工测试素材，不含真实用户内容。

## 2026-09-24 Python 能力链路新增证据

- 47 项 capability tests PASS；strict mypy 10 source modules、探针 1 文件及 Ruff PASS。
- 实际隔离 PostgreSQL，按照 M writer 结构合成 root/RELEASE_RECORD 和 compact version；不是浏览器作者发布证据。
- 两个真实 Python gRPC Host：发布读取 → 编译 → Execute → ContentService.CreateProject → 内容数据库落库 PASS。
- 最大 signed64 userId 原样传递、requestId 重放、跨用户隔离 PASS。
- 发布改到 build-2 后旧 sourceId/digest 被 FAILED_PRECONDITION 拒绝，项目数未增加 PASS。
- PRT 缺指针不读取 ONLINE；ONLINE compact版本恢复、百分比与最大/最小 signed64/白名单选择 PASS。
- 拆分 recordJson 篡改后摘要校验拒绝 PASS。
- Review 补充：Resolve 提前校验完整 descriptor；坏契约不能先 Resolve 成功再到 Execute 才发现。非字符串 inputDigest/grayStatus 拒绝，空白摘要保持 Java 正常兼容语义。
- 临时测试 Host、容器仅用于隔离验证；生产监听、资产、用户数据和页面均未更改。mTLS 生产证书握手不在本次通过范围。

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
