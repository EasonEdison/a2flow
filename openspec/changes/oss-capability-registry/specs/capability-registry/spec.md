# Capability Registry Specification

## ADDED Requirements

### Requirement: 草稿必须支持并发安全的修改

系统 SHALL 以 `draftRevision` 表示草稿并发版本。更新必须携带 `expectedDraftRevision`；不匹配时不得覆盖服务器内容。

#### Scenario: 过期 revision 更新草稿

- **WHEN** 客户端使用旧 `expectedDraftRevision` 更新已被其他实例修改的草稿
- **THEN** 系统返回 `DRAFT_REVISION_CONFLICT`，且草稿内容与 revision 均保持最新已提交值

### Requirement: 最终输入必须按来源隔离

系统 SHALL 分别维护 `modelArgumentSchema`、`resolvedInputSchema` 和 `inputBindings`。每个最终 required 输入必须由 `MODEL_ARGUMENT`、`STATIC_CONSTANT` 或 `TRUSTED_CONTEXT` 中恰好一个来源构造；来源不得覆盖。

#### Scenario: 两种来源竞争同一输入路径

- **WHEN** 草稿把同一 targetPath 同时绑定为模型参数和可信上下文
- **THEN** 静态验证返回路径冲突，发布不产生任何 release

### Requirement: 可信上下文和凭证必须失败关闭

系统 SHALL 禁止模型参数提供可信上下文或 `CredentialRef`。必需可信上下文或凭证槽位缺失时，Runtime 必须在调用适配器前终止。

#### Scenario: 模型伪造可信身份字段

- **WHEN** 模型参数包含只允许由 `TRUSTED_CONTEXT` 提供的字段，且 Runtime 没有对应可信值
- **THEN** Runtime 拒绝组装输入，适配器不被调用，错误不得回显凭证明文或可信值

### Requirement: 发布前必须进行确定性静态验证

系统 SHALL 在发布事务内针对精确 draftRevision 重跑 schema、远程引用、绑定闭合、来源隔离、常量、执行声明和敏感信息门禁。失败报告必须包含稳定 ruleCode 与 JSON Pointer path。

#### Scenario: required 字段没有来源

- **WHEN** `resolvedInputSchema` 声明一个 required 字段，而 `inputBindings` 无法构造该字段
- **THEN** 发布失败并返回定位该字段的稳定规则错误，数据库中不存在部分发布产物

### Requirement: 已发布契约必须不可变且可精确寻址

系统 SHALL 将发布内容写入共享 `ReleaseEnvelope`，保存规范化内容摘要，并只允许通过精确 `ReleaseRef` 读取。草稿不得被 Runtime 当作发布版本消费。

#### Scenario: 两实例并发发布同一 revision

- **WHEN** 两个应用实例用不同幂等键并发发布同一 draftRevision
- **THEN** 只有一个请求创建不可变 release，另一个收到明确冲突，已发布内容与摘要保持不变

### Requirement: Runtime 必须通过逻辑端口消费能力

系统 SHALL 提供 `PublishedCapabilityCatalogPort` 的只读语义，并定义 Runtime 消费、业务适配器实现的 `CapabilityInvocationPort`。逻辑端口不得预先绑定 Runtime 语言或传输协议。

#### Scenario: 精确发布版本被调用

- **WHEN** Runtime 解析一个受支持的 releaseRef，校验模型参数并以三类来源构造最终输入
- **THEN** 适配器收到通过 `resolvedInputSchema` 的输入、逻辑凭证引用、deadline 和调用标识，且调用记录关联同一 releaseRef

### Requirement: 适配器输出必须经过契约校验

系统 SHALL 在传播成功结果前使用发布版本的 `outputSchema` 校验适配器输出；不合规输出不得被伪装为成功。

#### Scenario: 适配器返回错误形状的成功结果

- **WHEN** 适配器把不满足 `outputSchema` 的载荷标为成功
- **THEN** Runtime 将结果分类为 `TERMINAL_FAILURE`，不把原始载荷作为成功数据传播

### Requirement: 重试必须受副作用和幂等语义约束

系统 SHALL 区分 `READ_ONLY`、`IDEMPOTENT_WRITE` 与 `NON_IDEMPOTENT_WRITE`，并保留 `NOT_STARTED`、`COMMITTED` 与 `UNKNOWN` 副作用状态。自动重试不得越过声明的安全边界。

#### Scenario: 非幂等写在超时后状态未知

- **WHEN** `NON_IDEMPOTENT_WRITE` 调用超时且适配器只能返回 `effectState=UNKNOWN`
- **THEN** Runtime 不自动重试，并保留相同 invocationId、独立 attemptId 和等待人工/业务对账的状态
