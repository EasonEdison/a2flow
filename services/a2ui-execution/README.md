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

## Generic list projection and composer effects

`ARRAY_OBJECT_TO_OPTIONS` projects a capability result array to official A2UI
ChoicePicker options. `valuePath` must resolve to a unique, non-empty string.
Each `labelColumns` entry reads a scalar or an array of scalars; arrays are
joined with `、`, columns are joined with `labelSeparator`, and object values,
missing paths, duplicate values, more than 100 rows, or more than 20 columns
fail the presentation. The transform never supplies business identity or data.

```json
{
  "type": "ARRAY_OBJECT_TO_OPTIONS",
  "valuePath": "/personId",
  "labelColumns": [
    {"label": "姓名", "sourcePath": "/name"},
    {"label": "电话", "sourcePath": "/phone"},
    {"label": "爱好", "sourcePath": "/hobbies"}
  ],
  "labelSeparator": "｜"
}
```

An ActionBinding may declare one `composerDraftEffect` with type
`COMPOSER_DRAFT`, mode `APPEND`, source `CAPABILITY_DATA`, an `itemsPath`, and
ordered scalar `columns`. It is emitted only for a successful business outcome
and contains text derived from the capability response. The effect is scoped to
the Action HTTP response and its request ID: it is not stored in the card,
returned by card GET, sent as a chat message, or interpreted as workflow
completion. Missing or non-scalar column values, an empty or oversized result,
or text longer than 4000 characters fail the presentation instead of emitting
partial text.

```json
{
  "type": "COMPOSER_DRAFT",
  "mode": "APPEND",
  "source": "CAPABILITY_DATA",
  "itemsPath": "/items",
  "columns": [
    {"label": "姓名", "sourcePath": "/name"},
    {"label": "电话", "sourcePath": "/phone"}
  ]
}
```
