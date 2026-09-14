"""Bounded ASGI adapter. The Host owns authentication and listener setup."""
from typing import Annotated, Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from .contracts import (
    ManagementError, PublicationTarget, TrustedManagementContext, identifier,
)

BODY_LIMIT = 1024 * 1024
RESPONSE_LIMIT = 2 * 1024 * 1024


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SaveDraft(_Closed):
    expectedRevision: int = Field(ge=0)
    document: dict[str, JsonValue]


class Target(_Closed):
    environment: str
    versionId: str = Field(min_length=1, max_length=256)
    channel: str
    grayUserIds: list[str] = Field(default_factory=list, max_length=1024)


class PreparePublication(_Closed):
    expectedRevision: int = Field(ge=0)
    target: Target


def _error(status, code):
    return JSONResponse({"error": {"code": code}}, status_code=status)


def _mapping(value):
    convert = getattr(value, "to_mapping", None)
    if callable(convert):
        return convert()
    if isinstance(value, tuple):
        return list(value)
    return value


def _response(value):
    response = JSONResponse(_mapping(value))
    if len(response.body) > RESPONSE_LIMIT:
        return _error(507, "OUTPUT_TOO_LARGE")
    return response


class BodyLimit:
    """Counts received bytes before framework JSON parsing."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > BODY_LIMIT:
                return await _error(413, "BODY_TOO_LARGE")(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body, delivered = b"".join(chunks), False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(service, *, identity_resolver):
    """Create an app without starting a listener.

    identity_resolver receives the server ASGI scope and must return an already
    authenticated TrustedManagementContext. This adapter never derives identity,
    role or environment from HTTP headers, query parameters or JSON.
    """
    if not callable(identity_resolver):
        raise ValueError("identity_resolver must be callable")
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.add_middleware(BodyLimit)

    def context(request):
        if request.query_params:
            raise ManagementError("QUERY_PARAMETERS_NOT_ALLOWED")
        try:
            value = identity_resolver(request.scope)
        except Exception:
            raise ManagementError("TRUSTED_CONTEXT_REQUIRED", 401) from None
        if type(value) is not TrustedManagementContext:
            raise ManagementError("TRUSTED_CONTEXT_REQUIRED", 401)
        return value

    def key_value(key):
        if type(key) is not str or not 1 <= len(key) <= 256:
            raise ManagementError("INVALID_ASSET_KEY")
        return identifier(key, "INVALID_ASSET_KEY")

    @app.exception_handler(RequestValidationError)
    async def request_invalid(request, error):
        return _error(400, "INVALID_INPUT")

    @app.exception_handler(ManagementError)
    async def management_error(request, error):
        return _error(error.status, error.code)

    @app.exception_handler(ValueError)
    async def value_error(request, error):
        return _error(400, "INVALID_INPUT")

    @app.exception_handler(Exception)
    async def unexpected(request, error):
        return _error(500, "INTERNAL_ERROR")

    @app.get("/management/assets/{kind}")
    def list_published(request: Request, kind: str):
        return _response(service.list_published(context(request), kind))

    @app.get("/management/assets/{kind}/{key:path}/draft")
    def get_draft(request: Request, kind: str, key: str):
        return _response(service.get_draft(
            context(request), kind, key_value(key)))

    @app.put("/management/assets/{kind}/{key:path}/draft")
    def save_draft(request: Request, kind: str, key: str, body: SaveDraft):
        return _response(service.save_draft(
            context(request), kind, key_value(key),
            body.expectedRevision, body.document))

    @app.post("/management/assets/{kind}/{key:path}/validate")
    def validate_draft(request: Request, kind: str, key: str):
        return _response(service.validate_draft(
            context(request), kind, key_value(key)))

    @app.post("/management/assets/{kind}/{key:path}/publication-plans")
    def prepare(request: Request, kind: str, key: str,
                      body: PreparePublication):
        who = context(request)
        target = PublicationTarget(
            body.target.environment, body.target.versionId,
            body.target.channel, tuple(body.target.grayUserIds))
        plan = service.prepare_publication(
            who, kind, key_value(key), body.expectedRevision, target)
        result = plan.to_mapping()
        result["status"] = "PREPARED_NOT_PUBLISHED"
        result["published"] = False
        return _response(result)

    @app.get("/management/assets/{kind}/{key:path}")
    def detail(request: Request, kind: str, key: str):
        return _response(service.get_published(
            context(request), kind, key_value(key)))

    return app
