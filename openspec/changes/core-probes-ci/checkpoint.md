# Core probes CI checkpoint

Owner: `portfolio_onboarding`, branch `codex/main-brain-v2/core-probes-ci`,
worktree `/home/admin/OpenSource/repos/.parallel/main-brain-v2/core-probes-ci`.

Original scope was committed/pushed through `d91ff27`; parent owns integration and
deployment. Main baseline remains `5c907ee`. Four-probe source and local command
validation are recorded in regression.

Approved extension in progress:

- Actual Python executor + isolated PostgreSQL probe now passed 70 checks against
  root `cb5adb3`; concurrent admission 1/8, fresh-process replay 0 dispatch,
  unknown-result retry 0 dispatch. Existing execution-reader role stays readonly
  by default; dedicated consumption connection uses only INSERT/SELECT grants.
- Runner requires all six Python probes, including A2UI preflight, plus both Java
  probes. CI Python probe step deadline is 21 minutes, job 40 minutes.

- Add Chat `scripts/verify_chat_write_approval.py` (security owner) and Workflow
  `scripts/verify_workflow_write_approval.py` (architecture owner), both synthetic,
  no network/model/PG; required final JSON probe name, result PASS, positive checks.
- Add model-requirements lock as a thin layer to the existing probe Dockerfile;
  preserve runtime/gRPC pins, do not build the full self-host application image.
- Java approval now runs its real PostgreSQL path in a public JRE 17 container,
  sharing only a disposable PG namespace. First new runner execution passed 41
  checks on approval `da2ff11f` and package 107 checks on `9d84cbc6`, with cleanup.
- Parent found an existing A2UI write-action compatibility gap. Architecture and
  security are updating their probes and contracts. Wait for the final committed
  joint candidate, then run the full expanded gate once; do not replay every
  intermediate revision.

Local source export only (no Git):
`/tmp/colima-a2flow-selfhost/core-probes-ci`. Maven target under that export contains
the independently compiled 609-file combined Java build; dependencies are copied
into that target, not symlinked to another owner's output. Docker context
`colima-a2flow-selfhost`; default context is unchanged. Prior self-host containers
were explicitly stopped at parent's request; do not restart them.

No probe containers or private DSN directories are intentionally retained.
Synthetic reports are in `/tmp/a2flow-core-probes-*-results`; they are not secrets
or deployment evidence. Remote GitHub Actions has not run.
