# Agent/Workflow Runtime Phase 1 提案

## 状态与权威

- Phase 1 基线：SW-P1-20260907.2
- 当前已合入主干：`28dde023e323c4fa4f9f509b9f6e3954bc669b7a`
- 工程实现批准子集：`SW-P1-SUBSET-01`；wire revision 仍为 `SW-CONTRACTS-P1-CANDIDATE.1`
- 模块设计状态：BASELINE_ALIGNED / EXPERIMENTAL
- Runtime 准出：NO READY
- 当前授权：在 experiments/runtime-phase1/ 做隔离可行性 spike；services/runtime/ 仅预留后续实现
- 共享契约所有者：oss-platform-contracts；本任务只消费已批准子集，不扩写共享 wire

## 目标

验证最小框架执行脊柱能否由 Python Deep Agents SDK 与 LangGraph 原生能力完成：

Deep Agents → use_skill → execute_ability / render_application → DISPLAY_ONLY 或 INTERACTIVE → 节点绑定续跑 → Finalizer / 最终结果。

该 spike 使用主干中项目自有的 Skill/A2UI fixture、合成 resolver、scripted model，以及不触网的 Anthropic MockTransport。它不需要真实模型 key，不包含真实业务写操作，也不构成产品 Runtime。

## 已撤销的旧主张

以下内容不再是活跃方案：

- TypeScript/LangGraphJS 作为 Runtime 候选或主选；Phase 1 已确定 Python。
- Runtime 自建第二套 durable Workflow scheduler、通用租约/fencing 引擎或跨系统 exactly-once 语义。
- Workflow/Runtime 负责业务调用幂等、补偿、重放或 fresh restart 前的旧结果核对。
- 通用 Skill 模型、脚本、非 A2UI Tool 失败自动 retry/recovery。
- 运行期间冻结旧资产 revision 并继续；现改为入口处轻量版本比较，不匹配即阻断并提示显式 reset。
- Skill 编译成固定业务子图，或要求 Skill 输出 Workflow 专用路由字段。
- presentation 出现即暂停、Action 成功即完成交互、Finalizer 可越过交互或改写业务事实。
- 用 thread_id 推断并行线程、分布式锁或 A 等待时 B1→B2 会自然推进。

## 固定边界

- Python + Deep Agents SDK + LangGraph；不 fork SDK，不静默自研替代引擎。
- PostgreSQL-only；不提供 SQLite、MySQL 或 InMemorySaver fallback。
- 所有 Skill 使用统一进入 use_skill；Workflow 节点不得直接读取 Skill body/resource。
- Ability 与 Application 通过 Tool 边界调用；trusted userId、环境与凭据由后端 context 注入，不暴露给模型选择。
- PRT 只读 PRT 当前版本；ONLINE 只读 ONLINE stable 或 ONLINE gray candidate，gray 维度仅 userId。
- Skill 是 Agent 执行的指令/资源包，不是固定子图。Workflow 只编排 Skill 节点、条件、序列与并行关系。
- 仅 A2UI render 或 Action 失败/结果不满足配置成功条件可重试 owning node。
- stop 不可 resume；restart 创建全新 run，不继承旧状态或核对旧业务结果。
- 调用 API 后端负责业务幂等与业务 retry；Runtime 仅可处理控制请求去重。

## 首批切片与后续

已完成的首批切片：

1. Python 3.11.13 与 task-owned venv 安装/健康复核；依赖 resolver、import、pip check 与实验 lock。
2. `SW-P1-SUBSET-01` 的 use_skill/trusted-context 严格 Pydantic 适配，并复用 15 个 shared fixture。
3. scripted Deep Agent、真实 Skill package bytes、strict Tool schema、spoof 拒绝与 content/artifact 分离。
4. Deep Agents 默认文件/shell/subagent Tool 暴露审计及 Harness Profile 收口。
5. 离线 Anthropic provider serializer 证据，以及 DISPLAY_ONLY/INTERACTIVE interrupt 小切片。

下一批仍需先写 RED：A 等待时 B1→B2 独立推进、A2UI-only retry、stop/fresh restart。临时 PostgreSQL 获批后再补 AsyncPostgresSaver 与双进程合法 resume；没有这些证据始终保持 NO READY。

## 版本与许可证候选

截至 2026-09-07 的官方公开信息：

