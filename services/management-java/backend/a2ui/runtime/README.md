# A2UI 确定性运行入口

`A2uiRuntimeFacade` 只编排确定性计算，不运行模型、不创建 Agent 循环、不保存消息，也不推进 Workflow。业务执行统一使用 `CapabilityExecutionPort`，身份为完整 signed64 `userId`（包括 0 和负数）、明确 `PRT|ONLINE`，无 Cookie。

## 服务契约

协议：`proto/a2flow/a2ui/v1/a2ui.proto`，服务 `A2uiExecution`：

- `Describe`：只读当前用户/环境发布指针，返回 `sourceId/digest/appBuildId`、参数 schema、交互模式、Catalog 和完整 Action 声明，不执行业务。
- `Activate`：按可信 `userId/environment` 读取当前有效发布，再进行 Show、InputBindings、顺序 LoadBindings、ResultAdapter。
- `Act`：Python 从持久化读取可信卡片并传入；Java 核对身份、环境、revision、完整发布身份、session/Catalog 和 Action declaration/context，再执行能力及条件分支、结果适配。

`RuntimeResponse` 返回完整增量消息、可恢复快照、执行摘要、完整 Action 声明、交互完成意图与明确 `businessSuccess`。无 Load 的首屏成功返回 `businessSuccess=true`，不表示曾调用业务。首屏创建随机 session token，Python 私有持久化；它只是卡片关联值，不能代替服务认证，不向浏览器暴露。

任意浏览器提供的 Build、session、身份、snapshot 均不得直接进入此入口。Java 根据服务端发布聚合读冻结 Build，无草稿回退；provider 对同一发布聚合先核对目标环境存在，再调用共享 resolver，且再次核对解析环境，阻止共享旧逻辑的 PRT→ONLINE 回退。

RPC 必须装配统一服务间 mTLS 认证；仅独立本机测试允许严格 loopback 明文。失败使用 gRPC 状态与稳定错误码；未知内部失败不外泄 payload 或异常堆栈。协议 `error_code` 目前为预留字段，不用空响应伪造成功。

## 执行与持久化边界

Python 在调用前负责用户/卡片授权、请求去重和消息级租约；成功后 CAS 提交返回快照/消息。Java 不提供跨进程消息锁，不自动重试业务。每条能力子请求 ID 使用父 requestId 与冻结 bindingId 的结构化 SHA-256，稳定且互不混淆。业务已执行而适配失败时，不得将错误当成“业务未执行”而重试。

Show、schema 校验、Pointer、结果转换、账本 reducer、可信时间字段保留参考实现算法；冻结模型复用 `A2uiApplicationModels`，仅为三个有兼容重载构造器的模型添加私有 Jackson mixin，完整保留 transform/footer。Load 依次读取前次结果，失败管线渲染后停止后续 Load。Action 先判断业务成功条件，再选第一个匹配分支。Application 模型不存在额外 Composite 列表；能力自身组合由统一 RPC 能力执行器负责。

当前没有 Workflow 调度、恢复或嵌入子树执行。`completeInteraction` 只是所选冻结分支的意图，调用方不得据此宣称 Workflow 已推进。

## 验证边界

`tests/runtime/A2uiAdapterSmoke.java` 验证五类结果转换和批次原子性；`A2uiFacadeSmoke.java` 使用测试替身验证只读 Describe、完整 manifest round-trip、Show/Load/Action 与 reset。它们不等于实际业务 RPC 或浏览器联调。共享编译、mTLS、独立 PostgreSQL 发布读取与 Python/B 端联调由集成任务单独记录。
