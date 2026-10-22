# Commit-triggered Chat dispatch

Baseline: `2e0b12a`. Scope: optimize durable inbox scheduling only, with latest-schema contracts from chat-state-convergence. SSE subscriptions, Agent execution, business approvals and Workflow execution stay unchanged.

## Ownership

Database turns and continuation intents remain authoritative. Lifespan owns the dispatcher; HTTP only accepts and subscribes. A typed process-local wake hint never authorizes execution. Existing conversation locks, writer generations, Runtime inspect and unknown-result isolation remain mandatory.

## Implementation

1. Add a typed thread-safe wake port with one coalesced pending signal and monotonic generation; bind it to the application event loop only during dispatcher lifetime. Clear/check under a lock around wait transitions, so a notification during drain or between clear/wait survives. No per-request queue or unbounded conversation set.
2. Emit hints only after admission transactions return successfully: ordinary and processing admission, replayed accepted request, trusted action service return after saved card completion, and committed continuation materialization. Never notify from the in-transaction card observer. Post-commit crash can miss a hint but never lose database intent.
3. Start with an unconditional reconciliation pass. Then wait for hints, active task completion, the earliest eligible database retry, stop, or a 30-second repair deadline. With capacity available, the repair deadline bounds idle reconciliation; notifications do not postpone it. Saturated workers wait for a slot, so 30 seconds is not an execution-start latency guarantee. Existing BUSY 2-second/materialization 5-second schedules remain database-controlled.
4. Keep eight active tasks, excluding their conversations before the SQL candidate LIMIT. Full capacity waits for task completion/stop rather than rescanning due rows. Slot release immediately rechecks database facts, including the next turn in the same conversation. A lost product advisory-lock race waits locally after releasing its connection, without changing the shared deadline of the lock owner. A single round-robin candidate cursor prevents a group of contended older conversations from starving later ones. This local wait stays inside the bounded task slots.
5. Shutdown stops new dispatch and awaits owned work; exceptions are observed/logged and retain durable recovery facts. Database failures use bounded retry rather than a hot error loop; continuation failure-state persistence errors are reported after processing the batch so a past-due intent cannot cause a zero-delay loop. Already-ready turns still dispatch during a persistent bad-intent failure; only the next preparation pass backs off.

## Processes and notification loss

The port is explicitly local, not a cross-worker bus. Each worker has the same startup and 30-second reconciliation; HTTP and its dispatcher share the port in that process. Other workers discover persisted work on their own sweep, and the existing database admission locks arbitrate contention. Current deployment has no requirement to add a dedicated PostgreSQL listener connection or notification query to every admission. No new service or execution engine is added. Process failure, unbound-port notifications and lost hints remain covered by persisted intent and reconciliation.

## Verification

Use real disposable PostgreSQL for successful commit vs rollback, commit before an omitted wake, concurrent duplicates and multi-process contention, continuation materialization/action resume, completed projection repair and unknown write outcomes. Controlled scheduler tests cover bounded coalescing, drain/wait races, capacity saturation/slot release, next-turn ordering, retry deadlines, startup/lost hints, shutdown and failure backoff. Measure local scripted commit-to-dispatch latency and idle pass count without claiming production/provider speed. Run related strict types/format, repository checks and existing core invariants.

Source delivery and deployment are separate. Existing public schema is older and intentionally unsupported by the previous latest-only change; this optimization does not migrate or clear it. No public installation/data reset or automatic deployment is implied.
