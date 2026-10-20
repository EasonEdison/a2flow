# Capability write confirmation

## User decision
READ executes without confirmation, including existing REQUEST_APPROVAL metadata. WRITE and DESTRUCTIVE require explicit confirmation and resume automatically. Parameter collection is not approval. Unknown/missing governance is rejected rather than defaulted. Existing six PRT content WRITE capabilities retain their published policy; they acquire a real confirmation path rather than being relabelled READ/AUTO.

## Boundary
The trusted Runtime creates and persists a confirmation for an immutable action/source and frozen UTF-8 argument JSON. Only after same-user submission does it send an approval receipt outside model arguments over the existing trusted internal gRPC channel. The receipt binds user, environment, run, tool call, action, source ID/digest, side effect, policy, confirmation ID, and SHA-256 of the exact arguments_json bytes. JSON is serialized once and reused; Java must not reserialize it for hashing.

Java validates plan and arguments, then validates the receipt and commits a unique durable consumption immediately before the business RPC. Duplicate, changed arguments/source, invalid policy and absent confirmation cause zero RPCs. READ ignores receipts and does not consume them. A2UI and management dry-run share the same final guard and cannot use admin/demo booleans. Their write calls without a receipt fail explicitly.

The receipt is a trusted-host attestation backed by Runtime persisted confirmation, not a browser/model token. Transport trust does not authorize an action by itself. Runtime must never inject receipts from model parameters. The Java store is not a second approval UI/platform.

## Crash semantics
Consumption and remote business execution cannot be atomic. Once consumption commits, a crash/timeout may leave the business outcome unknown; the receipt is not reusable and no business retry is introduced. A database failure prevents dispatch. No exactly-once business execution claim is made. Explicit V003 SQL is required before rollout; host startup never creates tables.

## Validation
An isolated loopback fake RPC probe checks READ, all metadata failures, unapproved writes, forged model values, exact approved execution, tampering and duplicate consumption. A dedicated loopback PostgreSQL probe checks persistence, concurrent claims and rollback without touching business tables. Parent owns integration, deployment and public confirmation/resume acceptance.
