# Design: Phase 1 Skill Registry and use_skill

> Design status: **PROPOSED against SW-P1-20260907.2**
> Runtime readiness: **NO READY**
> 公共 contract 字段和 HTTP/Tool schema 尚未冻结；本设计只提交本域语义和消费者需求。

## 1. Role and Invariants

Skill 是由 AI 执行的指令与资源集合，不是业务 Workflow 子图。Skill Registry 是 M 侧定义时模块；通用 Runtime 是唯一执行方。

必须保持：

- 同一发布 Skill 在对话和 Workflow 中使用同一 package、同一 `skillKey`、同一 `use_skill` 消费路径。
- Skill 内容不包含 Workflow 节点 ID、路由候选、分支选择字段或 Workflow 专用输出。
- Runtime 使用 Python、Deep Agents SDK 与 LangGraph；本服务语言由 main-brain 结合统一 packaging 决定。
- 所有正确性状态落 PostgreSQL；PRT/ONLINE 分库，多实例不依赖进程内锁。
- 共享解析、发布、授权和版本比较由 contracts 单一实现。
- Skill Registry 不执行包内脚本，不把 `allowed-tools` 当授权。
- Skill 发布独立于 Workflow 发布。

## 2. Ownership

| Concern | Owner | Skill Registry boundary |
| --- | --- | --- |
| 目录元数据、作者态草稿、Skill revision、包校验结果 | Skill Registry | Own |
| asset identity、package/release reference、环境解析、版本比较、授权错误 | Platform Contracts | Consume only |
| `use_skill` Tool 与 model loop | Runtime | Supply consumer requirements and fixtures |
| Workflow graph and Skill node placement | Workflow Composer | Workflow references published Skill; no reverse dependency |
| Ability invocation | Capability Registry + Runtime `execute_ability` | Skill metadata may describe need; never grants access |
| A2UI rendering/completion | A2UI + Runtime | No Skill-specific renderer or completion policy |
| business idempotency | Called API backend | Not owned by Skill/Workflow |

## 3. Catalog and Authoring

### SkillCatalogEntry

- `skillKey`：跨环境稳定的逻辑引用；精确形状由 contracts 决定。
- `namespace`、`slug`：创建后不可变。
- `displayName`、`description`、`tags`：目录发现元数据。
- `metadataRevision`：作者态乐观并发版本。
- `lifecycleState`：候选 `ACTIVE | ARCHIVED`。

普通目录响应不得包含正文、资源 bytes、内部 locator、凭证或管理员字段。

### SkillRevisionDraft

管理员作者态内容：

- `skillKey`、`semanticVersion`。
- 共享 package reference。
- Agent Skills metadata 摘要和校验 fingerprint。
- 可选 `requiredToolNames`，只用于兼容性提示与发布校验，不代表授权。
- `generation` 用于 compare-and-set。

不得包含 `workflowReleaseRef`、固定 graph、route/result adapter 或环境/userId 覆盖字段。

### Published Skill

公共发布层返回不可变 Skill release/reference。Skill Registry 只保存其本域关联，不复制共享发布状态机。一个发布 Skill 不知道它会被多少个 Workflow 或会话消费。

## 4. Candidate Package Contract

