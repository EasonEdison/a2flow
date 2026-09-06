# 业务能力注册平台 Phase 1 设计

## 1. 状态

| 项目 | 当前结论 |
| --- | --- |
| 基线 | SW-P1-20260907.2 |
| 设计 | PROPOSED / BASELINE ALIGNED |
| 共享接口 | `SW-CONTRACTS-P1-CANDIDATE.1` PROVISIONAL；等待 named approved revision |
| Runtime | Python + Deep Agents SDK + LangGraph |
| Registry backend | ENG-01：独立 Python 域模块；不自动等于独立常驻服务 |
| 数据库 | PostgreSQL-only；PRT/ONLINE 分库 |
| Runtime readiness | NO READY |
| 本批范围 | OpenSpec 对齐 + 合成契约样例，不执行真实外部写 |

## 2. 总体边界

`Capability Registry` 是 M 侧定义控制面。它管理草稿、静态验证和已发布 ability payload，不执行能力调用，不解析凭证明文，也不实现企业 API 平台。

`execute_ability` 是 Runtime 暴露给模型的统一 Tool。模型只提供已授权候选中的 `abilityKey` 和模型参数；Runtime 从隐藏的可信上下文获得 userId、环境、运行/节点标识和配置版本，再通过共享 resolver 解析生效发布版本。

```text
Model
  -> execute_ability(abilityKey, arguments)
Deep Agents / LangChain ToolRuntime
  -> inject authenticated userId + environment + run context
Shared Resolver
  -> PRT current OR ONLINE stable/gray; never cross-environment
Runtime admission
  -> version guard -> authorization -> schema/binding
CapabilityInvocationPort
  -> business adapter -> called API backend
Single Result Interpreter
  -> structured ability result
```

LangChain 官方 Tools 文档说明 `ToolRuntime` 参数由运行时注入并隐藏于模型 schema，这与 userId/environment/credential 不可由模型选择的基线一致；具体 SDK API 版本由 Runtime owner 验证后固定。

## 3. 能力发布 payload

本域 payload 候选：

- `metadata`：名称、描述、分类和可发现性信息。
- `modelArgumentSchema`：模型可填写参数的 JSON Schema。
- `resolvedInputSchema`：全部来源绑定后的 adapter 输入 schema。
- `outputSchema`：adapter 成功返回的结构 schema。
- `inputBindings[]`：按 RFC 6901 Pointer 映射模型参数、静态常量、可信上下文。
- `credentialRequirements[]`：逻辑凭证槽位；不包含环境引用或明文。
- `resultInterpretationPolicies[]`：候选 `ResultInterpretationPolicy` array，每项携带唯一 `policyRef`。
- `defaultSuccessPolicyRef`：必须解析到 array 内策略；普通 execute_ability 使用发布期默认策略，模型不可选择。
- `adapterOperationRef`：逻辑适配器操作引用，不是任意 URL 或脚本。
- `contractFormatVersion`：共享契约版本。

已发布 payload 必须由共享 `ReleaseEnvelope` 包裹并不可变。模型和普通调用方不得指定 release version；`abilityKey + trusted context` 交给共享 resolver 解析当前有效 `ReleaseRef`。

## 4. 输入来源与可信上下文

| 来源 | 示例 | 规则 |
| --- | --- | --- |
| `MODEL_ARGUMENT` | 查询词、用户明确填写的业务参数 | 不可信；只按 modelArgumentSchema 接收 |
| `STATIC_CONSTANT` | 非敏感固定枚举、adapter 固定选项 | 定义期配置；发布时校验；不得放凭证明文 |
| `TRUSTED_CONTEXT` | userId、PRT/ONLINE、授权主体、runId/nodeId | 由后端 ToolRuntime 注入；模型 schema 不可见 |
| `CREDENTIAL_REFERENCE` | credential slot 对应的不透明引用 | 由环境配置/adapter 绑定；模型和发布 payload 不持有实际引用 |

绑定规则：

