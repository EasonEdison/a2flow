from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import grpc
import pytest
from a2flow.a2ui.v1 import a2ui_pb2, a2ui_pb2_grpc
from a2flow.capability.v1 import capability_pb2
from a2flow_capability.models import Environment, ExecutionResult, JsonObject, TrustedContext

from a2flow_a2ui.ledger import SurfaceLedger
from a2flow_a2ui.models import (
    A2uiError,
    ApplicationBuild,
    ApplicationRelease,
    PublishedApplication,
    TrustedCard,
)
from a2flow_a2ui.rpc import A2uiRpcService
from a2flow_a2ui.runtime import A2uiRuntimeService, _execution_map, _predicate, map_request


def build_json() -> JsonObject:
    return {
        "appBuildId": "build-1",
        "appCode": "demo.app",
        "sourceDigest": "sha256:build",
        "protocolVersion": "v0.9.1",
        "protocolStatus": "ACTIVE",
        "protocolSourceCommit": "abc",
        "protocolSchemaDigests": {},
        "publicationEnvironment": "PRT",
        "catalog": {
            "catalogId": "catalog",
            "revision": "1",
            "digest": "sha256:catalog",
            "catalogSourceType": "LOCAL",
            "componentOrigins": {"Button": "STANDARD"},
        },
        "showTemplateCode": "show",
        "showTemplateDigest": "sha256:show",
        "paramsSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
        },
        "surfaceDeclarations": [
            {"surfaceId": "main", "rootComponentId": "root", "footerComponentIds": []}
        ],
        "initialMessages": [
            {
                "version": "v0.9.1",
                "createSurface": {"surfaceId": "main", "root": "root"},
            },
            {
                "version": "v0.9.1",
                "updateComponents": {
                    "surfaceId": "main",
                    "components": [
                        {"id": "root", "type": "Column", "children": ["submit"]},
                        {"id": "submit", "type": "Button", "label": "placeholder"},
                    ],
                },
            },
        ],
        "inputBindings": [
            {
                "targetMessageIndex": 1,
                "targetPath": "/updateComponents/components/1/label",
                "source": "APP_PARAMS",
                "sourcePath": "/title",
                "required": True,
                "constantValue": None,
            }
        ],
        "componentTypes": ["Column", "Button"],
        "capabilitySchemaAudits": [],
        "actionDeclarations": [
            {
                "surfaceId": "main",
                "sourceComponentId": "submit",
                "actionCode": "demo.submit",
                "contextTemplateDigest": "sha256:context",
            }
        ],
        "loadBindings": [],
        "actionBindings": [
            {
                "bindingId": "submit-binding",
                "surfaceId": "main",
                "sourceComponentId": "submit",
                "actionCode": "demo.submit",
                "declarationDigest": "sha256:context",
                "allowedSourceComponentIds": ["submit"],
                "contextSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
                "capability": {"actionCode": "demo.submit"},
                "requestMappings": [
                    {
                        "source": "ACTION_CONTEXT",
                        "sourcePath": "/name",
                        "targetPath": "/name",
                        "constantValue": None,
                    }
                ],
                "successOutcome": "ADAPTER_PIPELINE",
                "failureOutcome": "NO_UI_MESSAGES",
                "resultAdapters": [
                    {
                        "adapterId": "success",
                        "order": 1,
                        "type": "MESSAGE_TEMPLATE",
                        "templateCode": "result",
                        "templateRevision": "1",
                        "templateDigest": "sha256:result",
                        "messageTemplate": {
                            "version": "v0.9.1",
                            "updateDataModel": {
                                "surfaceId": "main",
                                "path": "/",
                                "value": {},
                            },
                        },
                        "bindings": [
                            {
                                "targetPath": "/updateDataModel/value/greeting",
                                "source": "CAPABILITY_DATA",
                                "sourcePath": "/greeting",
                                "required": True,
                                "constantValue": None,
                            }
                        ],
                        "source": None,
                        "sourcePath": None,
                        "cardinality": None,
                        "required": False,
                        "emittedActionDeclarations": [],
                    }
                ],
                "failureResultAdapters": [],
                "businessSuccessPredicate": {
                    "version": "v1",
                    "allOf": [
                        {
                            "source": "CAPABILITY_DATA",
                            "sourcePath": "/ok",
                            "operator": "EQUALS",
                            "expectedValue": True,
                        }
                    ],
                },
                "completeWorkflowInteractionOnSuccess": True,
                "successBranches": [],
            }
        ],
        "interactionMode": "INTERACTIVE",
    }


