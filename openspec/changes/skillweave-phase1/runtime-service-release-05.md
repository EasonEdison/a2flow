# AF-RUNTIME-05 — Minimal Runtime service entry

Coordinator: main-brain. Implementation owner: oss-agent-workflow-runtime.
Date: 2026-09-08. Baseline: AF-RUNTIME-04, ba7c1d269e3096768cddd19e7ee9bd3aedfc0c14.
Status: user-authorized scope; AF05-E1 transport/source implementation approved below. Dependency installation remains separately reviewed after the constrained resolver report.

## Outcome

Expose the accepted Python execution core through a minimal backend-callable service and HTTP adapter, with inspectable progress and execution output. This slice does not claim a complete digital employee, public deployment, live model integration, or full configurable Workflow runtime.

The user approved this as the immediate next slice. Other six domains remain paused. Main-brain owns ordinary implementation decisions, review, synchronization and server/GitHub integration; no user-mediated worker coordination is needed.

## Included

1. One formal service assembly/facade for start, inspect, node-bound Action, stop and fresh restart from a STOPPED source. Reuse RunLifecycle, ControlledRunRunner, ActionService and native LangGraph persistence/interrupt APIs. Production modules must not import experiments or test fixtures.
2. A thin HTTP adapter around that facade. Use a mature maintained framework and its documented public interfaces after checking installed dependencies. Propose exact routes, request/response shapes and dependency changes together; these are Runtime-local interfaces, not a new shared platform wire version.
3. Trusted identity/environment and configuration/graph factories supplied by the host backend. Reject missing trusted context; a request body, query or arbitrary header cannot grant userId/environment authority or select raw graph/checkpoint/policy internals. No invented token system or hardcoded default identity.
4. Read-only run/node/interaction projections needed for progress and card operations. Distinguish durable run lifecycle from actual native graph waiting/completion and unconfirmed control delivery. Do not expose raw checkpoint, prompts, private Tool results, internal exception strings or credentials as a status payload.
5. Minimal execution event output using accepted runtime facts and public SDK mechanisms. The owner must explicitly propose whether output is a live stream or bounded snapshot/events, along with disconnect, ordering and retention limits. Do not claim durable replay or guaranteed delivery without implementation and evidence; no new message broker or second scheduler.
6. Necessary migration of reusable experimental assembly into the formal package, with explicit synthetic fixtures kept in tests/experiments. A trusted injected graph factory is sufficient for this slice; a full M-published definition compiler is not required.

## Invariants

- Existing Tool admission, configured Action success/completion, Finalizer, current-version reset policy, userId/environment isolation and control request deduplication remain authoritative.
- Long model/Action/graph calls must not make stop or status unreachable behind an application-wide lock/event loop. Stop only prevents new admissions; already admitted work may finish and record facts without advancing a stopped run.
- Make the durable allocated run identity discoverable while start is still executing, through a reviewed owner-scoped control lookup or initial response event. Do not require waiting for the complete graph invocation before the caller can identify and stop its run. Execution saturation must not consume every control/read capacity slot.
- A transport disconnect is not user stop, successful completion, permission for replay, or a fresh execution request. Document the implemented lifetime clearly. Do not add automatic recovery or redispatch after uncertainty.
- Start/restart client retries retain canonical request identity; changed payload with reused requestId is rejected. No cross-run business idempotency, compensation, reconciliation, generic Skill retry or background recovery.
- Use bounded request/output sizes and explicit error projections. Unknown/unsupported fields and forged node/interaction ownership must fail before external execution.
- PRT and ONLINE remain separate trusted scopes; no ONLINE-to-PRT routing. Existing asset resolution ports remain injectable, not a claim that all publication databases are complete.

## Ownership and execution

- Runtime owns services/agent-workflow-runtime/, necessary experiments/runtime-phase1/ verification, and openspec/changes/oss-agent-workflow-runtime/.
- Main-brain owns this release under openspec/changes/skillweave-phase1/ and any shared root dependency decision. Do not edit other domain sources, shared contract candidates or another task checkpoint.
- Work only in the existing exclusive server worker and integration worktrees, inspect status and fetch/merge origin/main before edits/delivery; preserve all unrelated changes.
- Source work and in-process transport tests are authorized. No listening server, PostgreSQL window, container startup, provider call, secret configuration, system dependency replacement or deployment is authorized by this document.
- Runtime first returns baseline adoption, conflicts, exact owned files and the concrete transport/event proposal. Coordinator reviews it without another routine user kickoff. Stable source is pushed to the worker branch for review before target integration release.

