"""Fail-closed private-preview Host for the four management modules.

Importing this module performs no database I/O, DDL, seed, model call, or
listener start. An operator must call one of the factories explicitly.
"""

from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
import hmac
import importlib
import ipaddress
import os
from pathlib import Path
import re
import secrets
import stat
import time
from urllib.parse import parse_qs, urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from a2flow_asset_store import AssetReader, PostgresAssetRepository
from a2flow_management import (
    ManagementError,
    PostgresDraftRepository,
    TrustedManagementContext,
)
from a2flow_management.assembly import create_management_app


_FACTORY = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:"
    r"[A-Za-z_][A-Za-z0-9_]*"
)
_IDENTITY_HEADERS = frozenset({
    b"x-a2flow-environment",
    b"x-a2flow-role",
    b"x-a2flow-roles",
    b"x-a2flow-user-id",
    b"x-environment",
    b"x-role",
    b"x-roles",
    b"x-user-id",
})
_LOGIN_PATH = "/private-preview/login"
_LOGOUT_PATH = "/private-preview/logout"
_SESSION_COOKIE = "a2flow_preview_session"
_SESSION_SECONDS = 2 * 60 * 60
_TOKEN_LIMIT = 4096
_TOKEN_MINIMUM = 32
_UNSAFE_METHODS = frozenset({"DELETE", "PATCH", "POST", "PUT"})


def _required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_HOST_CONFIGURATION:" + name)
    return value


def _load_validator(reference):
    if type(reference) is not str or not _FACTORY.fullmatch(reference):
        raise RuntimeError(
            "INVALID_HOST_CONFIGURATION:A2FLOW_MANAGEMENT_VALIDATOR_FACTORY")
    module_name, attribute = reference.split(":", 1)
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
        validator = factory()
    except Exception:
        raise RuntimeError("MANAGEMENT_VALIDATOR_UNAVAILABLE") from None
    if not callable(getattr(validator, "validate", None)):
        raise RuntimeError("MANAGEMENT_VALIDATOR_UNAVAILABLE")
    return validator


def _read_secret_file(name):
    path = _required(name)
    if not os.path.isabs(path):
        raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name)
    descriptor = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        no_follow = getattr(os, "O_NOFOLLOW", None)
        if no_follow is None:
            raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name)
        descriptor = os.open(path, flags | no_follow)
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()):
            raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name)
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError("SECRET_FILE_PERMISSIONS:" + name)
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            value = stream.read(_TOKEN_LIMIT + 3).rstrip(b"\r\n")
    except RuntimeError:
        raise
    except OSError:
        raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (not _TOKEN_MINIMUM <= len(value) <= _TOKEN_LIMIT
            or any(byte < 0x21 or byte > 0x7e for byte in value)):
        raise RuntimeError("SECRET_FILE_INVALID:" + name)
    return value


def _loopback(scope):
    server = scope.get("server")
    if not isinstance(server, (tuple, list)) or not server:
        return False
    host = server[0]
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _browser_origin(value):
    if value is None:
        return None
    if type(value) is not str:
        raise RuntimeError("INVALID_MANAGEMENT_BROWSER_ORIGIN")
    parts = urlsplit(value)
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.path not in {"", "/"} or parts.query or parts.fragment):
        raise RuntimeError("INVALID_MANAGEMENT_BROWSER_ORIGIN")
    # Loopback remains the safe private-preview default; a public origin is
    # allowed only as an explicit operator configuration and should terminate
    # TLS in front (the preview token and session cookie otherwise travel in
    # plaintext). The exact-origin check below still rejects cross-site calls.
    origin = parts.scheme + "://" + parts.netloc
    if value not in {origin, origin + "/"}:
        raise RuntimeError("INVALID_MANAGEMENT_BROWSER_ORIGIN")
    return origin


def _static_directory(value):
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        raise RuntimeError("MANAGEMENT_STATIC_DIRECTORY_UNAVAILABLE")
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        raise RuntimeError("MANAGEMENT_STATIC_DIRECTORY_UNAVAILABLE") from None
    if not resolved.is_dir() or not (resolved / "index.html").is_file():
        raise RuntimeError("MANAGEMENT_STATIC_DIRECTORY_UNAVAILABLE")
    return str(resolved)


def _headers(scope, name):
    return [
        value for header_name, value in (scope.get("headers") or ())
        if header_name.lower() == name
    ]


