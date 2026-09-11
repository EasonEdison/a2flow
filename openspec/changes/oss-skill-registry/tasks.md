# Tasks: oss-skill-registry Phase 1

> Baseline: SW-P1-20260907.2
> Implementation release: SW-P1-SUBSET-01 at 3a48d4b106db8f382c3c96bbc8992f328b81e259
> Runtime readiness: **NO READY**
> Checked items identify completed source or documentation work only. Runtime
> admission remains governed by `readiness.md`.

## 0. ALIGN

- [x] 0.1 核对专属 worktree/分支/状态，fetch 并 merge `origin/main` 到基线集成 SHA `c168f2c3b7f86cb0bd5e2bec48caf4ec1de1df7e`。
- [x] 0.2 读取仓库 `AGENTS.md`、Phase 1 `baseline.md`、`plan.md` 和本任务 checkpoint。
- [x] 0.3 从活跃设计中移除 Workflow-bound Skill publication、WorkflowReleaseRef 门禁和固定依赖图。
- [x] 0.4 对齐 `use_skill` 唯一入口、trusted userId/environment、PRT/ONLINE 分库和普通用户权限边界。
- [x] 0.5 提交 use_skill 消费需求与候选包约束，明确共享 schema 仍由 contracts owner 冻结。
- [x] 0.6 准备 `evidence-first-brief` 通用指令样例、chat/Workflow 原样复用案例和校验正反例。
- [x] 0.7 main-brain 审查实际 diff；按评审补齐 Agent Skills name/compatibility、binary asset 和 validation/execution 分离边界。
- [x] 0.8 main-brain 以 SW-P1-SUBSET-01 命名放行 Skill Registry 所需定义子集；wire revision 仍为 SW-CONTRACTS-P1-CANDIDATE.1。

## 1. Approved-contract Gate

- [ ] 1.1 获得 trusted context、environment-local resolver、package/release reference、version evidence 和共享错误语义的命名 revision。
- [x] 1.2 SW-P1-SUBSET-01 已确认 model-visible request 仅含 skillKey，trusted context 由服务端注入，success material 使用批准的 useSkillResult。
- [x] 1.3 main-brain 已确认 Python、`services/skill-registry/` 独立 import package、根 pyproject/lock 由主控统一，且不新建常驻进程。
- [x] 1.4 requiredToolNames 是 compatibility hint，可映射但绝不授予 Tool/script 权限。
- [x] 1.5 仅按 SW-P1-SUBSET-01 实现 Registry owner 路径；未修改共享 contracts、根 manifest 或跨域 Runtime 代码。
- [x] 1.6 提交格式校验、安全 YAML、资源读取候选调研和模块路径清单；未安装依赖或实现通用解包。

## 2. Minimal Domain Slice after Review

- [x] 2.1 在 `services/skill-registry/` scaffold 经批准的最小模块，不安装未批准的共享依赖。
- [ ] 2.2 实现 Agent Skills-compatible package validator core：完整 name/description/compatibility 约束、name/directory、digest/size、安全路径、资源上限和文本/二进制 asset 区分。
- [x] 2.3 实现 catalog/material application ports，接口显式接受后端 trusted context，模型参数不含 userId/environment。
- [ ] 2.4 实现普通用户 authoring denial 与 discovery/material 权限分离。
- [ ] 2.5 实现 PRT current、ONLINE stable/gray 的 resolver adapter；只消费共享 contract，不自造 gray 算法。
- [ ] 2.6 实现 PostgreSQL repository 与唯一/乐观并发约束；不提供 SQLite/MySQL fallback。
- [x] 2.7 保证当前 source projection 无 WorkflowReleaseRef、graph、route 或 mode-specific output。

## 3. Focused Verification

- [ ] 3.1 用独立样例验证同一 package digest 在 chat/Workflow 的 use_skill 结果一致。
- [ ] 3.2 验证普通用户可浏览/授权使用但不能 create/edit/upload/publish。
- [ ] 3.3 验证 ONLINE 不读 PRT，gray 只使用 trusted userId，且没有第三 serving version。
- [ ] 3.4 验证 native-directory/raw-locator bypass 无法加载正文或资源。
- [ ] 3.5 验证正文提到 Tool、scripts/allowed-tools 不触发误拒且不提升权限；结构化 unsupported execution profile 才明确失败。
- [ ] 3.6 用两个进程和 PostgreSQL 验证唯一性、CAS 和 environment-local resolution。
- [ ] 3.7 将真实 method、params、成功 data 和字段断言写入 `regression.md`；无证据项保持 PLANNED/NO READY。

## 4. Delivery

- [x] 4.1 提交前重新 fetch/merge 最新 `origin/main`，执行精确范围、`git diff --check` 与敏感信息扫描。
- [x] 4.2 push worker 分支并通过本任务独占 integration worktree 合入服务器 `origin/main`，未强推。
- [x] 4.3 已向 main-brain 回报 worker/integration SHA、实际检查和剩余 NO READY 门禁。

## 5. SW-P1-SUBSET-01 Source Implementation

- [x] 5.1 Scaffold a stdlib-only importable module under services/skill-registry/ without root manifest or dependency changes.
- [x] 5.2 TDD immutable entry/resource descriptors and finite entry, per-entry byte, total-byte, path-length and path-depth limits.
- [x] 5.3 TDD exact logicalPath uniqueness, safe relative paths, actual-byte size/digest agreement, strict UTF-8 text and opaque binary retention.
- [x] 5.4 TDD separate model request and trusted invocation context plus catalog/material ports.
- [x] 5.5 TDD mapping of verified instructions/resources and trusted resolution evidence to the approved useSkillResult shape.
- [x] 5.6 Verify compatibility metadata remains a hint and cannot trigger Tool/script execution or authorization.
- [x] 5.7 Add owner README and keep YAML/frontmatter parsing, archive extraction, model filesystem locators, resolver admission, DB, process, deploy and production fallback out of scope.

## 6. SUBSET-01 Focused Verification

- [x] 6.1 Record each resource-validator and useSkill projection red/green cycle.
- [x] 6.2 Verify same verified material maps identically from chat and Workflow contexts except caller-supplied trusted evidence.
- [x] 6.3 Verify invalid paths, duplicates, size/digest mismatch, finite limits and invalid UTF-8 text fail closed; binary bytes remain opaque.
- [x] 6.4 Validate a success result against the approved schema definition and focused semantic checker; describe this as source-shape evidence only.
- [x] 6.5 Run import check, stdlib unit tests, git diff --check, sensitive-data scan and two-pass changed-Python review.
- [x] 6.6 Update regression.md/readiness.md while trusted provenance, resolver, DB/service and runtime proof remain NO READY.

## 7. SUBSET-01 Delivery

- [x] 7.1 Fetch and merge fresh origin/main before commit/push, then rerun complete source checks.
- [x] 7.2 Push the worker branch; merge through the exclusive integration worktree from fresh origin/main and push HEAD:main without rebase/force/stash/reset/clean.
- [x] 7.3 Report exact source/worker/integration SHAs, touched paths, fresh tests and NO READY boundaries.
