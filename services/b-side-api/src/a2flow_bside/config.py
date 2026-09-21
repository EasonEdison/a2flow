"""Explicit environment configuration; every value is required (fail-closed)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_BSIDE_CONFIGURATION:" + name)
    return value


def browser_origin(value: str) -> str:
    """Exact browser origin for login and unsafe cookie-backed requests.

    Loopback is the safe private default; a public origin is an explicit
    operator decision (TLS should terminate in front). Path/query/userinfo
    are rejected. The exact-origin check still rejects cross-site calls.
    """
    if not isinstance(value, str):
        raise RuntimeError("INVALID_BSIDE_BROWSER_ORIGIN")
    parts = urlsplit(value)
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or "*" in parts.netloc
            or parts.username is not None or parts.password is not None
            or parts.path not in {"", "/"} or parts.query or parts.fragment):
        raise RuntimeError("INVALID_BSIDE_BROWSER_ORIGIN")
    origin = parts.scheme + "://" + parts.netloc
    if value not in {origin, origin + "/"}:
        raise RuntimeError("INVALID_BSIDE_BROWSER_ORIGIN")
    return origin


def runtime_url(value: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError("INVALID_BSIDE_RUNTIME_URL")
    parts = urlsplit(value)
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.path not in {"", "/"} or parts.query or parts.fragment):
        raise RuntimeError("INVALID_BSIDE_RUNTIME_URL")
    return parts.scheme + "://" + parts.netloc


def session_seconds(value: str) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        raise RuntimeError("INVALID_BSIDE_SESSION_SECONDS") from None
    if not 60 <= seconds <= 7 * 24 * 3600:
        raise RuntimeError("INVALID_BSIDE_SESSION_SECONDS")
    return seconds


@dataclass(frozen=True)
class BsideConfig:
    conninfo: str = field(repr=False)
    pepper: str = field(repr=False)
    browser_origin: str
    runtime_url: str
    environment: str
    namespace: str
    session_seconds: int
    browser_origins: tuple[str, ...] = ()

    def __post_init__(self):
        primary = browser_origin(self.browser_origin)
        origins = tuple(browser_origin(value) for value in (self.browser_origins or (primary,)))
        if primary not in origins or len({value.split(":", 1)[0] for value in origins}) != 1:
            raise RuntimeError("INVALID_BSIDE_BROWSER_ORIGINS")
        object.__setattr__(self, "browser_origin", primary)
        object.__setattr__(self, "browser_origins", origins)

    @classmethod
    def from_environment(cls):
        conninfo = _required("A2FLOW_BSIDE_DATABASE_URL")
        pepper = _required("A2FLOW_BSIDE_PEPPER")
        if len(pepper) < 16:
            raise RuntimeError("INVALID_BSIDE_PEPPER")
        environment = _required("A2FLOW_BSIDE_ENVIRONMENT")
        if environment not in {"PRT", "ONLINE"}:
            raise RuntimeError("INVALID_BSIDE_ENVIRONMENT")
        namespace = _required("A2FLOW_BSIDE_ASSET_NAMESPACE")
        return cls(
            conninfo=conninfo,
            pepper=pepper,
            browser_origin=browser_origin(
                _required("A2FLOW_BSIDE_BROWSER_ORIGIN")),
            runtime_url=runtime_url(_required("A2FLOW_BSIDE_RUNTIME_URL")),
            environment=environment,
            namespace=namespace,
            session_seconds=session_seconds(
                _required("A2FLOW_BSIDE_SESSION_SECONDS")),
            browser_origins=tuple(value.strip() for value in
                _required("A2FLOW_BSIDE_BROWSER_ORIGINS").split(","))
                if "A2FLOW_BSIDE_BROWSER_ORIGINS" in os.environ else (),
        )
