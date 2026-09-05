# Design: Skill Registry

> Design status: **PROPOSED**
> Runtime readiness: **NO READY**
> Contract names and HTTP paths below are review vocabulary, not frozen public API.

## Context and Invariants

Skill Registry 属于 M 侧定义时平面。它负责回答“有哪些 Skill、某个版本引用什么包、依赖是否可解析、哪个发布引用可消费”，不负责回答“这个 Skill 如何运行”。首片必须满足：

- PostgreSQL 是开发、测试和部署唯一关系型存储；多实例共享 PostgreSQL。
- 发布内容不可变；Runtime 只消费精确 release 和 digest。
- 进程内锁、缓存和本地文件不得成为正确性来源。
- 包内容可以包含脚本，但注册平台永不执行脚本。
- 公共 identity/release/auth/revocation 语义由 `oss-platform-contracts` 冻结。
- 本域不得读取 Capability/Workflow 私有表，只通过其稳定查询/校验端口协作。

## Ownership

| Concern | Owner | Skill Registry responsibility |
| --- | --- | --- |
| Skill 目录、可编辑展示元数据 | Skill Registry | 全量拥有 |
| Skill 版本草稿、不可变 revision、校验报告 | Skill Registry | 全量拥有 |
| 公共 asset/release identity、授权、幂等、撤销 | Platform Contracts | 提交需求并调用，不复制实现 |
| Blob 上传、下载、保留与签名 | Artifact/Release provider | 仅保存无密钥 descriptor 并校验 |
| Capability 契约与 release 状态 | Capability Registry | 声明 requirement，解析并锁定 |
| Workflow 图与 release 状态 | Workflow Composer | 绑定精确 Workflow release |
| Agent/Workflow 执行 | Generic Runtime | 仅输出可消费的 PublishedSkillRef |
| 业务语义与页面渲染 | Digital Employee | 不拥有 |

## Recommended Domain Model

### 1. SkillCatalogEntry

可编辑目录外壳：

- `skillId`：公共 `AssetIdentity` 派生的稳定标识。
- `namespace`、`slug`：创建后不可变，组合键全局唯一。
- `displayName`、`summary`、`tags`：可编辑展示元数据。
- `lifecycleState`：首片只需 `ACTIVE | ARCHIVED`。
- `metadataRevision`：单调递增，用于 compare-and-set。
- `createdAt`、`updatedAt`、审计主体引用。

归档只阻止新 revision/publish；既有 release 是否可继续解析由公共撤销策略决定，不能通过删除目录记录悄然失效。

### 2. SkillVersionDraft

作者构建区，尚不可被 Workflow 或 Runtime 引用：

- `draftId`、`skillId`、`semanticVersion`。
- `packageDescriptor`：公共、内容寻址描述符。
- `capabilityRequirements[]`：`capabilityKey + semverRange`；MVP 全部为 required。
- `generation`：任何字段变化时递增。
- `state`：`DRAFT | FREEZING | FROZEN | REJECTED`。

草稿编辑不会改写任何已冻结 revision。

### 3. SkillRevision

由 draft freeze 产生的不可变定义，供 Workflow 编排引用：

- `skillRevisionRef`：稳定、不可变。
- `skillId`、`semanticVersion`。
- `packageDescriptor` 与声明依赖的完整快照。
- `sourceDraftGeneration`、`createdAt`。
- `revisionDigest`：对规范化 revision envelope 计算的 digest。

同一 Skill 的同一 SemVer 可以在发布前产生多个被拒绝 revision，但只能有一个成功 Skill Release；是否进一步限制为单 revision 由实现期产品体验决定。

### 4. ValidationReport and DependencyLock

`ValidationReport` 至少包含：

- `validationId`、`skillRevisionRef`、`status`（`PASSED | FAILED | RETRYABLE`）。
- `checks[]`：稳定 code、severity、message、field/path，不回显包内容或密钥。
- `policyVersion`、`validatedAt`、`expiresAt`。
- `dependencyLock`：每个声明 requirement 对应的精确 `CapabilityReleaseRef` 与 digest。
- `validationFingerprint`：revision digest、dependency lock、policy version 的规范化摘要。

