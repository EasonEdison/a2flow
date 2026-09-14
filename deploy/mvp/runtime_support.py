"""Private-host configuration, persistent request budget and safe diagnostics."""

import asyncio
import fcntl
import json
import os
from pathlib import Path
import re
import threading
import traceback

import httpx
from psycopg.conninfo import make_conninfo
from pydantic import SecretStr

from agent_workflow_runtime.model_factory import DeepSeekModelFactory


_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,127}")
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,127}")
_DIAGNOSTIC_LIMIT = 256 * 1024


class ModelRequestBudgetGuard(RuntimeError):
    """A fixed local admission failure raised before provider dispatch."""


def required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_HOST_CONFIGURATION:" + name)
    return value


def bounded_int(name, default, minimum, maximum):
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise RuntimeError("INVALID_HOST_CONFIGURATION:" + name) from None
    if not minimum <= value <= maximum:
        raise RuntimeError("INVALID_HOST_CONFIGURATION:" + name)
    return value


def secret_file(name):
    path = Path(required(name))
    if not path.is_absolute() or not path.is_file():
        raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name)
    try:
        value = path.read_text(encoding="utf-8")
    except OSError:
        raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name) from None
    value = value.rstrip("\r\n")
    if not value or len(value) > 4096 or any(character.isspace() for character in value):
        raise RuntimeError("SECRET_FILE_INVALID:" + name)
    return value


def database_conninfo():
    return make_conninfo(
        host=required("A2FLOW_DATABASE_HOST"),
        port=bounded_int("A2FLOW_DATABASE_PORT", 5432, 1, 65535),
        dbname=required("A2FLOW_DATABASE_NAME"),
        user=required("A2FLOW_DATABASE_USER"),
        password=secret_file("A2FLOW_POSTGRES_PASSWORD_FILE"),
    )


