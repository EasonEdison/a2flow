# AF-RUNTIME-07: node progress streaming and read-only history

Date: 2026-09-09. Coordinator: main-brain. Owner: oss-agent-workflow-runtime.
Base: accepted AF06 e551afc12fb7670ab26d8760a06ab83bd26ee144.
Status: user authorized continuation; coordinator reviewed the owner's existing-source/SDK proposal and releases the bounded source/fixture implementation below. Source delivery is not live-provider, PostgreSQL or frontend acceptance.

## Coordinator implementation decision D1

Owner returned clean e551afc baseline and actual callback/control/storage seams. Adopt the following engineering limits, not new business behavior:

- Preserve synchronous ControlledRunRunner and existing admission/Finalizer. Add public observation callbacks. Verify public ModelRequest.override(model_settings) streaming against installed SDK and the project DeepSeek adapter before broad wiring; explicitly consume transport-only stream controls, preserve closed provider options and original native final messages. A callback alone does not guarantee invoke becomes streamed. Auxiliary/internal model invocations are not automatically user-visible.
- `executionId` is a trusted Runtime-private observation segment for a business node activation/continuation, not a retry count or provider-generated identifier. Retain NODE operation association when available. Nested Agent model/Tool callbacks inherit the segment; parallel business nodes do not. A later continuation has a new segment under the same run/node; fresh restart has a different run. Missing trusted context is explicit capture-unavailable, not guessed attribution.
- Two PostgreSQL record types: capture head and append-only display records. Allocate seq inside the capture-head short transaction and commit head/batch atomically. Do not use a global sequence as a commit watermark. Trusted duplicate batch identity may deduplicate observation writes, never business operations. Foreign-key/owner/environment scoping and matching keyset indexes are required.
- Approved initial caps: 1 MiB displayed text and 2,000 records per execution segment; process capture queue capped at BOTH 4 MiB serialized pending data and 1,024 entries; batch at most64 records; adjacent text coalesces up to8 KiB or250 ms, flushing at model/tool/status boundaries. Account for bytes rather than relying only on queue length, avoid splitting UTF-8 characters or SSE records. These caps affect the display copy only; do not truncate AF06 native history retention under this release.
- One bounded process-owned observation writer is allowed, not a business scheduler. Nonblocking admission to its queue; own short database transactions; finite drain/shutdown and no unbounded threads/maps per run. Capture metadata and incomplete/gap reporting need bounded reserved space or deterministic head state even when text quota is exhausted.
- On display overflow stop further text capture for that segment and explicitly report truncated/incomplete. On write failure stop that segment's capture and expose unavailable/incomplete; do not replay business calls or raise an observer failure as a business failure. If the database cannot persist an error marker, an unsealed/absent capture remains unconfirmed, never complete. Authenticity/ordering/integrity errors must not silently resume writing an apparently contiguous stream. Existing operation fact persistence semantics remain unchanged.
- Keep `/events` snapshot unchanged. Add Runtime-local catalog/discovery of node execution segments, authorized keyset history and per-segment SSE; exact route/field names may follow existing style, but all must carry owner-checked run/node/execution identity. Catalog is needed to discover segments while POST start/action still runs; reuse existing control receipt for run discovery. Do not wait for POST completion or start a second execution.
- History pages at most100 records/256 KiB; cap individual frames to remain compatible. SSE reads the same committed cursor sequence, polling no faster than500 ms, heartbeat10 s, default subscriber capacity8 and send timeout5 s. Each subscription has a finite lease (initial60 s) and advertises reconnect using its last delivered committed record ID. No database connection spans client waits/sends, and stop capacity is independent. Query parameters are narrowly validated only on the new endpoints, not relaxed globally. Reject malformed/future/cross-segment cursors before stream headers where knowable; subsequent faults emit fixed safe error if possible, otherwise disconnect without false completion.
- Sealed observation is not a successful node. Returned Tool/model/NODE operation cannot manufacture business completion; only existing authoritative lifecycle/interaction evidence supplies displayed status. Interrupted/waiting/late-stopped paths and same-node continuations require explicit tests. Polling/history must never open an execution session or call a model/Tool/Finalizer.

Runtime may now implement within owned paths with zero new dependencies. Provide one stable worker commit plus focused evidence for root review; no main integration until source acceptance. Stop and report an actual SDK conflict if these public extension points cannot preserve behavior, rather than adding a second Agent loop. PG/live-provider/socket windows remain separately bounded and unreleased by this source decision.

## Outcome and approved product boundary

Expose observable progress while a Skill node is still running, plus saved authorized details that can be read without executing anything again. Feed the approved collapsed/expanded node UI without implementing that UI here.

- While running, UI can show provider-returned reasoning content and true Tool/status events; no fabricated progress or hidden model internals.
- At node end, truthful status/summary and saved details support collapse/reopen. Results and valid A2UI remain separately available; do not replace them with process text.
- Waiting for interaction is not completion. Model stream termination, model response or Tool return cannot declare Skill/Workflow success.
- Preserve stopped/failed/skipped/unknown states and late in-flight facts. An observer disconnect is not stop, retry or restart.
- D2 node-bound input is approved product behavior but a subsequent engineering slice: no input queue, steering, second Agent invocation or changed control semantics in AF07.

