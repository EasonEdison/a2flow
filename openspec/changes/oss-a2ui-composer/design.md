# A2UI 组件编排平台设计

## 文档状态

- 状态：PROPOSED
- 运行态：NO READY
- 协议版本：待 main-brain 裁决；首期推荐 A2UI v0.9.1 工具/规范实现，Wire version v0.9.1
- 范围：定义期 Catalog、Presentation Draft、校验、编译和不可变发布产物
- 不负责：Runtime 执行、传输、React 渲染、业务动作和部署

## 1. 设计原则

1. 声明式优先：资产只能描述数据与组件，不携带任意脚本、HTML 或可执行插件。
2. 精确依赖：只引用不可变 Release 与 digest，不解析 draft、latest 或默认版本。
3. 发布即冻结：发布后的内容、依赖锁和校验结果不可修改。
4. 编译确定性：相同输入生成相同规范化字节和 digest。
5. 失败关闭：未知协议、Catalog、组件、函数、绑定或 action 契约不静默降级。
6. 三方解耦：M 编排器定义；Runtime 通用执行；B Web Renderer 具体渲染。
7. 多实例正确：所有一致性依赖 PostgreSQL 事务、版本字段和唯一约束，不依赖进程内锁。
8. 证据分级：设计、源码、集成、部署和运行证据分别记录。

## 2. 上下文与责任边界

    Author/Reviewer
          |
          v
    M A2UI Composer
      - Catalog Draft
      - Presentation Draft
      - Validate / Compile
      - Publication payload
          |
          v
    Common Release Contract
      - identity / auth / idempotency / immutable storage
          |
          v
    Generic Runtime Presentation Executor
      - resolve exact release
      - instantiate surface
      - project run data
      - ordered stream / replay / action correlation
          |
          v
    Digital Employee Web Renderer
      - advertise catalogs
      - React component mapping
      - local data model / validation / accessibility
      - user action return channel

### 2.1 编排器拥有

- Catalog 与 Presentation 草稿的创建、读取和修订。
- 草稿结构、组件图、数据绑定、action 映射、依赖和资源限制校验。
- 协议 profile 选择和确定性编译。
- 向公共发布服务提交不可变领域 payload。
- 返回稳定、机器可读的 Validation Report。

### 2.2 Runtime presentation 执行拥有

- 解析精确 Presentation Release，拒绝 digest 或 profile 不匹配。
- 为每次 Run 分配真实 surfaceId，并将逻辑 Surface 模板实例化。
- 将已存在的通用 Run/Capability 结果投影为 dataModel；Presentation 引用本身不触发能力调用。
- 通过批准的传输适配器有序发送 A2UI 消息，持久化游标并支持重连重放。
- 接收 action，关联 runId、surfaceId、sourceComponentId 与幂等键，并交给通用 action port。
- 不包含数字员工字段、文案、业务分支或 React 代码。

### 2.3 数字员工 Web Renderer 拥有

- 维护 supportedCatalogIds、RendererCatalogSupportManifest 与具体 React 组件映射。
- 消费 A2UI 消息并维护 Surface/组件/dataModel 客户端状态。
- 执行 Catalog 声明的 renderer-side 函数与本地校验；不得执行资产中携带的脚本。
- 做 Markdown/URL/富文本清理、可访问性映射、主题与视觉样式。
- 通过 B 端后端/传输通道返回结构化 action。
- 对未知 Catalog 或不支持组件给出安全、可观察的失败表现，不选择其他 Catalog 猜测渲染。

### 2.4 公共发布契约拥有

- 通用 Asset/Release 身份、授权、审计、幂等和不可变存储。
- digest 算法与签名/证明扩展点。
- 跨域 ReleaseRef 和依赖锁公共字段。
- 本设计只提出消费需求，不复制实现。

## 3. 领域对象

所有名称和字段均为候选，最终以共享契约审查为准。

### 3.1 ProtocolProfile

| 字段 | 含义 |
| --- | --- |
| protocol | 固定为 a2ui |
| family | 候选 v0.9 |
| wireVersion | 候选 v0.9.1 |
| implementationVersion | 候选 v0.9.1 |
| schemaBundleDigest | 本次校验使用的官方 schema bundle digest |
| adapterRevision | 本平台编译适配器不可变修订 |

v1.0 Candidate 不与 v0.9 资产混用。协议升级通过新的 Release 和适配器完成。

### 3.2 CatalogDraft

