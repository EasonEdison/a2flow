"""Management browser authentication using the shared PostgreSQL accounts."""

from collections import deque
from datetime import datetime, timedelta, timezone
from http.cookies import CookieError, SimpleCookie
import secrets
import threading
import time
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from a2flow_bside.auth import (
    hash_password, verify_password, new_session_token, hash_session_token,
)
from a2flow_management import ManagementError, TrustedManagementContext
from .app import _headers, _IDENTITY_HEADERS, _UNSAFE_METHODS

_COOKIE = "a2flow_management_session"
_SECONDS = 7200
_LIMIT = 4096
_LOGIN_PATHS = {"/login", "/private-preview/login"}
_LOGOUT_PATHS = {"/logout", "/private-preview/logout"}


class AccountAuthentication:
    def __init__(self, *, users, sessions, pepper, environment, origins):
        self.users = users
        self.sessions = sessions
        self.pepper = pepper
        self.environment = environment
        self.origins = frozenset(origins)
        if not self.origins:
            raise RuntimeError("MANAGEMENT_BROWSER_ORIGIN_REQUIRED")
        if len({origin.split(":", 1)[0] for origin in origins}) != 1:
            raise RuntimeError("MIXED_MANAGEMENT_BROWSER_ORIGIN_SCHEMES")
        self.secure = all(origin.startswith("https://") for origin in origins)
        self._dummy_hash = hash_password(secrets.token_urlsafe(32), pepper=pepper)
        self._attempts = deque()
        self._lock = threading.Lock()

    def reject_identity(self, scope):
        if any(name.lower() in _IDENTITY_HEADERS for name, _ in scope.get("headers", ())):
            raise ManagementError("CLIENT_IDENTITY_FIELDS_NOT_ALLOWED", 400)

    def origin_allowed(self, scope):
        origins = _headers(scope, b"origin")
        if len(origins) != 1:
            return False
        try:
            origin = origins[0].decode("ascii")
        except UnicodeDecodeError:
            return False
        fetch_sites = _headers(scope, b"sec-fetch-site")
        return origin in self.origins and (not fetch_sites or fetch_sites == [b"same-origin"])

    def _token(self, scope):
        cookies = _headers(scope, b"cookie")
        if len(cookies) != 1:
            return None
        try:
            parsed = SimpleCookie()
            parsed.load(cookies[0].decode("ascii"))
            token = parsed[_COOKIE].value
            if len(token) != 43 or not all(c.isascii() and (c.isalnum() or c in "-_") for c in token):
                return None
            return token
        except (CookieError, KeyError, UnicodeDecodeError):
            return None

    def identity(self, scope):
        self.reject_identity(scope)
        # This mode deliberately never authenticates Authorization headers.
        if _headers(scope, b"authorization"):
            raise ManagementError("ACCOUNT_AUTHENTICATION_REQUIRED", 401)
        token = self._token(scope)
        if token is None:
            return None
        identity = self.sessions.find_identity(hash_session_token(token), datetime.now(timezone.utc))
        if not identity or identity["role"] not in {"ADMIN", "USER"}:
            return None
        return TrustedManagementContext(identity["userId"], self.environment, frozenset({identity["role"]}))

    def __call__(self, scope):
        principal = self.identity(scope)
        if principal is None:
            raise ManagementError("ACCOUNT_AUTHENTICATION_REQUIRED", 401)
        if scope.get("method") in _UNSAFE_METHODS and not self.origin_allowed(scope):
            raise ManagementError("ACCOUNT_ORIGIN_REQUIRED", 403)
        return principal

    def _admit(self, scope, username):
        # Bounded per-process limiter. Ignore untrusted forwarding headers.
        client = scope.get("client") or ("unknown", 0)
        address = client[0]
        now = time.monotonic()
        with self._lock:
            while self._attempts and self._attempts[0][0] < now - 60:
                self._attempts.popleft()
            if (len(self._attempts) >= 100 or
                    sum(item[1] == address for item in self._attempts) >= 20 or
                    sum(item[2] == username for item in self._attempts) >= 8):
                return False
            self._attempts.append((now, address, username))
            return True

    def login(self, username, password, scope):
        self.reject_identity(scope)
        if (_headers(scope, b"authorization") or not self.origin_allowed(scope)
                or not self._admit(scope, username)):
            return None
        user = self.users.find_by_username(username)
        encoded = user["password_hash"] if user else self._dummy_hash
        valid = verify_password(password, encoded, pepper=self.pepper)
        if not valid or not user or user["role"] not in {"ADMIN", "USER"}:
            return None
        token = new_session_token()
        self.sessions.create(token_sha256=hash_session_token(token), user_id=user["user_id"],
                             expires_at=datetime.now(timezone.utc) + timedelta(seconds=_SECONDS))
        return token

    def set_cookie(self, response, token):
        response.set_cookie(_COOKIE, token, max_age=_SECONDS, httponly=True,
                            secure=self.secure, samesite="strict", path="/")

    def logout(self, scope):
        self(scope)
        self.sessions.delete(hash_session_token(self._token(scope)))

    def delete_cookie(self, response):
        response.delete_cookie(_COOKIE, httponly=True, secure=self.secure,
                               samesite="strict", path="/")


