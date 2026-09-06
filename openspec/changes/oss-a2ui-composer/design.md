# A2UI 组件编排平台设计

## 文档状态

- 状态：`PROPOSED / PHASE 1 ALIGNED`
- 运行态：`NO READY`
- 权威基线：`SW-P1-20260907.2`，已同步服务器 `origin/main=0980f0ae304a340f24d7421ab4a51818af612b32`
- 工程裁决：ENG-01 已接受 future registry 为 Python 可导入后端模块；不要求独立进程，不授权根依赖编辑
- 协议版本：`PENDING_CROSS_DOMAIN_REVIEW`；任何 A2UI 版本均未由本任务冻结
- 当前实现证据：两份项目独立合成的 Application 夹具及无依赖静态校验器
- 当前门禁：registry 依赖共享契约的命名修订，尚未获 IMPLEMENT 放行
- 不负责：Runtime、传输、React Host、业务 Action 后端、部署和系统 Python

## 1. 不变量

1. M 侧资产是 Component Catalog 和 Application。Presentation 只指 Runtime 渲染后产生的运行期 Surface/消息，不是另一套共享资产。
2. Application 内容只能声明数据、组件、绑定和受限策略，不携带 HTML、脚本、远程模块、凭据或可信运行上下文。
3. 所有渲染从授权 Tool `render_application` 进入；模型不能绕过 Tool 直接构造可信 Runtime 命令。
4. `interactionMode` 必须显式为 `DISPLAY_ONLY` 或 `INTERACTIVE`。
5. 渲染成功、Action 调用成功、Action 业务成功、交互完成、Skill 完成和 Workflow 完成分别记录，不相互推断。
6. Action 通过 `successPolicyRef` 选择精确 Ability Release 中的命名 `ResultInterpretationPolicy`；`completeInteractionOnSuccess` 独立决定 policy matched 后是否完成当前交互。
7. execution/continue/Action ingress 在做新工作前比较当前有效版本；失配即 `RESET_REQUIRED`，不继续冻结旧资产、不静默迁移、不自动重启。
8. 平台 `controlRequestId` 只去重控制请求；被调 API 后端负责业务幂等、重试、对账和不确定结果。
9. 节点重试只允许 `RENDER_FAILED`、`ACTION_CALL_FAILED`、`ACTION_RESULT_NOT_SUCCESS`。
10. Finalizer 只能整理已成立事实，不能把失败改成成功，不能补做业务调用，也不能绕过未完成交互。
11. `userId`、PRT/ONLINE、ONLINE stable/gray 和有效版本解析只有共享后端契约一个 owner。
12. 所有一致性最终依赖 PostgreSQL；不提供 MySQL、SQLite 或内存 fallback。

## 2. 责任分解

    M Authoring
      ComponentCatalog + ApplicationDraft
      validate / compile / publish domain payload
                         |
                         v
    Shared Contracts
      trusted context / effective version / ReleaseRef
      ResultInterpretationPolicy / control envelope / publication
                         |
                         v
    Generic Runtime
      render_application / Surface / wait-resume
      Action dispatch / stop-restart / Finalizer boundary
                         |
                         v
    Digital Employee A2UI Host
      local React mapping / safe rendering / accessibility
      user action capture -> trusted backend ingress

### 2.1 A2UI Composer 拥有

- Component Catalog 与 Application Draft 的作者生命周期。
- 组件图、JSON Pointer 绑定、Action 映射、交互策略和资源上限校验。
- 使用批准 protocol profile 的确定性编译。
- Component Catalog/Application 领域 payload 与 Validation Report。
- 调用公共发布端口；不复制公共 Asset/Release、身份、环境或版本决议。
- 在 IMPLEMENT 放行后，于 `services/a2ui-registry/` 提供小型 Python 可导入模块；transport/process composition 保持可分离。

### 2.2 Shared Contracts 拥有

- 可信 `userId` 与环境上下文。
- PRT 当前版本和 ONLINE stable/gray 有效版本决议；ONLINE 永不读取 PRT。
- 公共 AssetRef/ReleaseRef、digest、授权、审计与发布幂等。
- `ResultInterpretationPolicy`、控制请求 envelope、版本失配和通用失败 envelope。
- 最终字段名、协议版本与 transport envelope。

### 2.3 Runtime 拥有