1. 每个最终 required 字段由且仅由一个来源构造。
2. 不同 targetPath 不得重复、覆盖或互为祖先。
3. userId、环境、权限、凭证和生效版本禁止使用 `MODEL_ARGUMENT`/`STATIC_CONSTANT`。
4. 结构化值按类型合成，不进行字符串模板拼接和隐式类型转换。
5. 绑定后再次执行 `resolvedInputSchema` 校验。
6. 缺少可信值或 credential slot 时在 adapter 调用前失败关闭。

## 5. 环境与版本解析

共享 resolver 是所有资产类型唯一实现，本域只定义消费者需求：

### PRT

- 使用 PRT 数据库。
- 只读取 PRT 当前发布版本。
- 不接受 ONLINE stable/gray，也不提供 fallback。

### ONLINE

- 使用 ONLINE 数据库。
- 以受信 `userId` 选择 ONLINE stable 或 ONLINE gray。
- 灰度期间最多 stable/candidate 两个服务版本；结束后一个。
- 任何情况下都不得读取 PRT 版本。

### 轻量版本失配门禁

`execute_ability` 每次进入真实业务调用前，比较运行状态记录的配置版本标识与 resolver 当前有效版本：

- 一致：继续授权和参数校验。
- 不一致：返回 `CONFIG_VERSION_MISMATCH` 与 `resetRequired=true`，adapter 调用次数必须为 0。
- 不继续冻结旧资产，不静默迁移，不自动 reset，不删除历史。
- continue/recovery 与 A2UI Action ingress 也必须在其各自入口执行同一共享门禁。

## 6. execute_ability Tool 及调用顺序

模型可见输入候选：

```text
ExecuteAbilityToolInput {
  abilityKey
  arguments
}
```

模型不可见的 `TrustedAbilityContext` 候选：

```text
TrustedAbilityContext {
  userId
  environment: PRT | ONLINE
  authorizationContext
  conversationId
  runId?
  nodeId?
  observedConfigVersions
  invocationId
}
```

调用顺序固定为：

1. ToolRuntime 注入可信上下文。
2. 共享 resolver 从正确环境数据库解析当前 `ReleaseRef`。
3. 版本门禁比较 observed 与 effective 版本。
4. 授权器检查主体可调用 ability、可使用 adapter operation 和 credential slot。
5. `modelArgumentSchema` 校验模型参数。
6. 绑定常量/可信上下文，形成 resolved input 并校验。
7. 从可信环境映射得到不透明 `CredentialRef`。
8. 通过 `CapabilityInvocationPort` 调用 adapter 一次。
9. 校验 output schema，执行唯一成功解释器。
10. 返回结构化结果，不暴露 credential、内部异常或未授权上下文。

任何 1-7 的失败都必须保证 adapter 未调用。

## 7. 调用授权

最小授权决策输入：

- authenticated principal / userId；
- environment；
- abilityKey 与解析后的 releaseRef；
- adapterOperationRef；
- credential slot；
- 当前 Skill/Workflow 允许的 ability allowlist；
- 可选 runId/nodeId/actionId 关联。

授权结果必须是 `ALLOW` 或带稳定 reason code 的 `DENY`。模型描述、模型参数和 ability 文案不能扩大授权。`DENY` 必须在 schema 合成和 adapter 调用之前或至少在任何外部副作用之前生效。

管理员的 M 侧发布权限与普通用户的 B 侧调用权限分离。普通用户可调用被授权能力，但不能创建、修改或发布 ability。

## 8. 成功解释器

成功解释器必须是 Runtime 内的纯函数：输入已通过 `outputSchema` 的结果和已发布的 `ResultInterpretationPolicy`，输出结构化判定；不得进行网络调用、写数据库、触发重试或改变 Workflow 状态。Capability Registry 和 A2UI 都不得实现另一解释器。

Contracts owner 当前给出的消费候选 revision 是 `SW-CONTRACTS-P1-CANDIDATE.1`，仍为 PROVISIONAL：

