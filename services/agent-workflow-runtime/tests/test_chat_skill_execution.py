"""Focused clean-room checks for bounded Skill execution in ordinary Chat."""

import asyncio
from collections.abc import AsyncIterator, Iterator
import hashlib
import json
from types import SimpleNamespace
import unittest

import httpx2
from langchain.agents.middleware import ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import tracing_context
from pydantic import Field, SecretStr

from skill_registry.ports import MaterialPort, SkillMaterial
from skill_registry.resources import PackageEntry, PackageEntryDescriptor
from skill_registry.use_skill import TrustedResolutionEvidence
from skillweave_contracts import TrustedContext

from agent_workflow_runtime.ability_execution import OperationSpec
from agent_workflow_runtime.business import (
    BusinessRegistry,
    parse_business_call_ref,
    schema_validator,
)
from agent_workflow_runtime.chat.assets import ChatAssets
from agent_workflow_runtime.chat.events import DONE, ERROR, ListEmitter
from agent_workflow_runtime.chat.loop import (
    ChatLoop,
    ChatLoopError,
    _ChatSkillToolAdmission,
)
from agent_workflow_runtime.chat.tools import (
    QuerySkillDependenciesModelArgs,
    RenderModelArgs,
    build_chat_tools,
)
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.models import ActionRejected


OWNER = TrustedContext(1009, "PRT")
SKILL_KEY = "demo/chat-skill"
CALCULATE_KEY = "demo.calculate"
CONFIRM_KEY = "demo.confirm"
DISPLAY_KEY = "demo.display"
CHOICE_KEY = "demo.choice"


class _DeepSeekWire(httpx2.SyncByteStream, httpx2.AsyncByteStream):
    def __init__(self, records: list[dict[str, object]]) -> None:
        self._parts = [
            ("data: " + json.dumps(record) + "\n\n").encode()
            for record in records
        ]
        self._parts.append(b"data: [DONE]\n\n")

    def __iter__(self) -> Iterator[bytes]:
        yield from self._parts

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for part in self._parts:
            yield part

    def close(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


def _deepseek_stream(
    *,
    content: str = "",
    tool_name: str | None = None,
    arguments: dict[str, object] | None = None,
    call_id: str = "call-fixture",
) -> list[dict[str, object]]:
    def chunk(
        delta: dict[str, object] | None = None,
        finish_reason: str | None = None,
        usage: dict[str, int] | None = None,
    ) -> dict[str, object]:
        return {
            "id": "fixture-response",
            "object": "chat.completion.chunk",
            "created": 7,
            "model": "deepseek-v4-pro",
            "choices": [] if delta is None else [{
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }],
            "usage": usage,
        }

    delta: dict[str, object] = {
        "role": "assistant",
        "content": content,
        "reasoning_content": "fixture reasoning",
    }
    if tool_name is not None:
        delta["tool_calls"] = [{
            "index": 0,
            "id": call_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(arguments or {}),
            },
        }]
    finish = "tool_calls" if tool_name is not None else "stop"
    return [
        chunk(delta),
        chunk({}, finish),
        chunk(usage={
            "prompt_tokens": 2,
            "completion_tokens": 3,
            "total_tokens": 5,
        }),
    ]


def _digest(content):
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _entry():
    content = b"Use only the registered calculate and Application tools."
    return PackageEntry(
        descriptor=PackageEntryDescriptor(
            handle_id="skill-instructions",
            logical_path="SKILL.md",
            media_type="text/markdown",
            declared_byte_size=len(content),
            declared_content_digest=_digest(content),
        ),
        content=content,
    )


def _ability(key, *, version="v1"):
    action = key == CONFIRM_KEY
    properties = (
        {"optionId": {"type": "string"}, "confirmed": {"type": "boolean"}}
        if action
        else {"value": {"type": "integer"}}
    )
    output = (
        {"confirmed": {"type": "boolean"}}
        if action
        else {"doubled": {"type": "integer"}}
    )
    policy = (
        {
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
            "policyRef": "confirmed",
            "operator": "JSON_POINTER_EQUALS",
            "jsonPointer": "/confirmed",
            "expectedLiteral": True,
        }
        if action
        else {
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
            "policyRef": "valid",
            "operator": "SCHEMA_VALID",
        }
    )
    definition = {
        "credentialRequirements": [],
        "inputBindings": [
            {
                "source": "MODEL_ARGUMENT",
                "sourcePath": "/" + name,
                "targetPath": "/" + name,
            }
            for name in properties
        ],
        "resolvedInputSchema": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
        "defaultSuccessPolicyRef": policy["policyRef"],
        "resultInterpretationPolicies": [policy],
    }
    return SimpleNamespace(
        asset_id="confirm" if action else "calculate",
        version_id=version,
        operation_ref="confirm" if action else "calculate",
        publication_metadata=SimpleNamespace(ability_key=key),
        definition=definition,
    )