## Exclusive implementation ownership

- Runtime owns services/agent-workflow-runtime/ and its change-local progress07 design/regression/readiness/tests. Reuse existing public SDK, controlled runner, Action service, trusted context, PostgreSQL patterns and bounded HTTP lanes.
- main-brain owns this release, synchronized product-baseline addendum, shared/root packaging changes if needed, review and GitHub delivery. Do not edit shared schemas or unowned modules without a bounded dependency decision.
- All application source/Git stays in the assigned server worker; fetch/merge latest origin/main before source changes. Return reviewed fixed source and gate evidence before main integration.
- Digital employee and other six domains remain paused. No editor, BFF, UI, business adapter, authentication provider, new scheduler or transport platform.

## Required engineering properties

1. Use public LangGraph/Deep Agents streaming or public callbacks. Preserve original execution/history result and stop/Finalizer enforcement. Validate against installed versions, including nested model/summary/tool calls; no SDK source/private serializer patch.
2. Bind each visible event to trusted environment/user, Workflow run, outer business node and this node execution. Framework model/tools names, model-provided IDs and client userId are not trusted bindings. Concurrent nodes and fresh runs must not cross-contaminate. IDs/order must distinguish replayed observation from new execution.
3. Minimal typed display projection: reasoning/text deltas allowed by policy, true tool/model operation lifecycle, waiting and authoritative outcome references. Do not emit whole model/tool inputs/results, native opaque payloads, credentials, arbitrary exceptions or unrestricted checkpoint/debug streams. AF06 native retention is separate from display.
4. Keep PostgreSQL as the durable observation source; bounded batching/coalescing is preferable to one commit per token. Saved records/history must survive observer reconnect and process replacement, without recovery of Skill execution. Exact caps/flush interval/byte accounting/cursor schema require review; do not silently drop text or claim a partial log is complete.
5. Read-only authenticated paginated history and an incremental observation endpoint. Preserve existing snapshot endpoint semantics or version the new entry explicitly. Verify cursor/order boundaries, cross-owner rejection and catch-up/live handoff. Authorization must happen before streaming headers; a stream cannot invoke the graph/model/tool.
6. Subscribers must not hold admission/control locks or lifetime database connections. A slow/disconnected client cannot stall the producer, consume unbounded memory or occupy stop capacity. Observe reads and stream leases need finite time/capacity; cleanup on normal close/error/cancellation. Do not add Redis, Kafka, SQLite or a generic job queue.
7. Progress failures must be explicit, not fake business failures/success. Before choosing behavior for unavailable persistence or capacity exhaustion, present the bounded failure policy to main-brain: no silent fallback, no raw sensitive exception and no retroactive change of recorded business facts.
8. Existing synchronous start/action may stay synchronous. Show how clients obtain the allocated run ID through the existing control receipt while execution is active; do not require waiting for start completion before observing. Do not create an unowned background job runner merely to add SSE.
9. Carry waiting/complete states from real lifecycle/interaction/graph evidence, including Action continuation. Do not derive Skill completion from generic NODE wrapper return without accounting for interrupts. Do not broaden unsupported retry/skip/stop/restart behavior.

## Acceptance gates

- Actual installed SDK + synthetic streaming transport: visible increment is observed before model/node completion, including provider reasoning and actual Tool start/end.
- Two parallel business nodes and repeated node execution: trustworthy attribution, ordered records, no leakage/mixing; same provider ID cannot merge distinct invocations.
- Real waiting/Action continuation and stopped in-flight cases retain the accepted control boundaries. Observation never runs Finalizer or business Tools.
- History paging/reconnect resumes observation without gaps/duplicates being presented as new progress; unauthorized/invalid/future cursors reject clearly. Partial/incomplete history is labeled.
- Slow subscriber, disconnect, time limit, output cap, writer/reader failure and cancellation release resources and preserve business fact semantics.
- Relevant regression gates for existing control/Action/model features; do not rerun unchanged unrelated suites repeatedly.
- PostgreSQL implementation tested with explicit offline checks; actual database/process validation requires a separately reviewed single-executor window. Never label mocked SQL as durable/multi-instance proof.
- HTTP in-process/ASGI stream evidence is distinct from actual socket/proxy/browser delivery. Real model call evidence is a further bounded gate, not implied by synthetic chunks.

## Real provider and infrastructure boundaries

User supplied a host-local credential and selected deepseek-v4-flash. Do not print/read the secret into task outputs, copy it to Git or change host security. Keep SDK retries=0; no Pro/provider fallback. This first source/fixture slice does not launch live requests, a database, a listener or deployment. Prepare a bounded command separately when needed; main-brain coordinates one executor. No dependency installation without explicit reviewed delta.

## Public references

- https://docs.langchain.com/oss/python/langgraph/streaming
- https://docs.langchain.com/oss/python/deepagents/streaming
- https://docs.langchain.com/oss/python/langchain/middleware/custom

Use these to identify supported interfaces, then verify the exact installed SDK behavior. Do not introduce a new runtime abstraction merely to mirror documentation examples.
