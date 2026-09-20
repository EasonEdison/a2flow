"""Engine-first three-Tool spine integration tests."""

import hashlib
import json
from pathlib import Path
import unittest

from langchain_core.messages import AIMessage, ToolMessage
from skill_registry import (
    MaterialPort,
    PackageEntry,
    PackageEntryDescriptor,
    SkillMaterial,
    TrustedResolutionEvidence,
)

from runtime_phase1.a2ui_probe import (
    build_render_application_tool,
    validate_render_application_model_args,
)
from runtime_phase1.ability_probe import (
    build_execute_ability_tool,
    validate_execute_ability_model_args,
)
from runtime_phase1.engine_spine_probe import build_engine_spine_probe
from runtime_phase1.scripted_model import ScriptedToolModel
from runtime_phase1.skill_registry_adapter import SkillRegistryResolver
from runtime_phase1.use_skill_probe import (
    TrustedInvocationContext,
    build_use_skill_tool,
    validate_use_skill_model_args,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = (
    REPO_ROOT
    / "openspec/changes/oss-skill-registry/examples/evidence-first-brief"
)
ABILITY_FIXTURE = (
    REPO_ROOT
    / "services/capability-registry/fixtures/phase1/"
    "execute-ability.examples.json"
)
APPLICATION_FIXTURE = (
    REPO_ROOT
    / "packages/a2ui-contract-fixtures/fixtures/"
    "display-only-result-card.application.json"
)


def workflow_context() -> TrustedInvocationContext:
    """Build deterministic trusted Workflow context for the engine probe."""

    return TrustedInvocationContext.from_mapping(
        {
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
            "trustedContext": {
                "userId": '1002',
                "environment": "PRT",
            },
            "invocationScope": {
                "kind": "WORKFLOW",
                "runId": "synthetic-engine-run",
                "nodeId": "synthetic-engine-node",
            },
            "controlRequestId": "synthetic-engine-control",
        }
    )


def _digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _package_entry(
    logical_path: str,
    content: bytes,
    handle_id: str,
) -> PackageEntry:
    return PackageEntry(
        descriptor=PackageEntryDescriptor(
            handle_id=handle_id,
            logical_path=logical_path,
            media_type="text/markdown",
            declared_byte_size=len(content),
            declared_content_digest=_digest(content),
        ),
        content=content,
    )


class IntegratedSkillMaterialPort(MaterialPort):
    """Load actual project-authored Skill bytes into the real registry."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def load_skill(self, skill_key: str, trusted_context: object) -> SkillMaterial:
        self.calls.append((skill_key, trusted_context))
        instruction_bytes = (SKILL_ROOT / "SKILL.md").read_bytes()
        resource_bytes = (
            SKILL_ROOT / "references/output-format.md"
        ).read_bytes()
        return SkillMaterial(
            instruction_entry=_package_entry(
                "SKILL.md",
                instruction_bytes,
                "engine_skill_instructions",
            ),
            resource_entries=(
                _package_entry(
                    "references/output-format.md",
                    resource_bytes,
                    "engine_skill_resource",
                ),
            ),
            required_tool_names=("execute_ability", "render_application"),
            resolution_evidence=TrustedResolutionEvidence(
                skill_key=skill_key,
                asset_id="engine_skill_asset",
                version_id="engine_skill_version",
                content_digest=_digest(instruction_bytes),
                environment="PRT",
                selection="PRT_CURRENT",
                evidence_ref="engine_skill_evidence",
            ),
        )


class SyntheticAbilityPort:
    """Replay one explicitly provisional Capability fixture without retries."""

    def __init__(self) -> None:
        self.fixture = json.loads(ABILITY_FIXTURE.read_text(encoding="utf-8"))
        self.case = self.fixture["cases"][0]
        self.calls: list[tuple[str, object, TrustedInvocationContext]] = []

    def __call__(
        self,
        ability_key: str,
        arguments: object,
        context: TrustedInvocationContext,
    ) -> dict[str, object]:
        self.calls.append((ability_key, arguments, context))
        if not self.fixture["fixtureMetadata"]["synthetic"]:
            raise AssertionError("Ability fixture must remain synthetic")
        if self.fixture["fixtureMetadata"]["runtimeEvidence"]:
            raise AssertionError("provisional fixture must not claim runtime evidence")
        if self.case["modelToolInput"] != {
            "abilityKey": ability_key,
            "arguments": arguments,
        }:
            raise AssertionError("model input drifted from provisional fixture")
        result = self.case["result"]
        return {
            "abilityKey": ability_key,
            "environment": context.trusted_context.environment,
            "releaseRef": self.case["resolvedAbility"]["releaseRef"],
            "status": result["status"],
            "output": self.case["adapterOutput"],
            "adapterCalled": result["adapterCalled"],
            "runtimeRetryCount": result["runtimeRetryCount"],
            "synthetic": True,
        }


class DisplayApplicationResolver:
    """Load the integrated display-only Application fixture."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, TrustedInvocationContext]] = []

    def __call__(
        self,
        application_key: str,
        context: TrustedInvocationContext,
    ) -> dict[str, object]:
        self.calls.append((application_key, context))
        application_bytes = APPLICATION_FIXTURE.read_bytes()
        return {
            "application": json.loads(application_bytes),
            "resolvedVersion": {
                "asset": {
                    "assetId": application_key,
                    "assetType": "APPLICATION",
                },
                "versionId": "engine_application_version",
            },
            "contentDigest": _digest(application_bytes),
        }


class EngineSpineIntegrationTest(unittest.TestCase):
    """Exercise the bounded use_skill -> Ability -> A2UI -> Finalizer chain."""

    def test_integrated_three_tool_spine_finalizes_on_successful_facts(self) -> None:
        material_port = IntegratedSkillMaterialPort()
        ability_port = SyntheticAbilityPort()
        application_resolver = DisplayApplicationResolver()
        model = ScriptedToolModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "use_skill",
                            "args": {
                                "skillKey": "demo/evidence-first-brief",
                            },
                            "id": "engine-use-skill",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute_ability",
                            "args": self._ability_model_input(),
                            "id": "engine-execute-ability",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "render_application",
                            "args": {
                                "applicationKey": "sample.display.result-card",
                                "data": {"title": "Synthetic result"},
                            },
                            "id": "engine-render-application",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Synthetic brief finalized."),
            ]
        )
        tools = [
            build_use_skill_tool(SkillRegistryResolver(material_port)),
            build_execute_ability_tool(ability_port),
            build_render_application_tool(application_resolver),
        ]
        validators = {
            "use_skill": validate_use_skill_model_args,
            "execute_ability": validate_execute_ability_model_args,
            "render_application": validate_render_application_model_args,
        }
        context = workflow_context()
        agent = build_engine_spine_probe(
            model,
            tools,
            validators,
            list(validators),
            harness_profile_key="scriptedtoolmodel",
        )

        state = agent.invoke(
            {"messages": [{"role": "user", "content": "Create a brief."}]},
            context=context,
        )

        self.assertEqual(
            ["use_skill", "execute_ability", "render_application"],
            [tool.name for tool in model.boundTools],
        )
        tool_messages = [
            message
            for message in state["messages"]
            if isinstance(message, ToolMessage)
        ]
        self.assertEqual(
            ["use_skill", "execute_ability", "render_application"],
            [message.name for message in tool_messages],
        )
        skill_content = json.loads(tool_messages[0].content)
        self.assertEqual(
            (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8"),
            skill_content["instructions"],
        )
        self.assertNotIn("content", skill_content["resources"][0])
        self.assertNotIn("evidenceRef", tool_messages[0].content)
        ability_content = json.loads(tool_messages[1].content)
        self.assertEqual(self._ability_case()["adapterOutput"], ability_content["output"])
        self.assertEqual(0, tool_messages[1].artifact["runtimeRetryCount"])
        self.assertTrue(tool_messages[1].artifact["synthetic"])
        self.assertNotIn("releaseRef", tool_messages[1].content)
        render_content = json.loads(tool_messages[2].content)
        self.assertEqual("DISPLAY_ONLY", render_content["interactionMode"])
        self.assertNotIn("contentDigest", tool_messages[2].content)
        self.assertEqual("Synthetic brief finalized.", state["messages"][-1].content)
        self.assertEqual(1, len(material_port.calls))
        self.assertEqual(1, len(ability_port.calls))
        self.assertEqual(1, len(application_resolver.calls))
        self.assertEqual(context, ability_port.calls[0][2])

    def test_parallel_tools_merge_runtime_owned_evidence(self) -> None:
        """Keep both handler facts when one model step runs Tools in parallel."""

        material_port = IntegratedSkillMaterialPort()
        ability_port = SyntheticAbilityPort()
        model = ScriptedToolModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "use_skill",
                            "args": {
                                "skillKey": "demo/evidence-first-brief",
                            },
                            "id": "parallel-use-skill",
                            "type": "tool_call",
                        },
                        {
                            "name": "execute_ability",
                            "args": self._ability_model_input(),
                            "id": "parallel-execute-ability",
                            "type": "tool_call",
                        },
                    ],
                ),
                AIMessage(content="Parallel Tools finalized."),
                AIMessage(content="Stale evidence must not finalize."),
            ]
        )
        tools = [
            build_use_skill_tool(SkillRegistryResolver(material_port)),
            build_execute_ability_tool(ability_port),
        ]
        validators = {
            "use_skill": validate_use_skill_model_args,
            "execute_ability": validate_execute_ability_model_args,
        }
        agent = build_engine_spine_probe(
            model,
            tools,
            validators,
            list(validators),
            harness_profile_key="scriptedtoolmodel",
        )

        state = agent.invoke(
            {"messages": [{"role": "user", "content": "Run both Tools."}]},
            context=workflow_context(),
        )

        tool_messages = [
            message
            for message in state["messages"]
            if isinstance(message, ToolMessage)
        ]
        self.assertCountEqual(
            ["use_skill", "execute_ability"],
            [message.name for message in tool_messages],
        )
        self.assertEqual("Parallel Tools finalized.", state["messages"][-1].content)
        self.assertEqual(1, len(material_port.calls))
        self.assertEqual(1, len(ability_port.calls))

        with self.assertRaisesRegex(RuntimeError, "Finalizer"):
            agent.invoke(
                {"messages": [{"role": "user", "content": "Run again."}]},
                context=workflow_context(),
            )

        self.assertEqual(1, len(material_port.calls))
        self.assertEqual(1, len(ability_port.calls))

    def test_reserved_runtime_is_rejected_before_ability_port(self) -> None:
        ability_port = SyntheticAbilityPort()
        invalid_args = self._ability_model_input()
        invalid_args["runtime"] = {"context": {"userId": "model-spoof"}}
        model = ScriptedToolModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute_ability",
                            "args": invalid_args,
                            "id": "engine-invalid-ability-runtime",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Tried to finalize."),
            ]
        )
        agent = build_engine_spine_probe(
            model,
            [build_execute_ability_tool(ability_port)],
            {"execute_ability": validate_execute_ability_model_args},
            ["execute_ability"],
            harness_profile_key="scriptedtoolmodel",
        )

        with self.assertRaisesRegex(RuntimeError, "Finalizer"):
            agent.invoke(
                {"messages": [{"role": "user", "content": "Run ability."}]},
                context=workflow_context(),
            )

        self.assertEqual([], ability_port.calls)

    @staticmethod
    def _ability_case() -> dict[str, object]:
        fixture = json.loads(ABILITY_FIXTURE.read_text(encoding="utf-8"))
        return fixture["cases"][0]

    @classmethod
    def _ability_model_input(cls) -> dict[str, object]:
        return dict(cls._ability_case()["modelToolInput"])


class EngineSpineAsyncFinalizerTest(unittest.IsolatedAsyncioTestCase):
    """Verify that async agent execution uses the same Finalizer gate."""

    async def test_async_finalizer_rejects_missing_tool_evidence(self) -> None:
        def unused_resolver(
            skill_key: str,
            context: TrustedInvocationContext,
        ) -> dict[str, object]:
            del skill_key, context
            raise AssertionError("resolver must not run")

        model = ScriptedToolModel(
            responses=[AIMessage(content="Async premature final response.")]
        )
        agent = build_engine_spine_probe(
            model,
            [build_use_skill_tool(unused_resolver)],
            {"use_skill": validate_use_skill_model_args},
            ["use_skill"],
            harness_profile_key="scriptedtoolmodel",
        )

        with self.assertRaisesRegex(RuntimeError, "Finalizer"):
            await agent.ainvoke(
                {"messages": [{"role": "user", "content": "Create a brief."}]},
                context=workflow_context(),
            )
