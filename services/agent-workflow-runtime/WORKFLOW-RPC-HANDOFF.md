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
