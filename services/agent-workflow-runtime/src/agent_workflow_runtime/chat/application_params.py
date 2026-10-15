"""Recoverable model-input rejection before any Application activation or generation."""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError
from langchain_core.tools import ToolException

from ..models import ActionRejected

# Bound model-visible diagnostics without including rejected input values.
_MAX_DIAGNOSTICS = 8


class ApplicationParamsRejected(ToolException):
    """Only raised by local preflight before dispatch; never wraps remote failures."""

    def __init__(self, app_code: str, schema: dict[str, Any], errors: list[dict[str, str]]) -> None:
        super().__init__("A2UI_PARAMS_INVALID")
        self.payload = {
            "errorCode": "A2UI_PARAMS_INVALID",
            "dispatch": "NOT_STARTED",
            "appCode": app_code,
            "paramsSchema": schema,
            "errors": errors,
            "guidance": (
                "Correct params using this current Application contract. Params are not "
                "arbitrary business output. Reuse already obtained business results; "
                "do not repeat a successful business query to repair rendering parameters. "
                "No activation, card save or generation model call was performed."
            ),
        }


def application_params_error_content(error: ToolException) -> str:
    """The native SDK returns status=error; no other ToolException is recoverable."""
    if not isinstance(error, ApplicationParamsRejected):
        raise error
    return json.dumps(error.payload, ensure_ascii=False, allow_nan=False)


def _pointer(parts: list[str | int]) -> str:
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _safe_instance_path(schema: dict[str, Any], parts: list[str | int]) -> str:
    # Unknown object keys can contain user values. Only publish schema-declared
    # property names and array offsets, never validation.message or instance data.
    current: Any = schema
    safe: list[str | int] = []
    for part in parts:
        if not isinstance(current, dict):
            break
        if isinstance(part, str):
            properties = current.get("properties", {})
            if not isinstance(properties, dict) or part not in properties:
                break
            current = properties[part]
        elif type(part) is int:
            items = current.get("items", {})
            if isinstance(items, list):
                if not 0 <= part < len(items):
                    break
                current = items[part]
            else:
                current = items
        else:
            break
        safe.append(part)
    return _pointer(safe)


def validate_application_params(
    app_code: str, schema: dict[str, Any], params: dict[str, Any],
) -> None:
    """Match the downstream A2UI execution service's Draft7 validation dialect."""
    try:
        Draft7Validator.check_schema(schema)
    except SchemaError:
        raise ActionRejected("APPLICATION_CONTRACT_INVALID") from None
    errors = []
    for error in Draft7Validator(schema).iter_errors(params):
        errors.append({
            "keyword": str(error.validator),
            "path": _safe_instance_path(schema, list(error.absolute_path)),
            "schemaPath": _pointer(list(error.absolute_schema_path)),
        })
        if len(errors) == _MAX_DIAGNOSTICS:
            break
    if errors:
        raise ApplicationParamsRejected(app_code, schema, errors)
