# Design

## Sources and ownership

PRESET remains the published management asset source. PERSONAL is an immutable B-user execution configuration using the existing native workflow contract. Personal configurations do not enter the management global catalog or its environment serving table. Management Java authoring and publication remain unchanged.

Use a personal repository keyed by namespace, environment, trusted owner and definition key. Reserve personal-wf- identifiers for explicit routing. Personal lookup failure never falls through to the preset reader. Ownership must be checked in catalog/detail, run admission, graph reconstruction, versions and capability-node binding reads. A random identifier or createdBy field is not authorization.

A composed reader combines the owner's personal catalog with published presets. Skill and capability dependencies always resolve through the existing trusted environment reader and execution boundary. Validate the existing one-to-eight serial business nodes plus summary contract and the complete referenced published dependency set. Do not introduce a second compiler or use invented specialist identities.

Personal definitions in this slice are immutable after successful creation. Existing running graphs therefore cannot change through an edit. Shared Skill and capability dependencies continue using the approved current-effective-publication policy; do not add a stale-version reset gate.

## Chat tools and persistence

Expose only published candidate metadata and constrained personal create/read tools to the ordinary Chat Agent. Never expose management grants, connection details, mutable schemas as execution truth, raw RPC addresses or credentials. Owner, environment and persistence idempotency scope are supplied by the trusted backend, not model arguments.

A stable conversation/tool-invocation request identity creates at most one saved workflow; a repeated request returns that saved fact. Unknown outcomes are not automatically re-created under another key. A successful save emits personal_workflow_created with the actual workflow catalog entry. Persist this event through the existing conversation delivery/history channel so refresh does not depend on assistant prose or client-only state.

The result entry includes definitionKey, name, source=PERSONAL, defaultRequirement and lightweight node descriptions. Display actual saved identity and steps in both Chat and My workflows. No automatic business execution follows creation. The result's Run entry reuses the established workflow confirmation/start and conversation attachment flow.

## Frontend and execution

Add a Create workflow quick action above the composer that preserves the current draft and fills an editable creation intent. Retain normal send and concurrency guards. Separate Preset workflows and My workflows in the existing Workflow center, preserving run history. Refetch server truth when opening the center or after creation; do not simulate registration only in frontend memory.

Reuse existing run ownership, native graph/checkpoint, interrupts, temporary interactions, action outbox and final summary. Missing runtime arguments use temporary interaction and submission resumes the same node. Unknown or failed business execution is explicit and is not automatically replayed.

## Delivery

Add only project-owned personal configuration storage and compatible source consumers. Preserve the existing realchat deployment entry, current images/configuration and rollback plans. Build web assets off the low-memory service host. Source integration, deployment and public proof are separate gates.
