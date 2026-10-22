# Async startup verification

Baseline `02e0ff6`; final behavior and 33-file quality candidate `814a5980cc498820b730a2f940f0142578d8b223`. Documentation follow-ups do not change those tested bytes.

## Actual creation and ownership chain

```text
create_app: register routers with an explicit typed Chat service dependency
  → FastAPI lifespan enters on the running loop
  → ChatWake(): loop + Event are immediately usable
  → chat_runtime_factory(wake)
      → DurableChat(wake=wake)
      → ChatCardStore(completion_observer=same_store.observe_completion)
      → ChatLoopRunner with that card store's readers/sinks
      → frozen ChatRuntime(store, runner, cards, action)
  → durable check_ready → launch the existing dispatcher
  → expose concrete ChatApplicationService to FastAPI Depends
  → revoke that service → stop/join worker → await retained card actions → close wake
```

`ChatWake` exposes only notify/clear/wait/close. There is no bind, NEW/unbound state, optional loop/Event, implicit default wake or delayed initialization. Five fields remain for real responsibilities: thread lock, immutable loop, immutable Event, terminal closed flag and the one-pending-callback gate. Clear-before-query and the existing drain/settle/wait algorithm remain unchanged. Application readiness is a single app-local typed service reference, not a proxy or a mutable general container. The small frozen ChatRuntime is an explicit composition result.

## Lifecycle and unchanged execution boundaries

Actual FastAPI lifespan/HTTP probes verify pre-start, failed-start and post-shutdown rejection of message/history/card requests before Chat ownership reads or action execution; pure metadata routes remain available. Factory failure, durable readiness failure and immediate worker startup failure all close the created wake. A normal shutdown waits for real dispatcher-owned tasks and retained card actions even after the HTTP subscriber disconnects. Multiple apps are isolated and a new lifespan creates fresh objects; closed wake operations reject reuse. Production generic/attended/realchat factories are exercised with blocked external edges, not merely the standalone signal.

The production factory constructs no Chat store/card observer/runner before lifespan. Observed store, dispatcher and card completion callback share the same wake/store. Source AST comparison additionally confirms all DurableChat methods except its constructor and all DurableDispatcher methods except run are identical to baseline. ChatCardStore, RpcChatActionService and ChatLoopRunner constructor arguments remain the same; only their creation scope changes.

The PostgreSQL tests retain all 22 scheduler cases, including committed admission, rollback, abrupt child-process exit, fresh workers, contention, full slots, same-conversation order, fenced generations, native BUSY/unknown/completed handling and double storage faults. Direct owners and spawned workers now construct their explicit wake inside a running loop and close it themselves. A real stop case confirms the dispatcher has not closed a resource owned by its caller.

## Final checks

| Group | Checks or boundary | Result |
| --- | --- | --- |
| Signal + PostgreSQL dispatch | 12 actual thread/asyncio + 22 PostgreSQL = 34 | PASS |
| Chat state convergence | 26 | PASS |
| Durable Chat delivery | 37 | PASS |
| Native turn recovery | 4 | PASS |
| Chat write approval | 239 | PASS |
| Workflow write approval | 41 | PASS |
| A2UI write preflight | 38 | PASS |
| Actual composition + lifespan | 9 | PASS |
| Account guard | 32 concurrent attempts: 7 admitted, 25 limited; related guard contracts | PASS |

All nine groups pass, with no skips. The default idle observation lasted 31.203 seconds: two candidate passes including startup, zero executions. Native BUSY inspection gap was 2.027 seconds. An accelerated 0.12-second settlement-failure retry observed a 0.158-second gap while healthy work completed with the fault present. Scripted local latency samples are not public model latency or throughput evidence.

Strict Mypy/Ruff/format passed on the same candidate for 33 files: 2 shared, 15 HTTP (including the new ChatRuntime type), 9 persistence, 3 transport and 4 composition. Repository checks parse 394 Python files and verify entry links/import boundaries; diff and exact outgoing sensitive-data checks pass. Independent read-only review found no scoped blocking issue.

Use [core probes](../../../docs/core-probes.md) to reproduce the selected groups. Probe PostgreSQL schemas and task-created containers were removed; all 12 pre-existing self-host/outbox containers were preserved. Provider/business ports are explicitly scripted. No production database, external model or business API, public deployment or remote CI result is claimed. Unrelated outbox/capability, Java/frontend builds and the complete historical unit suite were not rerun. The old test_app.Harness is not used as an adapter; current probes use explicit current-API fixtures.
