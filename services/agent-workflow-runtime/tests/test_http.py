"""Real in-process ASGI requests with explicitly synthetic backend ports."""

import asyncio
from dataclasses import replace
import json
import threading
import unittest

import httpx
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from skillweave_contracts import TrustedContext

from agent_workflow_runtime.http import BODY_LIMIT, create_app
from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.native_control import RunGraphBinding, guarded_node
from service_support import ServiceFixture, TrustedHost


class HttpTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = ServiceFixture()
        self.app = create_app(self.fixture.service, execution_capacity=1, read_capacity=1, stop_capacity=1)
        self.client = self.client_for(self.fixture.owner)
        self.addAsyncCleanup(self.client.aclose)

    def client_for(self, owner):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=TrustedHost(self.app, owner), raise_app_exceptions=False),
            base_url="http://runtime.test",
        )

    async def start(self, control="start"):
        return await self.client.post("/runtime/runs", json={
            "controlRequestId": control, "definitionKey": "sample.definition", "inputs": {},
        })

    async def action(self, run_id, interaction_id, control="confirm", **changes):
        body = {"interactionId": interaction_id, "actionName": "confirm_route_choice",
                "controlRequestId": control, "inputs": {"selection": "left"}, **changes}
        return await self.client.post(f"/runtime/runs/{run_id}/nodes/node-test/actions", json=body)

    async def test_formal_start_wait_action_finalizer_and_duplicate_controls(self):
        response = await self.start()
        self.assertEqual(200, response.status_code, response.text)
        waiting = response.json()
        self.assertEqual("RUNNING", waiting["lifecycle"])
        card = waiting["interactions"]["items"][0]
        self.assertEqual("WAITING", card["recordedPhase"])
        self.assertEqual("REVALIDATION_REQUIRED", card["actionEligibility"])
        run_id = waiting["runId"]
        again = await self.start()
        self.assertEqual(run_id, again.json()["runId"])
        self.assertEqual(1, self.fixture.factory_calls)
        completed = await self.action(run_id, card["interactionId"])
        self.assertEqual(200, completed.status_code, completed.text)
        self.assertEqual("SUCCEEDED", completed.json()["lifecycle"])
        attempt = completed.json()["interactions"]["items"][0]["lastAttempt"]
        self.assertTrue(attempt["businessSuccess"])
        self.assertTrue(attempt["interactionCompleted"])
        self.assertEqual("RETURNED", attempt["resumeDelivery"])
        duplicate = await self.action(run_id, card["interactionId"])
        self.assertEqual(409, duplicate.status_code)
        self.assertEqual(1, len(self.fixture.engine.executor.calls))
        graph = self.fixture.engine.built[run_id][0]
        run = self.fixture.life.read(self.fixture.owner, run_id)
        self.assertFalse(graph.get_state({"configurable": {"thread_id": run.thread_id}}).next)
        events = await self.client.get(f"/runtime/runs/{run_id}/events")
        self.assertEqual("runtime.snapshot", events.json()["type"])
        self.assertFalse(events.json()["replay"])
        self.assertEqual("snapshot", events.json()["delivery"])
        self.assertEqual("SUCCEEDED", events.json()["snapshot"]["lifecycle"])
        self.assertNotIn("result_json", events.text)
        self.assertNotIn("Completed with current run evidence", events.text)

    async def test_identity_wrong_bindings_stale_inputs_and_stop_reject_without_executor(self):
        waiting = (await self.start()).json()
        run_id = waiting["runId"]
        card = waiting["interactions"]["items"][0]
        for owner in (None, TrustedContext("other-user", "PRT"), TrustedContext("test-user", "ONLINE")):
            async with self.client_for(owner) as client:
                response = await client.get(f"/runtime/runs/{run_id}")
                self.assertEqual(401 if owner is None else 404, response.status_code)
                response = await client.get("/runtime/controls/start")
                self.assertEqual(401 if owner is None else 404, response.status_code)
        async with self.client_for(None) as client:
            forged = await client.get(f"/runtime/runs/{run_id}",
                                      headers={"x-user-id": "test-user", "x-environment": "PRT"})
            self.assertEqual(401, forged.status_code)
        forged = await self.action(run_id, card["interactionId"], userId="test-user")
        self.assertEqual(400, forged.status_code)
        self.assertEqual(404, (await self.action("missing", card["interactionId"])).status_code)
        self.assertEqual(404, (await self.action(run_id, "missing")).status_code)
        wrong_node = await self.client.post(f"/runtime/runs/{run_id}/nodes/wrong/actions", json={
            "interactionId": card["interactionId"], "actionName": "confirm_route_choice",
            "controlRequestId": "wrong-node", "inputs": {"selection": "left"},
        })
        self.assertEqual(404, wrong_node.status_code)
        malformed = await self.action(run_id, card["interactionId"], inputs={"selection": "secret-invalid"})
        self.assertEqual(400, malformed.status_code)
        self.assertNotIn("secret-invalid", malformed.text)
        old = self.fixture.engine.config.current
        self.fixture.engine.config.current = ((*old[0][:1], "changed"), *old[1:])
        stale = await self.action(run_id, card["interactionId"])
        self.assertEqual("RESET_REQUIRED", stale.json()["error"]["code"])
        self.fixture.engine.config.current = old
        stopped = await self.client.post(f"/runtime/runs/{run_id}/stop", json={"controlRequestId": "stop"})
        self.assertEqual("STOPPED", stopped.json()["lifecycle"])
        self.assertEqual("RUN_STOPPED", (await self.action(run_id, card["interactionId"])).json()["error"]["code"])
        observed = (await self.client.get(f"/runtime/runs/{run_id}")).json()
        self.assertEqual("NOT_OPERABLE", observed["interactions"]["items"][0]["actionEligibility"])
        self.assertEqual([], self.fixture.engine.executor.calls)

    async def test_fresh_restart_current_inputs_versions_new_thread_no_old_full_read(self):
        old = (await self.start()).json()
        old_run = self.fixture.life.read(self.fixture.owner, old["runId"])
        await self.client.post(f"/runtime/runs/{old_run.run_id}/stop", json={"controlRequestId": "stop"})
        self.fixture.runs.forbid_run_read.add(old_run.run_id)
        self.fixture.runs.forbid_fact_read.add(old_run.run_id)
        config = self.fixture.engine.config
        config.current = (*config.current, ("WORKFLOW:sample", "fresh-v2"))
        response = await self.client.post(f"/runtime/runs/{old_run.run_id}/restart", json={
            "controlRequestId": "restart", "inputs": {"fresh": "new input"},
        })
        self.assertEqual(200, response.status_code, response.text)
        new_id = response.json()["runId"]
        new = self.fixture.life.read(self.fixture.owner, new_id)
        self.assertNotEqual(old_run.run_id, new_id)
        self.assertNotEqual(old_run.thread_id, new.thread_id)
        self.assertEqual({"fresh": "new input"}, json.loads(new.initial_inputs_json))
        self.assertEqual(config.current, new.versions)
        again = await self.client.post(f"/runtime/runs/{old_run.run_id}/restart", json={
            "controlRequestId": "restart", "inputs": {"fresh": "new input"},
        })
        self.assertEqual(new_id, again.json()["runId"])
        conflict = await self.client.post(f"/runtime/runs/{old_run.run_id}/restart", json={
            "controlRequestId": "restart", "inputs": {"fresh": "changed"},
        })
        self.assertEqual("CONTROL_REQUEST_CONFLICT", conflict.json()["error"]["code"])
        self.assertEqual(2, self.fixture.factory_calls)

    def long_graph(self):
        started, release = threading.Event(), threading.Event()
        def factory(run, life):
            def long_node(state):
                started.set()
                if not release.wait(5):
                    raise RuntimeError("test barrier expired")
                return {}
            graph = StateGraph(dict)
            graph.add_node("long", guarded_node(life, run.context(), long_node))
            graph.add_edge(START, "long")
            graph.add_edge("long", END)
            return RunGraphBinding(graph.compile(checkpointer=MemorySaver()), life), {}
        self.fixture.factory_hook = factory
        return started, release

    async def test_long_start_discoverable_readable_stoppable_and_execution_saturation(self):
        started, release = self.long_graph()
        task = asyncio.create_task(self.start())
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            receipt = await self.client.get("/runtime/controls/start")
            self.assertEqual("DISPATCHING", receipt.json()["delivery"])
            run_id = receipt.json()["runId"]
            reads = await asyncio.wait_for(self.client.get(f"/runtime/runs/{run_id}"), 1)
            self.assertEqual("RUNNING", reads.json()["lifecycle"])
            self.assertEqual("NOT_ESTABLISHED", reads.json()["nativeExecution"]["liveness"])
            busy = await self.start("busy")
            self.assertEqual("CAPACITY_EXHAUSTED", busy.json()["error"]["code"])
            self.assertEqual(404, (await self.client.get("/runtime/controls/busy")).status_code)
            stop = await asyncio.wait_for(self.client.post(f"/runtime/runs/{run_id}/stop",
                                                           json={"controlRequestId": "stop"}), 1)
            self.assertEqual("STOPPED", stop.json()["lifecycle"])
            self.assertFalse(task.done())
            release.set()
            self.assertEqual("STOPPED", (await task).json()["lifecycle"])
            self.assertEqual(1, self.fixture.factory_calls)
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    async def test_actual_request_task_cancellation_does_not_release_running_slot(self):
        started, release = self.long_graph()
        task = asyncio.create_task(self.start())
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            run_id = (await self.client.get("/runtime/controls/start")).json()["runId"]
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            # Request really cancelled, synchronous work is still blocked.
            self.assertEqual("CAPACITY_EXHAUSTED", (await self.start("after-disconnect")).json()["error"]["code"])
            self.assertEqual(404, (await self.client.get("/runtime/controls/after-disconnect")).status_code)
            self.assertEqual("RUNNING", (await self.client.get(f"/runtime/runs/{run_id}")).json()["lifecycle"])
            stop = await self.client.post(f"/runtime/runs/{run_id}/stop", json={"controlRequestId": "stop"})
            self.assertEqual("STOPPED", stop.json()["lifecycle"])
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
        # Wait for actual native return/receipt, never dispatch again.
        for _ in range(100):
            receipt = await self.client.get("/runtime/controls/start")
            if receipt.json()["delivery"] == "RETURNED":
                break
            await asyncio.sleep(.01)
        self.assertEqual("RETURNED", receipt.json()["delivery"])
        self.assertEqual(1, self.fixture.factory_calls)

    async def test_long_completing_action_projection_and_stop_dont_take_action_scope(self):
        waiting = (await self.start()).json()
        run_id = waiting["runId"]
        card = waiting["interactions"]["items"][0]
        started, release = threading.Event(), threading.Event()
        def block():
            started.set()
            if not release.wait(5):
                raise RuntimeError("test barrier expired")
        self.fixture.engine.executor.hook = block
        task = asyncio.create_task(self.action(run_id, card["interactionId"]))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            observation = await asyncio.wait_for(self.client.get(f"/runtime/runs/{run_id}"), 1)
            self.assertEqual("EXECUTING", observation.json()["interactions"]["items"][0]["recordedPhase"])
            stopped = await asyncio.wait_for(self.client.post(f"/runtime/runs/{run_id}/stop",
                                                              json={"controlRequestId": "stop"}), 1)
            self.assertEqual("STOPPED", stopped.json()["lifecycle"])
            release.set()
            result = await task
            self.assertEqual("STOPPED", result.json()["lifecycle"])
            item = result.json()["interactions"]["items"][0]
            self.assertTrue(item["lastAttempt"]["interactionCompleted"])
            self.assertEqual("NOT_REQUESTED", item["lastAttempt"]["resumeDelivery"])
            self.assertEqual("NOT_OPERABLE", item["actionEligibility"])
            self.assertEqual(1, len(self.fixture.engine.executor.calls))
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    async def test_read_timeout_keeps_own_slot_and_never_exhausts_stop_lane(self):
        self.app = create_app(self.fixture.service, execution_capacity=1, read_capacity=1,
                              stop_capacity=1, read_timeout=.05)
        await self.client.aclose()
        self.client = self.client_for(self.fixture.owner)
        self.addAsyncCleanup(self.client.aclose)
        run_id = self.fixture.engine.run.run_id
        original = self.fixture.service.inspect
        entered, release = threading.Event(), threading.Event()
        def slow(*args):
            entered.set()
            release.wait(2)
            return original(*args)
        self.fixture.service.inspect = slow
        try:
            timed = await self.client.get(f"/runtime/runs/{run_id}")
            self.assertTrue(entered.is_set())
            self.assertEqual(504, timed.status_code)
            self.assertEqual("CAPACITY_EXHAUSTED", (await self.client.get("/runtime/controls/missing")).json()["error"]["code"])
            stopped = await self.client.post(f"/runtime/runs/{run_id}/stop", json={"controlRequestId": "stop"})
            self.assertEqual("STOPPED", stopped.json()["lifecycle"])
        finally:
            release.set()
            self.fixture.service.inspect = original

    async def test_actual_chunked_body_limit_validation_redaction_output_limit_and_no_replay(self):
        async def oversized():
            yield b" " * (BODY_LIMIT - 10)
            yield b"SECRET-OVERFLOW" * 10
        response = await self.client.post("/runtime/runs", content=oversized(),
                                          headers={"content-type": "application/json", "content-length": "1"})
        self.assertEqual(413, response.status_code)
        self.assertNotIn("SECRET", response.text)
        self.assertEqual(0, self.fixture.factory_calls)
        invalid = await self.client.post("/runtime/runs", json={
            "controlRequestId": {"secret": "PRIVATE-SENTINEL"}, "definitionKey": "sample.definition", "inputs": {},
        })
        self.assertEqual(400, invalid.status_code)
        self.assertNotIn("PRIVATE-SENTINEL", invalid.text)
        original = self.fixture.service.inspect
        self.fixture.service.inspect = lambda *a: {"private": "PRIVATE-RESULT" * 30000}
        try:
            first = await self.start()
            second = await self.start()
            self.assertEqual(507, first.status_code)
            self.assertEqual(507, second.status_code)
            self.assertNotIn("PRIVATE-RESULT", first.text)
            self.assertEqual(1, self.fixture.factory_calls)
        finally:
            self.fixture.service.inspect = original
        run_id = (await self.client.get("/runtime/controls/start")).json()["runId"]
        replay = await self.client.get(f"/runtime/runs/{run_id}/events", headers={"Last-Event-ID": "1"})
        self.assertEqual("REPLAY_UNSUPPORTED", replay.json()["error"]["code"])
        self.fixture.service.inspect = lambda *a: (_ for _ in ()).throw(RuntimeError("PRIVATE-EXCEPTION"))
        try:
            error = await self.client.get(f"/runtime/runs/{run_id}")
            self.assertEqual(500, error.status_code)
            self.assertNotIn("PRIVATE-EXCEPTION", error.text)
        finally:
            self.fixture.service.inspect = original

    async def test_asgi_disconnect_before_complete_body_never_dispatches(self):
        messages = iter([
            {"type": "http.request", "body": b'{"controlRequestId":', "more_body": True},
            {"type": "http.disconnect"},
        ])
        sent = []
        async def receive():
            return next(messages)
        async def send(message):
            sent.append(message)
        await TrustedHost(self.app, self.fixture.owner)(
            {"type": "http", "method": "POST", "path": "/runtime/runs", "headers": [],
             "query_string": b"", "http_version": "1.1", "scheme": "http", "server": ("test", 80)},
            receive, send,
        )
        self.assertEqual([], sent)
        self.assertEqual(0, self.fixture.factory_calls)

    async def test_exact_body_and_response_byte_boundaries(self):
        value = json.dumps({"controlRequestId": "exact", "definitionKey": "sample.definition", "inputs": {}}).encode()
        exact = value + b" " * (BODY_LIMIT - len(value))
        response = await self.client.post("/runtime/runs", content=exact, headers={"content-type": "application/json"})
        self.assertEqual(200, response.status_code)
        too_large = await self.client.post("/runtime/runs", content=exact + b" ", headers={"content-type": "application/json"})
        self.assertEqual(413, too_large.status_code)
        from agent_workflow_runtime.http import RESPONSE_LIMIT
        original = self.fixture.service.inspect
        try:
            # Compact JSON encoding overhead for {"x":""} is exactly 8 bytes.
            self.fixture.service.inspect = lambda *a: {"x": "a" * (RESPONSE_LIMIT - 8)}
            exact_response = await self.client.get("/runtime/runs/any")
            self.assertEqual(200, exact_response.status_code)
            self.assertEqual(RESPONSE_LIMIT, len(exact_response.content))
            self.fixture.service.inspect = lambda *a: {"x": "a" * (RESPONSE_LIMIT - 7)}
            overflow = await self.client.get("/runtime/runs/any")
            self.assertEqual(507, overflow.status_code)
        finally:
            self.fixture.service.inspect = original

    async def test_no_lifespan_dependency_and_unbounded_read_timeout_rejected(self):
        # Every HTTP test invokes the actual adapter without lifespan; all lanes
        # are initialized eagerly by create_app rather than a missing startup hook.
        for invalid in (None, 0, -1, float("inf"), float("nan"), True, 11):
            with self.assertRaises(ValueError):
                create_app(self.fixture.service, read_timeout=invalid)

    async def test_execution_timeout_is_not_misreported_as_read_deadline_or_replayed(self):
        def failed_factory(*args):
            raise TimeoutError("PRIVATE-BUSINESS-TIMEOUT")
        self.fixture.factory_hook = failed_factory
        response = await self.start()
        self.assertEqual(500, response.status_code)
        self.assertEqual("INTERNAL_ERROR", response.json()["error"]["code"])
        self.assertNotIn("PRIVATE-BUSINESS-TIMEOUT", response.text)
        receipt = (await self.client.get("/runtime/controls/start")).json()
        self.assertEqual("UNCONFIRMED", receipt["delivery"])
        again = await self.start()
        self.assertEqual(200, again.status_code)
        self.assertEqual("RUNNING", again.json()["lifecycle"])
        self.assertEqual("UNCONFIRMED", again.json()["initialControl"]["delivery"])
        self.assertEqual("NOT_ESTABLISHED", again.json()["nativeExecution"]["liveness"])
        self.assertEqual(1, self.fixture.factory_calls)
