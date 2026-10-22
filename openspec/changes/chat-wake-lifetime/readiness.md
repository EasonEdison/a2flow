# Single-use wake readiness

Status: **SOURCE_READY / NOT_DEPLOYED**.

ChatWake now binds once and closes permanently. Duplicate bind is an ownership error; repeated close is harmless; a new application lifetime uses a new object. Binding identities and callback-token branches have been removed. Real thread synchronization, version checking, callback coalescing and waiter cleanup remain.

All eight scoped regression groups and 32-file quality gates passed; see [verification](regression.md), [proposal and OpenCode references](proposal.md) and [tasks](tasks.md). The published OpenCode source and fixed reference are documented separately; no external execution framework or code was imported.

Source target integration/ref equality is the remaining delivery step. No public deployment, database migration/reset, model/provider or business operation was performed. Local gates do not establish remote CI or public runtime acceptance.
