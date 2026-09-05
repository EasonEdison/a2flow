# Readiness

## Overall

- Design review: `PROPOSED`
- Source artifact: `DESIGN ONLY`
- Implementation: `NOT STARTED`
- Automated contract validation: `NOT RUN`
- Deployment: `NOT RUN`
- Runtime: `NO READY`
- Evidence label: `C`

## Gate status

| Gate | Status | Required evidence |
| --- | --- | --- |
| 主控批准公共模型与待裁决项 | `NO` | 审查结论与 ADR |
| 六域接口需求完成归并 | `NO` | 六份输入/输出/边界回交和冲突清单 |
| Schema/错误码/事件类型冻结 | `NO` | 版本化 schema、兼容策略、固定 fixture |
| PostgreSQL 多实例正确性实现 | `NO` | 迁移、事务/CAS/outbox 代码与双实例测试 |
| 授权与审计实现 | `NO` | 默认拒绝、主体传播、脱敏审计负向证据 |
| Regression 计划执行 | `NO` | PC-01 至 PC-08 的真实 method/params/data/trace 证据 |
| Demo/部署/恢复验证 | `NO` | 目标环境、部署 SHA、重启恢复与 Run pin 证据 |

## 当前可以声称

- 已形成一份供主控审查的公共契约候选。
- 已明确公共层与六个领域的所有权、依赖输入输出、失败、重试和并发边界。

## 当前不能声称

- 不能声称设计已批准、接口已冻结、实现已完成、测试通过、已部署或 Runtime 可用。
- 合入 `main` 也只表示 proposed 设计源码完成集成，不提升上述状态。

## 升级条件

只有主控裁决三个架构闸门、六域契约归并完成、实现任务有真实证据且 regression 中必需用例全部通过，才可重新评估 READY。任一关键门禁为 NO/PARTIAL 时保持 `NO READY`。
