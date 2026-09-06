# Phase 1 execution plan

Baseline: SW-P1-20260907.2 (`baseline.md` in this change). Coordinator: main-brain. Status: AUTHORIZED / runtime NO READY. Delta PY-01 permits necessary system Python replacement, with Runtime as the single executor coordinated by main-brain.

Engineering supplement: `engineering-decisions.md` ENG-01 selects Python for M-backend domain modules, without requiring independent resident services or changing frontend/BFF scope. Exact packaging and dependent implementation remain review-gated.

## First milestone

Converge current contracts and demonstrate the smallest framework-backed execution spine: Deep Agents -> use_skill -> ability Tool -> display/interactive Application -> valid node-bound continuation -> final result, with PostgreSQL persistence and independent parallel progression. This is not the entire product release.

## Delivery gates

1. ALIGN: fetch/merge baseline in the task's existing server worktree; identify stale decisions and update the task's own proposal/design. Return baseline ID, conflicts removed, owned paths, first executable slice and dependencies to main-brain. Send acknowledgement early while continuing bounded work.
2. CONTRACT: platform-contracts owns shared candidate schemas. Other owners supply requirements/examples, not competing shared schemas. main-brain reviews actual contracts and design deltas, then releases dependent implementation against a named revision. No need for the user to mediate normal engineering.
3. PROVE: Runtime may immediately author an isolated framework feasibility spike after alignment, before production interface freeze. Other tasks may author independent contract examples/validation fixtures and revised module plans. Mark experimental adapters as provisional; do not silently freeze shared APIs.
4. IMPLEMENT: once main-brain reviews alignment and names the approved interface revision, implement the assigned small module slice. Cross-domain source changes stay with the owning task. Do not implement the entire platform before first integration feedback.
5. ACCEPT: source commits and checks are not runtime readiness. Record exact command/environment/output and unverified gates in regression/readiness. Each task pushes its worker branch and integrates through its exclusive integration worktree into server origin/main. main-brain reviews actual diffs/evidence and consolidates the milestone.

## Task assignments and exclusive paths

Every worker retains exclusive ownership of `openspec/changes/<actual-task-title>/`. Only main-brain edits this change and repository AGENTS.md. The following source paths are reserved; reservation alone does not bypass gates 1-4.

| Task | First deliverable | Reserved source paths | Dependencies / review |
| --- | --- | --- | --- |
| oss-platform-contracts | Shared contract candidate: trusted context, environment-local asset resolution/publication, version comparison, control request dedupe, execution events and interaction/result references. Provide minimal independent schemas/examples and contract checks, not a generic governance platform. Propose common packaging and backend language layout jointly with Runtime. | packages/contracts/ | Collect six consumer requirements. Root manifests/configuration remain coordinator-owned until an explicit exclusive transfer. |
| oss-skill-registry | Correct Skill package/catalog/use_skill boundary; candidate authoring/read contracts, environment separation and ordinary-user denial cases. Prepare one independently authored instruction Skill reusable unchanged in chat and Workflow. | services/skill-registry/ | Common resolver/publication and Runtime use_skill contract. No separate native-directory activation or fixed Skill graph. |
| oss-capability-registry | Ability metadata, typed invocation port, configured success interpretation and authorization boundary; synthetic read/write-call fixtures without real external writes. | services/capability-registry/ | Shared resolver/context; Runtime executes through Tool; called backend owns business idempotency. |
| oss-a2ui-composer | Component/Application publication contracts, interaction modes, Action success/completion policy; minimal display/selection Application fixtures and M validation plan. | services/a2ui-registry/, packages/a2ui-contract-fixtures/ | Shared contract owner; Runtime presentation execution; digital employee owns frontend host. Do not implement three different success evaluators. |
| oss-workflow-composer | Published sequence/condition/parallel graph candidate and validation examples, independent AI/user-choice routing and joins; coordinate executable graph feasibility with Runtime. | services/workflow-registry/ | Skill references, shared graph contract, Runtime graph mapping. No per-Skill graph generation or Skill output adaptation. |
| oss-agent-workflow-runtime | Python Deep Agents/LangGraph feasibility spike, pinned API/license research, Tool-only entry proof, display/interrupt/resume, Pg feasibility and parallel A-waits/B1->B2 proof. Propose smallest generic execution ports. | services/runtime/, experiments/runtime-phase1/ | Contracts owner, Skill/ability/Application ports. No second custom scheduler. Escalate actual SDK behavior conflicts with a reproducer. |
| oss-digital-employee | Product adapter/event consumption plan and bounded UI state examples: sidebar start, node-bound cards/input, stale reset prompt, stopped read-only history. Evaluate cheap personal-memory controls; report cost rather than promising a KB platform. | apps/digital-employee/, packages/a2ui-host/ | Consume Runtime/shared contracts. Digital employee owns reusable browser host, not Runtime business logic. Protected UX changes go to main-brain. |

## First milestone evidence matrix

| Gate | Required evidence | Owner |
| --- | --- | --- |
| Baseline alignment | Seven explicit baseline acknowledgements, stale-design diffs and scoped plans reviewed by main-brain | All / main-brain |
| Environment and identity | PRT current; ONLINE stable/gray both ONLINE; no third serving version; unauthorized identity/environment override rejected; all asset types covered | Contracts + registries |
| Skill reuse | Same instruction Skill enters through use_skill in chat and Workflow without extra routing fields | Skill + Runtime |
| Presentation lifecycle | DISPLAY_ONLY continues; INTERACTIVE waits; valid node-scoped Action/configured success governs completion; Finalizer cannot bypass interaction | A2UI + Runtime + digital employee |
| Version/stop admission | Stale version blocks before a new business call; stopped card cannot resume; fresh restart inherits no old run state | Runtime + contracts |
| Parallel progression | A waiting while B1 then B2 progress; join waits for A; allowed failure/skip and required failure retain their semantics | Runtime + Workflow |
| Persistence/control | Pg-backed wait/reopen/resume and competing control requests from two processes; report unsupported general recovery rather than claiming it | Runtime + contracts |
| Resource and provenance | Exact versions/public APIs/license notes; no company artifacts; no unrelated host mutation or public exposure | All |

## Execution constraints

- Work only on the assigned server worktree/branch. Before edits and before delivery, inspect status, fetch origin, merge origin/main. Never rebase, force-push, stash/reset/clean or touch another worker's changes/checkpoint.
- Retain each task's own checkpoint. Report baseline/commit/owned diff/evidence to main-brain; root does not read worker checkpoints. Update own tasks/regression/readiness separately.
- Shared machine is small and hosts unrelated services. No concurrent bulk dependency installation, container startup or full builds. Runtime owns the first bounded dependency feasibility check; coordinate any ephemeral PostgreSQL validation with main-brain before starting it. System Python replacement is user-authorized under delta PY-01: first check system-tool/service dependencies, identify the exact change and recovery path, then verify compatibility after any change. Only Runtime may execute this coordinated host change; other workers must not race it. Other system package replacement and background production services remain outside this grant.
- Use public docs and project-owned synthetic fixtures. No company repository reading/copying in these tasks. Do not copy private control-workspace documents wholesale into Git.
- No broad unit-test campaign required. Use focused schema/contract checks and explicitly requested integration/spike evidence; report missing runtime prerequisites honestly.
- Shared files, dependency pins and protocol versions are one-owner decisions reviewed by main-brain. Other tasks submit a requirement/diff suggestion without writing the owner's files.
- Integrate approved-scope worker delivery into server origin/main; no public deployment or unreviewed GitHub publication. Runtime remains NO READY until the required evidence actually exists.
