"""Generic business-call execution: the platform's only entry into business code.

Business bundles register services behind a stable typed RPC protocol
(BusinessService). Ability definitions declare operationRefs of the form
``business-call:<service>.<method>``; the platform resolves, validates
against the authored JSON-schema subset, invokes and records. The platform
core never imports or understands business logic itself.
"""

from __future__ import annotations

import re
from typing import Callable, Protocol

from skillweave_contracts import TrustedContext

_REF = re.compile(
    r"^business-call:([A-Za-z0-9][A-Za-z0-9._:-]{0,127})"
    r"\.([A-Za-z0-9][A-Za-z0-9._:-]{0,127})$"
)


class BusinessService(Protocol):
    """Uniform RPC surface implemented by business bundles."""

    def invoke(self, *, service: str, method: str,
               arguments: dict, owner: TrustedContext) -> dict: ...


class BusinessRegistry:
    """Service name -> BusinessService, wired once by the composition root."""

    def __init__(self, services: dict[str, BusinessService]):
        self._services = dict(services)

    def invoke(self, service: str, method: str,
               arguments: dict, owner: TrustedContext) -> dict:
        handler = self._services.get(service)
        if handler is None:
            raise LookupError("BUSINESS_SERVICE_NOT_REGISTERED")
        return handler.invoke(
            service=service, method=method, arguments=arguments, owner=owner)

    def dispatcher(self, service: str, method: str) -> Callable:
        def execute(arguments: dict, owner: TrustedContext) -> dict:
            return self.invoke(service, method, arguments, owner)
        return execute


def parse_business_call_ref(ref: str) -> tuple[str, str]:
    """Return (service, method) for business-call:<service>.<method>."""
    match = _REF.fullmatch(ref)
    if match is None:
        raise ValueError("INVALID_BUSINESS_CALL_REF")
    return match.group(1), match.group(2)


def schema_validator(schema: dict) -> Callable[[object], bool]:
    """Validate against the JSON-schema subset used by authored definitions."""
    check = _subset_check(schema)
    return lambda value: check(value, schema)


def _subset_check(schema: dict) -> Callable:
    def check(value, node):
        if type(node) is not dict:
            return False
        kind = node.get("type")
        if kind == "object":
            if type(value) is not dict:
                return False
            if node.get("additionalProperties") is False:
                allowed = set(node.get("properties", {}))
                if set(value) - allowed:
                    return False
            if any(key not in value for key in node.get("required", [])):
                return False
            properties = node.get("properties", {})
            return all(
                key not in properties or check(item, properties[key])
                for key, item in value.items()
            )
        if kind == "string":
            if type(value) is not str:
                return False
            if "minLength" in node and len(value) < node["minLength"]:
                return False
            if "maxLength" in node and len(value) > node["maxLength"]:
                return False
            if "enum" in node and value not in node["enum"]:
                return False
            return True
        if kind == "integer":
            if type(value) is not int or type(value) is bool:
                return False
            if "minimum" in node and value < node["minimum"]:
                return False
            if "maximum" in node and value > node["maximum"]:
                return False
            return True
        if kind == "number":
            if type(value) not in (int, float) or type(value) is bool:
                return False
            if "minimum" in node and value < node["minimum"]:
                return False
            if "maximum" in node and value > node["maximum"]:
                return False
            return True
        if kind == "boolean":
            if type(value) is not bool:
                return False
            if "enum" in node and value not in node["enum"]:
                return False
            if "const" in node and value is not node["const"]:
                return False
            return True
        if kind == "array":
            if type(value) is not list:
                return False
            if "minItems" in node and len(value) < node["minItems"]:
                return False
            if "maxItems" in node and len(value) > node["maxItems"]:
                return False
            return "items" not in node or all(
                check(item, node["items"]) for item in value)
        return False

    return check
