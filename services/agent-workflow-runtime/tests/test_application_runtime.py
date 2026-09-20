"""The same Skill display preparation works without any Workflow identity."""
from copy import deepcopy
import unittest

from agent_workflow_runtime.application_runtime import ApplicationRuntime
from agent_workflow_runtime.models import ActionRejected


def resolved(interactive=True):
    return {"resolvedVersion": {"versionId": "version-1"}, "application": {
        "asset": {"applicationKey": "choice-card", "protocolProfileRef": "a2flow.mvp08.v1",
                  "componentCatalogRef": "catalog-1"},
        "renderPolicy": {"tool": "render_application", "requiresPause": interactive,
                         "interactionMode": "INTERACTIVE" if interactive else "DISPLAY_ONLY"},
        "surfaceTemplate": {"rootId": "root", "components": [
            {"id": "root", "component": "Text", "text": {"path": "/prompt"}}],
            "inputSchema": {"type": "object"}},
    }}


DATA = {"prompt": "Choose", "options": [
    {"label": "First", "value": "a"}, {"label": "Second", "value": "b"}]}
ACTIONS = [{"actionName": "confirm", "inputSchema": {"type": "object"}}]


class ApplicationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime = ApplicationRuntime(lambda application: True)

    def prepare(self, application=None, data=None, actions=None):
        return self.runtime.prepare(application_key="choice-card",
            resolved=application if application is not None else resolved(),
            data=data if data is not None else deepcopy(DATA),
            actions=actions if actions is not None else deepcopy(ACTIONS))

    def test_preparation_has_no_workflow_or_conversation_lifecycle(self):
        prepared = self.prepare()
        self.assertTrue(prepared.interactive)
        self.assertEqual(DATA, prepared.display()["data"])
        self.assertFalse({"runId", "nodeId", "threadId", "userId", "state", "interactionId"}
                         & prepared.display().keys())
        self.assertEqual(prepared.display_json, self.prepare().display_json)

    def test_prepared_material_is_detached_from_all_callers(self):
        source, data, actions = resolved(), deepcopy(DATA), deepcopy(ACTIONS)
        prepared = self.prepare(source, data, actions)
        source["application"]["surfaceTemplate"]["components"].clear()
        data["prompt"] = "changed"
        actions[0]["actionName"] = "changed"
        view = prepared.display()
        view["data"]["prompt"] = "another change"
        self.assertEqual("Choose", prepared.display()["data"]["prompt"])
        self.assertEqual("confirm", prepared.display()["actions"][0]["actionName"])
        self.assertEqual(1, len(prepared.display()["components"]))

    def test_display_only_never_requests_interaction(self):
        prepared = self.prepare(resolved(False), actions=[])
        self.assertFalse(prepared.interactive)
        self.assertEqual([], prepared.display()["actions"])
        with self.assertRaises(ActionRejected):
            self.prepare(resolved(False))

    def test_rejects_mixed_identity_profile_and_invalid_data(self):
        for field, value in (("applicationKey", "other"), ("protocolProfileRef", "other")):
            application = resolved()
            application["application"]["asset"][field] = value
            with self.assertRaises(ActionRejected):
                self.prepare(application)
        for data in ({}, {**DATA, "userId": 123}, {**DATA, "options": [DATA["options"][0]] * 2}):
            with self.assertRaises(ActionRejected):
                self.prepare(data=data)

    def test_validators_remain_authoritative(self):
        for app_validator, data_validator, code in (
            (lambda _: False, None, "UNSUPPORTED_APPLICATION_PROFILE"),
            (lambda _: True, lambda *_: False, "INVALID_APPLICATION_DATA"),
        ):
            self.runtime = ApplicationRuntime(app_validator, data_validator)
            with self.assertRaisesRegex(ActionRejected, code):
                self.prepare()

    def test_multiple_named_actions_are_material_not_graph_routing(self):
        actions = deepcopy(ACTIONS) + [{"actionName": "refresh", "inputSchema": {}}]
        self.assertEqual(actions, self.prepare(actions=actions).display()["actions"])
        with self.assertRaisesRegex(ActionRejected, "INVALID_APPLICATION_ACTION"):
            self.prepare(actions=deepcopy(ACTIONS) * 2)
        with self.assertRaises(ActionRejected):
            self.prepare(actions=[])