def login_page(status=200):
    message = "<p role='alert'>账号或密码错误，请稍后重试。</p>" if status != 200 else ""
    response = HTMLResponse(
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>A2Flow 登录</title><style>body{font:16px system-ui;max-width:26rem;"
        "margin:12vh auto;padding:2rem;color:#1e293b;background:#f6f8fc}"
        "input,button{font:inherit;width:100%;padding:.8rem;margin:.5rem 0 1rem;"
        "box-sizing:border-box;border:1px solid #cbd5e1;border-radius:8px}"
        "button{background:#326bfb;color:white;cursor:pointer}</style>"
        "<h1>A2Flow 登录</h1>" + message + "<form method='post' action='/login'>"
        "<label>账号<input name='username' autocomplete='username' maxlength='128' required></label>"
        "<label>密码<input type='password' name='password' autocomplete='current-password' "
        "maxlength='1024' required></label><button type='submit'>登录</button></form></html>",
        status_code=status,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'")
    response.headers["Referrer-Policy"] = "same-origin"
    return response


def attach_account_browser(app, authentication, static_directory):
    @app.middleware("http")
    async def protect(request, call_next):
        try:
            authentication.reject_identity(request.scope)
            path = request.url.path
            if not (path.startswith("/management") or path in _LOGIN_PATHS | _LOGOUT_PATHS):
                if not await run_in_threadpool(authentication.identity, request.scope):
                    return RedirectResponse("/login", status_code=303)
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        except ManagementError as error:
            return JSONResponse({"error": {"code": error.code}}, status_code=error.status)

    @app.get("/private-preview/login")
    @app.get("/login")
    async def get_login(request: Request):
        if await run_in_threadpool(authentication.identity, request.scope):
            return RedirectResponse("/", status_code=303)
        return login_page()

    @app.post("/private-preview/login")
    @app.post("/login")
    async def post_login(request: Request):
        if (request.headers.get("content-type", "").split(";", 1)[0] != "application/x-www-form-urlencoded"
                or not authentication.origin_allowed(request.scope)):
            return login_page(401)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > _LIMIT:
                return login_page(401)
        try:
            values = parse_qs(body.decode("ascii"), keep_blank_values=True,
                              strict_parsing=True, max_num_fields=2, errors="strict")
            if set(values) != {"username", "password"} or any(len(v) != 1 for v in values.values()):
                raise ValueError
            username, password = values["username"][0], values["password"][0]
            if not 1 <= len(username) <= 128 or not 1 <= len(password) <= 1024:
                raise ValueError
        except (ValueError, UnicodeError):
            return login_page(401)
        token = await run_in_threadpool(authentication.login, username, password, request.scope)
        if token is None:
            return login_page(401)
        response = RedirectResponse("/", status_code=303)
        authentication.set_cookie(response, token)
        return response

    @app.post("/private-preview/logout")
    @app.post("/logout")
    async def logout(request: Request):
        await run_in_threadpool(authentication.logout, request.scope)
        response = RedirectResponse("/login", status_code=303)
        authentication.delete_cookie(response)
        return response

    app.mount("/", StaticFiles(directory=static_directory, html=True), name="management-ui")
