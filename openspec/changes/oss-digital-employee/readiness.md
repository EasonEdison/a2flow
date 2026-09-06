# 准备度

## 总结

- Overall：`NO READY`
- Design：`ALIGN / CONTRACT REVIEW`
- Runtime：`NO READY`
- Evidence：`SW-P1-20260907.2` 对齐文档与公开 SDK 能力调研
- Source state：设计源码；Git 集成只证明文档已交付，不表示接口批准、实现完成或 Runtime 可用

## 门禁矩阵

| 门禁 | 状态 | 证据/缺口 |
| --- | --- | --- |
| 基线对齐 | `YES` | 已按 `SW-P1-20260907.2` 删除旧版本继续、通用 retry、第二套 event/action 与产品侧业务幂等 |
| 首片业务范围 | `PARTIAL` | 合成 Workflow fixture 和 UI 状态已收敛，仍待 main-brain 批准 |
| 平台共享合约 | `NO READY` | 已发送 consumer requirements；等待 contracts owner 命名修订 |
| Runtime 消费合约 | `NO READY` | start/read/subscribe、节点输入/Action、stop/reset、A2UI retry 与错误语义未形成获批命名版本 |
| A2UI 消费合约 | `NO READY` | profile/catalog 支持声明、DISPLAY_ONLY/INTERACTIVE、Action 结果与完成交互未形成获批命名版本 |
| 业务 Tool 合约 | `NO READY` | 首片不做真实业务写入；未来 Tool 输入输出、授权和业务后端责任仍待裁决 |
| 个人长期记忆控制 | `PARTIAL` | 已给 A/B/B+ 条件成本；待代码核验 Store/namespace/delete 权限与最小 diff 后由 main-brain 判断是否低成本 |
| PostgreSQL 模型/迁移 | `NO READY` | 未实现 |
| 产品后端 | `NO READY` | 未实现 |
| React 产品壳/A2UI Host | `NO READY` | 未实现 |
| 自动化回归 | `NO READY` | `regression.md` 全部为 `PLANNED` |
| 多实例运行验证 | `NO READY` | 未部署、未执行 |
| 公开演示 | `NO READY` | 未部署、未执行 |

## 升级为可实现前的必要条件

1. main-brain 批准 proposal/design 与三项跨域裁决。
2. contracts owner 给出明确命名修订，覆盖可信上下文、发布引用、运行操作/事件/错误、stop/reset 与 Action。
3. Runtime 与 A2UI owner 确认精确版本、profile/catalog 支持声明和交互完成语义。
4. 任务拆分确认产品 BFF 不复制 Runtime 状态机、不增加第二套 event/action schema。
5. 安全审查批准受信 catalog、Action 重新授权和输入输出限制。

## 升级为 runtime READY 前的必要证据

1. PostgreSQL-only 持久化与恢复测试通过。
2. R1-R8 具备可复现命令、实际响应、字段级断言和结果。
3. 至少两个 BFF/worker 实例完成断线、实例切换、控制并发、stop 与配置失配验证。
4. 真实 Runtime 与 A2UI Host 端到端完成，且只有获批 A2UI retry，不含静默 fallback。
5. 部署、HTTPS 演示、日志/指标和三分钟演示路径具备可复查证据。

在全部必需门禁完成前，不得宣称产品可用、Runtime 可用、已部署或已验证。
