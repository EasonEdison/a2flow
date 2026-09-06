# Phase 1 Platform Contracts Specification

## MODIFIED Requirements

### Requirement: 可信 userId 与环境上下文

系统 SHALL 只接受服务端可信边界构造的 `userId` 和 `environment`。`environment` SHALL 仅为 PRT 或 ONLINE。模型、Tool 参数和业务 payload SHALL NOT 选择或覆盖该上下文。

#### Scenario: 模型参数伪造环境

- **触发**：模型生成的 Tool 参数携带另一个 userId、ONLINE/PRT override 或凭证字段。
- **期望结果**：Tool 执行器忽略或拒绝不可信字段，并只使用服务端 TrustedContext；不发生跨用户、跨环境或凭证泄露。

### Requirement: use_skill 只暴露逻辑选择

模型可见 `use_skill` 参数 SHALL 只含逻辑 `skillKey`。服务端 SHALL 在参数外注入可信上下文和调用作用域，并 SHALL 以 content + artifact 返回授权材料与版本证据。

#### Scenario: 模型请求原始 Skill locator

- **触发**：模型参数除 skillKey 外还提供 userId、environment、version、raw locator 或 Workflow routing。
- **期望结果**：请求 Schema 或服务端边界拒绝额外字段；resolver 只使用可信上下文，并且成功结果只返回 READ_ONLY opaque material handles。

#### Scenario: chat 与 Workflow 使用同一 Skill

- **触发**：chat 与 Workflow 在相同可信环境/userId 下分别选择同一 skillKey。
- **期望结果**：二者解析同一有效 Skill version/contentDigest；差异只在服务端 invocationScope，不改写 Skill 内容或增加 routing 字段。
### Requirement: 全资产共用环境内解析

Skill、Ability、Component/Application 和 Workflow SHALL 通过同一个 environment-aware resolver 语义读取版本。PRT SHALL 只读 PRT 当前版本；ONLINE stable/gray SHALL 只读 ONLINE 存储。

#### Scenario: ONLINE 灰度用户解析 candidate

- **触发**：可信环境为 ONLINE，userId 命中 ONLINE candidate 灰度规则。
- **期望结果**：resolver 返回 `selection=ONLINE_GRAY` 和 ONLINE candidate version；不会查询或返回 PRT 版本。

#### Scenario: PRT 请求尝试读取 ONLINE

- **触发**：PRT 请求的候选 payload 指向 ONLINE stable/candidate。
- **期望结果**：解析失败关闭；不 fallback 到 ONLINE，也不由模型更改环境。

### Requirement: serving 限制不删除历史

PRT SHALL 同时服务一个当前版本。ONLINE SHALL 在灰度中至多服务 stable 和 candidate 两版，灰度结束后服务一版。该限制 SHALL NOT 删除历史资产版本。

#### Scenario: 发布第三个 ONLINE serving 版本

- **触发**：ONLINE 已有 stable 和 candidate 时请求再加入第三个 serving version。
- **期望结果**：请求被拒绝且现有 serving 状态不变；历史版本记录不被删除。

### Requirement: 入口版本不一致阻止新工作

系统 SHALL 在执行、继续、node-bound input、interaction Action 和 A2UI retry 入口比较 recorded 与当前 effective 版本。任一不一致 SHALL 在新模型/Tool/业务调用前返回 RESET_REQUIRED。

#### Scenario: 等待交互期间资产版本变化

- **触发**：Run 等待某 Interaction，随后相关资产 effective version 变化，用户提交 Action。
- **期望结果**：Action 入口返回 mismatch 与 reset 提示；不执行 Action 业务 Tool，不迁移、不继续旧版本、不自动 restart。

### Requirement: 控制请求去重不等于业务幂等

系统 SHALL 以 controlRequestId 和 payloadDigest 去重平台控制命令。受版本门禁的命令 SHALL 携带非空 recordedAssetVersions，且同一 AssetRef SHALL NOT 出现两个版本。相同 ID/摘要 SHALL 返回原控制结果；相同 ID/不同摘要 SHALL 冲突。Workflow SHALL NOT 据此声明业务 exactly-once。

#### Scenario: 两实例竞争同一控制请求

- **触发**：两个实例同时接收相同 controlRequestId 和相同 payloadDigest。
- **期望结果**：只有一个控制事实被接受，两个调用观察同一控制结果；不会产生两个 Run/继续/Action admission。

#### Scenario: fresh restart 重复业务结果

- **触发**：用户显式 fresh restart，新的 Run 再次调用产生业务副作用的 API。
- **期望结果**：Workflow 不查询旧业务结果做跨 Run 去重；业务 API 后端按自身幂等契约处理，平台不宣称 exactly-once。

### Requirement: Run Node Interaction Result 引用分层

InteractionRef SHALL 总是绑定一个 NodeRef。Interaction、Node 和 Run Result SHALL 使用不同 scope，且一个层级的 Result SHALL NOT 自动证明上层完成。Capability Release SHALL 发布命名 `ResultInterpretationPolicy` 与默认策略引用；Action definition SHALL 显式选择 `successPolicyRef` 并独立声明 `completeInteractionOnSuccess`。

#### Scenario: Action 成功但交互未配置完成

- **触发**：Interaction Action 返回 configured business success，但发布配置未设置该结果完成交互。
- **期望结果**：记录 INTERACTION Result，交互仍可保持等待；不产生 NODE/RUN Result 完成事实。

### Requirement: 结果解释使用唯一最小策略

Runtime SHALL 在独立输出 Schema 校验之后，用唯一纯解释器执行 `SCHEMA_VALID` 或 `JSON_POINTER_EQUALS`。JSON Pointer 路径缺失 SHALL NOT 等同于路径存在且值为 JSON null，且 SHALL NOT 产生成功；JSON 原生类型之间 SHALL NOT 隐式转换。

#### Scenario: Pointer 路径缺失

- **触发**：策略为 `JSON_POINTER_EQUALS`，结果中不存在配置的 jsonPointer，而 expectedLiteral 为 null 或任意其他值。
- **期望结果**：解释结果不命中并报告 `PATH_MISSING`；不把缺失路径当作 null，不完成 Interaction。

### Requirement: 事件边界不互相冒充

系统 SHALL 分别记录 Interaction Result、Node Result、Run Result 和 VERSION_MISMATCH_BLOCKED 事实。每个事件 SHALL 携带独立 eventId 与单 Run `runSequence`，并 SHALL 只携带该 eventType 所需的最具体引用；同一事件 SHALL NOT 同时夹带其他层级引用、nodeStatus 或 versionGuardDecision 事实。sequence 的事务持久化/重放以及事件传输协议和版本在 main-brain 审查前 SHALL 保持候选。

#### Scenario: Finalizer 生成最终结果

- **触发**：所有必需节点和交互边界已满足，Finalizer 生成 Run Result。
- **期望结果**：产生独立 RUN Result 引用；Finalizer 不改写已有失败/跳过/交互业务事实，也不把外部异步提交表示成已完成。
