"""Stable failure codes and HTTP status mapping for the b-side service."""

from __future__ import annotations


class BsideError(RuntimeError):
    """Intentional, stable, non-sensitive request failure."""

    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code = code
        self.status = status


class RemoteRuntimeError(RuntimeError):
    """The Runtime control interface rejected or failed a proxied request."""

    def __init__(self, code: str, status: int = 502):
        super().__init__(code)
        self.code = code
        self.status = status
