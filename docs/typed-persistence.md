# Python 类型化数据访问规范与迁移

状态：2026-10-08 用户批准；分模块实施，不代表全仓迁移完成。

## 当前部署与回归结论（2026-10-08 23:05）

首批 B 通知 Repository 与第二批 Scheduler/Outbox 已部署，下面各批次的“未部署”是当时记录，现由本节更新。首次回归遇 RPC_EXECUTION_FAILED，随后复现并修复执行服务普通并发突发被拒绝的问题（84872cd）；不能确定它就是首次失败的原因。

新 Cron schedule 3 只触发一次并停用；公网手动完成阅读要点、编辑选题、确认稿件三张卡片，run 3a3c1af8c7e34536bb6034cf12321bec 数据库存储 SUCCEEDED。启动、三次续跑和四条通知共八条 Outbox completed，两条 Streams pending=0。完成通知22标记已读并跳转同一运行；刷新后历史工具数7/7/8与已确认卡片恢复，不重执行。旧失败及UNKNOWN记录未重放。

本次范围 READY；不等于其他 B Repository、内容服务或运行态存储全部完成 ORM 迁移。未跑全套单测、手机端或全面压测。

## 统一规范

- 使用 SQLAlchemy 2.x，数据库字段以 `Mapped[T]` 声明；普通查询使用表达式，不拼业务值或列名。
- Repository 输入/返回为明确类型；固定结构使用 dataclass/Pydantic DTO，不把任意 dict 数据库行传入业务层。HTTP JSON 只在边界序列化。
- 持久化实体、请求与响应分别建模，不让数据库字段自动暴露到 API。
- Repository 拥有短事务，跨 Repository 业务必须共享同一 Session/Connection 和事务，不能用两个独立连接拼接原子操作。
- Outbox、条件 upsert、SKIP LOCKED 可用 Core；必要的参数化原生 SQL 集中管理，保留幂等、锁、UNKNOWN 不自动重放语义。
- digest 由规范化序列化负责，与 ORM 解耦。禁止借迁移修改历史摘要、业务枚举落库值或已有表结构。
- 当前沿用既有 SQL schema/migrations；不调用 metadata.create_all，不同时引入 Alembic。后续迁移治理单独评估。
- 不引入 SQLModel 或自研通用 QueryWrapper。同步服务使用同步 Session；不为此增加异步连接栈。

## 第一批：通知读取与标记已读

- 新增 notification_repository.py：类型化通知实体、运行归属只读投影、NotificationView、Repository。
- 删除旧 NotificationsRepository SQL 实现，两个 B 组装入口均接新实现；API 输出字段不变。
- 保留用户过滤、未读优先/时间降序、limit、运行 ID 转 control ID 及原引用保留行为。
- NullPool 保留按操作短连接，不增加常驻数据库连接；连接超时、语句超时、锁超时保持不变；参数不记录到 SQLAlchemy 错误文本。
- SQLAlchemy==2.0.54 放入独立 requirements-db.txt，attended/realchat Dockerfile 均安装。psycopg 仍是数据库驱动。

## 验证与准出

- strict mypy（新增 Repository，依赖导入 follow-imports=silent）通过，未忽略缺失依赖或新增类型错误。
- 临时 PostgreSQL 实例实测：DTO 查询、同用户运行引用转换、跨用户不可转换/修改、重复已读、缺失 ID、提交持久化、未读排序和 limit 均通过。
- 无生产数据库写入、无模型调用；临时探针不提交。未跑全套单测。
- 本批为源码交付，尚未部署到公网；不能将前一次 UI 部署视为本批 ORM 已部署。

## 后续批次

1. Scheduler 的 schedule 推进与 Outbox 入队作为同一事务整体迁移，再迁移通知写入与限流。
2. B 端其他 Repository 按业务边界迁移并去掉 dict 传播。
3. 内容服务与运行态存储逐模块审查；保留 LangGraph/SDK 自带存储，不重写其实现。
4. 每批通过隔离 PostgreSQL 验证后再部署，分别记录源码、部署与公网证据。

## 第二批：Scheduler 与 Outbox（2026-10-08）

- 当前 Redis Streams 运行链路已改为 SQLAlchemy：定时扫描/推进、Outbox upsert/发布/认领/完成/延后/UNKNOWN 对账、通知限流与插入。
- 使用 Mapped 实体与 DueSchedule/WorkflowCommand DTO；业务不再解包十列位置元组。JSONB 仅作为序列化边界，不把散装 JSON 用作控制协议。
- 定时推进和 enqueue 共用显式 Session 事务。发布持有 SKIP LOCKED 行锁；外部执行前 claim 已提交，finish 提交后才能 ACK。
- 卡片完成观察器保留一个明确的参数化 SQL 入队适配器，加入卡片原 psycopg 事务。不是两套 Outbox 服务，不另开事务，不改卡片数据库层。生命周期通知使用 SQLAlchemy 事务。
- 原始 SQL schema/migrations、枚举文本、JSONB 相等幂等、60秒重发窗口、30秒容量延后、5分钟UNKNOWN收敛和通知限流语义保留。JSON文本先以Text绑定再cast JSONB，防止双重序列化。
- 真实隔离 PostgreSQL 验证通过：相同/冲突消息、并发只认领一次、卡片事务回滚、UNKNOWN不认领、容量延后、并发扫描只触发一次、入队失败整体回滚、通知幂等及20条限流。
- 真实隔离 Redis + PostgreSQL 验证通过：跳过已锁消息、发布冷却、消费入队引用、重复引用不再次派发、完成后ACK且pending清零。
- 新改5模块strict mypy通过；Ruff、语法与diff检查。未跑全套单测。探针使用独立临时实例，未触碰公网任务/数据。
- 未部署本批源码；现有历史 legacy loops/workers 不属于当前 Streams 入口，本轮未恢复或重写该旧队列。

参考：https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html