```text
ResultInterpretationPolicy =
  | {
      contractRevision,
      policyRef,
      operator: "SCHEMA_VALID"
    }
  | {
      contractRevision,
      policyRef,
      operator: "JSON_POINTER_EQUALS",
      jsonPointer,
      expectedLiteral: JsonPrimitive
    }

ResultInterpretation {
  policyRef
  matched: true | false
  evidencePath?
  observedValueDigest?
  reasonCode
}
```

`JsonPrimitive` 只允许 string、number、boolean 或 null。首版禁止 conditions array、ANY/ALL、NOT_EQUALS、脚本、正则表达式链、模型判断和任意表达式。

`SCHEMA_VALID` 必须是显式发布并被选中的策略，不能把“output schema 通过”自动等同于业务成功。`JSON_POINTER_EQUALS` 使用 RFC 6901 JSON Pointer，并遵循以下失败关闭语义：

- `MISSING` 与 `FOUND(null)` 是不同解析结果；`MISSING` 永不匹配，reasonCode 为 `PATH_MISSING`。
- `FOUND(null)` 可与 JSON null 比较。
- string、number、boolean 与 null 只在同类型同值时相等，不做隐式转换。

Capability Registry 校验并发布 `resultInterpretationPolicies` 和 `defaultSuccessPolicyRef`。Runtime 对当前环境/userId 解析并通过版本 guard 后的精确 ability release 查找策略；这不允许冻结旧 release 继续执行，版本失配仍然 `resetRequired=true`。A2UI Action 只能对该精确 release 选择 `successPolicyRef` 并配置 `completeInteractionOnSuccess`。

四个事实必须分别记录：output schema validity、policy match、Action call、interaction completion。Ability 执行结果拥有前两项；A2UI/Runtime 交互记录拥有后两项。Finalizer 不得覆盖任何失败事实。

## 9. 逻辑端口与结果

### 9.1 PublishedAbilityCatalogPort

```text
resolve(abilityKey, trustedContext) -> EffectiveAbilityContract | ResolutionFailure
```

实现归共享 resolver/发布读取层；Capability Registry 只提供环境内发布数据。未知、未发布、跨环境、版本不支持或摘要不一致均失败关闭。

### 9.2 CapabilityInvocationPort

```text
invoke(command) -> AdapterOutcome

AbilityInvocationCommand {
  invocationId
  abilityReleaseRef
  adapterOperationRef
  resolvedInput
  credentialBindings
  deadline
  traceContext?
}
```

这是 Runtime 消费、adapter 实现的逻辑端口。它不冻结 HTTP/gRPC/消息传输，也不允许 adapter 在内部做不可见的通用无限重试。

### 9.3 ExecuteAbilityResult

```text
ExecuteAbilityResult {
  invocationId
  abilityReleaseRef?
  status:
    SUCCEEDED
    | BUSINESS_NOT_SUCCESSFUL
    | AUTHORIZATION_DENIED
    | CONFIG_VERSION_MISMATCH
    | ARGUMENT_INVALID
    | CREDENTIAL_UNAVAILABLE
    | ADAPTER_FAILURE
    | ADAPTER_TIMEOUT
    | OUTPUT_INVALID
  output?
  outputSchemaValidated?
  policyMatched?
  interpretation?
  errorCode?
  resetRequired
  adapterCalled
}
```

错误 detail 仅供人阅读，程序分支使用稳定 `status/errorCode`。未授权、版本失配和凭证失败不得返回秘密、跨环境版本或其他用户信息。

## 10. 参数与发布静态验证

发布前验证：

1. 三份 schema 通过选定方言的 meta-validation；方言最终由 contracts/main-brain 审批。
2. MVP 发布产物自包含，不运行时拉取任意远程 `$ref`。
3. Pointer 绑定无重叠且 required 输入来源闭合。
4. 可信字段/credential 不出现在模型参数和常量来源。
5. 常量通过 resolved input 的对应子 schema。
6. `resultInterpretationPolicies` 的 policyRef 唯一、default ref 可解析；JSON Pointer 可由 output schema 支持，expectedLiteral 是类型兼容的 JSON primitive。
7. adapterOperationRef 和 credential slot 引用完整。
8. 合成定义不包含凭证明文、私有 endpoint 或任意脚本。

