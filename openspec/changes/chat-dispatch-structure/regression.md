# Dispatcher ownership verification

Baseline `7a6fcc5`; final behavior candidate `b4212bed`; formatting-only follow-up `fcab78a` has an identical complete `durable_chat.py` AST. Deployment is not included.

## Before and after

Before: producer commit → wake version/dirty/pending state → run loop with input-ID, task and conversation collections → task callback/removal and self-notification → version-aware wait. These collections described overlapping ownership.

After: producer commit → bounded `notify` → `clear` before database reads → `drain` admits into one task-to-turn map → `settle` observes exits and releases ownership → `wait` observes stop, task completion, signal or the next database/reconciliation deadline. Neither loop decides model/tool transitions. Runtime inspection in `dispatch` remains the execution admission authority.

`_version` and `_dirty` are removed. Event operations run on its owner loop. `_callback_pending` remains lock-protected across clear: a notifying thread may be paused between reserving and posting its callback. The cursor and repair deadline retain fairness and periodic recovery responsibilities; they are not Agent states.

## Proof boundaries

- Source AST comparison confirms the entire `DurableChat` class and `DurableDispatcher.dispatch` are identical to baseline. Admission transactions, generations, native NOT_STARTED/BUSY/COMPLETED/NEEDS_REVIEW interpretation, projection repair and approval behavior are unchanged.
- Signal tests use actual asyncio and threads. A 16,000-notification burst has at most one outstanding callback; repeated clear/wait, delayed thread posting, shutdown and replacement lifetimes preserve ownership. No old version API remains just to satisfy tests.
- All original 18 PostgreSQL scheduling cases remain; four new cases cover task exceptions, cancellation at native inspection, actual wait helper cleanup and retry-persistence double failure. The full-slot case additionally proves immediate handoff with no self-notification.
- If inspection fails and storing its retry deadline also fails, settlement releases every finished owner, then routes the storage fault through bounded backoff. Already-started healthy work keeps running. This is fact-inspection retry, never permission to repeat an unknown business operation.
- Normal stop awaits admitted executions; temporary waiter cancellation never cancels those executions. Signal close is in a shutdown `finally` even if settlement persistence fails.

## Validation record

All eight related groups passed with 423 total checks and no skips. The 32-file strict Mypy, Ruff and final format gates passed. The repository check parsed 392 Python files and checked current entry links/import boundaries; `git diff --check` passed. Independent read-only review found no scoped blocking issue; the root repeated the AST comparison. These checks use isolated PostgreSQL and scripted provider/business ports. They make no external model or business calls and do not prove remote CI or public deployment behavior. Reproduce via [core probes](../../../docs/core-probes.md), selecting `chat-dispatch-wake` or the relevant related groups. No unrelated historical unit-suite pass is claimed.


| Scoped group | Checks | Result |
| --- | ---: | --- |
| Dispatch wake (11 thread/asyncio + 22 PostgreSQL) | 33 | PASS |
| Chat state convergence | 26 | PASS |
| Chat durable delivery | 37 | PASS |
| Native turn recovery | 4 | PASS |
| Chat write approval | 239 | PASS |
| Workflow write approval | 41 | PASS |
| A2UI write preflight | 38 | PASS |
| Actual Python route composition | 5 | PASS |

The default idle window was 31.212 seconds, with two candidate reads including startup and no execution. BUSY inspection remained separated by 2.016 seconds. With an accelerated 0.12-second fault retry configuration, inspection-plus-retry-persistence failure had a 0.183-second observed gap and healthy work completed while the fault remained. Eight transaction-return-to-scripted-runner samples were 22.101–42.470 ms in this isolated local environment; these are neither public model latency nor a throughput guarantee.

Quality scope was 2 shared, 14 HTTP, 9 persistence, 3 transport and 4 composition files. The behavioral suite ran once against `b4212bed`; the final 32-file formatting check used `fcab78a`, with AST identity independently verified. Probe schemas and task-created containers were removed; all 12 existing self-host/outbox containers were preserved. Unrelated account/outbox/capability suites, complete historical unit suites, Java and frontend builds were not rerun because their source was untouched.
