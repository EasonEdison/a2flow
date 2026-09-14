# oss-workflow-composer 执行检查点

## 当前状态

- 任务：M 侧 Skill Workflow Composer Phase 1 对齐与图契约需求。
- 阶段：`PAUSED`；用户最新优先 Python Workflow/DeepAgent 运行引擎，M 端 Workflow Composer 停止新实现、设计/契约扩展和发布。
- 权威基线：`SW-P1-20260907.2 + ENG-01`。
- 基线提交：`1bcc61a4137436f5c3811d555d2af8244c0fc971`。
- 基线集成 SHA：`c168f2c3b7f86cb0bd5e2bec48caf4ec1de1df7e`。
- 本轮提交前 `origin/main` 同步 SHA：`bd0f3a98e57928735547e3188df39da01bfa0865`。
- 设计状态：`PROPOSED`。
- Runtime 状态：`NO READY`。
- 工作区：`/home/admin/OpenSource/repos/.parallel/oss-workflow-composer/platform`。
- Worker 分支：`codex/oss-workflow-composer/design`。
- 目标：`origin/main`。

## 已完成

- 已核对 pwd、branch、status 和 worktree list；worker worktree 无未知脏改动。
- 已执行 `git fetch origin` 和 `git merge --no-edit origin/main`，无冲突快进到统一基线集成 SHA。
- 已读取仓库 `AGENTS.md`、Phase 1 `baseline.md`、`plan.md` 和 `engineering-decisions.md`；ENG-01 选择 Python M 后端模块但不自动增加常驻服务。
- 已读取并合入 PY-01 增量：系统 Python 变更已授权但仅 Runtime 可执行；本任务未触碰主机 Python。
- 已读取 ENG-01：Workflow registry 后端后续采用 Python 可导入模块，精确包布局和依赖仍审查受控。
- 已将祖先 context 与 exact `skillKey` 要求同步给 Contracts/Runtime；两方均确认禁止前缀推断，Runtime 将验证显式 accumulator、parallel reducer 和 replay 去重。
- 已重写 proposal/design 的 active first-version semantics，并清理冲突旧 design-only 方案。
- 已向 main-brain 发送首个对齐回执，包含基线、冲突、专属范围、首个切片和真实依赖。
- 已修订 spec/tasks/regression/readiness，并增加有效图、验证场景和标准库自检脚本。
- 已按 TDD 先验证缺失 context case 和旧 `skillRef` 均会使 checker 失败，再修正为：`PASS nodes=11 edges=12 staticCases=5 runtimeCases=5 contextCases=2`。
- 已接收 Contracts 固定候选快照：内容 commit `404bbcacc1ef176c273c9a90fc4ae91bfadc42fd` 已进入 main；状态仍为 `SW-CONTRACTS-P1-CANDIDATE.1 / PROVISIONAL`，未冒充 named graph approval。
- 已基于官方项目元数据形成 `inputs/python-module-validation-candidates.md`：推荐 shared JSON Schema + strict Pydantic + NetworkX，提出未来 Python 包布局、分层 pipeline、复杂度/限额和 TDD/mutation 门禁。
- 本任务未安装依赖、未修改根 manifest/lock、未创建 `services/workflow-registry/`、未更改系统 Python。
- 已完整读取 `implementation-release-01.md`，SHA256 与下发值 `c14eb61371562bf512b393ab347c80d2c4e3be082e4a7e838dc13e2a0f9743a4` 一致；确认 `SW-P1-SUBSET-01` 不列入 Workflow owner，也不批准 graph/context/control/events。
- 已向 main-brain 直接回执：本任务只消费 snapshot `a1cb44e88ce5bb603c62b4618804c78ae0d5585c` 的 exact `skillKey/use_skill` 命名闭包，不开始 Workflow source。
- 首轮 10 个专属文件已由 worker `255475d4a5a71ed767adf22362c6353a40fc4e12` push 并集成；main-brain 实际复核后指出“直接前驱”偏差。
- 服务器未安装 OpenSpec CLI；未安装依赖，未执行 strict CLI validate。

## 已移除的冲突

- 串行-only 和“条件/并行以后再说”。
- 相邻 schemaRef 必须完全相等并强制 Adapter Skill。
- 固定旧 Skill release 继续执行和 Runtime 技术栈待定。
- 线性 ordinal-only manifest。
- 未限定的 retry/idempotency 口径。
- 缺失的 AI 不确定 A2UI 选择和 Finalizer 事实边界。

## 专属范围

- 可修改：`openspec/changes/oss-workflow-composer/`。
- 已预留、待共享契约审查后才实现：`services/workflow-registry/`。
- 不修改共享 contracts、Runtime、其他 registry、根配置和其他任务 checkpoint。

## 首个可执行切片

完成 sequence/AI condition/non-nested parallel/explicit join 发布图候选、A 等待/B1→B2/join 真值表、失败/skip/Finalizer/A2UI-only retry 边界，并增加非规范 JSON 样例与 Python 标准库验证。

## 真实依赖