class Releases:
    def __init__(self, published: PublishedApplication) -> None:
        self.published = published

    def current(self, app_code: str, context: TrustedContext) -> PublishedApplication:
        assert app_code == self.published.release.app_code
        assert context.environment is self.published.release.environment
        return self.published


class Capabilities:
    def __init__(self) -> None:
        self.calls: list[tuple[str, JsonObject, TrustedContext]] = []

    def execute_action_code(
        self, action_code: str, arguments: JsonObject, context: TrustedContext
    ) -> ExecutionResult:
        self.calls.append((action_code, arguments, context))
        return ExecutionResult(
            True,
            action_code,
            "cap-build",
            "sha256:cap",
            3,
            context.client,
            context.environment,
            context.environment,
            context.request_id,
            {"ok": True, "greeting": f"hello {arguments['name']}"},
        )


def service() -> tuple[A2uiRuntimeService, Capabilities, PublishedApplication]:
    build = ApplicationBuild.model_validate(build_json())
    release = ApplicationRelease("demo.app", "app-build", "sha256:app", "build-1", Environment.PRT)
    published = PublishedApplication(release, build)
    capabilities = Capabilities()
    return A2uiRuntimeService(Releases(published), capabilities), capabilities, published


def context(request_id: str = "request-1") -> TrustedContext:
    return TrustedContext(0, Environment.PRT, request_id, "PC")


def test_activate_and_action_preserve_release_session_and_trusted_child_request() -> None:
    runtime, capabilities, published = service()
    activated = runtime.activate(
        "demo.app", {"title": "提交"}, "app-build", "sha256:app", context()
    )
    assert activated.snapshot[1]["updateComponents"]["components"][1]["label"] == "提交"  # type: ignore[index]
    card = TrustedCard(
        0, published.release, activated.session, 7, activated.params, activated.snapshot
    )
    action = {
        "version": "v0.9.1",
        "action": {
            "name": "demo.submit",
            "surfaceId": "main",
            "sourceComponentId": "submit",
            "timestamp": "2026-09-25T00:00:00Z",
            "context": {"name": "A2Flow"},
        },
    }
    result = runtime.act(
        card,
        "correlation",
        activated.session.token,
        "build-1",
        7,
        "request-2",
        action,
        context("request-2"),
    )
    assert result.complete_interaction is True
    assert result.business_success is True
    assert result.selected_branch_id is None
    assert result.snapshot[-1]["updateDataModel"]["value"] == {"greeting": "hello A2Flow"}  # type: ignore[index]
    assert capabilities.calls[0][1] == {"name": "A2Flow"}
    assert capabilities.calls[0][2].request_id.startswith("a2ui:")


def test_act_rejects_authority_input_before_capability() -> None:
    runtime, capabilities, published = service()
    activated = runtime.activate(
        "demo.app", {"title": "提交"}, "app-build", "sha256:app", context()
    )
    card = TrustedCard(
        0, published.release, activated.session, 1, activated.params, activated.snapshot
    )
    action = {
        "version": "v0.9.1",
        "action": {
            "name": "demo.submit",
            "surfaceId": "main",
            "sourceComponentId": "submit",
            "timestamp": "2026-09-25T00:00:00Z",
            "context": {"name": "x", "target_endpoint": "evil"},
        },
    }
    with pytest.raises(A2uiError, match="A2UI_ACTION_CONTEXT_AUTHORITY_FORBIDDEN"):
        runtime.act(
            card,
            "correlation",
            activated.session.token,
            "build-1",
            1,
            "request-2",
            action,
            context("request-2"),
        )
    assert capabilities.calls == []


