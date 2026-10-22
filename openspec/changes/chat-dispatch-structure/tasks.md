# Implementation tasks

- [x] Record the concrete ownership plan before implementation.
- [x] Remove notification versions and dirty state; preserve the single outstanding callback gate.
- [x] Clear the Event before durable queries; keep Event operations on the owning loop.
- [x] Replace three active containers with one task-to-turn map.
- [x] Centralize drain, settlement and waiting without an extra Agent loop.
- [x] Bound retry-persistence faults and close the signal even if shutdown settlement fails.
- [x] Adapt all existing PostgreSQL cases and add task exit, waiter cleanup and double-fault probes.
- [x] Complete scoped probes, strict quality and independent source review.
- [x] Integrate, push and verify equal origin/main and github/main refs.

Deployment and public data changes are outside this source-only task.
