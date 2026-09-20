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

- Conversation-scoped ability execution and Application interactions.
- A bounded native-event-to-SSE bridge: the attended adapter still buffers a turn.

Source delivery is not deployment. Old-data migration is explicitly out of
scope: no automatic identity fallback, remapping or database rewrite is included.
The signed64 identity change targets fresh compatible schemas; do not upgrade
an old-schema installation as if its data had been migrated.

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

## Personal preference memory

The attended initializer creates native LangGraph PostgresStore tables.
Preferences live in that Store, scoped by environment/user/default profile;
there is no second memory database or automatic extraction service.

- GET /api/memory returns the authenticated user's revision, enabled flag and entries.
- PUT /api/memory replaces that document using the last read revision. An entry
  contains id and text; omitting an entry deletes it. Stale revisions return409.
- The default is disabled. Users explicitly add preferences and enable reading.
  Disabled entries can still be viewed or deleted in settings.
- At most20 entries,1000 characters each,8000 total characters. IDs are restricted
  to letters/digits/underscore/hyphen. Strict bodies reject userId/environment.
- Chat and attended Workflow nodes use the same SDK middleware to re-read current
  settings before each model call. Workflow reads use the trusted node owner,
  never a model-supplied user or environment. The attended composition points
  both paths to the same database and native Store.
  These preferences are labeled user data, not policy or business facts; they
  are not appended as graph history messages. No model memory-write Tool or
  generic filesystem access is enabled in this slice.

Deleting/disabling affects subsequent memory reads. It cannot recall an already
dispatched model request or erase content quoted in older chat replies.
User-requested in-chat memory writes are not delivered. No production database
migration/deployment is implied.

### Settings and read-only Workflow integration

The digital-employee navigation exposes Settings / Personal memory. Users can
view, add, edit, delete entries and change the switch. All edits take effect only
after explicit Save; the page separately shows the last saved enabled state.
Turning off reading retains the entries so the user can still inspect/delete them.

Saving sends only revision/enabled/entries. Identity and environment come from
the existing authenticated B-side route. Revision conflicts retain local edits,
block resubmission and ask the user to reread; reloading unsaved edits requires a
discard confirmation. An uncertain save response also requires a reread rather
than automatic replay. Request failures never substitute a browser-local store.

Workflow memory is read-only, cannot satisfy required-tool/interaction facts,
and does not bring old run progress into a fresh run. No new model tools are
enabled. Sync and async middleware use the same untrusted-preference policy;
injected system content is not appended to checkpoint messages.

Validation: frontend typecheck/build and four state tests passed. Browser
fixtures at desktop1440x1000 and mobile390x844 exercised CRUD, disabled reads,
revision conflicts, uncertain responses, failed reads and expired sessions,
without page errors or overflow; an in-app browser repeated edit/save. Python
targeted regression collected29 tests (27 passed,2 optional PG cases skipped);
the expanded memory suite passed9 tests against disposable PostgreSQL, including
a real Store settings write read by a Workflow node without changing the record.
The B-side memory authentication/body test also passed. All model traffic was
synthetic; browser fixture evidence is not deployed end-to-end acceptance.

## Live Chat delivery and transcript projection

Ordinary Chat now forwards native Deep Agents message events during the turn,
instead of collecting the whole response at either side of HTTP. Visible output
includes text, provider-returned reasoning and tool names (not tool arguments,
raw results, credentials or opaque provider metadata). SDK reasoning blocks take
precedence over the existing DeepSeek native reasoning field; neither is emitted
twice. This display is not a new model-history source.

The B-side saves one user message and one running assistant placeholder before
starting the worker. SSE carries stable decimal-string message IDs and increasing
per-turn sequence numbers. The browser incrementally decodes UTF-8/SSE, ignores
duplicate sequence numbers, rejects gaps/mixed IDs, and requires an explicit
terminal event. It updates the existing message, not a second final answer.

Two bounded queues (64 events each) separate native worker, projection producer
and HTTP subscriber. Disconnect closes the subscription, not the producer; it
does not retry tools. The native conversation lock still spans the worker turn.
Graceful application shutdown waits for owned producers. A process kill is not
a durable worker handoff and must not be interpreted as a completed turn.

The existing messages JSON is a display projection: text, reasoning, tool names,
structured cards and delivery state. Progress is saved at most once per second
when events arrive, plus the final outcome. `completed` is emitted only after the
native iterator/session exits and the final display save succeeds. Runner error
or missing terminal means `failed`; an exception or uncertain save is
`unconfirmed`, not success. If PostgreSQL cannot save, the older persisted
`running` record remains explicitly uncertain. No automatic retry or rollback.

Reload only reads the latest 200 saved messages in chronological order, and polls
every five seconds while a turn is running/unconfirmed. It never invokes the
model. A failed history read after an uncertain send blocks sending until a
successful reread. Running details expand; terminal details collapse and remain
inspectable. Workflow confirmation cards become actionable from saved completed
history, not speculative chunks.

Limits: no token-exact replay, cross-process resume, historical pagination UI,
all-time POST idempotency ledger, or automatic checkpoint-to-transcript repair.
A native completed turn with a failed display save remains unconfirmed; the
system will not repeat execution to reconstruct it. Hard process crashes can
leave running/uncertain records for manual review. These are intentionally not
presented as successful or automatically recovered executions.

Verification: 66 Python regressions (64 passed,2 opt-in PG cases skipped), seven
frontend unit tests and production build passed. Five isolated PostgreSQL tests
cover native conversation isolation and persisted latest-window delivery updates.
Synthetic in-app browser checks show pre-completion text/reasoning/tool activity,
reload during execution and automatic collapse after completion. No real model
call, existing-data migration or live deployment was performed.
