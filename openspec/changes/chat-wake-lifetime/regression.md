# Single-use ChatWake validation

Baseline `2b00de2`; production candidate `87be7fd`, lifecycle tests `17caa2a`.

The production change is limited to `chat_wake.py`. The dispatcher, application transaction hooks, schema, Runtime, executor, approvals and Workflow are unchanged. One existing probe threshold changes from 28 to 32 because the signal tests increase from 10 to 14; the 18 actual PostgreSQL scheduling cases are retained.

## Verified lifecycle boundaries

The 14 real asyncio/thread tests retain the 16,000-notification burst and 100 clear/wait races. They cover pre-bind notifications, a single queued notification callback during bursts, drain/clear/wait windows, zero timeout, stop and cancellation cleanup, close with waiters/queued callbacks, a paused posting thread racing loop shutdown, closed-loop safety, duplicate binding, terminal close-before-bind, repeated close and use of a fresh replacement object. Closed notifications are no-ops and cannot change the replacement object. Rebinding support assertions have been replaced with explicit rejection, not removed as an unexplained skip.

The 32-file strict Mypy, Ruff and format gates pass. Independent source review found no remaining dependency on reusable binding generations: the terminal flag and detached event reference safely fence delayed callbacks. The lock, version, dirty flag and callback-pending flag remain for actual concurrency, not lifecycle reuse.

All eight related probe groups passed with no skips: wake 32, Chat state 26, durable delivery 37, native completion 4, Chat approval 239, Workflow approval 41, A2UI preflight 38 and actual composition 5. Task-created resources were cleaned; existing resources were preserved. The 32-check wake group includes 14 signal races and all 18 real PostgreSQL cases, covering full-slot release, commit/rollback, contention, missing hints and unknown outcomes. These use disposable PostgreSQL and scripted provider/business ports, not public operations. They do not establish a full legacy unit-suite pass or remote CI success. No new dependencies, execution engine, services, queues, public data changes or deployment are included.

For reproduction, use the existing [core probe runner](../../../docs/core-probes.md) and `--python-probe chat-dispatch-wake` for the combined 32-check group. Default idle observation still covers an actual window longer than 30 seconds. Other unchanged checks remain separately selectable.
