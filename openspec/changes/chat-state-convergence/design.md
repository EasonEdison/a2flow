# Latest Chat persistence contract

User scope: implement only the current version; no legacy migration, dual writes or compatibility adapters. No Agent framework or Workflow execution-engine replacement.

| Record | Authority and important fields |
| --- | --- |
| `agent_conversations` | `(environment,user_id,conversation_id) -> thread_id`; no READY/RUNNING/FAILED or last-turn copy |
| `agent_chat_turns` | native `RUNNING/COMPLETED/NEEDS_REVIEW`, complete `result`, real timestamps |
| `chat_turns` | input/assistant message identity, scope, `source_kind/source_key/source_digest`, optional `processing_task_id`, dispatch generation and product delivery status |
| `chat_requests` | scope/clientRequestId/request digest -> unified turn; composite foreign key prevents cross-scope aliases |
| `chat_continuations` | stable card/confirmation identity, `PENDING/MATERIALIZED/NEEDS_REVIEW`; same transaction as card completion |
| `chat_turn_events` | delivery sequence, dispatch generation, public event; generation check fences stale producers |
| `messages` | user inputs and bound public display projection, not native model history |
| handling/approval records | task resolution, exact operations, confirmation/consumption and card association remain independent |

`processing_turns`, duplicate product request columns, duplicate request assistant IDs, continuation booleans and native event arrays are absent. Different client IDs may reference the same processing source. Reusing an ID with different content is a conflict, not a new execution.

## Execution and completion boundaries

1. Lock the product conversation and register its pair/source/alias atomically.
2. Product dispatch serializes the conversation and claims a new writer generation.
3. Native inspection uses the native execution lock. NOT_STARTED alone permits a new model turn; BUSY waits; NEEDS_REVIEW blocks.
4. Native completion commits a validated neutral result before releasing execution admission.
5. Live B delivery or direct completed-result repair binds the original message identities. Final projection and product COMPLETED commit in one PostgreSQL transaction.
6. A missing terminal journal record is repaired from committed delivery facts. There is no model/tool replay during subscription or projection repair.

The complete result includes terminal evidence, final model identity/text, ordered text/card/Workflow parts, tools/arguments/outcomes, model process and visible reasoning. The checksum is an integrity aid, not proof of authorization: structural, sequence, text/part/card relations and target turn identity are also validated. No provider/SDK state or identity credential is stored in this public result contract.

`waiting_action` is current-turn completion with an outstanding interaction, not business resolution. A waiting event distinguishes CURRENT_TURN cards from EXISTING cards using render facts consumed by the accumulator. Referring to an already-pending card does not render it again or change its original turn ownership; a card rendered in this turn must retain its complete part and render relation. A card submission or approved write creates a separate durable continuation. The original business operation is not submitted again. Reminder acknowledgement is not handling resolution.

Journal numbering and pure result ordering are distinct. Live delivery starts after the saved journal cursor, and stale-generation inserts are rejected. Completed recovery directly replaces the display from a saved snapshot rather than rewriting token history. Within the current generation the journal permits replacement at an existing sequence; it is not immutable event storage. A later generation appends after the saved cursor and cannot overwrite a prior generation at the same sequence. Every event write first verifies the active generation under the turn row lock.

## Installation and unsupported structures

Use the repository self-host initialization entry on an empty, isolated installation database. Native `ConversationStore.setup` verifies the exact current table fields before initialization; product startup checks required source/continuation/journal structure and rejects removed legacy fields. Incompatible existing data is not silently converted, cleared, renamed or retried.

This change deliberately ships no migration or destructive reset command. An existing installation needs a separately scoped operator/data decision before deploying this version. Source checks and disposable-database acceptance do not authorize deletion of public history. Backups and old releases remain untouched.

## Source navigation

- [state vocabulary](../../../packages/contracts/src/skillweave_contracts/chat_state.py)
- [neutral result accumulator and validator](../../../packages/contracts/src/skillweave_contracts/chat_result.py)
- [unified registration](../../../services/b-side-api/src/a2flow_bside/turn_registry.py)
- [product dispatch and atomic final projection](../../../services/b-side-api/src/a2flow_bside/durable_chat.py)
- [native admission/result persistence](../../../services/agent-workflow-runtime/src/agent_workflow_runtime/chat/persistence.py)
- [production Chat adapter](../../../deploy/attended/chat_runner.py)