@dataclass(frozen=True)
class ManagementPreviewConfig:
    """Explicit database binding and server-owned principal."""

    conninfo: str = field(repr=False)
    database: str
    environment: str
    namespace: str
    user_id: str
    roles: frozenset[str]
    static_directory: str | None = None
    browser_origin: str | None = None
    guest_user_id: str | None = None

    def __post_init__(self):
        if type(self.conninfo) is not str or not self.conninfo:
            raise RuntimeError("EXPLICIT_DATABASE_CONNECTION_REQUIRED")
        if type(self.database) is not str or not self.database:
            raise RuntimeError("EXACT_DATABASE_REQUIRED")
        if type(self.namespace) is not str or not self.namespace:
            raise RuntimeError("EXACT_NAMESPACE_REQUIRED")
        TrustedManagementContext(
            self.user_id, self.environment, self.roles)
        if self.guest_user_id is not None:
            if type(self.guest_user_id) is not str or not self.guest_user_id:
                raise RuntimeError("INVALID_GUEST_PRINCIPAL")
            TrustedManagementContext(
                self.guest_user_id, self.environment, frozenset({"USER"}))
        static_directory = _static_directory(self.static_directory)
        browser_origin = _browser_origin(self.browser_origin)
        if (static_directory is None) != (browser_origin is None):
            raise RuntimeError("INCOMPLETE_MANAGEMENT_BROWSER_CONFIGURATION")
        object.__setattr__(self, "static_directory", static_directory)
        object.__setattr__(self, "browser_origin", browser_origin)

    @property
    def principal(self):
        return TrustedManagementContext(
            self.user_id, self.environment, self.roles)

    @property
    def guest_principal(self):
        if self.guest_user_id is None:
            return None
        return TrustedManagementContext(
            self.guest_user_id, self.environment, frozenset({"USER"}))

    @classmethod
    def from_environment(cls):
        raw_roles = _required("A2FLOW_MANAGEMENT_ROLES").split(",")
        if any(not role for role in raw_roles) or len(set(raw_roles)) != len(raw_roles):
            raise RuntimeError(
                "INVALID_HOST_CONFIGURATION:A2FLOW_MANAGEMENT_ROLES")
        guest_user_id = os.environ.get("A2FLOW_MANAGEMENT_GUEST_USER_ID")
        if guest_user_id == "":
            raise RuntimeError(
                "INVALID_HOST_CONFIGURATION:A2FLOW_MANAGEMENT_GUEST_USER_ID")
        return cls(
            conninfo=_required("A2FLOW_MANAGEMENT_DATABASE_URL"),
            database=_required("A2FLOW_MANAGEMENT_DATABASE_NAME"),
            environment=_required("A2FLOW_MANAGEMENT_ENVIRONMENT"),
            namespace=_required("A2FLOW_MANAGEMENT_ASSET_NAMESPACE"),
            user_id=_required("A2FLOW_MANAGEMENT_USER_ID"),
            roles=frozenset(raw_roles),
            static_directory=_required("A2FLOW_MANAGEMENT_STATIC_DIRECTORY"),
            browser_origin=_required("A2FLOW_MANAGEMENT_BROWSER_ORIGIN"),
            guest_user_id=guest_user_id,
        )


