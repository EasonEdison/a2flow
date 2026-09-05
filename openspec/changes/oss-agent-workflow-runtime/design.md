# Agent/Workflow Runtime 设计

## 状态与约束

- 设计状态：PROPOSED
- Runtime 准出：NO READY
- 持久化：PostgreSQL-only；开发、测试和部署均不提供 SQLite/MySQL 或内存 fallback。
- 部署假设：API 与 worker 可多实例；单机部署只是拓扑选择。
- 协议状态：资产、Capability、事件、A2UI/AG-UI 的精确版本待主控统一。
- 核心边界：Runtime 不导入数字员工领域模型、业务字段、场景分支或展示文案。

## 设计原则

1. 将“单 Agent 决策循环”和“Workflow 节点调度”建模为不同 run 类型。
2. PostgreSQL 是运行真值；进程内缓存不得参与正确性判断。
3. 外部调用按至少一次尝试设计，端到端副作用通过稳定 operationKey 与 Capability 协作幂等。
4. 每次状态变更、revision 增长和事件追加在同一数据库事务完成。
5. 未知资产 revision、协议版本、schema 或授权一律 fail closed，不增加兼容 fallback。
6. Runtime 只承载通用 presentation/action 契约；产品前端负责渲染，产品后端负责业务适配。

## 逻辑架构

    Product Adapter
         |
         v
    Runtime Command Port ---- Run Query / Event Subscription Port
         |
         v
    Run Coordinator
      |              |
      v              v
    Agent Executor   Workflow Scheduler
      |              |
      +-------> CapabilityExecutionPort
      +-------> PresentationActionPort
         |
         v
    PostgreSQL: runs, attempts, checkpoints, actions,
                idempotency records, leases, ordered events

LangGraph 是 Agent/Workflow 编排实现候选，不是公共协议，也不拥有 Runtime 的跨实例租约、授权或产品展示边界。

## 组件职责

| 组件 | 负责 | 不负责 |
| --- | --- | --- |
| Runtime Command Port | start、resume action、cancel 的校验与命令幂等 | 业务参数拼装、UI 渲染 |
| Run Coordinator | run 身份、revision、状态机、父子关系和事务边界 | Workflow 图编辑、模型供应商细节 |
| Agent Executor | 单 Agent 的模型/工具循环、Agent checkpoint 与 terminal result | Workflow 节点依赖调度 |
| Workflow Scheduler | 已发布图的依赖推进、节点 attempt、重试、等待与恢复 | Agent 内部推理策略、业务分支 |
| CapabilityExecutionPort | 使用版本化 capabilityRef、typed input、operationKey 发起调用 | 注册 capability、实现具体业务系统 |
| PresentationActionPort | 产生通用 presentation/action request，接收关联 action decision | 选择业务文案、渲染组件 |
| Lease Manager | 领取、续租、过期恢复、fencing token | 通过单实例互斥假设保证正确性 |
| Event Store / Subscription | 事务内追加有序事件，从 afterSequence 回放和续传 | 对外传输协议版本与浏览器渲染 |
| Definition Resolver | 解析不可变已发布资产并校验 revision/schema/checksum | 发布、替换或修复资产 |

## 两类运行

### AgentRun

AgentRun 表示一个独立 Agent 的执行。它拥有输入、Agent 状态、模型/工具 attempt、checkpoint 和结果。即便内部使用 LangGraph 节点，也不得把它伪装成 Workflow 图节点调度器。

### WorkflowRun

WorkflowRun 表示已发布图的持久化调度。它拥有图 revision、节点依赖、节点 attempt 和父子关系。需要 Agent 能力的节点创建或关联一个 AgentRun 子运行；父 Workflow 只消费子运行的公开结果与状态，不读取其内部消息或推理过程。

这一区分允许分别测试 Agent 循环与 Workflow 调度，同时保持一个统一的 RunQuery/Event 输出面。

