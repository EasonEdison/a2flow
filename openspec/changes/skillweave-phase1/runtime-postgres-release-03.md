# A2Flow Runtime implementation slice 03

Record: AF-RUNTIME-03. Date: 2026-09-08.
Base: server main b2f15e08f1385ce14eef3525cfd2f4b9d99346ed.
Authority: continued development and main-brain engineering delegation.
Status: source implementation authorized; live test window separately gated.

## Scope and ownership

Only oss-agent-workflow-runtime resumes; six other domains remain paused.
Runtime owns services/agent-workflow-runtime/, experiments/runtime-phase1/
and its existing OpenSpec change. Root manifests, deployment Compose, locks
and shared contracts remain root-owned. No public HTTP or deployment release.

Implement PostgreSQL interaction state and control request persistence behind
the accepted AF-RUNTIME-02 internal ports. Preserve existing Action semantics,
AI-directed Skills and native LangGraph scheduling. Do not implement business
exactly-once, automatic takeover/recovery, rollback or generic Skill retries.

The user confirmed Docker Compose as the first deployment target. This slice
does not claim to deliver the complete deployment stack or start that stack.
PostgreSQL remains the only application database; no SQLite/MySQL fallback.

## Storage and concurrency decisions

- Interaction identity includes trusted userId, environment, runId, nodeId and
  interactionId. Control records additionally include controlRequestId. Every
  lookup/update must enforce trusted owner and environment, including delivery
  status reads. An internal get(key, owner) signature adjustment is approved.
- Persist an explicit schema version and validated JSON data, not pickle or
  executable types. Keep canonical immutable request input and actual results.
  Save interaction and control state atomically in one short transaction.
- Every save commits independently, before any subsequent external operation.
  Never hold a database transaction open across an executor or graph invocation.
- Admission and continuation use distinct stable per-owner/environment/run
  advisory lock namespaces. Each scope owns a dedicated session, with explicit
  unlock/close and bounded waits. Reads/saves within admission use that session.
  No process-local lock substitutes for cross-process exclusion, and no silent
  reconnect continues a scope after loss of its lock connection.
- Native continuation occurs outside admission scope. Tool worker threads take
  their own admission scopes and never the continuation lock. Match the existing
  synchronous graph adapter with official synchronous PostgresSaver lifecycle.
- EXECUTING and DISPATCHING are durable before dispatch. Unknown historical
  outcomes are not automatically redispatched. Check lock health at dispatch
  boundaries and fail closed on connection/commit uncertainty. Already in-flight
  external work cannot be retracted by a lost database connection. Do not claim
  atomicity across that boundary or uninterrupted exclusivity after lock loss.
  Any run-level uncertainty gate must be reviewed before adding it.
- Use bounded connections and least-privilege runtime access; schema bootstrap
  is explicit. Initial test budget: runtime role limit 8, server maximum 16,
  connection/lock wait 5 seconds, statement timeout 10 seconds. Measure actual
  connection use, including saver, waiting scopes and observation connections.

## Acceptance gates

1. A fresh independent process reads waiting and completed interactions.
2. Two processes submitting the same control request dispatch a synthetic
   executor once; changed input for that ID rejects. Independent cards do not
   overwrite each other. Test counters themselves are persistent.
3. An independent connection sees EXECUTING before the external executor runs.
   Exceptions do not roll back previously committed business/control facts.
4. Wrong owner/environment, stale versions and stopped runs reject before
   execution. Payload conflict and unconfirmed states survive process exit.
5. Loss of owned test worker/lock connection cannot silently reconnect and
   redispatch. Report the in-flight graph limitation and test its boundary.
6. Real PostgresSaver: Skill -> interactive Application -> process exit ->
   Action in a new process -> exact native resume -> guarded Finalizer. An
   already completed independent branch must not rerun.
7. Preserve the accepted 24 service/SDK and 31 experimental tests. Include
   explicit serialization, connection failure and bootstrap credential tests.

## Isolated PostgreSQL verification

Before starting, root reviews the exact commands and releases one bounded
window to one executor. Use the previously verified PostgreSQL 17.11 image
digest, no published ports, network none, private Unix socket and SCRAM only.
Temporary secrets are private files, never CLI values, logs or source. Reuse
the corrected verifier bootstrap with an explicit connection-limit parameter.
Its earlier offline safety tests alone are not a live verification claim.

Proposed exact resources: container a2flow-runtime03-pg, volume
a2flow-runtime03-pgdata, private directory
/home/admin/OpenSource/.tmp/af-runtime-03-pg. Limits: 256 MiB memory, no extra
swap, 0.5 CPU, 128 PIDs, 32 MiB shared memory, no restart. Maximum 15-minute
active window and two test worker processes. Start requires at least 768 MiB
available host memory; stop below 512 MiB, on swap growth above 128 MiB,
data above 1 GiB or readiness failure after 60 seconds.

Record test evidence, observed resources and exact cleanup. Preserve unrelated
images/data. No production assets, provider credentials or business writes.
main-brain reviews the stable source before server integration and GitHub
synchronization. Source acceptance, PostgreSQL evidence and product readiness
remain separate; full Runtime remains NO READY until its other gates pass.
