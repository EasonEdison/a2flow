# 业务能力注册平台设计

## 1. 状态与约束

| 项目 | 当前结论 |
| --- | --- |
| 设计状态 | PROPOSED |
| 设计批准 | 未批准，等待 main-brain |
| Runtime 证据 | NO READY |
| 数据库 | PostgreSQL-only |
| 应用拓扑 | API/worker 可多实例；不依赖进程内正确性状态 |
| Runtime 语言 | 待统一裁决 |
| 具体传输协议及版本 | 待统一裁决 |
| 本轮范围 | 契约与验收设计，不实现代码 |

## 2. 责任边界

`Capability Registry` 属于 M 侧定义控制面，负责草稿、静态验证、发布和只读查询。它不执行业务调用，不解析业务响应含义，不保管密钥，也不提供企业 API 平台能力。

通用 Runtime 负责选择一个明确的发布版本、组装可信输入、控制 deadline/重试/幂等并记录执行状态。业务适配器由 Runtime 核心之外的模块实现；数字员工后端可以提供适配器，但 Runtime 不得依赖数字员工领域模型。

```text
M Capability Registry
  -> immutable PublishedCapabilityContract
  -> PublishedCapabilityCatalogPort
Generic Runtime
  -> source binding and schema validation
  -> CapabilityInvocationPort
Business Adapter
  -> external system
Credential Provider
  -> resolves opaque CredentialRef inside trusted boundary
```

## 3. 领域对象

### 3.1 CapabilityDraft

草稿是可修改对象，建议字段如下：

- `draftId`：草稿标识。
- `assetIdentityRef`：引用共享资产标识，不在本域重新定义。
- `draftRevision`：单调递增的并发控制版本。
- `metadata`：名称、说明、标签；不承载执行秘密。
- `contract`：能力契约 payload。
- `validationReport`：最近一次静态验证结果及其对应的 `draftRevision`。
- `createdAt/updatedAt`：审计时间。

### 3.2 CapabilityContractPayload

- `contractFormatVersion`：契约格式版本；最终值由共享契约裁决。
- `modelArgumentSchema`：仅描述模型可以生成的参数。
- `resolvedInputSchema`：描述来源绑定完成后交给适配器的最终输入。
- `outputSchema`：描述成功输出。
- `inputBindings[]`：把最终输入 JSON Pointer 映射到唯一来源。
- `credentialRequirements[]`：逻辑凭证槽位，不包含环境引用或明文。
- `invocation`：逻辑操作名、效果分类、幂等能力和 deadline 上限。
- `annotations`：非执行语义的文档信息；不得改变校验或调用行为。

推荐绑定示例：

```yaml
inputBindings:
  - targetPath: /query
    source: MODEL_ARGUMENT
    sourcePath: /query
  - targetPath: /locale
    source: STATIC_CONSTANT
    value: zh-CN
  - targetPath: /principalRef
    source: TRUSTED_CONTEXT
    sourcePath: /principalRef
```

### 3.3 PublishedCapabilityContract

发布产物由共享 `ReleaseEnvelope` 包裹本域 payload，至少需要：

- 不可变 `ReleaseRef` 与资产身份。
- 发布版本及创建时间。
- 规范化 payload 的 `contentDigest`。
- 发布时验证器/方言标识。
- 完整、自包含的本域 payload。

本域不独立发明一套全局版本和发布状态机；这些字段是提交给 `oss-platform-contracts` 的消费者需求。

## 4. 输入来源隔离

最终输入的每个叶子目标都必须由且仅由一种来源提供：

| 来源 | 所有者 | 信任级别 | 规则 |
| --- | --- | --- | --- |
| `MODEL_ARGUMENT` | 模型/Agent 输出 | 不可信 | 先按 `modelArgumentSchema` 校验；不能覆盖其他来源 |
| `STATIC_CONSTANT` | 草稿作者 | 定义期可信 | 发布时内联并校验；禁止放置密钥或令牌 |
| `TRUSTED_CONTEXT` | Runtime 认证执行上下文 | 执行期可信 | 模型与普通调用参数不可写；缺失时调用失败关闭 |

绑定目标使用 RFC 6901 JSON Pointer。MVP 规则：

