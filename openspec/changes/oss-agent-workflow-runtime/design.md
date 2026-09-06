# Agent/Workflow Runtime Phase 1 设计

## 状态

- Authority：SW-P1-20260907.2
- 状态：BASELINE_ALIGNED / EXPERIMENTAL
- Runtime：NO READY
- 实现语言：Python
- Agent harness：Deep Agents SDK
- Workflow/checkpoint/interrupt：LangGraph
- 持久化：PostgreSQL-only

本设计描述可行性映射和消费者边界。共享 schema、包布局、服务 API 与生产拓扑由 main-brain 审查后才能冻结。

## 最小架构映射

    Chat command -----------+
                            |
    Workflow Skill node ----+--> Deep Agent
                                  |
                                  +--> use_skill
                                  |      |
                                  |      +--> authorized Skill instructions/resources
                                  |
                                  +--> execute_ability
                                  |
                                  +--> render_application
                                           |
                                           +--> DISPLAY_ONLY: return and continue
                                           |
                                           +--> INTERACTIVE: node-bound interrupt
                                                                 |
                                                                 +--> validated Action resume
                                                                        |
                                                                        +--> configured completion
                                                                                |
                                                                                +--> Finalizer

外层 Workflow 是 LangGraph StateGraph。Skill 节点调用同一个 Deep Agent executor，但必须由模型先调用 use_skill 取得授权后的指令/资源。Skill 本身不被编译为业务子图。

## Deep Agents 使用范围

### 采用的公开扩展点

- create_deep_agent：组装显式 model、Tools、middleware、backend、checkpointer、store 和 context_schema。
- Tools：只暴露 Runtime-owned use_skill、execute_ability、render_application 和获批只读检索。
- Harness Profile：显式排除默认 `ls/read_file/write_file/edit_file/delete/glob/grep/execute/task`；关闭 general-purpose subagent。
- Provider adapter：Anthropic Tool bind 强制 `strict=True`，并通过 MockTransport 验证实际 wire schema/content。
- Middleware：注入 trusted context、做版本准入、限制 Tool、记录事件；不创建另一套 scheduler。
- Backend：Phase 1 使用无 host shell 权限的 StateBackend/受控自定义 backend 语义；生产持久化仍由 PostgreSQL Store/Checkpointer 方案评审。
- Checkpointer：实验目标为 AsyncPostgresSaver；当前只 import，未运行 PG。
- Store：仅在 Skill resource 或长文本需要 SDK StoreBackend 时评估；不得自动演化成知识库平台。

### 明确不采用

- model=None 的默认模型，因为它隐含 provider/key，且官方已标为 deprecated。
- LocalShellBackend、默认文件系统 Tool、真实文件系统写权限、subagent/task swarm 和任意脚本执行。
- native Skill-directory activation 作为 use_skill 的替代入口。
- InMemorySaver/SQLite 作为 PostgreSQL 不可用时的 fallback。
- 默认或全局 Tool retry。任何 retry middleware 必须显式限定为 A2UI render/Action。

## TrustedContext 与 Tool schema

`SW-P1-SUBSET-01` 批准的 `TrustedInvocationContext` 由服务入口验证后注入 LangGraph runtime context：

- `contractRevision=SW-CONTRACTS-P1-CANDIDATE.1`；
- `trustedContext={userId, environment}`，environment 仅 PRT/ONLINE；
- conversation scope 为 `{kind:CONVERSATION, conversationId}`；
- Workflow scope 为 `{kind:WORKFLOW, runId, nodeId, conversationId?}`；
- `controlRequestId`。

这些字段不进入模型可填写的 Tool arguments。模型只能提交严格 `{skillKey}`；userId、environment、versionId 或其他 extra 字段在 ToolNode 调 resolver 前被拒绝。

获批 use_skill result 为 `{contractRevision, content, artifact}`：content 只含 instructions、read-only opaque resource handles 与描述性 requiredToolNames；artifact 保存 skillKey、不可变版本、digest、environment/selection 与 evidenceRef。Runtime 直接使用主干共享 `skillweave_contracts.UseSkillResult.from_mapping()` 验证完整 resolver result，再以 `content_and_artifact` 分离返回。

