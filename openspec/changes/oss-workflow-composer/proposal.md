# Skill Workflow 编排平台 Phase 1 对齐提案

## 状态

- 统一基线：`SW-P1-20260907.2` + `ENG-01`
- 工程决策：Workflow registry 后端按 ENG-01 规划为可导入 Python 模块；不自动启动独立常驻服务，根依赖仍由 main-brain 单一协调。
- 基线集成 SHA：`c168f2c3b7f86cb0bd5e2bec48caf4ec1de1df7e`
- 设计：`PROPOSED`
- 实现：等待 main-brain 对共享契约实际差异审查后放行
- Runtime：`NO READY`
- PY-01：必要时替换/升级系统 Python 已获授权，但仅 Runtime 可在 main-brain 协调下执行；本任务不改系统 Python，也不以授权缺失为 blocker。

本 change 合入 `main` 只表示 Phase 1 图契约需求和验证样例可供审查，不表示共享契约已冻结、服务已实现或 LangGraph 运行语义已经证明。

## Why

M 侧需要发布可被 Python + LangGraph Runtime 编译执行的多 Skill Workflow。首版必须覆盖顺序、条件和并行，同时保持 Skill 为可复用的 AI 指令/资源包，不把每个 Skill 固化为业务子图，也不要求 Skill 输出专用路由字段。

## 旧方案冲突清理

| 旧提案 | Phase 1 修订 |
| --- | --- |
| 只允许 `START -> SKILL... -> END` 串行链 | 支持顺序、AI 条件选择、非嵌套并行和显式 join |
| 相邻 Skill 必须完全相同 `schemaRef`，否则新增 Adapter Skill | 下游默认读取全部相关、已实际执行的前序/祖先节点最终结果和真实状态；Skill 无需 Workflow 适配，精确上下文契约由 contracts/Runtime 审查 |
| 固定 Skill release 并按旧版本继续执行 | 由可信 `environment + userId` 解析有效配置；入口发现版本失配即阻断并提示重置，不冻结旧配置继续 |
| Runtime 语言和图协议仍待选择 | Runtime 固定为 Python + Deep Agents SDK + LangGraph；具体版本/API 仍需 Runtime 实证 |
| 只定义线性 manifest 和 ordinal | 发布物必须保留节点、候选边、并行区域、join 和失败容忍语义 |
| 泛化 Runtime 重试由后续决定 | 首版仅允许 A2UI 渲染或 Action 失败的 owning node 重试；其他 Skill/Tool 失败无通用节点重试 |
| 未定义 AI 不确定和 Finalizer 边界 | AI 只能从配置候选选择；不确定时同节点显示 A2UI 选择卡；Finalizer 不得改写事实或绕过交互 |

## Phase 1 范围

- 编辑和发布有限无环图：sequence、AI decision condition、parallel split、explicit join、Finalizer。
- AI decision 节点从静态配置的候选中选择一个目标；Skills 不提供路由专用字段。
- AI 无法做出语义选择时，该 decision 节点展示配置好的 INTERACTIVE A2UI 选择卡，等待一次 node-bound 用户选择并直接路由，不再交给 AI 重选。
- 并行区域首版不嵌套。A 分支等待交互时，独立 B 分支必须继续 B1、B2，直到对应 join；join 仍等待 A。
- 节点成功、真实 `SKIPPED`、或配置为 allow-skip 的节点保持真实 `FAILED` 后可满足后继/join；required 节点失败阻断。
- Skill、decision 和 Finalizer 默认获得全部相关、已实际执行祖先节点的最终结果和真实状态。A→B→C 时 C 必须同时获得 A、B；join 后只汇总真实执行分支，不为未选 condition candidate 虚构结果。
- 发布图记录逻辑 Skill/Application 引用和图语义；共享 resolver 依据可信 environment/userId 解析实际版本。
- Contracts 候选 `SW-CONTRACTS-P1-CANDIDATE.1` 将公共 Skill identity 定义为 exact `skillKey`；Composer/Runtime 不得拆 `skill:` 前缀猜测映射。该候选仍待 main-brain 纳入最终 shared revision。
- 提供非规范图样例和 validation cases；共享 schema 字段名、版本和封装由 contracts 单一所有。

