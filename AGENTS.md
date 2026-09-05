# Platform contributor instructions

## Source and architecture

- Write new code and specifications independently from sanitized requirements and public documentation. Do not read or copy proprietary projects, schemas, tests, fixtures or credentials into this repository.
- PostgreSQL only, including development and integration tests. No MySQL or SQLite profiles or automatic database fallback.
- The digital employee depends on generic execution contracts. Runtime core must not import business models, presentation copy or scenario-specific branches.
- M composition, generic presentation execution and B frontend rendering have separate responsibilities.
- Languages, protocol versions and shared contract details are proposals until reviewed by main-brain. Domain owners must expose dependencies rather than independently freeze incompatible interfaces.

## Server worktrees and delivery

- All Git operations and repository edits happen in the assigned server worktree. The local task cwd is only a coordination surface.
- Shared integration target is `origin/main`. Every task has a unique `codex/<task-name>/design` branch and linked worktree.
- Before editing, verify pwd, branch, status, and worktree list; fetch origin and merge origin/main. Never stash/reset/clean other work or force-push.
- Current authorization is a design slice: write only `openspec/changes/<task-name>/`. Do not edit shared files, implement application code, install dependencies, change services or deploy.
- Begin with your own `checkpoint-<actual-task-title>.md`. Never read or modify another task checkpoint. Root private main-brain checkpoint belongs to the coordinator.
- Deliver proposal.md, design.md, tasks.md, regression.md, readiness.md and one capability spec under specs/. State PROPOSED for design and NO READY for runtime; all implementation checkboxes remain unchecked.
- Tests in regression.md are planned scenarios until executed. No invented build/test/runtime evidence.
- Keep the first design bounded: scope, inputs/outputs, contract dependencies, negative cases, acceptance gates, and explicit decisions for main-brain. Do not implement the full platform in one change.
- Before commit, inspect the exact diff and run git diff --check; inspect for secrets and proprietary details. Commit only owned change files using a clearly identified automation author if no identity is configured.
- Push the worker branch. Create a separate integration worktree on a unique codex/integrate/<task-name> branch from fresh origin/main, merge the worker, verify scope and whitespace, then push HEAD:main. On a non-fast-forward rejection, fetch and merge the new origin/main, recheck, and retry without force-push. Real conflicts or failed checks are reported with evidence.
- Integrating a proposed design does not approve that design or authorize implementation. Mark source delivery separately from runtime readiness.
- Report change directory, worker SHA, integrated main SHA, verification performed, and a concise list of cross-domain decisions. Do not change titles after creating checkpoints.
