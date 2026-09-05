# 回归计划

## 证据状态

- 状态：`PLANNED`
- 已执行自动化：无
- 已执行端到端：无
- 已执行部署验证：无
- Runtime：`NO READY`

下列 method、params 和 `data` 仅描述待批准的消费契约，不是已经发布的 API。

## R1 创建工作单与请求幂等

- 触发：对同一用户会话以相同 `requestId` 两次调用 `CreateMeetingFollowUpTask`。
- params：`sessionId`、`requestId`、`workflowReleaseRef`、合成会议文本。
- 期望成功 data：`workItemId`、`runId`、`acceptedRequestId`、`viewVersion`。
- 字段断言：两次响应的 `workItemId` 和 `runId` 相同；只存在一个 Runtime run 关联。
- 期望结果：返回同一已接受结果，不重复启动。
- 证据：`PLANNED`。

## R2 流式顺序、重复与断线恢复

- 触发：`SubscribeTaskView` 收到重复事件、随后断线，并在 cursor 后模拟 sequence gap。
- params：`workItemId`、`afterCursor`。
- 期望成功 data：`snapshotVersion`、`acceptedCursor`、`events[]`、`surfaces[]`。
- 字段断言：重复 `eventId` 只应用一次；断线后连续事件可续传；gap 时不应用后续 delta，改取完整 snapshot。
- 期望结果：恢复后的任务视图与 Runtime snapshot 一致。
- 证据：`PLANNED`。

## R3 A2UI 安全渲染与 action 回传

- 触发：Host 收到受信 catalog 的 surface snapshot 和行动项更新，用户点击“批准发布”。
- params：`surfaceId`、`catalogRef`、`presentationVersion`、`snapshot`/`updates`。
- 期望成功 data：`renderedSurfaceId`、`appliedSequence`、`action.commandId`、`action.expectedVersion`。
- 字段断言：只使用本地注册组件；action 上下文为 schema 允许字段；不执行 payload 中的代码或 HTML。
- 期望结果：页面呈现草稿并把结构化 action 交给产品后端。
- 证据：`PLANNED`。

## R4 未知 A2UI 资产 fail closed

- 触发：Host 收到未知协议版本、catalog、组件、函数或 action。
- params：无效 `presentationVersion` 或 `catalogRef` 及对应 payload。
- 期望错误 data：`surfaceId`、`errorCode`、`recoverable`、`requiredSnapshot`。
- 字段断言：surface 冻结或拒绝；显示安全错误与刷新入口；不执行、不静默降级。
- 期望结果：失败被隔离到目标 surface，固定产品壳仍可使用。
- 证据：`PLANNED`。

## R5 人工确认门禁与拒绝路径

- 触发：Runtime 发出发布前 interrupt；分别在未决定、拒绝和批准三种路径调用 `SubmitTaskDecision`。
- params：`workItemId`、`interruptId`、`decision`、`commandId`、`expectedVersion`。
- 期望成功 data：`runId`、`decisionStatus`、`newVersion`、`capabilityInvocationId`（仅批准路径）。
- 字段断言：未决定和拒绝路径不存在待办写入；只有有效批准产生一次 Capability 调用。
- 期望结果：副作用严格位于人工确认之后。
- 证据：`PLANNED`。

## R6 并发决定与过期决定

- 触发：两个客户端对同一 interrupt 并发提交相反决定，再提交一个过期决定。
- params：相同 `interruptId` 和 `expectedVersion`，不同 `commandId`。
- 期望成功/冲突 data：成功方含 `newVersion`；失败方含 `currentVersion`、`errorCode`、`refreshRequired`。
- 字段断言：至多一个决定生效；后到和过期请求不改变 run；主体不匹配同样被拒绝。
- 期望结果：客户端刷新并展示权威决定。
- 证据：`PLANNED`。

## R7 Adapter 暂时失败与副作用幂等

- 触发：`ExecuteCapability` 成功写入后丢失响应，Runtime 以相同副作用幂等键重试。
- params：`capabilityReleaseRef`、结构化行动项、`invocationId`、`sideEffectIdempotencyKey`、授权上下文。
- 期望成功 data：`receiptId`、`publishedItemIds[]`、`idempotencyHit`、`completedAt`。
- 字段断言：两次执行返回同一 `receiptId` 和项目集合；数据库没有重复待办；第二次标记幂等命中。
- 期望结果：run 可完成且副作用恰好一次可观察。
- 证据：`PLANNED`。

## R8 多实例恢复与最终结果

- 触发：run 进行中切换 API/事件消费实例，完成后调用 `GetTaskView`。
- params：`workItemId`、用户授权上下文。
- 期望成功 data：`session`、`workItem`、`runtimeSnapshot`、`summary`、`actionItems[]`、`publicationReceipt`、`surfaces[]`。
- 字段断言：新实例无需旧进程内状态即可恢复；工作单关联同一 `runId`；结果字段与 Runtime/Adapter 权威结果一致。
- 期望结果：用户刷新后仍能读取完整结果和回执。
- 证据：`PLANNED`。

## 计划环境

- 合成数据，不连接真实办公系统。
- PostgreSQL 是唯一关系型数据库；不启用 MySQL、SQLite 或内存 fallback。
- 多实例门禁至少包含两个无状态 API/worker 实例和共享 PostgreSQL。
- 协议契约、实现、测试和部署均未发生，因此本文件不能作为 runtime 可用证据。
