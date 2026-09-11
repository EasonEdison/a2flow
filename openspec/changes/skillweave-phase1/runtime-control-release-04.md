# A2Flow Runtime implementation slice 04

Record: AF-RUNTIME-04. Date: 2026-09-08.
Base: server main 09e61917ee3e59b3658a946fe7e0e4d63409a299.
Status: source implementation authorized after the owner's six-point plan and
independent SDK review; live PostgreSQL verification remains separately gated.

## Scope

Continue only the Python Agent/Workflow Runtime. Six other domains stay paused.
Implement native stop and fresh restart using existing SDK execution and
PostgreSQL state, not a second workflow scheduler. Runtime owns its service,
experiments and existing OpenSpec change; root manifests, shared contracts,
HTTP/B UI/Compose and deployment remain outside this slice.

## Confirmed behavior

- Once STOP is accepted, all branches admit no new nodes, model/Tool rounds,
  workflow-affecting Actions or retries. No successor, routing, Finalizer or
  success transition may advance the stopped run. State must exist even before
  any Application/card has been rendered.
- Already-dispatched work may finish. Preserve real success/failure/unknown
  outcomes without undoing business writes or continuing the stopped run.
  Old cards remain historical records and cannot resume it.
- Restart creates a fresh run and native checkpoint thread from the entry.
  Use fresh trusted input/current configuration, never old execution context,
  checkpoints, node results or interactions. Do not inspect previous business
  outcomes or block restart on old unknown results. Preserve old history.
- Control-request deduplication, trusted userId/environment and ordinary
  current-run Tool/authorization/version checks remain. There is no business
  rollback, compensation, cross-run business deduplication or generic recovery.

## Approved bounded implementation

Add only Runtime-owned run lifecycle, canonical control receipts and admitted
operation-result records. The latter store facts, never schedule/recover work.
Use a short run-row transaction for STOP/admission/conditional success; STOP
must not wait for the AF03 admission session held across a business executor.
Keep a consistent admission->run-lock ordering, never the reverse.
An Action/run combined write must commit before external dispatch; a nested
savepoint is not independent durability. Verify from another connection.

Use Runtime-owned node/router wrappers, AgentMiddleware and public model
callbacks (including inherited summary calls). A dedicated BaseException stop
signal may bypass ordinary SDK retries/error conversion, but only the controlled
runner may map it to an already recorded STOPPED state. Other BaseExceptions
must not be mislabeled STOPPED or silently swallowed. Real SDK tests must prove
the signal's behavior and independent late-result persistence.

This slice implements restart from a STOPPED source. This is an implementation
boundary, not a permanent product prohibition for every other source state.
Only old lifecycle identity/definition association may be read for authorization;
old business/Action/checkpoint/results must not be inspected or inherited.
The fresh-run factory resolves current configuration and new input. Duplicate
restart controls return the same assigned run without another graph invocation;
uncertain startup is not automatically replayed.

Engineering interpretation of the confirmed no-new-admission policy: STOP
linearizes at its committed run-state transition against each individual
operation's admission. A call already successfully admitted before that point
is in-flight; it may finish and record facts, never acquire a blanket permit
for subsequent rounds. Queued work not yet admitted must reject. This is not
atomicity between a database commit and arbitrary Python/network instructions.
STOPPED means future progression is closed, not that every old operation has
physically terminated. SDK bookkeeping is not business routing admission.

Keep the currently supported synchronous Runtime entry in scope. Async hook
checks may be tested, but do not claim a complete async stop/execution service
from the existing async Finalizer tests alone.

Use public SDK extensions. Cover node/router boundaries, model and Tool calls,
Finalizer and Action ingress. A model-only agent must also be stoppable.
Check internal SDK model calls such as summarization, not just the main model.
Account for parallel Tool batching and fatal-exception cancellation: raising an
exception is not proof that already-dispatched siblings' results were saved.

## Bounded acceptance

1. Waiting and no-card runs stop durably; wrong owner/environment rejects.
2. Race STOP with node/model/Tool/Action dispatch. After accepted STOP there are
   no new admissions; late real outcomes survive without successors or success.
3. Independent branches and multiple Tools cannot bypass stop; no ordinary
   error handling or Finalizer can turn the stopped run into success.
4. Old cards and native resume entries reject a stopped run across processes.
5. Fresh restart has new run/thread/interaction IDs and blank runtime context.
   An old successful or unconfirmed operation cannot add a restart gate or
   suppress a normal new-run business call. Old history remains unchanged.
6. Same control request returns the same platform result; conflicting input is
   rejected. A duplicate restart never creates another fresh run.
7. Keep accepted Action semantics and focused prior tests. Use deterministic
   synthetic models/business ports and real public SDK execution boundaries.

Any new live PostgreSQL window requires a separately reviewed exact test script
and single-executor release. AF03's completed window does not authorize reruns.
Deliver stable worker SHA and evidence for main-brain review before server-main
integration; main-brain owns GitHub synchronization. No production readiness or
deployment follows solely from a source/test slice passing.

Public references: [LangChain custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom),
[LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
and [persistence](https://docs.langchain.com/oss/python/langgraph/persistence),
plus the installed SDK source. These establish available hooks and checkpoint
semantics, not the product stop guarantee by themselves.
