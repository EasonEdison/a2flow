from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

import pytest
from a2flow_capability.models import Environment, ExecutionResult, JsonObject, TrustedContext
from jsonschema import Draft202012Validator
from test_runtime import build_json

from a2flow_a2ui.generation import contract, definition, validate_candidate, verify_definition
from a2flow_a2ui.models import (
    A2uiError,
    ApplicationBuild,
    ApplicationRelease,
    DefinitionSource,
    GeneratedCandidate,
    GenerationScope,
    PublishedApplication,
)
from a2flow_a2ui.rpc import _candidate
from a2flow_a2ui.runtime import A2uiRuntimeService

CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
MEMBERSHIP = {"Column": "A2UI_OFFICIAL", "Text": "A2UI_OFFICIAL"}


def source() -> PublishedApplication:
    raw = build_json()
    raw["catalog"]["catalogId"] = CATALOG_ID  # type: ignore[index]
    raw["initialMessages"] = [
        {"version": "v0.9.1", "createSurface": {"surfaceId": "main", "catalogId": CATALOG_ID}},
        {
            "version": "v0.9.1",
            "updateComponents": {
                "surfaceId": "main",
                "components": [
                    {"id": "root", "component": "Column", "children": ["title"]},
                    {"id": "title", "component": "Text", "text": {"path": "/title"}},
                ],
            },
        },
        {
            "version": "v0.9.1",
            "updateDataModel": {
                "surfaceId": "main",
                "path": "/",
                "value": {"title": ""},
            },
        },
    ]
    raw["inputBindings"] = [
        {
            "targetMessageIndex": 2,
            "targetPath": "/updateDataModel/value/title",
            "source": "APP_PARAMS",
            "sourcePath": "/title",
            "required": True,
        }
    ]
    raw["actionBindings"] = []
    raw["actionDeclarations"] = []
    raw["interactionMode"] = "DISPLAY_ONLY"
    build = ApplicationBuild.model_validate(raw)
    release = ApplicationRelease("demo.app", "source", "sha256:source", "build-1", Environment.PRT)
    return PublishedApplication(release, build)


def candidate() -> GeneratedCandidate:
    return GeneratedCandidate.model_validate(
        {
            "messages": [
                {
                    "version": "v0.9.1",
                    "createSurface": {"surfaceId": "main", "catalogId": CATALOG_ID},
                },
                {
                    "version": "v0.9.1",
                    "updateComponents": {
                        "surfaceId": "main",
                        "components": [
                            {"id": "root", "component": "Column", "children": ["new", "title"]},
                            {"id": "title", "component": "Text", "text": {"path": "/title"}},
                            {"id": "new", "component": "Text", "text": "Generated heading"},
                        ],
                    },
                },
            ],
            "actionPlacements": [],
        }
    )


def test_new_component_id_and_layout_are_accepted() -> None:
    published = source()
    result = validate_candidate(published, MEMBERSHIP, candidate())
    assert result.build.initial_messages[1]["updateComponents"]["components"][2]["id"] == "new"  # type: ignore[index]
    described = contract(published, MEMBERSHIP)
    assert {item.type for item in described.allowed_components} == {"Column", "Text"}
    assert described.allowed_data_paths == ("/title",)
    assert result.build.input_bindings[0].target_message_index == 2


def test_describe_exposes_v091_message_envelope_schema() -> None:
    schema = contract(source(), MEMBERSHIP).message_envelope_schema
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    messages = list(candidate().messages)
    assert validator.is_valid(messages)
    without_version = deepcopy(messages)
    del without_version[0]["version"]
    assert not validator.is_valid(without_version)
    reordered = list(reversed(messages))
    assert not validator.is_valid(reordered)


