# Readiness

The original four-probe scope passed local execution; the approved extension is
IN PROGRESS pending the final A2UI/Chat/Workflow compatibility candidate.

Original scoped source delivery and local execution:
Integrate with capability-approval `da2ff11f` and package-restore `9d84cbc6` (or a
verified descendant). The workflow intentionally requires their probe sources,
and bootstrap references the approval worker's V003 migration. Do not deploy this
branch alone without those dependencies.

The two PostgreSQL probes, timeout/collision cleanup, full combined JDK 17 Maven
compilation, both Java probe mains, repeated V003 application and static checks
passed locally. See [regression](regression.md). A remote GitHub Actions run remains
unverified and distinct from this source delivery/local command evidence.

No deployment is part of this branch.
