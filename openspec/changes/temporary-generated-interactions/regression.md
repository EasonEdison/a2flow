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

## Automatic continuation presentation correction

Follow-up source `8f0600ccce3507c6c2b5e84cc7a9f809290d54f0` deployed only to B.
Runtime and frontend remain at their previous deployed revisions. Card submission was
already dispatching the next model turn automatically; the defect was exposing the
server-owned trigger input as a user-authored chat bubble. The conversation display API
now excludes only user records with ref_kind=temporary_interaction. Model input/turn
identity, idempotency and assistant results are retained. Old conversation 43 showed
its answer without the internal trigger after reloading the history.

New public conversation 45: generated a required activity-name form; entered a fictitious
name and clicked Submit once, with no further chat message. Assistant 124 automatically
completed an introduction using the saved name. Database has one FINISHED action receipt;
121 is the real user request, 123 is the internal continuation input omitted from display,
122/124 are the initial/continuing assistant messages. No external business API was used.

Python parsing, diff-check and sensitive/company-material scans passed. Ruff reports
only an existing unused json import in app.py, reproduced unchanged on the baseline;
no unit tests were run, as requested. The B restart briefly returned 502 during startup;
startup completion was followed by HTTP 200 and running/restart=0/OOM=false.

After refresh, conversation 45 retained the completed form and automatic answer without
the internal user bubble. Browser screenshot captured the form directly followed by
the assistant response.


## Public Workflow acceptance, 2026-10-13

Normal management UI created and published two synthetic Skills and one linear Flow;
no prebuilt Application or business Ability was added, and the existing reading demo
was not modified. Workflow publication build `build_2ffdb3412485412fab248030bc1f2202`
materialized `wf_78a28b7295a845f98357bf63b54cdcdd` with both node prompts, a summary
prompt and exactly the two Skill dependencies. Runtime read-back version was
`java-123a29d076a6ae337b57e2cc42e5df6a5cfe74f31f8c6f4ff59155dfe647b449`.

The actual public run was started exactly once:

- Control ID: `be555892919f4d139f9b682a04c80357`.
- Run ID: `b84ee95ffefb42bf9bb9f72703005afb`.
- Nodes: `SKILL_01` (collect), `SKILL_02` (receipt), `workflow-summary`.
- One real generated `TEMPORARY` / `a2flow.temporary.v1` card waited for a required
  comments value. Waiting persisted while the page was reloaded and the same run reopened.
- The browser submitted one synthetic sentence, with no extra message or resume click.
  The original node completed, the second model node reproduced the exact saved sentence,
  and the summary said both nodes were complete. The run reached `SUCCEEDED`.
- The completed card contained the saved text and disabled controls. Reloading and reopening
  the same run preserved all three completed nodes, the read-only card and the downstream answer.

Backend evidence: one card, one FINISHED submission receipt, one successful ACTION
observation carrying `{status: SUBMITTED, values: ...}`, and one completed resume outbox
command targeting `SKILL_01`. The interaction had resume_started and resume_consumed
set true. The action did not declare business success. MODEL operation counts were
SKILL_01=4, SKILL_02=2 and summary=1 (7 total); the summary used no tool. There was one
RENDERED observation. Interrupt/replay history is retained, not counted as a fresh card.

Acceptance exposed and corrected these real integration gaps before completing the run:

1. Management previously checked a frozen Workflow snapshot without writing runtime
   material. It now uses the existing transactional asset publisher and environment pointer.
2. Optional prompt support required the shared validator on both Runtime and B. Updating
   only Runtime initially caused the employee catalog to reject the new bundle; deploying
   the matching B validator restored the catalog. The scheduler does not parse asset bundles.
3. The frontend run-view parser and adapter still required legacy card fields. They now
   validate temporary snapshots through the shared parser, preserve card identities for
   the existing card renderer, and retain strict legacy validation. The same waiting run
   was recovered after the frontend fix; no new run or model retry was used.

JDK 17 package build, Python import/SDK checks, actual returned view/cards parser probes,
TypeScript/Vite build, diff checks and secret/company-material scans passed. No unit tests
were run under the user's instruction. Browser logs retained the earlier catalog failure;
no new warning/error appeared during the corrected submit/completion/refresh sequence.
The three relevant containers were running with restart count zero and OOM false.

This closes the previously open public Workflow gate. The earlier isolated probes remain
separate evidence and are not substituted for this public run.

Final read-only comparison after the public refresh found identical operation IDs/statuses,
node outputs, card/result, observations, submit receipt, interaction flags and outbox rows.
MODEL remained 7, successful ACTION remained 1, and completed resume outbox remained 1.
Refresh did not trigger another execution.
