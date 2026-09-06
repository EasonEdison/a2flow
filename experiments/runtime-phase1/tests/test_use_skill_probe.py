"""Behavior tests for the provisional use_skill framework adapter."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from skillweave_contracts import ContractValidationError

from runtime_phase1.use_skill_probe import (
    TrustedInvocationContext,
    build_use_skill_tool,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SKILL_FIXTURE_ROOT = (
    REPOSITORY_ROOT
    / "openspec/changes/oss-skill-registry/examples/evidence-first-brief"
)
EXPECTED_SKILL_DIGEST = "1cc034c1d066b24771e9b0d91bc74abd89012268cf225802c25dd33316e06434"

EXPECTED_CONTENT = {
    "instructions": "Summarize only the supplied evidence.",
    "requiredToolNames": ["execute_ability"],
    "resources": [
        {
            "handleId": "material_demo_001",
            "accessMode": "READ_ONLY",
            "mediaType": "text/markdown",
            "byteSize": 494,
            "contentDigest": (
                "sha256:b28d7b34f8f5c3932e3d803fa462a64012229303ac50cf034a12b57c92bc3ba5"
            ),
            "logicalPath": "references/output-format.md",
        }
    ],
}
EXPECTED_ARTIFACT = {
    "contentDigest": f"sha256:{'4' * 64}",
    "environment": "PRT",
    "evidenceRef": "evidence_skill_resolution_1",
    "resolvedVersion": {
        "asset": {"assetId": "skill_demo", "assetType": "SKILL"},
        "versionId": "skill_v2",
    },
    "selection": "PRT_CURRENT",
    "skillKey": "demo/evidence-first-brief",
}
EXPECTED_SERVER_ARTIFACT = {
    "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
    "artifact": EXPECTED_ARTIFACT,
}


class RecordingResolver:
    """Synthetic resolver that records the trusted context it receives."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, TrustedInvocationContext]] = []

    def __call__(
        self,
        skill_key: str,
        context: TrustedInvocationContext,
    ) -> dict[str, object]:
        self.calls.append((skill_key, context))
        return {
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
            "content": EXPECTED_CONTENT,
            "artifact": EXPECTED_ARTIFACT,
        }


