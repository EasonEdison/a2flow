# userId: signed64 backend identity

Target: Python int and PostgreSQL BIGINT. Browser JSON and HTTP headers carry
canonical decimal strings to preserve values above JavaScript's safe integer
range. Floats, booleans, whitespace, exponents, leading zeros and out-of-range
values are rejected. Transport decoding does not authenticate a caller.

## Delivery status

Shared trusted contexts, Runtime ownership, B sessions, scheduler principals,
management principals and asset gray selectors now use integers internally.
Browser responses, HTTP headers and serialized trusted contexts use decimal
strings. Original stored asset payloads remain unchanged during decoding,
preserving their digest. Fresh user identity columns use BIGINT.

Run python -m deploy.attended.user_id_preflight with an explicitly selected
A2FLOW_USER_ID_AUDIT_DSN. The tool sets a read-only transaction and prints counts,
not identity values or credentials. It never performs DDL or changes records.
Only canonical decimal values are considered convertible; no automatic mapping
is invented for old named identities. The report is not deployment approval.

## Existing data: explicitly out of scope

No old-data migration is requested. This change supplies fresh-schema DDL only:
CREATE TABLE IF NOT EXISTS does not convert existing columns. No existing
database was audited or modified for this task. Deploying to an old-schema
database is not supported by this change; select a compatible deployment target
in a separately agreed deployment step. Validation uses synthetic fixtures and
a disposable PostgreSQL instance. Source integration is not deployment proof.

Do not silently reset checkpoints, remap owners, merge leading-zero identities,
delete old memory namespaces, or deploy partially switched producers/consumers.
