# Quality review and remaining work

Review baseline: `01010a63` (2026-10-20). This is a source/evidence audit, not a penetration test, full dependency audit or production certification. It covers repository entry points, current deployment assembly, runtime lifecycle and B authentication; it does not claim every implementation path was exercised.

## Findings addressed in this change

| Priority | Evidence and consequence | Change |
| --- | --- | --- |
| P1 | Root READMEs still described the 2026-09-07 engine experiment and said M/B were not delivered | Current capability matrix, implementation map, dated evidence and explicit limits |
| P1 | `native_control.py` allocated a run before graph setup, but failed lifecycle only when a graph existed | Fail setup runs through the existing lifecycle; preserve already stopped/successful terminal states |
| P1 | B `app.py` performed scrypt and synchronous PostgreSQL calls in async auth endpoints | Use FastAPI's existing bounded worker pool through synchronous handlers |
| P2 | `identity.py` accepted non-ASCII session strings before ASCII hashing | Validate the actual 43-character URL-safe token contract before lookup |
| P1 | Only two DTO modules were covered by the sole CI job; current M/B builds were absent | Add repository checks, both frontend builds, Java compilation and no-service Compose validation |
| P1 | Root license and contributor/security entry points were missing; provenance claim was overly broad | Owner-selected MIT, retained upstream notices, contributor/security/issue/PR guidance |
| P2 | Public contributor instructions mixed contradictory historical pauses and deployment snapshots | Replace with stable current rules; retain dated plans as historical evidence |

## Remaining issues, in priority order

### P1 — Fresh full-stack reproducibility

`deploy/java-management/prepare.py` assumes existing accounts/runtime state and creates roles/databases; current Compose requires an existing socket volume and private image/config/certificate chain. A new user cannot safely treat this as a fresh installer.

Next deliverable: a separate idempotent bootstrap for an empty installation, documented complete configuration inventory and publicly buildable image chain. Acceptance must start with an empty isolated database, create an administrator explicitly, publish an example asset, run the model-backed missing-input journey, restart and read the saved result. Existing data must remain untouched. Until then, the documented quick start is source validation and an explicitly synthetic UI preview.

### P1 — State/event transaction gap

`lifecycle.py` publishes events while its run-state transaction is still open; `SchedulerEventSink` in `deploy/attended/runtime_app.py` commits in a separate transaction. The state commit can fail after a notification was saved. This is a confirmed code-level failure window, not an observed production incident.

Next deliverable: write an event outbox in the same transaction as the lifecycle state, then deliver with stable event identities and consumer deduplication. Verify failures before/after both commits and process restart. This is a cross-service delivery contract change; it is not fixed by adding an unbounded retry or claiming exactly-once.

### P1 — Public authentication hardening

B-side registration/login still lacks a unified rate/admission policy. Moving blocking work off the loop does not prevent worker exhaustion. Shared proxy IPs, intended registration audience and thresholds need an explicit policy; deploy/account's existing limits should not be copied without considering B traffic. Public password access also needs verified HTTPS, exact origin/proxy configuration and a recovery procedure. No host/security policy changes are made by this source-quality change.

### P2 — Verification depth and maintainability

Repository checks catch syntax and direct dependency inversions, not runtime correctness. Strict Python checking still covers only two DTO files. Expand it by bounded module, add reproducible database failure-window checks and record expected execution invariants. Large B API/runtime assembly modules are candidates for separating transport from lifecycle logic after those boundaries have regression evidence.

### P2 — Product graph scope and measurement

The current loader supports 1–8 sequential nodes. Parallel/conditional graphs need a complete authoring-to-execution contract and end-to-end evidence, not only framework experiments. No workload/latency/cost/high-availability benchmark is published. Add a reproducible workload and report observed values before making scale claims.

## Validation record

See [this change's regression record](../openspec/changes/portfolio-quality/regression.md). Historical live acceptance remains separately linked from the README; this change does not replay those business operations. Full unit suites are not run for this change at the owner's direction.

Review references: [GitHub community profiles](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories), [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use). These guide repository hygiene, not a certification of this project.