def _application(key):
    interactive = key == CHOICE_KEY
    properties = (
        {
            "prompt": {"type": "string"},
            "options": {"type": "array"},
        }
        if interactive
        else {"text": {"type": "string"}}
    )
    return {
        "description": (
            "Let the user choose one option."
            if interactive
            else "Show one saved result."
        ),
        "asset": {
            "applicationKey": key,
            "protocolProfileRef": "a2flow.mvp08.v1",
            "componentCatalogRef": "demo.basic",
        },
        "renderPolicy": {
            "tool": "render_application",
            "interactionMode": "INTERACTIVE" if interactive else "DISPLAY_ONLY",
            "requiresPause": interactive,
        },
        "actionPolicies": (
            [
                {
                    "actionName": "confirm",
                    "abilityReleaseRef": CONFIRM_KEY + "@v1",
                    "successPolicyRef": "confirmed",
                    "completeInteractionOnSuccess": True,
                }
            ]
            if interactive
            else []
        ),
        "surfaceTemplate": {
            "rootId": "root",
            "components": [{"id": "root", "component": "Text"}],
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


class Reader(MaterialPort):
    def __init__(self):
        self.ability_version = "v1"
        self.calls = []

    def closure(self):
        return (
            ("ABILITY:calculate", self.ability_version),
            ("ABILITY:confirm", "v1"),
            ("APPLICATION:choice", "v1"),
            ("APPLICATION:display", "v1"),
            ("COMPONENT:basic", "v1"),
            ("SKILL:chat-skill", "v1"),
        )

    def resolve_asset(self, kind, key, context):
        if kind != "SKILL" or key != SKILL_KEY:
            raise AssertionError((kind, key))
        return {
            "kind": "SKILL",
            "key": SKILL_KEY,
            "assetId": "chat-skill",
            "versionId": "v1",
            "definition": {
                "requiredToolNames": ["execute_ability", "render_application"],
            },
            "dependencies": [
                {"kind": "ABILITY", "key": CALCULATE_KEY},
                {"kind": "APPLICATION", "key": DISPLAY_KEY},
                {"kind": "APPLICATION", "key": CHOICE_KEY},
            ],
            "recordedVersions": self.closure(),
        }

    def load_skill(self, skill_key, trusted_context):
        self.calls.append((skill_key, trusted_context))
        return SkillMaterial(
            instruction_entry=_entry(),
            resource_entries=(),
            required_tool_names=("execute_ability", "render_application"),
            resolution_evidence=TrustedResolutionEvidence(
                skill_key=SKILL_KEY,
                asset_id="chat-skill",
                version_id="v1",
                content_digest=_digest(b"skill"),
                environment="PRT",
                selection="PRT_CURRENT",
                evidence_ref="asset:chat-skill",
            ),
        )

    def resolve_ability(self, key, context):
        if key == CALCULATE_KEY:
            return _ability(key, version=self.ability_version)
        if key == CONFIRM_KEY:
            return _ability(key)
        raise AssertionError(key)

    def resolve_application(self, key, context):
        if key not in {DISPLAY_KEY, CHOICE_KEY}:
            raise AssertionError(key)
        asset_id = "display" if key == DISPLAY_KEY else "choice"
        versions = [("APPLICATION:" + asset_id, "v1"), ("COMPONENT:basic", "v1")]
        if key == CHOICE_KEY:
            versions.append(("ABILITY:confirm", "v1"))
        return {
            "application": _application(key),
            "resolvedVersion": {
                "asset": {"assetId": asset_id},
                "versionId": "v1",
            },
            "recordedVersions": tuple(versions),
        }


def _application_validator(value):
    return value in (_application(DISPLAY_KEY), _application(CHOICE_KEY))


def _data_validator(application, value):
    if application["asset"]["applicationKey"] == DISPLAY_KEY:
        return type(value) is dict and set(value) == {"text"} and type(value["text"]) is str
    return (
        type(value) is dict
        and set(value) == {"prompt", "options"}
        and type(value["prompt"]) is str
        and type(value["options"]) is list
        and len(value["options"]) == 2
    )


class Sink:
    def __init__(self):
        self.calls = []

    def __call__(self, prepared, metadata):
        self.calls.append((prepared, metadata))
        return {
            "cardId": "card:" + metadata["toolCallId"],
            "applicationKey": prepared.application_key,
            "interactive": prepared.interactive,
        }


def _operations(*, reader=None, calls=None):
    calls = [] if calls is None else calls

    def validate_calculate(value):
        valid = type(value) is dict and set(value) == {"value"} and type(value["value"]) is int
        if valid and reader is not None:
            reader.ability_version = "v2"
        return valid

    return {
        "calculate": OperationSpec(
            lambda value, owner: calls.append((value, owner)) or {"doubled": value["value"] * 2},
            validate_calculate,
            lambda value: type(value) is dict and type(value.get("doubled")) is int,
            lambda definition: True,
            model_allowed=True,
        ),
        "confirm": OperationSpec(
            lambda value, owner: {"confirmed": True},
            lambda value: type(value) is dict,
            lambda value: type(value) is dict and value.get("confirmed") is True,
            lambda definition: True,
            action_allowed=True,
        ),
    }


def _assets(reader=None, operations=None, sink=None, control_request_id="chatctrl1"):
    reader = reader or Reader()
    sink = sink or Sink()
    return ChatAssets(
        reader,
        operations or _operations(),
        OWNER,
        "conv1",
        control_request_id,
        sink,
        _application_validator,
        _data_validator,
    ), reader, sink


class ScriptedModel(BaseChatModel):
    rounds: list
    tools: list = Field(default_factory=list)
    observed: list = Field(default_factory=list)
    bound_tool_sets: list[tuple[str, ...]] = Field(default_factory=list)

    @property
    def configuration(self):
        return SimpleNamespace(harness_profile_key="chat-skill-test")

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        self.tools = list(tools)
        self.bound_tool_sets.append(tuple(tool.name for tool in tools))
        return self

    def _generate(self, messages, **kwargs):
        raise AssertionError("Expected native streaming")

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.observed.append(list(messages))
        for chunk in self.rounds.pop(0):
            yield ChatGenerationChunk(message=chunk)


class Factory:
    def __init__(self, model):
        self.model = model

    def create(self, reference, owner):
        return self.model


class GateAssets:
    """Explicit ChatAssets test API for model-request admission changes."""

    def __init__(self) -> None:
        self.names: frozenset[str] = frozenset()
        self.attempts: list[str] = []

    def begin_turn(self) -> None:
        self.names = frozenset()

    def admitted_tool_names(self) -> frozenset[str]:
        return self.names

    def waiting_action(self) -> None:
        return None

    def validate_context(self, context: object) -> None:
        del context

    def admit_skill(self, skill_key: str) -> dict[str, object]:
        self.attempts.append(skill_key)
        if skill_key == "reject":
            raise ActionRejected("SKILL_NOT_FOUND")
        self.names = (
            frozenset({"execute_ability"})
            if skill_key == "execute-only"
            else frozenset({
                "execute_ability",
                "query_skill_dependencies",
                "render_application",
            })
        )
        return {
            "content": {"instructions": "fixture", "resources": []},
            "artifact": {"resolvedVersion": {"versionId": "v1"}},
        }

    def execute_ability(
        self, ability_key: str, arguments: dict[str, object],
    ) -> dict[str, object]:
        return {"abilityKey": ability_key, "output": dict(arguments)}

    def query_skill_dependencies(
        self, application_codes: list[str],
    ) -> dict[str, object]:
        return {"applications": [
            {
                "appCode": app_code,
                "description": "Fixture Application.",
                "usage": (
                    "Call render_application with this appCode and params that "
                    "satisfy paramsSchema."
                ),
                "paramsSchema": {"type": "object"},
            }
            for app_code in application_codes
        ]}

    def render_application(
        self,
        app_code: str,
        params: dict[str, object],
        tool_call_id: str,
    ) -> dict[str, object]:
        del params
        return {"cardId": "card:" + tool_call_id, "applicationKey": app_code}

    def render_observation(self, card_id: str) -> dict[str, object]:
        return {
            "cardId": card_id,
            "applicationKey": CHOICE_KEY,
            "arguments": {},
        }


def _call(index, call_id, name, arguments):
    return AIMessageChunk(
        content="",
        tool_call_chunks=[{
            "index": index,
            "id": call_id,
            "name": name,
            "args": json.dumps(arguments),
            "type": "tool_call_chunk",
        }],
    )


def _loop(rounds, assets, reader, emitter):
    model = ScriptedModel(rounds=rounds)
    loop = ChatLoop(
        model_factory=Factory(model),
        model_reference="deepseek-v4-flash",
        owner=OWNER,
        conversation_id="conv1",
        reader=reader,
        control_request_id="chatctrl1",
        emitter=emitter,
        chat_assets=assets,
    )
    return loop, model


class ChatAssetsTests(unittest.TestCase):
    def test_admitted_tool_names_are_empty_until_successful_admission(self) -> None:
        assets, _, _ = _assets()
        self.assertEqual(frozenset(), assets.admitted_tool_names())
        assets.admit_skill(SKILL_KEY)
        self.assertEqual(
            frozenset({
                "execute_ability",
                "query_skill_dependencies",
                "render_application",
            }),
            assets.admitted_tool_names(),
        )
        assets.begin_turn()
        self.assertEqual(frozenset(), assets.admitted_tool_names())

        class RejectingReader(Reader):
            def resolve_asset(self, kind, key, context):
                del kind, key, context
                raise ActionRejected("SKILL_NOT_FOUND")

        rejected, _, _ = _assets(RejectingReader())
        with self.assertRaisesRegex(ActionRejected, "SKILL_NOT_FOUND"):
            rejected.admit_skill(SKILL_KEY)
        self.assertEqual(frozenset(), rejected.admitted_tool_names())

    def test_query_skill_dependencies_is_bound_and_returns_model_inputs(self):
        assets, reader, _ = _assets()
        with self.assertRaisesRegex(ActionRejected, "SKILL_NOT_ADMITTED"):
            assets.query_skill_dependencies([DISPLAY_KEY])
        assets.admit_skill(SKILL_KEY)

        value = assets.query_skill_dependencies([DISPLAY_KEY, CHOICE_KEY])

        self.assertEqual(
            [DISPLAY_KEY, CHOICE_KEY],
            [item["appCode"] for item in value["applications"]],
        )
        self.assertEqual(
            {"appCode", "description", "usage", "paramsSchema"},
            set(value["applications"][0]),
        )
        self.assertEqual(
            ["text"], value["applications"][0]["paramsSchema"]["required"],
        )
        self.assertIn("render_application", value["applications"][0]["usage"])
        with self.assertRaisesRegex(ActionRejected, "APPLICATION_NOT_ALLOWED"):
            assets.query_skill_dependencies(["demo.unbound"])
        with self.assertRaisesRegex(ActionRejected, "ARGUMENT_INVALID"):
            assets.query_skill_dependencies([DISPLAY_KEY, DISPLAY_KEY])

        class EmptyDescriptionReader(Reader):
            def resolve_application(self, key, context):
                resolved = super().resolve_application(key, context)
                resolved["application"]["description"] = ""
                return resolved

        empty_assets, _, _ = _assets(EmptyDescriptionReader())
        empty_assets.admit_skill(SKILL_KEY)
        self.assertEqual(
            "",
            empty_assets.query_skill_dependencies([DISPLAY_KEY])[
                "applications"
            ][0]["description"],
        )

        reader.ability_version = "v2"
        with self.assertRaisesRegex(ActionRejected, "RESET_REQUIRED"):
            assets.query_skill_dependencies([DISPLAY_KEY])

    def test_model_schemas_use_only_new_application_argument_names(self):
        self.assertEqual(
            {
                "a2uiApplicationCodeList": [DISPLAY_KEY],
            },
            QuerySkillDependenciesModelArgs.model_validate({
                "a2uiApplicationCodeList": [DISPLAY_KEY],
            }).model_dump(),
        )
        with self.assertRaises(ValueError):
            QuerySkillDependenciesModelArgs.model_validate({
                "a2uiApplicationCodeList": [DISPLAY_KEY, DISPLAY_KEY],
            })
        self.assertEqual(
            {"appCode": DISPLAY_KEY, "params": {"text": "saved"}},
            RenderModelArgs.model_validate({
                "appCode": DISPLAY_KEY,
                "params": {"text": "saved"},
            }).model_dump(),
        )
        with self.assertRaises(ValueError):
            RenderModelArgs.model_validate({
                "applicationKey": DISPLAY_KEY,
                "data": {"text": "saved"},
            })

    def test_bound_ability_rechecks_version_immediately_before_dispatch(self):
        reader = Reader()
        calls = []
        assets, _, _ = _assets(reader, _operations(calls=calls))
        assets.admit_skill(SKILL_KEY)
        result = assets.execute_ability(CALCULATE_KEY, {"value": 2})
        self.assertEqual({"doubled": 4}, result["output"])
        self.assertEqual(1, len(calls))
        with self.assertRaisesRegex(ActionRejected, "ABILITY_NOT_ALLOWED"):
            assets.execute_ability("demo.unbound", {"value": 2})
        with self.assertRaisesRegex(ActionRejected, "APPLICATION_NOT_ALLOWED"):
            assets.render_application("demo.unbound", {}, "unbound-render")

        reader = Reader()
        calls = []
        assets, _, _ = _assets(
            reader, _operations(reader=reader, calls=calls),
        )
        assets.admit_skill(SKILL_KEY)
        with self.assertRaisesRegex(ActionRejected, "RESET_REQUIRED"):
            assets.execute_ability(CALCULATE_KEY, {"value": 2})
        self.assertEqual([], calls)

    def test_render_metadata_and_action_binding_are_server_resolved(self):
        assets, _, sink = _assets()
        assets.admit_skill(SKILL_KEY)
        saved = assets.render_application(
            CHOICE_KEY,
            {
                "prompt": "Choose",
                "options": [
                    {"label": "A", "value": "a"},
                    {"label": "B", "value": "b"},
                ],
            },
            "tool-9",
        )
        self.assertEqual("card:tool-9", saved["cardId"])
        prepared, metadata = sink.calls[0]
        self.assertTrue(prepared.interactive)
        self.assertEqual(SKILL_KEY, metadata["skillKey"])
        self.assertEqual("conv1", metadata["conversationId"])
        self.assertEqual("chatctrl1", metadata["controlRequestId"])
        self.assertEqual("tool-9", metadata["toolCallId"])
        self.assertEqual(1009, metadata["owner"]["userId"])
        self.assertEqual(CONFIRM_KEY, metadata["actionBindings"][0]["abilityKey"])
        resolved, policy, ability, spec = assets.action_binding(CHOICE_KEY, "confirm")
        self.assertEqual("v1", resolved["resolvedVersion"]["versionId"])
        self.assertTrue(policy["completeInteractionOnSuccess"])
        self.assertEqual(CONFIRM_KEY, ability.publication_metadata.ability_key)
        self.assertTrue(spec.action_allowed)
        assets.check_versions(metadata["recordedVersions"])
        with self.assertRaisesRegex(ActionRejected, "RESET_REQUIRED"):
            assets.check_versions([["SKILL:chat-skill", "old"]])


class SeededChatAssetsIntegrationTests(unittest.TestCase):
    def test_real_seed_bundle_admits_skill_ability_and_application(self):
        from a2flow_asset_store import AssetReader
        from a2flow_asset_store.records import canonical
        from activity_planning_demo import (
            APPLICATION_KEY,
            BUDGET_KEY,
            CONFIRM_KEY,
            ability_definition,
            application_data_validator,
            application_validator,
            bundle_validator,
        )
        from activity_planning_demo.bundle import NAMESPACE, make_bundle
        from activity_planning_demo.service import ActivityPlanningService

        class BundleRepository:
            environment = "PRT"

            def __init__(self):
                self.validator = bundle_validator()
                self.bundle = self.validator.validate(
                    make_bundle("PRT"),
                    expected_namespace=NAMESPACE,
                    expected_environment="PRT",
                )

            def read(self, namespace):
                if namespace != NAMESPACE:
                    raise AssertionError(namespace)
                return self.bundle

        registry = BusinessRegistry({"activity-planning": ActivityPlanningService()})
        operations = {}
        for key in (BUDGET_KEY, CONFIRM_KEY):
            definition = ability_definition(key)
            service, method = parse_business_call_ref(
                definition["adapterOperationRef"],
            )
            expected = canonical(definition)
            operations[definition["adapterOperationRef"]] = OperationSpec(
                registry.dispatcher(service, method),
                schema_validator(definition["resolvedInputSchema"]),
                schema_validator(definition["outputSchema"]),
                lambda value, expected=expected: canonical(value) == expected,
                model_allowed=key == BUDGET_KEY,
                action_allowed=key == CONFIRM_KEY,
            )
        sink = Sink()
        assets = ChatAssets(
            AssetReader(BundleRepository(), NAMESPACE),
            operations,
            OWNER,
            "conv1",
            "chatctrl1",
            sink,
            application_validator,
            application_data_validator,
        )
        assets.admit_skill("activity-planning/plan")
        budget = assets.execute_ability(
            BUDGET_KEY, {"participants": 3, "budgetMinor": 1000},
        )
        self.assertEqual(333, budget["output"]["perPersonMinor"])
        card = assets.render_application(
            APPLICATION_KEY,
            {
                "prompt": "Choose",
                "options": [
                    {"label": "A", "value": "a"},
                    {"label": "B", "value": "b"},
                ],
            },
            "seeded-tool",
        )
        self.assertEqual("card:seeded-tool", card["cardId"])
        self.assertTrue(sink.calls[0][0].interactive)


class ChatLoopSkillTests(unittest.TestCase):
    def test_reused_assets_require_readmission_on_each_turn(self) -> None:
        calls: list[tuple[dict[str, object], object]] = []
        assets, reader, _ = _assets(operations=_operations(calls=calls))
        emitter = ListEmitter()
        loop, model = _loop([
            [_call(0, "skill-1", "use_skill", {"skillKey": SKILL_KEY})],
            [AIMessageChunk(content="Skill context ready")],
            [_call(0, "skill-2", "use_skill", {"skillKey": SKILL_KEY})],
            [_call(0, "ability-2", "execute_ability", {
                "abilityKey": CALCULATE_KEY,
                "arguments": {"value": 3},
            })],
            [AIMessageChunk(content="Calculated")],
        ], assets, reader, emitter)

        self.assertEqual("Skill context ready", loop.turn("Prepare"))
        self.assertEqual("Calculated", loop.turn("Continue"))
        self.assertEqual(
            [
                {"use_skill", "propose_workflow_run"},
                {
                    "use_skill", "propose_workflow_run",
                    "execute_ability", "query_skill_dependencies",
                    "render_application",
                },
                {"use_skill", "propose_workflow_run"},
                {
                    "use_skill", "propose_workflow_run",
                    "execute_ability", "query_skill_dependencies",
                    "render_application",
                },
                {
                    "use_skill", "propose_workflow_run",
                    "execute_ability", "query_skill_dependencies",
                    "render_application",
                },
            ],
            [set(names) for names in model.bound_tool_sets],
        )
        self.assertEqual(2, len(reader.calls))
        self.assertEqual([({"value": 3}, OWNER)], calls)

    def test_fresh_assets_on_checkpointed_second_turn_require_readmission(self) -> None:
        reader = Reader()
        calls = []
        saver = InMemorySaver()
        first_assets, _, _ = _assets(
            reader, _operations(calls=calls), control_request_id="turn-1",
        )
        first_model = ScriptedModel(rounds=[
            [_call(0, "skill-1", "use_skill", {"skillKey": SKILL_KEY})],
            [AIMessageChunk(content="Skill context ready")],
        ])
        first = ChatLoop(
            model_factory=Factory(first_model),
            model_reference="deepseek-v4-flash",
            owner=OWNER,
            conversation_id="conv1",
            reader=reader,
            control_request_id="turn-1",
            chat_assets=first_assets,
            checkpointer=saver,
            thread_id="shared-thread",
        )
        self.assertEqual("Skill context ready", first.turn("Prepare"))

        second_assets, _, _ = _assets(
            reader, _operations(calls=calls), control_request_id="turn-2",
        )
        second_model = ScriptedModel(rounds=[
            [_call(0, "skill-2", "use_skill", {"skillKey": SKILL_KEY})],
            [_call(0, "ability-2", "execute_ability", {
                "abilityKey": CALCULATE_KEY,
                "arguments": {"value": 3},
            })],
            [AIMessageChunk(content="Calculated")],
        ])
        second = ChatLoop(
            model_factory=Factory(second_model),
            model_reference="deepseek-v4-flash",
            owner=OWNER,
            conversation_id="conv1",
            reader=reader,
            control_request_id="turn-2",
            chat_assets=second_assets,
            checkpointer=saver,
            thread_id="shared-thread",
        )
        self.assertEqual("Calculated", second.turn("Continue"))
        self.assertTrue(any(
            isinstance(message, ToolMessage) and message.name == "use_skill"
            for message in second_model.observed[0]
        ), "the prior turn's use_skill result must remain history only")
        self.assertEqual(
            [
                {"use_skill", "propose_workflow_run"},
                {
                    "use_skill", "propose_workflow_run",
                    "execute_ability", "query_skill_dependencies",
                    "render_application",
                },
                {
                    "use_skill", "propose_workflow_run",
                    "execute_ability", "query_skill_dependencies",
                    "render_application",
                },
            ],
            [set(names) for names in second_model.bound_tool_sets],
        )
        self.assertEqual(2, len(reader.calls))
        self.assertEqual([({"value": 3}, OWNER)], calls)

    def test_unadmitted_plain_chat_can_finish_without_use_skill(self) -> None:
        assets, reader, _ = _assets()
        emitter = ListEmitter()
        loop, model = _loop(
            [[AIMessageChunk(content="Hello")]], assets, reader, emitter,
        )
        self.assertEqual("Hello", loop.turn("Hello"))
        self.assertEqual(
            [{"use_skill", "propose_workflow_run"}],
            [set(names) for names in model.bound_tool_sets],
        )
        self.assertEqual(frozenset(), assets.admitted_tool_names())

    def test_real_deepseek_wire_rejects_hidden_tool_then_allows_use_skill(self) -> None:
        responses = [
            _deepseek_stream(
                tool_name="execute_ability",
                arguments={
                    "abilityKey": CALCULATE_KEY,
                    "arguments": {"value": 99},
                },
                call_id="hidden-ability",
            ),
            _deepseek_stream(
                tool_name="use_skill",
                arguments={"skillKey": SKILL_KEY},
                call_id="admit-skill",
            ),
            _deepseek_stream(
                tool_name="execute_ability",
                arguments={
                    "abilityKey": CALCULATE_KEY,
                    "arguments": {"value": 3},
                },
                call_id="allowed-ability",
            ),
            _deepseek_stream(content="Calculated"),
        ]
        requests: list[dict[str, object]] = []

        def transport(request: httpx2.Request) -> httpx2.Response:
            self.assertEqual("api.deepseek.com", request.url.host)
            self.assertEqual("/chat/completions", request.url.path)
            requests.append(json.loads(request.content))
            return httpx2.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_DeepSeekWire(responses[len(requests) - 1]),
            )

        http_client = httpx2.Client(transport=httpx2.MockTransport(transport))
        http_async_client = httpx2.AsyncClient(
            transport=httpx2.MockTransport(transport),
        )
        self.addCleanup(http_client.close)
        self.addCleanup(lambda: asyncio.run(http_async_client.aclose()))
        factory = DeepSeekModelFactory(
            lambda *args: {
                "model_id": "deepseek-v4-pro",
                "credential_ref": "synthetic",
            },
            lambda *args: SecretStr("synthetic-offline-key"),
            http_client=http_client,
            http_async_client=http_async_client,
        )
        calls: list[tuple[dict[str, object], TrustedContext]] = []
        assets, reader, _ = _assets(operations=_operations(calls=calls))
        loop = ChatLoop(
            model_factory=factory,
            model_reference="deepseek-v4-pro",
            owner=OWNER,
            conversation_id="conv1",
            reader=reader,
            control_request_id="chatctrl1",
            chat_assets=assets,
        )

        with tracing_context(enabled=False):
            self.assertEqual("Calculated", loop.turn("Use the Skill"))

        wire_tools = [
            {tool["function"]["name"] for tool in request["tools"]}
            for request in requests
        ]
        self.assertEqual(
            [
                {"use_skill", "propose_workflow_run"},
                {"use_skill", "propose_workflow_run"},
                {
                    "use_skill", "propose_workflow_run",
                    "execute_ability", "query_skill_dependencies",
                    "render_application",
                },
                {
                    "use_skill", "propose_workflow_run",
                    "execute_ability", "query_skill_dependencies",
                    "render_application",
                },
            ],
            wire_tools,
        )
        admitted_schemas = {
            tool["function"]["name"]: tool["function"]["parameters"]
            for tool in requests[2]["tools"]
        }
        self.assertEqual(
            {"a2uiApplicationCodeList"},
            set(admitted_schemas["query_skill_dependencies"]["properties"]),
        )
        application_codes_schema = admitted_schemas[
            "query_skill_dependencies"
        ]["properties"]["a2uiApplicationCodeList"]
        self.assertEqual(1, application_codes_schema["minItems"])
        self.assertEqual(20, application_codes_schema["maxItems"])
        self.assertEqual(
            {"appCode", "params"},
            set(admitted_schemas["render_application"]["properties"]),
        )
        self.assertIn("call use_skill", requests[1]["messages"][-1]["content"])
        self.assertEqual([({"value": 3}, OWNER)], calls)
        self.assertEqual(1, len(reader.calls))

    def test_failed_admission_does_not_open_execution_tools(self) -> None:
        assets = GateAssets()
        reader = Reader()
        emitter = ListEmitter()
        loop, model = _loop([
            [_call(0, "reject-1", "use_skill", {"skillKey": "reject"})],
        ], assets, reader, emitter)
        with self.assertRaisesRegex(ChatLoopError, "MODEL_STREAM_FAILED"):
            loop.turn("Load missing Skill")
        self.assertEqual(
            [{"use_skill", "propose_workflow_run"}],
            [set(names) for names in model.bound_tool_sets],
        )
        self.assertEqual(frozenset(), assets.admitted_tool_names())

    def test_successful_skill_switch_replaces_visible_execution_tools(self) -> None:
        assets = GateAssets()
        reader = Reader()
        emitter = ListEmitter()
        loop, model = _loop([
            [_call(0, "full-1", "use_skill", {"skillKey": "full"})],
            [_call(0, "narrow-1", "use_skill", {"skillKey": "execute-only"})],
            [AIMessageChunk(content="Switched")],
        ], assets, reader, emitter)
        self.assertEqual("Switched", loop.turn("Switch Skills"))
        self.assertEqual(
            [
                {"use_skill", "propose_workflow_run"},
                {
                    "use_skill", "propose_workflow_run",
                    "execute_ability", "query_skill_dependencies",
                    "render_application",
                },
                {"use_skill", "propose_workflow_run", "execute_ability"},
            ],
            [set(names) for names in model.bound_tool_sets],
        )

    def test_display_only_card_continues_to_model_completion(self):
        assets, reader, _ = _assets()
        emitter = ListEmitter()
        rounds = [
            [_call(0, "skill-1", "use_skill", {"skillKey": SKILL_KEY})],
            [_call(0, "query-1", "query_skill_dependencies", {
                "a2uiApplicationCodeList": [DISPLAY_KEY],
            })],
            [_call(0, "display-1", "render_application", {
                "appCode": DISPLAY_KEY,
                "params": {"text": "Saved result"},
            })],
            [AIMessageChunk(content="Final answer")],
        ]
        loop, model = _loop(rounds, assets, reader, emitter)
        self.assertEqual("Final answer", loop.turn("Use the demo Skill"))
        self.assertEqual(4, len(model.observed))
        query_result = next(
            message for message in model.observed[2]
            if isinstance(message, ToolMessage)
            and message.name == "query_skill_dependencies"
        )
        query_content = json.loads(query_result.content)
        self.assertEqual(
            {"appCode", "description", "usage", "paramsSchema"},
            set(query_content["applications"][0]),
        )
        self.assertEqual(DISPLAY_KEY, query_content["applications"][0]["appCode"])
        render_result = next(
            message for message in model.observed[3]
            if isinstance(message, ToolMessage)
            and message.name == "render_application"
        )
        self.assertIn("renderedApplication", render_result.content)
        self.assertIn("Saved result", render_result.content)
        self.assertIn("does not assert", render_result.content)
        self.assertNotIn("components", render_result.content)
        self.assertNotIn("protocolProfile", render_result.content)
        kinds = [kind for kind, _ in emitter.events]
        self.assertIn("application_rendered", kinds)
        self.assertNotIn("waiting_action", kinds)
        self.assertEqual(DONE, kinds[-1])

    def test_interactive_card_stops_before_another_model_call(self):
        reader = Reader()
        calls = []
        assets, _, _ = _assets(reader, _operations(calls=calls))
        emitter = ListEmitter()
        rounds = [
            [_call(0, "skill-1", "use_skill", {"skillKey": SKILL_KEY})],
            [_call(0, "ability-1", "execute_ability", {
                "abilityKey": CALCULATE_KEY,
                "arguments": {"value": 2},
            })],
            [_call(0, "choice-1", "render_application", {
                "appCode": CHOICE_KEY,
                "params": {
                    "prompt": "Choose",
                    "options": [
                        {"label": "A", "value": "a"},
                        {"label": "B", "value": "b"},
                    ],
                },
            })],
            [AIMessageChunk(content="must not run")],
        ]
        loop, model = _loop(rounds, assets, reader, emitter)
        self.assertIsNone(loop.turn("Use the interactive Skill"))
        self.assertEqual(3, len(model.observed))
        self.assertEqual(1, len(calls))
        self.assertEqual({"value": 2}, calls[0][0])
        kinds = [kind for kind, _ in emitter.events]
        self.assertIn("application_rendered", kinds)
        self.assertEqual("waiting_action", kinds[-1])
        self.assertNotIn(DONE, kinds)
        self.assertNotIn(ERROR, kinds)
        self.assertEqual({"cardId": "card:choice-1"}, emitter.events[-1][1])

    def test_render_batch_rejects_sibling_ability_before_dispatch(self):
        reader = Reader()
        calls = []
        assets, _, _ = _assets(reader, _operations(calls=calls))
        emitter = ListEmitter()
        render_arguments = {
            "appCode": CHOICE_KEY,
            "params": {
                "prompt": "Choose",
                "options": [
                    {"label": "A", "value": "a"},
                    {"label": "B", "value": "b"},
                ],
            },
        }
        mixed = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {
                    "index": 0,
                    "id": "choice-1",
                    "name": "render_application",
                    "args": json.dumps(render_arguments),
                    "type": "tool_call_chunk",
                },
                {
                    "index": 1,
                    "id": "ability-1",
                    "name": "execute_ability",
                    "args": json.dumps({
                        "abilityKey": CALCULATE_KEY,
                        "arguments": {"value": 2},
                    }),
                    "type": "tool_call_chunk",
                },
            ],
        )
        rounds = [
            [_call(0, "skill-1", "use_skill", {"skillKey": SKILL_KEY})],
            [mixed],
            [AIMessageChunk(content="must not run")],
        ]
        loop, model = _loop(rounds, assets, reader, emitter)
        self.assertIsNone(loop.turn("Render, but do not run a sibling operation"))
        self.assertEqual([], calls)
        self.assertEqual(2, len(model.observed))
        self.assertEqual("waiting_action", emitter.events[-1][0])

    def test_use_skill_batch_rejects_sibling_ability_before_dispatch(self):
        reader = Reader()
        calls = []
        assets, _, _ = _assets(reader, _operations(calls=calls))
        emitter = ListEmitter()
        mixed = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {
                    "index": 0,
                    "id": "skill-1",
                    "name": "use_skill",
                    "args": json.dumps({"skillKey": SKILL_KEY}),
                    "type": "tool_call_chunk",
                },
                {
                    "index": 1,
                    "id": "ability-1",
                    "name": "execute_ability",
                    "args": json.dumps({
                        "abilityKey": CALCULATE_KEY,
                        "arguments": {"value": 2},
                    }),
                    "type": "tool_call_chunk",
                },
            ],
        )
        rounds = [[mixed], [AIMessageChunk(content="Admission completed alone")]]
        loop, model = _loop(rounds, assets, reader, emitter)
        self.assertEqual("Admission completed alone", loop.turn("Use and execute"))
        self.assertEqual([], calls)
        self.assertEqual(1, len(reader.calls))
        self.assertEqual(2, len(model.observed))
        tool_messages = [message for message in loop.history if message.type == "tool"]
        self.assertEqual(["success", "error"], [message.status for message in tool_messages])

    def test_forged_runtime_identity_is_rejected_before_skill_admission(self):
        assets, reader, _ = _assets()
        emitter = ListEmitter()
        rounds = [
            [_call(0, "forged", "use_skill", {
                "skillKey": SKILL_KEY,
                "runtime": {"userId": 9999, "environment": "ONLINE"},
            })],
            [AIMessageChunk(content="Rejected")],
        ]
        loop, model = _loop(rounds, assets, reader, emitter)
        self.assertEqual("Rejected", loop.turn("Forge identity"))
        self.assertEqual([], reader.calls)
        self.assertEqual("error", loop.history[2].status)
        self.assertEqual(2, len(model.observed))


