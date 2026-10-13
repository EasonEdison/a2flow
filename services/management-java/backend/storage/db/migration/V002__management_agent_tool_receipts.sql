-- Explicit migration, never applied automatically at host startup.
-- Only management-tool deduplication and factual result readback; no second job scheduler.
CREATE TABLE IF NOT EXISTS management_agent_tool_receipt (
    namespace varchar(200) NOT NULL,
    user_id bigint NOT NULL CHECK (user_id > 0),
    conversation_id varchar(128) NOT NULL,
    request_id varchar(160) NOT NULL,
    parent_request_id varchar(160) NOT NULL,
    turn_id varchar(160) NOT NULL,
    tool_call_id varchar(160) NOT NULL,
    method varchar(100) NOT NULL,
    arguments_digest char(64) NOT NULL,
    status varchar(16) NOT NULL CHECK (status IN ('CLAIMED','SUCCEEDED','REJECTED','UNKNOWN')),
    error_code varchar(160) NOT NULL DEFAULT '',
    result_json jsonb,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    PRIMARY KEY (namespace, user_id, conversation_id, request_id)
);
