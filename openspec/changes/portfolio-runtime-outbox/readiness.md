# Readiness

SOURCE AND ISOLATED VERIFICATION READY. INTEGRATION, DEPLOYMENT AND PUBLIC ACCEPTANCE PENDING ROOT.

The approved lifecycle transactional outbox and native waiting projection recovery are implemented. The 15 direct PostgreSQL/native-checkpoint checks in regression.md pass. Runtime does not import scheduler; deployment supplies the writer. Existing schema is reused. Business dispatch and external notification retry policies are unchanged.

Native checkpoint/outbox consistency is eventual through read-only recovery, not an exactly-once business execution guarantee. Waiting eligibility is rechecked under the run lock. External delivery ambiguity remains UNKNOWN. Deployment must include both Runtime and scheduler changes; no new migration is needed beyond existing runtime/scheduler bootstrap.

The initial heavy probe attempt inside the ECS Runtime container exited 137 and the container restarted once. The cause was not independently established as OOM; the subsequently observed OOMKilled flag was false. Its generated schema was removed and verified absent. All final evidence was obtained from the isolated local Docker environment instead; no further live-container fault probes were run. Root was notified and owns deployment health verification.
