"""Native StateBackend reads restricted to this checkpoint's intermediate results."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import ToolMessage

from .models import AgentError

RESULT_PATH = re.compile(r"/(?:large_tool_results|conversation_history)/[A-Za-z0-9_.-]+")


def validate_result_read(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {"file_path", "offset", "limit"}:
        raise ValueError("SESSION_RESULT_ARGUMENT_INVALID")
    path = value.get("file_path")
    if not isinstance(path, str) or not RESULT_PATH.fullmatch(path):
        raise ValueError("SESSION_RESULT_PATH_FORBIDDEN")
    if path.rsplit("/", 1)[1] in {".", ".."}:
        raise ValueError("SESSION_RESULT_PATH_FORBIDDEN")
    offset, limit = value.get("offset", 0), value.get("limit", 100)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 2000:
        raise ValueError("SESSION_RESULT_WINDOW_INVALID")
    return value


def require_current_result(arguments: object, state: object) -> str:
    try:
        value = validate_result_read(arguments)
    except ValueError:
        raise AgentError("SESSION_RESULT_READ_FORBIDDEN") from None
    files = state.get("files", {}) if isinstance(state, dict) else {}
    path = value["file_path"]
    if not isinstance(files, dict) or path not in files:
        raise AgentError("SESSION_RESULT_NOT_IN_CURRENT_CONTEXT")
    assert isinstance(path, str)
    return path


def denied_result(call_id: str, code: str) -> ToolMessage:
    return ToolMessage(content=code, tool_call_id=call_id, name="read_file", status="error")
