# Source readiness

Status: **SOURCE_READY / NOT_DEPLOYED**.

The current-schema implementation and isolated acceptance cover the three approved stages: atomic product completion, unified durable turn/continuation registration, and validated neutral native result recovery. Completed result repair does not re-execute a model or tool. Unknown execution remains review-only. Write approval, exact saved operations and Workflow interrupts remain independent and retain their existing guards.

See [design](design.md), [validation and limitations](regression.md), and [tasks](tasks.md). Core probe integration is included in the existing CI runner; local gate results do not imply a successful remote CI run.

This is a latest-only release. Existing incompatible tables are rejected without mutation. There is no legacy backfill, protocol adapter, dual write, destructive reset or automatic public upgrade. Source integration and target ref equality are required before closing source delivery. Public deployment and real-provider acceptance are separate, currently unperformed gates.
