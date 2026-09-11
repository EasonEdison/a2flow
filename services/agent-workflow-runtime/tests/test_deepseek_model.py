"""Positive project-adapter synthetic HTTP/SSE gates; never live provider proof."""

import asyncio
import json
import unittest
from unittest.mock import patch

import httpx2
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import (
    AIMessage, HumanMessage, ToolMessage, message_to_dict, messages_from_dict,
    message_chunk_to_message,
)
from langsmith import tracing_context
from pydantic import SecretStr

from agent_workflow_runtime.deepseek_model import DeepSeekProtocolError
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.model_content import model_content_view
from support import context
from test_deepseek_sdk_contract import completion, TOOL_SCHEMA


def call(arguments='{"x":1}', identity="c-1"):
    return {"id": identity, "type": "function",
            "function": {"name": "lookup", "arguments": arguments}}


def stream_data(arguments_end="1}", finish="tool_calls"):
    def chunk(delta=None, end=None, usage=None):
        return {"id": "repeated-id", "object": "chat.completion.chunk", "created": 7,
                "model": "deepseek-v4-pro", "opaque": {"signed": "exact", "number": 11},
                "choices": [] if delta is None else [
                    {"index": 0, "delta": delta, "finish_reason": end}],
                "usage": usage}
    return [
        chunk({"role": "assistant", "content": "an", "reasoning_content": "rea",
               "opaque_delta": {"signed": "delta", "number": 13}, "tool_calls": [
                   {"index": 0, **call('{"x":', "c-1")},
                   {"index": 1, **call('{"x":', "c-2")},
               ]}),
        chunk({"content": "swer", "reasoning_content": "son", "tool_calls": [
            {"index": 1, "id": "c-2", "type": "function",
             "function": {"name": "lookup", "arguments": "2}"}},
            {"index": 0, "id": "c-1", "type": "function",
             "function": {"name": "lookup", "arguments": arguments_end}},
        ]}),
        chunk({}, finish),
        chunk(usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}),
    ]


class Wire(httpx2.SyncByteStream, httpx2.AsyncByteStream):
    def __init__(self, records):
        self.parts = [("data: " + json.dumps(item) + "\n\n").encode() for item in records]
        self.parts.append(b"data: [DONE]\n\n")
        self.closed = False

    def __iter__(self):
        yield from self.parts

    async def __aiter__(self):
        for part in self.parts:
            yield part

    def close(self):
        self.closed = True

    async def aclose(self):
        self.closed = True


class Tokens(BaseCallbackHandler):
    def __init__(self):
        self.chunks = []

    def on_llm_new_token(self, token, **kwargs):
        self.chunks.append(kwargs["chunk"])


