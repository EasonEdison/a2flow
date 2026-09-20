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

- Durable conversation thread mapping and PostgreSQL checkpoint admission.
- Migration from legacy B-side text history into native messages, once per
  conversation. The current adapter still imports legacy history on each request.
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
