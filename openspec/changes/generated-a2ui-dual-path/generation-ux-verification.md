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
