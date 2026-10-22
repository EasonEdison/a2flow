# Create usable Chat dependencies during async startup

Baseline `02e0ff6`. Scope: creation, typed injection and application-owned shutdown of the existing Chat wake/dispatcher. Latest-only; no old bind alias, lazy initialization, global singleton or second execution engine. Record this plan before implementation.

## Lifecycle and dependency boundary

`ChatWake()` requires a running event loop and immediately captures that loop and creates its Event. Its operation API is notify/clear/wait/close; delete bind and every NEW/unbound branch. Keep its lock, immutable loop/Event, terminal closed flag and pending-callback gate. Notifications from other threads use call_soon_threadsafe; clear remains before database reads. Closed notify is a no-op; closed operations cannot reopen an object.

The real production composition currently constructs DurableChat, its CardCompletion observer and ChatLoopRunner synchronously. Move those dependent constructors together into one explicitly typed factory. The factory receives the already usable wake and returns a small frozen ChatRuntime value containing the concrete store, runner, card reader and action callback, not a mutable general service container. DurableChat requires the explicit wake; no hidden default constructor.

FastAPI lifespan creates the wake, invokes that factory, checks the durable schema, starts the existing dispatcher and exposes the concrete ChatApplicationService through a typed FastAPI dependency. One app-local optional service reference describes HTTP readiness only: it is assigned after startup succeeds and removed before shutdown starts. It is not a wake proxy, global registry, deferred bind or execution state. Synchronous route registration receives the explicit dependency callable; handlers work with the concrete class. Generic hosts without Chat retain explicit Chat unavailability.

On any startup failure, revoke request admission and close the created wake. On normal shutdown, revoke admission, signal stop, await admitted dispatcher work and retained card actions, then close the wake in a finally. Dispatcher no longer initializes or closes a resource owned by the application. A later application lifetime creates a new object; never rebind a closed object. Check immediate worker startup failures before yielding readiness.

## Preserved semantics

Do not alter dispatch admission, database transitions, reconciliation/deadlines, clear/drain/settle/wait, slot/conversation ownership, fencing, native execution facts, completed projection repair, unknown-result no-replay, control deduplication, card materialization or approval rules. The typed factory is composition only, not a new scheduler or DI framework. Follow the ownership/make principle of the official OpenCode coordinator without importing Effect or copying its loop.

## Verification and delivery

Exercise actual FastAPI lifespan and production factory routing: pre-start rejection before persistence, exact wake identity through admission/card observer/dispatcher, startup failures and cleanup, worker-start failure, normal stop waiting for admitted execution, thread callback/close interleaving, multi-app isolation, fresh restart objects and closed-object rejection. Preserve signal races, real PostgreSQL wake/slots/recovery/deduplication and Chat/Workflow/A2UI approval continuation probes. Run scoped types/lint/format and source checks. Report source integration separately from deployment; this task does not deploy or mutate public databases.