## 状态机

候选非终态包括 ACCEPTED、RUNNING、WAITING_ACTION、RETRY_SCHEDULED 和 CANCEL_REQUESTED。候选终态包括 SUCCEEDED、FAILED 和 CANCELLED。精确枚举名由公共契约统一，但必须满足：

- 状态迁移基于 expectedRevision 做比较并交换。
- 终态不可逆；重复同义命令返回已有结果，矛盾命令返回冲突。
- WAITING_ACTION 与 RETRY_SCHEDULED 不持有长租约。
- CANCEL_REQUESTED 禁止调度新的外部副作用，但不能假装撤回已经发生的调用。
- Workflow 已先提交终态时，后到取消返回 ALREADY_TERMINAL。
- 取消先提交时，晚到 attempt 不能推进主状态；其结果仅以审计事件记录，并明确提示外部副作用可能已经发生。

## PostgreSQL 逻辑记录

本轮不冻结表名或 DDL，只定义必须存在的逻辑记录：

| 记录 | 关键语义 |
| --- | --- |
| Run | runType、resolved asset revision、state、revision、parentRunId、cancelRequestedAt |
| Attempt | logicalStepId、attemptNo、errorClass、started/finished、lease fencing token |
| Checkpoint | run/thread identity、checkpoint namespace/id、序列化状态与兼容版本 |
| Lease | ownerId、expiresAt、fencingToken；时间以数据库为准 |
| ActionRequest | actionRequestId、runId、expectedRunRevision、schema、status、decision |
| IdempotencyRecord | scope、key、request fingerprint、status、稳定结果或冲突 |
| RunEvent | runId、单调 sequence、eventType、contractVersion、payload、occurredAt |

LangGraph PostgresSaver 可承载框架 checkpoint，但业务 run、lease、event、action 和外部副作用幂等仍由 Runtime 数据模型拥有。不得把 InMemorySaver 用作任何环境的持久化 fallback。

## 多实例领取与恢复

1. Worker 在短事务中从“可运行且无有效租约”的队列记录领取任务。可使用 PostgreSQL 行锁与 SKIP LOCKED 降低多个消费者的争抢，但它只用于队列领取，不作为一般查询一致性保证。
2. 领取时写入 ownerId、expiresAt，并递增 fencingToken；提交后才执行节点。
3. Worker 周期性续租，续租和每次结果写入都必须匹配 ownerId、fencingToken 与 expectedRevision。
4. 租约到期后其他实例可以领取并获得更大的 fencingToken。旧 worker 的任何晚写都会被拒绝。
5. 崩溃恢复从最新持久化 checkpoint 与 Run/Attempt 真值重建，不依赖旧进程内存。
6. 领取恢复次数与业务 retry attempt 分开计数，避免把基础设施接管误报为业务重试。

租约时长、续租周期和扫描批次是配置项，必须有下限、上限和指标；本提案不冻结具体数值。

## 幂等与外部副作用

命令幂等与 capability 副作用幂等分开处理：

- StartRun 使用调用方提供的 idempotencyKey 与规范化 request fingerprint。相同 key/相同请求返回同一 run；相同 key/不同请求返回冲突。
- 每个外部副作用生成稳定 operationKey，至少包含 runId、logicalStepId 与 effect identity。基础设施恢复和业务重试均复用同一个 operationKey。
- Runtime 先持久化调用意图，再在数据库事务外调用 CapabilityExecutionPort，最后用 fencing token 和 expectedRevision 提交结果。
- 若进程在外部调用成功后、结果落库前崩溃，恢复会用相同 operationKey 重试。Capability 必须声明并实现去重或结果查询；否则该 capability 不得被标记为可自动重试。
- “exactly once”不作为跨系统承诺；可验证承诺是 Runtime 状态 exactly-once transition、调用至少一次、协作式副作用幂等。

## 重试与失败分类

