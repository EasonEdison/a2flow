"""Resolve the identity already authenticated by the app middleware."""

from fastapi import Request

from .errors import BsideError
from .identity import RequestIdentity


def identity(request: Request) -> RequestIdentity:
    value = request.scope.get("a2flow.bside.identity")
    if not isinstance(value, RequestIdentity):
        raise BsideError("AUTHENTICATION_REQUIRED", 401)
    return value
