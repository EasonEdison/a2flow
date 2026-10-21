"""Resolve the identity already authenticated by the app middleware."""

from typing import Annotated

from fastapi import Depends, Request

from .errors import BsideError
from .identity import RequestIdentity


def identity(request: Request) -> RequestIdentity:
    value = request.scope.get("a2flow.bside.identity")
    if not isinstance(value, RequestIdentity):
        raise BsideError("AUTHENTICATION_REQUIRED", 401)
    return value


CurrentIdentity = Annotated[RequestIdentity, Depends(identity)]