class DeepSeekModelTest(unittest.TestCase):
    def model(self, handler):
        self.requests, self.wires = [], []
        def transport(request):
            self.assertEqual("api.deepseek.com", request.url.host)
            self.assertEqual("/chat/completions", request.url.path)
            self.requests.append(json.loads(request.content))
            answer = handler(self.requests[-1], len(self.requests))
            if isinstance(answer, list):
                wire = Wire(answer)
                self.wires.append(wire)
                return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=wire)
            if isinstance(answer, httpx2.Response):
                return answer
            return httpx2.Response(200, json=answer)
        client = httpx2.Client(transport=httpx2.MockTransport(transport))
        async_client = httpx2.AsyncClient(transport=httpx2.MockTransport(transport))
        self.addCleanup(client.close)
        self.addCleanup(lambda: asyncio.run(async_client.aclose()))
        return DeepSeekModelFactory(
            lambda *args: {"model_id": "deepseek-v4-pro", "credential_ref": "synthetic"},
            lambda *args: SecretStr("synthetic-offline-key"),
            http_client=client, http_async_client=async_client,
        ).create("synthetic", context().trusted_context)

    def test_http_typed_payload_reasoning_tool_metadata_and_native_roundtrip(self):
        response = completion("answer", "reason", [call()])
        model = self.model(lambda *_: response)
        with tracing_context(enabled=False):
            result = model.bind_tools([TOOL_SCHEMA]).invoke("synthetic")
        self.assertEqual("answer", result.content)
        self.assertEqual("reason", result.additional_kwargs["reasoning_content"])
        self.assertEqual({"x": 1}, result.tool_calls[0]["args"])
        self.assertEqual(5, result.usage_metadata["total_tokens"])
        raw = result.additional_kwargs["deepseek_payloads"][0]["payload"]
        self.assertEqual("response-marker", raw["opaque_response"])
        self.assertEqual("choice-marker", raw["choices"][0]["opaque_choice"])
        self.assertEqual("message-marker", raw["choices"][0]["message"]["opaque_message"])
        restored = messages_from_dict([message_to_dict(result)])[0]
        self.assertEqual(message_to_dict(result), message_to_dict(restored))
        self.assertEqual(model_content_view(result), model_content_view(restored))
        self.assertNotIn("synthetic-offline-key", repr(model))
        self.assertNotIn("synthetic-offline-key", model.model_dump_json())

    def test_next_sdk_request_keeps_both_assistant_reasoning_without_raw_replay(self):
        model = self.model(lambda _, count: completion(
            "first" if count == 1 else "", "no-tool" if count == 1 else "tool",
            None if count == 1 else [call()])).bind_tools([TOOL_SCHEMA])
        history = [HumanMessage(content="synthetic")]
        with tracing_context(enabled=False):
            first = model.invoke(history)
            history += [first, HumanMessage(content="followup")]
            second = model.invoke(history)
            history += [second, ToolMessage(content="synthetic", tool_call_id="c-1")]
            history = messages_from_dict([message_to_dict(message) for message in history])
            model.invoke(history)
        assistants = [m for m in self.requests[2]["messages"] if m["role"] == "assistant"]
        self.assertEqual(["no-tool", "tool"], [m["reasoning_content"] for m in assistants])
        self.assertNotIn("tool_calls", assistants[0])
        self.assertEqual("c-1", assistants[1]["tool_calls"][0]["id"])
        outbound = json.dumps(self.requests[2])
        self.assertNotIn("deepseek_payloads", outbound)
        self.assertNotIn("message-marker", outbound)

    def test_native_sse_records_callbacks_and_resource_close(self):
        records = stream_data()
        model = self.model(lambda body, _: records if body["stream"] else completion()).bind_tools([TOOL_SCHEMA])
        tokens = Tokens()
        with tracing_context(enabled=False):
            chunks = list(model.stream("synthetic", config={"callbacks": [tokens]}))
        merged = chunks[0]
        for chunk in chunks[1:]:
            merged += chunk
        self.assertEqual("answer", merged.content)
        self.assertEqual("reason", merged.additional_kwargs["reasoning_content"])
        self.assertEqual(["c-1", "c-2"], [c["id"] for c in merged.tool_calls])
        self.assertEqual([{"x": 1}, {"x": 2}], [c["args"] for c in merged.tool_calls])
        self.assertEqual(5, merged.usage_metadata["total_tokens"])
        payloads = merged.additional_kwargs["deepseek_payloads"]
        self.assertEqual(4, len(payloads))
        self.assertEqual(["repeated-id"] * 4, [p["payload"]["id"] for p in payloads])
        self.assertEqual([7] * 4, [p["payload"]["created"] for p in payloads])
        self.assertEqual([11] * 4, [p["payload"]["opaque"]["number"] for p in payloads])
        self.assertEqual("delta", payloads[0]["payload"]["choices"][0]["delta"]["opaque_delta"]["signed"])
        self.assertTrue(self.wires[0].closed)
        self.assertEqual(len(chunks), len(tokens.chunks))
        complete = message_chunk_to_message(merged)
        self.assertEqual(message_to_dict(complete),
                         message_to_dict(messages_from_dict([message_to_dict(complete)])[0]))
        restored = messages_from_dict([message_to_dict(complete)])[0]
        with tracing_context(enabled=False):
            model.invoke([HumanMessage(content="synthetic"), restored,
                          ToolMessage(content="one", tool_call_id="c-1"),
                          ToolMessage(content="two", tool_call_id="c-2")])
        assistant = self.requests[1]["messages"][1]
        self.assertEqual("reason", assistant["reasoning_content"])
        self.assertEqual(["c-1", "c-2"], [c["id"] for c in assistant["tool_calls"]])
        self.assertNotIn("deepseek_payloads", json.dumps(self.requests[1]))


    def test_async_invoke_stream_and_early_close_use_native_async_sdk(self):
        model = self.model(lambda body, _: stream_data() if body["stream"] else completion())
        async def exercise():
            with tracing_context(enabled=False):
                result = await model.ainvoke("synthetic")
                self.assertEqual("reason", result.additional_kwargs["reasoning_content"])
                chunks = [chunk async for chunk in model.astream("synthetic")]
                self.assertGreater(len(chunks), 1)
                self.assertTrue(self.wires[-1].closed)
                stream = model.astream("synthetic")
                await anext(stream)
                await stream.aclose()
                self.assertTrue(self.wires[-1].closed)
        asyncio.run(exercise())

    def test_stream_error_truncated_arguments_and_early_close(self):
        for suffix, finish in (("1", "tool_calls"), ("1}", "length"), ("1}", None)):
            with self.subTest(suffix=suffix, finish=finish):
                model = self.model(lambda *_: stream_data(suffix, finish))
                with tracing_context(enabled=False):
                    with self.assertRaises(DeepSeekProtocolError):
                        list(model.stream("synthetic"))
                self.assertTrue(self.wires[-1].closed)
        model = self.model(lambda *_: stream_data())
        with tracing_context(enabled=False):
            stream = model.stream("synthetic")
            next(stream)
            stream.close()
        self.assertTrue(self.wires[-1].closed)

    def test_full_tool_json_rejects_truncation_duplicate_keys_nonfinite_and_scalars(self):
        for raw in ('{"x":1', '{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', '[]'):
            with self.subTest(raw=raw):
                model = self.model(lambda *_: completion("", "reason", [call(raw)]))
                with tracing_context(enabled=False):
                    with self.assertRaises(DeepSeekProtocolError):
                        model.invoke("synthetic")

    def test_unsupported_inputs_and_conversion_misalignment_reject_before_transport(self):
        model = self.model(lambda *_: self.fail("unexpected transport"))
        with tracing_context(enabled=False):
            for message in (
                HumanMessage(content=[{"type": "image_url", "image_url": {"url": "synthetic"}}]),
                AIMessage(content="missing reasoning"),
                AIMessage(content=[{"type": "future", "payload": "synthetic"}]),
            ):
                with self.subTest(message=message.type):
                    with self.assertRaises(DeepSeekProtocolError):
                        model.bind_tools([TOOL_SCHEMA]).invoke([message])
            with self.assertRaises(DeepSeekProtocolError):
                model.invoke("synthetic", temperature=0.5)
            with patch("agent_workflow_runtime.deepseek_model.convert_to_openai_messages",
                       return_value={"role": "assistant", "content": "changed"}):
                with self.assertRaisesRegex(DeepSeekProtocolError, "ALIGNMENT"):
                    model.invoke("synthetic")
        self.assertEqual([], self.requests)

    def test_actual_harness_match_preserves_tool_admission_finalizer_and_stop(self):
        from langchain_core.tools import StructuredTool
        from langgraph.checkpoint.memory import MemorySaver
        from agent_workflow_runtime.assembly import build_engine, IMPLICIT_DEEP_AGENT_TOOLS
        from agent_workflow_runtime.finalizer import FinalizationRejected
        from agent_workflow_runtime.model_config import parse_deepseek_configuration
        from agent_workflow_runtime.native_control import ControlledRunRunner
        from lifecycle_support import fixture

        executed = []
        def lookup(x: int) -> str:
            """Synthetic approved operation."""
            executed.append(x)
            return "synthetic-result"
        def validate(args):
            if type(args) is not dict or set(args) != {"x"} or type(args["x"]) is not int:
                raise ValueError("closed contract")
        tool = StructuredTool.from_function(lookup)
        calls = [{"id": "call-1", "type": "function",
                  "function": {"name": "lookup", "arguments": '{"x":1}'}}]
        model = self.model(lambda request, count:
            completion("", "tool-reasoning", calls) if count == 1 else completion())
        config = parse_deepseek_configuration({
            "model_id": "deepseek-v4-pro", "credential_ref": "synthetic-ref"})
        repository, lifecycle, run = fixture()
        graph = build_engine(
            model, [tool], {"lookup": validate}, ["lookup"],
            harness_profile_key=config.harness_profile_key, run_lifecycle=lifecycle, checkpointer=MemorySaver(),
        )
        runner = ControlledRunRunner(lifecycle, None, None)
        with tracing_context(enabled=False):
            runner.invoke(run, graph, {"messages": [HumanMessage(content="synthetic")]})
        self.assertEqual([1], executed)
        self.assertEqual("SUCCEEDED", lifecycle.read(run.owner, run.run_id).status)
        self.assertTrue(any(f.kind == "FINALIZER" and f.status == "RETURNED"
                            for f in repository.operations(run.owner, run.run_id)))
        for request in self.requests:
            names = {item["function"]["name"] for item in request["tools"]}
            self.assertFalse(names & IMPLICIT_DEEP_AGENT_TOOLS)
            self.assertEqual({"lookup"}, names)

        # Closed admission rejects extra model args; Finalizer cannot fabricate facts.
        executed.clear()
        invalid = [{"id": "invalid-call", "type": "function",
                    "function": {"name": "lookup", "arguments": '{"x":1,"extra":2}'}}]
        model = self.model(lambda request, count:
            completion("", "tool-reasoning", invalid) if count == 1 else completion())
        _, life2, run2 = fixture()
        graph2 = build_engine(model, [tool], {"lookup": validate}, ["lookup"],
                              harness_profile_key=config.harness_profile_key, run_lifecycle=life2, checkpointer=MemorySaver())
        with tracing_context(enabled=False):
            with self.assertRaises(FinalizationRejected):
                ControlledRunRunner(life2, None, None).invoke(
                    run2, graph2, {"messages": [HumanMessage(content="synthetic")]})
        self.assertEqual([], executed)

        # A stopped Run never reaches the selected SDK or any tool.
        _, life3, run3 = fixture()
        graph3 = build_engine(model, [tool], {"lookup": validate}, ["lookup"],
                              harness_profile_key=config.harness_profile_key, run_lifecycle=life3, checkpointer=MemorySaver())
        life3.stop(run3.owner, run3.run_id, "synthetic-stop")
        before = len(self.requests)
        with tracing_context(enabled=False):
            stopped = ControlledRunRunner(life3, None, None).invoke(
                run3, graph3, {"messages": [HumanMessage(content="synthetic")]})
        self.assertEqual("STOPPED", stopped["status"])
        self.assertEqual(before, len(self.requests))
        self.assertEqual([], executed)

    def test_refusal_error_and_sdk_retries_zero(self):
        from openai import BadRequestError
        model = self.model(lambda _, count: completion("", "", refusal="synthetic-refusal")
                           if count == 1 else httpx2.Response(
                               400, json={"error": {"message": "synthetic", "type": "invalid_request_error"}}))
        self.assertEqual(0, model.client.max_retries)
        self.assertEqual(0, model.async_client.max_retries)
        with tracing_context(enabled=False):
            refused = model.invoke("synthetic")
            self.assertEqual("synthetic-refusal", refused.additional_kwargs["refusal"])
            with self.assertRaises(BadRequestError):
                model.invoke("synthetic")
        self.assertEqual(2, len(self.requests))

    def test_stream_cancellation_and_transport_error_close_resources(self):
        class WaitingWire(Wire):
            def __init__(self):
                super().__init__(stream_data())
                self.waiting = asyncio.Event()
            async def __aiter__(self):
                yield self.parts[0]
                self.waiting.set()
                await asyncio.Event().wait()
        async def cancel():
            wire = WaitingWire()
            model = self.model(lambda *_: httpx2.Response(
                200, headers={"content-type": "text/event-stream"}, stream=wire))
            async def consume():
                with tracing_context(enabled=False):
                    return [chunk async for chunk in model.astream("synthetic")]
            task = asyncio.create_task(consume())
            await asyncio.wait_for(wire.waiting.wait(), timeout=2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(wire.closed)
        asyncio.run(cancel())

        class BrokenWire(Wire):
            def __iter__(self):
                yield self.parts[0]
                raise httpx2.ReadError("synthetic-stream-error")
        wire = BrokenWire(stream_data())
        model = self.model(lambda *_: httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, stream=wire))
        with tracing_context(enabled=False):
            with self.assertRaises(httpx2.ReadError):
                list(model.stream("synthetic"))
        self.assertTrue(wire.closed)

    def test_streamed_partial_tool_cannot_reach_engine_dispatch(self):
        from langchain_core.tools import StructuredTool
        from agent_workflow_runtime.assembly import build_engine
        executed = []
        def lookup(x: int) -> str:
            """Synthetic approved operation."""
            executed.append(x)
            return "synthetic"
        def validate(args):
            if set(args) != {"x"} or type(args["x"]) is not int:
                raise ValueError("closed contract")
        for ending in ("1", "1}"):
            records = stream_data(ending, "tool_calls" if ending == "1" else None)
            model = self.model(lambda *_: records)
            graph = build_engine(model, [StructuredTool.from_function(lookup)],
                                 {"lookup": validate}, ["lookup"],
                                 harness_profile_key="deepseek:deepseek-v4-pro")
            with tracing_context(enabled=False):
                with self.assertRaises(DeepSeekProtocolError):
                    list(graph.stream({"messages": [HumanMessage(content="synthetic")]},
                                      stream_mode=["messages", "updates"]))
            self.assertTrue(self.requests[0]["stream"])
            self.assertEqual([], executed)
            self.assertTrue(self.wires[-1].closed)
