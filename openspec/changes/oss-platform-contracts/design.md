# Phase 1 公共契约设计

## 0. 状态与所有权

- Authority: `SW-P1-20260907.2 + ENG-01`
- Design: `PROVISIONAL / MAIN-BRAIN REVIEW PENDING`
- Runtime: `NO READY`
- Exclusive paths: `openspec/changes/oss-platform-contracts/`, `packages/contracts/`

本任务单一拥有公共候选 Schema。四个 M 域拥有各自资产 payload、校验和作者态；Runtime 拥有执行状态机；A2UI 域拥有展示/交互成功配置；数字员工拥有 UI 和业务适配。公共层不复制这些状态机。

## 1. 语言与打包建议

首轮以中立 JSON Schema + 合成 examples 作为跨语言真值，放在 `packages/contracts/`。ENG-01 允许后续在同一路径增加薄 `skillweave_contracts` Python 包；Runtime 已实测 Python 3.11.13/Pydantic 2.13.5，建议兼容范围为 Python `>=3.11,<4`、可选 Pydantic `>=2.13,<3`，精确 patch 由根 lock 固定。最小包只含 `models.py`、`schema_loader.py`、`py.typed` 等 schema/model 适配，不依赖 Deep Agents、LangGraph、PostgreSQL driver 或 Runtime adapter。模块局部 pyproject 需待批准 revision 与主控授权，不能自带第二份 lock。React/TypeScript 端可在根构建方案确定后生成只读类型。

本任务不修改根 manifest、lockfile 或协议依赖，不固定 HTTP/SSE/AG-UI/A2UI/事件总线版本。

## 2. 可信上下文

候选 `TrustedContext`：

~~~json
{"userId":"user_demo_001","environment":"ONLINE"}
~~~

- `userId` 是唯一身份与灰度术语；没有 sellerId alias。
- `environment` 只允许 `PRT` 或 `ONLINE`。
- 可信上下文由服务端认证/路由边界构造并以进程内参数传给 resolver/Tool 执行器。
- Tool 对模型暴露的参数 Schema 不得包含 `userId`、`environment`、凭证或权限；即使业务 payload 出现同名字段，也不能覆盖可信上下文。
- 权限判定和密钥传递在服务端完成，不把角色、token 或 credential 固化进资产/事件 payload。

JSON Schema 只能校验形状，不能证明 provenance；服务端注入与 override 拒绝必须由后续集成测试证明。

## 3. `use_skill` 服务端 envelope

模型可见请求只允许 `{skillKey}`。服务端在模型参数之外构造 `TrustedInvocationContext={trustedContext,invocationScope,controlRequestId}`；conversation scope 绑定 conversationId，Workflow scope 至少绑定 runId/nodeId。

`skillKey` 是 Skill 在公共契约中的唯一逻辑 identity，使用小写字母/数字/连字符和可选的 `/` 分段（例如 `route-fast` 或 `demo/route-fast`）。Workflow/其他域不得保存 `skill:route-fast` 后让 Runtime 拆前缀；如领域内保留通用 logicalRef，必须在发布边界通过显式 typed mapping 转换成 exact `skillKey`。

候选返回遵循 `content + artifact` 分层，但是否直接映射 Deep Agents `content_and_artifact` 由 Runtime spike 证明：

- `content={instructions,resources,requiredToolNames?}`；resource 是 `READ_ONLY`、digest-bound opaque handle，并携带规范化的包内相对 `logicalPath`（例如 `references/output-format.md`）；不含服务器绝对路径、URL、凭证或执行权限。
- `requiredToolNames` 只是兼容性提示，不能让 Runtime 动态授权或开放 Tool。
- `artifact={skillKey,resolvedVersion,contentDigest,environment,selection,evidenceRef}`；版本与 resolver evidence 不由模型提供。
- `resolvedVersion.asset.assetType=SKILL` 已表达类型，不在 artifact 顶层重复 assetType。