class _PreviewAuthentication:
    """Bearer for headless checks; HttpOnly session for the same-origin browser."""

    def __init__(self, token_pairs, browser_origin):
        for token, principal in token_pairs:
            if (type(token) is not bytes
                    or not _TOKEN_MINIMUM <= len(token) <= _TOKEN_LIMIT):
                raise RuntimeError("INVALID_PREVIEW_TOKEN")
            if type(principal) is not TrustedManagementContext:
                raise RuntimeError("INVALID_PREVIEW_PRINCIPAL")
        self._token_pairs = tuple(token_pairs)
        self._browser_origin = browser_origin
        self._session_state = (b"", 0.0, None)

    @property
    def browser_enabled(self):
        return self._browser_origin is not None

    @property
    def secure_cookie(self):
        return self._browser_origin.startswith("https://")

    def _reject_client_identity(self, scope):
        if any(name.lower() in _IDENTITY_HEADERS
               for name, _ in (scope.get("headers") or ())):
            raise ManagementError("CLIENT_IDENTITY_FIELDS_NOT_ALLOWED", 400)

    def _origin_allowed(self, scope):
        origins = _headers(scope, b"origin")
        if len(origins) != 1:
            return False
        try:
            origin = origins[0].decode("ascii")
        except UnicodeDecodeError:
            return False
        fetch_sites = _headers(scope, b"sec-fetch-site")
        if fetch_sites and fetch_sites != [b"same-origin"]:
            return False
        return hmac.compare_digest(origin, self._browser_origin)

    def _bearer(self, scope):
        authorizations = _headers(scope, b"authorization")
        if not authorizations:
            return False
        if len(authorizations) != 1:
            raise ManagementError("PREVIEW_AUTHENTICATION_REQUIRED", 401)
        value = authorizations[0]
        scheme, separator, provided = value.partition(b" ")
        if (separator != b" " or scheme.lower() != b"bearer" or not provided
                or len(provided) > _TOKEN_LIMIT):
            raise ManagementError("PREVIEW_AUTHENTICATION_REQUIRED", 401)
        for token, principal in self._token_pairs:
            if hmac.compare_digest(provided, token):
                return principal
        raise ManagementError("PREVIEW_AUTHENTICATION_REQUIRED", 401)

    def _session_cookie(self, scope):
        cookies = _headers(scope, b"cookie")
        if len(cookies) != 1:
            return False
        try:
            parsed = SimpleCookie()
            parsed.load(cookies[0].decode("ascii"))
            value = parsed[_SESSION_COOKIE].value.encode("ascii")
        except (CookieError, KeyError, UnicodeDecodeError, UnicodeEncodeError):
            return False
        session, expires_at, _ = self._session_state
        return (time.monotonic() < expires_at
                and hmac.compare_digest(value, session))

    def browser_authenticated(self, scope):
        return self.browser_enabled and self._session_cookie(scope)

    def login(self, supplied, scope):
        if not (self.browser_enabled and self._origin_allowed(scope)
                and type(supplied) is bytes):
            return False
        for token, principal in self._token_pairs:
            if hmac.compare_digest(supplied, token):
                self._session_state = (
                    secrets.token_urlsafe(32).encode("ascii"),
                    time.monotonic() + _SESSION_SECONDS,
                    principal,
                )
                return True
        return False

    def logout_allowed(self, scope):
        return self.browser_authenticated(scope) and self._origin_allowed(scope)

    def __call__(self, scope):
        if not _loopback(scope):
            raise ManagementError("PRIVATE_PREVIEW_LOOPBACK_REQUIRED", 403)
        self._reject_client_identity(scope)
        bearer = self._bearer(scope)
        if bearer is not False:
            return bearer
        if not self.browser_authenticated(scope):
            raise ManagementError("PREVIEW_AUTHENTICATION_REQUIRED", 401)
        if scope.get("method") in _UNSAFE_METHODS and not self._origin_allowed(scope):
            raise ManagementError("PREVIEW_ORIGIN_REQUIRED", 403)
        _, _, principal = self._session_state
        if principal is None:
            raise ManagementError("PREVIEW_AUTHENTICATION_REQUIRED", 401)
        return principal

    def set_cookie(self, response):
        session, expires_at, _ = self._session_state
        if not session or time.monotonic() >= expires_at:
            raise RuntimeError("PREVIEW_SESSION_UNAVAILABLE")
        response.set_cookie(
            _SESSION_COOKIE,
            session.decode("ascii"),
            max_age=_SESSION_SECONDS,
            httponly=True,
            secure=self.secure_cookie,
            samesite="strict",
            path="/",
        )

    def delete_cookie(self, response):
        self._session_state = (b"", 0.0, None)
        response.delete_cookie(
            _SESSION_COOKIE,
            httponly=True,
            secure=self.secure_cookie,
            samesite="strict",
            path="/",
        )


@dataclass(frozen=True)
class ManagementPreviewHost:
    """Inspectable composition result; it has not connected to PostgreSQL."""

    config: ManagementPreviewConfig
    reader: AssetReader
    drafts: PostgresDraftRepository
    app: object


