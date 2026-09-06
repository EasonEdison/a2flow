# 业务能力注册平台 Phase 1 对齐提案

## 状态

- 基线：SW-P1-20260907.2
- 基线提交：`b1a0c9f32497c04dd623edb0bb8858a01b5ae7ad`
- 已读集成 SHA：`c168f2c3b7f86cb0bd5e2bec48caf4ec1de1df7e`
- 设计状态：PROPOSED / BASELINE ALIGNED
- Contracts 候选：`SW-CONTRACTS-P1-CANDIDATE.1`，仍为 PROVISIONAL
- 实现放行：等待 main-brain 命名 approved contracts revision
- Runtime：NO READY

## 目标

M 侧业务能力注册平台负责能力元数据、参数/结果契约、发布前验证和成功判定配置。B 侧 Runtime 通过统一 `execute_ability` Tool 调用已授权能力，真实业务适配器位于 Runtime 核心之外。

本阶段先收敛消费共享契约的需求，并提供独立合成的调用、失败、结果样例；不实现真实外部写、不抢写共享 schema、不部署。

## 已接受边界

- Runtime 固定使用 Python + Deep Agents SDK + LangGraph；ENG-01 已选定 Capability Registry 为独立 Python 域模块，但不要求独立常驻服务。
- 已读 PY-01：必要时可替换/升级系统 Python，但唯一执行负责人是 Runtime；本任务不操作系统 Python，也不再把授权缺失当作 blocker。
- PostgreSQL-only，PRT 与 ONLINE 使用分离数据库，不提供 SQLite/MySQL 或跨环境 fallback。
- `userId` 是唯一用户/灰度身份；模型不得提供 userId、环境、凭证或生效版本。
- PRT 只解析 PRT 当前版本；ONLINE 只解析 ONLINE stable/gray，灰度也不得读取 PRT。
- `execute_ability` 必须复用共享可信上下文、配置解析和轻量版本失配门禁。
- 配置版本不匹配时，在业务调用前阻断并提示全新 reset；不得继续旧版本、静默迁移或自动重放。
- Runtime/Workflow 不拥有业务幂等、业务重试、对账、补偿或跨 run 去重；这些属于被调用 API 后端。

## 从旧方案移除的冲突

| 旧活动设计 | 修订结论 |
| --- | --- |
| Runtime 语言仍“待统一裁决” | 改为已接受 Python + Deep Agents SDK + LangGraph |
| Registry/Runtime 按 READ_ONLY/IDEMPOTENT_WRITE 自动重试 | 首版移除通用业务调用自动重试；业务幂等/重试归 API 后端 |
| 以 `effectState` 推导平台重试安全 | 只保留可观测调用结果，不把推导结果变成自动重试授权 |
| 缺少 PRT/ONLINE、userId 灰度规则 | 增加共享 resolver 输入/输出和禁止跨环境读取 |
| 精确 releaseRef 可由调用方直接选择 | 模型只能选已暴露的 abilityKey；生效版本由可信 resolver 决定 |
| 输出 schema 合法即等于业务成功 | 分离 schema 合法、配置成功判定和 A2UI 交互完成 |

## 首个可执行切片

1. 修订本 change 的 `execute_ability`、授权、版本、成功判定和失败边界。
2. 在 `services/capability-registry/` 放置不依赖共享实现的合成契约样例和轻量校验。
3. 向 contracts/Runtime/A2UI 提供消费者需求，不实现竞争性的共享契约。
4. main-brain 命名审核通过的共享契约 revision 后，再实现最小 registry 代码切片。

## 成功解释器归属建议

建议只保留一个解释器实现：

- `oss-platform-contracts` 单一拥有 `ResultInterpretationPolicy` 的共享 schema 和稳定语义；当前候选 revision 为 `SW-CONTRACTS-P1-CANDIDATE.1`。
- Capability Registry 在 ability release 的 `resultInterpretationPolicies` array 中发布带唯一 `policyRef` 的命名策略，并保证 `defaultSuccessPolicyRef` 可解析。
- A2UI 对精确 ability release 选择 `successPolicyRef`，并独立拥有 `completeInteractionOnSuccess`；不嵌入第二套表达式 DSL，也不再创建 `ResultConditionRef`。
- Runtime 在 adapter 输出通过 schema 后执行唯一解释器，返回结构化判定证据；Runtime 不把业务失败自动改成 Skill/Workflow 成功。

首版策略只支持以下两个 operator，不支持 ANY/ALL、NOT_EQUALS、脚本、任意表达式或模型判定：

- `SCHEMA_VALID`：策略包含 `contractRevision`、`policyRef`、`operator`。
- `JSON_POINTER_EQUALS`：额外包含 `jsonPointer` 和 JSON primitive 类型的 `expectedLiteral`。

JSON Pointer 解析必须区分 `MISSING` 与 `FOUND(null)`：`MISSING` 永不匹配并报告 `PATH_MISSING`；`FOUND(null)` 可与 JSON null 比较。字符串、数字、布尔值和 null 只按同类型同值比较，不做隐式转换。

解释结果分别记录 output schema validity、policy match、Action call 和 interaction completion；Finalizer 不能覆盖任何失败事实。

## 模块所有权

| 所有者 | 输入 | 输出 | 不负责 |
| --- | --- | --- | --- |
| Capability Registry | 共享发布/环境契约、管理员草稿 | ability payload、schema、命名成功策略、credential requirements | Runtime 调度、真实 API 调用、业务幂等 |
| Shared Contracts | 通用消费者需求 | trusted context、环境 resolver、release/version、授权/错误/成功策略 schema | 领域适配器 |
| Runtime | 模型参数、可信 ToolRuntime context、发布能力 | 一次受控调用及结构化结果 | M 侧发布、业务后端重试 |
| A2UI Registry | Action 配置、能力/策略引用 | Action 成功选择与交互完成配置 | 能力结果解释器实现 |
| API Backend / Adapter | resolved input、credential ref | 外部调用与业务结果 | 资产发布和 Workflow 状态 |

## 非目标

- 不实现企业 API 平台、真实业务写、凭证中心或任意脚本执行。
- 不新增通用业务调用 retry engine、exactly-once 承诺或 Workflow 补偿。
- 不抢写共享包、根 pyproject/lock 或精确进程部署拓扑；本 change 只记录本域 Python 模块边界与依赖需求。
- 不部署、不修改服务/数据库/端口、不配置 secret。

## 公开依据

- Deep Agents customization：<https://docs.langchain.com/oss/python/deepagents/customization>
- LangChain Tools/ToolRuntime：<https://docs.langchain.com/oss/python/langchain/tools>
- JSON Schema 2020-12：<https://json-schema.org/draft/2020-12>
- RFC 6901 JSON Pointer：<https://www.rfc-editor.org/rfc/rfc6901>