同一 Skill package 在 chat/Workflow 使用相同内容，不增加 routing、next-node 或 Workflow-specific output。Schema PASS 不证明 artifact 不进入模型输入、Checkpoint 可恢复或跨进程 PostgreSQL reopen；这些由 Runtime 验证。
## 4. 资产版本、历史与 serving 状态

公共 `AssetRef` 由 `{assetType, assetId}` 组成。候选 `assetType`：`SKILL`、`ABILITY`、`COMPONENT`、`APPLICATION`、`WORKFLOW`；最终枚举以六域审查为准。`AssetVersionRef` 增加不可空 `versionId`，但不强制 UUID/SemVer 生成算法。

历史资产版本与当前 serving 状态是不同集合：

| 环境 | 当前可服务版本 | 数据来源 | 灰度选择 |
| --- | --- | --- | --- |
| PRT | 一个 `currentVersionId` | PRT 数据库 | 无 |
| ONLINE | 一个 `stableVersionId`；灰度期间可再有一个 `candidateVersionId` | ONLINE 数据库 | 可信 `userId` |

ONLINE 不能出现第三个 serving version；这是活动 serving 限制，不是历史保留限制。灰度结束只改变 serving 指针/状态，不删除旧版本记录。

`AssetResolution` 返回：可信上下文、AssetRef、`effectiveVersionId` 与 `selection`。候选 selection 为 `PRT_CURRENT`、`ONLINE_STABLE`、`ONLINE_GRAY`。结构必须保证 PRT 只能对应 `PRT_CURRENT`，ONLINE 只能对应两个 ONLINE selection；没有跨库 fallback。

`AssetServingState` 带 `servingRevision`。单一 `AssetPublicationRequest` 以 controlRequestId、payloadDigest、expectedServingRevision 做并发保护：PRT 只能写 `PRT_CURRENT`，ONLINE 只能写 `ONLINE_STABLE` 或 `ONLINE_CANDIDATE`。它适用于所有 assetType，不是四套发布服务。

四个 M 域调用同一 publication/resolver 端口或模块；不得各自复制环境、灰度或版本选择算法。其实现位置和部署形态待 main-brain 评审。

## 5. 版本比较和入口拒绝

`RecordedAssetVersion` 保存某次已接受工作所见的 AssetVersionRef。执行、继续、node-bound input、interaction Action、A2UI retry 入口先调用 resolver，再生成 `VersionGuardDecision`：

- 所有 recorded/effective version 相同：`ALLOW`，`mismatches=[]`。
- 任一不同或当前无法解析：`RESET_REQUIRED`，至少一条 mismatch，拒绝新工作。

mismatch 至少含 AssetRef、`recordedVersionId`、`effectiveVersionId`（无法解析时为显式缺失原因）。响应给前端的是轻量 reset 提示所需事实，不自动 restart，不切换到旧版本，不静默迁移，不回放业务写入。

此门禁和引擎代码/Checkpoint 兼容性是两类问题，错误码与可观察证据必须分开。

## 6. 控制请求去重

`ControlRequest` 候选字段：

- `controlRequestId`：调用方生成的控制命令标识。
- `commandType`：`START_RUN`、`CONTINUE_RUN`、`SUBMIT_NODE_INPUT`、`SUBMIT_INTERACTION`、`RETRY_A2UI_NODE`、`STOP_RUN`。
- `target`：按命令包含 RunRef、NodeRef 或 InteractionRef。
- `payloadDigest`：控制 payload 的稳定摘要，算法暂不冻结。
- `recordedAssetVersions`：需要版本门禁的入口携带已记录版本。

服务端以控制作用域 + controlRequestId 持久去重：同 ID 同摘要返回首次控制结果；同 ID 异摘要返回冲突；并发首写只有一个胜者。`START_RUN` 的 fresh restart 使用新的 controlRequestId 和新的 runId，且不继承旧状态。

