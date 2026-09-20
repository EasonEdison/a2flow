"""Hand-authored native-core fixtures, NOT DeepSeek ingress/request evidence."""

import unittest

from langchain_core.messages import (
    AIMessage, AIMessageChunk, HumanMessage, ToolMessage,
    message_chunk_to_message, message_to_dict, messages_from_dict,
)

from agent_workflow_runtime.model_content import model_content_view


class ModelContentTest(unittest.TestCase):
    def test_standard_blocks_preserve_sdk_order_ids_signatures_and_extensions(self):
        blocks = [
            {"type": "reasoning", "reasoning": "synthetic reasoning",
             "id": "r-1", "extras": {"signature": "opaque-signature"}},
            {"type": "text", "text": "synthetic text", "index": 1},
            {"type": "non_standard", "value": {"opaque": [1, {"signed": "exact"}]}},
        ]
        message = AIMessage(content=blocks, response_metadata={"output_version": "v1"})
        before = message_to_dict(message)
        view = model_content_view(message)
        self.assertEqual(tuple(blocks), view.blocks)
        self.assertFalse(view.is_partial)
        view.blocks[0]["extras"]["signature"] = "changed-view-only"
        self.assertEqual(before, message_to_dict(message))

    def test_native_reasoning_tool_calls_and_envelope_are_detached(self):
        message = AIMessage(
            content="answer", id="native-id", name="assistant-name",
            additional_kwargs={"reasoning_content": "returned reasoning",
                               "opaque": {"signed": ["exact"]}, "refusal": None},
            tool_calls=[{"name": "lookup", "args": {"x": 1}, "id": "c-1", "type": "tool_call"}],
            response_metadata={"finish_reason": "tool_calls", "model_name": "synthetic",
                               "request_id": "request-1", "unknown": {"v": [1]}},
            usage_metadata={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
            future_extension={"signed": ["native-extra"]},
        )
        before = message_to_dict(message)
        view = model_content_view(message)
        self.assertEqual(message.content_blocks, list(view.blocks))
        self.assertTrue(any(b["type"] == "reasoning" for b in view.blocks))
        self.assertTrue(any(b["type"] == "tool_call" for b in view.blocks))
        self.assertEqual("native-id", view.message_id)
        self.assertEqual("assistant-name", view.name)
        self.assertEqual(message.usage_metadata, view.usage_metadata)
        view.additional_kwargs["opaque"]["signed"].append("view-only")
        view.response_metadata["unknown"]["v"].append(2)
        view.native_extensions["future_extension"]["signed"].append("view-only")
        view.usage_metadata["total_tokens"] = 999
        self.assertEqual(before, message_to_dict(message))

    def test_public_native_serialization_keeps_tool_and_no_tool_assistant_history(self):
        first = AIMessage(content="first", additional_kwargs={"reasoning_content": "prior-no-tool"})
        second = AIMessage(
            content="", additional_kwargs={"reasoning_content": "prior-tool", "signed": {"v": "exact"}},
            tool_calls=[{"name": "lookup", "args": {"x": 1}, "id": "c-1", "type": "tool_call"}],
            response_metadata={"finish_reason": "tool_calls", "unknown": {"x": 1}},
            future_extension={"opaque": [1, "two"]},
        )
        history = [HumanMessage(content="question"), first, HumanMessage(content="followup"),
                   second, ToolMessage(content="result", tool_call_id="c-1")]
        encoded = [message_to_dict(message) for message in history]
        restored = messages_from_dict(encoded)
        self.assertEqual(encoded, [message_to_dict(message) for message in restored])
        self.assertEqual("prior-no-tool", restored[1].additional_kwargs["reasoning_content"])
        self.assertEqual("prior-tool", restored[3].additional_kwargs["reasoning_content"])
        self.assertEqual({"opaque": [1, "two"]}, restored[3].model_extra["future_extension"])
        # This proves core storage only; it does not inspect any outgoing SDK request.

    def test_native_chunk_assembly_multiple_fragmented_calls_and_usage_only_tail(self):
        first = AIMessageChunk(
            content="an", id="stream-id", additional_kwargs={"reasoning_content": "rea"},
            tool_call_chunks=[
                {"name": "lookup", "args": '{"x":', "id": "c-1", "index": 0},
                {"name": '1004', "args": '{"y":', "id": "c-2", "index": 1},
            ],
        )
        second = AIMessageChunk(
            content="swer", additional_kwargs={"reasoning_content": "son"},
            tool_call_chunks=[
                {"name": None, "args": "1}", "id": None, "index": 0},
                {"name": None, "args": "2}", "id": None, "index": 1},
            ],
        )
        tail = AIMessageChunk(
            content="", response_metadata={"finish_reason": "tool_calls"},
            usage_metadata={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        )
        first_before = message_to_dict(first)
        self.assertTrue(model_content_view(first).is_partial)
        self.assertEqual(first_before, message_to_dict(first))
        accumulated = first + second + tail
        self.assertTrue(model_content_view(accumulated).is_partial)
        complete = message_chunk_to_message(accumulated)
        self.assertFalse(model_content_view(complete).is_partial)
        self.assertEqual("answer", complete.content)
        self.assertEqual("reason", complete.additional_kwargs["reasoning_content"])
        self.assertEqual([{"x": 1}, {"y": 2}], [call["args"] for call in complete.tool_calls])
        self.assertEqual(["c-1", "c-2"], [call["id"] for call in complete.tool_calls])
        self.assertEqual(5, complete.usage_metadata["total_tokens"])
        self.assertEqual("tool_calls", complete.response_metadata["finish_reason"])
        self.assertEqual(message_to_dict(complete),
                         message_to_dict(messages_from_dict([message_to_dict(complete)])[0]))
        # Native chunk parsing may expose partial args; no view calls any Tool.

    def test_refusal_and_unknown_states_are_opaque_not_success(self):
        message = AIMessage(content="", additional_kwargs={"refusal": "synthetic refusal"},
                            response_metadata={"finish_reason": "future-unknown"})
        view = model_content_view(message)
        self.assertEqual("synthetic refusal", view.additional_kwargs["refusal"])
        self.assertEqual("future-unknown", view.response_metadata["finish_reason"])
        self.assertEqual((), view.blocks)

    def test_repr_omits_content_and_metadata(self):
        view = model_content_view(AIMessage(
            content="PRIVATE-CONTENT", id="PRIVATE-ID",
            additional_kwargs={"reasoning_content": "PRIVATE-REASONING"},
            response_metadata={"request_id": "PRIVATE-REQUEST"},
        ))
        self.assertEqual("ModelContentView(is_partial=False)", repr(view))

    def test_other_message_roles_reject_without_echoing_input(self):
        with self.assertRaisesRegex(TypeError, "^AI_MESSAGE_REQUIRED$"):
            model_content_view(HumanMessage(content="PRIVATE"))
