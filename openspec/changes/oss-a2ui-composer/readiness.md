# A2UI 组件编排平台准出状态

## 总结

- Baseline alignment：`READY`（`SW-P1-20260907.2` 已读）
- Design：`PARTIAL`
- Synthetic contract fixtures：`READY`
- Source integration：`READY`
- Shared contract：`NO READY`
- Registry implementation：`NO READY`
- Build/PostgreSQL：`NO READY`
- Runtime/Host integration：`NO READY`
- Deployment/E2E：`NO READY`
- Overall Runtime readiness：`NO READY`
- Archive decision：`NO READY`

tasks.md 只记录工作完成情况，不能替代本文件的证据门禁。静态 fixture READY 不等于 shared contract、registry、Runtime 或产品 READY。

## 门禁矩阵

| 门禁 | 状态 | 当前证据 | 达到 READY 的条件 |
| --- | --- | --- | --- |
| Clean-room | READY | 仅使用已授权需求、公开概念和项目自创 synthetic fixtures；无真实业务数据 | 每次外部发布前重复敏感/来源扫描 |
| Baseline alignment | READY | review hardening 已集成 `origin/main=3eac2f9…`；已读取 `SW-P1-20260907.2`、PY-01 与 ENG-01 | 后续基线变更继续安全 merge 和重读 |
| Design convergence | PARTIAL | Component/Application、interaction/completion、version/reset、retry/Finalizer 边界已写入 | main-brain 审查实际 diff 并关闭歧义 |
| Synthetic fixture validation | READY | Node v20.20.2；`20/20 tests PASS`；`validated 2 synthetic Application fixtures` | 若 shared contract 改动，更新夹具并重新验证 |
| A2UI protocol decision | NO READY | fixture profile 为 `PENDING_CROSS_DOMAIN_REVIEW` | main-brain 批准 profile/wire version/升级策略 |
| Shared contract | NO READY | `SW-CONTRACTS-P1-CANDIDATE.1` 固定快照已进 main 且 54/54 owner fixtures GREEN，但尚未获 main-brain 批准 | main-brain 命名 approved revision |
| Registry implementation | NO READY | ENG-01 已选 Python 可导入模块，但 `services/a2ui-registry/` 未实现；当前有意受门禁阻断 | approved revision + package review + 明确 IMPLEMENT 放行后实现 |
| PostgreSQL correctness | NO READY | 无 schema、migration、事务或多实例证据 | PostgreSQL-only 实现与集成测试通过 |
| Runtime `render_application` | NO READY | 只有消费需求和 synthetic fixture | Runtime 实现并证明 display/interactive/version/action/retry |
| Digital employee Host | NO READY | 只有 `packages/a2ui-host/` 消费需求 | Host 组件映射、能力协商和安全失败契约通过 |
| Source integration | READY | review hardening `3eac2f9de3a7b306b62a5175dae374d550223959` 已 push、验证并集成服务器 `origin/main` | 后续元数据提交继续走相同集成流程 |
| OpenSpec strict validation | NO READY | 服务器未发现 OpenSpec CLI；未安装工具 | 可用批准工具后执行 strict validation |
| Deployment | NO READY | 未授权且未执行 | 另行授权，并从批准的目标分支执行 |
| Runtime E2E | NO READY | 无 Surface、interaction、Action 或恢复运行证据 | P1-P9 必需场景有字段级实际证据 |

## 明确不成立的声明

当前不能宣称：

- A2UI registry、Composer 服务或 Application 发布 API 已实现。
- `SW-CONTRACTS-P1-CANDIDATE.1` 已获批准。
- 任一 A2UI 版本已经冻结。
- Runtime 已实现 `render_application`、等待/恢复、Action、retry 或 Finalizer。
- Host 已兼容 Catalog/Application。
- PostgreSQL 多实例、不可变发布或业务幂等已经验证。
- 静态夹具或 server-local Git 集成等于部署、公开发布或运行态 READY。
- PY-01 表示本任务应修改系统 Python；该权限只由 Runtime 在 main-brain 协调下使用。

## 当前阻塞项

1. main-brain 尚未批准 shared contract candidate 与 A2UI protocol profile。
2. registry 未获命名 approved revision 与 IMPLEMENT 放行。
3. Runtime/Host 尚无真实消费、失败关闭和 Action ingress 证据。
4. 无 PostgreSQL、构建、部署或 E2E 证据。

## 下一准出动作

1. main-brain 审查实际提交与 `SW-CONTRACTS-P1-CANDIDATE.1` 依赖。
2. 只有 main-brain 命名 approved revision 并下发 IMPLEMENT 后，才实现 `services/a2ui-registry/`。