`CONTINUE_RUN`、`SUBMIT_NODE_INPUT`、`SUBMIT_INTERACTION`、`RETRY_A2UI_NODE` 必须携带至少一个 recordedAssetVersion；同一 AssetRef 只能出现一次，完整性仍由 Runtime 按当前入口依赖集合校验。`RETRY_A2UI_NODE.retryReason` 只允许 `RENDER_FAILED`、`ACTION_CALL_FAILED`、`ACTION_RESULT_NOT_SUCCESS`；其他命令不得携带 retryReason。

`ControlRequest` 不包含业务 idempotency key，也不保存“业务已执行所以禁止 fresh run”的判断。被调用 API 后端独立拥有业务幂等、重试和未知结果处理。

## 7. 引用、ResultInterpretationPolicy 与事件事实

`ResultInterpretationPolicy` 是唯一公共结果解释结构，由 `policyRef` 命名，只允许：

- `SCHEMA_VALID`：引用 Ability Release 的输出 Schema 校验事实。
- `JSON_POINTER_EQUALS`：使用 `jsonPointer` 与 JSON 原生 `expectedLiteral` 做严格类型和值相等比较。

Runtime 在独立的输出 Schema 校验之后运行一个纯解释器。JSON Pointer 路径缺失与路径存在且值为 JSON null 是不同事实；缺失路径必须返回不命中与 `PATH_MISSING`，绝不能产生成功。字符串、数字、布尔值和 null 不做隐式转换，也不增加脚本、正则或通用表达式引擎。

Capability Release 发布 `resultInterpretationPolicies` 数组与 `defaultSuccessPolicyRef`；每个数组项用 `policyRef` 命名，聚焦语义校验保证引用唯一且 default 可解析。A2UI Action 通过公共 `actionSuccessPolicyBinding` 选择 `successPolicyRef` 并单独声明 `completeInteractionOnSuccess`；`actionOutcomeFacts` 分别记录 `outputSchemaValid`、`successPolicyMatched`、`actionCallSucceeded` 与 `interactionCompleted`。四项事实不能从可见控件或其中任一事实推断其他事实。

公共引用只表达定位：

- `RunRef={runId}`。
- `NodeRef={runId,nodeId}`。
- `InteractionRef={runId,nodeId,interactionId}`，必须绑定一个具体节点。
- `ResultRef={runId,resultId,scope}`；`scope` 为 `INTERACTION`、`NODE` 或 `RUN`，交互/节点结果额外带所属 ID。

候选事件外壳包含 `eventId`、单 Run 严格递增的 `runSequence`、`eventType`、`occurredAt`、`trustedContext`、该事件最具体且唯一的引用，以及可选 `causationControlRequestId`。Run 生命周期/版本失配使用 RunRef；Node 状态使用 NodeRef；等待交互使用 InteractionRef；三层结果事件只使用对应 ResultRef。事件分支拒绝其他层级引用和外来事实字段，因此不产生重复 ID 的交叉归因。协议版本、消息总线、sequence 持久化/重放和 delivery guarantee 尚未冻结。

首轮事件边界：

| 事件事实 | 必需引用 | 不代表 |
| --- | --- | --- |
| `RUN_ACCEPTED` | RunRef | Run 已完成 |
| `NODE_STATUS_CHANGED` | NodeRef | 交互或全 Run 完成 |
| `INTERACTION_WAITING` | InteractionRef | 可见控件自动暂停或自动完成 |
| `INTERACTION_RESULT_RECORDED` | INTERACTION ResultRef | Node/Run 成功 |
| `NODE_RESULT_RECORDED` | NODE ResultRef | Finalizer 已完成 |
| `RUN_RESULT_RECORDED` | RUN ResultRef | 外部异步业务已经完成 |
| `VERSION_MISMATCH_BLOCKED` | RunRef + VersionGuardDecision | 已 reset 或已 restart |

