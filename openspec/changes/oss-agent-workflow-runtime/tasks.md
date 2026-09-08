# Agent/Workflow Runtime Phase 1 任务

## 状态

- Baseline：SW-P1-20260907.2
- Runtime：NO READY
- 当前批次：SW-P1-ENGINE-FIRST-01，仅继续 Python Deep Agent/Workflow 引擎；PG-P1-01 有界功能探针已完成，其他六域暂停

## 1. ALIGN

- [x] 核对专属 worker worktree、branch、status 与 worktree list。
- [x] fetch origin 并持续 merge 最新 origin/main；当前已消费 `28dde023e323c4fa4f9f509b9f6e3954bc669b7a`。
- [x] 阅读仓库 AGENTS.md、Phase 1 baseline.md 与 plan.md。
- [x] 消费 `SW-P1-ENGINE-FIRST-01`；不等待 M/BFF/A2UI Host 或其他 registry UI，只用已集成契约/模块与引擎独占合成 fixture/port。
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
- [x] 先写模型原始 args 携带保留 `runtime` 字段的失败测试，并证明 Skill/Application resolver 均未调用。
- [x] 先写 DISPLAY_ONLY 不 interrupt、INTERACTIVE 必须 interrupt 的失败测试。
- [x] 先写 runId/nodeId/application/version/tool-call identity 绑定且不碰撞的 interrupt payload 的失败测试；PostgreSQL resume 仍待后续。
- [x] 先写 Deep Agents 默认隐式文件/子代理 Tool 暴露的失败测试。
- [x] 先写 Anthropic provider wire strict schema 与 artifact 不出站的失败测试。
- [x] 先写 `SW-P1-SUBSET-01` key/result shape 偏差的失败测试。
- [x] 先写 A 等待、B1→B2 独立推进、join 等待的失败测试；LangGraph 1.2.11 实际只返回 trace=`[B1]`，预期 `[B1,B2]`，保留为显式 RED reproducer。
- [ ] 先写仅 A2UI owning node retry 的失败测试。
- [ ] 先写 stop 不可 resume 与 restart 全新状态的失败测试。
- [x] 已完成项目对应有效 RED→GREEN；依赖/import/network 错误未计为 RED。

## 3. GREEN：最小 SDK 映射

- [x] 用显式 scripted model 创建 Deep Agent，不使用真实 key 或默认模型。
- [x] 用公开 Tool/ToolRuntime/context_schema/HarnessProfile extension point 实现首批最小适配。
- [x] 用公开 `wrap_tool_call` / middleware 扩展点在 ToolRuntime 注入前校验闭合模型参数，不修改第三方源码。
- [x] 同步/异步 Deep Agent 准入复用同一闭合校验；异步合法、恶意与 `Command` 透传行为均有回归。
- [x] 关闭默认 `ls/read/write/edit/delete/glob/grep/task/execute` 模型可见入口，仅暴露 Runtime-owned Tool。
- [x] 用离线 Anthropic MockTransport 证明 strict provider schema 且 artifact/evidenceRef 未序列化出站。
- [x] 直接消费主干 `skillweave_contracts` 严格适配，对齐 `SW-P1-SUBSET-01` 的 use_skill/trusted-context 定义并复用 15 个共享 fixture；Pydantic 只承担 Tool argument/provider schema 边界。
- [x] 隔离证明每个 Workflow 分支一个原生 compiled subgraph 的结构候选：A interrupt 时 B 子图完成 B1→B2，父 join 未运行；不拆 Skill 内部步骤、不实现第二 scheduler。
- [x] 每分支 compiled subgraph 候选已完成单一 synthetic PG 双进程 interrupt/resume/join 验证；任意 DAG/嵌套/冲突仍未验收，平铺父图 RED 继续保留。
- [x] PG-P1-01 双进程探针使用 AsyncPostgresSaver；结构单测仍保留 MemorySaver，产品迁移未开始。
- [ ] 只为 A2UI render/Action 配置 scoped retry。
- [x] 当前 31 个 Tool/A2UI/SDK/参数准入/engine spine/credential-safety/分支子图候选用例通过并保留 RED/GREEN 证据；其余行为未开始。

## 4. PostgreSQL 与双进程门禁

