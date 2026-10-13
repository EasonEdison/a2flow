# Public static deployment — 2026-10-13

The user explicitly authorized deployment after reviewing the structural redesign.
Deployed source: `4531f77b22c17b04dfa17b6c03ee2196dbd97a65`, clean and equal to main.
Local source verification matched all 148 management and 76 employee tracked frontend files
against that integrated source before packaging the previously validated builds.

## Artifacts and rollout

- Management archive SHA256: `f0a85bc6fb82253cf024046ec8b4b1ed912600f9a1f84f5d3f65648b7d98cb09`.
- Employee archive SHA256: `483bbea581952c6bee5528218196c2ea29e853efbce85cba65fa7122799dfbd5`.
- Both archives were verified after upload. An interrupted employee transfer was corrected
  before any service switch; the incomplete archive was never deployed.
- New static release directory: `releases/ui-ux-4531f77/{management,employee}`.
- Compose plan and rollback configurations: `.deploy-plans/ui-ux-4531f77/`.
- Only the M/B static bind-mount sources changed. Existing backend image IDs, configuration,
  Java classes and permissions were preserved. M/B containers were recreated to activate
  the mounts; Runtime, execution, scheduler and databases were not redeployed.
- Old static directories/configurations remain. Old hashed assets are retained in the new
  directories so already-open pages can still load their previous lazy chunks.
- Rollback uses the recorded `management-rollback.json` and `bside-rollback.json` with the
  same compose project and `up -d --no-deps --no-build --pull never` for the named service.

## Verification and boundary

Both public entry pages returned HTTP 200 with byte-identical build HTML. All 52 management
assets and 6 employee assets returned HTTP 200 and matched the release bytes, including lazy
chunks. M/B containers are running, restart count zero, OOM false, with expected static mounts
and unchanged backend image IDs. Runtime remains running.

Built-file scanning found no employee leaks. Two management generic-api-key matches were
reviewed as minified dependency expressions: `columnsKey/onColumnResize` and `metaKey/shiftKey`.
They are JavaScript variables, not credentials. Outgoing project-sensitive patterns were absent.

## Authenticated browser follow-up

The user signed in through Chrome; the in-app browser had a separate expired session.
Reused the existing Chrome login without reading credentials, transferring cookies,
resetting passwords or altering authentication. No database credential query was needed.

- Management: all seven real Skill rows rendered with metadata; the Workflow list showed
  its existing published-to-preview asset, inline metrics and labeled row. Its detail
  editor loaded all three nodes and configuration. No edits or publication were made.
- Employee: existing Chat messages and two existing cards rendered. Page reload preserved
  login, history, cards and the separate composer. The workflow catalog showed three
  available definitions. This account's My runs view had no records, so completed Flow
  history was not re-exercised in this follow-up; earlier public Flow acceptance remains
  the execution evidence, and local read-only history evidence is recorded separately.
- Both pages fit the actual 1678px viewport without horizontal overflow. Product console
  error counts were zero; unrelated Chrome extension errors were excluded explicitly.
- Captured final authenticated screenshots privately. No new Chat message, action submit,
  model execution, workflow start, data change or permission change occurred.

Authenticated presentation acceptance is complete within the above observed states.
This does not claim a new end-to-end temporary-interaction execution test.
