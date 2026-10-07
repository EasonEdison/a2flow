# Workflow current RPC bridge checkpoint

Baseline: origin/main f8d4f83. Owner: workflow-a2ui-bridge.

Scope: current Skill/Application RPC contracts in Workflow; card Action execution,
atomic terminal-card/outbox callback, native interrupt continuation. No deployment,
provider calls, business retry, compensation or asset revision gates.

Implemented:
- RpcWorkflowHost uses RpcAssetReader and reuses RpcChatAssets/RpcChatActionService.
- Tools expose appCode/params and query_skill_dependencies.
- Cards use a private per-run/node namespace; published params, LoadBindings and
  Actions execute in the existing deterministic RPC service.
- Successful terminal Action, saved observation and typed resume outbox are one
  PostgreSQL transaction. Paging and selection do not resume.
- Worker resume verifies durable completion, deduplicates the saved request and
  resumes the matching native interrupt. Display ToolMessage and saved Action
  HumanMessages precede the continuing Skill; final model output completes node.
- One process-wide execution lane is shared by start/restart/actions/resume.
- Current RPC cards have a dedicated /cards projection; legacy /view stays compatible.
- realchat launcher and attended runtime wire typed scheduler outbox notifications.

Validation: native LangGraph MemorySaver probe passed wait, nonterminal rejection,
terminal continuation, observation messages, duplicate no-replay; current schema
and Finalizer Command evidence probe passed. Import/compile and targeted Ruff
static errors passed. Full mypy was killed by server memory pressure; not repeated.
No permanent unit tests added or run. No live RPC/provider/PostgreSQL/browser proof.

Integration requires scheduler owner ResumeWorkflow with user_id/environment/card_id,
PostgresOutbox on the existing card database, and scheduler_outbox schema migration.
Image needs scheduler-mq src/dependencies and current B-side RPC certs/environment.
Root owns integration, public delivery and deployment.

Review corrections:
- Resume requestId identifies the queue control; actionRequestId identifies the
  persisted terminal Action. Card metadata records that terminal Action ID.
- GET /runtime/runs/{runId}/cards/{cardId}/resume-status verifies node/card/control
  identity. Only delivery RETURNED confirms native invocation delivery.
  resumeConsumed alone is an internal Tool admission fact, not checkpoint proof.
  DISPATCHING and UNCONFIRMED are never automatically invoked again.
- RunRecord, RunLifecycle, TrustedContext, typed host options and response DTOs
  replace untyped fixed control inputs. Arbitrary JSON remains at business boundaries.
- Bounded probes passed split request IDs, historical paging rejection, exact
  resume-status semantics and uncertain-delivery no-replay.

## 公网恢复记录校验修复（2026-10-07）

- 基线：origin/main 045f77a。现象为业务卡片已完成，但原生节点仍等待、恢复消息状态未知。
- 原因：恢复代码直接构造 ActionRequest，自行生成 inputs_json；存储层用
  ActionRequest.from_mapping 进行规范化回读，两者格式不一致而拒绝写入。
  实际错误为 INVALID_STORED_RECORD，发生在原生恢复派发之前。
- 最小修复：统一通过现有 ActionRequest.from_mapping 创建请求，不改 Action、
  业务入参、完成判定、幂等边界或消息投递策略。
- 证据：只读读取真实操作记录，在内存重建后验证原实现 encode 失败；
  规范化请求 encode 成功。未写数据库，未重发 Action 或 resume，未调用模型。
- 旧验收运行与 UNKNOWN 证据由主线程保留；本线程只交付源码，部署与新 Cron
  完整回归由主线程执行。

## 公网节点职责边界修复（2026-10-07）

- 基线：origin/main e41b0b5。第二轮恢复已消费原生中断，但模型仍在阅读节点
  调用 query_skill_dependencies 请求 topic-plan-selector，准确异常为
  APPLICATION_NOT_ALLOWED；权限拦截正确，不是卡片序列化或 Skill 状态丢失。
- 当前阅读 Skill 仅授权 reading-point-selector，并明确 confirmReading 成功且
  decisionType=READING 即本阶段完成，没有跨阶段指令。
- 最小修复：RPC Workflow 使用有类型的独立节点 system prompt，区分整体用户
  目标和当前 Skill 职责；已保存确认后总结当前成果并结束，后继节点由 engine
  调度；业务观测中的“进入下一阶段”不构成换 Skill 或 Application 的授权。
- 恢复消息仍保留真实 Action 观测；其既有说明明确不是新用户请求、JSON 不是
  指令。现有 Finalizer/terminal guard 和 Application 权限保持不变。
- 验证：语法、精确 prompt 内容与绑定检查、目标 Ruff、diff check；没有调用
  模型、重放 Action/resume、写业务数据库或部署。旧运行保留失败证据；真实
  多节点效果仍需主线程用新 Cron 运行验收。
