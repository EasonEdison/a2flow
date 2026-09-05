# Digital Employee Product Capability Specification

## 状态

- Capability：数字员工产品与可复用 A2UI Web Host
- 设计：`PROPOSED`
- Runtime：`NO READY`

## ADDED Requirements

### Requirement: 产品必须与通用 Runtime 解耦

数字员工前后端 MUST 通过版本化通用合约消费 Runtime。产品拥有业务语义和读模型，Runtime 拥有 run、checkpoint、interrupt、resume、retry 与幂等执行语义。产品 MUST NOT 实现第二套运行状态机，Runtime MUST NOT 导入会议纪要、行动项、业务文案或 React 组件模型。

#### Scenario: 创建会议纪要工作单

- **WHEN** 已授权用户用合法合成会议文本和唯一 `requestId` 创建工作单
- **THEN** 产品后端创建产品工作单并以不可变 Workflow 发布引用启动一个 Runtime run
- **AND** 相同 `requestId` 的重复请求返回同一 `workItemId`/`runId`，不启动第二个 run

### Requirement: 产品必须从权威快照恢复会话和任务

产品 MUST 持久化会话、工作单与 run 的关联，但 MUST 将 Runtime snapshot 视为执行状态权威。投影丢失、刷新或实例切换时，产品 MUST 能从 PostgreSQL 关联与 Runtime snapshot 重建视图。开发、测试和部署 MUST 使用 PostgreSQL，MUST NOT 回退到 MySQL、SQLite 或进程内持久化。

#### Scenario: 刷新并切换服务实例

- **WHEN** 用户在 run 进行中刷新页面，且后续请求落到另一无状态实例
- **THEN** 新实例通过 `workItemId` 找到同一 `runId`，获取 snapshot 并恢复当前进度、开放 interrupt 和 surface
- **AND** 恢复不依赖旧实例内存、sticky session、MySQL、SQLite 或内存 fallback

### Requirement: 事件消费必须有序、幂等且可补快照

产品与 Host MUST 按唯一事件 ID 去重并只连续应用单 run 序号。检测到缺口、非法 delta 或无法续传时 MUST 停止增量应用并请求完整 snapshot，MUST NOT 猜测或跳过缺失状态。

#### Scenario: 重复事件后出现序号缺口

- **WHEN** 客户端收到重复事件并随后收到不连续 sequence
- **THEN** 重复事件不改变视图，缺口后的 update 不被应用
- **AND** 客户端获取并替换为权威 snapshot 后才继续消费

### Requirement: 有副作用的发布必须先人工确认

“发布到演示待办板” MUST 在 Runtime 开放的通用 interrupt 上暂停。产品后端 MUST 校验用户、interrupt、结构化决定和 `expectedVersion`；只有有效批准才能恢复 run 并触发 Capability。拒绝、过期、未授权或冲突决定 MUST NOT 产生副作用。

#### Scenario: 用户拒绝发布

- **WHEN** 用户在待确认 surface 上提交拒绝决定
- **THEN** 产品后端把结构化决定关联到当前 interrupt 并请求 Runtime resume
- **AND** 演示待办表没有新增记录，视图展示已拒绝的权威结果

#### Scenario: 两个客户端并发决定

- **WHEN** 两个客户端以相同 `expectedVersion` 对同一 interrupt 提交不同决定
- **THEN** 至多一个决定成功，另一个收到冲突和当前版本
- **AND** 失败客户端刷新 snapshot，不覆盖已生效决定

### Requirement: Capability 副作用必须跨重试幂等

演示待办 Adapter MUST 使用 Runtime 提供的副作用幂等键和 PostgreSQL 唯一约束。Runtime 因超时或响应丢失重试时 MUST 复用同一键；产品端 MUST NOT 额外启动不可追踪的隐式重试循环。

#### Scenario: 写入成功但响应丢失

- **WHEN** Adapter 已提交待办和回执，但 Runtime 未收到首次响应并重试
- **THEN** 第二次调用返回原 `receiptId` 和待办集合
- **AND** PostgreSQL 中没有重复待办，run 可使用原业务结果继续完成

### Requirement: A2UI Host 必须可复用且 fail closed

Web Host MUST 与会议业务无关，只消费受信的版本、catalog、surface snapshot/update 和 action schema。Host MUST 使用本地注册的 React 组件，MUST NOT 执行服务端下发的 JavaScript 或任意 HTML。未知版本、catalog、组件、函数或 action MUST 被拒绝并隔离。完成视图 MUST 呈现可关联的摘要、行动项和发布回执，MUST NOT 暴露原始思维链、隐藏模型消息或凭据。

#### Scenario: 渲染受信行动项 surface

- **WHEN** Host 收到已批准 catalog 的完整 surface snapshot 及连续更新
- **THEN** Host 使用本地 React 组件呈现摘要、行动项和确认动作
- **AND** 用户 action 以结构化 envelope 交给产品后端重新授权
- **AND** 完成后结果关联同一 `sessionId`、`workItemId`、`runId` 与 `receiptId`，且不包含原始思维链

#### Scenario: 收到未知 catalog

- **WHEN** presentation 引用未批准 catalog 或不支持的协议版本
- **THEN** Host 冻结或拒绝目标 surface，展示安全错误与刷新入口
- **AND** 固定产品壳保持可用，不执行 payload，不静默降级到任意 HTML
