# 验证记录

2026-10-07 第一批源码：contracts.py、cron.py、streams.py。

- Python 3.11 strict mypy：3个文件通过，无类型忽略。
- Ruff：新增三文件检查通过；格式检查后规范化 Streams 文件。
- 本机独立 Redis 8.0.3 Unix socket：初始化可重复、发送、消费、模拟未 ACK 超时后另一 consumer 接管、ACK + 删除、pending/队列清空通过。验证实例已 shutdown；未连接公网 Redis 或业务数据库。
- Cron `0 9 * * *` / Asia/Shanghai：UTC 00:00 后下一次为 UTC 01:00。
- 消息 DTO：正 int64 最大值 JSON 序列化为字符串，反序列化精确恢复。
- 未执行项目单测，遵守用户要求；以上是类型检查与最小真实适配器探针，不是端到端验收。

未完成：现有计划API接入、outbox与运行接受去重、消费者服务接线、Workflow/A2UI适配、Redis部署及公网定时任务验证。
