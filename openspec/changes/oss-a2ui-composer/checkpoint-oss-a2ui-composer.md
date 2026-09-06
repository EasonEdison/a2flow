# oss-a2ui-composer 执行检查点

## 任务身份

- 任务名称：`oss-a2ui-composer`
- 独占工作区：`/home/admin/OpenSource/repos/.parallel/oss-a2ui-composer/platform`
- Worker 分支：`codex/oss-a2ui-composer/design`
- 目标分支：`origin/main`
- 允许修改范围：
  - `openspec/changes/oss-a2ui-composer/`
  - `services/a2ui-registry/`
  - `packages/a2ui-contract-fixtures/`

## 当前磁盘真值

- Phase 1 基线：`SW-P1-20260907.2`
- 服务器同步：已有自有未提交改动时两次执行 `git fetch origin` + `git merge --no-edit origin/main`，从 `25c00aab…` 依次快进到 `c168f2c…` 与 `255475d4a5a71ed767adf22362c6353a40fc4e12`，无冲突、未 stash/reset/覆盖。
- PY-01：只撤销“系统 Python 不可替换”的禁令；Runtime 是唯一协调执行 owner，本任务不修改系统 Python。
- 工作区状态：当前仅本任务专属 change 与 `packages/a2ui-contract-fixtures/` 有改动。
- 设计状态：`PROPOSED / PHASE 1 ALIGNED`
- 运行态：`NO READY`

## 已完成里程碑

1. 已读取本任务入口、`AGENTS.md`、Phase 1 baseline/plan；未读取其他任务 checkpoint。
2. 已将旧 Presentation 资产设计收敛为 Component Catalog/Application。
3. 已明确 DISPLAY_ONLY/INTERACTIVE、Action 成功/完成分离、版本 reset、控制/业务幂等边界、A2UI-only retry 与 Finalizer 边界。
4. 已向 contracts owner 提交共享需求，并收到未批准候选 `SW-CONTRACTS-P1-CANDIDATE.1`。
5. 已新增两份 project-authored synthetic Application fixture、无依赖校验器和 focused tests。
6. TDD RED：删除两个 INTERACTIVE retry reason 后旧校验器未拒绝，测试报 `Missing expected exception`。
7. TDD GREEN：exact-set、success-condition ref 和 execution/continue/Action 三入口版本校验完成；最终 `node --test ...` 为 `12 pass / 0 fail`，目录校验输出 `validated 2 synthetic Application fixtures`。
8. 已标记 protocol profile 为 `PENDING_CROSS_DOMAIN_REVIEW`，未冻结旧稿 v0.9.1 建议。
9. 远端无 `rg`，使用限域 `grep`；未安装工具或依赖。
10. 手工远程 multi-file patch 曾两次因 hunk 行数错误被 Git 拒绝，文件未变；后续改为本机临时副本 + `apply_patch` + 标准 unified diff，再应用服务器。

## 当前依赖

- shared contracts：候选 `SW-CONTRACTS-P1-CANDIDATE.1` 已命名但未批准。
- Runtime：`render_application`、版本准入、Surface、interaction、Action、retry/stop/restart/Finalizer。
- digital employee：`packages/a2ui-host/` 的本地组件映射与可信 Action 回传。
- main-brain：批准协议/profile、shared revision，并明确下发 registry IMPLEMENT。

## 下一可执行动作

1. 将临时副本生成的标准 patch 应用到服务器 worker。
2. 执行范围、diff、focused test、敏感信息和 whitespace 验证。
3. commit/push worker，并通过独占 integration worktree 合入服务器 `origin/main`。
4. 回传 main-brain：`SW-P1-20260907.2`、actual diff、worker SHA、integrated SHA、测试证据与 NO READY 门禁。

## 禁止越界

- 未获 approved shared revision 与 IMPLEMENT 放行前，不实现 `services/a2ui-registry/`。
- 不部署、不开放端口、不启动服务、不修改系统包或系统 Python。
- 不把 synthetic fixture、source integration 或 contracts candidate 当作 Runtime READY。
- 不读取或更新其他任务 checkpoint。