| 字段 | 约束 |
| --- | --- |
| draftId | 平台草稿身份 |
| assetId | 公共资产身份；创建后不变 |
| revision | 单调递增，用于乐观并发 |
| protocolProfile | 明确版本，不接受 latest |
| catalogDocument | 符合目标 A2UI Catalog JSON Schema |
| lifecycle | DRAFT 或 ARCHIVED；发布不改变历史修订 |
| createdBy/updatedBy | 审计主体引用，不写入机密 |
| createdAt/updatedAt | 服务端时间 |

首期 Catalog 只允许声明组件、属性、Child/ComponentId 引用和命名函数 schema；不允许脚本体、远程模块或运行时下载代码。

### 3.3 PresentationDraft

| 字段 | 约束 |
| --- | --- |
| draftId/assetId/revision | 与 CatalogDraft 相同的并发语义 |
| protocolProfile | 必须与所有 Catalog 依赖同 family |
| catalogDependency | 首期恰好一个精确 Catalog Draft revision 或 ReleaseRef |
| surfaceTemplate | 单个逻辑 Surface，包含唯一 root 和扁平组件邻接表 |
| inputSchema | JSON Schema 2020-12，描述 Runtime 可提供的数据 |
| dataContractRefs | 精确 capability output schema ReleaseRef，仅用于兼容校验 |
| bindings | JSON Pointer 到 input/dataModel 的声明式绑定 |
| actionBindings | eventName 到精确 action contract ReleaseRef 的映射 |
| limits | 采用平台批准上限，作者不能自行放大 |
| revision | expectedRevision 成功后递增 |

首期不引入通用表达式语言。字符串格式化或客户端函数只有在目标 Catalog 声明且 Renderer 明确支持时才可引用。

### 3.4 ValidationReport

| 字段 | 含义 |
| --- | --- |
| valid | 所有 blocking rule 均通过时为 true |
| validatedDraftRevision | 被校验的精确草稿修订 |
| protocolProfile | 实际使用的协议 profile |
| dependencyLocks | 校验时解析到的精确 ReleaseRef 与 digest |
| errors | code、severity、jsonPointer、message、dependencyRef |
| warnings | 非阻断且不会改变运行语义的提示 |
| validatorRevision | 验证器规则不可变修订 |
| reportDigest | 规范化报告摘要 |

错误 message 面向人，调用方只能依赖 code 与 jsonPointer，不依赖文案。

### 3.5 CatalogRelease payload

- protocolProfile
- canonicalCatalogDocument
- validatorRevision
- validationReportDigest
- dependencyLocks
- domainPayloadDigest

### 3.6 PresentationRelease payload

- protocolProfile
- logicalSurfacePlan
- canonical A2UI component/data template
- inputSchema
- bindingPlan
- actionBindings
- dependencyLocks
- validatorRevision
- validationReportDigest
- domainPayloadDigest

公共 Release 外层再提供 releaseId、assetId、version、artifactDigest、createdAt、createdBy 等字段。确切字段由 oss-platform-contracts 决定。

## 4. 草稿与发布状态

### 4.1 草稿

- create：创建 revision=1 的 DRAFT。
- update：请求必须提交 expectedRevision；事务内 compare-and-swap。
- validate：纯读取、可重复执行，不推进 revision。
- archive：只阻止后续编辑/发布，不删除已发布产物。
- 草稿可变；任何 Release 都必须记录精确 draftRevision。

### 4.2 发布

发布命令输入 draftId、draftRevision、Idempotency-Key、期望 dependencyLocks 和授权上下文。

事务边界候选：

1. 锁定/核对目标草稿修订。
2. 将所有草稿依赖解析为精确 ReleaseRef 与 digest。
3. 用固定 schema bundle 和 validatorRevision 重新校验。
4. 编译领域 payload。
5. 按 RFC 8785 候选规则规范化 JSON，并由公共契约计算 digest。
6. 通过公共 Release Port 原子创建或返回既有 Release。
7. 提交审计记录。

不得先写部分 Release 再异步补依赖锁。瞬时故障使用同一 Idempotency-Key 重试；校验、授权和依赖冲突不自动重试。

### 4.3 幂等与并发

- 同一 Idempotency-Key 与相同请求指纹：返回同一 releaseId。
- 同一 Idempotency-Key 与不同请求指纹：409 IDEMPOTENCY_KEY_REUSED。
- 同一 draftId+draftRevision+publicationProfile 并发发布：唯一约束确保最多一个有效 Release，竞争者读取并返回相同结果。
- stale expectedRevision：409 DRAFT_REVISION_CONFLICT，返回 currentRevision。
- 发布期间依赖被新版本替代不影响结果，因为依赖按精确 ReleaseRef 锁定。
- 精确依赖不可读、digest 不符或未授权：失败关闭，不回退到其他版本。

