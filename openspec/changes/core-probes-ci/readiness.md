# Readiness

READY for coordinated source integration. The approved expanded gate passed
locally against application candidate `942c2502172c06218194dd2a6b322430a3130267`
plus the probe-only Chat update `739a2f185b6b125763192edd9b0f12a01fe81630` and
this branch's final runner/dependency fixes.

- Python: account guard, outbox 15, actual executor/PG 70, Chat 227, Workflow 41
  and A2UI 38 checks all passed in one sequential suite.
- Java: JDK 17 compiled 611 sources; durable approval 41 and package restore 107
  checks passed. All 573 committed Java input files matched the build export.
- Containers, temporary classes and private files were cleaned. No model or live
  business call occurred. See [regression](regression.md) for exact boundaries.

Original scoped source delivery and local execution:
Integrate with capability-approval `da2ff11f` and package-restore `9d84cbc6` (or a
verified descendant). The workflow intentionally requires their probe sources,
and bootstrap references the approval worker's V003 migration. Do not deploy this
branch alone without those dependencies.

The two PostgreSQL probes, timeout/collision cleanup, full combined JDK 17 Maven
compilation, both Java probe mains, repeated V003 application and static checks
passed locally. See [regression](regression.md). A remote GitHub Actions run remains
unverified and distinct from this source delivery/local command evidence.

No deployment is part of this branch. The GitHub workflow itself has not yet
executed remotely; local success does not imply a green GitHub run.
