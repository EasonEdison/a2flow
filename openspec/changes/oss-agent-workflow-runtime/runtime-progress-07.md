# AF-RUNTIME-07 D1 source and bounded verification

Status: SOURCE REVIEW CANDIDATE. Not deployed, not runtime READY.
Baseline: db6f52c (formal D1 release over accepted AF06 e551afc).
Scope: read-only node display capture/history/stream; no steering or new business recovery.

## Implementation boundaries

- ProgressMiddleware uses the public ModelRequest.override(model_settings={stream: True})
  interface. DeepSeekChat accepts only boolean transport stream controls through bind_tools
  and consumes them before provider option validation. The native synchronous invoke,
  native messages/raw history, existing model/Tool admission and Finalizer remain authoritative.
- ProgressCallbacks emits only explicitly visible primary model text/reasoning and lifecycle
  labels. Prompt, Tool arguments/results and raw provider payloads are not display records.
  Auxiliary SDK model calls outside the explicit visible-model context are not automatically shown.
- ControlledRunRunner owns an observation segment per invocation; guarded business NODE
  entries receive distinct nested segments with trusted owner/run/node and NODE operation ID.
  Segments are observation identities, not retry counters. Action continuation receives a new
  segment; fresh restart receives a new run. Empty root scopes create no invented head.
- Tool started is inside existing RunAdmission and ClosedModelArgsAdmission. Tool returned,
  capture RETURNED/sealed and capture_end do not imply node or Workflow success.
- ProgressWriter is host-started, one daemon writer, nonblocking producer admission, no business
  scheduling. Startup has a bounded ready handshake to avoid losing the first callback to the
  writer startup lock. Database access never occurs while holding its queue condition.
- Defaults: text 1 MiB and records 2000 per segment; both serialized pending 4 MiB and 1024
  entries per process, including in-flight batches and reserved metadata capacity.
  Batch <=64, adjacent text <=8 KiB /250 ms, UTF-8 preserved. Per-segment reserve holds gap/seal.
  Display failures mark incomplete/unavailable; if persistence also fails, absent/unsealed
  capture remains unconfirmed. Shutdown has a finite join (default2 s, ceiling5 s).
- PostgresProgress owns two tables: capture heads and append-only display records. A private
  per-run catalog head orders capture creation without a business runtime_runs row lock.
  Per-segment head locks serialize sequence allocation and record/head atomic commit.
  Batch identity/digest detects duplicates, including empty seal batches. There is no global
  sequence commit cursor. Connect/query/lock timeouts and closed short transactions are explicit.
- Reads use existing trusted owner resolution and independent repeatable-read read-only
  connections. Keyset pages <=100 /256 KiB; exact run/node/execution cursor validation and
  future-cursor rejection precede SSE headers. Missing/corrupt committed rows reject instead
  of silently polling. NODE operation association is available in the capture catalog.
- Existing AF05 /events remains its original snapshot endpoint with closed query input.
  New paths:
  GET /runtime/runs/{runId}/progress
  GET /runtime/runs/{runId}/nodes/{nodeId}/executions/{executionId}/history
  GET /runtime/runs/{runId}/nodes/{nodeId}/executions/{executionId}/stream
- SSE reads committed pages only; no graph handle or execution worker. Poll >=500 ms,
  heartbeat10 s, <=8 subscriptions/process, send timeout5 s, lease60 s; cancellation,
  transport disconnect and timeout release subscription capacity. Last-Event-ID resumes
  the same execution segment; it cannot be combined with after.
  Stream reports nodeCompletion=false with a statusReference; actual status remains AF05.

## Explicit host composition

Host authentication supplies a2flow.trusted_context, not client-selected owner fields.
Host schema lifecycle explicitly calls PostgresProgress.setup only under its own deployment
authorization; capture and subscription never create schema or listeners. Host lifespan starts
one ProgressWriter(repository), passes it to build_engine(progress=writer), passes the read
repository to RuntimeService(progress=repository), then calls bounded writer.shutdown.
No automatic server startup, secret resolution, migration or production fallback is introduced.

## Verification evidence

Final bounded command: existing installed Python3.11 environment, LANGSMITH_TRACING=false,
PYTHONDONTWRITEBYTECODE=1, PYTHONPATH includes contracts/src, skill-registry/src,
agent-workflow-runtime/src and tests, experiments/runtime-phase1 and its tests.

python -m unittest test_progress_sdk test_progress_writer test_progress_controlled test_progress_http test_postgres_progress test_progress_nodes test_progress_interaction.ProgressInteractionTest test_model_config test_model_content test_deepseek_model test_deepseek_sdk_contract test_http test_service test_lifecycle test_native_stop test_controlled_interaction test_postgres_projection -q

Result: 105 PASS, 3.972 s; git diff --check PASS.
All new SDK fixtures select deepseek-v4-flash with typed SDK SSE over injected MockTransport.
Historical accepted AF06 characterization fixtures remain unchanged.

New gates cover:
- actual installed SDK increment before synchronous Agent return, UTF-8 display only;
- real build_engine + ControlledRunRunner Tool admission/native Finalizer, closed args,
  stopped-before-start and stopped-late Tool return without successor model/Finalizer;
- real waiting/Action continue/fresh restart, distinct observation segments and original
  stop/interaction checks; actual parallel LangGraph business NODE identity association;
- writer dual limits, in-flight accounting, coalescing, reserved gap, invalid payload,
  persistence failure health, finite blocked drain and no invented empty head;
- ASGI auth/cursor preheaders, whole frames, reconnect, snapshot compatibility, slow send,
  lease/disconnect cleanup and subscriber capacity/release (no listener);
- scripted PostgreSQL connection protocol: owner scope, read transaction/close, byte pages,
  future cursors/integrity, head lock, single batch insert, rollback, catalog ordering
  and duplicate/empty-seal batch identity. This is NOT live PostgreSQL transaction evidence.

## Readiness and remaining gates

Source/offline gates: PASS for the named fixtures only.
Live PostgreSQL DDL/constraints/concurrent transactions/crash persistence: UNVERIFIED.
Real provider/network streaming, host lifespan wiring, deployment and downstream UI: UNVERIFIED.
No dependency changes, credentials read, live model call, PostgreSQL startup, listener, deployment,
server-main integration or GitHub push performed by this slice.

Main-brain reviews the worker fixed SHA before any exact integration release. D2 steering is
a later slice. Do not label source tests or sealed display records as business/runtime READY.

## P2 review correction after e3be4cf

Independent main review found a delayed-emitter race after append failure and segment removal.
The writer now rechecks scope.unavailable while holding the queue lock, before lookup/_new.
Failure remains terminal for that execution even if an emitter passed its outer check earlier.

test_failed_segment_cannot_be_recreated_by_already_admitted_emitter pauses exactly after the
outer check, waits for first append failure, no-head health update, segment removal and worker
idle/lock release, then resumes. The former e3be4cf implementation loaded in memory fails
deterministically (expected1 append, observed3); no worktree rollback was used.
The fixed code makes only the first failed append, no subsequent append/seal, and releases all
segment/queue accounting. Final same bounded suite plus this regression:106PASS4.420s.
Live PG/provider/deployment and main integration remain outside this correction.
