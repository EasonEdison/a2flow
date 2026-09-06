# Regression: oss-skill-registry Phase 1

> Baseline: SW-P1-20260907.2
> Current evidence: **ALIGNMENT / FIXTURE STATIC PASS**
> Runtime readiness: **NO READY**
> HTTP 与 Tool 字段仍待共享 contract revision；本表是消费者验收计划，不是运行通过声明。

## Current Static Evidence

执行日期：2026-09-07。环境：服务器专属 worker；Python 3.6.8；PyYAML 3.12；没有安装或升级依赖。

实际命令：

- `git diff --check`
- `python3 -`，对 `SKILL.md` frontmatter/name/description/reference、两个 reuse cases、十四个 validation cases 和禁止字段执行只读断言
- `sha256sum examples/evidence-first-brief/SKILL.md examples/evidence-first-brief/references/output-format.md`
- 精确文件/任务/scenario/敏感信息 grep 计数

实际结果：

- `git diff --check`：PASS。
- `fixture_static_check=PASS`；`sample_name=evidence-first-brief`；`description_chars=170`。
- `validation_cases=14`；`reuse_cases=2`；`same_model_input=true`。
- 以上只证明样例与 fixture 定义可解析、静态断言成立；没有执行 validator 的 14 个结果，也不是 chat/Workflow 双入口运行证据。
- `SKILL.md sha256=1cc034c1d066b24771e9b0d91bc74abd89012268cf225802c25dd33316e06434`。
- 样例 `SKILL.md` 中 Workflow/route/userId/environment 禁止字段命中 0；私有/敏感模式命中 0。
- `openspec` 与 `skills-ref` CLI 均不存在；未安装依赖，因此未执行 strict/OpenSpec 官方 validator。

以上只证明当前文档/fixtures 的静态一致性，不是 package validator 实现、Runtime `use_skill`、PostgreSQL 或跨域合同运行证据。

## Planned Contract Scenarios

| ID | Status | Method | Params / setup | Expected success `data` or failure | Field assertions |
| --- | --- | --- | --- | --- | --- |
| SK-P1-01 discovery-safe | PLANNED | candidate `listSkills` | trusted ordinary principal, current environment | `data.items[]` | 含 skillKey/name/description/tags；不含 instructions/resource bytes/locator/credential |
| SK-P1-02 authoring-denied | PLANNED | candidate `publishSkill` | ordinary principal + valid draft ref | shared forbidden failure | 无 draft/package/publication 副作用 |
| SK-P1-03 use-skill-chat | PLANNED | Tool `use_skill` | model input `{skillKey:"demo/evidence-first-brief"}` + injected PRT userId/context | `data={resolvedSkill,versionEvidence,instructions,resources}` | 不接受 model userId/environment；返回 PRT current |
| SK-P1-04 use-skill-workflow | PLANNED | Tool `use_skill` | 与 SK-P1-03 同 skillKey/package；injected Workflow node scope | 同上 | instructions/resources digest 与 chat 一致；无 route/nextNode/workflow-specific output |
| SK-P1-05 online-no-prt | PLANNED | shared resolver via `use_skill` | ONLINE context，Skill 仅存在于 PRT | `SKILL_NOT_FOUND`/approved equivalent | 没有 PRT 查询或 fallback |
| SK-P1-06 online-gray | PLANNED | shared resolver via `use_skill` | ONLINE trusted userId 命中 gray；模型另传伪造 userId | ONLINE gray resolved data | 仅 trusted userId 生效；最多 stable+gray 两版本 |
| SK-P1-07 native-bypass | PLANNED | Runtime material load | native directory/raw locator without authorized use_skill | `SKILL_ENTRY_BYPASS_DENIED`/approved equivalent | agent context 无 instructions/resources |
| SK-P1-08 package-valid | PLANNED | candidate `validatePackage` | `examples/evidence-first-brief/` + immutable candidate package reference | `data={status:"PASSED",checks,digest}` | name/dir/reference 通过；不执行内容 |
| SK-P1-09 package-invalid | PLANNED | candidate `validatePackage` | `examples/validation-cases.yaml` negative cases | `data.status="FAILED"` or approved failure envelope | 每例稳定 code；无执行/边界外写入 |
| SK-P1-10 execution-policy-separated | PLANNED | validate/load material | valid instruction mentions execute_ability，package may include scripts/allowed-tools；另有 structured executable profile case | deterministic validation passes or warns for content；structured unsupported profile fails explicitly | 无 script call、无新增 Tool permission、无自然语言误杀 |
| SK-P1-11 standalone-publish | PLANNED | candidate `publishSkill` | admin + valid revision + shared idempotency/publication input | `data={publishedSkillRef}` | 无 WorkflowReleaseRef/graph/route；相同 key 幂等 |
| SK-P1-12 stale-version | PLANNED | resolve at continue ingress | run evidence V1，effective config V2 | mismatch data/failure | Runtime 可在新业务调用前 reset；无 frozen V1 fallback |

## Focused Failure Boundaries

- package structure/digest/path 错误是 deterministic failure，不自动重试。
- package backend timeout 可以由作者态控制操作用同一 request key 有界重试；这不是 Workflow node retry。
- `use_skill` failure 是 Tool failure。Phase 1 不提供 generic Skill retry/recovery。
- publication timeout 是 unknown outcome；只允许按共享幂等语义查询/重试。
- environment/userId override、native bypass 和 ordinary-user authoring 均 fail closed。
- 任何版本不一致由 Runtime admission 在新工作前阻断；Registry 不提供 frozen-version continuation。

## Evidence Needed before READY

- main-brain 命名的 contracts revision 和 Runtime use_skill 合同测试。
- 实际 service SHA、依赖版本、license 和构建命令。
- PostgreSQL-only migration 与至少两个进程的并发证据。
- SK-P1-01 至 SK-P1-12 的真实 method/params/data/字段断言。
- 同一独立样例在 chat/Workflow 的 byte/digest 一致性。
- 未授权路径无副作用的日志/数据库证据。
