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

### Foundations follow-up

The three P1 findings above have a scoped follow-up implementation:

| Original issue | Implementation and evidence |
| --- | --- |
| Fresh installation | Independent [self-host bootstrap](../deploy/selfhost/README.md), public build stages, explicit admin and configuration inventory; preserved operator deployment |
| State/event transaction gap | Injected same-transaction outbox writer, stable lifecycle IDs, idempotent delivery recovery, and read-only native waiting recovery; [failure-window checks](../openspec/changes/portfolio-runtime-outbox/regression.md) |
| Public account protection | Shared PostgreSQL admission, registration policy, exact trusted proxy chain, HTTPS deployment template and account recovery; [guard checks](../openspec/changes/oss-account-abuse-guards/regression.md) |

The [foundations readiness record](../openspec/changes/production-foundations/readiness.md) distinguishes implemented source, fresh-install verification and public deployment. Do not interpret this table as a general security or availability certification. Model keys, DNS/TLS ownership and a configured business domain remain operator inputs; no universal default credentials or automatic business adapters are provided.

### P2 — Verification depth and maintainability

Repository checks catch syntax and direct dependency inversions, not runtime correctness. Strict Python checking still covers only two DTO files. Expand it by bounded module, add reproducible database failure-window checks and record expected execution invariants. Large B API/runtime assembly modules are candidates for separating transport from lifecycle logic after those boundaries have regression evidence.

### P2 — Product graph scope and measurement

The current loader supports 1–8 sequential nodes. Parallel/conditional graphs need a complete authoring-to-execution contract and end-to-end evidence, not only framework experiments. No workload/latency/cost/high-availability benchmark is published. Add a reproducible workload and report observed values before making scale claims.

## Validation record

See [this change's regression record](../openspec/changes/portfolio-quality/regression.md). Historical live acceptance remains separately linked from the README; this change does not replay those business operations. Full unit suites are not run for this change at the owner's direction.

Review references: [GitHub community profiles](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories), [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use). These guide repository hygiene, not a certification of this project.
