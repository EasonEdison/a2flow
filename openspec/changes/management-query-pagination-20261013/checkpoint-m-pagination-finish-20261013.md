# M pagination worker checkpoint

Owner: `m-pagination-finish-20261013`. Target: `services/management-java` only. Base: `origin/main` at `812b8b2eec40682f8d1cbdd2cd2de27017a0431c`.

## Implemented

- `CAPABILITY_LIST` alone returns a numbered summary page and SQL total. Candidate, published and detail contracts retain their existing paths. Keyword, current revision classification and editing/online filters run before SQL `LIMIT`; current-page relations are batched.
- `A2UI_APPLICATION_LIST` returns a numbered summary page and SQL total. Only the selected page reads canonical source to compare its digest with exact PRT/ONLINE published snapshots. Detail remains the edit contract.
- Capability, Component Center Application tab and dedicated Application page use server totals, reset to page one on filters, and guard stale responses.

## Evidence

- Local JDK 17 `mvn -q -DskipTests compile`: pass.
- Frontend `npm run build` including `tsc --noEmit`: pass.
- Disposable PostgreSQL fixture `management_query_test`, 125 capability and 125 Application rows: SQL page/total, tail page, keyword, revision-specific relation, last relation, specialist, editing, ONLINE/PRT/DRAFT, inline and referenced Build status checks: pass. Probe: `backend/storage/db/tests/ManagementPaginationJdbcProbe.java`.
- No server Maven/npm build and no production database write. Main integration, deployment, authenticated browser readback and runtime performance measurements remain root-owned.

## Resume cursor

Review exact outgoing files and status, run `git diff --check` and provenance/secret scan, commit and push only the worker branch. Give root exact SHA and evidence; root owns main integration and deployment.
