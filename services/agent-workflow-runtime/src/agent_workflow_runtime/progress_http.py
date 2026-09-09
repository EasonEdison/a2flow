"""Finite read-only SSE leases over committed pages, never graph generators."""

from functools import partial
import json
import re
from threading import BoundedSemaphore
from time import monotonic

import anyio
from fastapi import Request
from starlette.responses import StreamingResponse
from starlette.requests import ClientDisconnect

from .http import _Lane, error_response
from .models import ActionRejected
from .progress_writer import encoded
from .service import require_owner


def frame(event, value, event_id=None):
    data = encoded(value).decode("utf-8")
    value = (f"id: {event_id}\n" if event_id else "") + f"event: {event}\ndata: {data}\n\n"
    if len(value.encode("utf-8")) > 256 * 1024:
        raise ActionRejected("PROGRESS_FRAME_TOO_LARGE")
    return value.encode("utf-8")


class LeaseStream(StreamingResponse):
    def __init__(self, iterator, release, lease_seconds, send_timeout):
        super().__init__(iterator, media_type="text/event-stream",
                         headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no",
                                  "X-Progress-Lease-Seconds": str(lease_seconds)})
        self.release, self.lease_seconds, self.send_timeout = release, lease_seconds, send_timeout

    async def __call__(self, scope, receive, send):
        async def limited_send(message):
            with anyio.fail_after(self.send_timeout):
                await send(message)
        try:
            with anyio.move_on_after(self.lease_seconds):
                await super().__call__(scope, receive, limited_send)
        except (TimeoutError, OSError, ClientDisconnect):
            pass  # Only the observer is disconnected; there is no execution handle.
        finally:
            try:
                with anyio.CancelScope(shield=True):
                    with anyio.move_on_after(1):
                        await self.body_iterator.aclose()
            finally:
                self.release()


def add_progress_routes(app, service, *, read_capacity=2, subscriber_capacity=8,
                        lease_seconds=60, send_timeout=5, read_timeout=3):
    if (type(subscriber_capacity) is not int or not 1 <= subscriber_capacity <= 8
            or type(lease_seconds) not in (int, float) or not 0 < lease_seconds <= 60
            or type(send_timeout) not in (int, float) or not 0 < send_timeout <= 5):
        raise ValueError("INVALID_PROGRESS_TRANSPORT_LIMIT")
    reads = _Lane(read_capacity)
    subscribers = BoundedSemaphore(subscriber_capacity)

    def options(request, *, streaming=False):
        who = require_owner(request.scope.get("a2flow.trusted_context"))
        pairs = request.query_params.multi_items()
        if len(pairs) != len(dict(pairs)) or set(dict(pairs)) - {"after", "limit"}:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        raw_limit = request.query_params.get("limit", "100")
        if not re.fullmatch("[1-9][0-9]{0,2}", raw_limit) or int(raw_limit) > 100:
            raise ActionRejected("INVALID_PROGRESS_LIMIT")
        after = request.query_params.get("after")
        last = request.headers.get("last-event-id")
        if last is not None:
            if not streaming or after is not None:
                raise ActionRejected("INVALID_PROGRESS_CURSOR")
            after = last
        return who, after, int(raw_limit)

    @app.get("/runtime/runs/{run_id}/progress")
    async def catalog(request: Request, run_id: str):
        who, after, limit = options(request)
        return await reads.call(partial(service.progress_catalog, who, run_id,
                                        after=after, limit=limit), timeout=read_timeout)

    path = "/runtime/runs/{run_id}/nodes/{node_id}/executions/{execution_id}"

    @app.get(path + "/history")
    async def history(request: Request, run_id: str, node_id: str, execution_id: str):
        who, after, limit = options(request)
        return await reads.call(partial(service.progress_history, who, run_id, node_id, execution_id,
                                        after=after, limit=limit), timeout=read_timeout)

    @app.get(path + "/stream")
    async def stream(request: Request, run_id: str, node_id: str, execution_id: str):
        who, after, limit = options(request, streaming=True)
        if not subscribers.acquire(blocking=False):
            return error_response(503, "SUBSCRIBER_CAPACITY_EXHAUSTED")
        try:
            read = partial(service.progress_history, who, run_id, node_id, execution_id, limit=limit)
            first = await reads.call(partial(read, after=after), timeout=read_timeout)
            if first.status_code != 200:
                subscribers.release()
                return first
            page = json.loads(first.body)
        except BaseException:
            subscribers.release()
            raise

        async def observe():
            current, next_page = after, page
            heartbeat = monotonic()
            last_capture = None
            try:
                while True:
                    if next_page["capture"] != last_capture:
                        last_capture = next_page["capture"]
                        yield frame("capture", {"capture": last_capture,
                                                "statusReference": next_page["statusReference"],
                                                "nodeCompletion": False})
                    for record in next_page["records"]:
                        current = f"{execution_id}:{record['seq']}"
                        yield frame("progress", record, current)
                    current = next_page["nextCursor"]
                    if not next_page["hasMore"] and (
                        last_capture["sealed"] or last_capture.get("observation_outcome") == "UNAVAILABLE"
                    ):
                        yield frame("capture_end", {"nextCursor": current, "nodeCompletion": False,
                                                   "statusReference": next_page["statusReference"]})
                        return
                    if monotonic() - heartbeat >= 10:
                        yield frame("heartbeat", {"nextCursor": current, "reconnect": True})
                        heartbeat = monotonic()
                    await anyio.sleep(.5)
                    response = await reads.call(partial(read, after=current), timeout=read_timeout)
                    if response.status_code != 200:
                        yield frame("error", {"code": "PROGRESS_UNAVAILABLE", "nextCursor": current})
                        return
                    next_page = json.loads(response.body)
            except ActionRejected:
                yield frame("error", {"code": "PROGRESS_UNAVAILABLE", "nextCursor": current})

        return LeaseStream(observe(), subscribers.release, lease_seconds, send_timeout)
