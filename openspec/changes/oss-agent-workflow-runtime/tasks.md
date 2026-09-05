# Agent/Workflow Runtime 实现任务

## 状态

本文件只跟踪未来实现任务。当前设计为 PROPOSED，Runtime 为 NO READY；以下任务全部未开始。

## 1. 主控决策门禁

- [ ] CTO/main-brain 选择 TypeScript + LangGraphJS 或 Python + LangGraph，并记录 ADR。
- [ ] 与 oss-platform-contracts 统一 asset identity、revision、authorization、error envelope 与 event envelope。
- [ ] 与 Skill/Workflow/Capability/A2UI 域统一发布资产与执行端口，不在 Runtime 私建重复契约。
- [ ] 决定首个 transport 与协议版本，以及 A2UI payload/action response 的版本边界。

## 2. 测试先行与 PostgreSQL 基础

- [ ] 先写多实例领取、租约过期、fencing stale write 的 PostgreSQL 集成测试。
- [ ] 先写 start/action/cancel 命令幂等和 expectedRevision 并发测试。
- [ ] 先写 capability “成功后落库前崩溃”重复调用测试。
- [ ] 设计并评审 PostgreSQL-only migration；不得加入 SQLite、MySQL 或内存 fallback。
- [ ] 建立 Run、Attempt、Lease、ActionRequest、IdempotencyRecord、RunEvent 的 repository 边界。

## 3. Runtime 核心

- [ ] 实现 Runtime Command Port、Run Query 与状态机。
- [ ] 实现独立 Agent Executor 及其 checkpoint/resume。
- [ ] 实现独立 Workflow Scheduler、节点依赖与 Agent 子运行。
- [ ] 实现领取、续租、过期恢复与 fencing token。
- [ ] 实现错误分类、版本化重试策略与 retry budget。
- [ ] 实现 CapabilityExecutionPort 和稳定 operationKey。
- [ ] 实现 PresentationActionPort、WAITING_ACTION 与 SubmitAction。
- [ ] 实现协作式 CancelRun 与晚结果审计。
- [ ] 实现按 sequence 回放/续传的 Event Store 与 transport adapter。
- [ ] 实现无 raw chain-of-thought 的日志、指标和 trace 元数据。

## 4. 框架 parity spike

- [ ] 在候选语言中验证 PostgreSQL checkpointer 的真实进程重启恢复。
- [ ] 验证 interrupt/resume 的节点重放与副作用隔离。
- [ ] 验证 stream/custom event 与内部 RunEvent 的映射。
- [ ] 验证两个 worker 竞争和 stale writer 拒绝。
- [ ] 将结论回写 ADR；不保留双 runtime fallback。

## 5. 回归与准出

- [ ] 执行 regression.md 的八个计划场景并保存可复现实证。
- [ ] 执行数据库迁移、并发、故障注入、恢复和容量测试。
- [ ] 执行依赖方向与业务语义泄漏静态检查。
- [ ] 完成敏感信息、secret、许可证与供应链检查。
- [ ] readiness.md 的所有必需门禁通过后，才允许将 Runtime 从 NO READY 更新为 READY。
