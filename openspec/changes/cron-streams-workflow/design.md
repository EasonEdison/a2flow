# Cron 与 Redis Streams 执行方案

状态：2026-10-07 已批准实施；尚未部署或完成端到端验收。

## 边界

- M 继续 Java；调度、Workflow、通知和 Chat 属于 Python 运行态。
- Redis Streams 是消息投递通道，PostgreSQL 是计划、执行状态、checkpoint、通知与 outbox 的事实源。
- 五字段 cron + IANA 时区；不接受秒字段或自造 cron 解析器。沿用既有错过窗口不补跑的策略。
- 先限制活动 Workflow 执行并发为一；等待 A2UI 不占执行槽，不阻塞后续消息。
- 不引入业务补偿、跨运行业务幂等、Skill 自动重试或失败静默降级。

## 类型与入口

固定命令分别使用 StartWorkflow、ResumeWorkflow、NotificationCommand。入口校验后内部访问具名字段，不传多层 dict。真正动态的业务 JSON 保留在业务边界，不用于调度控制协议。

Streams 只携带 message_id，业务内容通过同环境数据库 outbox 读取，避免把身份、卡片、模型结果放入 Redis 大消息。userId 在后端为正 int64；浏览器/HTTP JSON 边界仍为十进制字符串。

## 投递与去重

1. 到期计划推进与 outbox 命令写入同一个数据库事务，schedule_id + scheduled_at 唯一。
2. relay 发送引用后记录投递时间；发送成功但记录失败允许重投同 message_id。
3. consumer 先核对数据库处理状态，以稳定 message_id/run_id 接受执行；不得重新生成 run_id。入口尚未实现去重时禁止启用该消费链路。
4. 数据库记录处理结果后才 XACK。一个 stream 一个消费组，ACK 后删除已处理条目；不按 MAXLEN 裁剪 pending。
5. Redis 丢失数据时，依据未完成 outbox 再投递。不是重跑已有业务；执行状态未知时记录 UNKNOWN 并停止自动执行。
6. XAUTOCLAIM 只恢复投递所有权，不能单凭租约超时重复执行 Skill。长运行接受与实际模型执行分离，消费者不持有整段模型调用。

## A2UI

复用 Chat 的资产读取、use_skill、契约查询、render_application、Action 与观测机制；Workflow 自身不是 A2UI 页面。
分页、编辑、选择不完成节点；终结 Action 成功落库后写恢复命令，继续当前 Skill，Skill 完成后由 Workflow 推进。失败不推进。停止的运行不恢复。

## 资源与验证

Redis 私有网络、持久化卷、AOF、noeviction；明确容器上限并保留持久化重写余量。初步预算128–192MiB不是已测 RSS，不新增公网端口。
未投递命令保留数据库；Redis 满或不可达必须暴露错误。验证正常投递、重复投递、ACK 前崩溃、积压、重启恢复及 A2UI 跨页/完成/刷新；最终记录实测内存。

官方语义：https://redis.io/docs/latest/commands/xautoclaim/ 与 https://redis.io/docs/latest/commands/xack/。
