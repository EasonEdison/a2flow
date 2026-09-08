# A2Flow internal Agent/Workflow Runtime — AF-RUNTIME-04

This is an importable internal Python library, not a published Action wire
contract or HTTP service. Its PostgreSQL adapter is implemented; live PostgreSQL
acceptance passed the bounded AF-RUNTIME-03-PG-W1 window; product readiness
and integration remain separately gated. It consumes the
approved Skill/Policy subset and public LangGraph APIs.

The trusted backend supplies InteractionRepository, ConfigurationPort,
ExecutorPort and a LangGraphContinuation bound to its compiled graph.
The render resolver additionally supplies the full recorded asset-version
closure in recordedVersions. All effective versions must come from the current
PRT/ONLINE backend resolver. An Action request cannot select the backend owner,
environment, graph thread, operation reference, policy or completion result.

ActionService.submit accepts exactly runId, nodeId, interactionId, actionName,
controlRequestId and inputs. It validates ownership and active wait state,
compares the full recorded/current version closure, resolves an allowed Action,
validates configured inputs, then saves an EXECUTING control reservation before
calling the injected executor. Configured result validation and the reviewed
SCHEMA_VALID or JSON_POINTER_EQUALS policy determine business success. Pointer
evaluation reuses installed jsonpointer 3.1.1; booleans are not numbers and a
missing path is not JSON null. Unsupported policies are rejected during config
construction, before executor dispatch.

A failed result or successful non-completing Action stays waiting. Successful
completion records its actual result and resumes only the matching native
interrupt ID. The resume payload contains a saved controlRequestId reference;
the replayed Tool rechecks saved facts, owner, active state and versions. It
marks resume_consumed only after this verification. The graph keeps the original
render context/controlRequestId: an Action request does not regenerate the card.
Direct forged resume success values produce another native wait; stopped or
stale-version errors remain observable.

The Deep Agent assembly requires a terminal guard when using Action-enabled
render Tools. Both sync and async Finalizer paths call the guard, so another
successful Tool with the same name cannot hide a required pending interaction.
The original use_skill evidence survives native checkpoint continuation, while
a new invocation still clears it.

Repository scope serializes admission per trusted user/environment/run without
requiring reentrancy. save commits each record independently
of later exceptions. continuation_scope is a separate run-scoped delivery lock;
native graph execution happens outside the admission lock because Tool replay
may run on an SDK worker thread. A real adapter must coordinate stop acceptance
with the admission boundary. PostgresInteractionRepository implements these
scopes with dedicated session advisory locks and independent short save transactions.
All get/for_run/for_node/save calls require a matching trusted scope. The internal
get(key, owner) signature prevents identity inference from an unscoped record.
The in-memory ports remain explicit test fixtures, never an automatic fallback.

Saved Attempt records distinguish business_success, interaction_completed
(the configured completion decision), and resume_status. NOT_REQUESTED means
no continuation was attempted, DISPATCHING means a dispatch was reserved,
RETURNED means the graph invocation returned (other branches may still wait),
and UNCONFIRMED preserves an exception/unknown delivery. Duplicate identical
control requests return the saved record, including UNCONFIRMED, without
business or graph replay. Historical EXECUTING is conservatively returned as
EXECUTION_UNCONFIRMED without altering or redispatching the durable reservation.
Reusing an ID with changed payload is rejected.
An executor exception remains EXECUTION_UNCONFIRMED because a side effect may
already have occurred. Before reserving a new control, a same-owner/environment/run
scan rejects while any EXECUTING, EXECUTION_UNCONFIRMED, DISPATCHING or UNCONFIRMED
record exists. DISPATCHING can be healthy in-flight, not a confirmed failure.
The rejection writes no new reservation. The current completion Tool is allowed;
normal later cards proceed after RETURNED. Fresh request IDs are independent user controls; this
does not claim business exactly-once, compensation or cross-run deduplication.

## Run focused tests

From the server worker repository with its existing Python 3.11 environment:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=packages/contracts/src:services/agent-workflow-runtime/src:services/skill-registry/src:experiments/runtime-phase1:experiments/runtime-phase1/tests \
/home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python \
  -m unittest discover -s services/agent-workflow-runtime/tests -v
