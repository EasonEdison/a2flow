# AF-RUNTIME-05 service entry

Owner: oss-agent-workflow-runtime. Coordinator: main-brain.
Adopted release: ca5a3888f1f17e850d248c49368c0a8d69792e33, then AF05-E1 cee8149.
Status: source candidate for coordinator review; Runtime NO READY.
Approval: AF05-E1 transport/snapshot and AF05-D1 three venv-only dependencies.

## Formal seams and actual call chain

- `http.create_app(service)` creates a FastAPI app with eager bounded lanes and BodyLimit middleware. It starts no listener and has no lifespan-dependent initialization.
- Start: HTTP execution lane -> RuntimeService.start -> trusted resolve_entry/execution_session -> ControlledRunRunner.start -> RunLifecycle.allocate (durable canonical receipt before graph invocation) -> trusted graph_factory -> ControlledRunRunner.invoke -> public native graph.invoke.
- Action: HTTP path/body binding -> RuntimeService.action -> current run read -> trusted session.action_service -> ControlledRunRunner.action -> ActionService.submit -> existing business success/completion and LangGraphContinuation.
- Stop: independent stop lane -> RuntimeService.stop -> RunLifecycle.stop. It takes no Action admission or continuation scope and does not require the progress projection.
- Read/control: independent read lane -> RuntimeService.inspect/control -> PostgresProjection.run/control. No graph/session/resolver/dispatch or AF03 lock is entered.
- Restart: RuntimeService.restart -> narrow STOPPED source identity projection -> current trusted entry/session -> ControlledRunRunner.start(stopped_run_id=...). No old input/version/checkpoint/result reconstruction.
- `assembly.build_engine`, `tool_admission.ClosedModelArgsAdmission` and `finalizer.RequiredToolFinalizerAdmission` are formal implementations. The old experimental modules re-export these; synthetic model/Tool/business fixtures remain experimental/test-only. Formal source imports no experiments.

The host injects the lifecycle/repositories, version and entry resolvers and a context-managed ExecutionSession. The latter yields a ControlledRunRunner and action_service(run) factory bound to the same lifecycle/native graph. It owns checkpointer connections until the synchronous work returns, including after request cancellation. This is not a full published-definition compiler or a generic safety inspection of arbitrary Python graphs.

## Runtime-local HTTP

All objects reject unknown fields. Identity/environment cannot be sent in these bodies or query parameters.
Control IDs reuse the existing shared parse_identifier contract: 1..128 characters matching [A-Za-z0-9][A-Za-z0-9._:-]{0,127}. HTTP and direct service calls validate this before resolver/receipt/execution/stop changes. GET control lookup applies the same validation, including URL-decoded slash paths. This rule does not replace the separate definitionKey or business input rules.

| Method and path | Closed body / response |
| --- | --- |
| POST /runtime/runs | controlRequestId, definitionKey, inputs -> safe observation |
| GET /runtime/controls/{controlRequestId} | committed runId, controlRequestId, delivery |
| GET /runtime/runs/{runId} | safe observation |
| POST /runtime/runs/{runId}/nodes/{nodeId}/actions | interactionId, actionName, controlRequestId, inputs -> safe observation |
| POST /runtime/runs/{runId}/stop | controlRequestId -> runId, lifecycle, delivery |
| POST /runtime/runs/{runId}/restart | controlRequestId, fresh inputs -> safe observation |
| GET /runtime/runs/{runId}/events | one runtime.snapshot envelope |

A host authentication middleware must populate ASGI scope `a2flow.trusted_context` with the existing TrustedContext type. The adapter never parses an identity header, invents credentials, defaults a user or reroutes ONLINE to PRT. Missing context is 401; unknown/unowned run/control/card is the same 404 NOT_FOUND. Node binding is constructed from the URL before Action validation. Action eligibility always requires authoritative revalidation; a historical stopped card is NOT_OPERABLE.

