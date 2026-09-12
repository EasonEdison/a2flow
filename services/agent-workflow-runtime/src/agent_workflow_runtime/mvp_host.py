"""MVP08 authenticated, same-origin host. No listener or implicit identity."""

from functools import partial
from pathlib import Path

from fastapi import Request
from starlette.staticfiles import StaticFiles

from .http import _Lane, create_app, error_response, bounded_response
from .models import ActionRejected
from .service import require_owner


class VerifiedIdentity:
    """The injected resolver is the host trust boundary, never a browser selector."""

    def __init__(self, app, resolver):
        if not callable(resolver):
            raise ValueError("VERIFIED_IDENTITY_RESOLVER_REQUIRED")
        self.app, self.resolver = app, resolver

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        clean = {key: value for key, value in scope.items() if key != "a2flow.trusted_context"}
        try:
            owner = require_owner(self.resolver(clean))
        except Exception:
            return await error_response(401, "TRUSTED_CONTEXT_REQUIRED")(scope, receive, send)
        clean["a2flow.trusted_context"] = owner
        await self.app(clean, receive, send)


def create_mvp_app(
    service, views, workflow_catalog, identity_resolver, *, lifespan=None,
    static_directory=None, read_capacity=2, read_timeout=3,
    unexpected_error_observer=None,
):
    if not callable(identity_resolver):
        raise ValueError("VERIFIED_IDENTITY_RESOLVER_REQUIRED")
    app = create_app(
        service, read_capacity=read_capacity, read_timeout=read_timeout,
        unexpected_error_observer=unexpected_error_observer,
    )
    if lifespan is not None:
        app.router.lifespan_context = lifespan
    reads = _Lane(read_capacity)

    def options(request, *, paged=False):
        owner = require_owner(request.scope.get("a2flow.trusted_context"))
        pairs = request.query_params.multi_items()
        allowed = {"limit", "after"} if paged else set()
        if (len(pairs) != len(dict(pairs)) or set(dict(pairs)) - allowed
                or request.headers.get("last-event-id") is not None):
            raise ActionRejected("INVALID_SERVICE_INPUT")
        raw = request.query_params.get("limit", "20")
        if not raw.isascii() or not raw.isdecimal() or not 1 <= int(raw) <= 100:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        return owner, request.query_params.get("after"), int(raw)

    @app.get("/runtime/session")
    async def session(request: Request):
        owner, _, _ = options(request)
        return bounded_response({"userId": owner.user_id, "environment": owner.environment})

    @app.get("/runtime/runs")
    async def runs(request: Request):
        owner, after, limit = options(request, paged=True)
        return await reads.call(partial(views.runs, owner, after=after, limit=limit), timeout=read_timeout)

    @app.get("/runtime/runs/{run_id}/view")
    async def view(request: Request, run_id: str):
        owner, _, _ = options(request)
        return await reads.call(partial(views.view, owner, run_id), timeout=read_timeout)

    @app.get("/runtime/workflows")
    async def workflows(request: Request):
        owner, after, limit = options(request, paged=True)
        return await reads.call(partial(workflow_catalog, owner, after=after, limit=limit), timeout=read_timeout)

    if static_directory is not None:
        directory = Path(static_directory).resolve(strict=True)
        if not directory.is_dir():
            raise ValueError("STATIC_DIRECTORY_REQUIRED")
        app.mount("/", StaticFiles(directory=directory, html=True), name="digital-employee")
    return VerifiedIdentity(app, identity_resolver)