Tool arguments 只保留最薄 Pydantic 适配：本地校验委托共享 `UseSkillRequest`，provider JSON Schema 使用批准的 ECMA-262 pattern，避免把 Pydantic 私有正则语义带到 wire。共享适配拒绝 extra、隐式类型 coercion 与 CR/LF key；Runtime 不再维护重复 DTO。execute_ability 与 render_application 采用相同 trusted context 注入原则，但其 full wire 未由该子集批准。

## PRT / ONLINE 与版本准入

- PRT resolver 只从 PRT 库读取当前版本。
- ONLINE resolver 只从 ONLINE 库读取 stable 或 userId 命中的 gray candidate。
- ONLINE 绝不读取 PRT；userId 是唯一 gray targeting 术语。
- start、每次新模型/Tool round、continue 和 Action ingress 都执行轻量 effective-version 比较。
- 任一参与资产版本不匹配时，阻断新的工作并生成 RESET_REQUIRED；不得继续旧版本、静默迁移或自动 restart。
- SDK checkpoint 兼容版本与业务配置版本是两类门禁，分别记录。

## Workflow 与 Skill 边界

Workflow graph 只包含 sequence、condition、parallel、AI decision、user choice、Skill node、A2UI presentation 和 Finalizer 等平台节点语义。Skill node 不展开 Skill 文档步骤。

同一合成 Skill 在两种入口下保持一致：

- Chat：Deep Agent 被要求使用某 Skill，模型调用 use_skill 后执行。
- Workflow：Workflow Skill node 为 Deep Agent 提供 node-bound 任务上下文，模型仍调用同一个 use_skill Tool。

不得为 Workflow 添加 Skill 专用 output 路由字段。路由只消费 Skill 的普通 final result/status，由 Workflow 节点配置解释。

## A2UI 映射

render_application 通过可信 resolver 获取 Application 配置，返回结构化 presentation result。

### DISPLAY_ONLY

- render 成功后立即将结果返回 Agent/Workflow。
- 不创建 interrupt，不阻塞同分支下一步。
- render 失败可以按 owning node 的 A2UI retry policy 重试。

### INTERACTIVE

- render 成功后创建 InteractionRef，并在 owning Workflow node 上触发 LangGraph interrupt。
- interrupt payload 至少携带 runId、nodeId、interactionId、applicationRef/version 与允许的 action 描述。
- resume 必须使用 Command(resume=...) 且通过 nodeId、interactionId、effectiveVersion 和授权校验。
- 普通 chat、其他 card、仅相同 thread_id 或仅 runId 均不能选择等待节点。
- Action 调用结果先按配置判断业务 success，再按配置判断是否完成 interaction。
- render 成功、Action 请求已发出或 Action 业务成功都不自动等于 Skill success。

官方 LangGraph 文档说明 interrupt 恢复会从节点开头重新执行，因此 render/Action 前后的控制记录必须可去重；这只处理平台控制重复，不接管业务 API 幂等。

## Finalizer 边界

Finalizer 可读取 predecessor final results/status 和已完成 InteractionRef，生成总结与完成判断。它不得：

- 把真实失败改成成功；
- 把“请求已提交”写成“异步业务已完成”；
- 绕过未完成 INTERACTIVE；
- 在 stop 后继续；
- 重新调用业务 Tool 来补事实。

## 并行与节点绑定验证

第一实验图：

    START
      |\
      | +--> A(INTERACTIVE wait) -----+
      |                                |
      +--> B1(DISPLAY_ONLY) --> B2 -----+--> JOIN --> FINALIZER

必须观测：

1. A 进入 interrupt。
2. B1 完成。
3. A 未 resume 时 B2 仍能完成。
4. JOIN 保持等待 A。
5. 只用 A 的 interactionId 可 resume A；B 或普通 chat 不能代替。
6. A 完成后 JOIN 与 Finalizer 才运行。

thread_id 只是 checkpoint cursor。单次 invoke、superstep、parallel task 与独立 branch progression 的实际关系必须由 SDK 运行记录证明。若 LangGraph 原生执行停在 A 所在 superstep，导致 B2 无法推进，则提交最小 reproducer 给 main-brain；不得通过私建 scheduler 掩盖。

## Retry 边界

