"""Real Deep Agent/ControlledRunRunner boundary with synthetic flash SDK SSE."""

import asyncio
import json
import unittest

import httpx2
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from langsmith import tracing_context
from pydantic import SecretStr

from agent_workflow_runtime.assembly import build_engine
from agent_workflow_runtime.finalizer import FinalizationRejected
from agent_workflow_runtime.model_config import parse_deepseek_configuration
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.native_control import ControlledRunRunner
from agent_workflow_runtime.progress_writer import ProgressWriter
from lifecycle_support import fixture
from support import context
from test_progress_writer import Store
from test_deepseek_model import Wire


class ControlledProgressTest(unittest.TestCase):
    def model(self, arguments):
        self.requests = []
        def transport(request):
            body = json.loads(request.content)
            self.requests.append(body)
            self.assertTrue(body["stream"])
            self.assertEqual("deepseek-v4-flash", body["model"])
            delta = {"role": "assistant", "reasoning_content": "synthetic-thought"}
            finish = "stop"
            if len(self.requests) == 1:
                delta["tool_calls"] = [{"index": 0, "id": "call-one", "type": "function",
                    "function": {"name": "lookup", "arguments": arguments}}]
                finish = "tool_calls"
            else:
                delta["content"] = "final"
            rows = [{"id": "synthetic", "object": "chat.completion.chunk", "created": 0,
                     "model": "deepseek-v4-flash", "choices": [
                         {"index": 0, "delta": delta, "finish_reason": finish}]}]
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=Wire(rows))
        client = httpx2.Client(transport=httpx2.MockTransport(transport))
        async_client = httpx2.AsyncClient(transport=httpx2.MockTransport(transport))
        self.addCleanup(client.close)
        self.addCleanup(lambda: asyncio.run(async_client.aclose()))
        return DeepSeekModelFactory(
            lambda *_: {"model_id": "deepseek-v4-flash", "credential_ref": "synthetic"},
            lambda *_: SecretStr("synthetic-key"),
            http_client=client, http_async_client=async_client,
        ).create("synthetic", context().trusted_context)

    def exercise(self, *, invalid=False, stopped=False, stop_in_tool=False):
        repository, lifecycle, run = fixture()
        store, executed = Store(), []
        writer = ProgressWriter(store).start()
        self.addCleanup(writer.shutdown)
        def lookup(x: int) -> str:
            """Approved synthetic operation."""
            facts = repository.operations(run.owner, run.run_id)
            self.assertTrue(any(f.kind == "TOOL" and f.status == "IN_FLIGHT" for f in facts))
            executed.append(x)
            if stop_in_tool:
                lifecycle.stop(run.owner, run.run_id, "during-tool")
            return "synthetic-result"
        def validate(args):
            if type(args) is not dict or set(args) != {"x"} or type(args["x"]) is not int:
                raise ValueError("closed args")
        model = self.model('{"x":1,"extra":2}' if invalid else '{"x":1}')
        config = parse_deepseek_configuration({"model_id": "deepseek-v4-flash",
                                               "credential_ref": "synthetic"})
        graph = build_engine(model, [StructuredTool.from_function(lookup)], {"lookup": validate},
            ["lookup"], harness_profile_key=config.harness_profile_key,
            run_lifecycle=lifecycle, progress=writer, checkpointer=MemorySaver())
        if stopped:
            lifecycle.stop(run.owner, run.run_id, "synthetic-stop")
        with tracing_context(enabled=False):
            if invalid:
                with self.assertRaises(FinalizationRejected):
                    ControlledRunRunner(lifecycle, None, None).invoke(
                        run, graph, {"messages": [HumanMessage(content="synthetic")]})
            else:
                ControlledRunRunner(lifecycle, None, None).invoke(
                    run, graph, {"messages": [HumanMessage(content="synthetic")]})
        self.assertTrue(writer.shutdown())
        records = [r for _, _, rows, _ in store.calls for r in rows]
        kinds = [r["kind"] for r in records]
        if invalid or stopped:
            self.assertEqual([], executed)
            self.assertNotIn("TOOL_STARTED", kinds)
        elif stop_in_tool:
            self.assertEqual([1], executed)
            self.assertIn("TOOL_RETURNED", kinds)
            self.assertEqual(1, len(self.requests))
            self.assertEqual("STOPPED", lifecycle.read(run.owner, run.run_id).status)
            self.assertFalse(any(f.kind == "FINALIZER" for f in repository.operations(run.owner, run.run_id)))
        else:
            self.assertEqual([1], executed)
            self.assertIn("REASONING_DELTA", kinds)
            self.assertIn("TEXT_DELTA", kinds)
            self.assertLess(kinds.index("TOOL_STARTED"), kinds.index("TOOL_RETURNED"))
            self.assertEqual("SUCCEEDED", lifecycle.read(run.owner, run.run_id).status)
            self.assertTrue(any(f.kind == "FINALIZER" and f.status == "RETURNED"
                                for f in repository.operations(run.owner, run.run_id)))
        if stopped:
            self.assertEqual([], self.requests)
            self.assertEqual([], records)
        else:
            self.assertTrue(all(binding["runId"] == run.run_id
                                and binding["nodeId"] == run.entry_node_id
                                for binding, _, _, _ in store.calls))

    def test_actual_harness_has_admitted_tool_and_native_finalizer(self):
        self.exercise()

    def test_closed_arguments_have_no_false_tool_started(self):
        self.exercise(invalid=True)

    def test_stopped_run_has_no_false_model_or_tool_progress(self):
        self.exercise(stopped=True)

    def test_stopped_late_tool_return_is_observed_without_success_or_next_model(self):
        self.exercise(stop_in_tool=True)
