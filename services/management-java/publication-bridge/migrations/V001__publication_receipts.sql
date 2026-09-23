-- Apply explicitly to EACH initialized runtime environment DB, never to an accounts database.
-- Asset/environment/serving tables remain owned by the existing Python asset-store setup.
CREATE TABLE a2flow_management_publication_receipts (
    namespace TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    receipt BYTEA NOT NULL,
    PRIMARY KEY (namespace, request_id)
);
