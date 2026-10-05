from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast
from unittest.mock import Mock

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
    ResultTransform,
    TrustedCard,
)
from a2flow_a2ui.rpc import A2uiRpcService, _response as rpc_response
from a2flow_a2ui.runtime import (
    A2uiRuntimeService,
    _execution_map,
    _predicate,
    _transform,
    map_request,
)


def test_rpc_internal_failure_logs_only_safe_stage_type_and_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class SecretFailure(Exception):
        pass

    context = Mock()
    context.abort.side_effect = RuntimeError("abort")
    service = A2uiRpcService(cast(Any, None))

    with (
        caplog.at_level(logging.ERROR, logger="a2flow_a2ui.rpc"),
        pytest.raises(RuntimeError, match="abort"),
    ):
        service._respond(
            context,
            lambda: (_ for _ in ()).throw(SecretFailure("private manuscript body")),
            stage="act",
        )

    message = caplog.text
    assert "stage=act" in message
    assert "exception_type=SecretFailure" in message
    assert "error_code=A2UI_EXECUTION_FAILED" in message
    assert "private manuscript body" not in message
    context.abort.assert_called_once_with(grpc.StatusCode.INTERNAL, "A2UI_EXECUTION_FAILED")


def build_json() -> JsonObject:
    return {
        "appBuildId": "build-1",
        "appCode": "demo.app",
        "description": "Demo application",
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
                    "version": "JSON_POINTER_V1",
                    "allOf": [
                        {
                            "source": "CAPABILITY_DATA",
                            "sourcePath": "/decisionType",
                            "operator": "EQUALS",
                            "expectedValue": "READING",
                        }
                    ],
                },
                "completeWorkflowInteractionOnSuccess": True,
                "successBranches": [],
            }
        ],
        "interactionMode": "INTERACTIVE",
    }


def test_catalog_function_contract_is_optional_and_preserved() -> None:
    legacy = ApplicationBuild.model_validate(build_json())
    assert legacy.catalog.function_contract is None
    assert legacy.description == "Demo application"

    current = build_json()
    function_contract: JsonObject = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://a2flow.dev/catalogs/demo/functions.json",
        "catalogId": "catalog",
        "functions": {
            "equals": {
                "type": "object",
                "properties": {
                    "call": {"const": "equals"},
                    "args": {"type": "object"},
                },
            }
        },
    }
    current["catalog"]["functionContract"] = function_contract  # type: ignore[index]
    parsed = ApplicationBuild.model_validate(current)

    assert parsed.catalog.function_contract == function_contract
    assert parsed.model_dump(by_alias=True)["catalog"]["functionContract"] == function_contract


def test_array_object_to_options_formats_scalar_and_array_columns() -> None:
    transform = ResultTransform.model_validate({
        "type": "ARRAY_OBJECT_TO_OPTIONS",
        "valuePath": "/personId",
        "labelColumns": [
            {"label": "姓名", "sourcePath": "/name"},
            {"label": "年龄", "sourcePath": "/age"},
            {"label": "爱好", "sourcePath": "/hobbies"},
        ],
        "labelSeparator": "\N{FULLWIDTH VERTICAL LINE}",
    })

    assert _transform(
        transform,
        [{"personId": "p1", "name": "张三", "age": 28, "hobbies": ["阅读", "徒步"]}],
        "/updateDataModel/value/options",
        {},
    ) == [{
        "label": (
            "姓名\N{FULLWIDTH COLON}张三\N{FULLWIDTH VERTICAL LINE}"
            "年龄\N{FULLWIDTH COLON}28\N{FULLWIDTH VERTICAL LINE}"
            "爱好\N{FULLWIDTH COLON}阅读\N{IDEOGRAPHIC COMMA}徒步"
        ),
        "value": "p1",
    }]

    with pytest.raises(A2uiError, match="A2UI_ADAPTER_RESULT_INVALID"):
        _transform(
            transform,
            [{"personId": "p1", "name": {"unsafe": "object"}, "age": 28, "hobbies": []}],
            "/updateDataModel/value/options",
            {},
        )


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
            {
                "decisionType": "READING",
                "greeting": f"hello {arguments['name']}",
            },
        )


