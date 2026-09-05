# 准出状态

## 结论

`NO READY`

本 change 当前只有 `PROPOSED` 设计。没有实现、构建、自动化测试、部署或 Runtime 证据，不得宣称功能可用。设计文件合入 `main` 也只代表 source delivery，不代表设计批准。

## 门禁

| Gate | 要求 | 当前状态 | 证据 |
| --- | --- | --- | --- |
| G1 领域边界 | main-brain 确认 Composer、Skill registry、shared contracts、Runtime 所有权 | `PARTIAL` | 已写依赖与边界，待跨任务评审 |
| G2 共享契约 | release identity、摘要、授权、幂等、撤销和 manifest 版本获批 | `NO READY` | 无已批准 contract/ADR |
| G3 实现 | PostgreSQL repositories、服务端校验/发布、React 编辑器完成 | `NO READY` | `tasks.md` 全部未勾选 |
| G4 自动化验证 | 单元、contract、PostgreSQL 集成、双实例并发测试通过 | `NO READY` | `regression.md` 全部 `PLANNED` |
| G5 Runtime 集成 | Runtime 成功解析并执行固定 release，错误路径失败关闭 | `NO READY` | 无运行 trace 或断言结果 |
| G6 演示链路 | 数字员工通过稳定 release 启动并完成纵切片 | `NO READY` | 无部署或 E2E 证据 |

任一必需 Gate 为 `PARTIAL` 或 `NO READY` 时，本 change 不可归档，不可标记 runtime-ready。

## 允许的当前声明

- 已提出受限串行图、不可变 Skill release 引用和线性 manifest 的设计候选。
- 已定义 planned 验收场景和跨域依赖输入/输出。
- 尚未验证任何 API、数据库、UI、Runtime 或部署行为。

## 升级为 READY 前必须具备

1. 三项待裁决契约有批准记录及确定版本。
2. 所有实现任务完成并由 PostgreSQL-only 自动化测试覆盖。
3. 至少双 API 实例证明草稿并发和发布幂等不依赖本地状态。
4. Runtime consumer contract test 验证顺序、摘要、未知版本和不可用依赖路径。
5. `regression.md` 写入真实 method、params、success data、字段断言结果和可复用证据。
