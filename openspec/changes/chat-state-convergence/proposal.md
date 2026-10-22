# Chat 状态与持久化收敛方案

状态：用户已批准三阶段实施与自主验证。2026-10-22 基线为 main/GitHub 06962a3。用户随后明确：**只按最新版本实现，不兼容旧版本**。此要求覆盖初版方案中的历史迁移、回填、双结构兼容和回退实现。本次不更换 Agent 框架，不改 Workflow 执行语义。

## 权威和目标

| 数据 | 最新结构职责 |
|---|---|
| agent_chat_turns | 原生执行是否开始、完整结束与可校验的完整结果快照 |
| agent_conversations | 用户/环境/会话与 checkpoint thread 关联，不再存日常执行状态 |
| chat_turns | 产品来源去重、队列顺序、分发代次和交付状态；可关联 processing_task_id |
| chat_requests | 多客户端请求号到同一 chat_turn 的映射与负载摘要，不重复助手消息ID |
| chat_continuations | 与卡片真实完成同事务保存的可靠续聊意图；PENDING/MATERIALIZED/NEEDS_REVIEW |
| chat_turn_events | SSE 传输日志及重订阅；不宣称不可变 Event Sourcing |
| messages | 产品消息与展示投影，不是第二套模型历史 |
| processing_tasks/operations/cards | 异常处理、真实业务回执及卡片关系；独立业务审批记录继续保留 |

waiting_action 表示当前 Agent 轮次完整结束并等待交互，不代表整个业务任务已完成。

## 阶段一：状态与终态事务

集中原生检查、产品轮次、展示交付及续聊响应的类型和映射，不混淆各状态域。最终助手投影和 chat_turns COMPLETED 同事务提交，验证消息对、会话、dispatch_generation 及可写状态。普通增量可保存但不能提前关闭队列；原生完成而产品投影未提交时仍能恢复。未知结果、缺失证据不授权自动执行。

## 阶段二：统一登记

chat_turns 直接使用 source_kind/source_key/source_digest/processing_task_id。统一登记器在消息准入事务中建立来源、消息对及轮次；普通消息、异常处理和卡片续聊均采用此契约。删除 processing_turns 的活动结构和所有重复登记回调，不保留旧 request_id 前缀兼容入口。

chat_requests 保留作用域、client_request_id、请求摘要和轮次引用。多个 clientRequestId 对同 processingRequestId 的多对一语义保持；同ID不同内容返回409。续聊意图不能改成内存任务，物化失败仍逐条隔离，卡片/任务绑定必须可靠且去重。

## 阶段三：完整结果与派生准入

共享中立契约定义有类型纯归并器和完整结果快照；Runtime 不导入 B 产品持久化或业务域。快照保留正文、最终消息身份、模型过程、真实工具参数及结果、卡片引用与顺序、个人工作流产物、等待及完成事实；结构、轮次身份和校验摘要都需验证。

原生 session 释放执行锁前保存快照；删除完整 events 数组。B 对 COMPLETED 直接绑定原消息身份并修复投影，不再通过 _Replay 重放 token，不再调用模型或业务工具。实时流和结果恢复使用同一结果归并契约，SSE 日志继续支持重订阅；代次 fencing 拒绝旧实例写入。

agent_conversations 删除 state/last_turn_id；实际忙碌、失败阻断和完成由同执行锁域下的 agent_chat_turns 与 checkpoint 事实推导。检查点缺失、执行中断、结果未知或快照无效仍显式阻断，不因租约或时间到期重跑。

## 最新结构与部署边界

只提供最新结构的全新安装与运行。不实现历史回填、旧事件转换、双写旧列、旧 API 或数据库兼容层。初始化和就绪检查发现不匹配结构时明确拒绝，不能把已有数据清空、重置或解释为新执行。

当前公网数据库不属于本次自动重建对象；本次源码实现和隔离自验不会删除或改写公网历史。部署如需更换数据环境，另按具体授权与数据保留范围执行，不以“不兼容”推导可删除历史。

## 自主验收

1. 同clientRequestId同内容复用、改内容409；并发重复只有一轮和一对消息。
2. 多clientRequestId对同processingRequestId仍多对一；不同来源不得冲突或串用。
3. 接收提交后执行前崩溃，原生NOT_STARTED才可领取；运行中/未知业务结果不重跑。
4. PostgreSQL真实注入最终状态写失败，最终消息与产品终态一起回滚；代次隔离。
5. 原生完成、B提交失败后只用快照恢复；无模型或业务重入。
6. 卡片完成后物化/任务绑定前崩溃仍只续聊一次；WRITE真实参数确认、一次执行后自动继续；READ直接执行。
7. 刷新、SSE重订阅、用户/环境/会话隔离；不匹配schema拒绝且原数据不变。
8. 实际生产装配及现有Workflow缺参、审批、总结、通知、结果引用相关核心探针不回归。
9. 类型/格式、仓库边界及准确出站文件检查。合成模型与真实PostgreSQL证据分别标明；源码、部署、公网验收分别报告。