- [x] 设计不替换默认解释器的并行 Python 3.11 方案：官方 RPM 事务仅新增 7 个 Python 相关包。
- [x] main-brain 协调后安装并验证 Python 3.11.13；默认 platform-python 3.6.8、DNF 与 tuned 均保持正常。
- [x] 创建 admin-owned task venv 并解析/import Deep Agents、LangGraph 与 AsyncPostgresSaver。
- [x] PG-P1-01 socket-only/资源限额窗口已批准；无 TCP publish、无 trust auth；OpenSource 不使用 MySQL，yihaidao 专属资源由 main-brain 独占清理。
- [x] 原 Docker Hub 固定 digest 两次受镜像代理阻塞；经用户批准改用同一 amd64 manifest digest 的 ECR mirror，首次 pull 成功。
- [x] process A 持久化 interrupt 后退出；独立 process B 查询同一 thread 并合法 resume。
- [x] 本窗口只验证 setup、A退出、B读回/合法 resume 与并行 join；未扩 generic crash recovery、model replay、业务 kill/reconciliation。
- [x] 验证 A 等待时 B1→B2、resume 后 join；未实现替代引擎或第二 scheduler。
- [x] 临时 container/volume/private socket+secret dir/image 均已精确清理；不宣称 secure erase。
- [ ] 新 libpq SCRAM verifier + NOLOGIN bootstrap 与失败禁用/UNSAFE_UNKNOWN 逻辑仅通过 3 个 synthetic sentinel 单元负例，尚未现场 PG 重跑。

## 5. 依赖与交付

- [x] 接入 main-brain 批准的 `SW-P1-SUBSET-01` use_skill/trusted-context 定义；未批准的 bundle 部分仍不使用。
- [x] 对接真实 Skill package bytes、A2UI owner fixture 与明确标记 provisional/synthetic 的 execute_ability fixture；未提升为共享 Capability 契约。
- [x] 更新 regression.md 的 Python/SDK/Tool/provider-wire 真实命令、版本、输出和字段断言。
- [x] 生成实验 `requirements.lock`；根依赖锁仍由 main-brain 单一所有。
- [ ] 保持 readiness.md 为 NO READY，直到 PG、双进程和全部目标行为有证据。
- [ ] push worker，并通过任务独占 integration worktree 合入 origin/main。

## AF-RUNTIME-02 — 2026-09-08

- [x] 读取 605720f 中的 runtime-action-release-02.md，独占新增 services/agent-workflow-runtime/。
- [x] Action 服务：可信身份/完整版本闭包/待交互准入、真实 executor 结果与 reviewed Policy 判定、保存的完成引用。
- [x] 原生 interrupt ID 映射与 Tool 恢复核验；同步/异步 Finalizer 使用交互门禁。
- [x] 控制 requestId 历史与不确定恢复状态保留；无业务 exactly-once 或自动重试声明。
- [x] 24 个新服务/真实 SDK 离线用例通过；原有 31 个实验回归通过。
- [ ] 主控审查稳定 worker 提交后才释放 server main 集成；GitHub 同步归 main-brain。

## AF-RUNTIME-03 — 2026-09-08

- [x] 采用 87e17e7 的 runtime-postgres-release-03.md；源码放行与 PG 窗口分离。
- [x] PostgreSQL 两表 owner/environment/run/node/card/request 唯一键、schemaVersion=1 JSON 严格序列化。
- [x] 独立短事务 save；admission/continuation 专属 session advisory lock；失连不重连续写。
- [x] 所有 get 显式 owner；run 新控制在途/未确认门禁经主控增量批准。
- [x] 修复主控 WIP 审查发现的伪 COMPLETED 缺少成功 Action 引用漏洞；保留正常中间保存态。
- [x] 38 个离线服务/SDK/存储协议与损坏记录测试 GREEN；实验 37 个用例 GREEN（既有 31 + 窗口故障 6）。
- [x] 准备 9 个 opt-in PG 独立进程用例；离线全部 SKIPPED，不计运行态通过。
- [x] bootstrap 显式支持 connection_limit=8，保留 SCRAM/NOLOGIN 安全测试。
- [x] 提供受控 PG 启动/资源监控/精确清理脚本；仅 --help 已执行。
- [ ] 主控审查脚本并单独释放 PG 窗口。
- [ ] 运行 PG/跨进程/失连/真实同步 PostgresSaver 验证并记录连接观测峰值。
- [ ] 主控审查稳定源码并放行 server main 集成；GitHub 同步由主控执行。

- AF-RUNTIME-03 窗口审查补充：显式禁用 LangSmith/LangChain tracing；独有 window marker + UID/group/session 验证后仅清理本脚本进程组；无论 parent 退出、killpg 竞态或双超时，finally 都执行日志检查和精确资源清理。模拟 PG-owned socket 权限失败已验证仅针对 PRIVATE/socket 的 sudo 删除，以及残留显式失败。docker logs 在清理前仅做本次两个 secret 的内存 substring 检查，只输出 PASS/FAIL。6 个离线故障测试通过，PG 仍未运行。