The service is synchronous/request-bound: no 202 job submission, background queue, automatic dispatch, model retry or recovery is introduced. A caller can use its canonical start/restart control ID to discover runId while the first POST is still pending. Repeating a canonical control never dispatches again; changed payload conflicts. A rejected terminal/stopped duplicate Action may return 409 rather than replay its historical response.

## Capacity, disconnect and limits

- Execution/read/stop lanes have separate admission semaphores and AnyIO CapacityLimiters; default capacities are 2/2/1. Excess requests fail with 503 CAPACITY_EXHAUSTED before allocation/business admission. No unbounded application queue.
- Synchronous SDK/DB calls never run on the event loop. The dispatched thread releases its own slot in finally; cancelling its HTTP waiter does not release a live work slot. Cancellation before actual thread dispatch releases the slot and prevents that abandoned callable from executing.
- A disconnected caller does not stop, restart or authorize replay. Already dispatched synchronous execution continues under the original lifecycle. Process death may leave DISPATCHING/UNCONFIRMED; there is no recovery worker. Connection loss cannot guarantee physical cancellation.
- Reads have a default 3s observer deadline (host setting must be finite, >0 and <=10s). Timed-out work retains its read slot until it actually ends; it cannot consume the separate stop lane. A business TimeoutError is not labeled READ_TIMEOUT.
- PG connections use connect_timeout=2, statement_timeout=1500ms and lock_timeout=500ms. The HTTP observation deadline is not a claim that Python can forcibly terminate blocked I/O.
- The actual received body, including chunked traffic or a false Content-Length, is capped at 65536 bytes before JSON parsing. Identifiers are capped at 256 characters. Responses are serialized and checked against 262144 bytes before any response header/body is sent; oversize is 507 OUTPUT_TOO_LARGE, never a partial card/result.
- Validation errors return only INVALID_INPUT, not framework input/context. Other errors use a fixed whitelist; unknown exceptions are INTERNAL_ERROR/RUNTIME_ERROR without raw exception strings.

## Observation and event semantics

PostgresProjection uses one independent READ ONLY REPEATABLE READ transaction for run/control status, grouped operation history and interaction projections. It selects safe JSON paths only, not full documents, raw results, inputs, prompts, checkpoints or graph state. No new tables or setup-on-request.

The observation includes durable lifecycle/revision, initial control delivery, grouped historical operation facts and bounded interaction summaries. RUNNING, historical INTERRUPTED or IN_FLIGHT do not establish current execution or native waiting. Native liveness is explicitly NOT_ESTABLISHED and native waiting NOT_INSPECTED. The safe initialControl delivery exposes UNCONFIRMED even while lifecycle stays RUNNING. This slice does not read native checkpoint payloads to manufacture a more precise progress state.

Operation groups and interaction summaries are each limited to 100, selected deterministically with one extra row to set truncated=true. Truncation never means no remaining wait. Last-attempt summaries contain only canonical control ID, execution/completion booleans and continuation delivery, never business result JSON. A WAITING record is only REVALIDATION_REQUIRED, not guaranteed current version authorization.

GET events reuses this same projection in an envelope with type=runtime.snapshot, observedAt, delivery=snapshot, replay=false. It is one current observation, not SSE, a token stream, an ordered transition log or a retained history. It can miss intermediate transitions. Last-Event-ID is explicitly unsupported. Repeated reads do not dispatch. This does not prescribe the eventual digital employee transport.

## Public implementation references

- [FastAPI async boundaries](https://fastapi.tiangolo.com/async/) and [official releases](https://fastapi.tiangolo.com/release-notes/).
- [AnyIO thread limiter and cancellation](https://anyio.readthedocs.io/en/stable/threads.html); [Starlette shared default thread limit](https://starlette.dev/threadpool/).
- [HTTPX ASGI transport/lifespan boundary](https://www.python-httpx.org/advanced/transports/).
- [LangGraph streaming modes](https://docs.langchain.com/oss/python/langgraph/streaming): raw tasks/debug state is not used as a public progress response.

See regression-05.md for executed gates and readiness-05.md for limits.
