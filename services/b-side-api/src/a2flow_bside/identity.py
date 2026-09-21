"""Session identity resolution and fail-closed request guards for /api.

Client headers, bodies or query strings can never supply identity: the server
resolves the session cookie itself, exactly like the management preview host.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable
from skillweave_contracts.user_id import require_user_id

from . import auth
from .errors import BsideError

SESSION_COOKIE = "a2flow_bside_session"

_IDENTITY_HEADERS = frozenset({
    "x-a2flow-environment", "x-a2flow-role", "x-a2flow-roles",
    "x-a2flow-user-id", "x-environment", "x-role", "x-roles", "x-user-id",
})

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class RequestIdentity:
    userId: int
    username: str
    role: str

    def __post_init__(self):
        require_user_id(self.userId)


def parse_session_token(cookie_value: str | None) -> str | None:
    if not cookie_value:
        return None
    token = cookie_value.strip()
    if not 20 <= len(token) <= 128:
        return None
    return token


def require_origin(headers, browser_origin: str | tuple[str, ...]) -> None:
    origins = headers.getlist("origin")
    allowed = (browser_origin,) if isinstance(browser_origin, str) else browser_origin
    if len(origins) != 1 or origins[0] not in allowed:
        raise BsideError("ORIGIN_REQUIRED", 403)


def resolve_identity(cookie_value: str | None, *, sessions: object,
                     now: Callable[[], dt.datetime]) -> RequestIdentity | None:
    """Resolve the session cookie into an identity (may be None)."""
    token = parse_session_token(cookie_value)
    if token is None:
        return None
    value = sessions.find_identity(auth.hash_session_token(token), now())
    if value is None:
        return None
    return RequestIdentity(**value)
