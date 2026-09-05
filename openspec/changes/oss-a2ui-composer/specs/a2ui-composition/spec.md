# A2UI Composition Capability Specification

## Status

PROPOSED。本文定义目标契约，不代表实现、部署或运行态证据。Runtime readiness 为 NO READY。

## ADDED Requirements

### Requirement: Drafts SHALL use explicit protocol and optimistic revision

系统 SHALL 为 CatalogDraft 与 PresentationDraft 保存明确 protocolProfile 和单调 revision。更新请求 MUST 提交 expectedRevision，服务 MUST 在 PostgreSQL 事务内比较并更新，不得用进程内锁保证正确性。

#### Scenario: Reject a stale draft update

- GIVEN 一个 PresentationDraft 当前 revision 为 7
- AND 两个 API 实例都可访问同一 PostgreSQL
- WHEN 调用方提交 expectedRevision=6 的更新
- THEN 系统返回 DRAFT_REVISION_CONFLICT
- AND error.details.currentRevision 等于 7
- AND 草稿内容与 revision 均不改变

### Requirement: Catalog validation SHALL be deterministic and declarative

系统 SHALL 依据锁定的 A2UI schema bundle 和 validatorRevision 校验 Catalog。Catalog MUST NOT 携带 JavaScript、HTML 执行体、远程模块或其他可执行代码。Schema 引用 MUST 从发布包或 allowlist 解析，校验期间 MUST NOT 访问网络。

#### Scenario: Validate a safe Catalog draft

- GIVEN 一个使用已批准 A2UI profile 的 CatalogDraft
- AND 组件、Child/ComponentId 引用、函数参数与可访问性要求均合法
- WHEN 调用 validate 且指定精确 draftRevision
- THEN data.valid 等于 true
- AND data.reportDigest、data.dependencyLocks 与 validatorRevision 均存在
- AND 相同输入重复校验产生相同 blocking 结果和 reportDigest

### Requirement: Presentation validation SHALL verify the complete component graph

系统 SHALL 校验唯一 root、componentId 唯一性、child 引用存在性、无环、可达性、Catalog 成员资格和资源上限。任一 blocking 规则失败时 MUST NOT 生成可发布 payload。

#### Scenario: Reject an invalid component graph

- GIVEN 一个包含唯一 root 但 child 指向不存在节点的 PresentationDraft
- AND 草稿还包含一个不可达节点
- WHEN 调用 validate
- THEN data.valid 等于 false
- AND errors 分别包含 DANGLING_COMPONENT_REFERENCE 与 UNREACHABLE_COMPONENT
- AND 每个错误包含稳定 jsonPointer
- AND publish 对该 draftRevision 返回 VALIDATION_FAILED

### Requirement: Bindings SHALL be type checked without executable expressions

系统 SHALL 只接受声明式 JSON Pointer binding，并校验组件属性类型、inputSchema、精确 capability output schema 和 action payload schema 的兼容性。Presentation 对 capability 的引用 MUST NOT 隐式触发 capability 调用。

#### Scenario: Reject an incompatible capability output binding

- GIVEN Text 组件属性要求字符串
- AND binding 指向的精确 capability output schema 只允许对象
- WHEN 调用 Presentation validate
- THEN data.valid 等于 false
- AND errors 包含 BINDING_TYPE_MISMATCH
- AND error.dependencyRef 指向该精确 capability Release
- AND Runtime invocation 信息不会被创建

### Requirement: Publication SHALL lock dependencies and produce immutable content

发布系统 SHALL 对精确 draftRevision 重新校验，锁定所有 Catalog、capability schema 与 action contract ReleaseRef/digest，生成确定性领域 payload，并通过公共 Release Port 创建不可变 Release。不得发布 floating、draft、latest 或默认依赖。

#### Scenario: Publish a validated Presentation revision

- GIVEN PresentationDraft revision 4 已通过相同 validatorRevision 校验
- AND 所有依赖均为已授权、可读取且 digest 匹配的精确 Release
- WHEN 使用新的 Idempotency-Key 发布 revision 4
- THEN data.releaseRef 指向一个不可变 Presentation Release
- AND data.artifactDigest 与返回 payload 的规范化内容一致
- AND dependencyLocks 完整包含 Catalog、capability schema 与 action contract
- AND 后续修改草稿不会改变该 Release

