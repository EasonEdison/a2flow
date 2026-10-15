# Employee workspace UI refresh

## Result

The employee workspace now uses one navigation, typography, form and list system across Chat, workflow catalogs/history/detail, schedules, notifications, personal memory and login. Run history displays a workflow name, execution requirement, request creation time, status and details action. Search and status filters operate together. Technical identifiers remain available in a disclosure rather than serving as the primary title.

The B API exposes title and requirement from the runtime view it already reads; this introduces no additional runtime calls. Dates are explicitly request creation times in the browser's local time, not invented execution durations. Current authorized catalog names are preferred; an unavailable definition is clearly labeled.

Schedules present workflow, execution requirements, rule/timezone, next/last trigger and actions. Creation is explicitly expanded above the list. Existing scheduling, editing, enable/disable and execution contracts remain unchanged. Completed final node results open by default while retaining user-controlled disclosure. Management navigation uses the existing session-expiry signal to show either login or logout.

## Validation and release

- Implementation: `97a399c`; integrated deployment source: `a0c9ff5`.
- Employee and management TypeScript/Vite builds pass. Source snapshots match all 80 employee and 151 management tracked build files. The employee build retains its existing large-chunk warning.
- Nine exact outgoing source files passed secret/company-data scanning and diff checks. Python syntax was checked with the actual Python 3.11 image; deployed module inspection confirms the metadata additions.
- Local read-only UI previews checked desktop 1536×1024 and narrow 390×843 layouts, history filters, schedule create/edit cancellation and record disclosure, notifications, memory, login and Chat. Local preview data are synthetic, all mutation routes are rejected; these checks do not prove real execution.
- Deployed B source/static and management static only, retaining existing images/configuration and rollback plans. Both containers run without restart or OOM. All 64 public static files match build hashes.
- Authenticated management browser shows no login link and one logout action. Public employee session expired on refresh; authenticated employee history/detail acceptance remains pending normal login.

No new workflow execution or scheduled task was created for this visual change. No schedule, notification, memory, asset or authentication policy was changed during acceptance. Unit tests were waived by the user; no new unit suite was run.
