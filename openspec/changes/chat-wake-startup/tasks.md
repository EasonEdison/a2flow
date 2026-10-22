# Async Chat startup tasks

- [x] Verify human authorization and current source; record the plan before changes.
- [x] Create ready ChatWake in a running loop; remove bind/unbound/default-lazy construction.
- [x] Move concrete production Chat dependency construction into the typed startup factory.
- [x] Inject the same wake into admission/card observer/dispatcher dependencies.
- [x] Give application lifespan readiness and close ownership; dispatcher only runs/stops/settles.
- [x] Exercise real FastAPI startup, failed startup, shutdown waiting and multiple lifetimes.
- [x] Adapt PostgreSQL owners/spawn boundaries to explicit async wake construction.
- [x] Complete the final nine scoped groups, 33-file quality and independent review evidence.
- [x] Integrate and push; verify origin/main and github/main equal and worktrees clean.

Source only; public deployment and production data changes are not included.