def service() -> tuple[A2uiRuntimeService, Capabilities, PublishedApplication]:
    build = ApplicationBuild.model_validate(build_json())
    release = ApplicationRelease("demo.app", "app-build", "sha256:app", "build-1", Environment.PRT)
    published = PublishedApplication(release, build)
    capabilities = Capabilities()
    return A2uiRuntimeService(Releases(published), capabilities), capabilities, published


def context(request_id: str = "request-1") -> TrustedContext:
    return TrustedContext(0, Environment.PRT, request_id, "PC")


def test_successful_action_emits_response_scoped_composer_draft_effect() -> None:
    raw = build_json()
    binding = cast(dict[str, Any], cast(list[Any], raw["actionBindings"])[0])
    binding["composerDraftEffect"] = {
        "type": "COMPOSER_DRAFT",
        "mode": "APPEND",
        "source": "CAPABILITY_DATA",
        "itemsPath": "/items",
        "columns": [
            {"label": "姓名", "sourcePath": "/name"},
            {"label": "电话", "sourcePath": "/phone"},
        ],
    }
    build = ApplicationBuild.model_validate(raw)
    release = ApplicationRelease(
        "demo.app", "app-build", "sha256:app", "build-1", Environment.PRT
    )

    class ResolveCapabilities(Capabilities):
        def __init__(self, decision_type: str = "READING") -> None:
            super().__init__()
            self.decision_type = decision_type

        def execute_action_code(
            self, action_code: str, arguments: JsonObject, child: TrustedContext
        ) -> ExecutionResult:
            self.calls.append((action_code, arguments, child))
            return ExecutionResult(
                True, action_code, "cap-build", "sha256:cap", 3, child.client,
                child.environment, child.environment, child.request_id,
                {
                    "decisionType": self.decision_type,
                    "greeting": "resolved",
                    "items": [
                        {"name": "张三", "phone": "138****0001"},
                        {"name": "李四", "phone": "139****0002"},
                    ],
                },
            )

    capabilities = ResolveCapabilities()
    runtime = A2uiRuntimeService(
        Releases(PublishedApplication(release, build)), capabilities
    )
    activated = runtime.activate("demo.app", {"title": "提交"}, context())
    result = runtime.act(
        TrustedCard(0, "demo.app", activated.params, activated.snapshot),
        "correlation",
        "request-2",
        {
            "version": "v0.9.1",
            "action": {
                "name": "demo.submit",
                "surfaceId": "main",
                "sourceComponentId": "submit",
                "timestamp": "2026-10-05T00:00:00Z",
                "context": {"name": "A2Flow"},
            },
        },
        context("request-2"),
    )

    assert len(result.composer_draft_effects) == 1
    effect = result.composer_draft_effects[0]
    assert effect.request_id == "request-2"
    assert effect.text == (
        "姓名\N{FULLWIDTH COLON}张三\N{FULLWIDTH COMMA}"
        "电话\N{FULLWIDTH COLON}138****0001\n"
        "姓名\N{FULLWIDTH COLON}李四\N{FULLWIDTH COMMA}"
        "电话\N{FULLWIDTH COLON}139****0002"
    )
    assert result.action_observation is not None
    assert result.action_observation.business_success is True
    wire = rpc_response(result)
    assert len(wire.composer_draft_effects) == 1
    assert wire.composer_draft_effects[0].request_id == "request-2"

    rejected_capabilities = ResolveCapabilities("OTHER")
    rejected_runtime = A2uiRuntimeService(
        Releases(PublishedApplication(release, build)), rejected_capabilities
    )
    rejected_activated = rejected_runtime.activate(
        "demo.app", {"title": "提交"}, context()
    )
    rejected = rejected_runtime.act(
        TrustedCard(
            0, "demo.app", rejected_activated.params, rejected_activated.snapshot
        ),
        "correlation",
        "request-3",
        {
            "version": "v0.9.1",
            "action": {
                "name": "demo.submit",
                "surfaceId": "main",
                "sourceComponentId": "submit",
                "timestamp": "2026-10-05T00:00:00Z",
                "context": {"name": "A2Flow"},
            },
        },
        context("request-3"),
    )
    assert rejected.business_success is False
    assert rejected.composer_draft_effects == ()


