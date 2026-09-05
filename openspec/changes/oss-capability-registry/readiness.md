# 业务能力注册平台准出状态

## 总结

**Runtime：NO READY**

本 change 只有 PROPOSED 设计。设计文件已进入 `origin/main`；这只能证明源码交付，不能证明设计已批准、实现存在、服务已部署或 Runtime 可用。

## 证据矩阵

| 门禁 | 状态 | 当前证据 | 达到 READY 仍需 |
| --- | --- | --- | --- |
| 设计源码交付 | YES | 首版内容 commit `a8cdbf9f3e47b99f5018db111a9304e5253e3d6e` 已集成 | main-brain 设计审查 |
| 需求边界 | PARTIAL | proposal/spec 已描述候选边界 | main-brain 审批跨域所有权 |
| 共享契约 | NO READY | 仅提出消费者需求 | `ReleaseRef`、错误、上下文和凭证引用正式版本 |
| 实现 | NO READY | 无代码 | 完成 tasks 中实现并审查 |
| PostgreSQL 持久化 | NO READY | 仅设计 | schema、迁移和集成证据 |
| 多实例一致性 | NO READY | 仅并发规则 | 两实例共享 PostgreSQL 的运行测试 |
| 安全/凭证 | NO READY | 仅边界规则 | 实现、扫描与负向用例 |
| Runtime 契约 | NO READY | 逻辑端口 PROPOSED | 传输映射、契约测试和真实 Runtime 消费 |
| 回归 | NO READY | CR-01 至 CR-08 为 PLANNED | 自动化和 E2E 实际通过 |
| 部署 | NO READY | 未授权、未执行 | 独立部署授权和运行证据 |

## 阻断项

- 共享资产/发布契约未批准。
- JSON Schema 方言及允许能力集未批准。
- Runtime 语言、传输协议和版本未批准。
- 可信上下文目录、CredentialRef 所有权未批准。
- 无实现、构建、数据库、部署、调用或 E2E 证据。

## 可接受的当前结论

- 可以说：“业务能力注册平台首版契约草案已完成并进入源码评审。”
- 不可以说：“业务能力注册平台已实现、可部署、可调用或 Runtime READY。”
- 设计文档合入 main 不改变以上结论。

## READY 判定条件

只有以下条件全部满足后，才允许把 Runtime 准备度改为 READY：

1. 待裁决项形成已接受的共享契约/ADR。
2. 所有必需实现任务完成并通过代码审查。
3. PostgreSQL-only、多实例、重启恢复和并发发布证据通过。
4. Runtime 与公开样例适配器完成契约测试。
5. CR-01 至 CR-08 有可复现实际证据且无必需门禁为 PARTIAL/NO READY。
6. 独立部署与运行验证获得明确授权并执行成功。