## Focused acceptance

- Exercise real in-process HTTP handling, not only direct facade calls; synthetic model/business/configuration ports are explicitly labeled.
- Start -> display/wait -> valid completing Action -> continuation -> final result through the formal assembly; no production import of experimental code.
- A pending long execution can be inspected/stopped through another request; late completion does not resume or mark success after accepted stop.
- Missing/forged owner/environment, wrong run/node/card, stale version, malformed input and stopped-card requests fail without business invocation; duplicate control request never repeats execution.
- Fresh restart uses current fresh inputs/configuration and a new run/thread, without old business/checkpoint/result reuse.
- Event/progress projections preserve actual wait/failure/stop meanings; disconnect and repeated reads do not replay business or pretend completion. Verify agreed bounds and error redaction.
- Keep AF04 relevant gates passing; record exact commands, fixed source, passed/skipped gates and transport limitations in regression/readiness. No new real PG claim without its separately reviewed window.

## Deferred

Real model/provider and real business API integration; public authentication product; digital employee UI/card layouts; complete Workflow compiler/AI routing/skip/retry/context retrieval; M platforms; durable event bus and distributed job scheduling; async engine conversion solely for HTTP; Docker Compose deployment. These remain later slices rather than being silently bundled here.

## AF05-E1 coordinator review — 2026-09-08

The owner acknowledged ca5a388 with no conflicts and an unchanged clean worker. The following Runtime-local implementation is approved, without changing shared platform contracts:

- Formal service/assembly/projection modules plus a FastAPI 0.141.1 HTTP adapter. Official release notes confirm this version. Do not add standard extras, Uvicorn or SSE packages for this in-process slice.
- POST /runtime/runs accepts controlRequestId, definitionKey and inputs. GET /runtime/controls/{controlRequestId} provides the owner-scoped committed receipt/runId during long start. GET /runtime/runs/{runId} returns a safe current observation. POST /runtime/runs/{runId}/nodes/{nodeId}/actions accepts interactionId, actionName, controlRequestId and inputs. POST stop accepts controlRequestId; POST restart accepts controlRequestId and fresh inputs under the run route. Entry node and all execution bindings remain trusted-backend supplied.
- GET /runtime/runs/{runId}/events returns one bounded runtime.snapshot observation with observedAt, delivery=snapshot and replay=false, reusing the same safe projection as GET run. It is not SSE, token streaming or historical replay, and cannot guarantee observing intermediate transitions. This slice does not prescribe the eventual digital employee transport.
- Request-bound synchronous execution is offloaded using public AnyIO thread APIs. Keep execution, read and stop capacity independent and bounded; reject excess execution before durable allocation/admission. Client disconnect does not stop accepted work or release its capacity while it is still running. No background job queue or automatic redispatch.
- Actual received request bytes are capped at 64 KiB, response bytes at 256 KiB, identifiers at 256 characters. Unknown fields fail. Validation errors must not echo default framework input/context. Collection limits are explicit; truncation or unavailable data must never imply no waiting or success. Do not silently trim a card/result.
- Projection uses independent short committed reads, no admission/continuation/advisory/update locks, raw results or checkpoints. Keep lifecycle and observed wait/delivery states separate; stopped interactions are historical and non-operable. State any non-atomic multi-query observation limit explicitly. Unknown/unowned resources do not leak existence.
- Runtime may author service-local requirements and tests. Dependency resolver dry-run is authorized against the existing project venv while constraining every already installed distribution to its current version. Report exact new packages, sources, versions, size and any replacements before installation; no system or root dependency mutations.
- Tests cover actual in-process ASGI requests, concurrent long-call/control/read barriers, actual disconnect/cancellation, identity/size/error redaction and no duplicate dispatch. HTTPX ASGITransport alone does not run ASGI lifespan; explicitly exercise lifespan if the adapter relies on it. No socket/proxy/real PostgreSQL/provider claim from these tests.

Public references reviewed by the coordinator: [FastAPI releases](https://fastapi.tiangolo.com/release-notes/), [AnyIO thread and cancellation semantics](https://anyio.readthedocs.io/en/stable/threads.html), [HTTPX in-process transports and lifespan boundary](https://www.python-httpx.org/advanced/transports/).
