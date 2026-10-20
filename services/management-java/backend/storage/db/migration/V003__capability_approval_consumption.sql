-- Explicit additive migration. Apply before enabling write confirmation; never on host startup.
-- This is a durable dispatch admission, not an exactly-once business result or retry queue.
CREATE TABLE IF NOT EXISTS capability_approval_consumption (
    receipt_id varchar(200) PRIMARY KEY,
    user_id bigint NOT NULL,
    environment varchar(16) NOT NULL CHECK (environment IN ('PRT','ONLINE')),
    run_id varchar(200) NOT NULL,
    tool_call_id varchar(200) NOT NULL,
    action_code varchar(200) NOT NULL,
    source_id varchar(200) NOT NULL,
    source_digest varchar(200) NOT NULL,
    arguments_digest char(64) NOT NULL,
    confirmation_id varchar(200) NOT NULL,
    side_effect_level varchar(16) NOT NULL CHECK (side_effect_level IN ('WRITE','DESTRUCTIVE')),
    approval_policy varchar(32) NOT NULL CHECK (approval_policy = 'REQUEST_APPROVAL'),
    consumed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, environment, confirmation_id),
    UNIQUE (user_id, environment, run_id, tool_call_id)
);
