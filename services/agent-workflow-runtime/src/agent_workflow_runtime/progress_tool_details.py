"""Credential-safe tool observations; bounded frames, never business control.

Chunks must be assembled completely before JSON decoding. The existing writer
marks capture limits explicitly; a partial value is never a complete result.
Only ToolMessage.content is observed, not artifacts, provider metadata or state.
"""

from collections.abc import Mapping, Sequence
import json
from typing import Literal, Protocol

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from .chat.events import public_tool_result


# Even JSON control characters expand to at most six bytes each. This keeps
# an escaped chunk, identifiers and frame overhead below the 16 KiB frame cap.
CHUNK_CHARACTERS = 1024


class DetailSink(Protocol):
    unavailable: bool

    def emit(self, kind: str, payload: dict[str, str]) -> None: ...


def _emit_detail(
    sink: DetailSink, operation_id: str, call: Mapping[str, object],
    kind: Literal["arguments", "result"], value: object,
) -> None:
    """Observation failure affects capture health, never the tool's outcome."""
    if sink.unavailable:
        return
    try:
        text = json.dumps(public_tool_result(value), ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False)
        count = max(1, (len(text) + CHUNK_CHARACTERS - 1) // CHUNK_CHARACTERS)
        for index in range(count):
            if sink.unavailable:
                break
            sink.emit("TOOL_DETAIL", {
                "toolOperationId": operation_id,
                "toolName": str(call["name"]),
                "toolCallId": str(call.get("id") or ""),
                "detailKind": kind,
                "chunkIndex": str(index),
                "chunkCount": str(count),
                "text": text[index * CHUNK_CHARACTERS:(index + 1) * CHUNK_CHARACTERS],
            })
    except Exception:
        sink.unavailable = True


def emit_tool_arguments(
    sink: DetailSink, operation_id: str, call: Mapping[str, object],
) -> None:
    _emit_detail(sink, operation_id, call, "arguments", call.get("args", {}))


def _tool_message(result: object, call_id: str) -> ToolMessage | None:
    if isinstance(result, ToolMessage):
        return result
    if not isinstance(result, Command) or not isinstance(result.update, Mapping):
        return None
    messages = result.update.get("messages", ())
    if isinstance(messages, ToolMessage):
        messages = (messages,)
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        return None
    return next((message for message in reversed(messages)
                 if isinstance(message, ToolMessage) and message.tool_call_id == call_id), None)


def emit_tool_result(
    sink: DetailSink, operation_id: str, call: Mapping[str, object], result: object,
) -> None:
    message = _tool_message(result, str(call.get("id") or ""))
    if message is None:
        _emit_detail(sink, operation_id, call, "result", {
            "toolMessageStatus": None, "result": {"type": type(result).__name__},
        })
        return
    value: object = message.content
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            pass
    _emit_detail(sink, operation_id, call, "result", {
        "toolMessageStatus": message.status, "result": value,
    })
