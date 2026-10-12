"""Bounded generator and generated source transport gates; no live provider calls."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import httpx2
from agent_workflow_runtime.a2ui_generation import DeepAgentA2uiGenerator
from agent_workflow_runtime.chat.rpc_assets import trusted_card
from agent_workflow_runtime.deepseek_model import DeepSeekProtocolError
from agent_workflow_runtime.finalizer import FinalizationRejected, RequiredToolFinalizerAdmission
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.rpc_client import GeneratedDefinition, GenerationScope, freeze
from agent_workflow_runtime.workflow_rpc import WorkflowAssets
from langchain_core.messages import AIMessage
from langsmith import tracing_context
from pydantic import SecretStr
from skillweave_contracts import TrustedContext


class GenerationTests(unittest.TestCase):
    def test_workflow_card_sink_persists_and_returns_the_card(self) -> None:
        assets = object.__new__(WorkflowAssets)
        assets.run = SimpleNamespace(run_id="run")
        assets.node_id = "node"
        assets._owner = TrustedContext(42, "PRT")
        assets._conversation_id = "workflow-scope"
        assets.store = SimpleNamespace(save=Mock(return_value={"cardId": "saved"}))
        prepared = SimpleNamespace(display=lambda: {"snapshotMessages": []})
        metadata = {"observation": {}}
        result = assets._save_card(prepared, metadata)
        self.assertEqual(result, {"cardId": "saved"})
        assets.store.save.assert_called_once_with(
            assets.owner, "workflow-scope", prepared, metadata,
        )
        self.assertEqual(metadata["workflow"], {"runId": "run", "nodeId": "node"})

    def test_workflow_replay_uses_saved_definition_without_generation_or_load(self) -> None:
        assets = object.__new__(WorkflowAssets)
        assets.run = SimpleNamespace(run_id="run")
        assets.node_id = "node"
        assets.current = Mock()
        assets._owner = TrustedContext(42, "PRT")
        assets._conversation_id = "workflow-scope"
        assets._control_request_id = "control"
        card = {"cardId": "saved"}
        assets.store = SimpleNamespace(
            read=Mock(return_value=card),
            get_binding=Mock(
                return_value={
                    "metadata": {
                        "applicationKey": "app",
                        "rpc": {"params": {}, "generatedDefinition": {}},
                        "generationIntent": "new layout",
                        "workflow": {"runId": "run", "nodeId": "node"},
                    },
                }
            ),
        )
        generator = Mock()
        result = assets.generate_application("app", {}, "new layout", "tool-1", generator)
        self.assertEqual(result, card)
        generator.generate.assert_not_called()
        with self.assertRaisesRegex(ActionRejected, "CARD_REPLAY_CONFLICT"):
            assets.generate_application("app", {}, "different layout", "tool-1", generator)

    def test_finalizer_requires_real_generation_tool_completion_not_text(self) -> None:
        gate = RequiredToolFinalizerAdmission(
            ["render_application"], tool_alternatives={"render_application": ("generate_a2ui",)}
        )
        state = {
            "messages": [AIMessage(content="done")],
            "_runtime_tool_evidence": {
                "invocation_id": "test",
                "facts": [],
            },
        }
        with self.assertRaises(FinalizationRejected):
            gate._check_terminal_response(state)
        state["_runtime_tool_evidence"]["facts"] = [("tool-1", "generate_a2ui")]
        gate._check_terminal_response(state)

    def generator(self, answer: str) -> DeepAgentA2uiGenerator:
        self.requests = []

        def handle(request: httpx2.Request) -> httpx2.Response:
            self.requests.append(json.loads(request.content))
            return httpx2.Response(
                200,
                json={
                    "id": "offline",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "deepseek-v4-pro",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": answer,
                                "reasoning_content": "",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

        factory = DeepSeekModelFactory(
            lambda *_: {"model_id": "deepseek-v4-pro", "credential_ref": "offline"},
            lambda *_: SecretStr("offline-fixture-key"),
            http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
            http_async_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
        )
        return DeepAgentA2uiGenerator(lambda: factory.create("offline", TrustedContext(42, "PRT")))

    def test_real_sdk_isolated_single_call_has_no_tools_or_parent_history(self) -> None:
        candidate = {
            "messages": [{"updateComponents": {"surfaceId": "main", "components": []}}],
            "actionPlacements": [],
        }
        generator = self.generator(json.dumps(candidate))
        with tracing_context(enabled=False):
            actual = generator.generate("生成简洁布局", freeze({"allowedComponents": []}))
        self.assertEqual(actual.model_dump(), candidate)
        self.assertEqual(len(self.requests), 1)
        self.assertFalse(self.requests[0].get("tools"))
        self.assertEqual(self.requests[0]["response_format"], {"type": "json_object"})
        user_messages = [m for m in self.requests[0]["messages"] if m["role"] == "user"]
        self.assertEqual(len(user_messages), 1)
        self.assertEqual(json.loads(user_messages[0]["content"])["intent"], "生成简洁布局")

    def test_invalid_json_is_not_repaired_or_retried(self) -> None:
        generator = self.generator("```json\n{}\n```")
        with (
            tracing_context(enabled=False),
            self.assertRaisesRegex(
                ActionRejected,
                "A2UI_GENERATION_RESULT_INVALID",
            ),
        ):
            generator.generate("生成", freeze({}))
        self.assertEqual(len(self.requests), 1)

    def test_json_mode_is_opt_in_and_rejects_unsupported_formats(self) -> None:
        generator = self.generator("ordinary text")
        model = generator._create_model()
        with tracing_context(enabled=False):
            model.invoke("ordinary request")
            self.assertNotIn("response_format", self.requests[0])
            invalid_formats = (None, {}, {"type": "text"}, {"type": "json_object", "extra": True})
            for response_format in invalid_formats:
                with (
                    self.subTest(response_format=response_format),
                    self.assertRaisesRegex(DeepSeekProtocolError, "UNSUPPORTED_RESPONSE_FORMAT"),
                ):
                    model.invoke("JSON request", response_format=response_format)
        self.assertEqual(len(self.requests), 1)
        model.client.close()
        asyncio.run(model.async_client.close())

    def test_generated_definition_is_private_and_scope_is_rebuilt_from_card_owner(self) -> None:
        definition = GeneratedDefinition(
            "people",
            freeze({"messages": [], "actionPlacements": []}),
            GenerationScope("conversation"),
            42,
            "PRT",
            "sha256:fixture",
        )
        roundtrip = GeneratedDefinition.from_record(definition.record())
        self.assertEqual(definition, roundtrip)
        card = {"display": {"applicationKey": "people", "snapshotMessages": []}}
        metadata = {
            "conversationId": "other",
            "rpc": {
                "params": {},
                "generatedDefinition": definition.record(),
            },
        }
        trusted = trusted_card(TrustedContext(42, "PRT"), card, metadata)
        self.assertEqual(trusted.app_code, "")
        self.assertEqual(trusted.scope.conversation_id, "other")
        self.assertEqual(trusted.generated_definition.scope.conversation_id, "conversation")
        # Execution service receives both scopes and must reject this mismatch.


if __name__ == "__main__":
    unittest.main()
