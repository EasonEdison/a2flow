"""Host-authored write confirmation. Model data never grants execution authority."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, cast

from skillweave_contracts import TrustedContext
from .models import ActionRejected, json_copy
from .rpc_client import AbilityDescription, freeze, thaw
from .temporary_interaction import TemporaryCandidate, prepare_interaction, validate_submission


def _plain_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and detach the same frozen JSON tree used by the RPC contract."""
    value = thaw(freeze(arguments))
    if not isinstance(value, dict):
        raise ActionRejected("INVALID_JSON")
    return cast(dict[str, Any], value)


def argument_bytes(arguments: Mapping[str, Any]) -> bytes:
    return json.dumps(_plain_arguments(arguments), ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def approval_required(description: AbilityDescription) -> bool:
    if (description.side_effect_level not in {"READ", "WRITE", "DESTRUCTIVE"}
            or description.approval_policy not in {"AUTO_EXECUTE", "REQUEST_APPROVAL"}):
        raise ActionRejected("CAPABILITY_GOVERNANCE_INVALID")
    if description.side_effect_level == "READ":
        return False
    if description.approval_policy != "REQUEST_APPROVAL":
        raise ActionRejected("CAPABILITY_GOVERNANCE_INVALID")
    return True


def prepare_confirmation(description: AbilityDescription, arguments: Mapping[str, Any]):
    if not approval_required(description):
        raise ActionRejected("WRITE_CONFIRMATION_NOT_REQUIRED")
    arguments = _plain_arguments(arguments)
    encoded = argument_bytes(arguments)
    if len(encoded) > 64 * 1024:
        raise ActionRejected("WRITE_CONFIRMATION_PARAMETERS_TOO_LARGE")
    candidate = TemporaryCandidate(
        title="确认写操作", mode="INTERACTIVE",
        components=[
            {"id": "root", "component": "Column", "children": ["purpose", "details", "choice", "submit"]},
            {"id": "purpose", "component": "Text", "text": {"path": "/data/purpose"}},
            {"id": "details", "component": "Text", "text": {"path": "/data/parameters"}},
            {"id": "choice", "component": "ChoicePicker", "label": "执行确认",
             "variant": "mutuallyExclusive", "options": [{"label": "我确认执行以上写操作", "value": "approve"}],
             "value": {"path": "/inputs/confirmation"}},
            {"id": "submit", "component": "Button", "child": "submitLabel",
             "action": {"event": {"name": "submit", "context": {
                 "confirmation": {"path": "/inputs/confirmation"}}}}},
            {"id": "submitLabel", "component": "Text", "text": "确认并执行"},
        ],
        inputSchema={"type": "object", "properties": {"confirmation": {
            "type": "array", "items": {"type": "string", "enum": ["approve"]},
            "minItems": 1, "maxItems": 1, "uniqueItems": True}},
            "required": ["confirmation"], "additionalProperties": False},
    )
    return prepare_interaction(candidate, {
        "purpose": "即将执行业务写操作：" + description.action_code + "。确认前不会发送业务请求。",
        "parameters": json.dumps(arguments, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2),
    })


def approval_binding(owner: TrustedContext, scope_id: str, tool_id: str,
                     ability_key: str, arguments: Mapping[str, Any], description: AbilityDescription) -> dict[str, Any]:
    if not scope_id or not tool_id or not approval_required(description):
        raise ActionRejected("WRITE_CONFIRMATION_BINDING_INVALID")
    arguments = _plain_arguments(arguments)
    return {"assetKey": description.asset_key, "abilityKey": ability_key,
            "arguments": arguments, "receipt": {
                "user_id": owner.user_id, "environment": owner.environment,
                "run_id": scope_id, "tool_call_id": tool_id,
                "action_code": description.action_code,
                "source_id": description.source_id, "source_digest": description.source_digest,
                "arguments_digest": hashlib.sha256(argument_bytes(arguments)).hexdigest(),
                "side_effect_level": description.side_effect_level,
                "approval_policy": description.approval_policy}}


def receipt_for(owner: TrustedContext, card_id: str, binding: dict[str, Any]) -> dict[str, Any]:
    """Call only after a durable same-owner confirmation/claim, never from tool args."""
    receipt = json_copy(binding["receipt"])
    if (receipt.get("user_id") != owner.user_id or receipt.get("environment") != owner.environment
            or receipt.get("arguments_digest") != hashlib.sha256(argument_bytes(binding["arguments"])).hexdigest()
            or not card_id):
        raise ActionRejected("WRITE_CONFIRMATION_BINDING_INVALID")
    return {**receipt, "receipt_id": card_id, "confirmation_id": card_id}


def require_confirmation(display, action_name, inputs):
    result = validate_submission(display, action_name, inputs)
    if result["values"] != {"confirmation": ["approve"]}:
        raise ActionRejected("WRITE_CONFIRMATION_REQUIRED")
    return result