```

The AF03 baseline's 38 deterministic tests cover admission, all asset-version mismatches, typed
policy evaluation, control deduplication, late stop/version changes, uncertain
execution/delivery, actual Deep Agent interruption/resume/Finalizer, two pending
same-name Tools and native A-waits/B1-to-B2 progression. The integration tests
reuse the existing project-authored Skill material test fixture.

Current limits: PostgreSQL Action repository and control ledger are implemented,
and 9 actual PostgreSQL/multi-process tests passed AF-RUNTIME-03-PG-W1.
Default offline discovery still skips these 9 tests without an authorized DB.
No async continuation/executor adapter, automatic
delivery recovery, node retry orchestration, full stop/restart service, HTTP
ingress, live model or real business API. Async Finalizer rejection is tested;
that is not evidence for async Action execution. The 38 ordinary tests are offline, memory-backed or explicit protocol fakes;
the separate 9-case window used real PostgreSQL. Runtime remains NO READY.

References: [LangGraph interrupt replay and resume mapping](https://docs.langchain.com/oss/python/langgraph/interrupts),
[jsonpointer resolver](https://python-json-pointer.readthedocs.io/en/latest/tutorial.html).

## PostgreSQL storage and lock boundary

Import PostgresInteractionRepository from agent_workflow_runtime.postgres.
Call setup() explicitly during authorized schema setup, not on request ingress.
Two Runtime-owned tables use (user_id, environment, run_id, node_id,
interaction_id), adding control_request_id for control identity. Interaction JSON
and control state save atomically; schemaVersion=1 and closed decoding preserve
immutable canonical requests. Completion/dispatch/consumption must reference an
actual successful completing Attempt; corrupt stored state fails closed.

Every scope creates an autocommit connection, holds a session advisory lock and
closes the connection on exit. Each save is a separate transaction, committed
before the executor. Admission and continuation have separate SHA256-derived
64-bit lock namespaces. Collisions only serialize unrelated work. No pool,
auto-reconnect or long transaction around executor/graph exists. Connection
and lock waits are 5 seconds; statements have a 10-second timeout. SDK Tool
threads use new admission scopes, never the continuation connection.

check_scope verifies all thread-local owning sessions still hold their locks,
including the continuation session when delivery status takes admission.
A detected loss poisons the scope; no replacement session continues it.
RETURNED is written only while continuation is still held and checked. However,
a lost connection CANNOT cancel/fence an already in-flight business operation or
graph. There is a check-to-dispatch race, not a distributed atomicity guarantee.
The graph may reach JOIN after lock loss while its Action remains DISPATCHING.
New Actions are gated; no automatic takeover, reconciliation or recovery exists.

The opt-in PG tests use independent subprocesses and durable executor/Skill/B1/B2
counters, including loss of the exact owned lock backend and exact owned worker.
The real native graph uses official synchronous PostgresSaver.from_conn_string
(autocommit, dict_row, explicit context-managed lifecycle), not AsyncPostgresSaver.
Connection observation includes saver/scopes/workers/observer at 5 ms intervals;
it reports an observed peak, not a guaranteed transient maximum.

## Isolated test window (single W1 completed; no standing authorization)

The controlled script is experiments/runtime-phase1/runtime_phase1/runtime03_pg_window.py.
Only main-brain may release a new execution window; W1 does not authorize reruns. From this worker repository:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=experiments/runtime-phase1 \
/home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python \
  -m runtime_phase1.runtime03_pg_window --authorized-window
```

The same command with --cleanup performs ownership-validated exact cleanup.
The flag is not authorization. Default unit discovery does not start PostgreSQL.
The script bounds the window to 15 minutes, runs no public listener and creates
only its named container/volume/private directory (plus .tmp parent if absent).
It removes those resources in finally; a newly pulled image is removed only if
Docker allows it without force. Existing/shared images and unrelated data stay.

### AF-RUNTIME-03-PG-W1 observed evidence

On fixed source 660db6a7dffe0c6f270f3e0c84767aab36d87f70, the single authorized
PG 17.11 window passed all 9 independent-process tests in 87.651 seconds.
Overall window: 105.14 seconds including pull. Observed connection peak: 4
(5 ms samples including observer; role hard limit 8). Minimum available host
memory: 1,039,332 KiB; swap growth: 0 KiB; data high-water sample: 49,792 KiB.
At teardown, runtime sessions=0 and advisory locks=0. The exact container logs
contained neither of this window's two plaintext secrets (PASS; logs not echoed).
The container, volume, private socket/secret directory and newly pulled image
were removed. No secure-erase claim. Post-cleanup readback found no 5432 listener.
These are bounded synthetic business/scripted-model results, not live-provider,
production deployment, business exactly-once or automatic recovery evidence.

## AF-RUNTIME-04 source candidate: synchronous stop and fresh restart

