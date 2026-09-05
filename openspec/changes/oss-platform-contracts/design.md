# 公共平台契约设计

## 状态与原则

- Design: `PROPOSED`
- Runtime: `NO READY`
- 数据基线：开发、测试、部署均为 PostgreSQL-only；应用正确性支持多实例。
- 所有跨域引用都精确、不可变、可审计；没有隐式 latest、静默 fallback 或进程内正确性状态。

本域拥有公共外壳和发布原子语义；领域拥有自己的定义 payload、校验规则、审批/发布门禁和业务状态机。主控拥有最终跨域裁决。

## 1. 概念模型

| 概念 | 推荐语义 | 所有权 | 不负责事项 |
| --- | --- | --- | --- |
| `AssetKey` | `{workspaceId, assetType, assetId}`，稳定逻辑身份 | 公共契约定义外壳，领域登记 `assetType` | 展示名、slug 不参与身份 |
| `RevisionRef` | `AssetKey + revision + contentDigest`，创建后不可变 | 各 M 域创建内容，公共层保证引用语义 | 不定义领域校验状态 |
| `ReleaseRef` | `releaseId + RevisionRef + dependencyReleases[]`，冻结可执行/可渲染输入 | 公共发布语义；领域门禁决定能否创建 | 不定义审批流 |
| `ActivationKey` | `AssetKey + environment` | 公共契约 | 环境枚举待主控裁决 |
| `ActivationPointer` | `ActivationKey -> releaseId`，带 `pointerVersion` | 公共发布语义 | 不自动回退旧 Release |
| `PrincipalRef` | `{issuer, subject, principalType}` | 可信认证边界构造 | 不在 payload 中信任客户端声明的角色 |

`assetId` 与 `releaseId` 推荐 UUIDv7。`revision` 是单 Asset 内严格递增的正整数；允许有间隙，不承诺全局顺序。`contentDigest` 采用 `sha256:<lowercase-hex>`。JSON 载荷先按 RFC 8785 规范化；摘要覆盖哪些元数据必须由每个资产类型提交 manifest 定义并由主控确认。

## 2. 推荐的最小数据形状

以下是语义模型，不是已批准的语言类型或网络协议：

~~~json
{
  "asset": {"workspaceId": "ws_...", "assetType": "skill", "assetId": "uuidv7"},
  "revision": 3,
  "contentDigest": "sha256:..."
}
~~~

~~~json
{
  "releaseId": "uuidv7",
  "assetRevision": {"asset": {}, "revision": 3, "contentDigest": "sha256:..."},
  "dependencyReleases": [{"relation": "uses", "releaseId": "uuidv7", "contentDigest": "sha256:..."}],
  "manifestSchema": "urn:portfolio:release-manifest:v1",
  "createdAt": "RFC3339",
  "createdBy": {"issuer": "https://issuer.example", "subject": "opaque", "principalType": "USER"}
}
~~~

Release 创建后所有字段不可修改。重新校验、补依赖、改展示信息或重新构建都产生新 Release；相同规范 manifest 可按幂等规则返回原 Release。

## 3. 写入、读取与并发边界

| 逻辑方法 | 必需输入 | 成功输出 | 失败与重试 | 并发边界 |
| --- | --- | --- | --- | --- |
| `CreateRevision` | `AssetKey`、领域 payload、`expectedHeadRevision`、`idempotencyKey`、可信主体 | `RevisionRef`、`createdAt` | 校验失败不可重试；超时可用同键重试 | 比较 asset head；旧期望值失败，不覆盖 |
| `CreateRelease` | 精确 `RevisionRef`、精确依赖 Release、manifest schema、幂等键、可信主体 | 完整 `ReleaseRef` | 缺依赖/摘要不符失败关闭；未知提交结果只用同键查询或重试 | 唯一幂等指纹；Release 本身只插入不更新 |
| `ActivateRelease` | `ActivationKey`、`releaseId`、`expectedPointerVersion`、幂等键、可信主体 | 新 `ActivationPointer` 与审计信息 | 冲突需重读并由调用方决定；不得自动 latest-wins | PostgreSQL 条件更新/CAS，一次只有一个胜者 |
| `ResolveRelease` | 精确 `releaseId`，或显式 `ActivationKey` | Release manifest、摘要、pointerVersion（如经 Pointer） | 不存在/无权访问失败关闭；只读暂时错误可退避重试 | 一次 Run 开始后钉住 releaseId，不随 Pointer 漂移 |

