# Workflow execution presentation

Approved scope: reuse the Chat assistant-ui execution view within Workflow steps; distinguish persisted business cards, model explanations and authoritative engine state. No business/control changes.

- Node header status comes from the engine. Model final text is a collapsed assistant explanation, not a green business-success panel.
- Tool start/end observations combine by operation ID. Model text/reasoning combine by provider model-call ID. Only provider-returned reasoning is shown.
- TOOL_DETAIL contains credential-redacted argument/result JSON in bounded numbered chunks. Display a value only when all chunks are present. Historical missing values are explicitly unavailable; never replay tools to fill them.
- Chat and Workflow share ExecutionPanel and ToolProcess; Workflow uses assistant-ui ExternalStore runtime scoped to the node. No second conversation store.
- Workflow card metadata exposes only its existing toolCallId, not private binding metadata. New recorded calls place cards after their render call; records before/after remain ordered. Older records lacking call linkage retain a separate card section rather than guessing timestamps.
- Card headings use the configured business step title; technical Application codes and card IDs are inside technical details. This does not invent an application display name or alter A2UI component contracts.
- Completed steps show readonly historical cards, initially folded. The authored A2UI content is preserved; no heuristic deletion of editor components.
- Raw action results remain expandable. Existing saved model explanations remain intact; new model responses are prompted to be brief and Chinese, without internal IDs unless requested.

Verification before public acceptance: TypeScript/build; bounded capture/import probes; live public historical restoration, tool detail expansion/copy, new run and A2UI action continuation; console/desktop/narrow viewport checks. A build is not runtime acceptance.
