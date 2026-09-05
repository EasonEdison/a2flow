# Readiness: oss-skill-registry

> Overall runtime readiness: **NO READY**
> Design status: **PROPOSED**
> 本 change 尚未获批、未实现、未部署、未执行回归，不得对外宣称 Skill Registry 可用。

## Gate Matrix

| Gate | Status | Required evidence |
| --- | --- | --- |
| Scope and clean-room review | PARTIAL | 本域文档范围与敏感信息检查记录；main-brain 复核 |
| Architecture approval | NO READY | main-brain/CTO 对 proposal、两阶段绑定和 MVP 依赖范围的明确批准 |
| Shared contracts | NO READY | 已冻结 AssetIdentity、ArtifactDescriptor、ReleaseRef、auth/idempotency/revocation |
| Capability/Workflow contracts | NO READY | 可执行的 resolver/binding 合同与合同测试 |
| PostgreSQL implementation | NO READY | migration、约束、并发状态机和恢复测试 |
| Package inspector safety | NO READY | digest/size/path/symlink/resource-limit 的真实测试证据 |
| Publication implementation | NO READY | 幂等发布、unknown outcome 恢复和单一 SemVer release 证据 |
| Multi-instance verification | NO READY | 至少 2 个实例共享 PostgreSQL 的并发与重启证据 |
| Regression | NO READY | `regression.md` 中 REG-01 至 REG-08 的真实 method/params/data/断言 |
| Deployment/demo | NO READY | 已授权部署、HTTPS demo 和复现步骤；本轮不在授权范围 |
| Source design delivery | DELIVERED | worker c83a869ded9f588c3241f003c072e17bc800a58a 已 push；首次集成 main 2970ca7548ec9d8d6c803d10e29198d5d172ef5d |

## Go / No-go Rule

只有以下条件全部满足时，整体状态才可从 `NO READY` 变更：

1. 设计和公共合同均已明确批准，待裁决项为零。
2. 所有实现 task 有对应 commit 与审查记录。
3. PostgreSQL-only、两实例并发、重启恢复和幂等发布验证通过。
4. REG-01 至 REG-08 均有实际响应与字段级断言，无必需 gate 为 PARTIAL/NO READY。
5. 部署由用户另行授权并产生可复用运行证据。

“文档已合入 main”“接口已编码”“单实例手工成功”都不能单独构成 runtime READY。

## Current Blockers

- 公共 artifact/release/auth/revocation 合同尚未冻结。
- SkillRevision 与 WorkflowRelease 的两阶段关系尚未跨域批准。
- Capability range 解析与 Workflow binding 端口尚无可执行合同。
- 实现、测试、部署和 Runtime 证据均不存在。
