# Skill Workflow Composer Phase 1 设计

## 1. 状态与权威

- 统一基线：`SW-P1-20260907.2`
- 设计状态：`PROPOSED`
- Runtime 状态：`NO READY`
- 权威边界：本 change 只提供 workflow-registry 消费者需求、图候选和 validation examples；共享 contract 字段、版本和包由 `oss-platform-contracts` 单一所有。
- PY-01：系统 Python 必要变更已获授权，但主机兼容评估、可恢复方案和唯一执行均归 Runtime/main-brain；Composer 不并发执行主机变更。

## 2. 目标与非目标

目标是发布可静态验证的 sequence、condition、parallel 图，让 Runtime 能用 Python + LangGraph 编译并证明等待、独立分支推进、join、失败阻断和 A2UI-only retry。非目标是实现调度器、冻结共享 API、引入循环/嵌套语义或把 Skill 变成固定业务节点。

## 3. 逻辑组件

| 组件 | 职责 | 不负责 |
| --- | --- | --- |
| Workflow Editor | 编辑受限图、配置候选/并行区域/失败要求、展示校验结果 | 运行调度、版本解析、业务调用 |
| Draft Application | 草稿 revision 和乐观并发 | 共享发布/gray 规则 |
| Graph Validator | 结构、可达性、decision、parallel/join、引用和边界校验 | 自动修图、运行态恢复 |
| Publication Adapter | 将已通过校验的图提交共享 publication contract | 自建第四套 release/resolver |
| Runtime Graph Consumer | 把已解析发布图映射为 LangGraph，并持久化运行状态 | 由 Composer 实现第二套 scheduler |

## 4. 非规范发布图候选

以下只表达消费者所需语义，字段名和 contractVersion 不具有共享契约权威：

```text
PublishedWorkflowGraph
  workflowRef
  graphRevision
  configurationRefs[]
  nodes[]
    nodeKey
    kind = START | SKILL | AI_DECISION | CONDITION_MERGE | PARALLEL_SPLIT | PARALLEL_JOIN | FINALIZER | END
    skillRef?
    candidates[]?
    selectionApplicationRef?
    failureRequirement = REQUIRED | ALLOW_SKIP
  edges[]
    from
    to
    edgeKind
    routeKey?
    branchKey?
  decisionRegions[]
    decisionNodeKey
    mergeNodeKey
    candidateKeys[]
  parallelRegions[]
    splitNodeKey
    joinNodeKey
    branchKeys[]
    branchExitNodeKeys
```

关键要求：

- Skill 节点引用逻辑 Skill identity，所有执行统一通过 `use_skill`；不得内嵌 Skill body、凭证或运行环境。
- Decision 候选是发布时有限集合，候选必须唯一映射到可达目标。AI 和用户都不能跳到集合外。
- A2UI 选择卡引用已发布 Application 配置；卡片属于 decision 节点 interaction，不要求上游 Skill 改输出。
- `failureRequirement` 是 authoring intent；运行状态必须保持真实 SUCCESS/FAILED/SKIPPED/WAITING，不得改写为成功。
- 发布物不携带 userId 或模型可修改的 environment。Runtime 从可信 ingress context 获取它们并调用共享 resolver。

## 5. 首版静态校验

### 5.1 全局图约束

- 恰好一个 START、一个 FINALIZER、一个 END；所有成功完成路径经 FINALIZER 到 END。
- 图必须有限、无环、全可达；所有非 END 节点至少有一个出边，所有非 START 节点至少有一个入边。
- 禁止子流程、递归、动态生成节点和嵌套 parallel region。
- condition candidate 在进入 parallel JOIN 前必须通过显式 CONDITION_MERGE 汇合；未选 candidate 不构成 join 成员。
- 节点/边 key 唯一，所有引用存在；编辑 layout 不进入发布语义或摘要。

### 5.2 Sequence

- 普通节点只能使用一种路由机制；不得同时配置无条件边和 decision candidates。
- REQUIRED 节点失败时不得激活其普通后继。
- ALLOW_SKIP 节点失败保持 FAILED，但可按已配置后继传播；真实 skip 保持 SKIPPED。等待不是 skip。

### 5.3 AI decision

- 至少两个 candidate；candidate key、展示 label 和 target 均唯一、完整。
- AI 只能从 candidates 返回一个 route key；Skills 无需路由字段。
- 语义无法判断才创建 node-bound INTERACTIVE selection；技术错误返回 FAILED，不展示伪 fallback。
- 用户选择必须命中当前 interaction 和候选集合，直接路由且不再交给 AI 重选。

### 5.4 Parallel 与 join

- 每个 split 必须有唯一对应 join 和不少于两个 branch key。
- 每个 branch 从 split 后第一个节点到 join 前最后一个节点必须可静态归属，首版分支不得交叉或嵌套。
- join 的成员集合必须等于 split 的 branch 集合；缺失、重复、额外成员均拒绝发布。
- join 不以同一次 invoke/super-step 已返回作为语义；它依据每个 branch 的持久化终态判断。

## 6. 执行真值表

| 分支状态 | 独立兄弟分支 | 对应 join |
| --- | --- | --- |
| `RUNNING` | 继续 | 等待 |
| `WAITING_INTERACTION` | 继续运行 B1、B2 等后继 | 等待，不自动 skip |
| `SUCCESS` | 继续 | 该分支满足 |
| `SKIPPED` 且节点允许 skip | 继续 | 该分支满足，保留 SKIPPED |
| `FAILED` 且节点为 ALLOW_SKIP | 继续 | 该分支满足，保留 FAILED |
| `FAILED` 且节点为 REQUIRED | 已运行兄弟不回滚；不再错误扩展该失败分支 | join 阻断并保留原因 |
| `STOPPED` | 所有分支不得接纳新工作 | 不进入 Finalizer |