Workflow 不作为 draft 范围解析：最终发布请求必须提供精确 `WorkflowReleaseRef`，并证明该 Workflow 绑定当前 `SkillRevisionRef`。

### 5. PublishedSkillRef

公共发布协议成功后返回，建议至少可表达：

- `skillId`、`skillRevisionRef`、`releaseId`、`semanticVersion`。
- Skill package `ArtifactDescriptor`。
- 精确 `WorkflowReleaseRef`。
- 精确 capability dependency lock。
- `releaseDigest`、`publishedAt`、公共状态。

最终字段、revision/release 命名、授权与撤销状态由 `oss-platform-contracts` 决定。

## Agent Skills Package Validation

首片按 [Agent Skills Specification](https://agentskills.io/specification) 做只读结构校验：

1. 通过受限 `ArtifactInspectorPort` 读取 descriptor 指向的制品；locator 必须符合共享 allowlist，避免任意 URL/SSRF。
2. 下载前检查声明 size 上限，读取时设置字节、文件数、路径深度和超时配额。
3. 对收到的字节重新计算 digest 并核对 size；不一致即失败，不重试为业务成功。
4. 拒绝路径穿越、绝对路径、设备文件和逃逸 symlink；不执行任何内容。
5. 必须有根目录 `SKILL.md`，其 YAML frontmatter 至少含合法 `name` 与 `description`；name 与目录名一致。
6. `license`、`compatibility`、`metadata` 按公开规范解析；`allowed-tools` 当前为实验字段，只记录兼容性警告，不解释为 Runtime 授权。
7. 额外业务依赖保存在 registry revision envelope，不私自扩展 Agent Skills 标准 frontmatter。

压缩/传输格式、media type、上限值和 inspector 部署方式在共享 descriptor 决策后确定。本域不建设通用 ZIP 管理器。

## Proposed Commands and Queries

| Operation | Proposed method | Required input | Success data |
| --- | --- | --- | --- |
| 注册目录 | `POST /api/v1/skills` | namespace, slug, displayName, summary, tags, idempotencyKey | skillId, metadataRevision, lifecycleState |
| 编辑元数据 | `PATCH /api/v1/skills/{skillId}` | expectedMetadataRevision, changed fields | skillId, metadataRevision, updatedAt |
| 查询目录 | `GET /api/v1/skills` | query/tags/cursor/limit | items, nextCursor |
| 创建版本草稿 | `POST /api/v1/skills/{skillId}/versions` | semanticVersion, packageDescriptor, requirements, idempotencyKey | draftId, generation, state |
| 冻结 revision | `POST /api/v1/skill-version-drafts/{draftId}/freeze` | expectedGeneration, idempotencyKey | skillRevisionRef, revisionDigest |
| 发起校验 | `POST /api/v1/skill-revisions/{revisionRef}/validations` | idempotencyKey | validationId, status |
| 发布 Skill | `POST /api/v1/skill-revisions/{revisionRef}/publications` | validationId, validationFingerprint, workflowReleaseRef, metadataRevision, idempotencyKey | publishedSkillRef |

HTTP 风格和错误 envelope 待公共 API 规范裁决；语义边界不依赖 REST。

## Validation and Publication Flow

1. 作者创建/编辑 catalog 和 version draft。
2. freeze 在 PostgreSQL 中以 `expectedGeneration` 原子比较并创建不可变 SkillRevision。
3. validator 校验包结构、完整性和 capability requirements；解析成功后生成精确 dependency lock。
4. Workflow Composer 使用 `SkillRevisionRef` 产出精确 `WorkflowReleaseRef`。
5. publish gate 重新核对：
   - catalog 为 ACTIVE；
   - SemVer 尚未被该 Skill 发布；
   - ValidationReport 为 PASSED、未过期且 fingerprint 匹配；
   - dependency releases 与 Workflow release 仍是可发布/可消费状态；
   - Workflow 确实绑定当前 SkillRevisionRef；
   - 请求 metadataRevision 仍存在，并快照展示元数据。
6. Skill Registry 调用公共 PublicationPort。成功后保存公共 `PublishedSkillRef`；Runtime 不得回查 draft 或本域私表。

这是一条有意的两阶段链路，用 `SkillRevisionRef` 打破 Skill/Workflow 相互发布依赖。若共享发布协议提供原生 bundle/assembly，则可重新评估。

## Failure, Retry and Expiry Boundaries

| Condition | Classification | Behavior |
| --- | --- | --- |
| 非法 metadata、SemVer 或 Agent Skills 结构 | Deterministic | 返回稳定校验 code；修改输入后新建/更新 draft，不自动重试 |
| digest/size 不匹配 | Integrity failure | 立即失败并审计；不得降级信任 locator |
| artifact/capability/workflow 端口 timeout、429、5xx | Retryable | validation 保持 RETRYABLE；后台最多 3 次指数退避加抖动，超限等待显式重试 |
| capability range 无匹配或 workflow binding 错误 | Dependency failure | 阻止发布；依赖可用后重新校验，不复用旧 PASSED |
| ValidationReport 过期或 policyVersion 变化 | Stale evidence | 发布失败为 stale；重新校验生成新 fingerprint |
| PublicationPort 响应丢失 | Unknown outcome | 使用同一 idempotencyKey 查询/重试，禁止创建第二 release |
| 依赖 release 在发布前撤销 | Invalidated | 最终 gate 阻止发布；已发布 Skill 的后续处置遵循公共撤销策略 |
| catalog ARCHIVED | Policy failure | 禁止新 revision/publish；不隐式删除历史 release |

成功校验只对给定 revision digest、dependency lock 和 policy version 有效。任何一个输入变化都令旧报告失效。

## Concurrency and Multi-instance Correctness

- `namespace + slug`、`skillId + semanticVersion` 的发布结果、idempotency key 由 PostgreSQL 唯一约束兜底。
- 元数据更新使用 `expectedMetadataRevision`；版本草稿 freeze 使用 `expectedGeneration`。冲突返回当前 revision/generation，服务端不做静默覆盖。
- 校验任务以 PostgreSQL lease/状态原子领取；同一 validation 被多个实例看到时只能一个实例完成状态转换。具体可采用行锁/`SKIP LOCKED`，实现期验证。
- 发布状态转换使用 compare-and-set；公共 PublicationPort 的幂等 key 与本地 publication record 绑定。
- 缓存只加速目录读取；发布 gate、唯一性、状态与幂等始终回到 PostgreSQL。
- 跨模块不追求分布式事务。采用可查询的幂等操作和本地 outbox（若需要事件）恢复，不把“请求超时”当“操作失败”。
- 目录分页建议按稳定 `publishedAt, releaseId` 游标；首片不承诺搜索索引的读后即一致。

## Security and Privacy Boundary

- locator 不得携带 token、签名参数或明文凭证；凭证由 ArtifactPort 的服务器侧配置提供。
- 错误与审计记录只保存 descriptor、稳定 code、主体引用和摘要，不持久化包正文。
- 授权至少区分目录读取、元数据编辑、revision 创建和发布；具体 principal/role 由公共合同定义。
- 所有外部引用均进行 namespace/host/scheme allowlist 校验，并设置下载上限。
- 包内脚本、声明的 tools 和 Markdown 都是非信任数据；本域只解析，不执行，也不把 allowed-tools 当授权。
- PostgreSQL 备份/恢复与审计保留属于部署治理，首片只声明需要，不宣称完成。

## Observability Contract

每个命令生成或透传 `requestId`；日志/指标以 skillId、revisionRef、validationId、publicationId 和稳定 errorCode 关联。禁止记录包正文、credentials 或用户输入全文。至少规划以下指标：

- registration/update/freeze/publish 成功与冲突计数；
- validation duration、retry、failure code；
- artifact bytes 与 digest mismatch；
- dependency resolution failure；
- publication unknown outcome 与恢复次数。

## Re-evaluation Triggers

- 公共 contracts 选择的制品协议无法表达 digest/mediaType/size。
- Workflow Composer 无法引用未发布但不可变的 SkillRevision。
- SemVer range 不能表达 Capability 兼容承诺，需转向显式 compatibility contract。
- 首个纵向切片证明模块化单体产生不可接受的独立扩缩容或故障隔离问题。
- 需要 Skill-to-Skill 依赖；届时单独设计循环、深度、锁文件与资源上限。
