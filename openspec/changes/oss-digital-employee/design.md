# 数字员工产品与可复用 A2UI Host 设计

## 状态与约束

- 设计状态：`PROPOSED`
- Runtime 准备度：`NO READY`
- 交付边界：设计文档，不包含代码、依赖、DDL、服务或部署变更
- 持久化：开发、测试和部署均为 PostgreSQL-only
- 运行拓扑：API、事件消费和 Adapter 必须允许多实例；进程内状态只可作可丢缓存

## 1. 场景与用户旅程

首个业务示例是“会议纪要整理与待办发布”。输入只使用用户手工输入或公开合成 fixture。用户在固定产品壳中创建会话和工作单，观察通用执行进度，在副作用动作前确认，并获得摘要、行动项列表和演示待办发布回执。

触发与预期：

1. **触发**：用户提交合法会议文本；**预期**：创建唯一工作单并启动一个关联 Runtime run，重复提交同一请求不产生第二个 run。
2. **触发**：Runtime 连续输出通用事件；**预期**：页面按序展示进度，既不暴露原始思维链，也不把业务阶段编码进 Runtime 类型。
3. **触发**：run 请求执行发布 Capability；**预期**：先暂停并显示行动项草稿，未批准时不得写入待办表。
4. **触发**：用户刷新或流连接中断；**预期**：页面从权威 snapshot 恢复，再从已确认 cursor 继续消费。
5. **触发**：用户批准后 Adapter 首次响应丢失；**预期**：Runtime 使用相同幂等键重试，数据库只产生一组待办与一个回执。
6. **触发**：两个页面同时提交相反决定；**预期**：只有匹配当前版本的第一个决定生效，后到请求收到冲突并刷新权威状态。
7. **触发**：Runtime 完成；**预期**：固定产品壳展示结果摘要，A2UI surface 展示结构化行动项，用户可读取发布回执。

## 2. 模块与所有权

### 2.1 React 产品壳

拥有路由、会话列表、工作单页面、连接状态、产品文案、无障碍和错误恢复入口。它不直接连接 Runtime，也不推断 Runtime 状态迁移。

### 2.2 可复用 A2UI Web Host

作为与业务无关的 React 包，接收 `surface snapshot + ordered updates + trusted catalog registry`，输出组件树和标准 action envelope。Host：

- 只解析已批准版本和 catalog；未知版本、catalog、组件、函数或 action 一律 fail closed。
- 不执行动态 JavaScript、HTML 或服务端表达式；组件实现来自前端本地受信注册表。
- 用 `surfaceId` 隔离渲染状态，用 snapshot 替换已知状态，用有序 update 增量更新。
- 检测序号缺口或非法 update 后冻结该 surface，显示可恢复错误并请求新 snapshot。
- 把输入值和 action 交给产品端 action dispatcher；Host 不持有业务授权规则。

### 2.3 数字员工产品后端

拥有身份校验、用户会话、工作单、输入净化、业务文案、结果视图和 Runtime 防腐层。它持久化产品实体与 `runId`/发布引用的关联，但 Runtime snapshot 是运行状态的唯一权威；产品投影可重建，不作为调度条件。

建议暴露四类产品语义：创建工作单、读取聚合视图、提交人工决定、请求重试。HTTP/RPC 形式和具体字段名待共享合约裁决。

### 2.4 Runtime Client Adapter

把产品语义转换为主控批准的通用 Runtime 命令，并把 snapshot/events 转换为稳定产品读模型。它必须保留 `requestId`、`commandId`、`runId`、事件 cursor、期望版本和发布引用，不得通过字符串解析推断事件。

### 2.5 业务 Capability Adapter

实现“发布到演示待办板”的业务语义，但通过 Capability Registry 声明的通用执行端口被 Runtime 调用。Adapter 拥有参数校验、授权复核、PostgreSQL 写入、幂等唯一约束和业务回执；不拥有 run 重试策略或 Workflow 调度。

## 3. 数据所有权

| 数据 | 权威所有者 | 数字员工可持久化 | 约束 |
| --- | --- | --- | --- |
| 用户会话、工作单、输入引用 | 产品后端 | 是 | PostgreSQL；避免在日志记录全文 |
| Workflow/Capability/A2UI 发布物 | 对应 M 端平台 | 只保存不可变引用和可选缓存 | 不复制发布状态机 |
| run、checkpoint、interrupt、retry、事件 cursor | Runtime | 只保存关联 ID、最后确认 cursor 和可重建投影 | Runtime snapshot 优先 |
| A2UI surface 运行快照 | Runtime/展示协议定义的权威存储 | 浏览器可缓存，产品端可作可丢投影 | 断线以 snapshot 重建 |
| 演示待办、发布回执、幂等执行记录 | 业务 Adapter | 是 | PostgreSQL 唯一键保证副作用一次 |

产品工作单可展示派生状态，例如“处理中、待确认、已完成、失败”，但这些只是 Runtime snapshot 的 UI 映射，不是第二套状态机，也不能驱动 Runtime 迁移。

## 4. 概念接口需求（非最终 wire schema）

### 4.1 产品到 Runtime