1. 绑定目标不得重复、互为祖先或产生覆盖。
2. `MODEL_ARGUMENT` 必须有 `sourcePath`，且来源路径受 `modelArgumentSchema` 约束。
3. `STATIC_CONSTANT` 必须有 `value`，值必须通过对应最终输入子 schema。
4. `TRUSTED_CONTEXT` 必须引用共享可信上下文目录中的通用 key；领域业务 key 不进入 Runtime 核心。
5. 最终输入的所有 required 字段必须可由绑定闭合；额外属性默认拒绝。
6. 来源合并保持对象/数组类型，不做字符串模板拼接或隐式类型转换。

## 5. 凭证模型

发布契约只声明逻辑需求：

```text
CredentialRequirement {
  slotId
  purpose
  required
  allowedProviderKinds?  // 可选约束，待共享裁决
}
```

环境部署或适配器注册提供不透明引用：

```text
CredentialRef {
  providerId
  referenceId
  version?       // 可选固定版本；不是 secret value
}
```

边界规则：

- `CredentialRef` 不能来自 `MODEL_ARGUMENT` 或 `STATIC_CONSTANT`。
- 能力发布产物不存储环境 `CredentialRef`，只存储 `CredentialRequirement`。
- Runtime 从可信部署配置获得 `slotId -> CredentialRef`，并把引用交给适配器。
- 凭证明文只在受信凭证提供者/适配器边界内按需解析，不进入 registry API、模型上下文、发布摘要、事件或普通日志。
- 缺少必需槽位、引用不可解析或权限不满足时，在外部业务调用前失败关闭。

## 6. 静态验证与发布

发布动作必须针对一个精确 `draftRevision` 执行，并通过以下门禁：

1. **结构门禁**：三份 schema 都是指定方言的合法 schema，根类型在 MVP 为 `object`。
2. **可复现门禁**：禁止未打包的远程 `$ref`；发布 payload 自包含。
3. **绑定门禁**：目标无重叠、来源字段完整、required 最终输入全部可构造。
4. **隔离门禁**：可信上下文和凭证不能被模型/常量占位或覆盖。
5. **样例门禁**：常量值和可选契约示例通过对应 schema。
6. **执行门禁**：效果分类、幂等声明、deadline 上限组合合法。
7. **敏感门禁**：定义中不允许凭证明文；自动扫描只能辅助，命中或无法判断时阻断人工复核。

校验报告包含稳定的 `ruleCode`、JSON Pointer `path`、严重级别和可修复说明。不得依赖自然语言 detail 进行程序判断。

发布在一个 PostgreSQL 事务中完成：锁定或比较草稿版本、重跑验证、写入不可变发布快照和唯一幂等记录。任一环节失败都不产生半发布产物。

## 7. 生命周期与并发

- `DRAFT`：可更新；每次更新携带 `expectedDraftRevision`。
- `PUBLISHED`：不可变；任何修改都产生新草稿和新发布版本。
- 废弃/下线语义由共享契约统一定义，本 change 不先行冻结。

并发规则：

- revision 不匹配返回 `DRAFT_REVISION_CONFLICT`，服务端不做静默覆盖。
- 发布请求必须携带 `publicationIdempotencyKey`。
- 相同 key + 相同规范化内容返回同一发布结果；相同 key + 不同内容返回冲突。
- 两个不同 key 竞争发布同一 revision 时只允许一个成功，另一个得到明确冲突。
- 唯一约束、事务和持久化幂等表是正确性来源；不得依赖单实例锁或内存缓存。

## 8. Runtime 逻辑端口

### 8.1 PublishedCapabilityCatalogPort

```text
resolve(releaseRef) -> PublishedCapabilityContract | ContractResolutionFailure
```

- 只返回精确的、已发布、摘要可校验的版本。
- 对草稿、未知引用、摘要不一致和不支持的契约版本失败关闭。
- 缓存只能加速，不能改变 release 不可变语义。

### 8.2 CapabilityInvocationPort

```text
invoke(command) -> InvocationOutcome

InvocationCommand {
  invocationId
  attemptId
  capabilityReleaseRef
  resolvedInput
  credentialBindings: Map<slotId, CredentialRef>
  deadline
  idempotencyKey?
  traceContext?
}

InvocationOutcome {
  status: SUCCEEDED | RETRYABLE_FAILURE | TERMINAL_FAILURE | UNKNOWN
  output?
  errorCode?
  retryAfter?
  effectState: NOT_STARTED | COMMITTED | UNKNOWN
}
```