def test_activate_and_action_use_current_release_and_trusted_child_request() -> None:
    runtime, capabilities, _ = service()
    activated = runtime.activate("demo.app", {"title": "提交"}, context())
    assert activated.snapshot[1]["updateComponents"]["components"][1]["label"] == "提交"  # type: ignore[index]
    card = TrustedCard(0, "demo.app", activated.params, activated.snapshot)
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
    observation = result.action_observation
    assert observation is not None
    assert observation.arguments == {"name": "A2Flow"}
    assert observation.result == {
        "decisionType": "READING",
        "greeting": "hello A2Flow",
    }
    assert observation.business_success is True
    assert observation.presentation_error_code is None


def test_action_observation_records_mapped_business_values_and_filters_authority() -> None:
    raw = build_json()
    binding = cast(dict[str, Any], raw["actionBindings"][0])  # type: ignore[index]
    binding["requestMappings"].extend(
        [
            {
                "source": "APP_PARAMS",
                "sourcePath": "/title",
                "targetPath": "/draftTitle",
                "constantValue": None,
            },
            {
                "source": "CONSTANT",
                "sourcePath": None,
                "targetPath": "/options",
                "constantValue": {
                    "kind": "MANUSCRIPT",
                    "endpoint": "business-endpoint",
                    "title": "保留业务标题",
                    "credentials": {"token": "secret"},
                },
            },
            {
                "source": "TRUSTED_CONTEXT",
                "sourcePath": "/userId",
                "targetPath": "/userId",
                "constantValue": None,
            },
        ]
    )
    build = ApplicationBuild.model_validate(raw)
    release = ApplicationRelease(
        "demo.app", "app-build", "sha256:app", "build-1", Environment.PRT
    )
    published = PublishedApplication(release, build)
    capabilities = Capabilities()
    runtime = A2uiRuntimeService(Releases(published), capabilities)
    activated = runtime.activate("demo.app", {"title": "用户草稿"}, context())
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
        TrustedCard(0, "demo.app", activated.params, activated.snapshot),
        "correlation",
        "request-2",
        action,
        context("request-2"),
    )

    assert capabilities.calls[0][1]["userId"] == 0
    observation = result.action_observation
    assert observation is not None
    assert observation.arguments == {
        "name": "A2Flow",
        "draftTitle": "用户草稿",
        "options": {
            "kind": "MANUSCRIPT",
            "endpoint": "business-endpoint",
            "title": "保留业务标题",
        },
    }


class InvalidPresentationCapabilities(Capabilities):
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
            {
                "decisionType": "READING",
                "receiptId": "receipt-1",
                "details": {
                    "title": "保留结果标题",
                    "endpoint": "business-endpoint",
                    "credentialHandle": "private-handle",
                },
            },
        )


