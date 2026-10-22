# Clear Chat dispatch ownership

Baseline `7a6fcc5`. Scope: the local hint and durable dispatcher coordination, not the model loop, Workflow, schema/API or business approval rules. Commit this concrete plan before implementation.

## Reference and boundary

Inspected [OpenCode v1.19.3 coordinator](https://github.com/anomalyco/opencode/blob/e3c4eb242585dcd77be1a867391b7c25fd47ce52/packages/core/src/session/run-coordinator.ts), a published 95-line implementation. Its active entries own execution, wakes merge, and settle hands off pending work. It borrows Effect Scope/FiberSet/Deferred. The previously inspected development reference `248bfbe` is different and is not substituted for this released source. Neither short coordinator itself supplies our PostgreSQL admission or crash recovery. Reuse the ownership/coalescing principle with existing asyncio only.

## Notify, drain, settle, wait

- `notify`: keep post-commit producer calls. ChatWake captures one loop, uses `call_soon_threadsafe`, and limits outstanding notification callbacks to one. Its API becomes `bind`, `notify`, `clear`, `wait`, `close`; no legacy alias.
- `drain`: **clear the asyncio Event before querying durable facts**, never between query and wait. Any notification delivered during or after the query leaves the Event set until the next drain. Notifications delivered before clear correspond to already-committed facts the following query reads. An unbound hint is a safe no-op because startup scans before waiting. Full-capacity/backoff paths need no remembered hint: owned-task completion or the retry timer forces a new drain.
- `settle`: a single owned task-to-turn map replaces input-ID, task and conversation sets. This path observes success/error/cancellation, schedules fenced inspection retry where needed and releases ownership. No done-callback mutates a second collection. Releasing a slot causes an immediate new drain, not an extra self-notification callback.
- `wait`: one dispatcher method owns its temporary stop/notification waiters, database deadline and repair timer. Normal wait includes owned task completion; full capacity waits only for completion/stop. Preparation/storage failure uses bounded backoff while ready work still runs. Stop awaits owned work then settles it and closes the hint.

`run` should read as clear-notify latch, drain, settle, wait, with explicit shutdown. A small execution wrapper may handle local lock-contention delay; no generic coordinator classes, new services or dependency framework.

## State deletion and retained reasons

Remove `_version` and `_dirty`: Event level plus clear-before-database ownership closes the old drain/clear/wait window. Retain `_callback_pending`: a thread can pause after reserving a callback but before posting; clear must not release this gate or repeated drains could enqueue unbounded callbacks. Retain the lock, loop/event association and terminal closed flag for real thread/lifetime races.

Replace three active containers with one task ownership map; derive conversation exclusions from its turns. Keep the scalar fairness cursor and reconciliation timestamp (previously run locals), since persistent lock contention must not starve later conversations and repeated hints must not postpone repair scans. Keep only an iteration-local failure indicator, not another execution state machine.

## Unchanged safety and checks

Database authority, post-commit hints, source/client aliases, same-ID conflict, per-conversation sequence, advisory locks, generation fencing, Runtime inspection, completion-only projection repair, UNKNOWN no replay, write confirmation and single card continuation remain intact. `dispatch` and repository methods keep their execution semantics. No new queue, broker, bind reuse, model loop or Workflow implementation.

Test actual notification/clear/wait interleavings and bounded thread posting under the new contract; do not retain counters only for tests. Adapt request tests to observe post-commit notify calls and persisted facts instead of a notification generation. Add task-success/error/cancellation settlement and temporary-waiter cleanup checks. Run real PostgreSQL commit/rollback/lost-hint, slot/same-conversation/fairness, contention/fencing, poison continuation, stop and existing recovery/approval probes, plus strict types/format. Report before/after call chains and exact state reasons. Source, deployment and public evidence stay separate.
