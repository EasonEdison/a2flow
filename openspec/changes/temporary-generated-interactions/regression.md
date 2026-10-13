# Regression evidence

Baseline: 665893d3338f978c4f3777ff8ac9283c4a099b89. Evidence date: 2026-10-13.

## Source and isolated integration

- Integrated Python imports and 12-component catalog admission passed. Scoped static checks,
  Python 3.11 parsing, TypeScript and Vite production build passed. No unit tests per user instruction.
- Real PostgreSQL and native LangGraph probe passed 29 checks at ee188fc:
  persisted interrupt, new graph/connection restoration, atomic submitted-card/outbox,
  exactly one submission observation and outbox command on replay, correct-node resume,
  structured SUBMITTED values reaching the next node, no second generation or resume execution,
  display-only completion without interrupt, and stopped-run action rejection/read-only view.
  This probe used synthetic Skill data and a deterministic candidate; no model or business RPC.
- Real PostgreSQL B-side continuation claim: two concurrent callers produce one dispatch owner
  and one message pair; repeated card returns the same IDs; another owner is rejected;
  completed assistant content is not overwritten. Nine connections checked isolated schema scope.
- Actual frontend with controlled API fixture: desktop/mobile layout; local draft reload and
  account isolation; submit clears draft; history polling receives continuation without a browser
  messages POST; completed card stays read-only after refresh. A confirmed invalid-field response
  leaves the form editable and a subsequent explicit corrected submission succeeds.
- Seven controlled real model calls used only synthetic data: selection+notes passed (4.747s);
  one display candidate failed root restriction, one verification wrapper failed file permissions,
  one failed candidate reception, one diagnosed components as an object instead of an array;
  after admitting the existing Card container as a root and supplying explicit candidate JSONSchema,
  display-only comparison passed (3.572s). A separate synthetic selection+notes probe passed (3.739s). Failures were not hidden or automatically retried.
- The root/container restriction, candidate-shape explanation, and Flow display serialization
  compatibility were repaired before deployment. No business data writes were performed.

## Deployment and public acceptance

Runtime source: `661a7a73c24f1335953aa3afff57bf7e4072c46e`, integrated to server and GitHub main.
Runtime and B images: `temporary-interactions-661a7a7`; frontend release uses the same
revision name (latest frontend change e6a1e56). Both containers running, zero restarts,
no OOM at final inspection. Previous images/plans/static releases are retained.

A chained delta-image build hit the overlay layer limit before service replacement.
The final images were rebuilt from the retained pre-task baseline images, with all
changed packages copied and import checks passed before deployment. No service was
switched by the failed build attempt.

Authenticated public checks used fictitious activities and no external business API:

| Conversation | Actual result |
| --- | --- |
| 39 | Candidate validation failed; older error allow-list hid the specific code. No card; exact cause cannot be reconstructed. |
| 40 | Explicit TEMPORARY_INTERACTION_INPUT_BINDING_INVALID; no card. |
| 41 | Required activity-name form generated. Empty submit rejected but remained editable; filled draft survived reload; accepted submit continued Agent with the actual activity name; another reload retained completed read-only card and answer. |
| 42 | Choice+notes candidate failed field_control_set: two declared fields, one input control. Retained as failed evidence. |
| 43, final deployed revision | One tool generated comparison, single-choice control and notes. Submitted B hiking and Saturday-morning/easy-pace note. Agent used both saved fields in its answer. Reload restored selected B, note, disabled controls and completed answer. |

| 44, final deployed revision | Pure comparison display generated in one tool call; task completed without input/submit controls or a waiting state. Reload retained the same card and answer; database DISPLAY_ONLY, no action receipt or continuation pair. |

The 42 failure led to a complete validated protocol example and explicit input-field /
control / submit-context set checks in the generation prompt. The example is a protocol
contract, not a selected business template. The service does not repair or retry candidates.
43 is a separate manual acceptance request after that source change.

Read-only database verification: 41 and 43 each have one COMPLETED temporary card,
one FINISHED action receipt and one server-created continuation message pair. Initial
assistant messages use only generate_interaction, with no Skill/RPC binding. Conversation
41 messages are 109/110 then 111/112; 43 messages are 115/116 then 117/118. Saved results
are SUBMITTED inputs, not business-success claims. The final refreshed browser had no
captured console warnings/errors.

Public Workflow with real-model generation has not yet been established by this evidence.
The 29-check isolated Flow probe above is not public UI/model acceptance. Old published
Application/Workflow tests are not reused as evidence of the new temporary path.


## Additional Flow real-model integration

At deployed source/image 661a7a7, an isolated real PostgreSQL/native LangGraph probe
passed 30 checks. DeepSeek generated one interactive candidate (six components,
one required comments field) with exactly one model call and no retry. The probe
persisted the wait, reopened the checkpoint, accepted a submission through the shared
path, committed one outbox command, resumed the correct node and delivered SUBMITTED
values downstream before SUCCEEDED. Replay did not regenerate or reexecute the node.
The stop branch reused that candidate; display-only branch still used a deterministic
candidate. A synthetic Skill reader drove the graph. This does not prove the public UI
or host model's autonomous tool selection in Flow.

The existing public reading demo was inspected read-only: all three Skills require
execute_ability and render_application plus business save/confirmation actions. It was
not modified or executed for this new path. A temporary input card cannot substitute
for those business completion conditions, so public Flow acceptance remains open.

All three task-owned isolated probe schemas were removed after checking their exact
scope. The final real-model schema contained the expected 15 synthetic tables; namespace
read-back was zero after cleanup. No production assets or business records were changed
by the Flow probes.
