"""Lossless publication envelope for the Java compiler's RPC runtime assets.

The envelope does not reimplement the Java compiler or authorize execution.
Execution resolves the immutable Java publication again and compares its identity.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .records import AssetError, closed

PROFILE = "a2flow.java-rpc.v1"


def is_java_asset(definition: object) -> bool:
    return isinstance(definition, dict) and definition.get("runtimeProfile") == PROFILE


def validate_java_asset(kind: str, key: str, definition: dict[str, Any]) -> dict[str, Any]:
    closed(definition, {"runtimeProfile", "assetKey", "sourceId", "sourceDigest", "payloadDigest", "payloadJson"})
    if kind not in {"ABILITY", "APPLICATION"} or definition["runtimeProfile"] != PROFILE:
        raise AssetError("UNSUPPORTED_JAVA_RUNTIME_ASSET")
    for field in ("assetKey", "sourceId", "sourceDigest", "payloadDigest", "payloadJson"):
        if type(definition[field]) is not str or not definition[field]:
            raise AssetError("INVALID_JAVA_RUNTIME_ASSET")
    payload = definition["payloadJson"]
    # Ability publication identity hashes authoring-semantic fields, not the
    # serialized envelope with revision metadata. Keep that identity unchanged;
    # payloadDigest separately proves exact byte preservation across the bridge.
    digest = definition["payloadDigest"].removeprefix("sha256:")
    if not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", definition["sourceDigest"]):
        raise AssetError("JAVA_SOURCE_DIGEST_INVALID")
    if (len(payload.encode()) > 16 * 1024 * 1024 or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or hashlib.sha256(payload.encode()).hexdigest() != digest):
        raise AssetError("JAVA_SNAPSHOT_DIGEST_MISMATCH")
    try:
        parsed = json.loads(payload)
    except (ValueError, TypeError):
        raise AssetError("INVALID_JAVA_SNAPSHOT") from None
    if type(parsed) is not dict:
        raise AssetError("INVALID_JAVA_SNAPSHOT")
    # Retain the exact serialized compiler payload, including fields this layer
    # does not interpret. A Java runtime re-resolves it, never trusts this as a plan.
    if kind == "APPLICATION" and (parsed.get("appCode") != key or definition["assetKey"] != key):
        raise AssetError("JAVA_APPLICATION_KEY_MISMATCH")
    if kind == "ABILITY":
        draft = parsed.get("draft")
        basic = draft.get("basicInfo") if isinstance(draft, dict) else None
        if (parsed.get("draftId") != definition["assetKey"] or not isinstance(basic, dict)
                or basic.get("actionCode") != key):
            raise AssetError("JAVA_ABILITY_KEY_MISMATCH")
    if kind == "APPLICATION":
        catalog = parsed.get("catalog")
        if (not isinstance(catalog, dict) or not catalog.get("catalogId") or not catalog.get("digest")
                or not isinstance(parsed.get("componentTypes"), list)):
            raise AssetError("JAVA_COMPILED_CATALOG_REQUIRED")
    return parsed


def application_abilities(definition: dict[str, Any], key: str) -> set[str]:
    build = validate_java_asset("APPLICATION", key, definition)
    result: set[str] = set()
    for field in ("loadBindings", "actionBindings"):
        bindings = build.get(field)
        if not isinstance(bindings, list):
            raise AssetError("JAVA_COMPILED_BINDINGS_REQUIRED")
        for binding in bindings:
            capability = binding.get("capability") if isinstance(binding, dict) else None
            code = capability.get("actionCode") if isinstance(capability, dict) else None
            if not isinstance(code, str) or not code:
                raise AssetError("JAVA_COMPILED_CAPABILITY_REQUIRED")
            result.add(code)
    return result