### Requirement: Publication SHALL be idempotent under retries and concurrency

系统 SHALL 将 Idempotency-Key 与请求指纹持久化，并通过数据库唯一约束处理多实例竞争。相同 key 和相同指纹 MUST 返回同一结果；相同 key 和不同指纹 MUST 冲突。

#### Scenario: Converge concurrent publish retries

- GIVEN 两个 API 实例同时发布同一 draftId、draftRevision 与 publicationProfile
- AND 两个请求使用同一 Idempotency-Key 和相同请求指纹
- WHEN 两个事务竞争
- THEN 两个响应返回同一 releaseId 与 artifactDigest
- AND 数据库只存在一个有效 Release
- AND 不产生部分 payload 或未锁定依赖的 Release

### Requirement: Runtime consumption SHALL preserve generic ownership

PublishedPresentationResolver SHALL 通过精确 ReleaseRef 与 digest 返回 transport-neutral Artifact。Runtime SHALL 实例化 surfaceId、投影已有数据、按序发送消息、持久化 cursor 并关联 action；Composer MUST NOT 执行 capability、发送运行流或包含数字员工业务语义。

#### Scenario: Instantiate and stream an exact Presentation Release

- GIVEN Runtime 获得一个 digest 匹配的 Presentation Release
- AND Renderer 能力支持其 protocolProfile 与 catalogId
- AND 输入 dataModel 符合发布的 inputSchema
- WHEN Runtime 启动 presentation execution
- THEN Runtime 先创建 Surface 再发送依赖它的更新
- AND 每个消息带可恢复的单调 cursor
- AND Composer 不接收 run state 或业务 action
- AND 断线恢复由 Runtime 从持久化 cursor 重放

### Requirement: Renderer negotiation SHALL fail closed on unsupported assets

Web Renderer SHALL 广告 supportedCatalogIds 和协议 profile，并提供可核对精确 Catalog ReleaseRef/digest 的 RendererCatalogSupportManifest，只映射本地注册的 React 组件。Runtime 或 Renderer MUST NOT 将未知 Catalog 替换为默认/latest Catalog。用户 action MUST 带可验证的 Surface、来源组件和幂等关联信息。

#### Scenario: Reject an unsupported Catalog without fallback

- GIVEN Presentation Release 精确引用 catalogA@digest1
- AND Renderer 只广告 catalogB@digest2
- WHEN Runtime 尝试启动该 Presentation
- THEN Surface 不被创建
- AND 返回 CATALOG_UNSUPPORTED
- AND 不尝试 catalogB、latest 或运行时网络下载
- AND 不产生业务 action 或 capability 副作用

## Cross-domain contract requirements

### oss-platform-contracts input

最终共享契约必须提供不可变 ReleaseRef、digest、授权上下文、审计主体、Idempotency-Key 和请求指纹语义。A2UI 域不得另建第二套公共 Release 身份。

### oss-capability-registry input

必须能按精确 ReleaseRef 读取 capability output schema 与 action contract schema。读取只用于编译/校验证据，不等价于执行授权。

### oss-agent-workflow-runtime output expectation

Runtime 必须定义 resolver、presentation execution、stream cursor、replay、action correlation 和 typed failure contract；不得依赖数字员工业务模型。

### oss-digital-employee output expectation

数字员工必须定义 Renderer supportedCatalogIds/profile、RendererCatalogSupportManifest、React 组件映射、安全渲染、可访问性和 action 回传契约。Renderer 不拥有发布资产变更权。

## Acceptance gates

1. main-brain 批准协议 profile 与升级策略。
2. 公共 ReleaseRef/digest/幂等字段完成跨域对齐。
3. Runtime 与 Renderer 分别接受本 spec 的输入输出和失败语义。
4. Validator、PostgreSQL 并发与 publication contract 测试全部实现并通过。
5. 端到端运行证据覆盖精确 Catalog 协商、流式恢复与 action 去重。
