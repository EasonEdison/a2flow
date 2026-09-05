# Skill Workflow Composer 设计

## 1. 状态与目标

- 设计状态：`PROPOSED`
- 运行状态：`NO READY`
- 目标：用最小串行链路证明“编辑草稿 -> 服务端校验 -> 不可变发布 -> Runtime 消费”的稳定边界。
- 非目标：通用 DAG、运行态调度、业务流程语义、A2UI 渲染和部署拓扑。

本设计描述逻辑模块和端口，不决定四个 M 平台是独立服务还是同一部署物内的模块。

## 2. 设计原则

1. 编辑模型与执行模型分离：画布布局不能成为 Runtime 契约。
2. 引用不可变发布物：每次执行都能定位到确定的 Workflow 和 Skill release。
3. 前端早反馈，服务端作最终裁决：客户端限制不能替代发布校验。
4. 首版失败关闭：依赖未知、schema 不兼容或协议不支持时不发布、不 fallback。
5. 多实例正确性依赖 PostgreSQL 事务、唯一约束和 compare-and-set，不依赖进程内状态。

## 3. 组件边界

| 组件 | 职责 | 不负责 |
| --- | --- | --- |
| Workflow Editor | 呈现受限画布、选择已发布 Skill、展示校验问题、提交带 revision 的草稿 | 最终校验、发布、运行调度 |
| Draft Application | 创建/读取/保存草稿，实施乐观并发 | Skill 生命周期、Runtime 状态 |
| Graph Validator | 结构、拓扑、依赖、schema 链四层校验 | 自动修图、隐式转换、运行重试 |
| Publication Application | 对指定 revision 重新校验、确定性编译、幂等发布 | 修改已发布 artifact、自动升级依赖 |
| Publication Read Port | 按 release ref 返回不可变 manifest 与摘要 | 创建 Run 或推送运行事件 |
| PostgreSQL Repositories | 草稿、release、依赖快照和幂等记录的持久化 | 使用 MySQL/SQLite fallback |

## 4. 编辑态模型

以下字段是概念契约，命名和协议版本仍由 shared contracts 统一：

```text
WorkflowDraft
  draftId
  workflowKey
  name
  description
  draftRevision
  status = DRAFT
  graph
    nodes[]: nodeId, nodeType(START|SKILL|END), skillReleaseRef?
    edges[]: edgeId, sourceNodeId, targetNodeId
    layout: nodeId -> x,y
```

约束：

- `START` 和 `END` 各一个；Skill 节点 1 至 8 个。
- `START` 入度 0、出度 1；`END` 入度 1、出度 0；每个 Skill 入度和出度均为 1。
- 全部节点从 `START` 可达且最终到达 `END`；禁止环、分支、自环、悬空节点和重复边。
- Skill 节点必须带精确 `skillReleaseRef`；其他节点不得携带。
- `layout` 只服务编辑器，不参与 artifact 摘要或运行语义。

草稿保存只要求请求结构可解析、节点/边数量在资源上限内；允许用户保存尚未连完或依赖尚未选择的草稿。校验和发布返回具体问题，不静默修复。

## 5. 校验流水线

校验在一个明确的 `draftRevision` 上执行，并返回：

```text
ValidationResult
  draftId
  draftRevision
  valid
  issues[]: code, severity(ERROR|WARNING), nodeId?, fieldPath?, message
  resolvedDependencies[]: nodeId, skillReleaseRef, inputSchemaRef, outputSchemaRef
```

四层顺序：

1. 结构：字段、类型、数量、唯一性和引用存在性。
2. 拓扑：单入口、单出口、单链路、全可达、无环。
3. 依赖：Skill release 存在、处于允许执行的发布状态、调用方有权引用。
4. schema 链：首版按规范化 `schemaRef` 完全相等校验相邻输出/输入。

问题 code 必须稳定，message 可本地化。建议首版 code 包含 `GRAPH_CYCLE`、`GRAPH_BRANCH_NOT_SUPPORTED`、`GRAPH_DISCONNECTED`、`SKILL_RELEASE_NOT_PUBLISHED`、`SKILL_RELEASE_UNAVAILABLE`、`STEP_SCHEMA_MISMATCH` 和 `DRAFT_REVISION_CONFLICT`。

## 6. 发布事务

逻辑操作 `PublishWorkflowDraft(draftId, expectedDraftRevision, requestKey)`：

1. 查询幂等记录；若该 key 已成功，返回原 release。
2. 读取草稿并比较 `expectedDraftRevision`；不一致则冲突失败。
3. 在同一 revision 上重新执行全部校验，不接受客户端传入的 `valid=true`。
4. 按唯一拓扑序生成 canonical `steps[]`，去除 layout、展示文案和草稿字段。
5. 计算 canonical artifact 摘要，创建不可变 Workflow release、依赖快照和幂等结果。
6. 在 PostgreSQL 单事务内提交；已提交但响应丢失时，相同 `requestKey` 返回同一 release。