def test_presentation_failure_preserves_business_result_and_old_ledger() -> None:
    build = ApplicationBuild.model_validate(build_json())
    release = ApplicationRelease(
        "demo.app", "app-build", "sha256:app", "build-1", Environment.PRT
    )
    published = PublishedApplication(release, build)
    capabilities = InvalidPresentationCapabilities()
    runtime = A2uiRuntimeService(Releases(published), capabilities)
    activated = runtime.activate("demo.app", {"title": "提交"}, context())
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
        TrustedCard(0, "demo.app", activated.params, activated.snapshot),
        "correlation",
        "request-presentation",
        action,
        context("request-presentation"),
    )

    assert len(capabilities.calls) == 1
    assert result.snapshot == activated.snapshot
    assert result.messages == ()
    assert result.complete_interaction is False
    assert result.business_success is True
    observation = result.action_observation
    assert observation is not None
    assert observation.result == {
        "decisionType": "READING",
        "receiptId": "receipt-1",
        "details": {
            "title": "保留结果标题",
            "endpoint": "business-endpoint",
        },
    }
    assert observation.business_success is True
    assert observation.presentation_error_code == "A2UI_ADAPTER_SOURCE_MISSING"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("version", "v1"),
        ("source", "TRUSTED_CONTEXT"),
        ("operator", "CONTAINS"),
    ),
)
def test_invalid_business_predicate_dialect_is_rejected_while_loading_publication(
    field: str, value: str
) -> None:
    raw = cast(dict[str, Any], build_json())
    predicate = raw["actionBindings"][0]["businessSuccessPredicate"]
    if field == "version":
        predicate[field] = value
    else:
        predicate["allOf"][0][field] = value
    with pytest.raises(ValueError):
        ApplicationBuild.model_validate(raw)


def test_act_rejects_authority_input_before_capability() -> None:
    runtime, capabilities, published = service()
    activated = runtime.activate("demo.app", {"title": "提交"}, context())
    card = TrustedCard(0, "demo.app", activated.params, activated.snapshot)
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
            "request-2",
            action,
            context("request-2"),
        )
    assert capabilities.calls == []


def test_activate_uses_current_release_without_caller_version_gate() -> None:
    runtime, capabilities, _ = service()
    activated = runtime.activate("demo.app", {"title": "x"}, context())
    assert activated.release.source_id == "app-build"
    assert capabilities.calls == []


def test_old_card_action_executes_against_current_application_release() -> None:
    original = PublishedApplication(
        ApplicationRelease(
            "demo.app", "app-build-v1", "sha256:app-v1", "build-1", Environment.PRT,
        ),
        ApplicationBuild.model_validate(build_json()),
    )
    releases = Releases(original)
    capabilities = Capabilities()
    runtime = A2uiRuntimeService(releases, capabilities)
    activated = runtime.activate("demo.app", {"title": "v1 card"}, context())

    current_json = build_json()
    current_json["appBuildId"] = "build-2"
    current_json["sourceDigest"] = "sha256:build-2"
    releases.published = PublishedApplication(
        ApplicationRelease(
            "demo.app", "app-build-v2", "sha256:app-v2", "build-2", Environment.PRT,
        ),
        ApplicationBuild.model_validate(current_json),
    )
    result = runtime.act(
        TrustedCard(0, "demo.app", activated.params, activated.snapshot),
        "correlation",
        "request-v2",
        {
            "version": "v0.9.1",
            "action": {
                "name": "demo.submit",
                "surfaceId": "main",
                "sourceComponentId": "submit",
                "timestamp": "2026-10-04T00:00:00Z",
                "context": {"name": "current"},
            },
        },
        context("request-v2"),
    )

    assert result.release.source_id == "app-build-v2"
    assert result.release.app_build_id == "build-2"
    assert capabilities.calls[0][1] == {"name": "current"}


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
                    app_code="demo.app",
                    params_json=activated.params_json,
                    snapshot_json=activated.snapshot_json,
                ),
                correlation_id="rpc-correlation",
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
        assert acted.session.app_build_id == activated.session.app_build_id
        assert acted.action_observation.binding_id == "submit-binding"
        assert json.loads(acted.action_observation.arguments_json) == {"name": "RPC"}
        assert json.loads(acted.action_observation.result_json)["decisionType"] == "READING"
        assert acted.action_observation.business_success is True
        assert acted.action_observation.presentation_error_code == ""
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