发布 revision、幂等和摘要使用共享 contracts，正确性来自 PostgreSQL 事务/唯一约束，不依赖单实例锁。

## 11. 失败、重试与业务幂等

首版平台规则：

- `execute_ability` 对一个已授权 Tool call 最多发起一次 adapter 调用。
- 参数、版本、授权、凭证和 contract 错误不调用 adapter。
- adapter 失败/超时返回结构化事实；Runtime 不自动重试业务调用。
- A2UI Action 失败或 configured success 未命中时，是否允许重试 owning node 由 A2UI/Workflow 基线控制；新的尝试可能再次调用 API，不由 Capability Registry 保证 exactly-once。
- 被调用 API 后端拥有业务幂等键定义、重复请求识别、业务重试、对账和补偿。
- 平台 `invocationId` 只用于关联与审计，不自动等于业务幂等键。
- 平台 control request 去重只覆盖控制请求，不转换为业务调用去重。
- 全新 Workflow restart 不读取旧 run 结果，不复用旧 invocation，不检查旧业务结果。

## 12. PostgreSQL 与多实例

- 草稿、发布快照、验证报告存在当前环境 PostgreSQL。
- PRT/ONLINE 数据源必须显式选择，不允许同查询跨库 union 或 fallback。
- 多实例通过数据库 revision/唯一约束处理草稿和发布竞争。
- 缓存只加速；缓存失效不能改变环境选择、授权和有效 release。
- 本批不创建 schema/migration；等待共享 release contract 和服务布局审核。

## 13. 依赖输入输出

| 依赖 | 本域需要 | 本域提供 | 失败边界 |
| --- | --- | --- | --- |
| contracts | TrustedContext、Environment、ReleaseRef、resolver/version guard、AuthorizationDecision、CredentialRef、ResultInterpretationPolicy、错误包络 | ability payload 消费需求、合成样例 | `SW-CONTRACTS-P1-CANDIDATE.1` 仍 PROVISIONAL；未命名 approved revision 前不实现依赖代码 |
| Runtime | ToolRuntime 注入、统一 execute_ability、一次调用、唯一解释器 | model/resolved/output schema、binding、success policy、adapter ref | 不支持契约版本或失配时业务调用前失败 |
| A2UI | 精确 ability release 上的 successPolicyRef 选择、completion 配置 | 可引用的命名成功策略 | 不允许 A2UI 自建第二解释器或 ResultConditionRef |
| Skill/Workflow | ability allowlist、可信 run/node 上下文 | abilityKey 与发布引用的解析结果 | Skill 文案不能扩大授权 |
| Adapter/API backend | 逻辑 operation、credential resolution、业务响应 | validated resolved input | adapter 失败只报告；业务幂等/重试归后端 |

## 14. 待 main-brain 审阅

1. 批准“contracts 拥有 policy schema、Runtime 拥有唯一解释器、Capability 发布命名策略、A2UI 选择策略/完成条件”的四方边界。
2. 批准 `execute_ability` 最小共享字段和版本门禁失败形态；模型 schema 只暴露 abilityKey/arguments。
3. 命名首个 contracts revision，并决定 capability-registry 服务语言/包布局后放行最小实现。

## 15. 公开资料与验证限制

- Deep Agents 支持注入 custom tools：<https://docs.langchain.com/oss/python/deepagents/customization>
- LangChain ToolRuntime context 由 runtime 注入且不出现在模型 tool schema：<https://docs.langchain.com/oss/python/langchain/tools>
- JSON Schema 2020-12：<https://json-schema.org/draft/2020-12>
- RFC 6901 JSON Pointer：<https://www.rfc-editor.org/rfc/rfc6901>

这些公开入口支持当前设计方向，不证明具体依赖版本、实现或 Runtime 行为已经验证。