- 作为唯一通用入口实现 `render_application`。
- 解析精确 Application Release，执行版本准入，创建 Surface 并投影运行数据。
- 对 `DISPLAY_ONLY` 渲染后继续；对 `INTERACTIVE` 建立 node/card/form 绑定并进入等待。
- 持久化交互、按受信任 ingress 恢复、调度 Action、区分调用结果/业务结果/交互结果。
- 落实 A2UI-only retry、stop/restart 和 Finalizer 边界。
- 不导入数字员工业务模型、文案或场景分支。

### 2.4 Digital Employee A2UI Host 拥有

- 位于 `packages/a2ui-host/` 的本地 React 组件映射与 Catalog 支持清单。
- 安全渲染、Markdown/URL 清理、可访问性、主题与交互控件。
- 捕获 actionName/sourceComponentId/payload，并通过 B 后端形成可信 Action ingress。
- 未知协议/Catalog/组件时失败关闭；不下载执行代码、不猜测 fallback。

## 3. 作者模型

字段名均为候选，最终以 main-brain 指定的共享契约修订为准。

### 3.1 ComponentCatalogDraft

| 字段 | 约束 |
| --- | --- |
| draftId / assetId / revision | 草稿身份与 PostgreSQL 乐观并发版本 |
| protocolProfileRef | 明确引用批准 profile；不接受 latest |
| catalogDocument | 声明式组件、属性、结构引用与函数 schema |
| lifecycle | `DRAFT` 或 `ARCHIVED` |
| createdBy / updatedBy | 共享审计主体引用，不包含凭据 |
| createdAt / updatedAt | 服务端时间 |

Catalog 不包含 React 代码、脚本体、远程模块或运行期下载地址。

### 3.2 ApplicationDraft

| 字段 | 约束 |
| --- | --- |
| draftId / assetId / revision | 与 Catalog 草稿相同的并发语义 |
| protocolProfileRef | 必须与精确 Catalog 依赖兼容 |
| catalogDependency | 精确 Catalog draft revision 或 ReleaseRef |
| surfaceTemplate | 单个逻辑 Surface、唯一 root、扁平组件图 |
| inputSchema | JSON Schema 2020-12 候选；只描述可投影数据 |
| bindings | RFC 6901 JSON Pointer；无脚本表达式 |
| interactionMode | 仅 `DISPLAY_ONLY` 或 `INTERACTIVE` |
| actionPolicies | event 到精确 Ability Release、successPolicyRef 与完成策略 |
| limits | 平台批准的固定上限，作者不可放大 |

首期不支持多 Surface 编排、任意表达式、运行期能力发现或自动业务调用。

### 3.3 ActionPolicy

| 字段 | 约束 |
| --- | --- |
| actionName | 在一个 Application 内唯一 |
| sourceComponentId | 必须指向声明该 event 的组件 |
| actionContractRef | 精确且已授权的 Action schema 引用 |
| abilityReleaseRef | Action 调用的精确 Ability Release；不接受 floating/latest |
| successPolicyRef | 选择该 Release 已发布的命名 `ResultInterpretationPolicy`；本域不内联 DSL |
| completeInteractionOnSuccess | 必填 boolean，不从 success condition 推断 |
| controlRequestDedupeOnly | 固定为 true，表示只去重平台控制请求 |
| businessIdempotencyOwner | 固定为 `CALLED_API_BACKEND` |

Application 不声明“业务 exactly-once”。若 Action 调用已发出但结果未知，Runtime 记录不确定事实并停止自动推进；是否重试、查询或补偿由被调 API 契约决定。

Ability Release 拥有 named policies 与 defaultSuccessPolicyRef；A2UI Action 必须显式选择 successPolicyRef。A2UI 不复制 policy 内容，也不实现解释器。当前候选只允许 SCHEMA_VALID，或 JSON_POINTER_EQUALS + JSON primitive expectedLiteral。Runtime 的唯一纯解释器必须区分 PATH_MISSING 与 FOUND(null)，missing 永不 match，并按 JSON 类型和值严格比较，不做字符串/数字/布尔/null 隐式转换。

### 3.4 ApplicationRelease 领域 payload

- protocolProfileRef
- logicalSurfacePlan
- canonical component/data template
- inputSchema 与 bindingPlan
- `interactionMode`
- actionPolicies
- dependencyLocks
- validatorRevision 与 validationReportDigest
- domainPayloadDigest

公共 releaseId、assetId、version、artifactDigest、授权与审计字段由 shared contracts 外层提供。

## 4. 交互与完成状态

