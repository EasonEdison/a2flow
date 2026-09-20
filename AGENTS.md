# A2Flow contributor instructions

## Authoring migration release (2026-09-20)

The project owner explicitly authorized adapting their existing Skill/A2UI authoring and execution implementation. This scoped release supersedes the earlier independent-source restriction for those components only. Preserve the reference workflows while adapting interfaces to this project's React/Python stack; do not import credentials, private endpoints, business data, operational logs or unrelated infrastructure. Main-brain owns integration and delivery. UI/source completion and real runtime acceptance remain separate gates.

## Current bounded release (2026-09-16)

Main-brain has released AF12 common management publication, retained-version history and configuration rollback backend work. This supersedes the historical M-side pauses below only for explicitly assigned paths. Skill registry owns asset-store and management-api changes; main-brain alone reviews and integrates. No automatic successor work, model calls, database mutation or deployment follows from this source release. Keep candidate preparation non-publishing, immutable history, trusted authorization, PRT/ONLINE isolation, userId gray routing and atomic dependency-safe serving changes. Configuration rollback never compensates business operations. Current quota and execution cursor belong in the private coordinator records, not permanent architecture requirements.

## Project identity

- The product name is A2Flow, with the tagline "Agent Workflows with Interactive UI". The user approved this name on 2026-09-07, replacing SkillWeave.
- GitHub repository: https://github.com/EasonEdison/a2flow ; the github remote uses git@github.com:EasonEdison/a2flow.git. Server-local origin and all worktree paths stay unchanged.
- Existing skillweave_contracts Python imports, historical OpenSpec paths, schema identifiers and baseline IDs remain valid internal identifiers. Do not mechanically rename them or rewrite history as part of this branding change.
- Use A2Flow in new product-facing documentation. main-brain owns GitHub synchronization after server main integration; the current engine-first scope and paused domains remain unchanged.

## Latest priority: seeded browser MVP (2026-09-11)

User-approved AF-MVP-08 supersedes the engine-only pause below for three bounded workstreams: thin PostgreSQL asset import/read adapters (oss-skill-registry), Runtime host/integration, and minimal digital-employee UI. Defer the four M authoring platforms. Read `openspec/changes/skillweave-phase1/mvp-seeded-assets-release-08.md` for exclusive paths, Tool/environment boundaries and source/live/deployment gates. Do not wait for M editors or treat synthetic execution as the real MVP. Earlier design-only and pause defaults do not revoke this scoped release.

## Previous priority: Python engine first (2026-09-07)

Read `openspec/changes/skillweave-phase1/priority-engine-first.md` (SW-P1-ENGINE-FIRST-01). Only the Python Agent/Workflow Runtime domain continues; all six other domains pause new work and preserve owned changes. This latest user instruction supersedes earlier start-all and candidate-extension approvals without changing established behavior or deployment boundaries.

## Current phase authorization (2026-09-07)

- The user authorized phase 1 execution and main-brain-led coordination. Read `openspec/changes/skillweave-phase1/baseline.md` (SW-P1-20260907.2) and `plan.md` before working. These supersede conflicting old design-only instructions and proposed languages/semantics below.
- Delta PY-01: the user permits necessary system Python replacement on this server. Runtime owns compatibility/dependency checks, a recoverable change plan and post-change verification; main-brain coordinates one executor. Do not treat replacement permission as missing. This is not an instruction to replace immediately and does not authorize other package/service/deployment changes.
- Start baseline alignment, shared contract candidates and the isolated Runtime feasibility spike now. Dependent application implementation follows main-brain's recorded interface/design review, not another user-mediated kickoff.
- Own only your existing change directory and the explicitly reserved paths in the phase 1 plan. Shared files need an exclusive owner grant. main-brain owns this AGENTS.md and the phase 1 baseline/plan.
- Runtime is Python + Deep Agents SDK + LangGraph; PostgreSQL only. Respect the baseline's Tool, PRT/ONLINE userId gray, A2UI, retry/stop/restart and clean-room boundaries. Old drafts are not authority.
- User communication, task synchronization, review and acceptance belong to main-brain. Report baseline acknowledgement, stale-design corrections, owned diff and evidence to main-brain. Runtime readiness and unapproved deployment/product scope remain separate gates.

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
