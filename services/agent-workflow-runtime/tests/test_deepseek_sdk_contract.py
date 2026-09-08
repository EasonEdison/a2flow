"""Fixed SDK synthetic HTTP characterization; known losses are NOT acceptance.

No captured/live provider data, private SDK override or network transport is used.
Tests named known_gap document blockers and must not count as supported behavior.
"""

import asyncio
import json
import unittest

import httpx2
from langchain_core.messages import HumanMessage, ToolMessage, message_to_dict, messages_from_dict
from langsmith import tracing_context
from pydantic import SecretStr

from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.model_content import model_content_view
from support import context


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "lookup", "description": "Synthetic lookup",
        "parameters": {"type": "object", "properties": {"x": {"type": "integer"}},
                       "required": ["x"], "additionalProperties": False},
    },
}


def completion(content="answer", reasoning="reason", calls=None, refusal=None):
    message = {"role": "assistant", "content": content, "reasoning_content": reasoning,
               "refusal": refusal, "opaque_message": "message-marker"}
    if calls:
        message["tool_calls"] = calls
    return {
        "id": "synthetic-response", "object": "chat.completion", "created": 0,
        "model": "deepseek-v4-pro", "opaque_response": "response-marker",
        "choices": [{"index": 0, "message": message,
                     "finish_reason": "tool_calls" if calls else "stop",
                     "opaque_choice": "choice-marker"}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }


class DeepSeekSdkContractTest(unittest.TestCase):
    def model(self, handler):
        self.requests = []
        def transport(request):
            self.assertEqual("api.deepseek.com", request.url.host)
            self.assertEqual("/chat/completions", request.url.path)
            self.requests.append(json.loads(request.content))
            return handler(request, len(self.requests))
        client = httpx2.Client(transport=httpx2.MockTransport(transport))
        async_client = httpx2.AsyncClient(transport=httpx2.MockTransport(transport))
        self.addCleanup(client.close)
        self.addCleanup(lambda: asyncio.run(async_client.aclose()))
        factory = DeepSeekModelFactory(
            lambda *args: {"model_id": "deepseek-v4-pro", "credential_ref": "synthetic-ref"},
            lambda *args: SecretStr("synthetic-offline-key"),
            http_client=client, http_async_client=async_client,
        )
        return factory.create("synthetic-model", context().trusted_context)

    def test_http_ingress_native_reasoning_text_tool_usage_and_serialization(self):
        calls = [{"id": "call-1", "type": "function",
                  "function": {"name": "lookup", "arguments": '{"x":1}'}}]
        model = self.model(lambda request, count: httpx2.Response(
            200, json=completion("answer", "returned reasoning", calls)))
        with tracing_context(enabled=False):
            result = model.bind_tools([TOOL_SCHEMA]).invoke([HumanMessage(content="synthetic")])
        self.assertEqual("answer", result.content)
        self.assertEqual("returned reasoning", result.additional_kwargs["reasoning_content"])
        self.assertEqual({"x": 1}, result.tool_calls[0]["args"])
        self.assertEqual("call-1", result.tool_calls[0]["id"])
        self.assertEqual(5, result.usage_metadata["total_tokens"])
        self.assertEqual("tool_calls", result.response_metadata["finish_reason"])
        self.assertEqual("deepseek", result.response_metadata["model_provider"])
        self.assertEqual({"type": "enabled"}, self.requests[0]["thinking"])
        encoded = message_to_dict(result)
        restored = messages_from_dict([encoded])[0]
        self.assertEqual(encoded, message_to_dict(restored))
        self.assertEqual(model_content_view(result), model_content_view(restored))

    def test_known_gap_unknown_wire_fields_are_lost_before_native_view(self):
        model = self.model(lambda request, count: httpx2.Response(200, json=completion()))
        with tracing_context(enabled=False):
            result = model.invoke("synthetic")
        native = json.dumps(message_to_dict(result))
        for marker in ("message-marker", "response-marker", "choice-marker"):
            self.assertNotIn(marker, native)
        # These fields were in actual HTTP fixture ingress, not manually added later.

    def test_known_gap_next_sdk_request_drops_reasoning_from_all_assistant_turns(self):
        calls = [{"id": "call-1", "type": "function",
                  "function": {"name": "lookup", "arguments": '{"x":1}'}}]
        def handler(request, count):
            if count == 1:
                return httpx2.Response(200, json=completion("first", "no-tool-reasoning"))
            if count == 2:
                return httpx2.Response(200, json=completion("", "tool-reasoning", calls))
            return httpx2.Response(200, json=completion("final", "final-reasoning"))
        model = self.model(handler).bind_tools([TOOL_SCHEMA])
        history = [HumanMessage(content="synthetic")]
        with tracing_context(enabled=False):
            first = model.invoke(history)
            history += [first, HumanMessage(content="followup")]
            second = model.invoke(history)
            history += [second, ToolMessage(content="synthetic-result", tool_call_id="call-1")]
            history = messages_from_dict([message_to_dict(message) for message in history])
            self.assertEqual("no-tool-reasoning", history[1].additional_kwargs["reasoning_content"])
            self.assertEqual("tool-reasoning", history[3].additional_kwargs["reasoning_content"])
            model.invoke(history)
        outgoing = self.requests[2]
        self.assertTrue(outgoing["tools"])
        assistants = [message for message in outgoing["messages"] if message["role"] == "assistant"]
        self.assertEqual(2, len(assistants))
        self.assertNotIn("tool_calls", assistants[0])
        self.assertEqual("call-1", assistants[1]["tool_calls"][0]["id"])
        for message in assistants:
            self.assertNotIn("reasoning_content", message)
        self.assertEqual("tool", outgoing["messages"][-1]["role"])
        # This actual outgoing SDK payload violates the selected tools-history gate.

    def test_sdk_sse_stream_interleaved_calls_reasoning_and_usage_only_tail(self):
        def chunk(delta=None, finish=None, usage=None):
            return {"id": "synthetic-stream", "object": "chat.completion.chunk",
                    "created": 0, "model": "deepseek-v4-pro",
                    "choices": [] if delta is None else [
                        {"index": 0, "delta": delta, "finish_reason": finish}],
                    "usage": usage}
        data = [
            chunk({"role": "assistant", "content": "an", "reasoning_content": "rea",
                   "opaque_delta": "delta-marker", "tool_calls": [
                       {"index": 0, "id": "c-1", "type": "function",
                        "function": {"name": "lookup", "arguments": '{"x":'}},
                       {"index": 1, "id": "c-2", "type": "function",
                        "function": {"name": "lookup", "arguments": '{"x":'}},
                   ]}),
            chunk({"content": "swer", "reasoning_content": "son", "tool_calls": [
                {"index": 1, "function": {"arguments": "2}"}},
                {"index": 0, "function": {"arguments": "1}"}},
            ]}),
            chunk({}, "tool_calls"),
            chunk(usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}),
        ]
        body = "".join("data: " + json.dumps(item) + "\n\n" for item in data) + "data: [DONE]\n\n"
        model = self.model(lambda request, count: httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=body))
        with tracing_context(enabled=False):
            chunks = list(model.bind_tools([TOOL_SCHEMA]).stream("synthetic"))
        self.assertTrue(self.requests[0]["stream"])
        self.assertTrue(all(model_content_view(item).is_partial for item in chunks))
        result = chunks[0]
        for item in chunks[1:]:
            result = result + item
        self.assertEqual("answer", result.content)
        self.assertEqual("reason", result.additional_kwargs["reasoning_content"])
        self.assertEqual([{"x": 1}, {"x": 2}], [call["args"] for call in result.tool_calls])
        self.assertEqual(["c-1", "c-2"], [call["id"] for call in result.tool_calls])
        self.assertEqual(5, result.usage_metadata["total_tokens"])
        self.assertEqual("tool_calls", result.response_metadata["finish_reason"])
        self.assertNotIn("delta-marker", json.dumps(message_to_dict(result)))
        self.assertEqual(message_to_dict(result),
                         message_to_dict(messages_from_dict([message_to_dict(result)])[0]))

    def test_sdk_refusal_and_http_error_are_not_fabricated_success(self):
        from openai import BadRequestError
        def handler(request, count):
            if count == 1:
                return httpx2.Response(200, json=completion("", "", refusal="synthetic-refusal"))
            return httpx2.Response(400, json={"error": {"message": "synthetic-error",
                                                      "type": "invalid_request_error"}})
        model = self.model(handler)
        with tracing_context(enabled=False):
            result = model.invoke("synthetic")
            self.assertEqual("synthetic-refusal", result.additional_kwargs["refusal"])
            with self.assertRaises(BadRequestError):
                model.invoke("synthetic")
        self.assertEqual(2, len(self.requests))  # max_retries=0, no fallback.
