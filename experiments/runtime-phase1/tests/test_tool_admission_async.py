"""Async admission tests for Deep Agent tool execution."""

import asyncio
import unittest

from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from runtime_phase1.deep_agent_probe import build_deep_agent_probe
from runtime_phase1.scripted_model import ScriptedToolModel
from runtime_phase1.tool_admission import ClosedModelArgsAdmission
from runtime_phase1.use_skill_probe import (
    TrustedInvocationContext,
    build_use_skill_tool,
)


SKILL_KEY = "demo/evidence-first-brief"
VALID_RESULT = {
    "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
    "content": {
        "instructions": "Use only supplied evidence.",
        "requiredToolNames": [],
        "resources": [],
    },
    "artifact": {
        "contentDigest": f"sha256:{'4' * 64}",
        "environment": "PRT",
        "evidenceRef": "evidence_async_admission_1",
        "resolvedVersion": {
            "asset": {"assetId": "skill_demo", "assetType": "SKILL"},
            "versionId": "skill_v2",
        },
        "selection": "PRT_CURRENT",
        "skillKey": SKILL_KEY,
    },
}


def trusted_context() -> TrustedInvocationContext:
    """Build deterministic server-owned invocation context."""

    return TrustedInvocationContext.from_mapping(
        {
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
            "trustedContext": {
                "userId": "synthetic-user",
                "environment": "PRT",
            },
            "invocationScope": {
                "kind": "CONVERSATION",
                "conversationId": "conversation-async-admission-1",
            },
            "controlRequestId": "control-async-admission-1",
        }
    )


class AsyncToolAdmissionTest(unittest.TestCase):
    """Keeps sync and async Deep Agent admission behavior equivalent."""

    def invoke_agent(
        self,
        args: dict[str, object],
        resolver_calls: list[str],
    ) -> dict[str, object]:
        """Invoke a two-turn scripted agent through its public async API."""

        def resolve_skill(
            skill_key: str,
            context: TrustedInvocationContext,
        ) -> dict[str, object]:
            del context
            resolver_calls.append(skill_key)
            return VALID_RESULT

        model = ScriptedToolModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "use_skill",
                            "args": args,
                            "id": "call-async-admission",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Finished."),
            ]
        )
        agent = build_deep_agent_probe(
            model,
            build_use_skill_tool(resolve_skill),
            harness_profile_key="scriptedtoolmodel",
        )
        return asyncio.run(
            agent.ainvoke(
                {"messages": [{"role": "user", "content": "Create a brief."}]},
                context=trusted_context(),
            )
        )

    def test_async_rejects_reserved_runtime_before_resolver(self) -> None:
        """Break caught: async middleware bypasses closed original args."""

        resolver_calls: list[str] = []
        state = self.invoke_agent(
            {
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
            resolver_calls,
        )

        self.assertEqual([], resolver_calls)
        tool_messages = [
            message
            for message in state["messages"]
            if isinstance(message, ToolMessage) and message.name == "use_skill"
        ]
        self.assertEqual(1, len(tool_messages))
        self.assertEqual("error", tool_messages[0].status)

    def test_async_allows_closed_request_and_executes_resolver(self) -> None:
        """Break caught: async admission rejects a valid closed request."""

        resolver_calls: list[str] = []
        state = self.invoke_agent({"skillKey": SKILL_KEY}, resolver_calls)

        self.assertEqual([SKILL_KEY], resolver_calls)
        self.assertEqual("Finished.", state["messages"][-1].content)
    def test_async_preserves_command_returned_by_handler(self) -> None:
        """Break caught: async admission rewrites LangGraph control commands."""

        admission = ClosedModelArgsAdmission(
            {"use_skill": lambda value: value},
        )
        request = ToolCallRequest(
            tool_call={
                "name": "use_skill",
                "args": {"skillKey": SKILL_KEY},
                "id": "call-async-command",
                "type": "tool_call",
            },
            tool=None,
            state={},
            runtime=None,
        )
        expected = Command(update={"admitted": True})

        async def return_command(
            tool_request: ToolCallRequest,
        ) -> Command:
            self.assertIs(request, tool_request)
            return expected

        actual = asyncio.run(
            admission.awrap_tool_call(request, return_command)
        )

        self.assertIs(expected, actual)
