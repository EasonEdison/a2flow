# Agent/Workflow Runtime Readiness

## 总结

- 当前结论：NO READY
- 设计：PROPOSED，等待 CTO/main-brain 审查
- 实现：未开始
- 自动化验证：未执行
- Runtime 证据：无
- 部署：未授权、未执行
- 证据等级：C（design-only）

源文件合入 main 只表示设计草案已交付，不表示设计已批准、代码已实现、服务已部署或 Runtime 可用。Git 交付证据以本 change 的 task checkpoint 为准。

## 门禁

| 门禁 | 当前状态 | 通过条件 |
| --- | --- | --- |
| 语言 ADR | NO READY | CTO 选择语言并记录替代方案、证据和复议触发条件 |
| 共享契约 | NO READY | 资产、Capability、Workflow、presentation/action、authorization 与 event envelope 经各 owner 统一 |
| PostgreSQL-only | NO READY | migration 和集成测试覆盖所有环境，无其他数据库或内存 fallback |
| 多实例正确性 | NO READY | 两个以上 worker 完成领取、续租、接管和 stale writer fencing 故障注入 |
| 幂等 | NO READY | start/action/cancel 与外部 capability operationKey 场景全部通过 |
| HITL/取消 | NO READY | 并发、重复提交、重启恢复和晚结果边界有运行证据 |
| 事件续传 | NO READY | 游标回放、gap 检测、至少一次去重和顺序断言通过 |
| 安全与边界 | NO READY | 无业务语义、raw chain-of-thought、凭据；授权与敏感信息检查通过 |
| 可复现运行 | NO READY | 干净环境构建、测试、启动和纵向 demo 成功 |

## 当前证据

- 已有：净化需求、平台边界、公开官方 LangGraph/PostgreSQL 资料与本 change 的设计/计划。
- 不存在：依赖安装、编译、单元测试、PostgreSQL integration、故障注入、浏览器验证、部署和生产运行证据。
- OpenSpec strict validate：若交付环境没有 CLI，将明确记为未执行，不能替代人工审查。

## 解除 NO READY 的最低证据

1. 主控批准语言与公共契约。
2. 实现 tasks.md 的 MVP 项，并以 PostgreSQL-only 配置运行。
3. regression.md 八个场景全部具有可复现实证。
4. 完成依赖方向、敏感信息、secret、许可证与供应链检查。
5. 在至少两个 API/worker 实例的测试拓扑证明恢复、fencing、幂等和续传。
6. 主控审查 readiness 证据后显式更新状态；任务完成比例不得自动改变准出结论。
