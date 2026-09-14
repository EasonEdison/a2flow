# A2Flow Workflow Composer

This module contributes the `WORKFLOW` `ManagementFeature` to the shared
management Host. The Host injects the trusted context, `AssetReader`,
environment-bound `DraftRepository`, namespace and asset validator.

## AF10 executable subset

A publishable candidate is a bounded sequential graph with two through eight
nodes. Each node has exactly `nodeId` and `skillKey`; the first node becomes
`entryNodeId`. Every Skill reference must resolve as a published asset in the
trusted PRT or ONLINE environment. Validation delegates the normalized
definition to the asset bundle validator, which is the contract consumed by the
current Runtime loader.

`AI_ROUTING`, `BRANCH` and `PARALLEL` are planned product topologies.
Administrators may preserve such drafts, but validation returns
`UNSUPPORTED_WORKFLOW_TOPOLOGY` and publication preparation is rejected until
Runtime support is integrated. The Composer does not implement a scheduler.

`prepare_publication` returns a deterministic `PublicationPlan`; it does not
write a published asset, modify serving selection, connect to PostgreSQL, or
claim deployment/runtime readiness.