def test_rpc_candidate_shape_has_distinct_safe_error_code() -> None:
    with pytest.raises(A2uiError, match="A2UI_GENERATION_CANDIDATE_SHAPE_INVALID"):
        _candidate(b'{"messages":[],"actionPlacements":[]}')


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda raw: raw["messages"][0].pop("version"), "A2UI_GENERATION_MESSAGE_VERSION_INVALID"),
        (
            lambda raw: raw["messages"][0].update({"extra": True}),
            "A2UI_GENERATION_MESSAGE_ENVELOPE_INVALID",
        ),
        (
            lambda raw: raw["messages"][0]["createSurface"].update({"extra": True}),
            "A2UI_GENERATION_CREATE_SURFACE_SHAPE_INVALID",
        ),
        (
            lambda raw: raw["messages"][1]["updateComponents"].pop("components"),
            "A2UI_GENERATION_UPDATE_COMPONENTS_SHAPE_INVALID",
        ),
        (lambda raw: raw["messages"].reverse(), "A2UI_GENERATION_MESSAGE_ORDER_INVALID"),
        (
            lambda raw: raw["messages"][1]["updateComponents"]["components"][0].pop("id"),
            "A2UI_GENERATION_COMPONENT_SHAPE_INVALID",
        ),
    ],
)
def test_candidate_error_codes_distinguish_envelopes_without_content(
    mutation: Callable[[JsonObject], object], code: str
) -> None:
    raw = candidate().model_dump(by_alias=True)
    raw["messages"] = list(raw["messages"])
    mutation(raw)
    with pytest.raises(A2uiError) as error:
        validate_candidate(source(), MEMBERSHIP, GeneratedCandidate.model_validate(raw))
    assert error.value.code == code


def test_generated_activation_uses_origin_load_and_persists_definition() -> None:
    published = source()

    class Reader:
        def current(self, app_code: str, context: TrustedContext) -> PublishedApplication:
            assert app_code == "demo.app"
            return published

        def generation_catalog(self, catalog_id: str, context: TrustedContext) -> dict[str, str]:
            assert catalog_id == CATALOG_ID
            return MEMBERSHIP

    class NoCapabilities:
        def execute_action_code(
            self, action_code: str, arguments: JsonObject, context: TrustedContext
        ) -> ExecutionResult:
            raise AssertionError("display-only generation must not execute an action")

    reader = Reader()
    runtime = A2uiRuntimeService(reader, NoCapabilities(), reader)  # type: ignore[arg-type]
    owner = TrustedContext(7, Environment.PRT, "request", "PC")
    scope = GenerationScope(conversationId="conversation")
    result = runtime.activate_generated("demo.app", {"title": "Hello"}, candidate(), scope, owner)
    assert result.definition_source is DefinitionSource.GENERATED
    assert result.generated_definition is not None
    assert result.release.app_code == "demo.app"
    assert result.snapshot[-1]["updateDataModel"]["value"] == {"title": "Hello"}  # type: ignore[index]


def test_approved_action_can_be_placed_on_new_component_id() -> None:
    published = source()
    build_raw = published.build.model_dump(by_alias=True)
    original = ApplicationBuild.model_validate(build_json())
    build_raw["actionBindings"] = [
        item.model_dump(by_alias=True) for item in original.action_bindings
    ]
    build_raw["actionDeclarations"] = [
        item.model_dump(by_alias=True) for item in original.action_declarations
    ]
    build_raw["actionBindings"][0]["sourceComponentId"] = "button"
    build_raw["actionBindings"][0]["allowedSourceComponentIds"] = ["button"]
    build_raw["actionDeclarations"][0]["sourceComponentId"] = "button"
    components = build_raw["initialMessages"][1]["updateComponents"]["components"]
    components[0]["children"].extend(["button", "button_label"])
    approved_action = {"event": {"name": "demo.submit", "context": {"name": {"path": "/title"}}}}
    components.extend(
        [
            {
                "id": "button",
                "component": "Button",
                "child": "button_label",
                "action": approved_action,
            },
            {"id": "button_label", "component": "Text", "text": "Submit"},
        ]
    )
    published = PublishedApplication(published.release, ApplicationBuild.model_validate(build_raw))
    candidate_raw = candidate().model_dump(by_alias=True)
    candidate_components = candidate_raw["messages"][1]["updateComponents"]["components"]
    candidate_components[0]["children"].extend(
        ["button", "button_label", "another_button", "another_label"]
    )
    candidate_components.extend(
        [
            {
                "id": "button",
                "component": "Button",
                "child": "button_label",
                "action": approved_action,
            },
            {"id": "button_label", "component": "Text", "text": "Submit"},
            {
                "id": "another_button",
                "component": "Button",
                "child": "another_label",
                "action": approved_action,
            },
            {"id": "another_label", "component": "Text", "text": "Submit elsewhere"},
        ]
    )
    candidate_raw["actionPlacements"] = [
        {"bindingId": "submit-binding", "surfaceId": "main", "sourceComponentId": button_id}
        for button_id in ("button", "another_button")
    ]
    generated = validate_candidate(
        published,
        {**MEMBERSHIP, "Button": "A2UI_OFFICIAL"},
        GeneratedCandidate.model_validate(candidate_raw),
    )
    assert generated.build.action_bindings[0].allowed_source_component_ids == (
        "button",
        "another_button",
    )
    assert {item.source_component_id for item in generated.build.action_declarations} == {
        "button",
        "another_button",
    }


