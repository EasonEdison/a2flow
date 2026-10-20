# Execution guards and automated core probes

## Authorized behavior

Read-only abilities execute without a confirmation. WRITE/DESTRUCTIVE abilities require an explicit, host-authored confirmation of the actual ability and arguments, then continue the same Chat task or Workflow node. Ordinary missing-input submission and notification acknowledgement never grant this authority.

Java remains the final RPC admission boundary. Trusted service identity and resource ownership remain required. Approval receipts bind owner, environment, execution scope, tool call, current published source identity and the SHA-256 of exact transmitted argument bytes. A database uniqueness claim precedes business dispatch. Unknown transport outcomes are not retried; this is not business exactly-once.

The host reuses persisted temporary cards and native LangGraph interrupts. The model cannot construct an approval receipt. READ policy overrides legacy REQUEST_APPROVAL metadata as explicitly selected for this release; WRITE with invalid governance fails closed. No asset is relabelled to bypass the gate.

Package restoration retains registered immutable BUILD/VERSION selection; arbitrary URL/file restoration is rejected. ZIP processing has streaming resource limits and preserves the original workspace on validation failure. Core account/outbox/approval/package probes run without production credentials or model keys.

## Out of scope

Executor-loss detection, upgrade/backup tooling, benchmark dashboards, broad refactors and new business services remain separate proposals. Unconfirmed A2UI write bindings must fail closed until an exact host confirmation can be provided; ordinary UI inputs and rendering do not grant a write permit.
