# Runtime state and notification outbox atomicity

## Approved scope

Store lifecycle state and notification commands on the same PostgreSQL connection and transaction. Reuse scheduler_outbox and its existing relay/notification deduplication. Keep Runtime independent from scheduler imports through an explicit transactional_event_writer supplied by deployment assembly. Reject simultaneous legacy event_sink and transactional writer configuration.

Terminal lifecycle events use stable identities derived from owner/environment/run/type. Waiting events retain separate identities; once persisted their outbox message ID remains stable across redelivery. Failure events join the FAILED state transaction, including graph setup failures. Failed state persistence must not emit an independently committed failure notification.

Recover stale notification claims by persisting only the idempotent in-app notification. Never retry business operations or external notifications. If no external sender is configured, recovered local delivery can complete. When an external sender exists, preserve UNKNOWN for that external dispatch and record that local persistence was reconciled.

## Validation plan

Use an isolated PostgreSQL schema, no deployed business rows or existing schedules. Verify commit and rollback of state plus outbox; deferred commit-time failure; persistence across fresh process/connection; duplicate message consumption; acknowledgement failure after durable local notification; stale claims before/after notification persistence; external sender recovery never sends. Execute a focused reproducible probe rather than a complete unit suite.

## Delivery boundary

Implementation and isolated validation belong to this worker. Root owns review, integration, deployment and public acceptance. No new database tables are needed for the application; isolated verification may create private fixture tables.

## Approved extension: native waiting notification recovery

Native LangGraph checkpoints commit independently from run lifecycle transactions. A crash after a saved interrupt and before enqueue can lose a waiting notice. A Runtime lifespan-owned recovery worker will scan at most three RUNNING runs with saved WAITING interactions per pass, rotating a keyset cursor and handling each run independently. It will reconstruct the existing trusted graph in explicit read-only mode and use public get_state(subgraphs=True), never invoke or resume. Read-only construction must not initialize presentation views.

Normal publication and recovery share the same identity derived from user/environment/run/node/native interrupt id. Before enqueue, recheck RUNNING and the matching WAITING interaction under the run row lock. This recovers projection delivery, not business execution. A stopped/completed run or consumed interaction will not receive a new waiting notice. Checkpoints and notification outbox are not represented as one transaction; the recovery pass closes the missing-notice window by eventual projection reconciliation. Failed reads log only error class and run identity and do not prevent subsequent candidates.

The worker runs only when explicit transactional event delivery is configured; startup/shutdown belongs to Runtime lifespan. One graph is constructed at a time, resources close after each read, and shutdown reports if the worker cannot exit. Notification enqueue failure after a durable interrupt preserves that waiting run and is logged for recovery rather than fabricating a workflow execution failure.