| 事件/事实 | 含义 | 是否自动推进 |
| --- | --- | --- |
| `RENDER_SUCCEEDED` | Surface 已成功产出 | DISPLAY_ONLY 可继续；INTERACTIVE 不可 |
| `ACTION_CALL_SUCCEEDED` | 被调 API 返回可解析结果 | 仍需判断业务成功条件 |
| `ACTION_RESULT_SUCCEEDED` | 输出 schema 合法且 success policy matched | 由完成布尔值决定 |
| `ACTION_RESULT_NOT_SUCCESS` | 输出 schema 或 success policy 未满足 | 保持交互并可走 A2UI-only retry |
| `INTERACTION_COMPLETED` | 当前 node/card/form 交互已完成 | Runtime 才可继续节点后继 |
| `SKILL_COMPLETED` | 当前 Skill 已完成 | 不等于 Workflow 完成 |
| `WORKFLOW_COMPLETED` | Workflow 所需节点均完成 | 由 Runtime 决定 |

### 4.1 DISPLAY_ONLY

- `requiresPause=false`。
- 不允许 actionPolicies 或交互 event。
- 渲染成功后 Runtime 可继续当前 Skill/Workflow。
- 只允许因 `RENDER_FAILED` 重试该 A2UI 节点。

### 4.2 INTERACTIVE

- `requiresPause=true`。
- 绑定范围固定为 Runtime 的 node/card/form 实例。
- 普通聊天输入不能恢复该交互；必须经受信任的 Action ingress。
- 作者配置的确定性选择直接路由，不再交给 AI 重选。
- Action 调用成功、输出 schema 合法、success policy matched 且 `completeInteractionOnSuccess=true` 时完成交互。
- policy matched 但该值为 false 时保留交互，等待后续显式 Action。
- Action 业务失败不完成交互，可按 `ACTION_RESULT_NOT_SUCCESS` 的有界策略重试。
- Action 调用失败可按 `ACTION_CALL_FAILED` 的有界策略重试。
- Renderer/Suface 渲染失败可按 `RENDER_FAILED` 的有界策略重试。

## 5. 版本准入与重置

Runtime 必须在下列边界比较执行记录引用版本与共享 resolver 返回的当前有效版本：

- 新 execution
- continue/resume
- Action ingress

失配时：

1. 在业务 Action 调用前返回类型化 `RESET_REQUIRED`。
2. 保留历史记录用于审计，但历史卡变为只读。
3. 不解析或执行冻结旧 Application。
4. 不自动迁移上下文、不自动重启、不重放业务调用。
5. 用户显式 reset 后创建全新 run，不继承旧 context、checkpoint、结果、完成标记或 interaction。

Composer 只把版本标识和精确依赖写入产物；实际有效版本选择与准入由 shared contracts + Runtime 负责。

## 6. 校验流水线

### 6.1 结构与组件图

- 文档符合批准的 protocol/schema bundle。
- `asset.kind=APPLICATION`，恰好一个逻辑 Surface 和 root。
- componentId 唯一，child 引用存在，图无环且全部可达。
- 组件、属性和函数存在于锁定 Catalog。
- 未知 blocking 字段失败关闭。

### 6.2 数据与 Action

- binding 只允许 JSON Pointer，路径和目标类型兼容。
- capability/ability output schema 只作为定义期证据，不授权执行。
- eventName 与 ActionPolicy 一一对应。
- `abilityReleaseRef` 必须精确，`successPolicyRef` 必须非空且在该 Release 中存在；本域不复制 policy 或实现第二套解释器。
- `completeInteractionOnSuccess` 必须显式存在。
- DISPLAY_ONLY 不得携带 Action；INTERACTIVE 至少一个 ActionPolicy。

### 6.3 安全与资源边界

- 禁止 `userId`、环境、灰度目标、secret、credential、Cookie、HTML 和 script。
- schema/ref 只从发布包或 allowlist 离线解析。
- 检测 schema/ref 环、组件环、过深嵌套和超大数组。
- URL scheme 必须由 Catalog 允许；Host 仍做二次清理。
- 初始大小与深度上限属于待审查参数，未批准前不写成兼容承诺。

### 6.4 确定性

相同 draftRevision、protocol profile、validatorRevision 与 dependencyLocks 必须产生相同规范化领域 payload 和 digest。协议规范化算法、digest 字段和签名扩展由 shared contracts 决定。

## 7. 草稿、发布与多实例