| 包 | 公开版本 | Python | 许可证 | 结论 |
| --- | --- | --- | --- | --- |
| deepagents | 0.7.13，Beta | >=3.11,<4.0 | MIT | 已安装/import/运行首批探针 |
| langgraph | 1.2.11 | >=3.10 | MIT | 1.2.10 与 LangChain 1.4.0 冲突后解析所得版本 |
| langgraph-checkpoint-postgres | 3.1.2 | >=3.10 | MIT | `AsyncPostgresSaver` import 通过，PG 尚未运行 |
| psycopg-binary | 3.3.5 | >=3.10 | LGPL-3.0-only metadata | 仅实验 venv；正式分发/notice 仍需评审 |

版本组合已在 task-owned Python 3.11.13 venv 解析、import、`pip check`，并冻结为 59 项实验 `requirements.lock`。它不修改 main-brain 所有的根 lock，也不代表生产依赖获批。

## 当前环境结论

PY-01 已由本任务作为唯一 host Python 执行者完成：DNF transaction 9 从官方仓库新增 Python 3.11.13、pip 与依赖共 7 包（无 update/remove）。默认 `python3` 仍为 platform-python 3.6.8；DNF 4.7.0 与 tuned active 已复核。

admin-owned venv `/home/admin/OpenSource/.venvs/skillweave-runtime-p1` 已安装并验证候选依赖。首次固定 LangGraph 1.2.10 被 resolver 因 LangChain 1.4.0 需要 >=1.2.11 而拒绝；改为 1.2.11 后通过。首次 `AsyncPostgresSaver` import 因没有 libpq implementation 失败，加入 venv-only `psycopg-binary==3.3.5` 后通过；未修改系统 libpq、现有 MySQL、公开端口或服务。

当前未启动 PostgreSQL 或公开服务。剩余环境门禁是 main-brain 协调的临时 PostgreSQL/双进程窗口与 `psycopg-binary` LGPL 分发评审，而不是 Python 可用性。

## 依赖输入

| 依赖 | 本任务需要的最小输入 | 当前状态 |
| --- | --- | --- |
| packages/contracts | `SW-P1-SUBSET-01` 的 trusted/use_skill 闭包 | 共享薄包已由 `main` 集成；Runtime 直接消费 `.from_mapping()` / `.to_mapping()` 与 15 个相关 fixture |
| Skill registry | use_skill Tool 的授权读取与中性 Skill fixture | 真实 `evidence-first-brief` bytes/digest 已消费；Registry runtime port 尚未接入 |
| Ability registry | execute_ability Tool 的 typed request/result 与配置成功解释 | 未接入；业务幂等仍由 API 后端 |
| A2UI registry | render_application Tool、DISPLAY_ONLY/INTERACTIVE、Action success/completion | owner fixture 已用于 mode/interrupt 探针；full Action wire 未批准 |
| Workflow registry | sequence/condition/parallel graph 与 nodeId 语义 | node-bound interrupt 已使用；独立并行推进待联合验证 |
| 执行资源 | Python 3.11、候选依赖、临时 PostgreSQL、两个进程 | Python/SDK 已满足；PG 与双进程仍需协调 |

## Phase 1 验收

- 旧冲突在 proposal/design/spec/tasks/regression/readiness 中全部移除。
- scripted model 的所有 Skill 使用都可观测到 use_skill Tool call。
- model-visible Tool schema 不允许提供 userId、environment 或 credential 参数。
- DISPLAY_ONLY 与 INTERACTIVE 行为由同一配置字段决定。
- resume 不能靠普通 chat 或仅 thread_id 猜测，必须匹配 node/interaction/version。
- A 等待期间 B1→B2 的真实 SDK 行为有复现；若不支持则提交最小失败证据，不自建第二引擎。
- PostgreSQL checkpointer 和双进程证据存在前，Runtime 始终 NO READY。

## 官方来源

- https://docs.langchain.com/oss/python/deepagents/overview
- https://docs.langchain.com/oss/python/deepagents/customization
- https://docs.langchain.com/oss/python/deepagents/backends
- https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/pyproject.toml
- https://github.com/langchain-ai/deepagents/blob/main/LICENSE
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/pyproject.toml
- https://pypi.org/project/langgraph-checkpoint-postgres/3.1.2/
