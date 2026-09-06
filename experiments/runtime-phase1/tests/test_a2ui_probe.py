"""A2UI mode characterization tests using project-owned synthetic fixtures."""

import hashlib
import json
import unittest
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from runtime_phase1.a2ui_probe import build_render_application_tool
from runtime_phase1.use_skill_probe import TrustedInvocationContext


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "packages" / "a2ui-contract-fixtures" / "fixtures"


class FixtureApplicationResolver:
    """Resolve only the two project-authored A2UI fixtures used by this probe."""

    def __call__(
        self,
        application_key: str,
        context: TrustedInvocationContext,
    ) -> dict[str, object]:
        del context
        fixture_name = {
            "sample.display.result-card": "display-only-result-card.application.json",
            "sample.interactive.route-selection":
                "interactive-selection-card.application.json",
        }[application_key]
        application_path = FIXTURE_ROOT / fixture_name
        application_bytes = application_path.read_bytes()
        application = json.loads(application_bytes)
        return {
            "application": application,
            "resolvedVersion": {
                "asset": {"assetId": application_key, "assetType": "APPLICATION"},
                "versionId": "application-version-1",
            },
            "contentDigest": (
                f"sha256:{hashlib.sha256(application_bytes).hexdigest()}"
            ),
        }


class A2uiProbeTest(unittest.TestCase):
    """Catches incorrect display/interactive wait semantics."""

    def setUp(self) -> None:
        self.tool = build_render_application_tool(FixtureApplicationResolver())
        self.context = TrustedInvocationContext.from_mapping(
            {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "trustedContext": {
                    "userId": "synthetic-user",
                    "environment": "PRT",
                },
                "invocationScope": {
                    "kind": "WORKFLOW",
                    "conversationId": "conversation-a2ui-1",
                    "runId": "run-a2ui-1",
                    "nodeId": "node-route-choice",
                },
                "controlRequestId": "control-a2ui-1",
            }
        )

    def _invoke(
        self,
        application_key: str,
        *,
        tool_call_id: str = "call-render-1",
    ) -> dict[str, object]:
        builder = StateGraph(MessagesState, context_schema=TrustedInvocationContext)
        builder.add_node("tools", ToolNode([self.tool]))
        builder.add_edge(START, "tools")
        builder.add_edge("tools", END)
        graph = builder.compile()
        return graph.invoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "render_application",
                                "args": {
                                    "applicationKey": application_key,
                                    "data": {"title": "Synthetic", "summary": "Done"},
                                },
                                "id": tool_call_id,
                                "type": "tool_call",
                            }
                        ],
                    )
                ]
            },
            context=self.context,
        )

    def test_display_only_returns_without_interrupt(self) -> None:
        """Break caught: DISPLAY_ONLY incorrectly pauses the node."""

        state = self._invoke("sample.display.result-card")

        self.assertNotIn("__interrupt__", state)
        message = state["messages"][-1]
        self.assertIsInstance(message, ToolMessage)
        self.assertEqual(
            {
                "applicationKey": "sample.display.result-card",
                "interaction": None,
                "interactionMode": "DISPLAY_ONLY",
                "rendered": True,
            },
            json.loads(message.content),
        )
        self.assertEqual(
            {
                "applicationKey": "sample.display.result-card",
                "contentDigest": (
                    "sha256:a4c429321a38bbe4a28f03184c5e65fe197eaa767b661277c2894294e86c0218"
                ),
                "interactionMode": "DISPLAY_ONLY",
                "resolvedVersion": {
                    "asset": {
                        "assetId": "sample.display.result-card",
                        "assetType": "APPLICATION",
                    },
                    "versionId": "application-version-1",
                },
            },
            message.artifact,
        )

    def test_interactive_interrupt_is_bound_to_runtime_node_and_version(self) -> None:
        """Break caught: an interactive wait is unbound or chat-resumable."""

        state = self._invoke("sample.interactive.route-selection")

        self.assertEqual(1, len(state["__interrupt__"]))
        self.assertEqual(
            {
                "actionName": "confirm_route_choice",
                "applicationKey": "sample.interactive.route-selection",
                "interactionId": (
                    "interaction:"
                    "d286ba61841e4a3e52f398fbd25594c10318f1ee598da01e50b751a43d8c2152"
                ),
                "kind": "A2UI_INTERACTION_REQUIRED",
                "nodeId": "node-route-choice",
                "ordinaryChatMayResume": False,
                "runId": "run-a2ui-1",
                "versionId": "application-version-1",
            },
            state["__interrupt__"][0].value,
        )

    def test_interactions_do_not_collide_within_one_node(self) -> None:
        """Break caught: two rendered forms share one Interaction identity."""

        first = self._invoke(
            "sample.interactive.route-selection",
            tool_call_id="call-render-1",
        )
        second = self._invoke(
            "sample.interactive.route-selection",
            tool_call_id="call-render-2",
        )

        self.assertNotEqual(
            first["__interrupt__"][0].value["interactionId"],
            second["__interrupt__"][0].value["interactionId"],
        )

    def test_strict_model_schema_forbids_trusted_node_binding(self) -> None:
        """Break caught: provider schema permits a model-supplied node binding."""

        strict_schema = convert_to_openai_tool(self.tool, strict=True)
        strict_parameters = strict_schema["function"]["parameters"]
        self.assertFalse(strict_parameters["additionalProperties"])
        self.assertEqual(
            {"applicationKey", "data"},
            set(strict_parameters["properties"]),
        )
