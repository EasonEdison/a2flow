# Workstreams

[Documentation / 文档目录](README.md) · [Architecture](architecture.en.md) · [平台架构](architecture.zh-CN.md)

## Current stage

Python Agent/Workflow engine work is the current priority. Other domains preserve their existing modules and proposals while implementation is paused; reviewed dependencies may be consumed by the engine. See the [engine-first decision](../openspec/changes/skillweave-phase1/priority-engine-first.md). The wave list below describes the overall delivery structure, not simultaneous active work or completed product capabilities.

main-brain coordinates architecture, contract review, dependencies, scope and integration acceptance. Seven domain tasks have distinct change directories and server worktrees.

| Task | Owns | Dependencies to propose |
| --- | --- | --- |
| oss-platform-contracts | Common asset identity, revision, authorization, immutable release and contract conventions | Collect consumer needs; own shared publication semantics |
| oss-skill-registry | M Skill registration, metadata, versioned package references and validation | Common asset/release contracts; capability and workflow references |
| oss-capability-registry | M callable capability registration and typed inputs/outputs | Common asset/release contracts; execution port consumed by Runtime |
| oss-a2ui-composer | M component catalog and presentation composition | Public A2UI contract, capability references, published artifact contract |
| oss-workflow-composer | M Skill Workflow composition and graph validation | Skill revision references, published graph contract consumed by Runtime |
| oss-agent-workflow-runtime | B generic Agent execution and durable Workflow orchestration | Published assets and generic execution/capability ports |
| oss-digital-employee | B product frontend/backend, renderer integration and business adapters | Generic Runtime, A2UI presentation and action contracts |

## Initial design method

Each task independently proposes an OpenSpec change in its own directory. Cross-domain interfaces remain proposed until coordinator review. Common release semantics must not be reimplemented in each registry. The Runtime design separates single-Agent execution, Workflow scheduling and generic presentation execution internally. The digital-employee task owns the web host and business adaptation, while keeping generic renderer code reusable.

## Delivery waves

1. Parallel bounded proposals and consumer contract requirements.
2. main-brain reconciles interfaces and records language, protocol and publication decisions.
3. Shared contracts and PostgreSQL foundations, then parallel module implementation against approved contracts.
4. End-to-end vertical slice and multi-instance recovery verification.

The target vertical slice connects registration, publication, execution, user intervention, explicit checkpoint/interaction continuation and result rendering. Generic internal Skill recovery is outside first-version scope. Advanced graph features and broad editor features require explicit later scope.

## Git topology

All repositories and linked worktrees live on the server. Every worker branch integrates into the same main branch through its own integration checkout. The origin remote is a server-local bare repository. The separate github remote points to [EasonEdison/a2flow](https://github.com/EasonEdison/a2flow); the first main-history synchronization completed on 2026-09-07. main-brain reviews outgoing changes, pushes integrated main to GitHub and verifies matching SHAs. A server-local push alone is not GitHub synchronization, product deployment or runtime acceptance.