- platform-contracts：`SW-P1-SUBSET-01` 已命名 corrected snapshot `a1cb44e88ce5bb603c62b4618804c78ae0d5585c` 的 exact `skillKey/use_skill` 闭包；wire field 仍为 `SW-CONTRACTS-P1-CANDIDATE.1`。完整 graph/context/resolver/interaction/result/control revision 仍待 main-brain 命名。
- Runtime：LangGraph 编译映射、实际执行祖先 state accumulator、A waits/B1→B2/join/A2UI retry 和 reducer 重放去重实证。
- Skill registry：exact `skillKey` 和统一 `use_skill`，禁止 Runtime/Composer 拆前缀映射。
- A2UI registry：selection Application、interaction mode、Action success/completion。

## 下一可执行动作

暂停期间无可执行待办，不自行恢复，也不补新接口。仅在 main-brain 明确提出运行引擎所需的最小依赖或解除暂停后，先重读权威文件、核对本 checkpoint/Git 真值，再 fetch/merge 最新 `origin/main` 并执行被点名的最小动作。

## 交付记录

- 本轮 worker commit/push：交付完成时以本 checkpoint 所在 worker HEAD 与 `origin/codex/oss-workflow-composer/design` 对齐为真值。
- 本轮 `origin/main` 集成：交付完成时包含上述 worker HEAD；精确 SHA 由 Git ref 和最终回报给出。
- 服务实现：未开始，等待共享 contract revision 审查放行。
- Runtime 证据：本任务未执行；main-brain 已提供 `7a8fd6ca…` 结构实验输入，但恢复/并发/持久化等未证明，整体保持 `NO READY`。

## 暂停交接（2026-09-07）

- 暂停指令：用户将优先级切换到 Workflow/DeepAgent Python 运行引擎；此处 Workflow 明确不是 M 端 Workflow Composer。
- 当前 worker HEAD：`cb24c7fefedad5faed7ce1dfe91ecd39d087803d`。
- 远端 worker：`origin/codex/oss-workflow-composer/design` = `cb24c7fefedad5faed7ce1dfe91ecd39d087803d`。
- 当前已知 `origin/main`：`f3e5a05398df58dfd4f5a5dfc1445e05604d0977`；只做 read-only 包含关系检查，确认其包含本任务最新交付 `cb24c7fefedad5faed7ce1dfe91ecd39d087803d`，本次暂停未 fetch/merge。
- 已合 main 的本任务交付：`255475d4a5a71ed767adf22362c6353a40fc4e12`（基线设计）、`0980f0ae304a340f24d7421ab4a51818af612b32`（祖先 context/exact skillKey 修正）、`10390429783a54920cb162eba4c613ee1360f453`（Python module/validator 候选）、`cb24c7fefedad5faed7ce1dfe91ecd39d087803d`（subset release 边界同步）。
- 未提交文件：仅 `openspec/changes/oss-workflow-composer/checkpoint-oss-workflow-composer.md`（本暂停交接）；按指令不创建空 ACK commit、不 push、不强行合并。
- 活动命令/进程：无；没有 shell session、测试、安装、服务、数据库或发布动作在运行。
- Runtime 输入：main-brain 指定未来 graph 编译方案引用 `7a8fd6ca…` 的父图双 compiled-subgraph 结构实验；MemorySaver 仅为结构实验，恢复、并发、任意 DAG、嵌套与持久化均未证明。本任务暂停期间不复跑、不扩展。
- 精确恢复点：等待 main-brain 的明确最小依赖请求或解除暂停；不得把 M Composer 待办当作 Python 运行引擎优先事项。

## AF10 Resume Checkpoint (2026-09-14)

- Status: HANDOFF
- Current phase: VERIFYING
- Scope: bounded Workflow ManagementFeature backend, focused tests, and the private AF10 release note.
- Out of scope: frontend, real PostgreSQL, real publication, model calls, deployment, new dependencies, shared/root/other-owner files.

### Worktree

- Worker: `/home/admin/OpenSource/repos/.parallel/oss-workflow-composer/platform`
- Branch: `codex/oss-workflow-composer/design`
- Target: `origin/main`
- Synchronized HEAD: `da20a8523805b35fa78985d93a5f0006399d5aad`
- Dirty before resume: this checkpoint only; preserved without stash/reset/clean.

### In Progress

- Implement the released AF10 sequential multi-Skill management slice against shared ManagementFeature, DraftRepository, AssetReader and Runtime loader contracts.

### Next Executable Action
- Main-brain reviews the pushed fixed candidate and integrates it; this worker starts no further work.

### Completed With Evidence

- Shared baseline synchronized by fast-forward merge to `da20a8523805b35fa78985d93a5f0006399d5aad`.
- Added `a2flow_workflow_composer.WorkflowManagementFeature` with explicit Host-owned reader, draft repository, namespace and validator dependencies.
- Sequential definitions normalize to the exact Runtime/asset contract; published Skill references are resolved in trusted environment context.
- AI routing, branch and parallel topology drafts can be saved but return `UNSUPPORTED_WORKFLOW_TOPOLOGY` and cannot prepare publication.
- Focused unit and real AssetReader tests: 8/8 passed with Python 3.11.

### Last External Progress

- 2026-09-15: focused Workflow management suite completed 8/8; no PostgreSQL, model, publish or deployment action executed.
