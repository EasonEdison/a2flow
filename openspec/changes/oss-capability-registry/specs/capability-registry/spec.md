# Capability Registry Phase 1 Specification

## MODIFIED Requirements

### Requirement: execute_ability 必须隔离模型参数与可信上下文

系统 SHALL 只向模型暴露 `abilityKey` 和 `arguments`。userId、环境、权限、凭证、生效版本和运行标识必须由后端 ToolRuntime 注入或解析，不得由模型提供。

#### Scenario: 模型伪造环境与身份

- **WHEN** 模型在 arguments 中提交 userId、environment、credentialRef 或 releaseVersion
- **THEN** Tool 在 adapter 调用前拒绝请求，返回稳定错误且 `adapterCalled=false`

### Requirement: 能力解析必须遵守 PRT/ONLINE 分库

系统 SHALL 通过共享 resolver 解析能力。PRT 只读取 PRT current；ONLINE 只读取 ONLINE stable/gray 并以受信 userId 灰度，绝不读取 PRT。

#### Scenario: ONLINE 灰度用户解析能力

- **WHEN** 受信环境为 ONLINE 且 userId 命中 candidate 灰度
- **THEN** resolver 返回 ONLINE candidate release，PRT 数据源读取次数为 0

### Requirement: 版本失配必须在业务调用前阻断

系统 SHALL 在 execute_ability、continue/recovery 和 A2UI Action 业务入口比较 observed 与 effective 配置版本。失配时必须提示全新 reset，不得继续旧版本、静默迁移或自动重放。

#### Scenario: 执行前检测到能力版本变化

- **WHEN** run 记录的 ability version 与当前 resolver 返回版本不同
- **THEN** 返回 `CONFIG_VERSION_MISMATCH`、`resetRequired=true` 和 `adapterCalled=false`

### Requirement: 授权和参数校验必须先于 adapter

系统 SHALL 在调用 adapter 前完成 ability/operation/credential slot 授权、modelArgumentSchema 校验、来源绑定和 resolvedInputSchema 校验。模型描述不得扩大 allowlist。

#### Scenario: 用户没有 credential slot 权限

- **WHEN** 主体可发现 ability 但无权使用其 credential slot
- **THEN** 返回 `AUTHORIZATION_DENIED`，adapter 不被调用，错误不泄露凭证或其他用户信息

### Requirement: 发布契约必须分离 schema、绑定和成功策略

系统 SHALL 发布 model argument、resolved input、output schema、来源绑定、credential requirement、adapter operation、`resultInterpretationPolicies` array 和模型不可选择的 `defaultSuccessPolicyRef`；每个 policy 必须有唯一 `policyRef`，default ref 必须可解析。实际 release/version 包络由共享 contracts 拥有。

#### Scenario: success policy 与输出 schema 不兼容

- **WHEN** `JSON_POINTER_EQUALS` 的 `jsonPointer` 指向 output schema 不支持的路径，或 JSON primitive `expectedLiteral` 类型不兼容
- **THEN** 发布静态验证失败并返回稳定 ruleCode/path，不产生发布版本

### Requirement: 成功解释器必须只有一个实现

系统 SHALL 使用共享 `ResultInterpretationPolicy` schema，并由 Runtime 在 output schema 校验后执行唯一解释器。首版只允许 `SCHEMA_VALID` 和 `JSON_POINTER_EQUALS`；禁止 ANY/ALL、NOT_EQUALS 或其他表达式 AST。Capability Registry 发布命名策略；A2UI 对精确 ability release 选择 `successPolicyRef` 并拥有 `completeInteractionOnSuccess`，不得实现第二套解释器。

#### Scenario: 业务成功条件未命中

- **WHEN** adapter 返回通过 output schema 的结果，但配置的 successPolicyRef 判定 matched=false
- **THEN** execute_ability 返回 `BUSINESS_NOT_SUCCESSFUL`，A2UI/Finalizer 不得把当前事实改写为成功

### Requirement: JSON Pointer 判定必须失败关闭且类型严格

系统 SHALL 区分 `MISSING` 与 `FOUND(null)`。`MISSING` 必须返回 `matched=false` 和 `PATH_MISSING`；`FOUND(null)` 可按 JSON null 参与比较。字符串、数字、布尔值和 null 必须同类型同值才相等，禁止隐式类型转换。

#### Scenario: 路径缺失不能被当成 null 或不等式成功

- **WHEN** `jsonPointer` 无法解析到值
- **THEN** 解释器返回 `matched=false`、`reasonCode=PATH_MISSING`，且不得把缺失值视为 JSON null 或成功条件

### Requirement: 一次 Tool 调用不得自动重试业务调用

系统 SHALL 对一个已授权 execute_ability Tool call 最多调用 adapter 一次。Runtime/Workflow 不拥有业务重试、业务幂等、对账、补偿或跨 run 去重。

#### Scenario: adapter 调用超时

- **WHEN** adapter 在调用后超时且业务结果未知
- **THEN** 返回 `ADAPTER_TIMEOUT`、`adapterCalled=true`，Runtime 自动重试次数为 0

### Requirement: 全新 restart 不得复用旧调用状态

系统 SHALL 将 Workflow restart 视为从入口创建的新 run，不继承旧上下文、checkpoint、结果、interaction、invocation 或完成标识，也不查询旧业务结果来决定是否开始。

#### Scenario: 用户对失败 run 发起 restart

- **WHEN** 用户显式 restart 一个包含旧 execute_ability 失败的 run
- **THEN** 新 run 使用新 invocation 上下文从入口开始，Capability Registry/Runtime 不执行旧业务结果对账
