# Agent/Workflow Runtime Capability Specification

## 状态

- 规范状态：PROPOSED
- Runtime 准出：NO READY
- 适用域：业务无关 Agent/Workflow Runtime

## ADDED Requirements

### Requirement: 区分 Agent 与 Workflow 运行语义

Runtime SHALL 将单 Agent 执行与 Workflow 调度建模为不同 run 类型；Workflow 可通过显式节点创建 Agent 子运行，但不得读取 Agent 内部推理状态。

#### Scenario: Workflow 调用 Agent 子运行

- 触发：已发布 Workflow 的一个节点引用已发布 Agent revision，并启动 WorkflowRun。
- 期望：Scheduler 按依赖创建独立 AgentRun，持久化 parentRunId/childRunId；父运行只消费公开结果与状态，Agent Executor 不承担 Workflow 图调度。

### Requirement: 只执行已发布且可验证的资产

Runtime SHALL 在执行前解析不可变 asset revision，并校验 contractVersion、schema、checksum 与授权；未知或不受支持的输入 SHALL fail closed。

#### Scenario: 请求未知 revision

- 触发：StartRun 指向未发布 revision 或不受支持的 contractVersion。
- 期望：返回稳定拒绝错误，不创建可运行任务，不尝试旧 revision、其他协议或隐式 fallback。

### Requirement: PostgreSQL-only durable recovery

Runtime SHALL 将 run、attempt、checkpoint、action、幂等记录、租约与事件的正确性状态持久化到 PostgreSQL，不依赖进程内唯一状态。

#### Scenario: Worker 在 checkpoint 后退出

- 触发：Worker 完成一个 checkpoint 后进程退出，另一个实例随后领取该 run。
- 期望：新实例只依赖 PostgreSQL 恢复到最后可提交边界；已成功且有持久记录的工作不重复，Runtime 不切换到内存、SQLite 或 MySQL。

### Requirement: 多实例租约与 fencing

Runtime SHALL 使用有期限租约和单调 fencingToken 保护每次 attempt；所有续租与提交 SHALL 校验 owner、token 和 expectedRevision。

#### Scenario: 过期 owner 晚到提交

- 触发：Worker A 租约过期，Worker B 取得更大 fencingToken 后，A 再提交结果。
- 期望：A 的写入被拒绝且产生审计事件；B 保持唯一有效 owner，run 不被旧结果推进。

### Requirement: 外部副作用协作幂等

Runtime SHALL 为同一逻辑副作用复用稳定 operationKey，并只对声明了幂等或结果查询能力的 Capability 自动重试。

#### Scenario: 调用成功但结果落库前崩溃

- 触发：Capability 已产生副作用，Worker 在保存结果前退出，恢复后重试该 step。
- 期望：重试携带相同 operationKey，Capability 返回同一 effectReceipt，副作用不重复；若 Capability 无幂等声明，run 停止自动重试并暴露明确失败。

### Requirement: HITL 决策可持久恢复且只生效一次

Runtime SHALL 原子持久化 ActionRequest、WAITING_ACTION 状态、revision 和事件；提交 decision SHALL 校验 actionRequestId、expectedRunRevision 与授权。

#### Scenario: 重复和冲突的人工决策

- 触发：同一 ActionRequest 先收到合法 approve，再收到相同 approve 和不同 reject。
- 期望：首次 approve 生效；相同重复返回原结果；reject 返回冲突；重启恢复不会重复 interrupt 前的非幂等副作用。

### Requirement: 取消具有确定的并发边界

Runtime SHALL 将取消作为持久化协作信号，在取消提交后禁止新副作用，并以 revision 比较决定取消与完成的竞争结果。

#### Scenario: 取消与 attempt 完成竞争

- 触发：CancelRun 与 Worker.CommitAttempt 并发提交。
- 期望：数据库中先成功的合法终态规则生效；若取消先提交，晚结果不能推进主状态且仅留下审计；Runtime 不声称已撤回已经发生的外部副作用。

### Requirement: 事件可从游标续传且 presentation 保持通用

Runtime SHALL 为每个 run 生成严格单调 sequence 的持久事件，并支持从 afterSequence 回放；presentation/action payload SHALL 只包含版本化通用契约。

#### Scenario: 客户端在 presentation action 前断线

- 触发：客户端记录 sequence=N 后断线，期间产生 progress、presentation 和 action-required 事件，再以 afterSequence=N 重连。
- 期望：返回所有 sequence>N 的已提交事件并进入 live tail；重复投递可按 runId+sequence 去重；payload 不含业务实体、业务文案、renderer 实现或 raw chain-of-thought。