This section supersedes earlier statements that stop/restart is entirely
unimplemented. AF04 is source/offline-tested only: its three new PostgreSQL
record types have NOT run in a live database window. AF03's nine PostgreSQL
passes do not prove AF04. Runtime remains NO READY.

Import RunLifecycle/RunStoppedControl from agent_workflow_runtime.lifecycle,
PostgresRunRepository from agent_workflow_runtime.postgres_lifecycle, and
ControlledRunRunner/RunGraphBinding/guarded_node/guarded_router from
agent_workflow_runtime.native_control. Backend-owned configuration, graph
factories and trusted identity are required; there is no HTTP handler or UI.

AF04 assembly must bind the same RunLifecycle to the ActionService,
LangGraphContinuation, RunGraphBinding and ControlledRunRunner. Call Actions
through ControlledRunRunner.action, which validates this complete chain before
a business executor can run. The old ActionService/adapter path without a
lifecycle remains solely for the separate AF03 API/tests; it is not AF04 stop
coverage. Raw compiled graphs are rejected at the AF04 runner entry.

A binding is a trusted assembly contract, not an inspection or generic safety
proof for arbitrary Python graphs. Factories must guard every owned business
node and router; nested Skill calls do not grant later nodes blanket admission.
Deep Agents require RunAdmissionMiddleware and inherited RunModelCallbacks
(provided by the runner). The experiment build_engine_spine_probe accepts
run_lifecycle and returns the explicit binding. Its Finalizer is also admitted.
Keep public SDK summary behavior: model callbacks guard each actual main or
summary attempt, including the gap before ordinary Exception retry.

The runner and guarded Workflow nodes bind a trusted ContextVar, carried by
public RunnableConfig/thread context propagation, for actual model/Tool fact
node_id. Internal SDK "model" names and model-supplied args are not identity.
run.context(node_id) constructs a backend-selected node scope. The two-parallel-
Workflow-node/inner-agent test verifies each fact matches its actual node.

STOP linearizes at its committed run-row transition against each individual
admission. A successfully admitted call may start/finish after that instant;
there is no atomicity claim between a database commit and a network/Python first
instruction. Later nodes/routes/model rounds/Tools/Actions/retries/Finalizer and
success admission reject. STOPPED closes progression, not physical cancellation:
snapshot exposes still-pending admitted model/Tool/Action calls. Late actual
outcomes are saved even after STOPPED, without undoing business writes.

Run state exists without any card. Run/control/operation facts are separate
Runtime-owned tables with closed schemaVersion=1 decoding. The operation ledger
is audit only, not a scheduler or recovery queue. STOP uses an independent,
short row-lock transaction; it never takes the long AF03 admission session lock.
Actions take AF03 admission before the short Run lock, save EXECUTING on the
independent AF03 connection, then commit the Run admission before dispatch.
A partial/uncertain commit must not dispatch; no savepoint is called durable.
Independent-connection visibility and multi-process races still require AF04 PG
verification; in-memory fixtures are not that proof.

Only ControlledRunRunner maps RunStoppedControl (BaseException) to a matching,
already stored STOPPED run. Ordinary Exception retries do not catch this signal.
An in-process observer retains other fatal BaseExceptions seen at owned
boundaries because a synchronous native executor can otherwise suppress a late
sibling fatal after an earlier stop. KeyboardInterrupt/SystemExit/custom fatal
tests prove they are re-raised, not relabeled STOPPED. No cross-process fatal
transport or full async execution guarantee is claimed.

Restart in this slice accepts a STOPPED source, creates new run/thread/context
and current configuration/input, and invokes a fresh graph factory. This does
not permanently prohibit future support for other source states. Only the old
lifecycle identity/status/definition association is projected; old input,
versions, interactions, checkpoints and operation outcomes are not read.
Same canonical control returns the assigned run without another factory/invoke;
changed payload rejects. Startup uncertainty remains saved as UNCONFIRMED and
is not replayed automatically. A run snapshot status is lifecycle state, not a
claim that an uncertain startup completed.

Latest offline discovery: 69 service cases = 60 PASS + 9 AF03 PG SKIP;
38 experiment cases PASS. See the AF04 section of the owned regression/readiness
documents for exact commands, evidence and pending gates. The AF04 window script
runtime_phase1.runtime04_pg_window and eight opt-in process cases are prepared,
not executed. They reuse the reviewed AF03 safety implementation through an
immutable WindowSpec. The owned pg-window-04.md records exact targets, hashes,
budget and offline preparation evidence. A new exact-script review and separate
single-executor release are mandatory.
