# Dispatch wake validation

Baseline `2e0b12a`; tested production candidate includes `16e418c` and probe revision `d4f1133`. Source-only acceptance uses disposable real PostgreSQL and scripted native/model/business ports. There are no public operations or external provider calls.

## Results

All **11 Python core probe groups passed**, including account guard, outbox, capability approval, Chat native recovery, dispatch wake, Chat state convergence, durable delivery, actual route composition, Chat/Workflow approval and A2UI preflight. The seven temporary databases and task containers were cleaned. The new group has **28 checks: 18 PostgreSQL scheduling/transaction/process tests and 10 real asyncio/thread signal tests**, with no skips.

Related quality checks cover 32 files with strict Mypy, Ruff and format checks. The final dispatcher change was rechecked directly for types/lint and against the full formatting scope. Repository syntax/import boundaries and documentation links also pass. Java and frontend sources are unchanged and were not rebuilt. This is a scoped invariant gate, not a claim that every legacy unit test passes.

## Measurements

The final local run used `reconcile_seconds=30`, `max_concurrency=8`, and `retry_seconds=2` for normal latency/idle observations.

| Boundary measured | Result |
| --- | --- |
| Transaction return plus notification to scripted native runner start record | 8 samples, 17.157–34.337 ms |
| Actual idle window | 31.206 seconds; startup plus one periodic candidate reconciliation, zero execution |
| Actual BUSY inspection interval | 2.028 seconds; one later execution after the native fact changed |
| Injected materialization and failure-record write errors | 0.151-second pass gap with an explicit accelerated 0.12-second retry; healthy turn completed while poison remained broken |
| Two independent spawn processes contending for one turn | One execution recorded in append-only synthetic receipts |

These figures measure the local disposable PostgreSQL fixture and scripted runner, not public model first-token latency, production performance or a measured speedup ratio. Candidate reconciliation counts are not total database statement counts. Some failure scenarios explicitly accelerate the scan interval to 0.08/0.1/0.12 seconds and local retry to 0.06/0.12 seconds; the real BUSY deadline remains two seconds.

## Failure and concurrency boundaries

- A real trigger rolls back ordinary admission: no messages, wake or execution. A rolled-back card observer also creates no continuation and emits no hint.
- A spawned process commits then exits before notifying. A running worker finds the row by reconciliation; startup also discovers committed rows without a hint.
- Repeated notifications and replayed client aliases reuse persisted turns. The wake port keeps one pending callback, and checks a counter under a lock around drain/clear/wait transitions. Thread bursts, timeout, stop, cancellation and rebind have no lost-wait or child-task leaks.
- Eight bounded slots retain application ownership. Full capacity ignores notification storms for scanning; slot release immediately checks subsequent work. Active conversations are excluded before SQL LIMIT; a scalar round-robin cursor lets later conversations progress during persistent older lock contention.
- A forced interleaving holds an advisory lock before generation claim while another process loses the lock. The loser does not change the winner deadline. Claim still checks actual database eligibility, and stale-generation deferral cannot shorten a later deadline.
- A pending continuation whose failure-state write also fails reports the batch fault. Healthy intents still materialize and ready turns execute before the next preparation backoff; no past-due zero-delay retry loop or global starvation.
- Submitted-card continuation materializes once; processing aliases share one turn. Unknown native execution blocks replay and later turns. Native completion is projection repair only. Existing actual SDK/approval/Workflow probes remain green.

The direct durable-recovery probe now explicitly advances `next_attempt_at` in two synthetic fault scenarios before directly calling dispatch again. Those tests exercise completion repair and unknown-result isolation, not wall-clock delay; the new scheduling probe independently checks the real retry deadline.

## Reproduction and limits

Follow [core probe instructions](../../../docs/core-probes.md). Select `--python-probe chat-dispatch-wake` for this group, or leave the default to run all eleven Python groups. Each run reports its selection, actual measurements and cleanup. It creates its own databases; no installation DSN is accepted by the outer runner. SSE subscriptions were not changed.

Notifications are process-local hints, not execution authority or a cross-worker bus. Each worker reconciles its durable database; when slots are available, periodic reconciliation discovers missed/foreign-process hints. A full worker waits for capacity, so 30 seconds is not a guaranteed execution-start latency. Latest-schema installation constraints from [Chat state convergence](../chat-state-convergence/readiness.md) remain unchanged. No deployment, migration or public data reset was performed.
