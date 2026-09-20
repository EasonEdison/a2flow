"""Focused clean-room checks for bounded Skill execution in ordinary Chat."""

import hashlib
import json
from types import SimpleNamespace
import unittest

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from pydantic import Field

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
from agent_workflow_runtime.chat.loop import ChatLoop
from agent_workflow_runtime.models import ActionRejected


OWNER = TrustedContext(1009, "PRT")
SKILL_KEY = "demo/chat-skill"
CALCULATE_KEY = "demo.calculate"
CONFIRM_KEY = "demo.confirm"
DISPLAY_KEY = "demo.display"
CHOICE_KEY = "demo.choice"


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
    return {
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
            "inputSchema": {"type": "object"},
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


def _assets(reader=None, operations=None, sink=None):
    reader = reader or Reader()
    sink = sink or Sink()
    return ChatAssets(
        reader,
        operations or _operations(),
        OWNER,
        "conv1",
        "chatctrl1",
        sink,
        _application_validator,
        _data_validator,
    ), reader, sink


class ScriptedModel(BaseChatModel):
    rounds: list
    tools: list = Field(default_factory=list)
    observed: list = Field(default_factory=list)

    @property
    def configuration(self):
        return SimpleNamespace(harness_profile_key="chat-skill-test")

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        self.tools = list(tools)
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
    def test_display_only_card_continues_to_model_completion(self):
        assets, reader, _ = _assets()
        emitter = ListEmitter()
        rounds = [
            [_call(0, "skill-1", "use_skill", {"skillKey": SKILL_KEY})],
            [_call(0, "display-1", "render_application", {
                "applicationKey": DISPLAY_KEY,
                "data": {"text": "Saved result"},
            })],
            [AIMessageChunk(content="Final answer")],
        ]
        loop, model = _loop(rounds, assets, reader, emitter)
        self.assertEqual("Final answer", loop.turn("Use the demo Skill"))
        self.assertEqual(3, len(model.observed))
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
                "applicationKey": CHOICE_KEY,
                "data": {
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
            "applicationKey": CHOICE_KEY,
            "data": {
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


if __name__ == "__main__":
    unittest.main()
