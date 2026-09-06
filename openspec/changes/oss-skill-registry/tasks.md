# Tasks: oss-skill-registry Phase 1

> Baseline: SW-P1-20260907.2
> Runtime readiness: **NO READY**
> Checked items below are documentation/example alignment only, not service implementation or runtime proof.

## 0. ALIGN

- [x] 0.1 核对专属 worktree/分支/状态，fetch 并 merge `origin/main` 到基线集成 SHA `c168f2c3b7f86cb0bd5e2bec48caf4ec1de1df7e`。
- [x] 0.2 读取仓库 `AGENTS.md`、Phase 1 `baseline.md`、`plan.md` 和本任务 checkpoint。
- [x] 0.3 从活跃设计中移除 Workflow-bound Skill publication、WorkflowReleaseRef 门禁和固定依赖图。
- [x] 0.4 对齐 `use_skill` 唯一入口、trusted userId/environment、PRT/ONLINE 分库和普通用户权限边界。
- [x] 0.5 提交 use_skill 消费需求与候选包约束，明确共享 schema 仍由 contracts owner 冻结。
- [x] 0.6 准备 `evidence-first-brief` 通用指令样例、chat/Workflow 原样复用案例和校验正反例。
- [ ] 0.7 main-brain 审查实际 diff，记录冲突消除结果并命名可实现的共享 contract revision。

## 1. Approved-contract Gate

- [ ] 1.1 获得 trusted context、environment-local resolver、package/release reference、version evidence 和共享错误语义的命名 revision。
- [ ] 1.2 与 Runtime owner 确认 `use_skill` model-visible input、trusted injection 和 success material 的最终合同。
- [ ] 1.3 与 main-brain 确认 `services/skill-registry/` 的语言、目录和根依赖所有权。
- [ ] 1.4 确认 `requiredToolNames` 是 revision 元数据还是只从指令推导；不得授予权限。
- [ ] 1.5 在以上 gate 完成前，不写共享 contracts、根 manifest 或跨域 Runtime 代码。

## 2. Minimal Domain Slice after Review

- [ ] 2.1 在 `services/skill-registry/` scaffold 经批准的最小模块，不安装未批准的共享依赖。
- [ ] 2.2 实现 Agent Skills-compatible package validator core：frontmatter、name/directory、digest/size、安全路径和资源上限。
- [ ] 2.3 实现 catalog/material application ports，接口显式接受后端 trusted context，模型参数不含 userId/environment。
- [ ] 2.4 实现普通用户 authoring denial 与 discovery/material 权限分离。
- [ ] 2.5 实现 PRT current、ONLINE stable/gray 的 resolver adapter；只消费共享 contract，不自造 gray 算法。
- [ ] 2.6 实现 PostgreSQL repository 与唯一/乐观并发约束；不提供 SQLite/MySQL fallback。
- [ ] 2.7 保证 published Skill 无 WorkflowReleaseRef、graph、route 或 mode-specific output。

## 3. Focused Verification

- [ ] 3.1 用独立样例验证同一 package digest 在 chat/Workflow 的 use_skill 结果一致。
- [ ] 3.2 验证普通用户可浏览/授权使用但不能 create/edit/upload/publish。
- [ ] 3.3 验证 ONLINE 不读 PRT，gray 只使用 trusted userId，且没有第三 serving version。
- [ ] 3.4 验证 native-directory/raw-locator bypass 无法加载正文或资源。
- [ ] 3.5 验证 scripts/allowed-tools 不执行、不提升权限。
- [ ] 3.6 用两个进程和 PostgreSQL 验证唯一性、CAS 和 environment-local resolution。
- [ ] 3.7 将真实 method、params、成功 data 和字段断言写入 `regression.md`；无证据项保持 PLANNED/NO READY。

## 4. Delivery

- [x] 4.1 提交前重新 fetch/merge 最新 `origin/main`，执行精确范围、`git diff --check` 与敏感信息扫描。
- [ ] 4.2 push worker 分支并通过本任务独占 integration worktree 合入服务器 `origin/main`，禁止强推。
- [ ] 4.3 回报 worker/integration SHA、实际检查和剩余 NO READY 门禁。