def test_published_local_functions_copy_but_new_expression_is_rejected() -> None:
    published = source()
    build_raw = published.build.model_dump(by_alias=True)
    local_action = {"functionCall": {"call": "required", "args": {"value": {"path": "/title"}}}}
    check = {
        "condition": {"call": "required", "args": {"value": {"path": "/title"}}},
        "message": "Required",
    }
    components = build_raw["initialMessages"][1]["updateComponents"]["components"]
    components[0]["children"].extend(["local_button", "local_label"])
    components.extend(
        [
            {
                "id": "local_button",
                "component": "Button",
                "child": "local_label",
                "action": local_action,
                "checks": [check],
            },
            {"id": "local_label", "component": "Text", "text": "Local"},
        ]
    )
    published = PublishedApplication(published.release, ApplicationBuild.model_validate(build_raw))
    candidate_raw = candidate().model_dump(by_alias=True)
    generated_components = candidate_raw["messages"][1]["updateComponents"]["components"]
    generated_components[0]["children"].extend(
        ["local_button", "local_label", "new_local", "new_label"]
    )
    generated_components.extend(
        [
            {
                "id": "local_button",
                "component": "Button",
                "child": "local_label",
                "action": local_action,
                "checks": [check],
            },
            {"id": "local_label", "component": "Text", "text": "Local"},
            {
                "id": "new_local",
                "component": "Button",
                "child": "new_label",
                "action": local_action,
                "checks": [check],
            },
            {"id": "new_label", "component": "Text", "text": "New local"},
        ]
    )
    membership = {**MEMBERSHIP, "Button": "A2UI_OFFICIAL"}
    validate_candidate(published, membership, GeneratedCandidate.model_validate(candidate_raw))
    candidate_raw["messages"][1]["updateComponents"]["components"][5]["checks"][0]["condition"][
        "args"
    ]["value"] = "other"
    with pytest.raises(A2uiError, match="A2UI_GENERATION_AUTHORITY_FORBIDDEN"):
        validate_candidate(published, membership, GeneratedCandidate.model_validate(candidate_raw))
    candidate_raw["messages"][1]["updateComponents"]["components"][5]["checks"][0]["condition"][
        "args"
    ]["value"] = {"path": "/title"}
    del candidate_raw["messages"][1]["updateComponents"]["components"][3]["checks"]
    with pytest.raises(A2uiError, match="A2UI_GENERATION_AUTHORITY_FORBIDDEN"):
        validate_candidate(published, membership, GeneratedCandidate.model_validate(candidate_raw))


def test_component_input_target_must_remain_present() -> None:
    published = source()
    build_raw = published.build.model_dump(by_alias=True)
    build_raw["initialMessages"][1]["updateComponents"]["components"][0]["justify"] = "start"
    build_raw["inputBindings"] = (
        *build_raw["inputBindings"],
        {
            "targetMessageIndex": 1,
            "targetPath": "/updateComponents/components/0/justify",
            "source": "CONSTANT",
            "required": True,
            "constantValue": "start",
        },
    )
    published = PublishedApplication(published.release, ApplicationBuild.model_validate(build_raw))
    candidate_raw = candidate().model_dump(by_alias=True)
    root = candidate_raw["messages"][1]["updateComponents"]["components"][0]
    root["justify"] = "start"
    validate_candidate(published, MEMBERSHIP, GeneratedCandidate.model_validate(candidate_raw))
    del root["justify"]
    with pytest.raises(A2uiError, match="A2UI_GENERATION_INPUT_TARGET_INVALID"):
        validate_candidate(published, MEMBERSHIP, GeneratedCandidate.model_validate(candidate_raw))