- 可 retry：render_application 技术失败；Action 调用技术失败；Action 结果未满足该 Application 配置的 success 条件。
- retry 作用域：仅 owning A2UI node，保留 predecessor 与其他 branch 已完成事实。
- 不可通用 retry：Skill 模型调用、Skill instruction 执行、非 A2UI Tool、execute_ability 业务失败。
- Deep Agents 默认 middleware 与 LangChain Agent/ToolNode 的异常行为需按实际安装版本审计。
- 若引入 ToolRetryMiddleware，只允许匹配 render_application 或 Action adapter；禁止 fallback 模型、其他 Tool 或全局 retry。

## Stop 与 fresh restart

Stop admission guard 在新 node、模型 round、Tool、Action、retry 和 Finalizer 前检查：

- stop 后不再发起新工作；
- 已分发调用的晚结果保留为事实，但不能推进；
- stopped interaction/card 只读，后端拒绝操作；
- stop 不可 resume。

Restart 创建新 runId、thread/checkpoint namespace 和 InteractionRef 集合，从入口重新执行。它不继承旧消息、结果、状态、Action 或 completion，不查询旧业务结果来阻止新 run。调用 API 后端自行负责业务请求幂等/retry；Workflow 不补偿、不 reconciliation、不跨 run dedup。

## PostgreSQL 与双进程门禁

Phase 1 不自建独立 lease scheduler。先验证 LangGraph + AsyncPostgresSaver 在两个 stateless Python 进程上的原生约束：

- 同一个 run/node 的并发 invoke 如何冲突或串行；
- interrupt/checkpoint 如何被另一进程查询和 resume；
- pending writes 与 node replay 的实际边界；
- process kill 后可恢复边界；
- parallel branch checkpoint/state 是否支持目标进度。

任何额外 admission/ownership 机制必须以真实 SDK 缺口、最小 reproducer 和 contracts 评审为前提；不能从旧 design 直接继承 fencing/lease 方案。

## Scripted model

实验使用显式 scripted chat model：

- 按脚本顺序产生 use_skill Tool call 和 final response；
- 不联网，不使用模型 key；
- 记录实际 model input 与绑定 Tool objects；
- ToolNode 测试确认 userId/environment/versionId extra 不可由模型传入；
- 读取项目自有 `evidence-first-brief` Skill bytes/digest，不使用真实业务字段。

scripted model 被刻意编排为调用 use_skill，只证明 SDK/契约映射，不证明真实模型会稳定遵循 Skill。system prompt 不是授权；mandatory use_skill 仍需 Runtime admission guard。另有独立 Anthropic MockTransport 测试通过真实 provider serializer，证明 wire strict schema 与 artifact/evidenceRef 不出站，但仍不证明 live-model 行为。

## 当前可执行性

Python 3.11.13、task-owned venv、Deep Agents 0.7.13、LangGraph 1.2.11 与 checkpoint-postgres 3.1.2 已安装并通过 import/pip check。首批 15 个测试覆盖 named contracts subset、ToolRuntime 注入、provider wire、默认 Tool 收口和 A2UI mode/interrupt；这只是 source feasibility。

当前只等待 main-brain 协调临时 PostgreSQL 与两个 stateless process 的验证窗口。PG 获批前不得以 InMemory/SQLite 替代 resume 证据，也不得启动公开端口或触碰现有 MySQL。独立并行 progression、scoped retry、stop/restart 必须继续按 TDD 在实验目录完成；若 SDK 原生不支持，提交最小 reproducer 而不自建第二 scheduler。

## 公开依据

- Deep Agents create_deep_agent 可注入 Tools、Middleware、Backend、Checkpointer、Store：
  https://docs.langchain.com/oss/python/deepagents/customization
- Backend 为可插拔 filesystem surface；LocalShellBackend 不适合 Web/API：
  https://docs.langchain.com/oss/python/deepagents/backends
- Deep Agents 0.7.13 要求 Python >=3.11、MIT：
  https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/pyproject.toml
  https://github.com/langchain-ai/deepagents/blob/main/LICENSE
- LangGraph interrupt 使用 Command(resume=...)，并会从节点开头重放：
  https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph 提供 PostgresSaver/AsyncPostgresSaver：
  https://docs.langchain.com/oss/python/langgraph/persistence
