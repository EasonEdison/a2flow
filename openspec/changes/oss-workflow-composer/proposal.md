# Skill Workflow 编排平台首版提案

## 状态

- 设计：`PROPOSED`
- 实现：未开始
- Runtime：`NO READY`
- 交付含义：本 change 进入 `main` 只表示可审查的设计源码已交付，不表示设计获批、功能可用或运行态已验证。

## Why

M 侧需要把多个已发布 Skill 版本组合成可发布、可追溯且可被通用 Runtime 消费的 Workflow。首个纵向切片的重点是证明定义、校验、发布和执行契约可以闭环，而不是提前建设通用低代码或复杂 DAG 平台。

## 本轮范围

- React + TypeScript 方向的受限图编辑：`START -> SKILL... -> END`。
- 每个 Workflow 含 1 至 8 个 Skill 节点；仅允许单入口、单出口、单链路。
- 节点只引用已发布且不可变的 Skill release；禁止 `latest`、版本范围和草稿引用。
- 草稿允许暂时语义无效；校验和发布必须由服务端重新执行并失败关闭。
- 发布时把编辑图编译为去除布局信息的线性、不可变 execution manifest。
- 定义 Workflow 发布物与 Runtime 的消费边界，不定义 Run、调度、checkpoint、重试执行或运行态事件。

## 明确不做

- 条件分支、并行、循环、子流程、动态节点、定时触发和多 Agent swarm。
- 任意表达式、脚本、URL、密钥、数据映射语言和用户可配置重试算法。
- Runtime 实现、数字员工业务语义、A2UI 渲染、部署、数据库或服务变更。
- 自动升级 Skill 依赖、静默 fallback 或在依赖不可用时发布不完整 artifact。

## 候选方案

### A. 节点/边草稿，发布为线性 manifest（推荐）

编辑态保留 `nodes`、`edges` 和独立 `layout`，服务端强制单链路拓扑；发布态按拓扑序生成 `steps[]`。它既能支持有意义的图编辑体验，又让 Runtime 只消费简单确定的执行序列，并保留未来引入 DAG 的演进空间。

代价是需要两层校验和一次确定性编译，但复杂度仍可被首版边界控制。

### B. 直接编辑有序步骤数组

实现最小、Runtime 契约最直接，但不能真实验证图编辑能力；后续迁移到 DAG 时还需要新增节点标识、边和布局模型。若选择该方案需 main-brain 显式批准；不得在推荐方案实现失败时静默切换。

### C. 首版采用完整 DAG 或 Open Workflow DSL

标准能力和表达力更强，但会立即引入分支、并发、表达式、错误策略和更大的兼容面，超出单机资源下的首个纵切片目标。本轮只把 Open Workflow Specification 作为术语与演进参考，不声明兼容。

## 推荐的最小数据流

- Workflow 输入契约由第一个 Skill release 的输入 schema 派生。
- 第一个步骤接收 Workflow 输入；后续步骤只接收前一步输出。
- 相邻步骤首版要求输出与输入使用完全相同的规范化 `schemaRef`；不做隐式类型转换。
- Workflow 输出契约由最后一个 Skill release 的输出 schema 派生。
- 不兼容时应新增显式 Adapter Skill，而不是在编排器中嵌入映射脚本。

## 依赖与交付

| 依赖方 | 需要的输入 | 本任务输出 | 失效边界 |
| --- | --- | --- | --- |
| shared contracts | `AssetRef` / `ReleaseRef`、不可变发布、授权、幂等语义 | Workflow 对这些语义的消费者要求 | 未裁决时不得冻结协议版本 |
| Skill registry | 按 release ref 查询发布状态、输入/输出 schemaRef、可执行性 | 被引用 release 列表与校验错误 | 查询超时、无权或非发布状态均阻断发布 |
| Runtime | manifest 版本协商与解析确认 | 不可变线性 execution manifest | 不支持版本、摘要不符或依赖不可用时失败关闭 |
| 数字员工 | 选择已发布 Workflow release 并发起运行 | 稳定 Workflow release ref | 不直接依赖编辑草稿或 M 侧布局 |

## 风险控制

- 并发编辑使用 `expectedDraftRevision` 乐观并发；旧 revision 写入不得覆盖新 revision。
- 发布需要 `requestKey` 幂等语义；响应丢失重试不得创建第二个 release。
- 发布前同一 revision 内重新校验拓扑、Skill release 和 schema 链；不复用陈旧 UI 校验结果。
- 正确性状态只落 PostgreSQL；多实例不得依赖进程内锁、会话或缓存。
- 发布物不含 secret、URL、脚本、业务字段或编辑器位置。

## 待 main-brain 裁决

1. 统一 `AssetRef` / `ReleaseRef`、发布幂等键和 release 撤销语义由 shared contracts 采用何种字段与版本规则。
2. Runtime 通过 release ref 拉取 manifest，还是由启动请求携带 manifest；无论选择哪种，摘要校验和版本协商必须一致。
3. MVP 是否批准“相邻 `schemaRef` 完全相等 + Adapter Skill”规则，还是引入受限显式映射；本提案推荐前者。

## 公开参考

- [Open Workflow Specification](https://github.com/open-workflow-specification/specification)：作为声明式工作流和可移植执行定义的能力上界参考，本轮不承诺兼容。
- [JSON Schema 官方说明](https://json-schema.org/understanding-json-schema/about)：结构校验与跨字段/拓扑语义校验需要分层处理。
- [React Flow 官方概念](https://reactflow.dev/learn/concepts/terms-and-definitions)：验证 React 图编辑器的 nodes、edges、handles 和受控状态模型可承载本轮交互；具体依赖版本仍待实现阶段评估。
