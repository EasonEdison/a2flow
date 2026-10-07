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