已确认样例：split 后 A 进入 INTERACTIVE decision 并等待；B1 成功后 B2 必须继续；B2 到 join 后等待 A。A 获得合法用户选择并完成后，join 才可满足。该行为必须由 Runtime spike 实证，不能仅从 LangGraph `thread_id` 或一次 graph invocation 推断。

## 7. 前驱上下文

- Skill 和 decision 默认读取所有直接前驱的最终结果及真实状态，而不是只读前一个 Skill 的 payload。
- final summarization 读取本次 run 的前驱/节点最终结果和状态；中间 Tool 结果按需通过只读 retrieval Tool 获取，不能重放业务调用。
- 不要求 Skill 输出 route、branch 或 Workflow 专用字段；Runtime 通过统一 context envelope 调用 `use_skill`。
- context envelope、结果引用和预算属于 shared contracts/Runtime；本任务只要求 branch/node identity 稳定可关联。

## 8. A2UI、Finalizer 与 retry

- DISPLAY_ONLY Application 呈现后不暂停；INTERACTIVE Application 产生 node-bound interaction 并等待。
- Action 的业务成功和是否完成 interaction 由 A2UI 配置判定；render/Action transport success 不等于 Skill success。
- Decision 选择卡只能在 AI 语义不确定时展示；技术失败不能伪装成用户选择。
- Finalizer 只能基于已保存事实生成最终表达，不能把 FAILED/SKIPPED 改成 SUCCESS，不能绕过未完成 required interaction，也不能在 accepted stop 后执行。
- 节点 retry 入口仅在 A2UI render failure、Action call failure 或 Action result 不满足配置成功条件时存在。
- A2UI retry 保留已完成前驱和独立分支，重入 owning node；其他 Skill/model/script/non-A2UI Tool failure 不提供通用 retry。
- LangGraph interrupt resume 会从 owning node 开头重跑，Runtime 必须隔离 interrupt 前副作用并依赖 control request dedupe；业务副作用幂等仍归被调用 API 后端。

## 9. environment、userId 与版本失配

- PRT 与 ONLINE 使用分离资产数据库。PRT 只解析 PRT current；ONLINE 只解析 ONLINE stable/gray，绝不读取 PRT。
- `userId` 是唯一灰度身份词；trusted context 由后端注入，模型和图定义不能覆盖。
- run 记录用于比较的 Workflow、Skill、Application 等有效版本标识。
- 在执行、continue 或 Action ingress 发现当前有效版本与记录值不一致时，必须在新业务调用前阻断并提示 reset。
- reset 只提示；显式 restart 创建全新 run，不继承旧 context/checkpoint/result/interaction，也不检查旧业务结果。

## 10. 发布、并发与 PostgreSQL

- Draft 保存使用 expected revision 乐观并发；旧 revision 不得覆盖新 revision。
- 发布操作对同一 control request 保持幂等，但不得声称业务 exactly-once。
- Workflow registry 通过 shared publication/resolver contract 持久化环境分离的资产；不得自建独立 gray 或跨环境 fallback。
- PostgreSQL 是唯一关系型持久化；多实例正确性不得依赖进程内锁、缓存或 session affinity。
- 具体表和 API 在 main-brain 批准 shared graph revision 后进入 `services/workflow-registry/` 实现计划。

## 11. LangGraph 映射要求

公开 Graph API 可表达普通边、conditional edges 和同 super-step 的 parallel destination；interrupt/persistence 可保存等待并通过 Command resume。它们是实现候选，不自动证明产品语义。

Runtime feasibility 必须至少证明：

1. 编译发布图时拒绝孤儿节点、环、非法 candidate 和 split/join。
2. A interrupt 后，B1 和 B2 能在 A 未恢复前完成，且 join 等待 A。
3. resume 只命中 node-bound interaction；无效/旧 interaction 被拒绝。
4. allow-skip failure 和 required failure 按真值表传播。
5. A2UI owning-node retry 不重跑已完成前驱或独立分支。
6. accepted stop 后没有新 node/model/Tool/Action/retry/Finalizer。

若标准 LangGraph 调用模型不能满足 A 等待/B 继续，Runtime owner 必须提供最小 reproducer 并向 main-brain 报告；不得由 Composer 增加自研调度器规避。

## 12. 失效边界

- Skill/Application/Workflow 引用解析失败、跨环境读取、未授权或版本不支持：发布或 ingress 失败关闭。
- AI 返回候选外 route：decision FAILED，不选择默认分支。
- AI 技术异常：FAILED，不打开选择卡。
- 用户选择 interaction/node/version 不匹配：拒绝，不触发新业务调用。
- join 配置不完整、嵌套 parallel、循环或不可达：拒绝发布。
- 共享 contract 尚未批准：只交付 requirement fixture，不实现依赖接口。

## 13. 第一阶段文件边界

- 当前拥有并修改：`openspec/changes/oss-workflow-composer/`。
- 已预留但暂不实现：`services/workflow-registry/`。
- 不修改：`packages/contracts/`、Runtime、A2UI registry、Skill registry、数字员工、根 manifests 和其他任务 checkpoint。

## 14. 公开依据

- LangGraph Graph API 说明 multiple outgoing edges 在下一 super-step 并行，conditional edges 可返回一个或多个目标。
- LangGraph Interrupts 说明持久化等待、resume、multiple parallel interrupts，以及 resume 时 owning node 从开头重跑。
- LangGraph Persistence 区分 thread-scoped Checkpointer 与跨 thread Store，并给出 PostgreSQL checkpointer 入口。
- 上述文档不构成版本/API 已安装或 A 等待/B1→B2 已通过的证据；这些仍是 Runtime `NO READY` 门禁。
