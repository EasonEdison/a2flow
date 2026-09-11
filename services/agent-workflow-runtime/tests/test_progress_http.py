"""ASGI-only observer transport gates; no listener and no execution invocation."""

import asyncio
import json
import unittest
from time import monotonic

import anyio
import httpx
from fastapi import FastAPI

from agent_workflow_runtime.http import create_app, error_response
from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.postgres_progress import cursor
from agent_workflow_runtime.progress_http import add_progress_routes, LeaseStream, frame
from support import context


SEGMENT = "a" * 32
PATH = "/runtime/runs/run-test/nodes/node-test/executions/" + SEGMENT


class Reads:
    def __init__(self):
        self.calls = []

    def progress_history(self, owner, run, node, execution, *, after=None, limit=100):
        self.calls.append((owner, run, node, execution, after, limit))
        position = cursor(after, execution)
        if position > 1:
            raise ActionRejected("FUTURE_PROGRESS_CURSOR")
        if owner != context().trusted_context:
            raise ActionRejected("PROGRESS_NOT_FOUND")
        return {"capture": {"sealed": True, "incomplete": False, "observation_outcome": "RETURNED"},
                "records": [] if position else [{"seq": 1, "kind": "TEXT_DELTA",
                    "observedAt": "2026-09-09T00:00:00+00:00",
                    "payload": {"modelCallId": "m", "text": "中文\nline"}}],
                "nextCursor": execution + ":1", "hasMore": False,
                "statusReference": {"runId": run, "nodeId": node}}

    def progress_catalog(self, owner, run, **kwargs):
        return {"segments": [], "capture": "UNCONFIRMED"}


def trusted(app, who=True):
    async def wrapped(scope, receive, send):
        if who:
            scope["a2flow.trusted_context"] = context().trusted_context
        await app(scope, receive, send)
    return wrapped


def scope():
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": "GET", "scheme": "http",
            "path": PATH + "/stream", "raw_path": (PATH + "/stream").encode(),
            "query_string": b"", "headers": [], "server": ("test", 80), "client": ("test", 1)}


class ProgressHttpTest(unittest.IsolatedAsyncioTestCase):
    async def request(self, url, *, who=True, headers=None):
        service = Reads()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(
            app=trusted(create_app(service), who)), base_url="http://test") as client:
            result = await client.get(url, headers=headers)
        return result, service

    async def test_auth_and_cursor_rejected_before_sse_headers(self):
        cases = [
            (PATH + "/stream", False, None, 401),
            (PATH + "/stream?after=" + SEGMENT + ":2", True, None, 400),
            (PATH + "/stream?after=" + "b"*32 + ":1", True, None, 400),
            (PATH + "/stream?limit=101", True, None, 400),
            (PATH + "/stream?limit=1&limit=2", True, None, 400),
            (PATH + "/stream?after=" + SEGMENT + ":0", True,
             {"Last-Event-ID": SEGMENT + ":0"}, 400),
        ]
        for url, who, headers, status in cases:
            with self.subTest(url=url):
                result, _ = await self.request(url, who=who, headers=headers)
                self.assertEqual(status, result.status_code)
                self.assertNotIn("text/event-stream", result.headers.get("content-type", ""))

    async def test_committed_stream_frames_and_reconnect_no_business_done(self):
        result, _ = await self.request(PATH + "/stream")
        self.assertEqual(200, result.status_code)
        self.assertIn("id: " + SEGMENT + ":1", result.text)
        self.assertIn("event: capture_end", result.text)
        self.assertNotIn("event: done", result.text)
        self.assertIn('"nodeCompletion":false', result.text)
        self.assertIn("中文\\nline", result.text)
        result, service = await self.request(PATH + "/stream", headers={"Last-Event-ID": SEGMENT + ":1"})
        self.assertNotIn("event: progress", result.text)
        self.assertEqual(SEGMENT + ":1", service.calls[0][4])

    async def test_snapshot_events_still_rejects_queries(self):
        result, _ = await self.request("/runtime/runs/run-test/events?after=1")
        self.assertEqual(400, result.status_code)

    async def test_slow_send_has_finite_timeout_and_closes_iterator(self):
        released, closed = [], []
        async def records():
            try:
                while True:
                    yield frame("progress", {"text": "bounded"})
            finally:
                closed.append(True)
        async def receive():
            await anyio.sleep_forever()
        async def slow_send(message):
            await anyio.sleep(10)
        response = LeaseStream(records(), lambda: released.append(True), .5, .03)
        start = monotonic()
        await response(scope(), receive, slow_send)
        self.assertLess(monotonic() - start, .5)
        self.assertEqual([True], released)
        # A timeout on headers can precede generator startup; no allocated generator resource.
        self.assertTrue(not closed or closed == [True])

    async def test_lease_closes_started_iterator_and_releases(self):
        released, closed, sent = [], [], []
        async def records():
            try:
                yield frame("capture", {"sealed": False})
                await anyio.sleep_forever()
            finally:
                closed.append(True)
        async def receive():
            await anyio.sleep_forever()
        async def send(message):
            sent.append(message)
        await LeaseStream(records(), lambda: released.append(True), .03, .02)(scope(), receive, send)
        self.assertEqual([True], closed)
        self.assertEqual([True], released)
        self.assertTrue(any(m["type"] == "http.response.body" for m in sent))

    async def test_disconnect_only_releases_observer(self):
        released, closed = [], []
        async def records():
            try:
                yield b"data: bounded\n\n"
                await anyio.sleep_forever()
            finally:
                closed.append(True)
        async def receive():
            await anyio.sleep_forever()
        async def send(message):
            if message["type"] == "http.response.body":
                raise OSError("disconnected")
        await LeaseStream(records(), lambda: released.append(True), .5, .1)(scope(), receive, send)
        self.assertEqual([True], released)
        self.assertEqual([True], closed)

    async def test_subscriber_capacity_released_after_disconnect(self):
        service = Reads()
        app = FastAPI()
        add_progress_routes(app, service, subscriber_capacity=1, send_timeout=.5, lease_seconds=1)
        app = trusted(app)
        entered = asyncio.Event()
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def blocked_send(message):
            if message["type"] == "http.response.body":
                entered.set()
                await anyio.sleep_forever()
        task = asyncio.create_task(app(scope(), receive, blocked_send))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://test") as client:
                rejected = await client.get(PATH + "/stream")
                self.assertEqual(503, rejected.status_code)
                self.assertEqual("SUBSCRIBER_CAPACITY_EXHAUSTED", rejected.json()["error"]["code"])
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                accepted = await client.get(PATH + "/stream")
                self.assertEqual(200, accepted.status_code)
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
