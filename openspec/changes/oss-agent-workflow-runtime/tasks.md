# Agent/Workflow Runtime Phase 1 任务

## 状态

- Baseline：SW-P1-20260907.2
- Runtime：NO READY
- 当前批次：Python/SDK 隔离环境与首批 Tool/A2UI 探针完成；PostgreSQL、并行、retry/stop/restart 仍未协调或实现

## 1. ALIGN

- [x] 核对专属 worker worktree、branch、status 与 worktree list。
- [x] fetch origin 并持续 merge 最新 origin/main；当前已消费 `28dde023e323c4fa4f9f509b9f6e3954bc669b7a`。
- [x] 阅读仓库 AGENTS.md、Phase 1 baseline.md 与 plan.md。
- [x] 撤销 TypeScript、Runtime 业务幂等、通用 retry/recovery、旧版本冻结续跑和第二 scheduler 主张。
- [x] 调研 Deep Agents/LangGraph/PostgreSQL checkpointer 当前官方 API、版本与 MIT 许可证。
- [x] 核对服务器 Python 与现有镜像，确认默认解释器为 platform-python 3.6.8。
- [x] 完成 PY-01 RPM/alternatives/系统工具与服务引用审计，并回传精确事务和恢复方案。
- [x] 修订本 change 的 proposal/design/spec/regression/readiness/checkpoint。
- [x] main-brain 以 `SW-P1-SUBSET-01` 批准 use_skill/trusted-context 闭包用于本实验；wire revision 仍为 `SW-CONTRACTS-P1-CANDIDATE.1`，其余 bundle 仍 provisional。

## 2. RED：先写实验行为测试

- [x] 创建 experiments/runtime-phase1/ 的 Python 3.11+ 隔离元数据与 README。
- [x] 先写 use_skill、真实 Skill fixture bytes 与 content/artifact 分离测试。
- [x] 先写 Tool schema 不暴露 userId/environment/versionId 的失败测试，并经真实 ToolNode 验证 resolver 未被调用。
- [x] 先写 DISPLAY_ONLY 不 interrupt、INTERACTIVE 必须 interrupt 的失败测试。
- [x] 先写 runId/nodeId/application/version/tool-call identity 绑定且不碰撞的 interrupt payload 的失败测试；PostgreSQL resume 仍待后续。
- [x] 先写 Deep Agents 默认隐式文件/子代理 Tool 暴露的失败测试。
- [x] 先写 Anthropic provider wire strict schema 与 artifact 不出站的失败测试。
- [x] 先写 `SW-P1-SUBSET-01` key/result shape 偏差的失败测试。
- [ ] 先写 A 等待、B1→B2 独立推进、join 等待的失败测试。
- [ ] 先写仅 A2UI owning node retry 的失败测试。
- [ ] 先写 stop 不可 resume 与 restart 全新状态的失败测试。
- [x] 已完成项目对应有效 RED→GREEN；依赖/import/network 错误未计为 RED。

## 3. GREEN：最小 SDK 映射

- [x] 用显式 scripted model 创建 Deep Agent，不使用真实 key 或默认模型。
- [x] 用公开 Tool/ToolRuntime/context_schema/HarnessProfile extension point 实现首批最小适配。
- [x] 关闭默认 `ls/read/write/edit/delete/glob/grep/task/execute` 模型可见入口，仅暴露 Runtime-owned Tool。
- [x] 用离线 Anthropic MockTransport 证明 strict provider schema 且 artifact/evidenceRef 未序列化出站。
- [x] 直接消费主干 `skillweave_contracts` 严格适配，对齐 `SW-P1-SUBSET-01` 的 use_skill/trusted-context 定义并复用 15 个共享 fixture；Pydantic 只承担 Tool argument/provider schema 边界。
- [ ] 用 LangGraph StateGraph 表达 sequence/condition/parallel，不实现第二 scheduler。
- [ ] 用 AsyncPostgresSaver 替代所有内存/SQLite checkpointer。
- [ ] 只为 A2UI render/Action 配置 scoped retry。
- [x] 首批 15 个 Tool/A2UI/SDK 用例通过并保留 RED/GREEN 证据；其余行为未开始。

## 4. PostgreSQL 与双进程门禁

- [x] 设计不替换默认解释器的并行 Python 3.11 方案：官方 RPM 事务仅新增 7 个 Python 相关包。
- [x] main-brain 协调后安装并验证 Python 3.11.13；默认 platform-python 3.6.8、DNF 与 tuned 均保持正常。
- [x] 创建 admin-owned task venv 并解析/import Deep Agents、LangGraph 与 AsyncPostgresSaver。
- [ ] main-brain 协调临时 PostgreSQL；不得使用或修改现有 MySQL。
- [ ] 验证 process A interrupt 后 process B 查询并合法 resume。
- [ ] 验证并发 invoke、process kill、pending writes 和 node replay 行为。
- [ ] 验证 A 等待时 B1→B2；若 SDK 原生不支持，提交最小 reproducer，不自建替代引擎。

## 5. 依赖与交付

- [x] 接入 main-brain 批准的 `SW-P1-SUBSET-01` use_skill/trusted-context 定义；未批准的 bundle 部分仍不使用。
- [x] 对接真实 Skill package bytes 与 A2UI owner fixture；execute_ability fixture 待后续。
- [x] 更新 regression.md 的 Python/SDK/Tool/provider-wire 真实命令、版本、输出和字段断言。
- [x] 生成实验 `requirements.lock`；根依赖锁仍由 main-brain 单一所有。
- [ ] 保持 readiness.md 为 NO READY，直到 PG、双进程和全部目标行为有证据。
- [ ] push worker，并通过任务独占 integration worktree 合入 origin/main。