def test_relative_path_stays_in_its_published_list_template() -> None:
    published = source()
    build_raw = published.build.model_dump(by_alias=True)
    build_raw["initialMessages"][1]["updateComponents"]["components"] = [
        {"id": "root", "component": "Column", "children": ["listA", "listB"]},
        {"id": "listA", "component": "List", "children": {"componentId": "cardA", "path": "/a"}},
        {"id": "cardA", "component": "Column", "children": ["claimText"]},
        {"id": "claimText", "component": "Text", "text": {"path": "claim"}},
        {"id": "listB", "component": "List", "children": {"componentId": "cardB", "path": "/b"}},
        {"id": "cardB", "component": "Column", "children": ["other"]},
        {"id": "other", "component": "Text", "text": "Other"},
    ]
    published = PublishedApplication(published.release, ApplicationBuild.model_validate(build_raw))
    membership = {**MEMBERSHIP, "List": "A2UI_OFFICIAL"}
    policy = contract(published, membership)
    assert policy.allowed_data_paths == ("/a", "/b")
    assert len(policy.relative_data_bindings) == 1
    binding = policy.relative_data_bindings[0]
    assert (binding.source_component_id, binding.path, binding.property_path) == (
        "claimText",
        "claim",
        "/text",
    )
    assert binding.template_scopes[0].template_component_id == "listA"
    candidate_raw = {
        "messages": [
            deepcopy(message)
            for message in published.build.initial_messages
            if "updateDataModel" not in message
        ],
        "actionPlacements": [],
    }
    validate_candidate(published, membership, GeneratedCandidate.model_validate(candidate_raw))
    components = candidate_raw["messages"][1]["updateComponents"]["components"]
    components.append({"id": "extra", "component": "Text", "text": {"path": "claim"}})
    components[2]["children"] = ["claimText", "extra"]
    validate_candidate(published, membership, GeneratedCandidate.model_validate(candidate_raw))
    components[2]["children"] = ["other", "extra"]
    components[5]["children"] = ["claimText"]
    with pytest.raises(A2uiError, match="A2UI_GENERATION_DATA_PATH_NOT_ALLOWED"):
        validate_candidate(published, membership, GeneratedCandidate.model_validate(candidate_raw))


@pytest.mark.parametrize(
    "mutation,code",
    [
        (
            lambda raw: raw["messages"][1]["updateComponents"]["components"][2].update(
                {"component": "Unknown"}
            ),
            "A2UI_GENERATION_COMPONENT_NOT_ALLOWED",
        ),
        (
            lambda raw: raw["messages"][1]["updateComponents"]["components"][0].update(
                {"children": ["root", "title", "new"]}
            ),
            "A2UI_GENERATION_TREE_INVALID",
        ),
        (
            lambda raw: raw["messages"][1]["updateComponents"]["components"][2].update(
                {"text": {"path": "/private"}}
            ),
            "A2UI_GENERATION_DATA_PATH_NOT_ALLOWED",
        ),
    ],
)
def test_candidate_boundary_rejects_invalid_layout(
    mutation: Callable[[JsonObject], None], code: str
) -> None:
    raw = deepcopy(candidate().model_dump(by_alias=True))
    mutation(raw)
    with pytest.raises(A2uiError) as error:
        validate_candidate(source(), MEMBERSHIP, GeneratedCandidate.model_validate(raw))
    assert error.value.code == code


def test_definition_digest_binds_scope_and_owner() -> None:
    context = TrustedContext(7, Environment.PRT, "request", "PC")
    scope = GenerationScope(conversationId="conversation")
    artifact = definition("demo.app", candidate(), scope, context)
    verify_definition(artifact, scope, context)
    with pytest.raises(A2uiError, match="A2UI_GENERATED_CARD_SCOPE_MISMATCH"):
        verify_definition(artifact, GenerationScope(conversationId="other"), context)
