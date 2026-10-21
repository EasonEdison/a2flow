# Durable Chat turns and safe recovery

Approved scope: message idempotency, durable interaction continuation, and evidence-based recovery. Source implementation only; no production deployment in this change.

## Problems
Normal message POSTs currently create separate user/assistant records without a request identity. Interaction completion, continuation message creation and in-process task creation span separate failure boundaries. Runtime blocks every incomplete conversation, but cannot provide a durable completed result for repairing lost product projections.

## Ownership
Deep Agents remains the only model/tool loop. B owns message acceptance, user-visible history and durable turn delivery. Runtime owns conversation execution admission, checkpoints and per-turn execution facts. Cards own submitted input and recorded business results. Workflow continues to use native interrupt/resume independently.

## Contract
POST /api/conversations/messages accepts conversationId and clientRequestId in JSON. GET /api/conversations/messages takes conversationId as query parameter. Existing ownership checks are mandatory. Old path-based message routes are removed in a coordinated frontend/backend release; unrelated endpoints are unchanged.

Same owner/conversation/request identity with the same payload returns the original message pair; a changed payload conflicts. Receive messages and dispatch intent in one transaction. Card completion saves continuation intent in the result transaction; durable workers materialize the continuation exactly once. Ordinary input, temporary submission and approved write results share delivery plumbing without conflating their authority.

Runtime inspection returns NOT_STARTED, BUSY, COMPLETED or NEEDS_REVIEW. Only proven NOT_STARTED may execute; BUSY waits; COMPLETED replays saved safe events to repair product projection without another Agent invocation. Ambiguous execution stays NEEDS_REVIEW. Lease expiry alone never authorizes replay. A completed turn's events and conversation READY transition are saved before releasing native execution admission.

## Non-goals
No checkpoint removal, second Agent loop, business retry, automatic UNKNOWN reset, external exactly-once claim, workflow scheduler rewrite, or business reconciliation API. Existing unresolved legacy conversations remain conservative.
