# 数字员工首个垂直切片提案

## 状态

- 设计：`PROPOSED`
- Runtime：`NO READY`
- 证据等级：设计草案，未实现、未测试、未部署

## 为什么做

当前平台需要一个足够小、又能暴露真实工程边界的 B 端示例，验证数字员工产品可以消费通用 Runtime，而不把业务语义、交互文案或 React 渲染逻辑放入 Runtime。首个示例选择“会议纪要整理与待办发布”：用户提交合成会议文本，系统生成摘要和行动项草稿，在发布到演示待办板前暂停并请求人工确认，最终返回可阅读结果与发布回执。

该示例不连接真实办公系统，不包含任何组织私有数据。演示发布目标是本项目自己的 PostgreSQL 待办表，既能验证有副作用操作的幂等性，又保持 clean-room 和首片规模。

## 候选方案

### 方案 A：产品后端防腐层 + 固定产品壳 + 可复用 A2UI Host（推荐）

- React + TypeScript 前端只访问数字员工产品后端。
- 产品后端拥有会话、工作单、业务输入校验、Runtime 合约适配和业务 Capability Adapter。
- 通用 Runtime 仍是 run/checkpoint/retry/interrupt 的唯一权威；产品后端不复制状态机。
- 固定产品壳呈现导航、会话和任务级体验；可复用 A2UI Host 只渲染受信目录中的声明式 surface，并把 action 回送产品后端。

优点是业务边界清晰、可在 Runtime 协议定版前通过适配端口隔离变化，并能复用安全渲染 Host。代价是产品后端要维护读模型转换和协议适配。

### 方案 B：React 前端直接连接 Runtime

链路更短，但前端会直接承担 Runtime 身份、恢复、并发和协议差异，业务授权也容易渗入通用 Runtime。首片不推荐。

### 方案 C：产品后端输出自定义页面 JSON，不消费 A2UI

短期可控，但会形成第二套声明式 UI 协议，无法验证 M 端 A2UI 组合物的真实消费链路。首片不推荐。

## 推荐范围

首片只覆盖一条固定 Workflow：

1. 创建用户会话和“会议纪要转行动项”工作单。
2. 用已发布 Workflow 引用启动通用 Runtime；展示摘要生成和行动项整理进度。
3. Runtime 在“发布待办”前产生通用人工确认请求。
4. 产品后端把确认请求映射为业务文案；A2UI Host 渲染草稿与批准/拒绝动作。
5. 用户批准后，Runtime 通过通用 Capability 执行端口调用数字员工拥有的演示待办 Adapter。
6. Adapter 使用 Runtime 提供的幂等键写入 PostgreSQL；Runtime 完成后，产品端展示摘要、行动项和发布回执。
7. 刷新、断线或切换实例后，通过 Runtime snapshot + cursor 恢复，不依赖进程内状态。

首片不做自由编排、第三方办公系统集成、多租户计费、任意自定义组件、客户端执行模型生成代码或 Runtime 状态机复制。

## 依赖与交付关系

| 依赖方 | 本任务需要的输入 | 本任务提供的输出 | 所有者 | 当前状态 |
| --- | --- | --- | --- | --- |
| `oss-platform-contracts` | 不可变发布引用、主体/授权上下文、请求关联和错误约定 | B 端消费约束与必需字段 | 平台合约任务 | `PROPOSED` |
| `oss-workflow-composer` | 可执行 Workflow 发布引用及入口输入 schema | 选定发布版本和启动输入 | Workflow 组合任务 | `PROPOSED` |
| `oss-agent-workflow-runtime` | Start、snapshot/event stream、interrupt/resume、retry 契约 | 业务无关命令及可追踪 idempotency key | Runtime 任务 | `NO READY` |
| `oss-a2ui-composer` | 版本化 catalog/presentation artifact、surface/action 约定 | React Host 能力声明、渲染错误与 action 回传 | A2UI 组合任务 | `PROPOSED` |
| `oss-capability-registry` | Capability 发布引用、输入输出 schema、调用授权 | 演示待办 Adapter 的通用执行实现 | Capability 注册任务 | `PROPOSED` |

Runtime 必须输出可排序、可去重、可补快照的通用事件；不得输出本示例的会议、行动项或发布分支状态名作为 Runtime 核心类型。数字员工负责把通用事件和 presentation payload 适配为用户体验。

## 公开资料依据

- A2UI v1.0 Candidate 将声明式 UI surface 与传输解耦，并定义增量 component/data model 更新：<https://github.com/a2ui-project/a2ui/blob/main/specification/v1_0/docs/a2ui_protocol.md>
- AG-UI 官方事件文档描述 snapshot/delta 与流事件类别：<https://docs.ag-ui.com/concepts/events>
- AG-UI 官方 interrupt 文档描述人工暂停、关联和恢复语义：<https://docs.ag-ui.com/concepts/interrupts>

这些资料只支持候选比较，不表示本 change 已选定具体协议版本或 wire schema。

## 成功条件

- 产品后端和 Runtime 的所有权、输入输出、失败、重试和并发边界可独立审查。
- A2UI Host 只渲染受信 catalog，不执行服务端下发的任意代码。
- 至少覆盖创建、流式进度、人工确认、刷新恢复、失败重试、重复命令、并发动作和结果展示。
- 所有实现与运行证据保持未完成，直到共享合约获批并执行真实验证。

## 需要主控裁决（最多三项）

1. Runtime 对外采用何种协议与版本，以及 snapshot/cursor、interrupt/resume 和幂等命令的最终 wire schema。
2. A2UI 采用的规范版本、catalog/artifact 身份与 action 回传绑定；是否以 AG-UI 作为首选传输绑定。
3. 数字员工产品后端是否采用 TypeScript，并将演示 Capability Adapter 作为独立模块还是独立进程交付。