这是 Runtime 消费、适配器实现的逻辑端口，不等于已经选择 HTTP、gRPC 或消息协议。Runtime 调用前按顺序执行：

1. 解析精确发布契约并校验摘要/格式版本。
2. 单独校验 `modelArguments`。
3. 从可信执行上下文获取 `TRUSTED_CONTEXT`，从发布定义读取常量。
4. 按绑定生成 `resolvedInput`，再用 `resolvedInputSchema` 校验。
5. 从可信配置提供 `CredentialRef`；不解析为普通参数。
6. 调用适配器并对成功输出执行 `outputSchema` 校验。

输出 schema 不匹配是 `TERMINAL_FAILURE`，原始不合规输出不得作为成功结果传播。

## 9. 失败、重试与副作用

发布契约只声明重试安全属性，不配置 Runtime 的全局重试次数：

- `READ_ONLY`：同输入重复调用不产生业务副作用。
- `IDEMPOTENT_WRITE`：适配器声明支持调用方幂等键。
- `NON_IDEMPOTENT_WRITE`：可能产生不可安全重复的副作用。

边界规则：

- 参数、上下文、凭证、契约或 schema 错误均在适配器调用前终止，不重试。
- 适配器明确返回临时失败且 `effectState=NOT_STARTED` 时，Runtime 可按自身策略重试。
- 超时/断连后若副作用未知，返回 `UNKNOWN`；只有 `READ_ONLY` 或同一幂等键得到保证的 `IDEMPOTENT_WRITE` 才可自动重试。
- `NON_IDEMPOTENT_WRITE` 的 `UNKNOWN` 必须等待人工/业务对账决策。
- 所有重试复用同一 `invocationId` 和幂等键，每个物理尝试使用不同 `attemptId`。
- 适配器不得在端口内部进行不可见的无限重试。

## 10. 持久化、可观测与安全

- 草稿、发布快照、校验报告和发布幂等记录都持久化到 PostgreSQL。
- API/worker 多实例共享数据库；服务重启不能丢失已确认发布结果。
- 日志/事件只记录 releaseRef、invocationId、attemptId、ruleCode、结果分类和耗时等通用字段。
- 模型参数、可信上下文值和业务输出默认不进入日志；如需审计，仅记录策略允许的摘要/字段。
- 错误信息必须脱敏。若未来选择 HTTP，可把稳定错误码映射到 RFC 9457；当前不冻结 HTTP 表示。
- 授权主体和权限模型依赖共享安全契约；本域至少区分草稿编辑、发布、发布读取三种动作。

## 11. 依赖契约

| 依赖 | 输入给本域 | 本域输出 | 失效处理 |
| --- | --- | --- | --- |
| 共享资产/发布契约 | AssetIdentity、ReleaseRef、发布包络、内容摘要规范 | Capability payload 与验证报告 | 版本不支持或摘要不一致时拒绝发布/解析 |
| 可信上下文目录 | 通用 context key、类型和提供者责任 | 本域声明的 context requirement | 未知 key 或运行时缺失时失败关闭 |
| Runtime | deadline、执行上下文、幂等/trace 元数据、环境 credential binding | 已发布契约、逻辑调用端口与结果分类 | 不支持契约版本时不得降级到草稿/旧格式 |
| 业务适配器 | 对逻辑端口的实现、凭证解析、外部调用结果 | resolvedInput、CredentialRef、调用元数据 | 超时按 effectState/幂等语义分类，不猜测副作用 |
| Skill/Workflow | 精确能力 releaseRef | 可解析的不可变能力契约 | 引用不存在/未发布时组合或执行失败 |

## 12. 待 main-brain 裁决

1. 是否批准 JSON Schema Draft 2020-12 作为首个共享数据契约方言，以及禁止远程 `$ref` 的 MVP 能力集。
2. 是否批准逻辑端口先于传输绑定，并由哪个任务拥有 `ReleaseRef`、错误包络、可信上下文目录和 `CredentialRef` 的共享定义。
3. 效果/幂等枚举是否进入共享调用契约；HTTP、gRPC 或消息传输映射何时冻结。

## 13. 重新评估触发器

- 首个真实垂直切片无法用 JSON 值表达输入/输出。
- 选定传输协议提供了更强且跨语言可用的正式 IDL。
- schema 验证器在目标语言间出现无法收敛的兼容性差异。
- 凭证提供者需要跨环境可移植的标准引用格式。