| 类别 | 行为 |
| --- | --- |
| TRANSIENT | 在版本化策略预算内退避重试，复用 operationKey |
| PERMANENT_VALIDATION | 立即失败，不重试 |
| AUTHORIZATION | fail closed，不通过其他身份或旧协议 fallback |
| USER_REJECTED | 作为明确 action 结果推进到定义的分支，不当作技术失败重试 |
| CANCELLED | 停止新工作，进入取消收敛 |
| UNKNOWN | 默认不可自动重试，等待策略明确或人工处理 |

重试策略属于发布定义或受治理的 Runtime policy。Runtime 不得自行把失败转成另一模型、另一 capability 或旧版本资产。

## HITL 与通用 action

- 节点请求人工动作时，在同一事务中创建 ActionRequest、将 run 置为 WAITING_ACTION、递增 revision 并追加事件，然后释放租约。
- ActionRequest 只包含通用类型、schema、presentation artifact reference、data 和允许的 decision；业务文案来自已发布 presentation artifact 或产品适配层。
- 提交动作必须携带 actionRequestId、expectedRunRevision、actor authorization context 和 decision。
- 首次合法 decision 原子生效；完全相同的重复提交返回原结果；不同 decision 或过期 revision 返回冲突。
- 恢复时重新进入节点意味着 interrupt 前代码可能重放，因此所有 interrupt 前副作用必须被隔离或幂等。LangGraph 两种语言的官方文档都明确提示该边界。

## 取消并发边界

取消是持久化协作信号，不是进程 kill：

1. CancelRun 以 expectedRevision 提交 CANCEL_REQUESTED，并追加事件。
2. Scheduler 在开始模型调用、capability 调用、action 创建和节点提交前检查取消状态。
3. 可取消的下游调用接收 cancellation signal；不可取消调用允许完成，但其晚结果受 fencing/revision 拒绝，不能重新推进 run。
4. 已完成的外部副作用不做隐式补偿。是否存在补偿是发布 Workflow 的显式节点设计。
5. 终态竞争按数据库中先成功的 compare-and-swap 决定，并产生可审计结果。

## 事件与续传

- RunEvent 是执行可观察性的权威日志；每个 run 的 sequence 严格单调且不可复用。
- 状态变更与对应事件在同一事务中提交，避免 snapshot 已变但事件缺失。
- SubscribeRunEvents(afterSequence) 先回放 sequence 大于游标的已提交事件，再进入 live tail。
- 传输允许至少一次投递；消费者以 runId + sequence 去重，并在发现 gap 时重新回放。
- 事件 payload 不含 raw chain-of-thought、密钥或未经治理的完整模型上下文。可公开的是步骤状态、工具/模型调用元数据、经策略裁剪的输入输出摘要和错误分类。
- SSE、WebSocket、AG-UI event 或其他 transport adapter 在主控裁决后映射此内部语义，不能反向污染核心状态机。

## Presentation/Action 端口

PresentationActionPort 只接受版本化、可校验的通用输入：

- presentationArtifactRef 与 revision
- data 与 dataSchemaVersion
- action schema/allowed decisions
- runId、logicalStepId、actionRequestId
- authorization/correlation context

输出是通用 presentation event 或 action decision。Runtime 不选择具体组件实现、不执行 DOM/React 渲染、不拼业务文案；数字员工前端负责 renderer，数字员工后端负责业务数据适配。未知组件、schema 或 action version 必须拒绝。

## 输入输出契约

