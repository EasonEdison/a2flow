# Chat 状态与两把锁的阅读入口

三组状态描述不同的事实。枚举统一定义在 [chat_state.py](../packages/contracts/src/skillweave_contracts/chat_state.py), 不是三套竞争性的执行引擎。

| 枚举 | 权威来源 | 值及含义 |
| --- | --- | --- |
| ProductTurnStatus | B 端 chat_turns.status | QUEUED: 已接收待分发; RUNNING: 已进入分发/恢复检查; COMPLETED: 本轮展示终态已提交, 包括 waiting_action; NEEDS_REVIEW: 不确定事实阻止自动推进 |
| AgentTurnState | Runtime agent_chat_turns.state | RUNNING: 模型/工具调用前已记录执行准入, 可能在崩溃后残留; COMPLETED: 完整结果已验证保存; NEEDS_REVIEW: 原生执行异常/中断已记录 |
| TurnInspectionStatus | 本次 inspect_turn() 的现场结论 | NOT_STARTED: 无本轮执行证据且无会话/checkpoint 阻断; BUSY: 没拿到原生执行锁; COMPLETED: 已保存的本轮结果通过校验; NEEDS_REVIEW: 事实不足或不一致, 不可自动重放 |

COMPLETED 不表示业务任务成功。返回补参卡片可以结束当前 Agent 轮次, 用户提交后登记下一轮。BUSY/NOT_STARTED 不作为上述两张表的状态列保存。单独看到 RUNNING 行也不能证明执行者还活着。

## 从接口跳到真正实现

```text
DurableDispatcher.dispatch
  → ChatRunner.inspect_turn (Protocol 声明)
  → 实际注入的 ChatLoopRunner.inspect_turn
  → ConversationStore.inspect_turn (真正取锁、读取执行结果及 checkpoint)
```

入口分别在 [B 分发器](../services/b-side-api/src/a2flow_bside/durable_chat.py), [部署适配器](../deploy/attended/chat_runner.py) 和 [Runtime 持久化](../services/agent-workflow-runtime/src/agent_workflow_runtime/chat/persistence.py)。公开 [RuntimeTurnInspection](../packages/contracts/src/skillweave_contracts/chat_result.py) 保留原有 Literal 字符串协议和 result 字段, 不要求调用端改用枚举对象。

## 两把逻辑锁保护不同范围

| 位置 | 键的原始输入与算法 | 保护范围 |
| --- | --- | --- |
| DurableChat.dispatch_lock | bside-chat:environment:conversation_id, PostgreSQL hashtextextended | B worker 的产品分发归属, 跨事务持有; 产品消息/事件写入另受 dispatch_generation 约束 |
| ConversationStore 的原生执行锁 | JSON(environment,user_id,conversation_id), SHA256 前 8 字节有符号整数; _execution_identity | 真正 Agent 会话的执行准入、模型/工具调用、checkpoint 与完整结果提交 |

B 的 dispatch_lock 不是 Runtime 的执行锁。即便取得 B 锁, 也不能假设 Runtime 没有执行者。inspect_turn 只在检查期间临时尝试原生执行锁; 真正执行时 session 再取得同一原生锁并重新校验准入。检查结论不是未来执行的预约。

- 原生锁取不到: 直接返回 BUSY, 此时还没通过查询本轮状态来判断是否执行过。
- 原生锁取得了, 但本轮仍有 RUNNING 或不可信结果: 返回 NEEDS_REVIEW, 不能当成 NOT_STARTED。
- 原生锁取得了, 本轮完成结果合法: 返回 COMPLETED, B 只修复展示。
- 本轮无执行证据, 其他会话/checkpoint 检查也通过: 返回 NOT_STARTED; session 仍有最终执行准入检查。

## BUSY 分支为什么传回 current status

set_status(current["status"]) 在此分支保留产品状态, 并把 next_attempt_at 按原行为推迟两秒:

```text
原来 QUEUED  → 仍是 QUEUED
原来 RUNNING → 仍是 RUNNING
```

BUSY 可能来自同一会话的其他执行, 不能据此断定当前轮次已开始。方法也承担其他产品状态更新, 因此没有增加第三种 BUSY 表状态或新重试框架。

连接级 advisory lock 会在持锁连接断开时释放, 协程却可能仍在等待外部操作。dispatch_generation 防止旧 B 写入者覆盖新代次的产品投影/事件, 不会撤销已经发出的业务请求, 也不提供业务 exactly-once。未知业务结果仍不能自动重放; 业务幂等属于被调用 API。

本次仅补词汇、命名和说明: 两张表结构、锁键、锁顺序、准入判定、两秒重查、审批和自动续聊语义不变。验证和交付边界见 [方案](../openspec/changes/chat-state-vocabulary/proposal.md)。
