# Execution guards and automated core probes

## Authorized behavior

Read-only abilities execute without a confirmation. WRITE/DESTRUCTIVE abilities require an explicit, host-authored confirmation of the actual ability and arguments, then continue the same Chat task or Workflow node. Ordinary missing-input submission and notification acknowledgement never grant this authority.

The deployed Python CapabilityExecutor is the final business RPC admission boundary; the Java management execution entry enforces the same policy. Both use the same durable consumption table. Trusted service identity and resource ownership remain required. Approval receipts bind owner, environment, execution scope, tool call, current published source identity and the SHA-256 of exact transmitted argument bytes. A database uniqueness claim precedes business dispatch. Unknown transport outcomes are not retried; this is not business exactly-once.

The host reuses persisted temporary cards and native LangGraph interrupts. The model cannot construct an approval receipt. READ policy overrides legacy REQUEST_APPROVAL metadata as explicitly selected for this release; WRITE with invalid governance fails closed. No asset is relabelled to bypass the gate.

Package restoration retains registered immutable BUILD/VERSION selection; arbitrary URL/file restoration is rejected. ZIP processing has streaming resource limits and preserves the original workspace on validation failure. Core account/outbox/approval/package probes run without production credentials or model keys.

## Out of scope

Executor-loss detection, upgrade/backup tooling, benchmark dashboards, broad refactors and new business services remain separate proposals. A2UI Action uses read-only PrepareAct to map the actual current published capability and arguments, then a host-authored confirmation on the same card. Confirmed Act re-resolves and remaps; a changed source or argument digest rejects before dispatch. Ordinary UI inputs and rendering do not grant a write permit. Automatic WRITE Load bindings remain rejected. Dynamic time-derived arguments that change between preview and confirmation are also rejected rather than silently substituted.

## Runtime and storage boundaries

The execution publication reader retains its default read-only connections. Only the dedicated approval connection disables that transaction default, and its role receives INSERT/SELECT on capability_approval_consumption, never UPDATE/DELETE or broad database write permissions. Self-host bootstrap applies the explicit V003 migration and grant; existing deployments apply both before rolling the execution hosts. The mTLS caller is trusted to have persisted the user confirmation. The execution host validates bindings and consumes a one-use receipt; it does not independently authenticate the browser Cookie.
