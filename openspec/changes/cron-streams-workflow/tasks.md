# 实施任务

- [x] Cron 表达式、时区和明确的错过触发策略。
- [x] 具名消息 DTO、Redis Streams 引用投递、PostgreSQL outbox。
- [x] 稳定触发 ID、运行接受去重、UNKNOWN 只读对账；删除旧失败盲重入队路径。
- [x] 定时计划 API 与页面。
- [x] Workflow 复用当前 RPC Skill/A2UI；成功终结 Action 经消息恢复。
- [x] Workflow 真实执行详情 catalog/history/SSE 接入。
- [x] 低内存部署与真实三节点业务链路验证。
- [x] 公网账号登录后的运行、历史卡片、通知与进度接口回读。
- [ ] 最终版本浏览器点击、刷新恢复、通知跳转及执行详情展开视觉验收。

未完成项受验收浏览器输入失效阻塞；不以接口通过替代页面通过。具体证据见 regression.md。
