# userId: signed64 backend identity

Target: Python int and PostgreSQL BIGINT. Browser JSON and HTTP headers carry
canonical decimal strings to preserve values above JavaScript's safe integer
range. Floats, booleans, whitespace, exponents, leading zeros and out-of-range
values are rejected. Transport decoding does not authenticate a caller.

## Delivery status

The shared require_user_id/user_id_from_wire/user_id_to_wire codec and read-only
column preflight are delivered. Existing TrustedContext and application consumers
are NOT switched yet. This additive batch is not a completed Long migration.

Run python -m deploy.attended.user_id_preflight with an explicitly selected
A2FLOW_USER_ID_AUDIT_DSN. The tool sets a read-only transaction and prints counts,
not identity values or credentials. It never performs DDL or changes records.
Only canonical decimal values are considered convertible; no automatic mapping
is invented for old named identities. The report is not deployment approval.

Remaining coordinated batches:

1. Switch shared trusted contexts, schemas, Skill/ability authorization and gray
   lists together, including fixtures and immutable payload/version handling.
2. Switch B sessions, Runtime ingress, scheduler and management principals; keep
   browser/header wire strings explicit at those boundaries.
3. Review existing ownership in columns, JSON records, native checkpoints and
   native Store namespaces. Supply a reviewed migration for foreign keys and
   BIGINT columns; nonnumeric identities require an explicit mapping decision.
4. Verify old-run access, restart behavior, user isolation and gray selection in
   a disposable copy before any live migration or deployment.

Do not silently reset checkpoints, remap owners, merge leading-zero identities,
delete old memory namespaces, or deploy partially switched producers/consumers.
