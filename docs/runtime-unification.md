# Runtime unification: incremental delivery

## Delivered source

- The attended B-side binds its authenticated user and configured environment
  to each private Runtime request, including SSE. Browser cookies stop at B-side.
- The current single-host Runtime listener accepts loopback peers only and
  disables proxy-header rewriting. Identity headers are not credentials; never
  expose this listener through a public proxy. A multi-host deployment needs an
  explicit trusted-network boundary before changing this policy.
- Conversation and Workflow construction now share the Deep Agents SDK factory.
  Conversation model/tool rounds and ToolRuntime injection use the SDK rather
  than a second handwritten ReAct loop. Native tool IDs and provider message
  metadata remain in the completed in-memory graph state.
- Workflow lifecycle, stop, closed tool arguments and required-tool Finalizer
  remain Workflow policies. Plain conversation greetings need not call a tool.
- SDK filesystem/execute/subagent tools remain disabled. Existing conversation
  tools are still use_skill and propose_workflow_run; the latter never starts a run.

## Not yet delivered

- Shared PostgreSQL Store memory and view/delete/disable controls.
- Conversation-scoped ability execution and Application interactions.
- A bounded native-event-to-SSE bridge: the attended adapter still buffers a turn.

Do not treat this source change as completion of persistent history/memory or
as a deployment. Existing fixed-owner Workflow runs need an explicit ownership
migration using authoritative B-side ownership records before upgrading a live
installation. No automatic identity fallback or database rewrite is included.

SDK extension reference:
[Deep Agents customization](https://docs.langchain.com/oss/python/deepagents/customization).
Compatibility is tested against the repository's pinned SDK, not an implicit
dependency upgrade.

## Conversation checkpoint delivery

Attended schema initialization now explicitly creates the native PostgresSaver
tables and the small agent_conversations ownership/admission table. Request
handling performs no schema initialization. A private, random thread ID is
mapped to (environment, userId, conversationId); it is never chosen by the model
or browser. Each turn uses a dedicated PostgreSQL session advisory lock. Do not
put this connection behind a transaction-pooling proxy.

The first checkpoint imports all available legacy user/assistant display rows
before the current input's server-issued message ID, with an owner predicate.
There is no 200-row/4000-character truncation. Display events remain display text;
we never fabricate old tool calls/results. Later turns pass only the new input
to the SDK. Existing transcript rows remain untouched. New submitted inputs are
marked so they cannot be mistaken for legacy imported history.

Concurrent turns return CONVERSATION_BUSY without calling the model. Failed or
crashed turns block with CONVERSATION_REQUIRES_REVIEW rather than replay tools.
Users can start a new conversation; operator recovery of an incomplete thread
is not included. A missing checkpoint for an existing conversation fails closed.
The latest completed turn ID is deduplicated; this is not a full historical
request ledger or a business exactly-once guarantee.

The B-side transcript is still a display projection, not the model history.
Transcript delivery-status reconciliation and incremental SSE remain follow-up
work. This change does not make disconnect/reconnect streaming durable.
