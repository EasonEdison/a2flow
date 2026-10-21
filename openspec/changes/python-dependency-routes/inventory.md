# Python HTTP and composition boundary inventory

Inspected source baseline: `b5785c5` (2026-10-22). Paths and line numbers below
refer to that immutable baseline; the refactor moves declarations. This is a
source inventory, not a claim that each server process has been deployed.

## Active boundaries in the approved refactor

| Baseline location | Finding | Treatment |
| --- | --- | --- |
| `services/b-side-api/src/a2flow_bside/app.py:309–1270` | `create_app` contains 42 route closures; 13 repository/service/callback arguments lack annotations. Ownership, card continuation and lifecycle logic share the closure scope. | Split domain routers; explicit typed service dependencies; retain middleware, exception mapping and lifecycle at application composition. |
| `services/b-side-api/src/a2flow_bside/assembly.py:65–115` | Generic environment factory leaves `chat_runner` untyped and defines an untyped catalog callback/connection lambda. This remains a supported importable factory; real deployment uses attended composition. | Annotate real dependencies and callback signatures; preserve the explicit fail-closed runner when absent. |
| `deploy/attended/bside_app.py:68–265` | Production B factory builds real runner, durable dispatcher, card actions, processing repository, memory and catalog callbacks through untyped nested functions. | Type actual callback inputs/returns and dependencies, preserving explicit construction. |
| `deploy/attended/chat_runner.py:26–72` | Runner constructor receives eight untyped dependencies/callbacks, although it is the actual Chat adapter. | Type configuration, reader, history, observations and asset construction; preserve its single native Agent execution and stream producer ownership. |
| `services/b-side-api/src/a2flow_bside/chat_delivery.py:97` | Product delivery constructor has untyped runner/messages/context parameters. | Type the adjacent boundary without changing projection, cancellation or continuation behavior. |
| `services/b-side-api/src/a2flow_bside/durable_chat.py:550–558` | Fenced projection writer and dispatcher have implicit repository/runner/processing dependencies. | Type known single implementations and existing supported ports; preserve dispatch generation fencing. |
| `services/agent-workflow-runtime/src/agent_workflow_runtime/http.py:173–262` | Small HTTP factory has untyped service, lane and observer arguments. Only seven base routes; does not warrant another router hierarchy. | Add direct dependency/callback annotations; retain route layout and lane semantics. |
| `services/agent-workflow-runtime/src/agent_workflow_runtime/progress_http.py:29–53` | Progress route attachment and leased SSE callback/service boundary are untyped. | Review alongside the Runtime HTTP entry; keep admission/release and disconnect behavior. |

Active deployment path: `deploy/selfhost/launcher.py` selects
`deploy.realchat.launcher`; its `bside()` delegates to the attended B factory and
mounts employee static assets. Its `runtime()` constructs `RpcWorkflowHost`,
which inherits `MvpRuntimeHost` and attaches the Runtime HTTP/progress routes.
Names containing “mvp” therefore do not establish that code is retired.

## Other inspected ingress and engine boundaries

| Baseline location | Evidence and boundary decision |
| --- | --- |
| `deploy/accounts/app.py:201–309` | Shared account ingress already takes concrete `AccountAuthentication`, typed account ports and typed Request/Response middleware; its six alias routes are in a small attach function. No oversized untyped route factory. Dynamic account row fields remain a separate data-contract concern. |
| `services/agent-workflow-runtime/src/agent_workflow_runtime/management_agent/host.py:53–54` | Management gRPC ingress already injects concrete `ManagementStore` and `ManagementRunner`; generated request/response methods are annotated. `dict[str, Any]` encoding helpers represent existing persistence/serialization boundaries, not an untyped service locator. No route-factory split. |
| `services/agent-workflow-runtime/src/agent_workflow_runtime/workflow_rpc_host.py:261,498–588` | Active production host is typed at its overridden constructor and returns a verified identity wrapper. Its approximately 90-line app attachment is smaller than B factory; preserve its native Workflow action and resume semantics. |
| `services/agent-workflow-runtime/src/agent_workflow_runtime/mvp_assembly.py:101` | Active inherited host has broad untyped constructor options. Documented engine construction debt, not evidence of a second Agent loop or reason to introduce a Bean container. Type direct entry boundaries where required; do not rewrite internal graph execution in this change. |
| `services/agent-workflow-runtime/src/agent_workflow_runtime/model_factory.py:17` | Configuration and secret resolvers plus HTTP clients lack signatures. Callback typing is relevant to actual deployment composition; preserve native SDK construction. |
| `services/agent-workflow-runtime/src/agent_workflow_runtime/service.py:55` | RuntimeService has implicit lifecycle/session/resolver/progress/validation dependency shapes. Relevant to HTTP service navigation; type supported implementations/ports without altering control state semantics. |
| `services/agent-workflow-runtime/src/agent_workflow_runtime/chat/loop.py:672` | Native Agent adapter has many implicit SDK/tool/context constructor parameters. Engine-internal, not another HTTP factory. No new execution loop, checkpoint ownership change or speculative generic interfaces. |
| `services/agent-workflow-runtime/src/agent_workflow_runtime/asset_adapters.py:21`, `workflow_loader.py:24`, `native_control.py:199`, `progress_writer.py:98` | Additional internal dependency typing debt recorded for visibility. No independent oversized route factory; avoid expanding a transport/composition refactor into a graph/asset/lifecycle rewrite. |
| `deploy/mvp/runtime_support.py:80` | Older demo model support has untyped local file/token settings. Not the realchat model factory, and no route dependency issue; excluded. |

AST inventory scanned non-test Python under `services`, `deploy` and `apps` for
factories with nested HTTP decorators and a body exceeding 180 lines. The B
factory was the sole match. Small route attachments and gRPC ingress were then
inspected separately, along with untyped constructors on the active call chain.

## Verification added

`services/b-side-api/tests/test_route_composition.py` constructs the real generic
and attended B factories, blocks socket/psycopg access, replaces only explicit
external readiness/catalog/RPC boundaries, and checks concrete repository,
Runtime client, Chat runner, durable continuation and processing dependencies.
It also calls the realchat B entry and verifies its static mount delegates to the
attended app.

The baseline fixture `tests/fixtures/routes-b5785c5.json` pins all 42 routes in
registration order, methods, response class/status, complete per-path OpenAPI
wire schema digests and request-component schema digests. It excludes Python
module locations, so a router move is allowed while an API contract drift fails.
The request-level test separately pins authentication, missing Origin, rejected
undeclared queries and non-owned conversation behavior using offline ASGI.

The additional Runtime composition check constructs the actual `RpcWorkflowHost`
through `deploy.realchat.launcher.runtime()` without opening a connection. Its
separate immutable fixture pins all 19 Runtime routes and OpenAPI schemas,
including action, card, resume and progress endpoints. The example activity
package is needed on the test PYTHONPATH, matching the real host imports.

Baseline execution: all five tests pass in `a2flow-core-probes:local`, with
`--network none`, no model key, no database and no production requests. The same
test file must be rerun after integrating the router/composition changes; this
baseline result alone does not establish post-refactor equivalence.

Baseline broader checks (same image/source): B discovery before the fifth new
test ran 72 tests: 64 passed, two PostgreSQL tests skipped and six existing
failures/errors (old schedule/run/notification fakes and incomplete
InternalRunStart fixture). Runtime `test_http` ran 12 tests: ten passed; existing
timeout-state and stale-reset assertions failed unchanged. These are recorded
comparison boundaries, not successful whole-suite results.
