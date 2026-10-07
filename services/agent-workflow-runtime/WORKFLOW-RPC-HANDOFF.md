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
