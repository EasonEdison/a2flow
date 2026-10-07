# 实施任务

- [x] 明确 Cron、消息、A2UI 及资源边界。
- [x] 编写具名消息 DTO、独立 Cron 计算器和 Streams 引用投递适配器。
- [ ] 将上述模块接入实际调度入口，移除旧启动失败盲目重入队。
- [ ] PostgreSQL outbox、稳定运行 ID 与命令处理去重闭环。
- [ ] 定时计划 API/页面支持 cron + timezone。
- [ ] Workflow 复用当前 Skill/A2UI，终结 Action 通过消息恢复节点。
- [ ] 部署 Redis 与消费者，实际测量内存。
- [ ] 公网完整定时触发、等待、完成交互、后继节点、通知验收。

源码模块存在不代表已接线或已上线。准出以 regression.md 为准。