对 Skill registry 的依赖查询无法与本地事务形成分布式原子性。首版依赖 shared contracts 保证 published release 不被原地修改；若存在撤销，发布和 Runtime 启动都必须失败关闭，撤销后已运行实例的处理由 Runtime 与 shared contracts 另行裁决。

## 7. 发布态 execution manifest

```text
WorkflowExecutionManifest
  contractName = workflow-execution-manifest
  contractVersion
  workflowReleaseRef
  artifactDigest
  inputSchemaRef
  outputSchemaRef
  steps[]
    stepKey
    ordinal
    skillReleaseRef
    inputBinding = WORKFLOW_INPUT | PREVIOUS_STEP_OUTPUT
```

语义：

- `steps` 非空，`ordinal` 从 1 连续递增；`stepKey` 在 release 内稳定唯一。
- 第一步输入来自 Workflow 输入，其余步骤输入来自前一步成功输出。
- manifest 只引用 Skill release，不内嵌 Skill 包、凭证或业务配置。
- 相同 Workflow release ref 永远返回相同 manifest 与摘要。
- Runtime 遇到未知 `contractVersion`、摘要不符或 release 不可解析时不得猜测执行。

具体字段封装、数字版本和传输协议在 main-brain 协调后冻结。本任务只拥有上述消费者需求和领域语义。

## 8. Runtime 交互边界

推荐启动链路：数字员工提交 `workflowReleaseRef + workflowInput + runRequestKey` 给 Runtime；Runtime 经 Publication Read Port 解析 manifest，再按 `ordinal` 调用 Skill execution port。

Composer 不创建 `runId`，不保存 Run/Attempt，不决定 worker 选举、租约、checkpoint、退避或最大重试次数。为让 Runtime 安全重试，每个步骤提供稳定 `stepKey`；Runtime 组合 `runId + stepKey + attempt` 和能力侧幂等协议。首版 manifest 不提供用户自定义重试策略，避免 M 侧冻结未经裁决的 Runtime 语义。

## 9. 并发、失效与重试边界

- 并发保存：`expectedDraftRevision` 必须等于当前值；成功后原子递增。旧写入返回冲突并带当前 revision，不自动合并。
- 并发发布：同 key 返回同一结果；不同 key 针对同一 draft revision 也只能产生一个规范 release，具体唯一键由 shared contracts 裁决。
- 依赖查询超时：校验结果可返回不可判定问题，发布必须失败；客户端可重试，不生成半成品。
- 发布响应丢失：调用方使用相同 `requestKey` 重试并得到原结果。
- Runtime 解析失败：由 Runtime 记录运行启动失败；Composer 不降级到草稿或其他 Skill 版本。
- 多实例：任意 API 实例可处理下一请求；session affinity 和本地缓存均不能参与正确性。

## 10. PostgreSQL 持久化边界

首版只需要四个逻辑聚合，物理表设计在实现计划中确定：

- Draft head：当前 revision 和元数据。
- Draft snapshot：指定 revision 的 graph/layout，用于审计与确定发布输入。
- Workflow release：不可变 manifest、摘要、发布时间和发布主体。
- Release dependency/idempotency：固定 Skill release 列表与发布请求结果。

关键约束由唯一索引和事务表达：`draftId + draftRevision` 唯一、Workflow release identity 唯一、`publisherScope + requestKey` 唯一。不得增加 MySQL、SQLite 或内存持久化 profile。

## 11. 前端方案

React + TypeScript 编辑器使用受控 nodes/edges 状态。React Flow 是推荐实现候选，因为其公开 API 已覆盖节点、边、连接和受控状态；本轮不安装或锁定版本。UI 应在连接时限制多出边、显示节点级问题、区分“已保存”与“可发布”，但服务端仍是权威。

若依赖评估未通过，应停止前端实现并返回 main-brain 重新选择方案；不得静默改用步骤列表。

## 12. 安全与可观测性

- 发布权限、资产可见性和租户/主体范围依赖 shared contracts；所有依赖引用必须服务端鉴权。
- 禁止在 draft/manifest 中存储 secret、cookie、任意脚本、任意 URL 或原始 chain-of-thought。
- M 侧记录审计事件：草稿创建/更新、校验、发布请求和发布结果，包含 actor、draft/release ref、revision、requestKey 摘要与 issue codes。
- Runtime 的 step/run 事件、trace、checkpoint 和重试证据不回写为 Composer 的正确性状态。

## 13. 演进路径

只有在串行纵切片通过运行态门禁后，才提出 DAG 扩展：先增加条件分支，再评估并行与 join；循环、子流程和表达式语言分别独立提案。演进必须提升 manifest contract 版本并保持旧 release 可解析，不能改变既有 release 的含义。

## 14. 待裁决项

1. shared contracts 的 release identity、摘要规范、授权和撤销模型。
2. Runtime 的 manifest 解析方向、版本协商和启动失败标准错误。
3. 是否接受首版严格 schemaRef 相等规则；若拒绝，受限映射必须作为独立设计，而非隐式转换。
