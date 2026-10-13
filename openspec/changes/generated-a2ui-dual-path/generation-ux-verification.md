# A2UI generation progress and selection verification

Date: 2026-10-13. This follow-up adds generation progress, safe failure explanations,
natural-language tool selection and a bounded quality probe. It does not broaden
component authority, execute business Actions, retry generation or substitute layouts.

## Source and local checks

- Runtime emits preparing, generating, validating/loading, saving and a terminal
  generation milestone. Tool return, user confirmation and Workflow completion remain separate.
- Chat persists milestones with the matching tool call; Workflow uses the matching tool operation.
- UI displays the same stage history and cumulative time for live and restored records.
  Missing completion evidence is not rendered as success; failures use safe Chinese explanations.
- Ordinary business requests use the published layout. Explicit layout changes use
  generation without requiring the user to name a tool. Existing admission and binding checks remain.
- Runtime/B production import check, fatal Ruff, strict checks for new typed modules,
  TypeScript and Vite build passed. No unit tests were run, as requested.
- Local browser protocol fixtures passed at 1100x1000 and 390x844: live/history,
  failures including unknown outcomes, invalid-event isolation and parallel tool attribution.
  No console/page errors or horizontal overflow. These are fixture checks, not public SSE proof.
- Scoped outgoing files passed Gitleaks and private-domain scans.

## Actual published-contract and model probe

The probe reads published PRT definitions with read-only database connections. It
never activates a generated card, calls a business Action, changes an asset or publishes.
The explicit budget was four cases and at most four model attempts, with no retry.

| Case | Published-source/admission matrix | Actual model attempt | Generated admission | Elapsed |
| --- | --- | --- | --- | --- |
| People selector | PASS | 1 | PASS, layout changed | 4511 ms |
| Reading points | PASS, including relative List and declared read-only fields | 1 | PASS, layout changed | 3086 ms |
| Topic selector | PASS, including relative List and declared read-only fields | 1 | PASS, layout changed | 2144 ms |
| Manuscript editor | UNSUPPORTED SOURCE | 0 | Not attempted | Not applicable |

Negative candidates with wrong envelope/version, missing action placement or anchor,
and undeclared/out-of-scope data paths were rejected in applicable supported cases.
Three actual model attempts passed; this small sample is not a general reliability rate.
Generated candidates from this probe were not rendered, so it is not visual acceptance.

## Manuscript limitation

The published manuscript source contains registered PLATFORM_CUSTOM Markdown and
TextDownload components. The generation contract permits only A2UI_OFFICIAL types
while requiring original anchor types to remain. These requirements make this source
ineligible for layout generation. The Runtime now detects that conflict before creating
a model and reports A2UI_GENERATION_SOURCE_COMPONENT_UNSUPPORTED. The UI explains
that the card currently includes unsupported layout components. No component was
removed, allowed list expanded, asset modified or alternative layout auto-selected.
Stable published manuscript rendering remains governed by its existing contract.

## Delivery status

Source integration, deployment and public-page evidence are recorded separately below
when completed. Do not interpret the preceding fixture checks as deployed acceptance.

## Deployed revisions and public acceptance

- Initial source integration: `d7da6fc231ca7c6e5a271c7d59fe96853f0beac9`.
- Public testing exposed a missing event allow-list entry in the native Chat stream
  bridge. Fixed in `1d155eec70af87f6d3ab6acc4cb00c9068570b81`; older records
  without milestones are retained as missing evidence, never backfilled with invented stages.
- Chinese mappings for actual component-tree validation errors were completed in
  `a457241d2d3c243c2dcc477a78d03952d700f5d3`.
- Deployed Runtime image: `generation-ux-d7da6fc`; B image: `generation-ux-1d155ee`;
  employee static build: `generation-ux-a457241`. Unchanged services were not rebuilt.
  Builds ran locally; old images and deployment plans were retained for rollback.
- Final checks: both updated Python containers running with zero restarts, public
  employee route HTTP 200, and source refs synchronized to server origin and GitHub main.
  Frontend build passed with the existing chunk-size warning.

Authenticated public Chat checks used only fictitious demo people; no person was
selected and no business Action was submitted:

| Evidence | Observed result |
| --- | --- |
| Conversation 36 / message 98, ordinary display request | `render_application`; published people card |
| Conversation 36 / message 100, explicit natural-language layout request | Generated card displayed. Initial premature generation call was rejected by per-turn admission, then skill admission and generation succeeded. This predates the stream-bridge fix and has no saved milestones. |
| Conversation 37 / message 102, new layout sample after bridge fix | Actual live generation stage visible; generated tree rejected with `A2UI_GENERATION_TREE_INVALID`. Saved stages: preparing 0, generating 213, validating/loading 4135, failed 4155 ms. Refresh retained the failure and timings. |
| Conversation 38 / message 104, independent new layout sample | Generated people card displayed. Saved stages: preparing 0, generating 201, validating/loading 3294, saving 3392, completed 3403 ms. Refresh retained the card and all five milestones. |
| Final static release on existing failed history | Chinese text: “生成的界面未通过校验；未自动重试。” No re-execution was requested. |

The successful restored page had no captured console warnings or errors. The failed
sample is retained in the evidence; this release does not promise every generated
layout will pass. The independent successful request was a separate manual acceptance
sample, not application retry or fallback. All failure handling remained explicit.

Workflow progress in this batch was checked through implementation review and browser
protocol fixtures, including parallel operation attribution. A new public Workflow run
was not performed; earlier Workflow acceptance is not counted as evidence for this batch.

## Follow-up outcome

Generation progress, persisted failure explanations and natural-language layout
selection are delivered within the approved scope. The bounded quality regression is
complete with three supported cases and the explicit manuscript limitation above.
This follow-up does not change the earlier release's gates or assert universal generated
layout readiness. Public model variability, manuscript component support and Workflow
live validation retain the precise evidence boundaries described here.
