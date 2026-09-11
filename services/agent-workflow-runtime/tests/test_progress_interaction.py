"""Actual flash SDK plus existing real Action/interrupt/Finalizer fixtures."""

import asyncio
import json
from unittest.mock import patch

import httpx2
from pydantic import SecretStr

from agent_workflow_runtime.assembly import build_engine
from agent_workflow_runtime.model_config import parse_deepseek_configuration
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.progress_writer import ProgressWriter
from test_controlled_interaction import ControlledInteractionTest as InteractionFixture
from test_deepseek_model import Wire
from test_progress_writer import Store


class ProgressInteractionTest(InteractionFixture):
    def setUp(self):
        super().setUp()
        self.display = Store()
        self.writer = ProgressWriter(self.display).start()
        self.addCleanup(self.writer.shutdown)

    def streamed_model(self, responses):
        responses = iter(responses)
        def transport(request):
            body = json.loads(request.content)
            self.assertTrue(body["stream"])
            self.assertEqual("deepseek-v4-flash", body["model"])
            message = next(responses)
            delta = {"role": "assistant", "content": message.content,
                     "reasoning_content": "synthetic visible reasoning"}
            if message.tool_calls:
                delta["tool_calls"] = [
                    {"index": index, "id": call["id"], "type": "function",
                     "function": {"name": call["name"], "arguments": json.dumps(call["args"])}}
                    for index, call in enumerate(message.tool_calls)]
            rows = [{"id": "synthetic", "object": "chat.completion.chunk", "created": 0,
                     "model": "deepseek-v4-flash", "choices": [{
                         "index": 0, "delta": delta,
                         "finish_reason": "tool_calls" if message.tool_calls else "stop"}]}]
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=Wire(rows))
        client = httpx2.Client(transport=httpx2.MockTransport(transport))
        async_client = httpx2.AsyncClient(transport=httpx2.MockTransport(transport))
        self.addCleanup(client.close)
        self.addCleanup(lambda: asyncio.run(async_client.aclose()))
        return DeepSeekModelFactory(
            lambda *_: {"model_id": "deepseek-v4-flash", "credential_ref": "synthetic"},
            lambda *_: SecretStr("synthetic-key"),
            http_client=client, http_async_client=async_client,
        ).create("synthetic", self.run.owner)

    def assemble(self, run):
        def engine(*args, **kwargs):
            kwargs["harness_profile_key"] = parse_deepseek_configuration(
                {"model_id": "deepseek-v4-flash", "credential_ref": "synthetic"}).harness_profile_key
            return build_engine(*args, **kwargs, progress=self.writer)
        with patch("test_controlled_interaction.ScriptedToolModel", self.streamed_model), patch(
            "test_controlled_interaction.build_engine_spine_probe", engine,
        ):
            return super().assemble(run)

    def test_skill_wait_action_resume_finalizer_succeeds_through_controlled_entry(self):
        super().test_skill_wait_action_resume_finalizer_succeeds_through_controlled_entry()
        self.assertTrue(self.writer.shutdown())
        bindings = [binding for binding, _, _, _ in self.display.calls]
        self.assertEqual(2, len({b["executionId"] for b in bindings}))
        self.assertEqual({self.run.run_id}, {b["runId"] for b in bindings})
        self.assertEqual({self.run.entry_node_id}, {b["nodeId"] for b in bindings})
        records = [r for _, _, rows, _ in self.display.calls for r in rows]
        self.assertIn("TOOL_INTERRUPTED", [r["kind"] for r in records])
        self.assertNotIn("NODE_SUCCEEDED", [r["kind"] for r in records])

    def test_stopped_wait_blocks_old_card_and_command_and_restart_has_new_interaction(self):
        super().test_stopped_wait_blocks_old_card_and_command_and_restart_has_new_interaction()
        self.assertTrue(self.writer.shutdown())
        bindings = [binding for binding, _, _, _ in self.display.calls]
        self.assertEqual(2, len({b["runId"] for b in bindings}))
        self.assertEqual(3, len({b["executionId"] for b in bindings}))
        old_segments = {b["executionId"] for b in bindings if b["runId"] == self.run.run_id}
        self.assertEqual(1, len(old_segments))
