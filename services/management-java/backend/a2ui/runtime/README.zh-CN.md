# A2UI 确定性运行核心

这里只解释已经校验、冻结的 Application 配置，不运行模型，不调度 Workflow。

## 数据边界

- 复用 `A2uiApplicationModels` 的编译模型；不另建同义的运行配置 DTO。
- `mapping/A2uiCapabilityRequestMapper` 区分卡片输入、Application 调用参数、可信上下文、前序能力结果和常量。`userId` 是后端 `Long`，不从卡片或模型输入覆盖。
- `action/A2uiCapabilityOutcomeEvaluator` 按已发布业务成功条件选择成功、失败或首个命中的成功分支。结果展示和完成交互意图来自同一次选择，不能由模型改写业务事实。
- `adapter/A2uiResultAdapterEngine` 负责结果消息模板、消息透传和配置的封闭转换。先生成完整批次，再在隔离的 Surface 状态上验证，失败不暴露部分消息。

## 尚未接通的边界

本模块不是已上线的 A2UI 服务。发布资产读取、首次加载、Action 协调与 RPC facade 的源码已补入，当前契约和责任边界见 [运行入口说明](README.md)。真实 RPC 能力执行、Chat 消息持久化和前端完整渲染仍须整体联调并逐项验收；源码完成不等于运行态可用。

业务执行采用 RPC，可信 `userId` 通过服务上下文传递，不把浏览器 Cookie 转发到业务执行链。RPC 服务接入不能把任意外部提交的 userId 当成已验证身份。管理端浏览器账号登录和 HTTP 编辑接口保持独立。

Workflow 当前暂停；保留 `completeWorkflowInteractionOnSuccess` 配置意图不等于执行了 Workflow 推进。

`tests/runtime/A2uiMappingSmoke.java` 是无网络核心验证入口，不证明 RPC、数据库发布或页面可用。
