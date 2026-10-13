# Execution design

- New platform tool: generate_interaction(intent, data). No appCode or Skill binding
  is required for collecting user input. Workflow nodes retain their original Skill
  business requirements; temporary interaction is not a substitute for required tools.
- Isolated single model call generates title, mode, full A2UI components and inputSchema.
  The server supplies /data from caller context and neutral /inputs values. The candidate
  cannot declare arbitrary RPC, code, URLs or new business authority.
- Strict structural/official-component, binding, input schema and submit-action checks.
  First supported input shape is bounded flat scalar/string-array fields; unsupported
  shapes fail explicitly. No repair/retry/fallback is added.
- Profile a2flow.temporary.v1, source TEMPORARY. Persist the candidate as a scoped card,
  not an invented published Application/Skill. DISPLAY_ONLY does not suspend a task.
- INTERACTIVE exposes the platform submit action. Card, result, idempotency receipt,
  observation and Workflow completion outbox are committed in one local transaction.
- Result is {status: SUBMITTED, values: {...}}. Observations do not assert capability or
  business success; the result is untrusted user input supplied to the owning Agent.
- Chat creates at most one continuation message pair per completed card, then executes
  ChatDelivery server-side. Replayed action requests reuse receipts and never rerun
  the model. Existing in-process conversation work is allowed to finish first.
- Flow uses existing node scope, interrupt, durable submit fact and resume gate.
  Native replay returns the saved generated card rather than another model call.
- Historical completed cards are read-only. Refresh is a saved-state read, not execution.
  Local browser drafts are scoped to the current account and browser; they do not sync across devices.
- No new runtime version-reset requirement, automatic whole-Flow generation, generic
  business CRUD, or long-lived application instance is introduced.

- Generation supplies the full candidate JSONSchema and a validated two-field protocol example.
  The model must produce matching inputSchema fields, bound controls and submit-context fields.
  Strict admission remains authoritative; safe rejection logs contain reason/type/count metadata,
  never generated content or user input. No candidate normalization or retry is performed.

- Card submission automatically starts the next model turn. The server-owned continuation
  input record is retained for turn identity/deduplication but omitted from the conversation
  display API; it must not appear as a user-authored chat bubble. Assistant progress and
  answers remain visible, including after history reload. This also covers existing records.