Phase 1 候选包与 [Agent Skills Specification](https://agentskills.io/specification) 兼容：

```text
<skill-name>/
├── SKILL.md              # required
├── references/           # optional, read-only material
├── assets/               # optional, read-only material
└── scripts/              # optional by public spec; non-executable in Phase 1
```

`SKILL.md` frontmatter：

- required：`name`、`description`；
- optional：`license`、`compatibility`、string-to-string `metadata`；
- `allowed-tools` 是实验字段，只能作为提示，不能提升 Runtime 权限；
- `name` 必须匹配包目录名；
- body 是通用指令，不得要求调用者输出 Workflow 路由字段。

Registry revision envelope 可以附带 `requiredToolNames`，但不会把 Tool/Ability 版本解析为固定业务图。具体 Tool 授权和环境版本由执行时 trusted context 决定。

公共 package reference 必须满足消费者性质：不可变 content digest、media type、size、受控 fetch handle、无内嵌 credentials。确切 schema 由 contracts owner 定义。

## 5. Validation

只读 inspector 校验：

1. package reference 可被后端授权读取，且不接受模型提供任意 URL。
2. 读取前后核对 size/digest；不匹配即 fail closed。
3. 设置 bytes、文件数、单文件、路径深度和超时上限。
4. 拒绝绝对路径、`..`、设备文件和逃逸 symlink。
5. 校验 `SKILL.md` frontmatter、name/目录一致性和 UTF-8 文本边界。
6. references/assets 只作为资源；scripts 只登记为非执行内容。
7. 不执行 Markdown、scripts 或 `allowed-tools`。
8. 不把 `workflow`、`route`、`nextNode` 等字段加入 SkillWeave revision envelope。
9. 同一个 package digest 不得因 chat/workflow 消费模式产生不同内容。

## 6. use_skill Consumer Requirements

### Model-visible input

推荐最小输入只有：

```json
{"skillKey": "demo/evidence-first-brief"}
```

模型不得提供 `userId`、environment、gray target、credentials、package locator 或精确数据库。requestId/runId/nodeId 等控制上下文由 Runtime 生成或注入，不作为身份选择入口。

### Trusted input

Runtime 从可信后端上下文提供：

- `userId`；
- environment（PRT 或 ONLINE）；
- conversation/run/node scope；
- authorization principal；
- 当前 configuration/version evidence。

### Required resolution

1. 先用 trusted context 调共享 environment-local resolver。
2. PRT 只得到 PRT current。
3. ONLINE 只得到 ONLINE stable 或基于 userId 的 ONLINE gray；绝不访问 PRT。
4. resolver 返回精确 Skill release/version/package reference 与配置版本证据。
5. Registry material reader 校验发布状态、授权和 digest 后返回正文及受控资源句柄。
6. Runtime 将 material 加入当前 agent/node 上下文，继续同一模型/Tool loop；不得启动 per-Skill graph。

### Candidate success material

字段名待 contracts/Runtime 审核，但语义至少包括：

- resolved Skill identity/release/version；
- configuration/version evidence，供执行及 continue ingress 比较；
- instructions；
- resource descriptors/opaque handles；
- required Tool compatibility hints；
- immutable content digest。

结果不得带可复用凭证、服务器文件路径或可绕过授权的原始 locator。

### Failure semantics

- `SKILL_NOT_FOUND`：当前环境无发布版本。
- `SKILL_FORBIDDEN`：主体无正文/资源使用权。
- `SKILL_VERSION_MISMATCH`：有效配置与 run 证据不一致；Runtime 在新业务调用前提示显式 reset。
- `SKILL_PACKAGE_INVALID`：发布内容/校验证据无效。
- `SKILL_MATERIAL_UNAVAILABLE`：受控后端暂时不可用；这是 Tool failure，不得扩展为通用 Skill node retry。
- `SKILL_ENTRY_BYPASS_DENIED`：试图通过 native directory、locator 或模型提供环境直接加载。

最终 code 由 contracts owner 统一。

## 7. Environment-local Resolution

| Serving environment | Database/read candidates | Forbidden |
| --- | --- | --- |
| PRT | PRT current only | ONLINE stable/gray、任何 fallback |
| ONLINE stable user | ONLINE stable only | PRT、gray 未命中版本 |
| ONLINE gray user | ONLINE gray only | PRT；第三 serving version |
| rollout complete | one ONLINE current version | 历史版本继续新工作 |

`userId` 是唯一灰度身份字段。任何 sellerId/tenantId 等第二身份或模型提供 userId 的方案均拒绝。

## 8. Authorization

| Actor/action | Browse discovery metadata | Load via use_skill | Create/edit/validate/publish |
| --- | --- | --- | --- |
| Ordinary user | Allowed | Allowed only when B-side authorization passes | Denied |
| Administrator | Allowed | Subject to same execution authorization | Allowed in current M environment |
| Model/tool caller | Sees allowed discovery set | Calls `use_skill(skillKey)` only | Cannot choose identity/environment or author |

读目录不等于获得正文/资源读取权；管理员权限也不自动变成 Runtime business authorization。

## 9. Concurrency and Persistence

- PostgreSQL unique constraints protect logical identity, revision/version and scoped idempotency。
- metadata/draft updates use expected revision/generation compare-and-set。
- publication uses shared idempotent contract; timeout is unknown outcome and must query/retry with the same control request key。
- multi-instance readers always resolve current environment configuration through shared contract; process cache is advisory only。
- version evidence is returned with every loaded material so Runtime can apply the baseline's lightweight mismatch/reset admission。
- registry validation retry is authoring-control retry, not Workflow node retry；不得把它推广为 Skill model/Tool 自动恢复。

## 10. Deep Agents Mapping

[Deep Agents Skills](https://docs.langchain.com/oss/python/deepagents/skills) documents native directory-based skill discovery and `skills=[...]`. Phase 1 intentionally does not pass the M registry as a parallel native skills source. [Deep Agents customization](https://docs.langchain.com/oss/python/deepagents/customization) supports explicit Tools and Middleware；Runtime owner can implement `use_skill` with those public extension points.

If Runtime later projects authorized material into a Backend path for context management：

- projection happens only after successful `use_skill`；
- path is scoped to the current trusted execution；
- it does not create a second discovery/activation path；
- scripts remain non-executable unless a future, separately approved sandbox Tool permits them。

## 11. First Implementation Slice after Review

Only after main-brain names the approved contracts revision：

1. scaffold `services/skill-registry/` in the coordinator-approved service language/layout；
2. implement package validator core against local in-memory file descriptors and the approved package reference interface；
3. implement catalog/material ports with explicit trusted context parameters at the service boundary；
4. add synthetic positive/negative contract tests；
5. keep PostgreSQL repository interface explicit；do not create SQLite/MySQL fallback；
6. do not integrate Runtime or start services until the dependent interface review allows it。

## 12. Open Questions for main-brain

1. Approved shared revision and exact names for trusted context、environment-local resolver、package reference and version evidence。
2. Whether `requiredToolNames` belongs in Skill revision metadata or is derived only from instructions；either way it must not grant authorization。
3. Coordinator-approved service language/layout for `services/skill-registry/` and whether the first slice may use an in-memory test repository before the PostgreSQL adapter exists。
