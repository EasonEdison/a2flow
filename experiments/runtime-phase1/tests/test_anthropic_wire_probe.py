"""Offline provider-wire evidence for the Runtime use_skill boundary."""

import json
import unittest
from typing import Any

import anthropic
import httpx2

from runtime_phase1.anthropic_probe import StrictToolChatAnthropic
from runtime_phase1.deep_agent_probe import build_deep_agent_probe
from runtime_phase1.use_skill_probe import (
    TrustedInvocationContext,
    build_use_skill_tool,
)


SKILL_KEY = "demo/evidence-first-brief"
MODEL_NAME = "claude-sonnet-4-6"
APPROVED_SKILL_KEY_PATTERN = (
    r"^(?!.*[\r\n])[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*$"
)


class AnthropicWireProbeTest(unittest.TestCase):
    """Records the actual Anthropic request body without making a network call."""

    def test_artifact_is_not_serialized_to_provider(self) -> None:
        """Break caught: resolver evidence leaks into the provider message body."""

        captured_requests: list[dict[str, Any]] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured_requests.append(json.loads(request.content))
            if len(captured_requests) == 1:
                content = [
                    {
                        "type": "tool_use",
                        "id": "toolu_use_skill_1",
                        "name": "use_skill",
                        "input": {"skillKey": SKILL_KEY},
                    }
                ]
                stop_reason = "tool_use"
            else:
                content = [{"type": "text", "text": "Provider serialization verified."}]
                stop_reason = "end_turn"
            return httpx2.Response(
                200,
                json={
                    "id": f"msg_mock_{len(captured_requests)}",
                    "type": "message",
                    "role": "assistant",
                    "model": MODEL_NAME,
                    "content": content,
                    "stop_reason": stop_reason,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            )

        def resolve_skill(
            skill_key: str,
            context: TrustedInvocationContext,
        ) -> dict[str, object]:
            self.assertEqual(SKILL_KEY, skill_key)
            self.assertEqual(1007, context.trusted_context.user_id)
            return {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "content": {
                    "instructions": "Summarize only the supplied evidence.",
                    "resources": [],
                    "requiredToolNames": [],
                },
                "artifact": {
                    "skillKey": SKILL_KEY,
                    "resolvedVersion": {
                        "asset": {
                            "assetType": "SKILL",
                            "assetId": "skill_demo",
                        },
                        "versionId": "skill_v2",
                    },
                    "contentDigest": f"sha256:{'4' * 64}",
                    "environment": "PRT",
                    "selection": "PRT_CURRENT",
                    "evidenceRef": "evidence_provider_001",
                },
            }

        transport = httpx2.MockTransport(handler)
        http_client = httpx2.Client(transport=transport)
        anthropic_client = anthropic.Anthropic(
            api_key="synthetic-test-key",
            http_client=http_client,
        )
        self.addCleanup(anthropic_client.close)
        model = StrictToolChatAnthropic(
            model_name=MODEL_NAME,
            api_key="synthetic-test-key",
            max_tokens=64,
        )
        object.__setattr__(model, "_client", anthropic_client)
        agent = build_deep_agent_probe(
            model,
            build_use_skill_tool(resolve_skill),
            harness_profile_key=f"anthropic:{MODEL_NAME}",
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
                        "conversationId": "conversation-wire-1",
                    },
                    "controlRequestId": "control-request-wire-1",
                }
            ),
        )

        self.assertEqual(2, len(captured_requests))
        first_request, second_request = captured_requests
        self.assertEqual(["use_skill"], [tool["name"] for tool in first_request["tools"]])
        tool_schema = first_request["tools"][0]["input_schema"]
        self.assertEqual({"skillKey"}, set(tool_schema["properties"]))
        self.assertFalse(tool_schema["additionalProperties"])
        self.assertEqual(
            APPROVED_SKILL_KEY_PATTERN,
            tool_schema["properties"]["skillKey"]["pattern"],
        )

        tool_results = [
            block
            for message in second_request["messages"]
            for block in message["content"]
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
        self.assertEqual(1, len(tool_results))
        self.assertEqual(
            {
                "instructions": "Summarize only the supplied evidence.",
                "requiredToolNames": [],
                "resources": [],
            },
            json.loads(tool_results[0]["content"]),
        )
        serialized_request = json.dumps(second_request, sort_keys=True)
        self.assertNotIn("artifact", serialized_request)
        self.assertNotIn("evidence_provider_001", serialized_request)
        self.assertEqual(
            "Provider serialization verified.",
            state["messages"][-1].content,
        )
