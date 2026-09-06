# oss-capability-registry 执行检查点

## 当前状态

- 任务：`oss-capability-registry`
- 服务器 worktree：`/home/admin/OpenSource/repos/.parallel/oss-capability-registry/platform`
- worker 分支：`codex/oss-capability-registry/design`
- 集成目标：`origin/main`
- 当前基线：SW-P1-20260907.2
- 基线提交：`b1a0c9f32497c04dd623edb0bb8858a01b5ae7ad`
- 消费者内容已合入 main SHA：`57d11fcfee3481512d444a51fee0db3280357789`
- 阶段：`SW-P1-SUBSET-01` 已批准；正在执行 Capability Registry 第一实现切片
- Runtime：`NO READY`

## 本轮已核对

- 2026-09-07 已核对 pwd、分支、status 和全部 server worktree。
- worker 起始状态干净，已执行 fetch origin 与 merge origin/main。
- 恢复时 worker 已同步到 `255475df9c9d9fdf7ca280b6df7b9a2875b965ff`，随后在本任务脏改期间只 fetch/read 最新 origin/main，未带脏 merge。
- 已读取仓库 AGENTS.md、Phase 1 baseline.md 和 plan.md。
- 未读取或修改 main-brain 及其他任务 checkpoint。
- 已读 PY-01：系统 Python 变更已获必要时授权，但只由 Runtime 在 main-brain 协调下执行；本任务未操作系统 Python。
- 已读 ENG-01：Capability Registry 后端采用独立 Python 域模块；不自动成为独立常驻服务，本任务不改根 pyproject/lock。
- 已使用公开 Deep Agents/LangChain Tools 文档核对 ToolRuntime 隐藏可信上下文的设计依据。
- Contracts owner 已给出 `SW-CONTRACTS-P1-CANDIDATE.1`：最小 `ResultInterpretationPolicy`，不采用 ResultCondition AST。
- main-brain 已确认按该方向收口；精确 release 只指当前 resolver/version guard 结果，不允许冻结旧 release 继续。
- 已创建 3 个 PROVISIONAL fixture 文件，覆盖 9 个合成调用/结果场景和 2 个非法策略样例。
- 现有 Python 3.6.8 已完成 JSON 语法和 stdlib 不变量检查；missing/null/严格类型检查通过，未安装/升级 Python 或依赖。
- 已核对 main 中 A2UI 最新交付使用 `successPolicyRef`、拒绝旧 `businessSuccessConditionRef` 并分离四类事实。
- 已合入实现放行 commit `3a48d4b106db8f382c3c96bbc8992f328b81e259`。
- 已完整读取 `implementation-release-01.md`，SHA256=`c14eb61371562bf512b393ab347c80d2c4e3be082e4a7e838dc13e2a0f9743a4`。
- 批准子集：authored Ability definition、named policy publication metadata、adapter-operation binding validation 与端口。
- 明确不实现结果解释器、业务调用/重试/幂等、credential resolution、PostgreSQL 或部署。
- TDD Task 1：先观察 `ModuleNotFoundError: capability_registry`，再实现 immutable models、ports 与 happy path，1/1 GREEN。
- TDD Task 2：15 个 boundary 断言先失败，再实现字段、模型/服务端分离、Pointer/target 冲突门禁，10/10 GREEN。
- TDD Task 3：operation 缺失、input path 与 credential slot 不支持三例先失败，再实现 catalog 兼容校验，13/13 GREEN。
- 边界 review 新增 2 个畸形 JSON RED 用例；混合类型顶层 key 与非标量 binding source 现均失败关闭，15/15 GREEN。
- Contracts owner 已确认最终薄包 import API，但稳定主干 SHA 尚待其独立 review、push 与集成；本线程未读取其脏 worktree。
- 所有测试均使用 `/bin/python3.11` 和标准库；未安装依赖、未调用外部服务。

## 已移除的活动冲突

- Runtime 语言“待定”改为 Python + Deep Agents SDK + LangGraph。
- 移除 Runtime 对业务能力调用的通用自动重试与平台业务幂等承诺。
- 增加 PRT/ONLINE 分库、userId 灰度、禁止跨环境读取。
- 增加执行/continue/Action 入口的轻量版本失配 reset 门禁。
- 移除 ANY/ALL、NOT_EQUALS 和 ResultConditionRef 候选；统一 `resultInterpretationPolicies[]`、`defaultSuccessPolicyRef` 与 A2UI `successPolicyRef`。
- `MISSING` 永不匹配且报告 PATH_MISSING；`FOUND(null)` 与缺失分离；JSON primitive 不做隐式类型转换。
- 分离 output schema validity、policy match、Action call 和 A2UI interaction completion。
- 明确 Runtime 是唯一解释器；Registry/A2UI 不实现第二套解释器。

## 本线程所有权

- `openspec/changes/oss-capability-registry/`
- `services/capability-registry/`（Phase 1 计划预留）

不修改共享 contracts、根依赖、其他任务目录和其他 checkpoint。不部署、不配 secret、不调用真实外部写。

## 首个可执行切片

- 修订本任务 OpenSpec 并向 main-brain 回传基线、冲突、范围、切片、依赖。
- 创建 PROVISIONAL 合成 ability/call/failure/result fixture。
- 用现有轻量工具验证 JSON 与可信边界。
- 等待 Contracts 稳定 commit 与 main-brain 命名 approved revision 后再实现 Registry Python 模块。

## 真实依赖

- contracts：TrustedContext、Environment、ReleaseRef、resolver/version guard、AuthorizationDecision、CredentialRef、approved ResultInterpretationPolicy、错误包络。
- Runtime：统一 execute_ability Tool、ToolRuntime 注入、一次 adapter 调用和唯一成功解释器。
- A2UI：当前解析并通过 version guard 的精确 release 上选择 successPolicyRef，独立 completeInteractionOnSuccess；不新增解释器或 ResultConditionRef。

## Next Executable Action

等待 Contracts 薄包稳定 SHA；随后先写 `SharedResultPolicySetValidator` 失败测试，再实现仅做异常 issue 映射的 adapter。

## 交付记录

- 2026-09-06 首版设计 worker：`14649a9a7454565b17fa1c141594d52b9b24bd35`。
- 2026-09-06 首版设计集成 main：`c858766c90d9dba472c2600bf0694aa6423e0a5c`。
- 本轮已向 main-brain 发送 .1 初步回执，随后读取 PY-01 并整体升级为 SW-P1-20260907.2。
- 本轮内容 worker commit：`a661f2c78055b20dda91fc74ebd61cc46e6e6177`。
- 本轮内容集成 main：`a661f2c78055b20dda91fc74ebd61cc46e6e6177`（fast-forward）。
- ResultInterpretationPolicy consumer 内容 commit：`6883610b70e6a8502b45084b953bb1de05a83558`。
- 同步最新 main 后 worker/main：`57d11fcfee3481512d444a51fee0db3280357789`（fast-forward 集成）。
- fixture 输出：9 cases、2 rejected policies；missing/null/strict JSON type 检查通过。
- 设计/共享契约仍待 named approved revision；Runtime 仍 NO READY。