HTTP 映射推荐用 `ETag`/`If-Match` 表达 `expectedPointerVersion`；缺少必须的前置条件返回 428，值过期返回 412。若非 HTTP 传输，必须保持等价 CAS 语义。409 只用于非前置条件的领域冲突。

幂等键的作用域为 `workspaceId + principal + logicalMethod`。服务端保存请求规范摘要与结果：同键同摘要返回首次结果；同键异摘要返回 `IDEMPOTENCY_KEY_REUSED`。保留时长、最大键长度和最终 Header 名待主控裁决；当前 IETF Idempotency-Key 仍是草案，不作为已冻结标准。

## 4. 授权主体与审计

认证技术可以变化，但领域服务接收的可信上下文必须至少包含：

- `PrincipalRef.issuer + subject`：联合形成稳定主体键；`subject` 本身不得假设全局唯一。
- `principalType`: `USER` 或 `SERVICE`；代理执行可另带 `delegationId`，不能覆盖原主体。
- `workspaceId`：资源隔离边界，由可信中间件解析并与路径/资源核对。
- `traceparent`：按 W3C Trace Context 传播，仅用于追踪，不承载身份或个人信息。

公共操作权限建议为 `asset.readRevision`、`asset.createRevision`、`release.create`、`release.activate`、`release.read`；各领域提交增量权限。角色到权限的映射由产品/部署策略拥有，公共资产不可把角色名固化进 manifest。

默认拒绝。403 与 404 的选择必须服从不泄露资源存在性的策略；错误详情、事件和审计不得包含令牌、凭证或完整敏感 payload。所有创建 Revision、创建 Release、切换 Pointer 的成功与拒绝都要有主体、资源、结果、时间和 trace 关联的审计记录。

## 5. 公共错误约定

HTTP 错误采用 `application/problem+json`，保留 RFC 9457 的 `type`、`title`、`status`、`detail`、`instance`，并增加：

~~~json
{
  "type": "https://docs.example/problems/precondition-failed",
  "title": "Precondition failed",
  "status": 412,
  "detail": "The activation pointer has changed.",
  "instance": "urn:problem:uuidv7",
  "code": "ACTIVATION_VERSION_MISMATCH",
  "traceId": "32-lowercase-hex",
  "retryable": false,
  "violations": [{"path": "expectedPointerVersion", "reason": "stale"}]
}
~~~

`detail` 只供人读，客户端只分支稳定的 `code`、HTTP status 与结构化扩展。建议映射：400 格式错误，401 未认证，403 无权，404 不存在/隐藏，409 领域冲突或幂等键复用，412 前置条件失败，422 领域校验失败，429 限流，503 暂时不可用。只有服务端明确 `retryable=true` 时客户端才自动重试；429/503 可配 `Retry-After`。

## 6. 公共事件约定

事件推荐 CloudEvents 1.0 JSON 信封。必需字段为 `specversion=1.0`、`id`、`source`、`type`、`subject`、`time`、`datacontenttype`、`data`；`dataschema` 在有稳定公开 schema 时提供。公共扩展建议为 `workspaceid`、`aggregateversion`、`correlationid`、`causationid` 与 `traceparent`。

- 交付是至少一次，不承诺 exactly-once；消费者以 `(source,id)` 持久化去重。
- 只保证同一聚合根的 `aggregateversion` 单调，不承诺跨资产全局顺序。
- 消费者遇到重复事件必须无副作用；遇到缺口或倒序必须延迟、重取聚合或进入可观测失败，不能猜测填补。
- 生产者只在业务事务提交后发布。实现阶段推荐 PostgreSQL transactional outbox，但本 change 不提交 DDL。
- 事件 `data` 只携带最小引用与变更事实；大 payload 通过有授权的精确 Release/Revision 读取。
- 领域事件类型和 data schema 由领域提交，公共层只校验信封、命名、版本和去重边界。