def _login_page(status=200):
    message = "<p>Authentication failed.</p>" if status != 200 else ""
    response = HTMLResponse(
        "<!doctype html><meta charset=utf-8><meta name=viewport "
        "content='width=device-width,initial-scale=1'>"
        "<title>A2Flow private preview</title>"
        "<style>body{font:16px system-ui;max-width:32rem;margin:10vh auto;"
        "padding:2rem}input,button{font:inherit;width:100%;padding:.7rem;"
        "margin:.4rem 0;box-sizing:border-box}</style>"
        "<h1>A2Flow private preview</h1>"
        "<p>Enter the administrator token (editing) or the visitor token "
        "(read-only). It is exchanged for a two-hour, process-local HttpOnly "
        "session and is never placed in the UI bundle.</p>"
        + message
        + "<form method=post action='" + _LOGIN_PATH + "'>"
        "<label>Preview token<input type=password name=token required "
        "autocomplete=current-password></label>"
        "<button type=submit>Continue</button></form>",
        status_code=status,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'")
    response.headers["Referrer-Policy"] = "same-origin"
    return response


def _attach_browser(app, authentication, static_directory):
    @app.middleware("http")
    async def protect_static(request, call_next):
        if not _loopback(request.scope):
            return JSONResponse(
                {"error": {"code": "PRIVATE_PREVIEW_LOOPBACK_REQUIRED"}},
                status_code=403,
            )
        path = request.url.path
        if path.startswith("/management") or path in {_LOGIN_PATH, _LOGOUT_PATH}:
            return await call_next(request)
        if not authentication.browser_authenticated(request.scope):
            return RedirectResponse(_LOGIN_PATH, status_code=303)
        return await call_next(request)

    @app.get(_LOGIN_PATH)
    async def login_page(request: Request):
        if authentication.browser_authenticated(request.scope):
            return RedirectResponse("/", status_code=303)
        return _login_page()

    @app.post(_LOGIN_PATH)
    async def login(request: Request):
        content_type = request.headers.get("content-type", "").split(";", 1)[0]
        if content_type != "application/x-www-form-urlencoded":
            return _login_page(401)
        body = await request.body()
        if len(body) > _TOKEN_LIMIT + 32:
            return _login_page(401)
        try:
            values = parse_qs(
                body.decode("ascii"),
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=1,
            )
            supplied = values["token"]
            if set(values) != {"token"} or len(supplied) != 1:
                raise ValueError
            token = supplied[0].encode("ascii")
        except (KeyError, UnicodeDecodeError, UnicodeEncodeError, ValueError):
            return _login_page(401)
        if not authentication.login(token, request.scope):
            return _login_page(401)
        response = RedirectResponse("/", status_code=303)
        authentication.set_cookie(response)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post(_LOGOUT_PATH)
    async def logout(request: Request):
        if not authentication.logout_allowed(request.scope):
            return HTMLResponse("Forbidden", status_code=403)
        response = RedirectResponse(_LOGIN_PATH, status_code=303)
        authentication.delete_cookie(response)
        response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/", StaticFiles(directory=static_directory, html=True), name="preview-ui")


def create_management_preview_host(config, *, validator, bearer_token,
                                   guest_token=None):
    """Build the protected ASGI Host without setup, seed, or connection attempts."""
    if type(config) is not ManagementPreviewConfig:
        raise RuntimeError("INVALID_MANAGEMENT_PREVIEW_CONFIG")
    token_pairs = [(bearer_token, config.principal)]
    if guest_token is not None:
        if config.guest_principal is None:
            raise RuntimeError("GUEST_PRINCIPAL_REQUIRED")
        token_pairs.append((guest_token, config.guest_principal))
    repository = PostgresAssetRepository(
        config.conninfo,
        environment=config.environment,
        database=config.database,
        validator=validator,
    )
    reader = AssetReader(repository, config.namespace)
    drafts = PostgresDraftRepository(
        config.conninfo,
        environment=config.environment,
        database=config.database,
    )
    identity = _PreviewAuthentication(token_pairs, config.browser_origin)
    assembly = create_management_app(
        reader=reader,
        drafts=drafts,
        namespace=config.namespace,
        identity_resolver=identity,
    )
    if config.static_directory is not None:
        _attach_browser(assembly.app, identity, config.static_directory)
    return ManagementPreviewHost(config, reader, drafts, assembly.app)


def create_management_preview_app(config, *, validator, bearer_token,
                                  guest_token=None):
    """Return only the ASGI app for programmatic Host assembly."""
    return create_management_preview_host(
        config, validator=validator, bearer_token=bearer_token,
        guest_token=guest_token).app


def create_app_from_environment():
    """Uvicorn factory; every value is explicit protected Host configuration."""
    config = ManagementPreviewConfig.from_environment()
    validator = _load_validator(
        _required("A2FLOW_MANAGEMENT_VALIDATOR_FACTORY"))
    token = _read_secret_file("A2FLOW_MANAGEMENT_AUTH_TOKEN_FILE")
    guest_token = None
    if os.environ.get("A2FLOW_MANAGEMENT_GUEST_TOKEN_FILE"):
        guest_token = _read_secret_file(
            "A2FLOW_MANAGEMENT_GUEST_TOKEN_FILE")
    return create_management_preview_app(
        config, validator=validator, bearer_token=token,
        guest_token=guest_token)
