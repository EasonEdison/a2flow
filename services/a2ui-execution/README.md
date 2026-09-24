# A2UI Execution

Python runtime for published A2UI Application Builds. It preserves the existing
`A2uiExecution.Describe/Activate/Act` contract and A2UI `v0.9.1` message model.

The runtime reads only authoritative `A2UI_APPLICATION` publication state. Load
and Action bindings call the published capability invoker by `actionCode`; the
inventory is identity-only and the capability publication remains authoritative.
There is no HTTP fallback, draft execution, cross-environment fallback, script
adapter, retry, or user-controlled trusted context.

## Host

Run `python -m a2flow_a2ui`. The process registers both `CapabilityExecution`
and `A2uiExecution` on one gRPC listener. It reuses the explicit capability host
configuration:

- `A2FLOW_CAPABILITY_DSN_FILE`, `A2FLOW_CAPABILITY_DATABASE`,
  `A2FLOW_CAPABILITY_ENVIRONMENT`
- `A2FLOW_CAPABILITY_TARGETS_FILE`, `A2FLOW_CAPABILITY_BIND`,
  `A2FLOW_CAPABILITY_RPC_MODE`
- for MTLS: `A2FLOW_CAPABILITY_KEY_FILE`, `A2FLOW_CAPABILITY_CERT_FILE`,
  `A2FLOW_CAPABILITY_CLIENT_CA_FILE`
- `A2FLOW_RUNTIME_ASSET_DSN_FILE`, `A2FLOW_RUNTIME_ASSET_DATABASE`,
  `A2FLOW_RUNTIME_ASSET_NAMESPACE` for the retained action identity index

`LOOPBACK_TEST` is accepted only on a loopback bind. Other listeners require
mutual TLS. The service performs read-only startup checks and never runs DDL.

## Boundaries

M-side editing, compiling and publication stay in Java. This package executes an
already published immutable Build and does not expose browser authentication.
The inbound caller must be the authenticated workflow runtime that constructs
the trusted card and `ExecutionContext`.