## 5. 校验流水线

### 5.1 结构校验

- 文档符合目标 A2UI schema 与 JSON Schema 2020-12。
- Catalog 的 $id/catalogId、协议 family 和 Release 清单一致。
- 禁止未知 blocking 字段；扩展字段必须在批准命名空间中。
- schema 引用仅可解析发布包中已捆绑或 allowlist 的文档，校验和运行时均不访问网络。

### 5.2 Catalog 语义校验

- 组件、函数和属性命名符合目标 A2UI 规则。
- Child 与 ComponentId 使用协议规定的结构引用类型。
- 保留字与命名限制按所选 profile 的官方 schema 校验，不把 v1.0 专属规则反向混入 v0.9.1。
- 函数只定义名称、参数和结果 schema，不包含可执行代码。
- 每个交互组件必须声明可访问名称要求或明确的可推导规则。

### 5.3 Presentation 图校验

- 首期恰好一个逻辑 Surface、一个 root。
- componentId 在 Surface 内唯一。
- 所有 child 引用存在，图无环，不可达节点按阻断错误处理。
- component 与 function 必须存在于锁定 Catalog。
- 所有消息/模板使用同一协议 family 和精确 Catalog。
- 发布前得到确定顺序；Runtime 只实例化，不重新排序语义。

### 5.4 数据与 action 校验

- binding 仅使用 RFC 6901 JSON Pointer，不支持脚本表达式。
- binding 路径存在且组件期望类型与 inputSchema/capability output schema 兼容。
- action eventName 在 Presentation 内唯一映射。
- action payload schema 与目标 action contract 兼容。
- dataContractRefs 只提供 schema 证据，不授权 Runtime 自动调用 capability。
- 需要业务授权的 action 仍由 B 端和 Runtime 执行期检查，发布通过不等于运行授权。

### 5.5 安全与资源上限

初始候选上限，待主控确认：

- 每个 Presentation 最多 200 个组件。
- 最大可达树深度 20。
- Catalog 文档最多 256 KiB。
- Presentation 领域 payload 最多 1 MiB。
- 所有 URL 属性必须由 Catalog 声明 scheme 策略；首期不接受 javascript、data HTML 或任意 iframe。
- Markdown/富文本仍需 Renderer 二次清理。
- 检测 schema/ref 环、组件环、过深嵌套和超大数组，防止资源耗尽。
- 资产不得包含密钥、Cookie、令牌或私有连接信息。

## 6. 候选 API

成功响应统一为 requestId 与 data；错误统一为 requestId、error.code、error.message、error.details。外层公共约定待 oss-platform-contracts 审查。

| Method | Params | 成功 data |
| --- | --- | --- |
| POST /api/a2ui/catalog-drafts | name, protocolProfile, catalogDocument | draftId, assetId, revision, lifecycle |
| PUT /api/a2ui/catalog-drafts/{draftId} | expectedRevision, catalogDocument | draftId, revision, updatedAt |
| POST /api/a2ui/catalog-drafts/{draftId}:validate | draftRevision | valid, reportDigest, errors, warnings, dependencyLocks |
| POST /api/a2ui/catalog-drafts/{draftId}:publish | draftRevision, dependencyLocks; header Idempotency-Key | releaseRef, artifactDigest, validationReportDigest |
| POST /api/a2ui/presentation-drafts | name, protocolProfile, catalogDependency, surfaceTemplate, inputSchema | draftId, assetId, revision, lifecycle |
| PUT /api/a2ui/presentation-drafts/{draftId} | expectedRevision, mutable draft fields | draftId, revision, updatedAt |
| POST /api/a2ui/presentation-drafts/{draftId}:validate | draftRevision | valid, reportDigest, errors, warnings, dependencyLocks |
| POST /api/a2ui/presentation-drafts/{draftId}:publish | draftRevision, dependencyLocks; header Idempotency-Key | releaseRef, artifactDigest, validationReportDigest |
| GET /api/a2ui/releases/{releaseId} | exact releaseId | releaseRef, protocolProfile, dependencyLocks, artifactDigest, payload |

API 不提供 latest、默认 Catalog 或按名称猜测 Release 的读取方式。

## 7. Runtime 消费接口需求

本域不冻结 Runtime 方法名，只定义必须满足的语义：

### 输入

- exact Presentation ReleaseRef 与 artifactDigest
- runId/attemptId
- rendererCapabilities，包括 supportedCatalogIds 与协议 profile
- 已存在的通用 dataModel 输入
- presentation stream cursor 或恢复点

### 输出

