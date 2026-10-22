# Async Chat startup readiness

Status: **SOURCE_READY / NOT_DEPLOYED**.

ChatWake is created ready during FastAPI async startup. Bind and unbound/default-lazy construction are gone. Application lifespan owns typed service readiness, production store/card/runner construction, worker shutdown, retained action completion and final wake close. Existing dispatch admission, database fencing, deduplication, approvals and automatic continuation retain their execution semantics.

Nine scoped groups, actual lifespan/production composition, 33-file strict types/lint/format, source AST invariants, independent review and repository/diff checks passed. See [verification](regression.md), [plan](proposal.md) and [tasks](tasks.md). Integration and equal remote refs are recorded after push. No deployment, public database migration/reset or real provider/business operation was performed.