建议首批公共事件：`asset.revision.created.v1`、`release.created.v1`、`activation.changed.v1`。完整命名域由主控统一，不能由本任务单方面冻结。

## 7. 发布与运行数据流

1. 领域在 M 端校验输入并调用 `CreateRevision`，产生新的不可变 Revision。
2. 领域发布门禁通过后提交 Revision 和精确依赖 Release，公共层验证引用与摘要并创建 Release。
3. 有权主体以当前 Pointer 版本执行 `ActivateRelease`；事务写入新 Pointer、审计和 outbox。
4. Runtime 在 Run 开始时以显式环境解析一次 Pointer，保存 `releaseId + contentDigest + pointerVersion`。
5. 后续 Pointer 变化只影响新 Run；恢复中的 Run 继续使用已钉住 Release。

任何步骤失败都不得自动换用旧 Revision、旧 Release、其他环境或可变 head。

## 8. 六个领域必须提交给主控的接口需求

| 领域 | 必须提交的输入 | 必须提交的输出/事件 | 必须说明的边界 |
| --- | --- | --- | --- |
| Skill registry | Skill manifest 的摘要覆盖范围、依赖类型、创建/发布权限 | Revision/Release payload schema、校验错误码、领域事件 | 名称唯一性、兼容性和发布门禁；不得自建公共 Release 语义 |
| Capability registry | 输入/输出 schema 格式、provider binding 是否进入摘要、Runtime 调用身份 | 可执行 Capability Release、调用端口版本、错误映射和事件 | 注册与真实业务实现分离；超时/副作用/幂等由调用契约明示 |
| A2UI composer | 组件与 composition 的资产拆分、动作引用、资源依赖 | 可渲染 Release、presentation/action schema、事件 | M 端组合、Runtime 搬运/校验、B 前端渲染三方边界 |
| Workflow composer | 图 manifest、Skill/Capability 精确依赖、编译产物摘要 | Runtime 可消费的 graph Release、校验错误和事件 | 图校验/发布与运行调度状态机分离 |
| Agent/Workflow Runtime | 解析/缓存所需字段、run pin 证据、调用主体、事件关联 | 接受的 Release contract、运行引用回执、不可重试错误清单 | 不解析数字员工业务语义；缓存不可覆盖 PostgreSQL 真值 |
| Digital employee | workspace/用户主体传播、启动时选择环境、A2UI action 授权 | 前后端所需查询投影、错误本地化字段、run/trace 关联 | 产品语义和适配器归 B 产品；Runtime 合同保持通用 |

每个领域还必须给出：方法名或端点候选、必需/可选字段、版本策略、权限矩阵、幂等范围、并发期望、超时/重试责任、负向场景与最小 fixture。主控在 Wave 2 统一后，公共层才可生成共享 schema/SDK。

## 9. PostgreSQL 与多实例实现门禁

- 身份、revision、Release、Pointer、幂等结果、审计、outbox 和消费者去重均需持久化。
- 唯一约束/条件更新承担并发正确性；进程锁、单机定时器、缓存只可优化，不能成为真值。
- 至少用两个 API/worker 实例的集成测试证明并发 revision、Pointer CAS、重复命令和重复事件。
- 不创建 MySQL/SQLite profile，也不提供数据库不可用时的内存 fallback。

## 10. 待主控裁决（最多三个架构闸门）

1. 是否批准“四层分离”以及 Release manifest 的公共 schema 版本策略；推荐批准。
2. 是否批准 HTTP + RFC 9457 + CloudEvents 1.0 作为首个跨模块基线，并由未来 ADR 冻结具体传输；推荐批准外壳、保留消息载体选择。
3. `environment` 的首批值、Pointer 作用域和幂等键保留策略；推荐 MVP 仅 `preview`/`stable`，Pointer 作用域为 `workspace + asset + environment`。

## 11. 失效与重新评估触发器

若主控选择单仓同进程也不放松边界；若未来需要跨仓、签名制品、离线镜像或多租户，再评估 OCI/签名/策略引擎。若跨语言固定样例不能产生同一摘要，必须阻止发布并重新选择规范化方案。
