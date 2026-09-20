"""Deep Agents characterization tests with a deterministic model."""

import json
import unittest

from langchain_core.messages import AIMessage, ToolMessage

from runtime_phase1.deep_agent_probe import build_deep_agent_probe
from runtime_phase1.scripted_model import ScriptedToolModel
from runtime_phase1.use_skill_probe import (
    TrustedInvocationContext,
    build_use_skill_tool,
)


SKILL_KEY = "demo/evidence-first-brief"
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
    "skillKey": SKILL_KEY,
}
EXPECTED_SERVER_ARTIFACT = {
    "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
    "artifact": EXPECTED_ARTIFACT,
}


class DeepAgentProbeTest(unittest.TestCase):
    """Catches Tool bypass and trusted evidence leakage into model content."""

    def test_deep_agent_exposes_only_runtime_owned_tools(self) -> None:
        """Break caught: Deep Agents exposes implicit file or subagent tools."""

        def resolve_skill(
            skill_key: str,
            context: TrustedInvocationContext,
        ) -> dict[str, object]:
            del skill_key, context
            return {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "content": EXPECTED_CONTENT,
                "artifact": EXPECTED_ARTIFACT,
            }

        use_skill_tool = build_use_skill_tool(resolve_skill)
        model = ScriptedToolModel(responses=[AIMessage(content="No tool call needed.")])
        agent = build_deep_agent_probe(
            model,
            use_skill_tool,
            harness_profile_key="scriptedtoolmodel",
        )

        agent.invoke(
            {"messages": [{"role": "user", "content": "Say hello."}]},
            context=TrustedInvocationContext.from_mapping(
                {
                    "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                    "trustedContext": {
                        "userId": '1007',
                        "environment": "PRT",
                    },
                    "invocationScope": {
                        "kind": "CONVERSATION",
                        "conversationId": "conversation-tool-boundary-1",
                    },
                    "controlRequestId": "control-request-tool-boundary-1",
                }
            ),
        )

        self.assertEqual(
            {"use_skill"},
            {tool.name for tool in model.boundTools},
        )

    def test_deep_agent_rejects_model_supplied_runtime_before_resolver(self) -> None:
        """Break caught: injected runtime hides a closed-request violation."""

        resolver_calls: list[str] = []

        def resolve_skill(
            skill_key: str,
            context: TrustedInvocationContext,
        ) -> dict[str, object]:
            del context
            resolver_calls.append(skill_key)
            return {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "content": EXPECTED_CONTENT,
                "artifact": EXPECTED_ARTIFACT,
            }

        model = ScriptedToolModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "use_skill",
                            "args": {
                                "skillKey": SKILL_KEY,
                                "runtime": {
                                    "context": {
                                        "trustedContext": {
                                            "userId": "spoofed-user",
                                            "environment": "ONLINE",
                                        }
                                    }
                                },
                            },
                            "id": "call-spoof-runtime",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Rejected."),
            ]
        )
        agent = build_deep_agent_probe(
            model,
            build_use_skill_tool(resolve_skill),
            harness_profile_key="scriptedtoolmodel",
        )
        state = agent.invoke(
            {"messages": [{"role": "user", "content": "Create a brief."}]},
            context=TrustedInvocationContext.from_mapping(
                {
                    "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                    "trustedContext": {
                        "userId": '1007',
                        "environment": "PRT",
                    },
                    "invocationScope": {
                        "kind": "CONVERSATION",
                        "conversationId": "conversation-runtime-spoof-1",
                    },
                    "controlRequestId": "control-runtime-spoof-1",
                }
            ),
        )

        self.assertEqual([], resolver_calls)
        tool_messages = [
            message
            for message in state["messages"]
            if isinstance(message, ToolMessage) and message.name == "use_skill"
        ]
        self.assertEqual(1, len(tool_messages))
        self.assertEqual("error", tool_messages[0].status)

    def test_deep_agent_calls_use_skill_and_projects_only_content(self) -> None:
        """Break caught: agent bypasses use_skill or exposes trusted evidence."""

        resolver_calls: list[tuple[str, TrustedInvocationContext]] = []

        def resolve_skill(
            skill_key: str,
            context: TrustedInvocationContext,
        ) -> dict[str, object]:
            resolver_calls.append((skill_key, context))
            return {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "content": EXPECTED_CONTENT,
                "artifact": EXPECTED_ARTIFACT,
            }

        use_skill_tool = build_use_skill_tool(resolve_skill)
        model = ScriptedToolModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "use_skill",
                            "args": {"skillKey": SKILL_KEY},
                            "id": "call-use-skill-agent-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Completed from authorized Skill material."),
            ]
        )
        agent = build_deep_agent_probe(
            model,
            use_skill_tool,
            harness_profile_key="scriptedtoolmodel",
        )
        context = TrustedInvocationContext.from_mapping(
            {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "trustedContext": {
                    "userId": '1007',
                    "environment": "PRT",
                },
                "invocationScope": {
                    "kind": "CONVERSATION",
                    "conversationId": "conversation-agent-1",
                },
                "controlRequestId": "control-request-agent-1",
            }
        )

        state = agent.invoke(
            {"messages": [{"role": "user", "content": "Create a brief."}]},
            context=context,
        )

        self.assertEqual(
            "Completed from authorized Skill material.",
            state["messages"][-1].content,
        )
        self.assertEqual([(SKILL_KEY, context)], resolver_calls)
        self.assertGreaterEqual(len(model.observedMessages), 2)
        tool_messages = [
            message
            for message in model.observedMessages[-1]
            if isinstance(message, ToolMessage) and message.name == "use_skill"
        ]
        self.assertEqual(1, len(tool_messages))
        self.assertEqual(EXPECTED_CONTENT, json.loads(tool_messages[0].content))
        self.assertEqual(EXPECTED_SERVER_ARTIFACT, tool_messages[0].artifact)
        self.assertNotIn('1007', tool_messages[0].content)
        self.assertNotIn("evidence:skill-resolution-1", tool_messages[0].content)
