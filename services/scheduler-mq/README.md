# Scheduler delivery

Run `python -m a2flow_scheduler.main` with `services/scheduler-mq/src`,
`services/b-side-api/src`, and `packages/contracts/src` on `PYTHONPATH`.
Install `requirements.txt`; apply the B-side schema and scheduler `schema.sql`
to the same PostgreSQL database before starting the process.

Required configuration:

- `A2FLOW_SCHEDULER_DATABASE_URL` (optional password file via
  `A2FLOW_SCHEDULER_POSTGRES_PASSWORD_FILE`).
- `A2FLOW_SCHEDULER_REDIS_URL` or `A2FLOW_SCHEDULER_REDIS_URL_FILE`.
- `A2FLOW_SCHEDULER_STREAM_NAMESPACE` (separate environments/deployments).
- `A2FLOW_SCHEDULER_BSIDE_URL`.
- `A2FLOW_SCHEDULER_INTERNAL_TOKEN` or `A2FLOW_SCHEDULER_INTERNAL_TOKEN_FILE`.
- Optional `A2FLOW_SCHEDULER_TRIGGER_SECONDS` (default 5, maximum 60).
- Optional existing `A2FLOW_LARK_WEBHOOK_URL` / `A2FLOW_LARK_SECRET`.

Use `PostgresOutbox(connection).enqueue(command)` within the transaction that
persists a card action or lifecycle event. It neither commits nor accesses Redis.
Commands are the strict `StartWorkflow`, `ResumeWorkflow`, and
`NotificationCommand` DTOs in `contracts.py`. Reusing a message ID with different
content raises a conflict. Scheduled control IDs are UUID5 values over schedule
identity and the UTC scheduled instant. Schedule rules accept `cron` with
`{"expression":"0 9 * * 1-5"}` plus an explicit IANA timezone; existing once and
period rules remain supported.

Cron dispatches only a due instant in the current minute. After downtime,
older cron windows are skipped directly to the next future instant with an
in-app diagnostic; no old cron execution or unbounded missed-count loop runs.

The publisher sends only durable message IDs into Redis Streams. Pending rows
are republished after 60 seconds, so a lost Redis instance can be reconstructed
from PostgreSQL without replaying admitted business commands. Duplicate stream
references cannot claim an already admitted command. Stream acknowledgement
means delivery has a durable outcome, not that a workflow completed successfully.

Each command makes at most one automatic POST attempt. Ambiguous delivery and
interrupted dispatch become durable `unknown` rows. Start and resume unknowns
are reconciled with read-only B-side control queries every 30 seconds; a 404
retains UNKNOWN and never restarts business execution. Stale dispatch claims
become UNKNOWN after five minutes. External notification ambiguity remains
actionable in the outbox; no blind Feishu retry is performed. In-app notifications
are saved idempotently before optional external delivery.

The process requires internal B-side start, resume, and control-read endpoints.
It does not run the legacy automatic wait-timeout stop monitor or consume legacy
`queue_items`. Existing legacy modules are retained for callers during migration;
new publishers must write typed commands to this outbox. Historical queue
migration is an explicit operator decision, not startup replay.

Inspect unresolved delivery using a restricted database connection:

```sql
SELECT message_id, channel, state, error_code, claimed_at, reconciled_at
FROM scheduler_outbox WHERE state IN ('unknown', 'rejected') ORDER BY created_at;
```

Do not reset UNKNOWN to pending without investigating the original control ID.