## 明确不做

- 循环、递归、嵌套并行、子流程、动态生成拓扑和多 Agent swarm。
- 自研调度器、第二套 checkpoint/interrupt 引擎或修改 LangGraph/Deep Agents 源码。
- 每 Skill 固定业务子图、强制路由字段、隐式数据转换或自动 Adapter Skill。
- 通用 Skill/model/script/non-A2UI Tool retry、Workflow 业务补偿、跨 run 对账或业务幂等。
- 允许模型提供 userId、environment、凭证或越过 `use_skill` / Tool 边界。
- 未经 main-brain 共享契约审查即实现 `services/workflow-registry/`。

## 候选方案

### A. 受限 DAG + 显式 decision/split/join（推荐）

发布图保留稳定 node key 和有向边；decision 明确候选集合，parallel split 与 join 成对且首版禁止嵌套。它能表达已确认的三类拓扑，并给 Runtime 足够信息验证独立分支进度和 join 门禁。

### B. 任意 DAG + Runtime 推断 join

作者自由连边、Runtime 根据拓扑猜测并发区和失败传播。灵活但难以静态验证 A 等待/B 继续、join 归属和 required failure，首版不采用。

### C. 完整 Workflow DSL 或 workflow-as-code

表达力强，但会把循环、嵌套、脚本和运行细节带入首阶段，也容易形成第二套调度抽象。本轮仅参考公开图概念，不声明兼容。

## 已确认的图执行语义

1. Sequence：节点完成为可传播终态后才激活后继。
2. Decision：AI 读取全部相关、已执行祖先节点的最终结果/状态，从配置候选中选一个；语义不确定才进入 A2UI 用户选择。技术失败必须保持失败，不伪装成不确定。
3. Parallel：split 激活多个独立分支；一个分支 `WAITING_INTERACTION` 不冻结其他分支。
4. Join：等待所有成员分支达到可 join 终态；waiting 继续等待，allow-skip failure/实际 skip 可 join，required failure 阻断。
5. Finalizer：读取本次 run 全部相关、已执行祖先节点的真实结果/状态并生成最终表达；不虚构未选分支结果，不能改变状态、补业务调用、绕过交互或在 stop 后运行。
6. Retry：仅 A2UI 渲染/Action 失败满足配置条件时重试 owning node，并保留已完成前驱和独立分支；整图 restart 是无继承的新 run。

## 所有权与真实依赖

| 所有者 | 本任务需要 | 本任务提供 |
| --- | --- | --- |
| platform-contracts | graph identity/version、exact `skillKey`/显式 typed mapping、可信 context、resolver、事件/interaction/result refs、control request dedupe | sequence/decision/parallel/join/context 的消费者约束和样例 |
| skill-registry | `use_skill` 接受共享契约的 exact `skillKey` 和可发现元数据 | 无 Workflow 专用 Skill 输出/适配要求，不做前缀猜测 |
| a2ui-registry | decision selection Application、DISPLAY_ONLY/INTERACTIVE、Action success/completion 语义 | node-bound 选择和 A2UI-only retry 的引用需求 |
| Runtime | LangGraph 编译映射、祖先 context 累积、状态传播、interrupt/checkpoint、独立分支进度实证 | 发布图候选、context cases、join truth table、失败/等待边界 |
| digital employee | node-bound 输入/Action 和 reset UX | 可浏览/启动的 Workflow identity，不暴露草稿和调度内部 |

## 首个可执行切片

当前可独立完成：修订本 change，增加一份有效 parallel/decision 图候选，以及 A→B→C 和 join 后真实执行分支 context cases，用 Python 标准库做 JSON 结构/断言检查。`services/workflow-registry/` 仅预留所有权，不在共享 graph revision 获批前写实现。

## 公开参考

- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)：nodes、edges、conditional routing、parallel super-step 和 compile checks。
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)：持久化 interrupt、node restart、multiple interrupts 与 resume 约束。
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)：Checkpointer、Store 和 PostgreSQL 持久化边界。
- [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)：Runtime SDK 入口；本任务不锁定依赖版本。
