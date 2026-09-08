# A2Flow internal Action Runtime — AF-RUNTIME-03

This is an importable internal Python library, not a published Action wire
contract or HTTP service. Its PostgreSQL adapter is implemented; live PostgreSQL
acceptance remains separately gated. It consumes the
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

38 deterministic tests cover admission, all asset-version mismatches, typed
policy evaluation, control deduplication, late stop/version changes, uncertain
execution/delivery, actual Deep Agent interruption/resume/Finalizer, two pending
same-name Tools and native A-waits/B1-to-B2 progression. The integration tests
reuse the existing project-authored Skill material test fixture.

Current limits: PostgreSQL Action repository and control ledger are implemented,
but 9 actual PostgreSQL/multi-process tests are not yet run (skipped offline).
No async continuation/executor adapter, automatic
delivery recovery, node retry orchestration, full stop/restart service, HTTP
ingress, live model or real business API. Async Finalizer rejection is tested;
that is not evidence for async Action execution. All tests are offline and
memory-backed or explicit protocol fakes; Runtime remains NO READY.

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

## Isolated test window (NOT YET AUTHORIZED)

The controlled script is experiments/runtime-phase1/runtime_phase1/runtime03_pg_window.py.
Only main-brain may release its execution window. From this worker repository:

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
