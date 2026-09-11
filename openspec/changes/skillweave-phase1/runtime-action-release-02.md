# A2Flow Runtime implementation slice 02

Record: AF-RUNTIME-02. Date: 2026-09-08.
Authority: user instruction to continue development, existing engine-first
priority, and main-brain's delegated engineering responsibility.
Base: server main 5efc7e7bfc7be1451808368c5e75f653b217ed39.
Status: scoped implementation authorized; not runtime acceptance or deployment.

## Ownership and deliverable

Only oss-agent-workflow-runtime resumes. The other six domains remain paused.
Runtime owns services/agent-workflow-runtime/ as a new internal Python module,
alongside its existing experiments/runtime-phase1/ and OpenSpec change paths.
This extends the earlier probe-only path grant for this slice; it does not
approve a public HTTP protocol, new resident process, or full shared Action
schema. Root manifests, locks and packages/contracts remain outside this grant.

Deliver a Runtime-owned Action admission, execution, result interpretation and
interaction completion module, with a LangGraph continuation adapter. Replace
the explicit post-interrupt unimplemented boundary only where this module
provides the required checks. Keep AI-directed Skill execution and public SDK
extension points; do not build a second scheduler or fixed business Skill graph.

Use reviewed Skill/Policy definitions and narrow injected ports for trusted
configuration, execution and saved interaction state. Internal models are not
published wire contracts. Test doubles must be explicit test fixtures, not
runtime storage fallbacks. Reuse the existing Python 3.11 environment.

## Acceptance cases

1. DISPLAY_ONLY returns without interrupt. INTERACTIVE waits on its specific
   run, node, Application and interaction identity.
2. Client/model input cannot set trusted userId/environment or declare business
   success. The Runtime obtains those facts through trusted adapters.
3. Before an operation is dispatched, reject wrong ownership, stale interaction,
   stopped run, or effective-version mismatch. Mismatch requests an explicit
   Workflow reset and does not execute the old Action or restart automatically.
4. Evaluate the executor's actual result against configuration-owned success
   policy. Transport or ToolMessage success alone is insufficient.
5. Failure does not resume. Success without the configured interaction-completion
   flag does not resume. Successful completion supplies the verified result to
   LangGraph continuation; a caller-provided completion boolean is insufficient.
6. Pending interaction and negative business facts cannot be overridden by the
   Finalizer. Verify this at the real adapter boundary, not only in a DTO test.
7. Deduplicate platform control requestIds within an explicit run/interaction
   scope. This is not business exactly-once or cross-run business deduplication.
   Unsupported concurrency/durability must be stated, not implied by a dict.
8. Preserve history; do not add rollback, compensation, old-result reconciliation,
   generic Skill recovery, or generalized retries.
9. Preserve the established independent-branch progression and join behavior.

Stop/fresh restart orchestration, eligible node retry implementation, complete
configuration publication, multi-instance locking, HTTP service, B interface,
and real-model deployment are subsequent slices, not required to over-expand
this one. Rejecting a stopped run in Action ingress is included now.

## Verification and delivery

Use deterministic synthetic fixtures and focused positive/negative tests.
Existing memory probes do not prove PostgreSQL durability. No new PostgreSQL
container or host/service change is granted here; submit a bounded verification
plan if persistence becomes the next necessary gate. No real business writes,
provider secrets or public endpoints are needed for this source slice.

Report adopted baseline, actual old-plan conflicts, changed paths, stable worker
SHA, test evidence and remaining limitations. main-brain reviews the stable diff
before releasing integration, then the owner integrates through its exclusive
server integration worktree. main-brain owns reviewed github/main synchronization
and ref readback. Source delivery, SDK tests, PostgreSQL evidence and product
readiness remain separate claims.