def test_release_change_is_rejected_before_capability() -> None:
    runtime, capabilities, _ = service()
    with pytest.raises(A2uiError, match="RESET_REQUIRED"):
        runtime.activate("demo.app", {"title": "x"}, "stale", "sha256:app", context())
    assert capabilities.calls == []


def test_ledger_batch_is_atomic_and_replayable() -> None:
    ledger = SurfaceLedger.empty().reduce(
        [{"version": "v0.9.1", "createSurface": {"surfaceId": "main"}}]
    )
    with pytest.raises(A2uiError):
        ledger.reduce(
            [
                {
                    "version": "v0.9.1",
                    "updateComponents": {
                        "surfaceId": "main",
                        "components": [{"id": "one"}],
                    },
                },
                {"version": "v0.9.1", "deleteSurface": {"surfaceId": "missing"}},
            ]
        )
    assert ledger.snapshot() == ({"version": "v0.9.1", "createSurface": {"surfaceId": "main"}},)


def test_build_and_mapping_are_closed() -> None:
    raw = build_json()
    raw["unknown"] = True
    with pytest.raises(ValueError):
        ApplicationBuild.model_validate(raw)

    build = ApplicationBuild.model_validate(build_json())
    mapping = build.action_bindings[0].request_mappings[0]
    assert map_request((mapping,), action={"name": "x"}, params={}, trusted={}, previous=None) == {
        "name": "x"
    }
    conflicting = mapping.model_copy(update={"source_path": "/name", "target_path": "/name/value"})
    with pytest.raises(A2uiError, match="A2UI_REQUEST_MAPPING_INVALID"):
        map_request(
            (mapping, conflicting), action={"name": "x"}, params={}, trusted={}, previous=None
        )