- `StartRun` 输入：授权上下文、不可变 Workflow 发布引用、业务输入引用或结构化输入、`requestId`/幂等键。
- `GetRunSnapshot` 输入：`runId`；输出：当前版本、开放 interrupt、已确认 cursor、结果/错误摘要和可恢复 presentation surfaces。
- `SubscribeRunEvents` 输入：`runId` 与 cursor；输出：包含全局唯一 `eventId`、单 run 单调 `sequence`、类型、时间和结构化 payload 的事件。
- `ResumeRun` 输入：`runId`、interrupt 关联、结构化决定、`commandId`、`expectedVersion`。
- `RetryRunStep` 输入：`runId`、可重试失败关联、`commandId`、`expectedVersion`。

上述名称只表达消费需求。Runtime 团队拥有最终命令、状态和错误模型。

### 4.2 Runtime 到 Capability Adapter

- 输入必须包含不可变 Capability 发布引用、结构化参数、授权上下文、`runId`、调用 ID 与副作用幂等键。
- 输出为 schema 校验后的业务结果或分类错误（可重试、不可重试、未授权、冲突）。
- Runtime 决定是否以及何时重试；每次重试必须复用同一副作用幂等键。

### 4.3 A2UI presentation

- presentation 必须携带版本、`surfaceId`、catalog/artifact 引用、snapshot 或 ordered update、关联 `runId`/事件序号。
- action 必须携带 `surfaceId`、action 名、结构化上下文、`commandId` 和用户当前看到的 `expectedVersion`。
- 产品后端重新校验身份、授权、开放 interrupt 和版本；前端禁用按钮不是安全边界。

## 5. 事件、恢复与并发

```text
用户 -> 产品后端: 创建工作单（requestId）
产品后端 -> Runtime: StartRun（不可变发布引用）
Runtime -> 产品端: snapshot + ordered events + A2UI presentation
Runtime -> 产品端: interrupt（发布前确认）
用户 -> 产品后端: approve/reject（commandId, expectedVersion）
产品后端 -> Runtime: ResumeRun
Runtime -> Capability Adapter: Execute（sideEffectIdempotencyKey）
Capability Adapter -> PostgreSQL: 唯一键写入待办与回执
Runtime -> 产品端: completion snapshot/result
```

- **断线**：客户端提交最后连续 cursor；服务端能续传则续传，不能保证连续性时返回 snapshot。客户端不得猜测缺失事件。
- **乱序/重复**：按 `eventId` 去重，按 sequence 连续应用。重复事件无效果；发现 gap 立即停止增量应用并补 snapshot。
- **命令重复**：相同 `commandId` 返回原决定结果；同一开放 interrupt 的不同命令用 `expectedVersion` 竞争，至多一个成功。
- **过期确认**：过期、已关闭、主体不匹配或版本过旧的决定均拒绝，不自动转为新 run 的批准。
- **Adapter 暂时失败**：Runtime 按批准策略重试，复用副作用幂等键；超过预算后保持可诊断失败，等待显式 Retry 命令。
- **实例切换**：产品后端和 Adapter 不依赖 sticky session 或进程锁；关联、唯一约束和命令结果均落 PostgreSQL。

## 6. 安全与可观测性

- 用户输入、presentation 和 Adapter 输出均按 schema、大小、深度和允许类型校验。
- A2UI Host 仅渲染本地受信组件；链接、富文本和下载动作采用明确策略。
- 页面只展示用户可理解的活动摘要、工具结果和错误，不展示原始思维链、模型隐藏消息或密钥。
- 日志使用关联 ID 和错误类别，正文默认不入日志；审计记录决定主体、时间、目标 interrupt 和结果。
- 指标至少区分启动、恢复、cursor gap、确认冲突、Adapter 重试、幂等命中、渲染拒绝和最终结果。

## 7. 失效边界

| 失效 | 责任方 | 对用户的结果 | 禁止行为 |
| --- | --- | --- | --- |
| Runtime 不可达 | 产品后端 | 工作单保留，可重试连接 | 不伪造本地运行成功 |
| 事件缺口 | Runtime Client / Host | 冻结增量并补 snapshot | 不跳过缺口继续渲染 |
| 未知 A2UI 资产 | Web Host | 安全错误卡和刷新入口 | 不降级执行任意 HTML/JS |
| 决定冲突或过期 | Runtime + 产品后端 | 显示已处理/已过期并刷新 | 不覆盖首个有效决定 |
| Adapter 暂时失败 | Runtime | 展示失败和显式重试入口 | 不在产品端另起隐式重试循环 |
| PostgreSQL 不可用 | 各持久化模块 | 请求失败且保持可诊断 | 不回退到内存、SQLite 或 MySQL |

## 8. 分阶段验证

1. 先用合成 fixture 验证产品 API、Runtime fake contract 和安全 Host 的契约测试。
2. 共享合约批准后，接入真实 Runtime，验证断线补快照、interrupt/resume 和 Adapter 幂等。
3. 在至少两个 API/worker 实例与一个 PostgreSQL 上做并发确认、实例切换和重复交付测试。
4. 最后才建立公开演示和三分钟路径；未完成运行证据前保持 `NO READY`。

## 9. 待裁决

仅保留 proposal 中的三项主控裁决：Runtime wire 协议、A2UI/传输版本、产品后端及 Adapter 交付边界。裁决前所有接口名和字段都是消费需求，不是已发布契约。
