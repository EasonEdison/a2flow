# Agent/Workflow Runtime 提案

## 状态

- 设计状态：PROPOSED
- Runtime 准出：NO READY
- 证据等级：C（仅设计，未实现、未测试、未部署）
- 决策所有者：CTO / main-brain

## 为什么要做

数字员工产品需要一个业务无关的执行底座：它既能执行单个 Agent 的模型/工具循环，又能调度可恢复的 Workflow；同时能够把通用展示请求、人工动作和执行事件交给产品层处理。若把这些能力直接写进数字员工后端，业务语义、界面文案和运行状态会互相绑死，也无法独立验证多实例恢复与幂等边界。

本提案只定义首个可审查的 Runtime 边界，不实现代码，不冻结尚未批准的跨域协议。

## 本次范围

- 区分单 Agent 执行与 durable Workflow 调度，并允许 Workflow 通过显式节点调用 Agent 子运行。
- 定义 PostgreSQL-only 的运行状态、租约、checkpoint、事件、幂等、HITL 和取消语义。
- 定义 CapabilityExecutionPort 与 PresentationActionPort 两个业务无关端口。
- 定义多实例 worker 的领取、续租、过期恢复与 fencing 边界。
- 定义从事件游标续传的通用输出语义，不锁定 SSE、AG-UI 或其他传输版本。
- 比较 TypeScript/LangGraphJS 与 Python/LangGraph，给出可撤销推荐。

## 不在范围

- 数字员工业务实体、业务分支、提示文案与前端渲染。
- M 侧资产编辑、发布和审批流程。
- 任意图拓扑、multi-agent swarm、通用低代码平台。
- 模型供应商、沙箱实现、RAG/向量库与长期记忆实现。
- 数据库 DDL、应用脚手架、部署、密钥或生产配置。
- 对外协议版本的单方面冻结。

## 语言方案

| 方案 | 优点 | 代价与风险 | 本提案结论 |
| --- | --- | --- | --- |
| TypeScript + LangGraphJS | 与 React/TypeScript 产品及共享契约同语言；官方能力覆盖 durable execution、checkpoint、streaming、interrupt/HITL 与 PostgresSaver；减少跨语言 DTO 生成和调试链路 | Python AI 生态的部分新集成可能更早或更丰富；必须用验收 spike 验证 PostgreSQL、interrupt、stream 与多实例封装 | 推荐用于 MVP，但保持 PROPOSED |
| Python + LangGraph | Python AI/数据生态成熟；官方提供同步与异步 PostgreSQL checkpointer；复杂模型与评测集成选择多 | 前后端跨语言契约与构建链更多；仍需自行补齐租约、fencing、外部副作用幂等和产品协议适配 | 保留为强备选 |
| TypeScript 网关 + Python Runtime | 可同时利用两侧生态 | MVP 即引入两个进程、两套序列化与恢复边界，扩大运维和故障面 | 首个纵向切片不采用 |

推荐理由不是“LangGraphJS 天然保证完整分布式语义”。官方资料证明两种实现都有核心编排原语和 PostgreSQL checkpointer；Runtime 仍必须自行拥有多实例租约、fencing、事件顺序和外部副作用幂等。TypeScript 的主要收益是首个纵向切片的契约一致性与较低系统复杂度。若 parity spike 未通过，回退到 Python 方案须由 CTO 记录 ADR，而不是在代码中静默双栈。

## 依赖输入与输出

| 依赖域 | Runtime 输入 | Runtime 输出 | 所有权 |
| --- | --- | --- | --- |
| 公共契约 | 资产标识、不可变 revision、校验和、授权上下文、错误包络 | run 标识、状态、revision、错误分类 | oss-platform-contracts |
| Skill/Workflow 发布 | 已发布且不可变的 Agent/Workflow 定义引用 | 实际解析到的 revision 与校验结果 | oss-skill-registry / oss-workflow-composer |
| Capability 注册 | capability revision、输入/输出 schema、幂等声明 | 带稳定 operationKey 的调用与标准结果 | oss-capability-registry |
| A2UI 组合 | presentation artifact revision、数据 schema、action schema | 通用 presentation/action 事件，不包含渲染逻辑 | oss-a2ui-composer |
| 数字员工产品 | start/resume/cancel/subscribe 命令与业务适配后的输入 | run snapshot、事件、action request、terminal result | oss-digital-employee |

## 成功标准

- 单 Agent 与 Workflow 具有独立运行语义、状态和测试，不以一种模式冒充另一种。
- 任一进程退出后，另一实例只凭 PostgreSQL 可安全恢复，不依赖进程内唯一状态。
- 领取过期后旧 worker 的写入被 fencing 拒绝。
- 重试复用稳定 operationKey，重复投递不制造重复外部副作用。
- HITL 决策、取消和事件续传均可被并发测试验证。
- Runtime 核心不出现数字员工业务字段、业务文案或前端 renderer 依赖。

## 请求主控裁决

1. 是否批准 TypeScript + LangGraphJS 为 MVP 首选，并要求用 parity spike 作为最终锁定门禁。
2. 公共契约由哪个包拥有，以及资产 revision、授权、错误包络和事件 envelope 的最小字段。
3. 首个对外传输是否采用某一 AG-UI/SSE 方案，以及 A2UI payload 与 action response 的版本边界。

## 公开依据

- [LangGraphJS 概览](https://docs.langchain.com/oss/javascript/langgraph/overview)
- [LangGraphJS 持久化](https://docs.langchain.com/oss/javascript/langgraph/persistence)
- [LangGraphJS Interrupts](https://docs.langchain.com/oss/javascript/langgraph/interrupts)
- [LangGraphJS Streaming](https://docs.langchain.com/oss/javascript/langgraph/streaming)
- [LangGraphJS PostgresSaver API](https://reference.langchain.com/javascript/langchain-langgraph-checkpoint-postgres/index/PostgresSaver)
- [LangGraph Python 持久化](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Python Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph Python PostgreSQL checkpointer](https://reference.langchain.com/python/langgraph.checkpoint.postgres)