def test_existing_grpc_contract_describe_activate_and_act() -> None:
    runtime, _, _ = service()
    server = grpc.server(ThreadPoolExecutor(max_workers=2))
    a2ui_pb2_grpc.add_A2uiExecutionServicer_to_server(A2uiRpcService(runtime), server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    stub = a2ui_pb2_grpc.A2uiExecutionStub(channel)
    owner = capability_pb2.ExecutionContext(
        user_id=0,
        environment=capability_pb2.PRT,
        request_id="rpc-activate",
        client="PC",
    )
    try:
        described = stub.Describe(a2ui_pb2.DescribeRequest(context=owner, app_code="demo.app"))
        assert described.release.app_build_id == "build-1"
        assert described.actions[0].action_name == "demo.submit"
        activated = stub.Activate(
            a2ui_pb2.ActivateRequest(
                context=owner,
                app_code="demo.app",
                params_json=b'{"title":"RPC"}',
                expected_source_id="app-build",
                expected_digest="sha256:app",
            )
        )
        action_context = capability_pb2.ExecutionContext(
            user_id=0,
            environment=capability_pb2.PRT,
            request_id="rpc-act",
            client="PC",
        )
        acted = stub.Act(
            a2ui_pb2.ActRequest(
                context=action_context,
                card=a2ui_pb2.TrustedCard(
                    user_id=0,
                    release=activated.release,
                    session=activated.session,
                    revision=2,
                    params_json=activated.params_json,
                    snapshot_json=activated.snapshot_json,
                ),
                correlation_id="rpc-correlation",
                runtime_session_token=activated.session.token,
                app_build_id=activated.session.app_build_id,
                expected_surface_revision=2,
                idempotency_key="rpc-act",
                action_message_json=json.dumps(
                    {
                        "version": "v0.9.1",
                        "action": {
                            "name": "demo.submit",
                            "surfaceId": "main",
                            "sourceComponentId": "submit",
                            "timestamp": "2026-09-25T00:00:00Z",
                            "context": {"name": "RPC"},
                        },
                    }
                ).encode(),
            )
        )
        assert acted.complete_interaction is True
        assert acted.release == activated.release
        assert acted.session == activated.session
    finally:
        channel.close()
        server.stop(0).wait(timeout=3)


def test_java_compiler_build_shape_load_branch_predicate_and_metadata() -> None:
    raw = build_json()
    raw["loadBindings"] = [
        {
            "bindingId": "first-binding",
            "capability": {"actionCode": "first"},
            "requestMappings": [
                {
                    "source": "TRUSTED_CONTEXT",
                    "sourcePath": "/userId",
                    "targetPath": "/identity",
                    "constantValue": None,
                }
            ],
            "successOutcome": "NO_UI_MESSAGES",
            "failureOutcome": "NO_UI_MESSAGES",
            "resultAdapters": [],
            "failureResultAdapters": [],
        },
        {
            "bindingId": "second-binding",
            "capability": {"actionCode": "second"},
            "requestMappings": [
                {
                    "source": "CAPABILITY_PREVIOUS_RESULT",
                    "sourcePath": "/data/value",
                    "targetPath": "/previous",
                    "constantValue": None,
                }
            ],
            "successOutcome": "ADAPTER_PIPELINE",
            "failureOutcome": "NO_UI_MESSAGES",
            "resultAdapters": [
                {
                    "adapterId": "pass",
                    "order": 1,
                    "type": "A2UI_PASSTHROUGH",
                    "templateCode": None,
                    "templateRevision": None,
                    "templateDigest": None,
                    "messageTemplate": None,
                    "bindings": [],
                    "source": "CAPABILITY_DATA",
                    "sourcePath": "/messages",
                    "cardinality": "MANY",
                    "required": True,
                    "emittedActionDeclarations": [
                        {
                            "surfaceId": "main",
                            "sourceComponentId": "submit",
                            "actionCode": "demo.submit",
                            "contextSchema": {"type": "object"},
                        }
                    ],
                }
            ],
            "failureResultAdapters": [],
        },
    ]
    raw_action = raw["actionBindings"][0]  # type: ignore[index]
    assert isinstance(raw_action, dict)
    raw_action.pop("successBranches")
    build = ApplicationBuild.model_validate(raw)
    assert build.action_bindings[0].success_branches == ()
    assert build.load_bindings[1].result_adapters[0].bindings == ()

    result = ExecutionResult(
        True,
        "first",
        "source",
        "sha256:digest",
        2,
        "PC",
        Environment.PRT,
        Environment.PRT,
        "child",
        {"value": 7},
    )
    assert _execution_map(result) == {
        "actionCode": "first",
        "capabilityVersion": 2,
        "clientType": "PC",
        "requestedEnvironment": "PRT",
        "resolvedEnvironment": "PRT",
        "success": True,
        "httpStatus": None,
        "contentType": None,
        "traceId": None,
        "data": {"value": 7},
        "errorCode": None,
        "message": None,
    }
    predicate = build.action_bindings[0].business_success_predicate
    assert predicate is not None
    root_predicate = predicate.model_copy(
        update={
            "all_of": (
                predicate.all_of[0].model_copy(update={"source_path": "", "expected_value": 7}),
            )
        }
    )
    root_result = ExecutionResult(
        True,
        "first",
        "source",
        "sha256:digest",
        2,
        "PC",
        Environment.PRT,
        Environment.PRT,
        "child",
        7,
    )
    assert _predicate(root_predicate, root_result) is True


def test_boolean_mask_uses_java_overlap_prefix_semantics() -> None:
    build = ApplicationBuild.model_validate(build_json())
    original = build.action_bindings[0].request_mappings[0]
    raw_mapping = original.model_dump(by_alias=True)
    raw_mapping.update(
        {
            "source": "APP_PARAMS",
            "sourcePath": "/items",
            "targetPath": "/selected",
            "transform": {"type": "ARRAY_FILTER_BY_BOOLEAN_MASK", "maskSourcePath": "/mask"},
        }
    )
    typed_mapping = type(original).model_validate(raw_mapping)
    assert map_request(
        (typed_mapping,),
        action={},
        params={"items": ["a", "b", "c"], "mask": [False, True]},
        trusted={},
        previous=None,
    ) == {"selected": ["b"]}
