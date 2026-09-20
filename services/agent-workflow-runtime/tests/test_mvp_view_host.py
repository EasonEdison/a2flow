"""Offline read-model/ASGI checks; no database, listener or identity provider."""

from dataclasses import replace
import json
import unittest

import httpx

from agent_workflow_runtime.models import ActionRejected, ActionRequest, Attempt, Interaction
from agent_workflow_runtime.mvp_host import create_mvp_app
from agent_workflow_runtime.ui_projection import initial_view, change_node, put_output, project_view
from lifecycle_support import fixture
from support import context


class ViewFunctionsTest(unittest.TestCase):
    def value(self):
        _, _, run = fixture()
        return initial_view(run, {"nodes": [{"nodeId": "plan", "skillKey": "plan"},
                                           {"nodeId": "copy", "skillKey": "copy"}]},
                            (("WORKFLOW:demo", "v1"),))

    def test_terminal_node_cannot_be_reopened(self):
        view = self.value()
        change_node(view, "plan", "RUNNING")
        change_node(view, "plan", "SUCCEEDED", "saved final")
        with self.assertRaisesRegex(ActionRejected, "NODE_VIEW_TERMINAL"):
            change_node(view, "plan", "RUNNING")

    def test_stop_uses_lifecycle_and_keeps_previous_success(self):
        view = self.value()
        change_node(view, "plan", "SUCCEEDED")
        result = project_view(view, 4, "STOPPED", 5, {})
        self.assertEqual(["SUCCEEDED", "STOPPED"], [node["status"] for node in result["nodes"]])
        self.assertEqual("4:5", result["revision"])
        self.assertEqual("PENDING", view["nodes"][1]["status"])

    def test_output_identity_replay_and_conflict(self):
        view = self.value()
        put_output(view, "plan", "MODEL_TEXT", "final")
        put_output(view, "plan", "MODEL_TEXT", "final")
        self.assertEqual(1, len(view["outputs"]))
        with self.assertRaisesRegex(ActionRejected, "OUTPUT_BINDING_CONFLICT"):
            put_output(view, "plan", "MODEL_TEXT", "different")

    def test_card_action_state_comes_from_saved_interaction_not_capture(self):
        view = self.value()
        _, _, run = fixture()
        card = {"cardId": "card", "nodeId": "plan", "interactionId": "one"}
        item = Interaction(
            run.context("plan"), "one", "application", "v1", run.thread_id,
            (("WORKFLOW:demo", "v1"),), display_json=json.dumps(card),
        )
        request = ActionRequest(
            run.run_id, "plan", "one", "confirm", "control", "{}",
        )
        completed = replace(
            item, phase="COMPLETED",
            attempts=(Attempt(request, "EXECUTED", True, True, '{"confirmed":true}'),),
        )
        returned = project_view(view, 1, "RUNNING", 2, {"one": completed})
        self.assertEqual("READ_ONLY", returned["cards"][0]["state"])
        self.assertEqual("NOT_OPERABLE", returned["cards"][0]["actionEligibility"])
        self.assertEqual({"confirmed": True}, returned["outputs"][0]["content"])
        waiting = project_view(view, 1, "RUNNING", 2, {"one": item})
        self.assertEqual("REVALIDATION_REQUIRED", waiting["cards"][0]["actionEligibility"])
        self.assertEqual("WAITING", waiting["nodes"][0]["status"])


    def test_interaction_node_outside_definition_fails_closed(self):
        view = self.value()
        _, _, run = fixture()
        item = Interaction(
            run.context('1003'), "one", "application", "v1", run.thread_id,
            (("WORKFLOW:demo", "v1"),),
        )
        with self.assertRaisesRegex(ActionRejected, "PROJECTION_UNAVAILABLE"):
            project_view(view, 1, "RUNNING", 2, {"one": item})

class Reads:
    def __init__(self):
        self.calls = []
    def runs(self, owner, **kwargs):
        self.calls.append(("runs", owner, kwargs))
        return {"items": [], "nextCursor": None}
    def view(self, owner, run_id):
        self.calls.append(("view", owner, run_id))
        return {"runId": run_id, "availability": "UNCONFIRMED"}


class HostTest(unittest.IsolatedAsyncioTestCase):
    def test_missing_resolver_fails_at_construction(self):
        with self.assertRaisesRegex(ValueError, "VERIFIED_IDENTITY_RESOLVER_REQUIRED"):
            create_mvp_app(object(), Reads(), lambda *_: [], None)

    async def test_session_uses_verified_identity_and_rejects_owner_query(self):
        views = Reads()
        app = create_mvp_app(object(), views, lambda *_: [], lambda scope: context().trusted_context)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            result = await client.get("/runtime/session", headers={"X-User-Id": "attacker"})
            self.assertEqual({"userId": '1008', "environment": "PRT"}, result.json())
            result = await client.get("/runtime/session?userId=attacker")
            self.assertEqual(400, result.status_code)

    async def test_failed_identity_rejects_before_any_read_or_execution(self):
        views = Reads()
        app = create_mvp_app(object(), views, lambda *_: [], lambda scope: None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for path in ("/runtime/session", "/runtime/runs", "/runtime/runs/r/view"):
                result = await client.get(path)
                self.assertEqual(401, result.status_code)
        self.assertEqual([], views.calls)

    async def test_refresh_routes_only_use_read_ports(self):
        views = Reads()
        app = create_mvp_app(object(), views, lambda owner, **kwargs: {"items": [], "nextCursor": None},
                             lambda scope: context().trusted_context)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for path in ("/runtime/runs", "/runtime/runs/r/view", "/runtime/workflows"):
                result = await client.get(path)
                self.assertEqual(200, result.status_code)
        self.assertEqual(["runs", "view"], [call[0] for call in views.calls])