| 操作 | 关键输入 | 成功输出 data | 失败边界 |
| --- | --- | --- | --- |
| StartRun | runType、assetRef/revision、input、idempotencyKey、authContext | runId、state、revision、resolvedAsset | 未发布/未知版本/schema/授权失败即拒绝 |
| SubmitAction | actionRequestId、expectedRunRevision、decision、authContext | runId、state、revision、acceptedDecision | 重复同义返回原结果；冲突或过期拒绝 |
| CancelRun | runId、expectedRevision、reasonCode、authContext | runId、state、revision、cancelAccepted | 已终态返回稳定结果，不撤回外部副作用 |
| GetRun | runId、authContext | snapshot、currentSequence | 不泄露内部 checkpoint 或推理链 |
| SubscribeRunEvents | runId、afterSequence、authContext | ordered events、nextSequence | gap 可回放；未知版本 fail closed |
| InvokeCapability | capabilityRef/revision、typedInput、operationKey、executionContext | typedOutput、effectReceipt | 无幂等保证时禁止自动重试 |

以上是消费者需求，不是已批准的共享接口；字段名和 envelope 由 main-brain 与域所有者统一。

## 可观察性

每个命令、领取、续租、attempt、checkpoint、action、retry、cancel、fencing rejection 与 terminal transition 都应带 runId、logicalStepId、attemptNo、revision、fencingToken 和 correlationId。日志和 trace 仅记录经策略允许的元数据；指标至少覆盖运行延迟、等待时间、租约接管、重试、幂等命中、事件 lag 与 stale write rejection。

## 语言裁决建议

建议 CTO 先批准 TypeScript + LangGraphJS 的限时 parity spike，验证：

- PostgresSaver 初始化与真实重启恢复；
- interrupt/resume 的重复执行边界；
- event streaming 与自定义运行事件适配；
- 两 worker 竞争、租约过期和 stale writer fencing；
- capability operationKey 在“调用成功、落库前崩溃”后的去重。

若全部通过，锁定 TypeScript MVP。若缺口来自可控的 Runtime 外层能力，则仍可选择 TypeScript；只有出现关键框架/生态能力不可接受且 Python 验证通过，才改选 Python。禁止为了“兼容两边”保留双 runtime。

## 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 把 LangGraph checkpoint 误当成完整分布式调度 | 独立建模 lease、fencing、event、idempotency 与 action |
| 外部副作用无法 exactly once | 明确至少一次 + 稳定 operationKey；不支持幂等的 capability 禁止自动重试 |
| 事件协议过早冻结 | 先稳定内部语义，transport/version 等主控裁决 |
| 业务语义渗入核心 | 核心测试使用中性 fixture；依赖规则禁止 Runtime 引用数字员工模块 |
| checkpoint 无界增长 | 实现前定义 retention、归档与删除安全门禁，并做容量测试 |
| 取消造成错误“已撤回”承诺 | 暴露 late completion/audit，补偿必须由 Workflow 显式定义 |

## 公开依据

- LangGraphJS v1 将 durable execution、checkpointing、persistence、streaming 与 HITL 列为一等能力：[官方发布说明](https://docs.langchain.com/oss/javascript/releases/langgraph-v1)
- JavaScript persistence 文档说明 checkpoint 用于中断恢复、故障恢复与 thread 状态，并列出 PostgresSaver：[官方文档](https://docs.langchain.com/oss/javascript/langgraph/persistence)
- Python persistence 文档提供 PostgresSaver/AsyncPostgresSaver 与 pending writes 语义：[官方文档](https://docs.langchain.com/oss/python/langgraph/persistence)
- 两种语言的 interrupt 都会在恢复时重新执行所在节点，因此副作用必须隔离或幂等：[JavaScript](https://docs.langchain.com/oss/javascript/langgraph/interrupts)、[Python](https://docs.langchain.com/oss/python/langgraph/interrupts)
- JavaScript streaming 支持 state、message、custom、tool 等事件模式：[官方文档](https://docs.langchain.com/oss/javascript/langgraph/streaming)
- PostgreSQL 官方说明 SKIP LOCKED 适合 queue-like 多消费者场景，但不提供一般一致视图：[SELECT locking clause](https://www.postgresql.org/docs/current/sql-select.html)
- PostgreSQL unique constraints 可作为幂等键冲突的数据库最终门禁：[Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)