class UseSkillProbeTest(unittest.TestCase):
    """Catches identity leakage and content/artifact projection regressions."""

    def setUp(self) -> None:
        self.resolver = RecordingResolver()
        self.tool = build_use_skill_tool(self.resolver)
        self.context = TrustedInvocationContext.from_mapping(
            {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "trustedContext": {
                    "userId": "synthetic-user",
                    "environment": "PRT",
                },
                "invocationScope": {
                    "kind": "CONVERSATION",
                    "conversationId": "conversation-test-1",
                },
                "controlRequestId": "control-request-1",
            }
        )

    def test_consumes_integrated_skill_package_bytes(self) -> None:
        """Break caught: Runtime probes drift from the integrated Skill fixture."""

        skill_path = SKILL_FIXTURE_ROOT / "SKILL.md"
        reference_path = SKILL_FIXTURE_ROOT / "references/output-format.md"
        skill_bytes = skill_path.read_bytes()
        reference_bytes = reference_path.read_bytes()
        self.assertEqual(
            EXPECTED_SKILL_DIGEST,
            hashlib.sha256(skill_bytes).hexdigest(),
        )

        expected_content = {
            "instructions": skill_bytes.decode("utf-8"),
            "requiredToolNames": [],
            "resources": [
                {
                    "handleId": "material_fixture_001",
                    "accessMode": "READ_ONLY",
                    "contentDigest": f"sha256:{hashlib.sha256(reference_bytes).hexdigest()}",
                    "logicalPath": "references/output-format.md",
                    "mediaType": "text/markdown",
                    "byteSize": len(reference_bytes),
                }
            ],
        }
        expected_artifact = {
            "contentDigest": f"sha256:{EXPECTED_SKILL_DIGEST}",
            "environment": "PRT",
            "evidenceRef": "evidence_integrated_skill_fixture",
            "resolvedVersion": {
                "asset": {
                    "assetId": "skill_demo",
                    "assetType": "SKILL",
                },
                "versionId": "skill_v2",
            },
            "selection": "PRT_CURRENT",
            "skillKey": "demo/evidence-first-brief",
        }

        def resolve_fixture(
            skill_key: str,
            context: TrustedInvocationContext,
        ) -> dict[str, object]:
            self.assertEqual("demo/evidence-first-brief", skill_key)
            self.assertEqual(self.context, context)
            return {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "content": expected_content,
                "artifact": expected_artifact,
            }

        tool = build_use_skill_tool(resolve_fixture)
        builder = StateGraph(MessagesState, context_schema=TrustedInvocationContext)
        builder.add_node("tools", ToolNode([tool]))
        builder.add_edge(START, "tools")
        builder.add_edge("tools", END)
        graph = builder.compile()
        state = graph.invoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "use_skill",
                                "args": {"skillKey": "demo/evidence-first-brief"},
                                "id": "call-integrated-skill-fixture",
                                "type": "tool_call",
                            }
                        ],
                    )
                ]
            },
            context=self.context,
        )

        tool_message = state["messages"][-1]
        self.assertEqual(expected_content, json.loads(tool_message.content))
        self.assertEqual(
            {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "artifact": expected_artifact,
            },
            tool_message.artifact,
        )

    def test_skill_key_with_trailing_newline_is_rejected(self) -> None:
        """Break caught: Runtime accepts a key rejected by the approved subset."""

        builder = StateGraph(MessagesState, context_schema=TrustedInvocationContext)
        builder.add_node("tools", ToolNode([self.tool]))
        builder.add_edge(START, "tools")
        builder.add_edge("tools", END)
        graph = builder.compile()
        state = graph.invoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "use_skill",
                                "args": {"skillKey": "demo/evidence-first-brief\n"},
                                "id": "call-invalid-newline-key",
                                "type": "tool_call",
                            }
                        ],
                    )
                ]
            },
            context=self.context,
        )

        message = state["messages"][-1]
        self.assertEqual("error", message.status)
        self.assertEqual([], self.resolver.calls)

    def test_invalid_resolver_result_is_rejected(self) -> None:
        """Break caught: Runtime forwards a result outside the approved subset."""

        def resolve_invalid(
            skill_key: str,
            context: TrustedInvocationContext,
        ) -> dict[str, object]:
            del skill_key, context
            return {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "content": {
                    "instructions": "Use the supplied evidence.",
                    "resources": [
                        {
                            "logicalPath": "references/output-format.md",
                            "mode": "READ_ONLY",
                        }
                    ],
                },
                "artifact": EXPECTED_ARTIFACT,
            }

        tool = build_use_skill_tool(resolve_invalid)
        builder = StateGraph(MessagesState, context_schema=TrustedInvocationContext)
        builder.add_node("tools", ToolNode([tool]))
        builder.add_edge(START, "tools")
        builder.add_edge("tools", END)
        graph = builder.compile()
        with self.assertRaises(ContractValidationError):
            graph.invoke(
                {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "use_skill",
                                    "args": {
                                        "skillKey": "demo/evidence-first-brief"
                                    },
                                    "id": "call-invalid-resolver-result",
                                    "type": "tool_call",
                                }
                            ],
                        )
                    ]
                },
                context=self.context,
            )

    def test_resolver_identity_and_environment_must_match_trusted_input(self) -> None:
        """Break caught: resolver evidence changes requested Skill or environment."""

        mismatches = [
            ("skillKey", "demo/another-skill"),
            ("environment", "ONLINE"),
        ]
        for field_name, field_value in mismatches:
            with self.subTest(field_name=field_name):
                artifact = copy.deepcopy(EXPECTED_ARTIFACT)
                artifact[field_name] = field_value
                if field_name == "environment":
                    artifact["selection"] = "ONLINE_STABLE"

                def resolve_mismatch(
                    skill_key: str,
                    context: TrustedInvocationContext,
                ) -> dict[str, object]:
                    del skill_key, context
                    return {
                        "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                        "content": EXPECTED_CONTENT,
                        "artifact": artifact,
                    }

                tool = build_use_skill_tool(resolve_mismatch)
                builder = StateGraph(
                    MessagesState,
                    context_schema=TrustedInvocationContext,
                )
                builder.add_node("tools", ToolNode([tool]))
                builder.add_edge(START, "tools")
                builder.add_edge("tools", END)
                graph = builder.compile()
                with self.assertRaisesRegex(ValueError, "resolved Skill"):
                    graph.invoke(
                        {
                            "messages": [
                                AIMessage(
                                    content="",
                                    tool_calls=[
                                        {
                                            "name": "use_skill",
                                            "args": {
                                                "skillKey": "demo/evidence-first-brief"
                                            },
                                            "id": f"call-mismatch-{field_name}",
                                            "type": "tool_call",
                                        }
                                    ],
                                )
                            ]
                        },
                        context=self.context,
                    )

    def test_model_schema_exposes_only_skill_key(self) -> None:
        """Break caught: trusted identity or version becomes model-selectable."""

        schema = self.tool.tool_call_schema.model_json_schema()

        self.assertEqual({"skillKey"}, set(schema["properties"]))
        self.assertEqual(["skillKey"], schema["required"])

    def test_tool_node_separates_model_content_from_resolution_artifact(self) -> None:
        """Break caught: trusted/evidence fields leak into model-facing content."""

        builder = StateGraph(MessagesState, context_schema=TrustedInvocationContext)
        builder.add_node("tools", ToolNode([self.tool]))
        builder.add_edge(START, "tools")
        builder.add_edge("tools", END)
        graph = builder.compile()
        state = graph.invoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "use_skill",
                                "args": {"skillKey": "demo/evidence-first-brief"},
                                "id": "call-use-skill-1",
                                "type": "tool_call",
                            }
                        ],
                    )
                ]
            },
            context=self.context,
        )

        tool_message = state["messages"][-1]
        self.assertIsInstance(tool_message, ToolMessage)
        self.assertEqual(EXPECTED_CONTENT, json.loads(tool_message.content))
        self.assertEqual(EXPECTED_SERVER_ARTIFACT, tool_message.artifact)
        self.assertNotIn("synthetic-user", tool_message.content)
        self.assertEqual(
            [("demo/evidence-first-brief", self.context)],
            self.resolver.calls,
        )

    def test_spoofed_trusted_fields_are_rejected_before_resolver(self) -> None:
        """Break caught: model-supplied identity or version reaches resolution."""

        strict_schema = convert_to_openai_tool(self.tool, strict=True)
        strict_parameters = strict_schema["function"]["parameters"]
        self.assertFalse(strict_parameters["additionalProperties"])

        builder = StateGraph(MessagesState, context_schema=TrustedInvocationContext)
        builder.add_node("tools", ToolNode([self.tool]))
        builder.add_edge(START, "tools")
        builder.add_edge("tools", END)
        graph = builder.compile()

        for field_name in ("userId", "environment", "versionId"):
            with self.subTest(field_name=field_name):
                state = graph.invoke(
                    {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "name": "use_skill",
                                        "args": {
                                            "skillKey": "demo/evidence-first-brief",
                                            field_name: "spoofed",
                                        },
                                        "id": f"call-spoof-{field_name}",
                                        "type": "tool_call",
                                    }
                                ],
                            )
                        ]
                    },
                    context=self.context,
                )
                message = state["messages"][-1]
                self.assertIsInstance(message, ToolMessage)
                self.assertEqual("error", message.status)
        self.assertEqual([], self.resolver.calls)
