# Readiness

NOT READY for standalone integration: the workflow intentionally requires the
capability-approval and package-restore workers' probes, and bootstrap references
the approval worker's V003 migration. Integrate the three owned changes together.

The two PostgreSQL probes and focused package-restore probe passed locally.
Timeout cleanup passed. Final joint Java execution and static checks are recorded
in [regression](regression.md) as they complete. A remote GitHub Actions run remains
distinct from source delivery and local verification.

No deployment is part of this branch.