A2UI DISPLAY_ONLY/INTERACTIVE、Action businessSuccess 与 completesInteraction 由已发布配置和 A2UI/Runtime 边界判断；公共事件只保存最终事实。Finalizer 可以产出 RUN Result，但不能改写 Interaction/Node 的业务事实。

## 8. 失败、重试和并发

| 边界 | 失败处理 | 重试责任 | 并发正确性 |
| --- | --- | --- | --- |
| TrustedContext | 缺失/非法/override 一律拒绝 | 调用方重新认证，不降级身份 | 服务端上下文不可由模型 payload 覆盖 |
| AssetResolution | 环境内版本不存在即失败关闭 | 可重试暂时读错；不跨环境 fallback | PostgreSQL 真值；缓存不可决定正确性 |
| VersionGuard | mismatch 拒绝新工作并提示 reset | 不自动重试/迁移/restart | 每个 ingress 重新比较 |
| ControlRequest | 同 ID 异摘要冲突 | 同 ID 同摘要可安全查询/重试 | PostgreSQL 唯一约束/事务，支持多实例 |
| ExecutionEvent | 引用或边界非法拒绝记录 | 传输重试策略待定 | 事件事实与运行事务边界由 Runtime 证明 |
| Business Tool | 公共层不承诺业务 exactly-once | 被调用 API 后端拥有 | Workflow 不补偿、不对账、不跨 Run 去重 |

## 9. 六域必须回交的接口需求

| 领域 | 必须回交给 contracts/main-brain | 公共层不会拥有 |
| --- | --- | --- |
| Skill registry | Skill AssetVersion payload、resource/body 加载引用、`use_skill` 需要的输入/结果外壳 | Skill 指令执行和固定子图 |
| Ability registry | Ability 版本引用、Tool 调用/结果引用、命名 `ResultInterpretationPolicy` 集合与 `defaultSuccessPolicyRef` | 业务幂等、业务重试、真实业务实现 |
| A2UI composer | Component/Application 关系、DISPLAY_ONLY/INTERACTIVE、Action `successPolicyRef` 与 `completeInteractionOnSuccess` | Renderer、Action 业务状态机、协议版本 |
| Workflow composer | graph version、节点稳定 ID、依赖资产版本集合和 AI/user choice 引用 | LangGraph 调度和每 Skill 子图 |
| Runtime | Python 字段命名/序列化、ingress guard 调用点、control result、事件落库边界 | 产品业务模型和第二套 scheduler |
| Digital employee | 服务端可信上下文注入、卡片 Node/Interaction ref、reset/stopped 展示所需字段 | 身份选择、Runtime 状态机、M 发布 |

main-brain 归并实际需求并命名契约 revision 后，六域才能把本候选作为实现依赖。

## 10. 验证策略

首轮使用项目自造、无业务数据的 JSON 正反例。正例覆盖 PRT current、ONLINE stable/gray、ALLOW、RESET_REQUIRED、控制请求、两种结果解释策略、包内相对材料引用和三层 Result；反例覆盖 sellerId/环境 override、ONLINE->PRT、第三 serving 版本、mismatch 却 ALLOW、未批准策略操作符、缺少 expected literal、父目录穿越、错误作用域引用和业务幂等字段。

聚焦校验只证明 Schema 形状和部分交叉约束；不证明服务端可信注入、PostgreSQL 多实例去重、Runtime ingress 拦截、事件事务性、A2UI/Finalizer 语义或产品可用。

## 11. 待 main-brain 审查

1. `assetType` 候选枚举是否把 Component 与 Application 分开，以及 ResultInterpretationPolicy v0 的两个操作符是否批准。
2. Runtime 的 Python 消费方式：直接 JSON Schema + Pydantic 手写模型，还是经批准后生成类型。
3. ControlRequest/ExecutionEvent 的最终字段命名与持久化 owner；HTTP/SSE/事件总线版本继续保持未冻结。
