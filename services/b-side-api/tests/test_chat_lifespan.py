"""Actual FastAPI lifespan/request probes with offline persistence/action edges.

The historical test_app.Harness uses removed constructor parameters and is not
an entry point for this suite. Only its simple repository fakes are reused.
Actual Runtime/approval/PostgreSQL behavior has separate disposable-PG probes.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import threading
import unittest
from unittest.mock import patch

import httpx
from a2flow_bside import app as app_module
from a2flow_bside import auth
from a2flow_bside.chat_runtime import ChatRuntime
from a2flow_bside.durable_chat import DurableChat, DurableDispatcher
from test_app import (
    NOW,
    ORIGIN,
    ORIGIN_HEADERS,
    PEPPER,
    FakeAccountGuard,
    FakeConversations,
    FakeMessages,
    FakeNotifications,
    FakeRunOwnership,
    FakeRuntimeClient,
    FakeSchedules,
    FakeSessions,
    FakeUsers,
    catalog,
)


class CountedConversations(FakeConversations):
    def __init__(self):
        super().__init__()
        self.owner_reads = 0
        self.rows[1] = {"id": 1, "user_id": 1, "title": "Synthetic", "created_at": NOW}

    def owner(self, conversation_id):
        self.owner_reads += 1
        return super().owner(conversation_id)


class CurrentHarness:
    """Current explicit factory contract; no implicit Chat fallback or old adapter."""

    def __init__(self, factory=None):
        users = FakeUsers()
        users.rows[1] = {"user_id": 1, "username": "synthetic", "role": "USER"}
        sessions = FakeSessions(users)
        self.token = "s" * 43
        sessions.create(
            token_sha256=auth.hash_session_token(self.token),
            user_id=1,
            expires_at=NOW + dt.timedelta(days=1),
        )
        self.components = dict(
            users=users,
            sessions=sessions,
            conversations=CountedConversations(),
            messages=FakeMessages(),
            schedules=FakeSchedules(),
            notifications=FakeNotifications(),
            run_ownership=FakeRunOwnership(),
            runtime_client=FakeRuntimeClient(),
            workflow_catalog=catalog,
            pepper=PEPPER,
            browser_origin=ORIGIN,
            environment="PRT",
            session_seconds=7200,
            now=lambda: NOW,
            account_guard=FakeAccountGuard(),
        )
        self.app = app_module.create_app(**self.components, chat_runtime_factory=factory)

    async def client(self):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://127.0.0.1",
            cookies={"a2flow_bside_session": self.token},
        )


class OfflineDurable(DurableChat):
    """Only external database work is replaced; the dispatcher still owns tasks."""

    def __init__(self, wake, *, queued=False, fail_ready=False):
        super().__init__(lambda: self.unexpected_database(), environment="PRT", wake=wake)
        self.fail_ready = fail_ready
        self.ready_checks = 0
        self.queued = queued
        self.sent = False

    @staticmethod
    def unexpected_database():
        raise AssertionError("No lifecycle probe may contact a database")

    def check_ready(self):
        self.ready_checks += 1
        if self.fail_ready:
            raise RuntimeError("SYNTHETIC_READY_FAILURE")

    def materialize(self, messages, processing_tasks):
        pass

    def candidates(self, **kwargs):
        if not self.queued or self.sent:
            return []
        self.sent = True
        return [{"input_message_id": 1, "conversation_id": 1}]

    def next_delay(self, **kwargs):
        return None


class HoldingDispatcher(DurableDispatcher):
    """Real run/drain/settle/wait with a controlled external execution boundary."""

    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.stopped = asyncio.Event()
        self.instances.append(self)

    async def dispatch(self, turn):
        self.started.set()
        await self.release.wait()
        self.stopped.set()
        return True


class ChatLifespanTests(unittest.IsolatedAsyncioTestCase):
    async def assert_unavailable_without_chat_reads(self, harness, client):
        conversations = harness.components["conversations"]
        before = conversations.owner_reads
        requests = [
            ("GET", "/api/conversations/messages?conversationId=1", None),
            (
                "POST",
                "/api/conversations/messages",
                {"conversationId": 1, "text": "Synthetic", "clientRequestId": "synthetic-request"},
            ),
            ("GET", "/api/conversations/1/cards", None),
            (
                "POST",
                "/api/conversations/1/cards/synthetic/actions",
                {"requestId": "synthetic-card", "actionName": "submit", "inputs": {}},
            ),
        ]
        for method, path, body in requests:
            response = await client.request(method, path, json=body, headers=ORIGIN_HEADERS)
            self.assertEqual(
                (503, "CHAT_APPLICATION_UNAVAILABLE"),
                (response.status_code, response.json()["error"]["code"]),
                path,
            )
        self.assertEqual(
            before, conversations.owner_reads, "readiness must precede ownership storage"
        )
        metadata = await client.get("/api/conversations")
        self.assertEqual(200, metadata.status_code)

    def factory(self, records, **store_options):
        def create(wake):
            store = OfflineDurable(wake, **store_options)
            runtime = ChatRuntime(
                durable_chat=store,
                runner=object(),
                cards=lambda *_: [],
                action=lambda *_: {"ok": True},
            )
            records.append((wake, runtime))
            return runtime

        return create

    async def test_prestart_poststop_generic_and_restart_use_concrete_readiness(self):
        records = []
        harness = CurrentHarness(self.factory(records))
        self.assertEqual([], records, "constructing routes must not invoke Chat factory")
        with patch.object(app_module, "DurableDispatcher", HoldingDispatcher):
            async with await harness.client() as client:
                await self.assert_unavailable_without_chat_reads(harness, client)
                for expected_lifetimes in (1, 2):
                    async with harness.app.router.lifespan_context(harness.app):
                        self.assertEqual(expected_lifetimes, len(records))
                        wake, runtime = records[-1]
                        worker = HoldingDispatcher.instances[-1]
                        self.assertIs(wake, runtime.durable_chat.wake)
                        self.assertIs(wake, worker.store.wake)
                        self.assertEqual(1, runtime.durable_chat.ready_checks)
                        response = await client.get("/api/conversations/1/cards")
                        self.assertEqual({"cards": []}, response.json())
                    with self.assertRaises(RuntimeError):
                        wake.clear()
                    await self.assert_unavailable_without_chat_reads(harness, client)
                self.assertIsNot(records[0][0], records[1][0])
        generic = CurrentHarness()
        async with generic.app.router.lifespan_context(generic.app):
            async with await generic.client() as client:
                response = await client.post(
                    "/api/conversations/messages",
                    headers=ORIGIN_HEADERS,
                    json={
                        "conversationId": 1,
                        "text": "Synthetic",
                        "clientRequestId": "generic-request",
                    },
                )
                self.assertEqual(
                    (503, "CHAT_DURABLE_DISPATCH_UNAVAILABLE"),
                    (response.status_code, response.json()["error"]["code"]),
                )
                self.assertEqual(200, (await client.get("/api/conversations")).status_code)

    async def test_startup_factory_ready_and_immediate_worker_failures_close_wake(self):
        for failure in ("factory", "ready", "worker"):
            with self.subTest(failure=failure):
                wakes = []

                def create(wake):
                    wakes.append(wake)
                    if failure == "factory":
                        raise RuntimeError("SYNTHETIC_FACTORY_FAILURE")
                    return ChatRuntime(
                        durable_chat=OfflineDurable(wake, fail_ready=failure == "ready"),
                        runner=object(),
                    )

                class FailingWorker(HoldingDispatcher):
                    async def run(self, stop):
                        raise RuntimeError("SYNTHETIC_WORKER_START_FAILURE")

                harness = CurrentHarness(create)
                with patch.object(app_module, "DurableDispatcher", FailingWorker):
                    with self.assertRaises(RuntimeError):
                        async with harness.app.router.lifespan_context(harness.app):
                            self.fail("failed startup exposed readiness")
                self.assertEqual(1, len(wakes))
                with self.assertRaises(RuntimeError):
                    wakes[0].clear()
                async with await harness.client() as client:
                    await self.assert_unavailable_without_chat_reads(harness, client)

    async def test_multi_app_lifetimes_and_wakes_are_isolated(self):
        first, second = [], []
        a, b = CurrentHarness(self.factory(first)), CurrentHarness(self.factory(second))
        with patch.object(app_module, "DurableDispatcher", HoldingDispatcher):
            async with b.app.router.lifespan_context(b.app):
                async with a.app.router.lifespan_context(a.app):
                    self.assertIsNot(first[0][0], second[0][0])
                with self.assertRaises(RuntimeError):
                    first[0][0].clear()
                second[0][0].clear()
                async with await b.client() as client:
                    self.assertEqual(
                        200, (await client.get("/api/conversations/1/cards")).status_code
                    )

    async def test_shutdown_revokes_admission_and_waits_owned_execution_and_retained_action(self):
        records = []
        action_started, action_release = threading.Event(), threading.Event()

        def action(*args):
            action_started.set()
            if not action_release.wait(5):
                raise RuntimeError("SYNTHETIC_ACTION_RELEASE_TIMEOUT")
            return {"synthetic": True}

        def create(wake):
            store = OfflineDurable(wake, queued=True)
            records.append(wake)
            return ChatRuntime(
                durable_chat=store, runner=object(), cards=lambda *_: [], action=action
            )

        harness = CurrentHarness(create)
        with patch.object(app_module, "DurableDispatcher", HoldingDispatcher):
            lifetime = harness.app.router.lifespan_context(harness.app)
            await lifetime.__aenter__()
            worker = HoldingDispatcher.instances[-1]
            try:
                await asyncio.wait_for(worker.started.wait(), 1)
                async with await harness.client() as client:
                    request = asyncio.create_task(
                        client.post(
                            "/api/conversations/1/cards/synthetic/actions",
                            headers=ORIGIN_HEADERS,
                            json={
                                "requestId": "synthetic-action",
                                "actionName": "submit",
                                "inputs": {},
                            },
                        )
                    )
                    self.assertTrue(await asyncio.to_thread(action_started.wait, 1))
                    request.cancel()
                    await asyncio.gather(request, return_exceptions=True)
                    shutdown = asyncio.create_task(lifetime.__aexit__(None, None, None))
                    await asyncio.sleep(0)
                    await self.assert_unavailable_without_chat_reads(harness, client)
                    self.assertFalse(shutdown.done(), "shutdown returned while owned work remained")
                    worker.release.set()
                    await asyncio.wait_for(worker.stopped.wait(), 1)
                    await asyncio.sleep(0)
                    self.assertFalse(shutdown.done(), "retained card action was not awaited")
                    action_release.set()
                    await asyncio.wait_for(shutdown, 2)
                    self.assertEqual(set(), harness.app.state.chat_tasks)
            finally:
                worker.release.set()
                action_release.set()
            with self.assertRaises(RuntimeError):
                records[0].clear()
