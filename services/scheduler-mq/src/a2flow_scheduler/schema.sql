-- scheduler-mq v1 schema (idempotent).

CREATE TABLE IF NOT EXISTS run_wait_states (
    run_id text PRIMARY KEY,
    user_id bigint NOT NULL,
    workflow_key text NOT NULL,
    waiting_since timestamptz NOT NULL,
    last_event_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS run_wait_states_overdue
    ON run_wait_states(waiting_since);

-- PostgreSQL owns payloads and admission state; Redis carries references only.
CREATE TABLE IF NOT EXISTS scheduler_outbox (
    message_id text PRIMARY KEY,
    channel text NOT NULL CHECK (channel IN ('workflow', 'notifications')),
    payload jsonb NOT NULL,
    state text NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'dispatching', 'completed', 'unknown', 'rejected')),
    published_at timestamptz,
    claimed_at timestamptz,
    completed_at timestamptz,
    reconciled_at timestamptz,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS scheduler_outbox_pending
    ON scheduler_outbox(created_at) WHERE state = 'pending';