class ChatSkillToolAdmissionMiddlewareTests(unittest.TestCase):
    def test_sync_and_async_tool_boundaries_reject_only_unadmitted_skill_tools(
        self,
    ) -> None:
        assets = GateAssets()
        middleware = _ChatSkillToolAdmission(assets)
        hidden_ability = ToolCallRequest(
            tool_call={
                "name": "execute_ability",
                "args": {},
                "id": "hidden-ability",
                "type": "tool_call",
            },
            tool=None,
            state={},
            runtime=None,
        )
        sync_calls: list[str] = []

        def sync_handler(request: ToolCallRequest) -> ToolMessage:
            sync_calls.append(request.tool_call["name"])
            return ToolMessage(
                content="called",
                name=request.tool_call["name"],
                tool_call_id=request.tool_call["id"] or "",
            )

        rejected = middleware.wrap_tool_call(hidden_ability, sync_handler)
        self.assertIsInstance(rejected, ToolMessage)
        self.assertEqual("error", rejected.status)
        self.assertEqual(
            "Error: call use_skill in the current turn for a Skill that admits this tool.",
            rejected.content,
        )
        self.assertEqual([], sync_calls)

        assets.names = frozenset({"execute_ability"})
        allowed = middleware.wrap_tool_call(hidden_ability, sync_handler)
        self.assertEqual("called", allowed.content)
        self.assertEqual(["execute_ability"], sync_calls)

        def business_failure(request: ToolCallRequest) -> ToolMessage:
            del request
            raise ActionRejected("BUSINESS_FAILURE")

        with self.assertRaisesRegex(ActionRejected, "BUSINESS_FAILURE"):
            middleware.wrap_tool_call(hidden_ability, business_failure)

        assets.names = frozenset()
        hidden_render = ToolCallRequest(
            tool_call={
                "name": "render_application",
                "args": {},
                "id": "hidden-render",
                "type": "tool_call",
            },
            tool=None,
            state={},
            runtime=None,
        )
        async_calls: list[str] = []

        async def async_handler(request: ToolCallRequest) -> ToolMessage:
            async_calls.append(request.tool_call["name"])
            return ToolMessage(
                content="called",
                name=request.tool_call["name"],
                tool_call_id=request.tool_call["id"] or "",
            )

        async_rejected = asyncio.run(
            middleware.awrap_tool_call(hidden_render, async_handler),
        )
        self.assertIsInstance(async_rejected, ToolMessage)
        self.assertEqual("error", async_rejected.status)
        self.assertEqual([], async_calls)

    def test_sync_and_async_hooks_preserve_prompt_without_accumulation(self) -> None:
        assets = GateAssets()
        tools = list(build_chat_tools(
            reader=Reader(),
            trusted_context=OWNER,
            conversation_id="conv1",
            control_request_id="chatctrl1",
            chat_assets=assets,
        ))
        middleware = _ChatSkillToolAdmission(assets)
        request = ModelRequest(
            model=ScriptedModel(rounds=[]),
            messages=[],
            system_message=SystemMessage(content="base prompt"),
            tools=tools,
            runtime=None,
        )
        sync_requests = []

        def sync_handler(prepared):
            sync_requests.append(prepared)
            return ModelResponse(result=[AIMessage(content="sync")])

        middleware.wrap_model_call(request, sync_handler)
        self.assertEqual(
            {"use_skill", "propose_workflow_run"},
            {tool.name for tool in sync_requests[0].tools},
        )

        async_requests = []

        async def async_handler(prepared):
            async_requests.append(prepared)
            return ModelResponse(result=[AIMessage(content="async")])

        asyncio.run(middleware.awrap_model_call(sync_requests[0], async_handler))
        text = async_requests[0].system_message.text
        self.assertIn("base prompt", text)
        self.assertEqual(1, text.count("Skill admission is local to the current turn"))


if __name__ == "__main__":
    unittest.main()
