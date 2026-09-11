"""DeepSeek-only public BaseChatModel adapter over the typed OpenAI SDK.

No SSE/HTTP parser, private provider override, alternate history or Agent loop.
Raw typed payloads are opaque native-message extensions, never outbound fields.
"""

import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage,
    convert_to_openai_messages,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from .model_config import DeepSeekConfiguration


class DeepSeekProtocolError(RuntimeError):
    """Stable codes only, with no response, prompts, secrets or arguments."""


def _reject(code):
    raise DeepSeekProtocolError(code)


def _arguments(raw):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _reject("DUPLICATE_TOOL_ARGUMENT")
            result[key] = value
        return result
    def constant(_):
        _reject("NON_FINITE_TOOL_ARGUMENT")
    try:
        value = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=constant)
    except (ValueError, TypeError):
        _reject("INVALID_COMPLETE_TOOL_ARGUMENTS")
    if type(value) is not dict:
        _reject("TOOL_ARGUMENTS_REQUIRE_OBJECT")
    try:
        json.dumps(value, allow_nan=False)
    except ValueError:
        _reject("NON_FINITE_TOOL_ARGUMENT")
    return value


def _usage(usage):
    if usage is None:
        return None
    value = {
        "input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }
    if any(type(n) is not int or n < 0 for n in value.values()):
        _reject("INVALID_TOKEN_USAGE")
    return value


def _reasoning(value):
    if value is not None and type(value) is not str:
        _reject("UNSUPPORTED_REASONING_FORMAT")
    return value


def _finish(reason, calls):
    if reason != ("tool_calls" if calls else "stop"):
        _reject("INCOMPLETE_OR_UNSUPPORTED_FINISH")


def _calls(calls):
    result, seen = [], set()
    for call in calls or ():
        if (call.type != "function" or type(call.id) is not str or not call.id or call.id in seen
                or type(call.function.name) is not str or not call.function.name):
            _reject("INVALID_TOOL_CALL_IDENTITY")
        seen.add(call.id)
        result.append({"type": "tool_call", "id": call.id, "name": call.function.name,
                       "args": _arguments(call.function.arguments)})
    return result


class _StreamProjection:
    """Project typed chunks; native addition owns reasoning/argument accumulation."""

    def __init__(self):
        self.accumulated = None
        self.finish_reason = None
        self.saw_usage = False
        self.identities = {}

    def project(self, chunk):
        raw = chunk.model_dump(mode="json")
        extra = {"deepseek_payloads": [{"payload": raw}]}
        metadata = {}
        first = self.accumulated is None
        if first:
            metadata = {"model_provider": "deepseek", "model_name": chunk.model, "id": chunk.id}
        if len(chunk.choices) > 1:
            _reject("MULTIPLE_CHOICES_UNSUPPORTED")
        content, tool_chunks = "", []
        if chunk.choices:
            choice = chunk.choices[0]
            if choice.index != 0:
                _reject("UNEXPECTED_CHOICE_INDEX")
            delta = choice.delta
            if self.finish_reason is not None and (
                delta.content or delta.tool_calls or getattr(delta, "reasoning_content", None)
            ):
                _reject("CONTENT_AFTER_FINISH")
            if delta.content is not None:
                if type(delta.content) is not str:
                    _reject("UNSUPPORTED_CONTENT_FORMAT")
                content = delta.content
            reasoning = _reasoning(getattr(delta, "reasoning_content", None))
            if reasoning is not None:
                extra["reasoning_content"] = reasoning
            if delta.refusal is not None:
                extra["refusal"] = delta.refusal
            for call in delta.tool_calls or ():
                if type(call.index) is not int or call.index < 0:
                    _reject("INVALID_TOOL_CHUNK_INDEX")
                identity = self.identities.setdefault(call.index, {})
                emitted = {"index": call.index, "id": None, "name": None, "args": ""}
                for key, value in (("id", call.id),
                                   ("name", call.function.name if call.function else None)):
                    if value is not None:
                        if key in identity and identity[key] != value:
                            _reject("CHANGING_TOOL_CHUNK_IDENTITY")
                        if key not in identity:
                            emitted[key] = value
                        identity[key] = value
                if call.type is not None and call.type != "function":
                    _reject("UNSUPPORTED_TOOL_CHUNK_TYPE")
                if call.function and call.function.arguments is not None:
                    if type(call.function.arguments) is not str:
                        _reject("INVALID_TOOL_ARGUMENT_FRAGMENT")
                    emitted["args"] = call.function.arguments
                tool_chunks.append(emitted)
            if choice.finish_reason is not None:
                if self.finish_reason is not None:
                    _reject("MULTIPLE_FINISH_MARKERS")
                self.finish_reason = choice.finish_reason
                metadata["finish_reason"] = choice.finish_reason
        usage = _usage(chunk.usage)
        if usage is not None:
            if self.saw_usage:
                _reject("MULTIPLE_USAGE_RECORDS_UNSUPPORTED")
            self.saw_usage = True
        message = AIMessageChunk(
            content=content,
            additional_kwargs=extra, response_metadata=metadata,
            tool_call_chunks=tool_chunks, usage_metadata=usage,
        )
        # Keep only native Tool fragments for strict completion validation, not
        # a second accumulated raw-response/history copy.
        tool_delta = AIMessageChunk(content="", tool_call_chunks=tool_chunks)
        self.accumulated = tool_delta if first else self.accumulated + tool_delta
        return ChatGenerationChunk(message=message)

    def validate_complete(self):
        if self.accumulated is None:
            _reject("EMPTY_PROVIDER_STREAM")
        seen = set()
        for call in self.accumulated.tool_call_chunks:
            if not call["id"] or not call["name"] or call["id"] in seen:
                _reject("INVALID_TOOL_CALL_IDENTITY")
            seen.add(call["id"])
            _arguments(call["args"])
        _finish(self.finish_reason, self.accumulated.tool_call_chunks)


class DeepSeekChat(BaseChatModel):
    """Native model using documented custom-model extension points.

    The explicit class name matches the pinned core's public custom-model naming
    convention; actual harness restrictions still require outgoing-request tests.
    Client instances are host-owned and excluded from model serialization/repr.
    """

    model_name: str
    configuration: DeepSeekConfiguration = Field(exclude=True, repr=False)
    client: object = Field(exclude=True, repr=False)
    async_client: object = Field(exclude=True, repr=False)

    @property
    def _llm_type(self):
        return "deepseek"

    @property
    def _identifying_params(self):
        return {"model_name": self.model_name}

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        if set(kwargs) - {"parallel_tool_calls", "stream"}:
            _reject("UNSUPPORTED_MODEL_OPTIONS")
        if "stream" in kwargs and type(kwargs["stream"]) is not bool:
            _reject("INVALID_STREAM_CONTROL")
        options = {"tools": [convert_to_openai_tool(tool) for tool in tools], **kwargs}
        if tool_choice is not None:
            options["tool_choice"] = tool_choice
        return self.bind(**options)

    def _request(self, messages, stop, stream, kwargs):
        kwargs = dict(kwargs)
        transport_stream = kwargs.pop("stream", stream)
        if type(transport_stream) is not bool or transport_stream != stream:
            _reject("INVALID_STREAM_CONTROL")
        if set(kwargs) - {"tools", "tool_choice", "parallel_tool_calls"}:
            _reject("UNSUPPORTED_MODEL_OPTIONS")
        if "parallel_tool_calls" in kwargs and type(kwargs["parallel_tool_calls"]) is not bool:
            _reject("INVALID_PARALLEL_TOOL_OPTION")
        tools = kwargs.get("tools")
        if tools is not None and (
            type(tools) is not list or any(
                type(tool) is not dict or tool.get("type") != "function" for tool in tools
            )
        ):
            _reject("UNSUPPORTED_TOOL_SCHEMA")
        converted = []
        roles = {HumanMessage: "user", SystemMessage: "system", AIMessage: "assistant", ToolMessage: "tool"}
        for message in messages:
            role = roles.get(type(message))
            if role is None:
                _reject("UNSUPPORTED_HISTORY_MESSAGE")
            content = message.content
            if not isinstance(content, str) and not (
                type(content) is list and all(
                    type(block) is dict and block.get("type") == "text"
                    and set(block) <= {"type", "text"} and type(block.get("text")) is str
                    for block in content
                )
            ):
                _reject("UNSUPPORTED_HISTORY_CONTENT")
            if isinstance(message, AIMessage):
                if message.invalid_tool_calls:
                    _reject("INVALID_HISTORY_TOOL_CALLS")
                try:
                    json.dumps(message.tool_calls, allow_nan=False)
                except (TypeError, ValueError):
                    _reject("INVALID_HISTORY_TOOL_ARGUMENTS")
                if set(message.additional_kwargs) & {"tool_calls", "function_call", "audio"}:
                    _reject("UNSUPPORTED_LEGACY_HISTORY_FIELDS")
            item = convert_to_openai_messages(message, pass_through_unknown_blocks=False)
            if not isinstance(item, dict) or item.get("role") != role:
                _reject("HISTORY_CONVERSION_ALIGNMENT_FAILED")
            if set(item) - {"role", "content", "name", "tool_calls", "tool_call_id"}:
                _reject("UNSUPPORTED_CONVERTED_HISTORY_FIELDS")
            if isinstance(message, AIMessage):
                reasoning = _reasoning(message.additional_kwargs.get("reasoning_content"))
                if tools and self.configuration.options.thinking == "enabled" and reasoning is None:
                    _reject("HISTORY_REASONING_REQUIRED")
                if reasoning is not None:
                    item["reasoning_content"] = reasoning
            converted.append(item)
        if len(converted) != len(messages):
            _reject("HISTORY_CONVERSION_ALIGNMENT_FAILED")
        params = {
            "model": self.model_name, "messages": converted, "stream": stream,
            **self.configuration.options.sdk_options(), **kwargs,
        }
        if stop is not None:
            if type(stop) is not list or any(type(value) is not str for value in stop):
                _reject("INVALID_STOP_OPTION")
            params["stop"] = stop
        if stream:
            params["stream_options"] = {"include_usage": True}
        return params

    @staticmethod
    def _result(response):
        if len(response.choices) != 1 or response.choices[0].index != 0:
            _reject("MULTIPLE_OR_INVALID_CHOICES")
        choice = response.choices[0]
        wire = choice.message
        if wire.content is not None and type(wire.content) is not str:
            _reject("UNSUPPORTED_CONTENT_FORMAT")
        calls = _calls(wire.tool_calls)
        _finish(choice.finish_reason, calls)
        extra = {"deepseek_payloads": [{"payload": response.model_dump(mode="json")}]}
        reasoning = _reasoning(getattr(wire, "reasoning_content", None))
        if reasoning is not None:
            extra["reasoning_content"] = reasoning
        if wire.refusal is not None:
            extra["refusal"] = wire.refusal
        message = AIMessage(
            content=wire.content or "", tool_calls=calls,
            additional_kwargs=extra, usage_metadata=_usage(response.usage),
            response_metadata={"model_provider": "deepseek", "model_name": response.model,
                               "id": response.id, "finish_reason": choice.finish_reason},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        params = self._request(messages, stop, False, kwargs)
        return self._result(self.client.chat.completions.create(**params))

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        params = self._request(messages, stop, False, kwargs)
        return self._result(await self.async_client.chat.completions.create(**params))

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        params = self._request(messages, stop, True, kwargs)
        projection = _StreamProjection()
        with self.client.chat.completions.create(**params) as stream:
            for chunk in stream:
                yield projection.project(chunk)
            projection.validate_complete()

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        params = self._request(messages, stop, True, kwargs)
        projection = _StreamProjection()
        async with await self.async_client.chat.completions.create(**params) as stream:
            async for chunk in stream:
                yield projection.project(chunk)
            projection.validate_complete()
