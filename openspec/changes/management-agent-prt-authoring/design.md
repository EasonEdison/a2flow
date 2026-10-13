# Design

## Responsibilities

React management conversation -> Java authenticated ingress -> Python management Deep Agent
-> bounded management tools -> existing Java dispatcher, asset services and release center.
Java remains the authority for assets, validation, versions, ownership and publication.
Python reuses build_agent, model factory and native PostgreSQL checkpoints. No second workflow
orchestration system is introduced. Existing B conversations and runtime domains remain isolated.

## Identity and transport

Every external management request validates Cookie and administrator access at the Java ingress.
The turn receives a trusted identity; model arguments cannot set userId, roles or environment.
Tools do not revalidate browser Cookie. Existing Java asset edit/publish guards still execute.
Java and Python use internal loopback gRPC. Java creates an opaque, bounded-lifetime grant tied
to principal, namespace, conversation, parent request and PRT. The grant is injected into tool
closures, not exposed to the model/browser. No browser Cookie crosses the internal transport.
Receipt lookup is scoped to the same authenticated principal/namespace.

## Conversation contract

POST /api/management/v2/agent/conversations/{create,list,read,send} returns the existing JSON
envelope. Send returns a durable turn/request identity quickly; Read(afterEventSeq) exposes
persisted events and turn status. Refresh only reads/polls; it never resends a mutation.
The new conversation domain is private per user. Old scope-shared authoring history is not reused.

Deep Agent history, tool messages/results and checkpoints carry the actual asset IDs, versions
and publication outcomes. A narrow Java tool receipt table provides create-operation idempotency
and request/argument conflict detection; it is not a separate task engine. Publication uses
existing immutable versions, digest checks and request idempotency.

Normal failures remain in history and permit a later explicit correction. A failed checkpoint
is not automatically replayed. Incomplete/unknown mutations freeze further writes until receipt
readback gives a definite outcome; a new model tool-call ID must not bypass this condition.
Grant expiration and host interruption are explicit failures, never automatic successful resumes.

## Asset and publication semantics

Search and reuse existing assets/interfaces. Create when requested, modify an explicitly chosen
asset, and clarify only when the target or missing business information changes the outcome.
Use typed/bounded tool arguments and existing domain validators. Business endpoints cannot be
invented. No generic shell/file backend tooling is enabled.

Changed/new assets default to PRT publication, without a separate repeated confirmation per asset.
Publish in actual dependency order. Version identities come from the release center. Verify the
serving/readback result before declaring the bundle ready. Unchanged dependencies retain their
published versions. Keep partial success and explain the failed item; no automatic bulk rollback
or duplicate reconstruction. Compile/preview and safe read-only validation are distinct from
business execution. Business writes need their own explicit user instruction.

## UI

Add a lazy management chat route and navigation entry within the current clean-modern shell.
Show conversation history, model text, actual tool progress, failures and structured asset/PRT
results with links. Do not display secrets, raw credential context or fabricated progress.
Block overlapping turns, recover observation after refresh, and preserve manual editors.
