# Phase 1 公共契约候选

- Baseline: `SW-P1-20260907.2 + ENG-01`
- Aligned worker base: `0980f0ae304a340f24d7421ab4a51818af612b32`
- Status: `PROVISIONAL / MAIN-BRAIN REVIEW PENDING`
- Runtime readiness: `NO READY`

## 目标

为 Phase 1 提供一套最小、跨语言可消费的公共外壳，覆盖可信 `userId/environment` 上下文、全部资产的环境内 serving/resolution、版本失配决策、控制请求去重，以及 Run/Node/Interaction/Result 引用和事件边界。

公共契约只统一引用和边界，不建设通用治理平台，不替四个 M 域实现四套发布能力，也不拥有 Workflow、A2UI、Skill、Ability 或数字员工业务状态机。

## 本轮纠正的旧方案

- 删除 `preview/stable` 作为环境；环境只有 `PRT` 与 `ONLINE`。
- 删除 `workspaceId`、`issuer + subject` 作为 Phase 1 公共请求主体；灰度和执行身份统一为可信 `userId`。
- 删除 ONLINE 灰度读取 PRT 的可能性；ONLINE stable/candidate 都来自 ONLINE 存储。
- 删除 Run 内冻结旧 Release 后继续执行；执行、继续和 Action 入口发现版本不一致时拒绝新工作并提示显式 reset。
- 删除把控制请求去重扩展成业务 exactly-once 的暗示；业务 API 后端拥有业务幂等、重试和未知结果处理。
- 删除对 HTTP、SSE、CloudEvents、AG-UI、A2UI 版本及事件总线的预冻结。
- 收缩四层 Asset/Revision/Release/Pointer 通用平台；Phase 1 只保留领域资产版本引用与一个共享 environment-aware resolver/publication 语义。

## 推荐切片

### 1. 可信请求上下文

`TrustedContext` 仅含服务端认证/路由层解析后的 `userId` 与 `environment`。模型、Skill 文本、Tool 参数和前端业务 payload 不得选择或覆盖它；权限与凭证不进入公共 JSON payload。

模型可见 `use_skill` 请求只选择逻辑 `skillKey`。服务端另注入 conversation/run/node scope 与 controlRequestId；成功结果按 `content + artifact` 分层，content 只含指令和授权只读材料 handle，artifact 保存精确版本、环境选择、摘要和 evidenceRef。

### 2. 环境内 serving 与解析

全部资产类型使用共同外壳：`SKILL`、`ABILITY`、`COMPONENT`、`APPLICATION`、`WORKFLOW`。PRT 只暴露一个当前 PRT 版本；ONLINE 暴露 stable，灰度时至多再暴露一个 candidate。灰度选择依据可信 `userId`，stable/candidate 都从 ONLINE 数据库读取。历史版本可保留，serving 结束不删除历史。

### 3. 轻量版本门禁

Run/Node/Interaction 只记录其已观察的资产版本集合。每次执行、继续或 Action 入口重新解析当前有效版本；一致时允许进入，不一致时返回 `RESET_REQUIRED` 和逐资产 mismatch，且在任何新模型/Tool/业务调用之前停止。

### 4. 控制请求去重

平台控制命令使用 `controlRequestId + payloadDigest`。同 ID 同摘要返回原控制结果；同 ID 异摘要拒绝。该语义不跨 fresh run 去重业务结果，也不替被调用 API 实现业务幂等。

### 5. 执行引用与事件边界

公共层定义稳定的 Run、Node、Interaction、Result 引用，并单一提供最小 `ResultInterpretationPolicy`：只允许 `SCHEMA_VALID` 和 `JSON_POINTER_EQUALS`，由 Runtime 的唯一纯解释器执行。`INTERACTION_RESULT_RECORDED`、`NODE_RESULT_RECORDED`、`RUN_RESULT_RECORDED` 是不同事实；Schema 校验、策略命中、Action 调用、交互完成、节点完成和 Finalizer 最终结果不得互相冒充。事件传输协议和版本仍待主控。

## 交付物

- 修订本 change 的 proposal/design/spec/tasks/regression/readiness/checkpoint。
- 在 `packages/contracts/` 提供候选 JSON Schema、独立合成正反例和聚焦校验入口。
- 给 Runtime 提供 Python 消费/打包建议，不修改根依赖清单。

## 不在范围

- Python Runtime、Deep Agents/LangGraph 适配器、PostgreSQL DDL 或发布服务实现。
- Tool 的最终方法名/字段、HTTP 路径、SSE/AG-UI/A2UI 版本、消息总线和根目录依赖。
- 业务调用的重试、补偿、对账、跨 Run 去重或 exactly-once 保证。
- 部署、secret、公共端口和现有服务变更。

## 接口审查闸门

候选 Schema 可以先验证，但六域只能在 main-brain 命名的契约 revision 后依赖实现。合入源码不代表接口批准或 Runtime READY。
