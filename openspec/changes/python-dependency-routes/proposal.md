# Typed Python HTTP dependencies and domain routers

Approved 2026-10-22: retain explicit construction, make real dependencies navigable, split oversized HTTP factories and inspect adjacent active entry points. No Bean container or execution-engine rewrite. Baseline `b5785c5`; initial scope recorded before implementation.

## Problem and decision

B `create_app` mixed 42 route closures, admission middleware, shared orchestration and untyped repository/callback captures in 1270 lines. IDE navigation could not reliably identify `processing_tasks.context_for_card` or the actual Chat stream implementation. The actual production root is `deploy.realchat.launcher` delegating to attended composition; typing only the generic factory would leave production unchanged.

Use six domain routers and two small application services. Keep authentication, query admission, exceptions and lifespan in `app.py`, with explicit keyword construction. Repositories and processing/dispatch dependencies use concrete classes. Existing replaceable Runtime/Chat ports and the direct/fenced projection writers have real structural protocols. Callback aliases specify their actual arguments and results. No service registry, string-key lookup or model-selected implementation is introduced.

SQL values and extensible JSON remain dynamic at their data boundaries. They do not replace dependency object types. Fixed processing, message and recovery shapes are typed. Missing required SQL RETURNING rows fail explicitly instead of being cast into an assumed shape.

## Scope

B HTTP/routes, Chat admission and card continuation, processing repository, delivery and durable dispatcher, generic and attended assembly, realchat launcher, model factory resolvers. Small Runtime HTTP/progress attachment and RuntimeService boundaries also gain types. [Inventory](inventory.md) records inspected active/retired and internal-engine cases. Internal graph machinery is not globally retyped; only direct service call targets are annotated where needed.

## Invariants

Preserve ordered routes, request/response schemas, authentication and ownership, Origin/query admission, approval requirements, message idempotency, processing deduplication, Runtime authoritative completion, UNKNOWN no replay, generation fencing, card continuation intent and native Workflow semantics. Browser disconnect still releases only the subscriber; owned background work persists until its real outcome. No production migrations or deployment are performed.

## Alternatives

A full dependency container adds lifecycle/discovery rules without solving missing contracts. Protocols for every repository duplicate single implementations. Keeping all handlers in one typed closure improves navigation but leaves a large responsibility boundary. The chosen split keeps manual assembly visible and limits abstractions to supported implementation variation.

## Acceptance

Immutable wire fixtures pin 42 B and 19 Runtime routes and OpenAPI contracts. Offline production factories are constructed with blocked external boundaries. Expanded real-dependency mypy/Ruff gates and existing PostgreSQL/approval probes run in isolated test containers. Source integration, hosted CI and deployment are reported separately.
