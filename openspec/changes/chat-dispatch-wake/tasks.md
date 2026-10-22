# Dispatch wake implementation

- [x] Verify human authorization and current main; commit the concrete proposal before code.
- [x] Keep durable admission, transaction, generation and Runtime inspection boundaries.
- [x] Notify only after successful ordinary/processing/card/continuation commits.
- [x] Bound active tasks and exclude active conversations before candidate LIMIT.
- [x] Preserve retry deadlines; use local contention backoff and a bounded round-robin cursor.
- [x] Coalesce thread-safe wake signals and verify drain/wait/stop races.
- [x] Verify real PostgreSQL crash, rollback, continuation and multi-process behavior.
- [x] Measure local scripted dispatch latency and default idle reconciliation frequency.
- [x] Run related core invariants, strict types, format and repository checks.
- [x] Review exact outgoing scope and integrate/push both target main refs (verified source integration `73a01b5`).

Public deployment, schema migration/reset and provider/business acceptance are not performed by these source tasks.