- 有序 A2UI envelope 序列及单调 cursor
- 实例化后的 surfaceId
- protocolProfile 与 catalogId
- 可关联的 action ingress 元数据
- 类型化的失败 code

### 失败边界

- RELEASE_NOT_FOUND、DIGEST_MISMATCH：不执行，不找替代版本。
- PROTOCOL_UNSUPPORTED、CATALOG_UNSUPPORTED：不发起 Surface，不降级到其他 Catalog。
- DATA_BINDING_INVALID：不部分渲染。
- STREAM_ORDER_CONFLICT：按 Runtime 持久化游标恢复，不由 Composer 修复。
- ACTION_CONTRACT_MISMATCH：拒绝动作，不调用 capability。

## 8. Renderer 接口需求

Renderer 启动或每次交互应按 A2UI 提供 supportedCatalogIds、协议 profile、可选主题/Surface 能力。数字员工构建还应产出 RendererCatalogSupportManifest，记录 catalogId、精确 Catalog ReleaseRef、artifactDigest 与 rendererBuildRevision；Runtime 用它核对发布依赖。具体 metadata 映射待跨域裁决。Renderer 仅接受已经协商且 digest 匹配的 Catalog，并使用本地注册的 React 组件映射。

action 返回至少包含：

- runId 或 Runtime 可验证的关联令牌
- surfaceId
- sourceComponentId
- eventName
- timestamp
- context
- 客户端 dataModel 元数据，仅当协议/Surface 明确要求
- actionId 或 Idempotency-Key

具体传输 envelope、鉴权头和 AG-UI 映射由 Runtime 与数字员工任务共同提出并由 main-brain 裁决。

## 9. 重试和恢复

| 失败 | 责任方 | 重试 |
| --- | --- | --- |
| 草稿 revision 冲突 | Composer API | 客户端读取 currentRevision 后显式合并 |
| 校验失败 | Composer Validator | 修正草稿后新修订再校验 |
| 发布事务瞬时失败 | Composer + Common Release | 同一 Idempotency-Key 有界重试 |
| 依赖不存在/未授权/digest 不符 | Composer | 不自动重试或替换依赖 |
| Stream 断线/乱序 | Runtime | 按持久化 cursor 重放 |
| Catalog 不支持 | Runtime + Renderer | 返回类型化失败，不选择默认 Catalog |
| action 重复 | Runtime | 按 actionId/幂等键去重 |
| React 组件渲染异常 | Web Renderer | 安全错误边界与遥测；不回写修改 Release |

## 10. 数据持久化与多实例

后续实现仅使用 PostgreSQL：

- draft 表保存 JSONB 内容、revision 和审计字段。
- validation_report 保存输入指纹、规则版本、错误和 digest。
- domain_release_payload 保存不可变规范化 payload 与 digest。
- publication_request 保存 Idempotency-Key、requestFingerprint 和结果。
- 数据库唯一约束实现发布去重；事务隔离和 compare-and-swap 实现草稿并发。
- 进程内缓存只能优化读取，不能决定正确性；缓存键必须包含 releaseId 与 digest。
- 不提供 MySQL、SQLite 或内存持久化 fallback。

表名、索引和事务隔离级别属于实现计划，本轮不冻结。

## 11. 可观察性

每次 create/update/validate/publish 记录 requestId、actorRef、assetId、draftId、draftRevision、releaseId、protocolProfile、validatorRevision、结果 code 和耗时。日志不得记录完整用户数据、资产正文、凭据或 action 敏感 context。

Runtime 和 Renderer 需沿用 runId、surfaceId、stream cursor、actionId，以便端到端关联；这些不是 Composer 的运行态所有权。

## 12. 测试策略

- Validator 规则表驱动单测。
- Catalog 与 Presentation 的官方 schema fixtures。
- PostgreSQL 集成测试覆盖乐观并发、唯一约束、事务回滚和多实例竞争。
- 属性测试覆盖 component graph、JSON Pointer 和规范化确定性。
- 契约测试分别对接公共 Release Port、Runtime resolver 与 Renderer capability handshake。
- E2E 只在跨域契约批准和实现完成后执行，不把设计样例当运行证据。

## 13. 升级与重新评估触发器

满足以下任一条件时重审 A2UI profile：

- A2UI v1.0 从 Candidate 转为官方稳定。
- 目标 React Renderer 对 v1.0 的核心协议和 Catalog 清单通过兼容矩阵。
- v0.9.1 缺少 MVP 必需且无法用 Catalog 内声明式能力表达的语义。
- 官方 schema 或安全公告要求迁移。

升级必须生成新 adapterRevision 和新 Release；旧 Release 仍按原 profile 可重放，不静默重编译。
