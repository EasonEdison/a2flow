# Dispatch wake readiness

Status: **SOURCE_READY / NOT_DEPLOYED**.

The latest-schema Chat dispatcher now combines committed local wake hints, task completion, database retry deadlines, startup discovery and 30-second reconciliation. Persisted turns/intents, conversation locks, generation fencing and Runtime inspection still control execution. There is no new Agent loop, message broker or cross-process notification service.

[Validation](regression.md) records 11 passing core groups, 28 new checks, scoped type/format gates and measured local scheduling boundaries. [Proposal](proposal.md) and [tasks](tasks.md) record the contract and delivery scope. Local success does not establish remote CI or public provider success.

Source integration `73a01b5` was pushed to server origin and GitHub main; both remote refs were verified equal. The combined-status API returned no records, so remote CI success is not claimed. Existing public structures are older than the prior latest-only state change; this work does not migrate, clear or deploy them. Public installation/data decisions and deployment are separate.
