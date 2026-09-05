# 准备度

## 总结

- Overall：`NO READY`
- Design：`PROPOSED`
- Runtime：`NO READY`
- Evidence：仅设计文档
- Source state：PROPOSED 文档源码；Git 集成只证明文档已交付，不表示设计批准

## 门禁矩阵

| 门禁 | 状态 | 证据/缺口 |
| --- | --- | --- |
| 业务范围 | `PARTIAL` | 首片已收敛，仍待主控批准 |
| 平台共享合约 | `NO READY` | Asset/Release/Auth/Correlation 未定版 |
| Runtime 消费合约 | `NO READY` | 协议、命令、snapshot/events、interrupt/retry 未定版 |
| A2UI 消费合约 | `NO READY` | 版本、catalog/artifact、action 绑定未定版 |
| Capability Adapter 合约 | `NO READY` | 发布引用、授权、输入输出和幂等字段未定版 |
| PostgreSQL 模型/迁移 | `NO READY` | 未实现 |
| 产品后端 | `NO READY` | 未实现 |
| React 产品壳/A2UI Host | `NO READY` | 未实现 |
| 自动化回归 | `NO READY` | `regression.md` 全部为 `PLANNED` |
| 多实例运行验证 | `NO READY` | 未部署、未执行 |
| 公开演示 | `NO READY` | 未部署、未执行 |

## 升级为可实现前的必要条件

1. 主控批准 proposal/design 与三项跨域裁决。
2. 共享发布引用、Runtime、A2UI 和 Capability 契约具备明确版本与兼容策略。
3. 任务拆分确认不会让产品后端复制 Runtime 状态机。
4. 安全审查批准受信 catalog、action 授权和输入输出限制。

## 升级为 runtime READY 前的必要证据

1. PostgreSQL-only 迁移、唯一约束和恢复测试通过。
2. R1-R8 具备可复现命令、实际响应、字段级断言和结果。
3. 至少两个 API/worker 实例完成断线、实例切换、并发决定和幂等重试验证。
4. 真实 Runtime 与 A2UI Host 端到端完成，不含静默 fallback。
5. 部署、HTTPS 演示、日志/指标和三分钟演示路径具备可复查证据。

在全部必需门禁完成前，不得宣称产品可用、Runtime 可用、已部署或已验证。
