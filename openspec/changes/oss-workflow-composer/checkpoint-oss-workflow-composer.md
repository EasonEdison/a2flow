# oss-workflow-composer 执行检查点

## 当前状态

- 任务：M 侧 Skill Workflow Composer Phase 1 对齐与图契约需求。
- 阶段：main-brain 首轮审查后的 context/Skill identity 小修订。
- 权威基线：`SW-P1-20260907.2 + ENG-01`。
- 基线提交：`1bcc61a4137436f5c3811d555d2af8244c0fc971`。
- 基线集成 SHA：`c168f2c3b7f86cb0bd5e2bec48caf4ec1de1df7e`。
- 本次修订前 `origin/main` 同步 SHA：`f419910d387eab687359baabdbf7af384eae1da3`。
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

- platform-contracts：候选 `SW-CONTRACTS-P1-CANDIDATE.1` 定义 exact `skillKey`；完整 graph/context/resolver/interaction/result/control revision 仍待 main-brain 命名。
- Runtime：LangGraph 编译映射、实际执行祖先 state accumulator、A waits/B1→B2/join/A2UI retry 和 reducer 重放去重实证。
- Skill registry：exact `skillKey` 和统一 `use_skill`，禁止 Runtime/Composer 拆前缀映射。
- A2UI registry：selection Application、interaction mode、Action success/completion。

## 下一可执行动作

等待 main-brain 复核本轮 context/Skill identity 小修订并命名 shared graph revision；在放行前不实现 `services/workflow-registry/`。

## 交付记录

- 本轮 worker commit/push：交付完成时以本 checkpoint 所在 worker HEAD 与 `origin/codex/oss-workflow-composer/design` 对齐为真值。
- 本轮 `origin/main` 集成：交付完成时包含上述 worker HEAD；精确 SHA 由 Git ref 和最终回报给出。
- 服务实现：未开始，等待共享 contract revision 审查放行。
- Runtime 证据：无，保持 `NO READY`。
