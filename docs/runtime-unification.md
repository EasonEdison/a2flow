# Runtime unification: incremental delivery

## RPC 兼容性边界（2026-09-26）

- 不比较 Java 与 Python 的整份描述符，不比较字段总数，也不要求请求传齐接口中的可选字段。
- 新增无关字段、消息、方法及 JSON 名称元数据不构成拒绝原因。
- 根据注册描述符解析实际服务、单次调用方法及参数映射；实际传入参数仍遵循必填与类型约束。
- 执行服务只校验实际注入的 `user_id / environment / request_id / client` 的字段编号、类型和单值语义，以及 `PRT / ONLINE` 的枚举值。共享 oneof 不能让这些字段相互覆盖。
- 身份上下文由服务端注入，不能从模型业务参数覆盖；此约束与描述符是否完全一致无关。

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
- SDK filesystem/execute/subagent tools remain disabled. Wired conversation
  tools are use_skill, execute_ability, render_application and
  propose_workflow_run; the latter never starts a run.

## Not yet delivered

- Arbitrary Application/component profiles, generalized LoadBinding and HTTP adapters.
- Automatic model resumption after a Chat card Action (Actions update the card
  directly; the next user turn can read recent saved card outcomes).
- Live-provider/deployed-browser acceptance of the new Chat Application chain.

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

The B-side transcript is a display projection, not the model history. Incremental
SSE and saved delivery outcomes are implemented in the live-delivery section
below; token-exact replay and automatic checkpoint-to-transcript repair are not.

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

## Shared Skill execution foundations

Workflow structure, node progress and workflow controls are ordinary product UI,
not A2UI. A Skill may produce an Application whether invoked by Chat or a
Workflow node. Reuse must not manufacture Workflow run/node identities for Chat.

The shared Application preparation module now validates published templates,
render policy, data and backend-resolved Action descriptors into immutable
display material. It has no graph, checkpoint, run/node, user, persistence or
transport dependency. This is deliberately a preparation service, not a new
conversation lifecycle or a promise that arbitrary Applications can execute.
The existing Workflow render Tool delegates preparation to it, then retains its
own saved interaction, identity, interrupt/resume and completion policy. Its
one-Action MVP continuation restriction remains; accepting multiple display
descriptors in the pure preparation service does not enable new routing.

The shared Ability execution module owns registered-operation authorization,
definition/input/output validation, result-policy evaluation and JSON isolation.
Callers still own trusted identity, Skill binding, current-version admission and
registry selection. It never turns model input into a URL or credential.
Workflow preserves its current Action ledger and business-result semantics;
Action execution is not replaced by a fail-fast model Tool helper.

Conversation wiring, durable surfaces, authenticated Actions and the existing
bounded Application profile UI are now implemented below.
User Actions execute configured business operations and update saved
card state directly, without an obligatory model call. Only the owning lifecycle
decides whether completion resumes an Agent or advances a Workflow node.
No generic HTTP transport, LoadBinding expansion, deployment or live-model call
is delivered by this foundational extraction.

Verification of this foundation: 38 combined offline regressions passed against
the pinned runtime image with network disabled, including the existing three-node
Workflow, Skill display-only/interactive behavior, saved Action continuation,
Chat regression, shared Ability validation and immutable Application preparation.
A publication change during input validation prevents dispatch: the shared
Ability caller supplies a required version-admission callback run immediately
before the registered operation. Independent scoped preparation review found no
blocking issue. This is not Chat Application end-to-end or deployment evidence.

## Chat Skill / Application vertical slice

Chat uses an authenticated conversation owner and the same published Skill,
Ability and Application definitions as Workflow, never fabricated run/node IDs.
`use_skill` grants only that Skill's resolved dependency closure. Ability calls
check registered callability, input/result schemas and configured success.
Every dispatch/render/Action checks the recorded version closure. Changed
configuration returns `RESET_REQUIRED`; old cards are not reinterpreted silently.
Skill admission and Application rendering are exclusive tool batches to avoid
concurrent admission changes or business calls racing an interactive stop.