class RequestBudget:
    """Persist exact admitted requests so a container restart cannot reset quota."""

    def __init__(self, path, limit, max_tokens):
        self.path = Path(path)
        if not self.path.is_absolute():
            raise RuntimeError("MODEL_BUDGET_PATH_INVALID")
        self.limit = limit
        self.max_tokens = max_tokens
        self._thread_lock = threading.Lock()

    def _admit_persisted(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "r+", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            raw = stream.read()
            if raw:
                try:
                    state = json.loads(raw)
                except (TypeError, ValueError):
                    raise ModelRequestBudgetGuard("MODEL_BUDGET_STATE_INVALID") from None
            else:
                state = {"schemaVersion": 1, "limit": self.limit, "calls": 0}
            if (type(state) is not dict or set(state) != {"schemaVersion", "limit", "calls"}
                    or state["schemaVersion"] != 1 or state["limit"] != self.limit
                    or type(state["calls"]) is not int or not 0 <= state["calls"] <= self.limit):
                raise ModelRequestBudgetGuard("MODEL_BUDGET_STATE_INVALID")
            if state["calls"] >= self.limit:
                raise ModelRequestBudgetGuard("MODEL_CALL_LIMIT_EXCEEDED")
            state["calls"] += 1
            stream.seek(0)
            stream.truncate()
            json.dump(state, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())

    def admit(self, request, body):
        if (request.method != "POST" or request.url.scheme != "https"
                or request.url.host != "api.deepseek.com"
                or request.url.port not in (None, 443)
                or not request.url.path.endswith("/chat/completions")):
            raise ModelRequestBudgetGuard("UNEXPECTED_PROVIDER_DESTINATION")
        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            raise ModelRequestBudgetGuard("INVALID_PROVIDER_REQUEST") from None
        if (payload.get("model") != "deepseek-v4-flash"
                or payload.get("max_tokens") != self.max_tokens
                or type(payload.get("stream")) is not bool):
            raise ModelRequestBudgetGuard("MODEL_BUDGET_NOT_APPLIED")
        with self._thread_lock:
            self._admit_persisted()


class SyncBudgetTransport(httpx.BaseTransport):
    def __init__(self, budget):
        self.budget = budget
        self.inner = httpx.HTTPTransport(retries=0)

    def handle_request(self, request):
        self.budget.admit(request, request.read())
        return self.inner.handle_request(request)

    def close(self):
        self.inner.close()


class AsyncBudgetTransport(httpx.AsyncBaseTransport):
    def __init__(self, budget):
        self.budget = budget
        self.inner = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        self.budget.admit(request, await request.aread())
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        await self.inner.aclose()


class BoundedDeepSeekFactory:
    def __init__(self, owner):
        self.owner = owner
        self.call_limit = bounded_int("A2FLOW_MODEL_CALL_LIMIT", 27, 1, 10000)
        self.max_tokens = bounded_int("A2FLOW_MODEL_MAX_TOKENS", 2048, 1, 8192)
        self.timeout = bounded_int("A2FLOW_MODEL_TIMEOUT_SECONDS", 20, 1, 120)
        self.budget = RequestBudget(
            required("A2FLOW_MODEL_BUDGET_FILE"), self.call_limit, self.max_tokens,
        )

    def configuration(self, reference, owner):
        if reference != "deepseek-v4-flash" or owner != self.owner:
            raise RuntimeError("MODEL_CONFIGURATION_NOT_FOUND")
        return {
            "model_id": "deepseek-v4-flash",
            "credential_ref": "file:deepseek",
            "timeout_seconds": float(self.timeout),
            "options": {
                "thinking": "enabled", "reasoning_effort": "low",
                "max_tokens": self.max_tokens,
            },
        }

    def secret(self, reference, owner):
        if reference != "file:deepseek" or owner != self.owner:
            raise RuntimeError("MODEL_CREDENTIAL_UNAVAILABLE")
        return SecretStr(secret_file("A2FLOW_DEEPSEEK_API_KEY_FILE"))

    def create(self, reference, owner):
        sync_client = httpx.Client(transport=SyncBudgetTransport(self.budget))
        async_client = httpx.AsyncClient(transport=AsyncBudgetTransport(self.budget))
        factory = DeepSeekModelFactory(
            self.configuration, self.secret,
            http_client=sync_client, http_async_client=async_client,
        )
        try:
            return factory.create(reference, owner)
        except Exception:
            sync_client.close()
            asyncio.run(async_client.aclose())
            raise


class SafeErrorObserver:
    """Append bounded structural diagnostics without messages, bodies or locals."""

    def __init__(self):
        self.path = Path(required("A2FLOW_SAFE_ERROR_FILE"))
        if not self.path.is_absolute():
            raise RuntimeError("SAFE_ERROR_PATH_INVALID")
        self._lock = threading.Lock()

    def __call__(self, error):
        try:
            exception_type = type(error).__name__
            if not _TOKEN.fullmatch(exception_type):
                exception_type = "UnknownError"
            code = str(error)
            if not _CODE.fullmatch(code):
                code = None
            frames = []
            for frame in traceback.extract_tb(error.__traceback__)[-4:]:
                filename = Path(frame.filename).name
                if _TOKEN.fullmatch(filename) and _TOKEN.fullmatch(frame.name):
                    frames.append({"file": filename, "line": frame.lineno, "function": frame.name})
            record = {
                "schemaVersion": 1,
                "category": ("MODEL_REQUEST_BUDGET_GUARD"
                             if isinstance(error, ModelRequestBudgetGuard) else "BACKEND_EXCEPTION"),
                "exceptionType": exception_type,
                "code": code,
                "frames": frames,
            }
            encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with self._lock:
                if self.path.exists() and self.path.stat().st_size + len(encoded) > _DIAGNOSTIC_LIMIT:
                    return
                descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                try:
                    os.write(descriptor, encoded)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        except Exception:
            pass
