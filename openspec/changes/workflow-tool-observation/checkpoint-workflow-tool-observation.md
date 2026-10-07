# Workflow tool observation

Baseline: origin/main 39b0dbd. Scope: approved workflow presentation reuse;
this worker captures tool arguments/results only, without UI/control changes.

- TOOL_DETAIL adds string fields toolOperationId, toolName, toolCallId,
  detailKind (arguments/result), chunkIndex (zero-based), chunkCount, text.
- Assemble every chunk before decoding JSON; missing chunks are incomplete.
- Arguments retain full sanitized JSON. Results contain toolMessageStatus and
  result from the matching ToolMessage, never arbitrary Command state/artifacts.
- Reuses Chat credential redaction; existing capture byte/count limits remain
  explicit CAPTURE_INCOMPLETE, not silently truncated JSON.
- Synchronous and asynchronous handlers are observed; exceptions and graph
  interrupts propagate unchanged. Candidate only; no deployment authorization
  exercised by this worker. Integration/runtime acceptance belongs to coordinator.

## Failure visibility follow-up

A real RPC failure during Action continuation exposed a pre-existing missing
failure boundary: the native checkpoint stored the error, but the sequential
node permit and display remained running. Shared invoke now publishes the existing
RUN_FAILED event for initial execution and continuation failures. The sequential
composition closes only open NODE facts as UNCONFIRMED and projects that state.
Completed nodes and successful business Actions are not changed or rolled back.
GraphInterrupt remains a wait, not failure. The original exception is re-raised;
observation-write failures add explicit notes and do not replace it.

Only new exceptions are handled. No scan, history repair, retry or automatic
replay is added; a historical stuck run remains unchanged and can use normal Stop.
Isolated current-image probes passed for continuation error, original exception,
pending-node-only updates, preserved Action, interrupt exclusion and observer
failure. No model invocation or production data mutation was used by the probes.

The approved terminal follow-up also persists FAILED for a real shared graph
execution exception. Both snapshot and view expose lifecycle=FAILED; polling
treats it as terminal, and the existing non-RUNNING admission rejects new work.
STOPPED/SUCCEEDED/FAILED cannot be overwritten with a different terminal state.
Successful business Actions and completed nodes remain unchanged. Failure events
use the existing RUN_FAILED notification path; scheduler uncertainty reconciliation
still performs GET only and never replays a workflow command.
Isolated probes additionally cover FAILED storage/codec/read projection,
non-active admission rejection and terminal immutability. Historical stuck runs
are not repaired; normal Stop remains the authorized way to close those old runs.
