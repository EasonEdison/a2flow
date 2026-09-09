"""Actual installed SDK streaming inside synchronous Agent invocation, no network."""

import asyncio
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

import httpx2
from langchain.agents import create_agent
from langsmith import tracing_context
from pydantic import SecretStr

from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.progress_observer import (
    ProgressCallbacks, ProgressMiddleware, bind_progress,
)
from support import context


class Sink:
    def __init__(self):
        self.events = []
        self.increment = threading.Event()

    def offer(self, scope, kind, payload):
        self.events.append((scope.execution_id, kind, payload))
        if kind == "REASONING_DELTA":
            self.increment.set()


class ProgressSdkTest(unittest.TestCase):
    def test_sync_agent_invoke_has_real_sdk_increment_before_return(self):
        sink, release = Sink(), threading.Event()
        requests = []
        def event(delta, finish=None):
            return ("data: " + json.dumps({
                "id": "synthetic", "object": "chat.completion.chunk", "created": 0,
                "model": "deepseek-v4-flash", "choices": [
                    {"index": 0, "delta": delta, "finish_reason": finish}],
            }) + "\n\n").encode()
        class Wire(httpx2.SyncByteStream):
            closed = False
            def __iter__(self):
                yield event({"role": "assistant", "reasoning_content": "可展示思考",
                             "opaque": "DO-NOT-DISPLAY"})
                if not release.wait(3):
                    raise AssertionError("consumer blocked execution")
                yield event({"content": "answer"}, "stop")
                yield b"data: [DONE]\n\n"
            def close(self):
                self.closed = True
        wire = Wire()
        def transport(request):
            self.assertEqual("api.deepseek.com", request.url.host)
            requests.append(json.loads(request.content))
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=wire)
        client = httpx2.Client(transport=httpx2.MockTransport(transport))
        async_client = httpx2.AsyncClient(transport=httpx2.MockTransport(transport))
        try:
            model = DeepSeekModelFactory(
                lambda *_: {"model_id": "deepseek-v4-flash", "credential_ref": "synthetic"},
                lambda *_: SecretStr("synthetic-key"),
                http_client=client, http_async_client=async_client,
            ).create("synthetic", context().trusted_context)
            graph = create_agent(model, middleware=[ProgressMiddleware()])
            def invoke():
                with tracing_context(enabled=False), bind_progress(
                    context(), "execution-one", sink,
                ):
                    return graph.invoke({"messages": [{"role": "user", "content": "PRIVATE-INPUT"}]},
                                        config={"callbacks": [ProgressCallbacks()]})
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(invoke)
                try:
                    self.assertTrue(sink.increment.wait(2))
                    self.assertFalse(future.done())
                    self.assertTrue(requests[0]["stream"])
                    self.assertEqual("deepseek-v4-flash", requests[0]["model"])
                finally:
                    release.set()
                result = future.result(timeout=3)
            self.assertEqual("answer", result["messages"][-1].content)
            self.assertTrue(wire.closed)
            projected = json.dumps(sink.events, ensure_ascii=False)
            self.assertIn("可展示思考", projected)
            self.assertNotIn("DO-NOT-DISPLAY", projected)
            self.assertNotIn("PRIVATE-INPUT", projected)
            self.assertNotIn("deepseek_payloads", projected)
            self.assertEqual("MODEL_RETURNED", sink.events[-1][1])
        finally:
            release.set()
            client.close()
            asyncio.run(async_client.aclose())
