-- Attended-automation v1 schema (idempotent). All rows are userId-scoped.

CREATE TABLE IF NOT EXISTS users (
    id bigserial PRIMARY KEY,
    user_id bigint UNIQUE NOT NULL,
    username text UNIQUE NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL DEFAULT 'USER',
    lark_open_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    token_sha256 text PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users(user_id),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversations (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL,
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
    user_id bigint NOT NULL,
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
    user_id bigint NOT NULL,
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
    user_id bigint NOT NULL REFERENCES users(user_id),
    workflow_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS run_ownership_user
    ON run_ownership(user_id, created_at DESC);
ALTER TABLE run_ownership ADD COLUMN IF NOT EXISTS run_id text;
CREATE INDEX IF NOT EXISTS run_ownership_run ON run_ownership(run_id);

-- Work activity reads use Runtime facts; these columns only record admission provenance.
ALTER TABLE run_ownership ADD COLUMN IF NOT EXISTS environment text;
ALTER TABLE run_ownership ADD COLUMN IF NOT EXISTS source_type text;
CREATE INDEX IF NOT EXISTS run_ownership_activity_page
    ON run_ownership(user_id, environment, created_at DESC, control_id DESC);
CREATE TABLE IF NOT EXISTS work_activity_attention_acks (
    user_id bigint NOT NULL,
    environment text NOT NULL,
    activity_id text NOT NULL,
    attention_id text NOT NULL,
    acknowledged_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(user_id, environment, activity_id, attention_id)
);

-- Follow-up processing is separate from workflow state and reminder acknowledgement.
CREATE TABLE IF NOT EXISTS processing_tasks (
    task_id text PRIMARY KEY,
    user_id bigint NOT NULL,
    environment text NOT NULL CHECK(environment IN ('PRT','ONLINE')),
    conversation_id bigint NOT NULL REFERENCES conversations(id),
    activity_id text NOT NULL,
    run_id text NOT NULL,
    attention_id text NOT NULL,
    objective text NOT NULL,
    origin_message_id bigint REFERENCES messages(id),
    status text NOT NULL CHECK(status IN ('OPEN','WAITING_INPUT','RESULT_RECORDED','FAILED','UNKNOWN','RESOLVED')),
    result_summary text,
    resolution_summary text,
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS processing_tasks_attention
    ON processing_tasks(user_id,environment,activity_id,attention_id,created_at DESC);
CREATE TABLE IF NOT EXISTS processing_cards (
    user_id bigint NOT NULL,
    environment text NOT NULL,
    conversation_id bigint NOT NULL REFERENCES conversations(id),
    card_id text NOT NULL,
    task_id text NOT NULL REFERENCES processing_tasks(task_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(user_id,environment,conversation_id,card_id)
);
CREATE TABLE IF NOT EXISTS processing_operations (
    operation_id text PRIMARY KEY,
    task_id text NOT NULL REFERENCES processing_tasks(task_id),
    operation_digest text NOT NULL,
    ability_key text NOT NULL,
    arguments jsonb NOT NULL,
    turn_id text NOT NULL,
    tool_call_id text NOT NULL,
    request_id text UNIQUE NOT NULL,
    status text NOT NULL CHECK(status IN ('RUNNING','RETURNED','FAILED','UNKNOWN')),
    result jsonb,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    UNIQUE(task_id,operation_digest)
);

-- Product dispatch facts are independent of native Agent checkpoints.
CREATE TABLE IF NOT EXISTS chat_turns (
 input_message_id bigint PRIMARY KEY REFERENCES messages(id),
 assistant_message_id bigint UNIQUE NOT NULL REFERENCES messages(id),
 user_id bigint NOT NULL,
 environment text NOT NULL CHECK(environment IN ('PRT','ONLINE')),
 conversation_id bigint NOT NULL REFERENCES conversations(id),
 source_kind text NOT NULL CHECK(source_kind IN ('USER_MESSAGE','PROCESSING','CARD_CONTINUATION')),
 source_key text NOT NULL,
 source_digest text NOT NULL,
 processing_task_id text REFERENCES processing_tasks(task_id),
 dispatch_generation bigint NOT NULL DEFAULT 0,
 status text NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','RUNNING','COMPLETED','NEEDS_REVIEW')),
 run_references jsonb NOT NULL DEFAULT '[]',
 processing_context jsonb,
 next_attempt_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(user_id,environment,conversation_id,source_kind,source_key),
 UNIQUE(input_message_id,user_id,environment,conversation_id)
);
CREATE INDEX IF NOT EXISTS chat_turns_dispatch ON chat_turns(environment,status,next_attempt_at,input_message_id);
CREATE TABLE IF NOT EXISTS chat_turn_events (
 input_message_id bigint NOT NULL REFERENCES chat_turns(input_message_id),
 sequence integer NOT NULL,
 dispatch_generation bigint NOT NULL DEFAULT 0,
 event jsonb NOT NULL,
 PRIMARY KEY(input_message_id,sequence)
);
CREATE TABLE IF NOT EXISTS chat_continuations (
 user_id bigint NOT NULL,
 environment text NOT NULL CHECK(environment IN ('PRT','ONLINE')),
 conversation_id bigint NOT NULL REFERENCES conversations(id),
 reference text NOT NULL,
 card_id text NOT NULL,
 request_id text NOT NULL,
 write_completed boolean NOT NULL,
 state text NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','MATERIALIZED','NEEDS_REVIEW')),
 error_code text,
 next_attempt_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id,environment,conversation_id,reference)
);
CREATE TABLE IF NOT EXISTS chat_requests (
 user_id bigint NOT NULL,
 environment text NOT NULL CHECK(environment IN ('PRT','ONLINE')),
 conversation_id bigint NOT NULL REFERENCES conversations(id),
 client_request_id text NOT NULL,
 request_digest text NOT NULL,
 input_message_id bigint NOT NULL REFERENCES messages(id),
 PRIMARY KEY(user_id,environment,conversation_id,client_request_id),
 FOREIGN KEY(input_message_id,user_id,environment,conversation_id)
   REFERENCES chat_turns(input_message_id,user_id,environment,conversation_id)
);