DISPLAY_ONLY saves a card and continues the model. INTERACTIVE saves first,
then ends the model round through a public SDK middleware hook. The transcript
records `waiting_action`, not business completion. This is not a suspended
Workflow graph. An Action does not call the model again or advance a Workflow.
New Chat turns retain native checkpoint messages and receive the last20 saved
card statuses/results as explicitly untrusted-result/read-only factual context;
this is not another history or memory engine.

Two PostgreSQL tables preserve conversation cards and control-request claims.
Action admission verifies current Skill/Application binding, saved choices,
revision and user/environment/conversation ownership. A claim commits before
business dispatch. Repeating its request ID cannot execute again; unconfirmed
effects remain UNKNOWN or EXECUTING and are never automatically retried.
Configured business success and interaction completion are distinct. Success
without completion, or a known business failure, keeps the card interactive.
The saved choice and result survive reload. This is platform request dedup,
not business exactly-once, compensation or cross-system transactions.

Authenticated endpoints:

- `GET /api/conversations/{conversationId}/cards`
- `POST /api/conversations/{conversationId}/cards/{cardId}/actions`, with only
  requestId, actionName, inputs and expectedRevision. No caller identity fields.

The Chat page reads saved cards, renders the registered Column/Text/ChoicePicker/
Button subset, supports Markdown and collapse, and makes completed cards read-only.
Unknown profiles do not execute. This is the existing bounded demo profile, not
a claim of arbitrary A2UI compatibility. Fresh compatible schema initialization
is explicit; request handlers never run DDL. No old-data migration is included.

Verification:65 focused Python tests passed with a disposable PostgreSQL17,
including native SDK use_skill→Ability→Application, direct Action, duplicate
control requests, refreshed store read, a subsequent checkpointed turn, the
attended streaming adapter, B-side authorization and existing three-node Workflow.
The model was scripted, not a paid provider. Frontend typecheck/build and a
separate synthetic browser select→submit→refresh→read-only check passed with no
console errors (desktop1280×900 and mobile390×844 screenshots). These are distinct
backend and UI acceptance evidence, not a combined live deployed environment.

## Managed component catalogs and shared PRT assets

COMPONENT catalogs now use the same management draft, validation, immutable
publication and rollback APIs as other assets. A catalog declares an installed
renderer protocol and its registered members. Registration cannot install code:
the currently implemented profile exposes Column, Text, ChoicePicker and Button.
The Application editor loads its published catalog; missing catalogs fail closed.
Application compilation and asset resolution check actual membership and protocol,
and catalog publication must preserve validity of serving dependents.

`deploy.assets` supplies structural Application validators rather than comparing
definitions to hardcoded demo JSON. Parameter data follows the configured schema
using jsonschema. Business operations still require an installed adapter.

`deploy/realchat` is a parallel loopback-only PRT composition with one PostgreSQL
asset namespace shared by M, Chat and Runtime. It does not migrate or replace old
databases. Seed installs prerequisite examples only; real UI publication and
subsequent Chat rendering must be verified independently before claiming the
end-to-end deployment works.

### Real PRT acceptance (2026-09-20)

The parallel composition was deployed from reviewed source `8144ac2` with the
Compose-only mount fix `61f62a6`. No previous database was migrated or deleted.
In an actual Chromium browser, the M editor created a component catalog with
Column/Text and published v1. An Application referencing ChoicePicker/Button
was rejected with `APPLICATION_COMPONENT_NOT_REGISTERED`. Publishing all four
members as catalog v2 allowed the same Application to publish as v3, with an
edited button label. These were UI save/validate/publish requests, not SQL edits.

A real DeepSeek v4 flash Chat turn invoked use_skill and render_application,
showing the edited M-authored label. Its Action reached the installed example
business adapter and persisted COMPLETED revision2. Reload retained the selected
option and read-only controls; PostgreSQL readback confirmed Application v3,
the new catalog, and one FINISHED Action request. Desktop1440x1000 and
mobile390x844 had no page errors or horizontal overflow. The unauthenticated
session check returned the expected401 before registration.

The adapter is a real in-process example backend, not an external production
business integration. Layout and bindings remain the bounded four-component
profile; this does not establish arbitrary A2UI or uploaded renderer support.
