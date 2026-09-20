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
