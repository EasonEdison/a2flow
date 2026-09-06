# Agent/Workflow Runtime Phase 1 Capability Specification

## 状态

- Baseline：SW-P1-20260907.2
- Specification：BASELINE_ALIGNED
- Runtime：NO READY

## ADDED Requirements

### Requirement: Runtime 使用 Python Deep Agents 与 LangGraph

Runtime SHALL 使用 Python Deep Agents SDK 的公开 Tools、Middleware、Backend、Store 和 Checkpointer 扩展点，并以 LangGraph 作为 Workflow/checkpoint/interrupt 基础。Runtime SHALL NOT fork 框架或静默实现第二 Workflow scheduler。

#### Scenario: SDK 无法满足关键并行行为

- 触发：隔离 reproducer 证明 LangGraph 原生执行无法在 A 等待时推进 B1→B2。
- 期望：保存版本、代码、命令和输出并报告 main-brain；不得以未评审的自研 scheduler 伪装通过。

### Requirement: 模型只看到 Runtime-owned Tool

Runtime SHALL 通过 Deep Agents 公开 Harness Profile 排除默认文件、shell 与 subagent Tool，并对 provider Tool schema 使用 strict binding。系统提示 SHALL NOT 被当作授权边界。

#### Scenario: SDK 默认绑定隐式 Tool

- 触发：使用显式模型构建最小 Deep Agent 并记录实际 bound Tool names。
- 期望：bound set 只包含本次 Runtime 明确提供的 Tool；`ls/read/write/edit/delete/glob/grep/execute/task` 均不出现。

### Requirement: 所有 Skill 使用统一进入 use_skill

同一个 Skill SHALL 在 chat 与 Workflow 中作为 Agent 指令/资源执行，并 SHALL 先经过 use_skill Tool；Workflow SHALL NOT 直接读取 Skill body/resource 或要求专用路由字段。

#### Scenario: 同一合成 Skill 从两个入口执行

- 触发：scripted model 分别在 chat 和 Workflow Skill node 使用 `demo/evidence-first-brief` Skill。
- 期望：两个 Tool trace 都先记录 use_skill；Skill package bytes/digest 完全相同，且没有 Workflow 专用 output 字段或固定子图。

### Requirement: trusted identity 和环境不可由模型选择

Runtime SHALL 使用 `SW-P1-SUBSET-01` 的 TrustedInvocationContext 从可信后端注入 contract revision、userId、PRT/ONLINE、conversation/run/node scope 与 controlRequestId；`use_skill` model schema SHALL 严格只接受 `{skillKey}`。PRT SHALL 只读 PRT 当前版本；ONLINE SHALL 只读 ONLINE stable 或 ONLINE gray candidate。

#### Scenario: 模型尝试覆盖环境

- 触发：scripted Tool call 在公开 args 中加入其他 userId、PRT/ONLINE 或 credential。
- 期望：schema/授权拒绝该调用且 resolver 未执行；ONLINE 不访问 PRT。

### Requirement: server artifact 不进入模型 provider wire

Runtime SHALL 先严格验证完整 use_skill result，再把 content 作为 Tool result 发送给模型；artifact/version/evidence SHALL 保留在服务端状态，不得序列化进 provider message。

#### Scenario: Anthropic 第二轮请求序列化 Tool result

- 触发：离线 provider transport 返回 use_skill Tool call，Runtime resolver 返回 content + artifact。
- 期望：第二轮 wire 只含 content；请求 JSON 不含 `artifact` 或 `evidenceRef`。

### Requirement: 版本失配阻断并提示 reset

Runtime SHALL 在 start、continue、新模型/Tool round 和 Action ingress 比较记录版本与当前有效版本；不匹配 SHALL 阻断新工作并返回 RESET_REQUIRED。

#### Scenario: 等待卡片期间 Application 版本变化

- 触发：run 记录 applicationVersion=v1，Action ingress 的 effective version 为 v2。
- 期望：Action 不调用业务后端，run 不续跑、不静默迁移、不自动 restart，并返回显式 reset 提示。

### Requirement: A2UI 模式决定等待

render_application SHALL 根据发布配置区分 DISPLAY_ONLY 与 INTERACTIVE。render 成功本身 SHALL NOT 自动建立等待或完成 Skill。

#### Scenario: Display-only 与 interactive 相邻出现

- 触发：同一 Skill 先 render DISPLAY_ONLY，再 render INTERACTIVE。
- 期望：第一个结果返回后继续；第二个产生 owning node 的 InteractionRef/interrupt，直到合法 resume 才继续。

### Requirement: Action success、interaction completion 与 Finalizer 分离

Runtime SHALL 按 Application 配置判断 Action 业务 success，并独立判断该 success 是否完成 interaction。Finalizer SHALL NOT 覆盖业务事实或绕过未完成交互。

#### Scenario: Action 成功但配置不完成交互

- 触发：INTERACTIVE Action 返回满足 success 条件，但 completeInteractionOnSuccess=false。
- 期望：记录 businessSuccess=true、interactionCompleted=false，node 继续等待，Finalizer 不运行。

### Requirement: 并行分支保持独立推进

当 A 处于等待，独立分支 B1 完成后 B2 SHALL 能继续；JOIN SHALL 等待 A。Runtime SHALL NOT 把 thread_id 当作分支 selector、OS thread 或分布式锁。

#### Scenario: A 等待期间执行 B1 和 B2

- 触发：LangGraph 从 START 并行进入 A(INTERACTIVE) 与 B1(DISPLAY_ONLY)，B1 后接 B2。
- 期望：A 未 resume 时 B1、B2 完成，JOIN 未完成；只有 A 的 nodeId/interactionId/version 可恢复 A。

### Requirement: retry 仅限 A2UI owning node

Runtime SHALL 只对 render failure、Action technical failure 或 Action result 未满足配置 success 条件重试 owning A2UI node。Skill 模型、脚本、非 A2UI Tool 和 ability business failure SHALL NOT 获得通用 retry/recovery。

#### Scenario: Ability 与 render 同时失败

- 触发：一个 Skill execution 出现 ability business failure，另一个 A2UI node 出现 render technical failure。
- 期望：ability failure 保持失败且不 retry；仅 A2UI owning node 按配置 retry，已完成 predecessor 和其他 branch 不重放。

### Requirement: stop 与 restart 不承担业务幂等

Stop SHALL 阻止所有新 node、模型/Tool round、Action、retry 和 Finalizer，且不可 resume。Restart SHALL 创建全新 run，不继承或检查旧业务结果。业务幂等/retry SHALL 由被调用 API 后端负责。

#### Scenario: Stop 后收到 late result 并 restart

- 触发：run 停止后收到已分发 ability 的 late result，随后用户显式 restart。
- 期望：late result 仅保留事实且不推进；旧 card 操作被拒；新 runId 从入口开始，无旧 checkpoint/result/interaction，Runtime 不做跨 run dedup。
