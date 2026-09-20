-- Attended-automation v1 schema (idempotent). All rows are userId-scoped.

CREATE TABLE IF NOT EXISTS users (
    id bigserial PRIMARY KEY,
    user_id text UNIQUE NOT NULL,
    username text UNIQUE NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL DEFAULT 'USER',
    lark_open_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    token_sha256 text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users(user_id),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversations (
    id bigserial PRIMARY KEY,
    user_id text NOT NULL,
    title text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id bigserial PRIMARY KEY,
    conversation_id bigint NOT NULL REFERENCES conversations(id),
    role text NOT NULL,
    content jsonb NOT NULL,
    ref_kind text,
    ref_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_conversation_id_id
    ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS workflow_schedules (
    id bigserial PRIMARY KEY,
    user_id text NOT NULL,
    workflow_key text NOT NULL,
    environment text NOT NULL,
    rule_type text NOT NULL,
    rule_json jsonb NOT NULL,
    timezone text NOT NULL DEFAULT 'Asia/Shanghai',
    input_text text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    next_run_at timestamptz NOT NULL,
    last_run_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS queue_items (
    id bigserial PRIMARY KEY,
    queue text NOT NULL,
    payload jsonb NOT NULL,
    dedup_key text UNIQUE,
    state text NOT NULL DEFAULT 'pending',
    attempts integer NOT NULL DEFAULT 0,
    claimed_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS queue_items_claim
    ON queue_items(queue, state, id);

CREATE TABLE IF NOT EXISTS notifications (
    id bigserial PRIMARY KEY,
    user_id text NOT NULL,
    kind text NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    ref_type text,
    ref_id text,
    read boolean NOT NULL DEFAULT false,
    idempotency_key text UNIQUE NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notifications_user
    ON notifications(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS run_ownership (
    control_id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users(user_id),
    workflow_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS run_ownership_user
    ON run_ownership(user_id, created_at DESC);
ALTER TABLE run_ownership ADD COLUMN IF NOT EXISTS run_id text;
CREATE INDEX IF NOT EXISTS run_ownership_run ON run_ownership(run_id);
