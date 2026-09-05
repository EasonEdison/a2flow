# Tasks: oss-skill-registry

> 状态：**PROPOSED**。本轮仅交付设计，以下实现任务全部未开始、不得视为授权。
> Runtime readiness：**NO READY**。

## 0. Architecture Gates

- [ ] 0.1 main-brain 冻结公共 `AssetIdentity`、`ArtifactDescriptor`、`ReleaseRef`、授权、幂等和撤销语义。
- [ ] 0.2 main-brain 与 Workflow Composer 裁决两阶段 `SkillRevisionRef → WorkflowReleaseRef → SkillRelease`。
- [ ] 0.3 main-brain 裁决 OCI-compatible transport、允许的 locator，以及 M 侧模块化单体/独立服务形态。
- [ ] 0.4 main-brain 确认 MVP 仅含 Capability/Workflow 依赖，不含 Skill-to-Skill 依赖。
- [ ] 0.5 审查并批准本 change；在此之前禁止 scaffold 应用代码。

## 1. Contract and Persistence

- [ ] 1.1 根据已批准公共合同定义 Skill Registry 的 command/query port 与错误码。
- [ ] 1.2 设计 PostgreSQL-only schema、唯一约束、乐观并发列、审计字段和迁移。
- [ ] 1.3 定义 `SkillCatalogEntry`、`SkillVersionDraft`、`SkillRevision`、`ValidationReport` 和 publication record。
- [ ] 1.4 验证多实例下 metadata update、freeze、validation claim 和 publish compare-and-set。
- [ ] 1.5 定义无密钥、可审计的 artifact locator 与 credential provider 边界。

## 2. Catalog and Metadata

- [ ] 2.1 实现目录注册及 `namespace + slug` 唯一性与幂等。
- [ ] 2.2 实现 metadataRevision compare-and-set 编辑，冲突时返回当前 revision。
- [ ] 2.3 实现 ACTIVE/ARCHIVED 策略，不隐式删除既有 release。
- [ ] 2.4 实现只暴露 PUBLISHED 项的稳定游标目录查询。
- [ ] 2.5 增加授权与审计，禁止日志记录正文和凭证。

## 3. Versioning and Validation

- [ ] 3.1 实现 SkillVersionDraft、generation 并原子 freeze 为不可变 SkillRevision。
- [ ] 3.2 实现 SemVer 解析和同一 Skill 单一发布版本约束。
- [ ] 3.3 实现受限 ArtifactInspectorPort：size/digest/path/symlink/timeout 配额。
- [ ] 3.4 实现 Agent Skills `SKILL.md` frontmatter/name/description/name-directory 校验，绝不执行脚本。
- [ ] 3.5 通过 Capability Registry port 解析 range 并生成精确 dependency lock。
- [ ] 3.6 实现 validation fingerprint、TTL、policyVersion、失效与最多 3 次有界重试。
- [ ] 3.7 验证 `allowed-tools` 只作为实验兼容性信息，不提升权限。

## 4. Workflow Binding and Publication

- [ ] 4.1 校验精确 WorkflowReleaseRef 绑定当前 SkillRevisionRef。
- [ ] 4.2 实现 publish gate，对 catalog、SemVer、validation、dependencies、workflow、metadataRevision 做最终核对。
- [ ] 4.3 通过公共 PublicationPort 发布，不复制公共 release 状态机。
- [ ] 4.4 处理超时后的 unknown outcome：同一 idempotencyKey 查询/重试。
- [ ] 4.5 输出 Runtime 只读可消费的 PublishedSkillRef，不暴露 draft 或私有表。

## 5. Verification and Delivery

- [ ] 5.1 编写单元/合同测试覆盖规范中的 8 个验收场景及稳定错误码。
- [ ] 5.2 以 PostgreSQL 启动至少两个 API/worker 实例，验证并发注册、freeze、任务领取和发布。
- [ ] 5.3 用真实测试制品验证 digest mismatch、路径穿越、逃逸 symlink 和 size 限额。
- [ ] 5.4 验证 Capability/Workflow 端口的 timeout、429、5xx、撤销和 stale validation。
- [ ] 5.5 执行纵向切片回归并在 `regression.md` 填入真实 method、params、data 与字段断言。
- [ ] 5.6 所有必需门禁通过后更新 `readiness.md`；存在 PARTIAL/NO READY 时不得宣称可用或归档。
