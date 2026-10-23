# State vocabulary readiness

Status: **SOURCE_READY / NOT_DEPLOYED**.

Product, native persisted execution and computed inspection states have separate documented enums. Product dispatch and native execution lock names expose their distinct scopes. Original wire/DB strings, DDL, key derivations, BUSY preservation/two-second inspection, generation fencing, admission, approvals and continuation semantics remain.

Eight scoped groups (429 checks), 34-file types/lint/format, independent review, source equivalence checks and repository/diff validation passed. See [verification](regression.md), [reading guide](../../../docs/chat-state-and-locks.md), [proposal](proposal.md) and [tasks](tasks.md). Source integration/remote equality are recorded after push. No public deployment or production data operation was performed.
