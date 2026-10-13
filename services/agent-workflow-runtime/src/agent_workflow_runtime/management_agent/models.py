"""Closed host contracts. Authority is never part of a model-visible tool schema."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from skillweave_contracts import TrustedContext

MAX_JSON_BYTES = 1024 * 1024
MAX_TURNS = 100


class AgentError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
        raise AgentError("INVALID_AGENT_IDENTIFIER")
    return value


def encode(value: object) -> bytes:
    try:
        result = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError):
        raise AgentError("INVALID_AGENT_JSON") from None
    if len(result) > MAX_JSON_BYTES:
        raise AgentError("AGENT_OUTPUT_TOO_LARGE")
    return result


def decode(value: bytes) -> Any:
    if len(value) > MAX_JSON_BYTES:
        raise AgentError("AGENT_OUTPUT_TOO_LARGE")
    try:
        result = json.loads(value)
        encode(result)
        return result
    except (TypeError, ValueError, UnicodeError):
        raise AgentError("INVALID_AGENT_JSON") from None


@dataclass(frozen=True)
class AgentIdentity:
    user_id: int
    namespace: str
    environment: str
    grant: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        TrustedContext(self.user_id, self.environment)
        identifier(self.namespace)
        if self.environment != "PRT":
            raise AgentError("MANAGEMENT_AGENT_PRT_ONLY")
        if not isinstance(self.grant, str) or (self.grant and not 16 <= len(self.grant) <= 4096):
            raise AgentError("MANAGEMENT_GRANT_REQUIRED")

    @property
    def scope(self) -> tuple[str, str, int]:
        return self.namespace, self.environment, self.user_id

    @property
    def owner(self) -> TrustedContext:
        return TrustedContext(self.user_id, self.environment)
