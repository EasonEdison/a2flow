# Single-use ChatWake lifecycle

Baseline: `2b00de2`. Scope: the in-process hint and its lifecycle/race tests only. The dispatcher, database schema, transaction hooks, candidate scheduling, retry deadlines, approvals, Workflow and SSE remain unchanged.

## Small contract

Represent NEW by an unbound open object, BOUND by its captured running event loop, and CLOSED by one boolean. `bind()` succeeds exactly once; any duplicate binding is an ownership error, including the same loop. `close()` is terminal and idempotent, including close-before-bind. A new application lifetime needs a new object. Pre-bind hints keep advancing the version and are covered by unconditional startup discovery; post-close notify is a safe no-op.

Delete the `_binding` identity object, callback token argument, stale-versus-new-binding checks and reusable bind behavior. Queued notify callbacks check the terminal state and event reference; close wakes existing waiters once through their owning loop. No later binding exists to protect.

Retain the thread lock, `call_soon_threadsafe`, monotonic version, dirty flag and callback-pending flag. They address real thread/drain/clear/wait races and bound queued callbacks, rather than object reuse. Wait stop/cancel/timeout cleanup remains. Database facts alone authorize execution; the hint still does no business work.

## OpenCode source reference

Inspected official repository sources on 2026-10-22, without copying implementation:

- [Fixed reference coordinator](https://github.com/anomalyco/opencode/blob/248bfbe1117da1e7cc23bd41273188318afec3a5/packages/core/src/session/run-coordinator.ts) and [host-scoped session owner](https://github.com/anomalyco/opencode/blob/248bfbe1117da1e7cc23bd41273188318afec3a5/packages/core/src/session/session.ts): scoped execution ownership, coalesced pending wake and handoff when draining settles.
- [Published v1.19.3 coordinator](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/core/src/session/run-coordinator.ts), tag commit `e3c4eb242585dcd77be1a867391b7c25fd47ce52`: also scoped and coalesced, with a boolean pending wake. Its source differs from the fixed reference; they are not described as the same release implementation.
- Observed `dev` ref `e965774fa0e2a8ffb27bf02827a2c3c6a8c0f45b`. The fixed reference is not presented as the current development tip. [Official release](https://github.com/anomalyco/opencode/releases/tag/v1.19.3) identifies the published version.

Apply only the ownership/coalescing principle to existing Python/asyncio. Do not transplant the Effect fiber execution layer or add a framework/service/queue.

## Verification and delivery

Keep real thread bursts and drain/clear/wait races. Replace rebind support tests with terminal-lifecycle assertions: pre-bind hints, cross-thread hints, duplicate bind, close-before-bind, repeated close, close versus queued deliver/notify, closed-loop notification, stop/cancel cleanup and fresh replacement objects. Run related strict types/format and actual PostgreSQL scheduling/Chat state/durable/approval probes. Preserve full-slot release, commit/rollback, low-frequency reconciliation and unknown-outcome guards. Source integration and public deployment remain separate; no deployment or data reset is implied.
