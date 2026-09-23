CREATE SCHEMA IF NOT EXISTS a2flow_content;

CREATE TABLE IF NOT EXISTS a2flow_content.content_project (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    audience TEXT NOT NULL,
    output_format TEXT NOT NULL CHECK (output_format IN ('ARTICLE', 'SPOKEN_SCRIPT')),
    current_source_id UUID,
    current_selection_id UUID,
    current_manuscript_id UUID,
    revision BIGINT NOT NULL CHECK (revision BETWEEN 1 AND 4294967295),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id, user_id)
);

CREATE TABLE IF NOT EXISTS a2flow_content.content_source (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    user_id BIGINT NOT NULL,
    revision BIGINT NOT NULL CHECK (revision BETWEEN 1 AND 4294967295),
    title TEXT NOT NULL,
    source_url TEXT,
    body TEXT NOT NULL,
    digest TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, revision),
    UNIQUE (id, project_id, user_id),
    FOREIGN KEY (project_id, user_id)
        REFERENCES a2flow_content.content_project(id, user_id)
);

CREATE TABLE IF NOT EXISTS a2flow_content.content_artifact (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    user_id BIGINT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('READING_BRIEF', 'TOPIC_PLAN', 'MANUSCRIPT')),
    revision BIGINT NOT NULL CHECK (revision BETWEEN 1 AND 4294967295),
    body_json JSONB NOT NULL,
    body_markdown TEXT NOT NULL,
    input_refs JSONB NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('MODEL_GENERATED', 'USER_EDITED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, kind, revision),
    UNIQUE (id, project_id, user_id),
    FOREIGN KEY (project_id, user_id)
        REFERENCES a2flow_content.content_project(id, user_id)
);

CREATE TABLE IF NOT EXISTS a2flow_content.content_confirmation (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    user_id BIGINT NOT NULL,
    artifact_id UUID NOT NULL,
    decision_type TEXT NOT NULL CHECK (decision_type IN ('READING', 'TOPIC', 'MANUSCRIPT')),
    selection_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id, project_id, user_id),
    FOREIGN KEY (project_id, user_id)
        REFERENCES a2flow_content.content_project(id, user_id),
    FOREIGN KEY (artifact_id, project_id, user_id)
        REFERENCES a2flow_content.content_artifact(id, project_id, user_id)
);

CREATE TABLE IF NOT EXISTS a2flow_content.content_request_receipt (
    user_id BIGINT NOT NULL,
    operation TEXT NOT NULL,
    request_id TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    result_ref UUID NOT NULL,
    result_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, operation, request_id)
);

CREATE INDEX IF NOT EXISTS content_project_owner_updated_idx
    ON a2flow_content.content_project(user_id, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS content_source_owner_idx
    ON a2flow_content.content_source(user_id, project_id, revision DESC);
CREATE INDEX IF NOT EXISTS content_artifact_owner_idx
    ON a2flow_content.content_artifact(user_id, project_id, kind, revision DESC);
CREATE INDEX IF NOT EXISTS content_confirmation_owner_idx
    ON a2flow_content.content_confirmation(user_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS content_confirmation_artifact_idx
    ON a2flow_content.content_confirmation(artifact_id, project_id, user_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'content_project_current_source_fk'
          AND conrelid = 'a2flow_content.content_project'::regclass
    ) THEN
        ALTER TABLE a2flow_content.content_project
            ADD CONSTRAINT content_project_current_source_fk
            FOREIGN KEY (current_source_id, id, user_id)
            REFERENCES a2flow_content.content_source(id, project_id, user_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'content_project_current_selection_fk'
          AND conrelid = 'a2flow_content.content_project'::regclass
    ) THEN
        ALTER TABLE a2flow_content.content_project
            ADD CONSTRAINT content_project_current_selection_fk
            FOREIGN KEY (current_selection_id, id, user_id)
            REFERENCES a2flow_content.content_confirmation(id, project_id, user_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'content_project_current_manuscript_fk'
          AND conrelid = 'a2flow_content.content_project'::regclass
    ) THEN
        ALTER TABLE a2flow_content.content_project
            ADD CONSTRAINT content_project_current_manuscript_fk
            FOREIGN KEY (current_manuscript_id, id, user_id)
            REFERENCES a2flow_content.content_artifact(id, project_id, user_id);
    END IF;
END $$;
