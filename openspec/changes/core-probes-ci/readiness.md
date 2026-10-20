# Readiness

PASS for scoped source delivery and local execution of the public gate commands.
Integrate with capability-approval `da2ff11f` and package-restore `9d84cbc6` (or a
verified descendant). The workflow intentionally requires their probe sources,
and bootstrap references the approval worker's V003 migration. Do not deploy this
branch alone without those dependencies.

The two PostgreSQL probes, timeout/collision cleanup, full combined JDK 17 Maven
compilation, both Java probe mains, repeated V003 application and static checks
passed locally. See [regression](regression.md). A remote GitHub Actions run remains
unverified and distinct from this source delivery/local command evidence.

No deployment is part of this branch.