- create 产生 revision 1。
- update 必须带 expectedRevision，并在 PostgreSQL 事务中 compare-and-swap。
- validate 为纯读取，不推进 revision。
- archive 只阻止后续编辑/发布，不删除历史 Release。
- publish 对精确 draftRevision 重新校验并锁定全部依赖。
- 发布事务必须原子，不先落部分 payload 再补依赖。
- 相同发布控制请求的幂等语义由 shared contracts + PostgreSQL 唯一约束实现。
- 进程内缓存只优化精确 Release 读取，不决定正确性。
- 不提供 MySQL、SQLite、内存存储或 latest/default fallback。

## 8. 候选 API

具体 envelope 与字段待 shared contract 修订。候选资源名使用 Application，不再暴露 Presentation asset API。

| Method | Params | 成功 data |
| --- | --- | --- |
| POST /api/a2ui/catalog-drafts | name, protocolProfileRef, catalogDocument | draftId, assetId, revision |
| PUT /api/a2ui/catalog-drafts/{draftId} | expectedRevision, mutable fields | draftId, revision, updatedAt |
| POST /api/a2ui/catalog-drafts/{draftId}:validate | draftRevision | valid, reportDigest, errors, dependencyLocks |
| POST /api/a2ui/catalog-drafts/{draftId}:publish | draftRevision, dependencyLocks, control request | releaseRef, artifactDigest |
| POST /api/a2ui/application-drafts | name, catalogDependency, surfaceTemplate, interactionMode | draftId, assetId, revision |
| PUT /api/a2ui/application-drafts/{draftId} | expectedRevision, mutable fields | draftId, revision, updatedAt |
| POST /api/a2ui/application-drafts/{draftId}:validate | draftRevision | valid, reportDigest, errors, dependencyLocks |
| POST /api/a2ui/application-drafts/{draftId}:publish | draftRevision, dependencyLocks, control request | releaseRef, artifactDigest |
| GET /api/a2ui/releases/{releaseId} | exact releaseId | releaseRef, protocolProfileRef, locks, digest, payload |

## 9. Runtime Tool 消费需求

`render_application` 候选输入：

- exact Application ReleaseRef/digest
- trusted execution context reference（不是资产内 `userId`/environment）
- runId/nodeId/attemptId
- renderer capabilities / supported Catalogs
- 已有 dataModel

候选结果必须区分：

- render 成功并是否需要等待
- `RENDER_FAILED`
- `VERSION_MISMATCH / RESET_REQUIRED`
- `PROTOCOL_UNSUPPORTED`
- `CATALOG_UNSUPPORTED`
- `DATA_BINDING_INVALID`

Runtime 负责实例化 surfaceId、有序输出、持久化 cursor 与重连；Composer 不拥有 run state。

Action ingress 至少需要受信任关联 run/node/card/form、sourceComponentId、actionName、payload 和 `controlRequestId`。具体字段由 shared contracts/Runtime/Host owner 联合确定。

## 10. Finalizer、停止与重启

- Finalizer 只总结已保存事实；不能调用 Action、触发重试、完成待交互节点或改写失败。
- accepted stop 后不再启动新节点、模型/Tool round、Workflow Action 或 retry；已发出调用的迟到结果只能保存，不得推进。
- stopped run 不可 resume，历史卡只读，后端拒绝操作。
- restart 创建全新 run，不继承旧上下文或交互，也不做业务对账、补偿或跨 run 去重。

## 11. 可观察性

Composer create/update/validate/publish 记录 requestId、actorRef、assetId、draftId、revision、releaseId、validatorRevision、结果 code 与耗时，不记录资产正文、用户数据或凭据。

Runtime/Host 使用 runId、nodeId、surfaceId、interactionId、`controlRequestId` 和类型化 outcome 关联，但这些字段不改变 Composer 的运行态边界。

## 12. 验证策略

- Phase 1：项目独立合成的 DISPLAY_ONLY 与 INTERACTIVE 夹具。
- 规则测试：组件图、交互策略、Action 成功/完成分离、版本 reset、Finalizer、retry allowlist、敏感字段。
- IMPLEMENT 后：Validator 表驱动/属性测试，PostgreSQL 乐观并发与发布事务测试。
- 联合契约：shared resolver、`render_application`、Runtime Action ingress、Host capability negotiation。
- E2E：只有 Runtime/Host 真正运行后才可记录；静态夹具不算运行证据。

## 13. 未决裁决

1. A2UI protocol profile 与 wire version。
2. shared contracts 的命名修订及最终字段。
3. Runtime/Host transport、cursor 与 Action ingress envelope。
4. Application Draft/Release API、资源上限和 PostgreSQL schema。
