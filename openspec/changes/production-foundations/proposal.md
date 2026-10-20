# Production foundations

## Scope
Provide an independently bootstrapped full self-hosted stack; atomically persist lifecycle and notification commands using the existing scheduler outbox; share database-backed login/registration admission across M and B. Deploy reviewed main and verify real HTTP/UI persistence.

## Invariants
Existing business runs are not replayed. Notifications can be delivered more than once but must be deduplicated by stable identity. Business calls are not retried by this change. Initialization targets empty isolated data and requires an explicit administrator. Public password access uses trusted TLS and exact browser origins. Preserve current real-chat launchers and rollback manifests.

## Validation
Empty-volume startup, explicit admin, example publication, model-backed missing input and continuation, restart/readback; PostgreSQL state rollback and delivery crash windows; shared auth rate budget, proxy spoof rejection, safe cookie/origin behavior; public route and UI verification after deployment. Evidence distinguishes source, deployed and runtime proof.
