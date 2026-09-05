# Regression Plan: oss-skill-registry

> Evidence status: **PLANNED ONLY**
> Runtime readiness: **NO READY**
> 本文件没有任何已执行、通过或运行态证据。接口路径和错误 envelope 尚待公共 API 合同批准。

## Planned Environment

- PostgreSQL-only 测试数据库；不得使用 SQLite/MySQL 替代。
- 至少 2 个 API/worker 实例共享 PostgreSQL，实例重启后状态可恢复。
- 受控 artifact fixture provider，可返回固定 digest、损坏内容、timeout/429/5xx 和恶意目录条目。
- Capability Registry、Workflow Composer、PublicationPort 使用合同测试替身或真实测试模块；替身行为和调用必须可断言。
- fixture 只使用独立公开样例，不含公司源码、域名、数据、凭证或日志。

## Planned Contract Scenarios

| ID | Status | Method | Params / setup | Expected success `data` or failure | Field-level assertions |
| --- | --- | --- | --- | --- | --- |
| REG-01 register-idempotent | PLANNED | `POST /api/v1/skills` | `{namespace:"demo", slug:"research-assistant", displayName, summary, tags, idempotencyKey:"reg-01"}`；两个实例并发重放 | 成功 `data={skillId,metadataRevision,lifecycleState}` | 两次 `skillId` 相同；`metadataRevision=1`；`lifecycleState=ACTIVE`；数据库只有一个 namespace/slug |
| REG-02 metadata-cas | PLANNED | `PATCH /api/v1/skills/{skillId}` | 两请求都带 `expectedMetadataRevision:4`，修改不同 summary | 首个成功 `data={skillId,metadataRevision:5,updatedAt}`；第二个 conflict | 最终 summary 等于首个提交；错误含 `currentMetadataRevision=5`；无静默覆盖 |
| REG-03 freeze-generation | PLANNED | `POST /api/v1/skill-version-drafts/{draftId}/freeze` | `{expectedGeneration:3,idempotencyKey:"freeze-03"}`，随后用 generation 2 重试 | 成功 `data={skillRevisionRef,revisionDigest}`；旧 generation conflict | ref/digest 非空且重放相同；冻结快照不随 draft 后续变化；只生成一个 revision |
| REG-04 validate-conforming | PLANNED | `POST /api/v1/skill-revisions/{revisionRef}/validations` | 合法 descriptor；根 `SKILL.md` name/description 与目录名匹配；含不会被执行的 `scripts/` | `data={validationId,status:"PASSED",checks,dependencyLock,validationFingerprint,expiresAt}` | integrity/structure passed；无脚本调用；allowed-tools 不产生授权；lock 中每个 capability 为精确 release+digest |
| REG-05 reject-unsafe | PLANNED | `POST /api/v1/skill-revisions/{revisionRef}/validations` | `{idempotencyKey:"val-05"}`；分别注入缺失 `SKILL.md`、name mismatch、`../`、绝对路径、逃逸 symlink、超限文件数 | `data={validationId,status:"FAILED",checks}` 或批准后的标准 failure envelope | 每类有稳定 errorCode 和安全 path；无边界外写入；无自动业务重试；不能 publish |
| REG-06 digest-mismatch | PLANNED | `POST /api/v1/skill-revisions/{revisionRef}/validations` | `{idempotencyKey:"val-06"}`；descriptor 声明 digest D/size S，provider 返回不一致 bytes | `data={validationId,status:"FAILED",checks}`，checks 含 integrity code | 不替换 D/S；不降级 warning；publication record 不存在；审计不含包正文 |
| REG-07 dependency-stale | PLANNED | `POST /api/v1/skill-revisions/{revisionRef}/publications` | `{validationId,validationFingerprint,workflowReleaseRef,metadataRevision,idempotencyKey:"pub-07"}`；先撤销 locked capability，或令 workflow 指向其他 revision | 标准 publish failure envelope，无 success `data` | error 指向 capability revoked 或 workflow binding mismatch；旧 fingerprint 不可复用；Runtime 未收到 release |
| REG-08 publish-recovery | PLANNED | `POST /api/v1/skill-revisions/{revisionRef}/publications` | `{validationId,validationFingerprint,workflowReleaseRef,metadataRevision,idempotencyKey:"pub-08"}`；两实例并发；首次响应丢失 | `data={publishedSkillRef}` | 两调用收敛到相同 releaseId/releaseDigest；同 Skill SemVer 仅一条 publication；目录仅在 PUBLISHED 后返回 package descriptor、dependency lock、workflow ref |

## Planned Failure and Retry Assertions

- artifact/capability/workflow 的 timeout、429、5xx：validation 进入 `RETRYABLE`，最多 3 次有界退避；超限后等待显式重试。
- deterministic validation error 与 digest mismatch：不进入自动重试循环。
- PublicationPort unknown outcome：必须用原 idempotencyKey 查询/重试；不得换 key。
- validation `expiresAt` 到期、`policyVersion` 变化或 dependency state 变化：publish gate 返回 stale，重新校验后才可继续。
- API/worker 进程在 freeze、validation、publish 各状态点重启：恢复依赖 PostgreSQL，不依赖进程内内存。

## Evidence Required Before Changing Status

每个场景执行后必须补充：

- 实际日期、Git SHA、环境、实例数和 PostgreSQL 版本。
- 实际 method/path、脱敏 params、响应 status 与成功 `data`。
- 每条字段级断言及结果。
- 必要的数据库唯一性/状态查询、stub 调用记录、日志 requestId。
- 失败场景的稳定 errorCode 与未发生副作用的证据。

在上述证据为空时，本文件只能保持 `PLANNED ONLY`。
