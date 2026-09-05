# Workstreams

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

## First design slice

Each task independently proposes an OpenSpec change in its own directory. Cross-domain interfaces remain proposed until coordinator review. Common release semantics must not be reimplemented in each registry. The Runtime design separates single-Agent execution, Workflow scheduling and generic presentation execution internally. The digital-employee task owns the web host and business adaptation, while keeping generic renderer code reusable.

## Delivery waves

1. Parallel bounded proposals and consumer contract requirements.
2. main-brain reconciles interfaces and records language, protocol and publication decisions.
3. Shared contracts and PostgreSQL foundations, then parallel module implementation against approved contracts.
4. End-to-end vertical slice and multi-instance recovery verification.

The initial slice should be small enough to demonstrate registration, publication, execution, user intervention, recovery and result rendering. Advanced graph features and broad editor features require explicit later scope.

## Git topology

All repositories and linked worktrees live on the server. Every worker branch integrates into the same main branch through its own integration checkout. The initial origin is a server-local bare repository. External Git hosting and off-host backup are not configured yet; server-local pushes are not public publication or off-host backup.
