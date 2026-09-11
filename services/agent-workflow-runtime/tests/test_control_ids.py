"""AF05 review fix: control IDs reuse the shared contract at both ingress layers."""

import json
import unittest
from urllib.parse import quote
from unittest.mock import patch

import httpx

from agent_workflow_runtime.http import create_app
from agent_workflow_runtime.models import ActionRejected
from service_support import ServiceFixture, TrustedHost


class ControlIdTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = ServiceFixture()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=TrustedHost(create_app(self.fixture.service), self.fixture.owner),
                raise_app_exceptions=False,
            ), base_url="http://runtime.test",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_128_character_controls_round_trip_start_stop_restart_action(self):
        start_id, stop_id, restart_id, action_id = (c * 128 for c in "abcd")
        response = await self.client.post("/runtime/runs", json={
            "controlRequestId": start_id, "definitionKey": "sample.definition", "inputs": {},
        })
        self.assertEqual(200, response.status_code, response.text)
        run_id = response.json()["runId"]
        receipt = await self.client.get("/runtime/controls/" + start_id)
        self.assertEqual(run_id, receipt.json()["runId"])
        stopped = await self.client.post(f"/runtime/runs/{run_id}/stop", json={"controlRequestId": stop_id})
        self.assertEqual(200, stopped.status_code, stopped.text)
        self.assertEqual("STOPPED", stopped.json()["lifecycle"])
        self.assertEqual(run_id, (await self.client.get("/runtime/controls/" + stop_id)).json()["runId"])
        restarted = await self.client.post(f"/runtime/runs/{run_id}/restart", json={
            "controlRequestId": restart_id, "inputs": {},
        })
        self.assertEqual(200, restarted.status_code, restarted.text)
        new_id = restarted.json()["runId"]
        self.assertEqual(new_id, (await self.client.get("/runtime/controls/" + restart_id)).json()["runId"])
        card = restarted.json()["interactions"]["items"][0]
        completed = await self.client.post(f"/runtime/runs/{new_id}/nodes/node-test/actions", json={
            "controlRequestId": action_id, "interactionId": card["interactionId"],
            "actionName": "confirm_route_choice", "inputs": {"selection": "left"},
        })
        self.assertEqual(200, completed.status_code, completed.text)
        self.assertEqual("SUCCEEDED", completed.json()["lifecycle"])
        self.assertEqual(action_id, completed.json()["interactions"]["items"][0]["lastAttempt"]["controlRequestId"])
        self.assertEqual(1, len(self.fixture.engine.executor.calls))

    async def test_invalid_http_controls_fail_before_resolution_receipt_or_stop_change(self):
        run = self.fixture.engine.run
        controls_before = dict(self.fixture.runs.controls)
        for invalid in ("a" * 129, "client/start-1", "stop/1"):
            bodies = (
                ("/runtime/runs", {"controlRequestId": invalid, "definitionKey": "sample.definition", "inputs": {}}),
                (f"/runtime/runs/{run.run_id}/stop", {"controlRequestId": invalid}),
                (f"/runtime/runs/{run.run_id}/restart", {"controlRequestId": invalid, "inputs": {}}),
                (f"/runtime/runs/{run.run_id}/nodes/node-test/actions", {
                    "controlRequestId": invalid, "interactionId": "card", "actionName": "confirm_route_choice",
                    "inputs": {"selection": "left"},
                }),
            )
            for path, body in bodies:
                with self.subTest(control=invalid, route=path):
                    result = await self.client.post(path, json=body)
                    self.assertEqual(400, result.status_code, result.text)
                    self.assertEqual({"error": {"code": "INVALID_INPUT"}}, result.json())
            lookup = await self.client.get("/runtime/controls/" + quote(invalid, safe=""))
            self.assertEqual(400, lookup.status_code, lookup.text)
            self.assertEqual("INVALID_INPUT", lookup.json()["error"]["code"])
        self.assertEqual(0, self.fixture.entry_calls)
        self.assertEqual(0, self.fixture.factory_calls)
        self.assertEqual([], self.fixture.engine.executor.calls)
        self.assertEqual(controls_before, self.fixture.runs.controls)
        self.assertEqual("RUNNING", self.fixture.life.read(run.owner, run.run_id).status)

    async def test_direct_service_uses_identical_control_rule_before_any_backend_read_or_write(self):
        service, run = self.fixture.service, self.fixture.engine.run
        before = dict(self.fixture.runs.controls)
        for invalid in ("a" * 129, "client/start-1", "", "-leading", "space id", "line\n"):
            payload = {"controlRequestId": invalid, "interactionId": "card",
                       "actionName": "confirm_route_choice", "inputs": {"selection": "left"}}
            operations = (
                lambda: service.start(run.owner, invalid, "sample.definition", {}),
                lambda: service.stop(run.owner, run.run_id, invalid),
                lambda: service.restart(run.owner, run.run_id, invalid, {}),
                lambda: service.action(run.owner, run.run_id, "node-test", payload),
                lambda: service.control(run.owner, invalid),
            )
            with patch.object(self.fixture.projection, "control", side_effect=AssertionError("invalid lookup read")):
                for operation in operations:
                    with self.assertRaisesRegex(ActionRejected, "^INVALID_SERVICE_INPUT$"):
                        operation()
        self.assertEqual(0, self.fixture.entry_calls)
        self.assertEqual(0, self.fixture.factory_calls)
        self.assertEqual([], self.fixture.engine.executor.calls)
        self.assertEqual(before, self.fixture.runs.controls)
        self.assertEqual("RUNNING", self.fixture.life.read(run.owner, run.run_id).status)

    async def test_definition_and_business_input_do_not_inherit_control_id_pattern(self):
        definition = "authorized/definition/" + "x" * 150
        seen = []
        def authorized_entry(owner, key):
            seen.append(key)
            return "node-test"
        self.fixture.service.resolve_entry = authorized_entry
        inputs = {"businessId": "item/1", "description": "x" * 300}
        response = await self.client.post("/runtime/runs", json={
            "controlRequestId": "valid.id:with-dash_1", "definitionKey": definition, "inputs": inputs,
        })
        self.assertEqual(200, response.status_code, response.text)
        saved = self.fixture.life.read(self.fixture.owner, response.json()["runId"])
        self.assertEqual([definition], seen)
        self.assertEqual(definition, saved.definition_key)
        self.assertEqual(inputs, json.loads(saved.initial_inputs_json))
