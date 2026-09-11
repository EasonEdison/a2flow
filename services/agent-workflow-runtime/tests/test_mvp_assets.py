"""Runtime-local real-operation gates using explicit offline port substitutes."""

from dataclasses import replace
import json
from types import SimpleNamespace
import unittest

from agent_workflow_runtime.asset_adapters import RuntimeAssets, OperationSpec
from agent_workflow_runtime.models import ActionRejected, Interaction
from lifecycle_support import fixture


VERSIONS = (("WORKFLOW:w", "v1"), ("ABILITY:confirm", "v1"), ("APPLICATION:card", "v1"))


class Reader:
    current = VERSIONS
    application_version = "v1"

    def versions(self, owner, definition):
        return self.current

    def resolve_ability(self, key, context):
        return SimpleNamespace(
            asset_id="confirm", version_id="v1", operation_ref="confirm",
            publication_metadata=SimpleNamespace(ability_key=key),
            definition={"credentialRequirements": [], "inputBindings": [
                {"source": "MODEL_ARGUMENT", "sourcePath": "/optionId", "targetPath": "/optionId"}],
                "defaultSuccessPolicyRef": "confirmed",
                "resultInterpretationPolicies": [{
                    "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1", "policyRef": "confirmed",
                    "operator": "JSON_POINTER_EQUALS", "jsonPointer": "/confirmed", "expectedLiteral": True,
                }]})

    def resolve_application(self, key, context):
        return {"application": {
            "asset": {"applicationKey": key, "protocolProfileRef": "a2flow.mvp08.v1"},
            "actionPolicies": [{"actionName": "confirm", "abilityReleaseRef": "confirm@v1",
                                "successPolicyRef": "confirmed", "completeInteractionOnSuccess": True}],
        }, "resolvedVersion": {"versionId": self.application_version},
            "recordedVersions": (("APPLICATION:card", self.application_version),),
            "contentDigest": "synthetic"}



def valid_input(value):
    return (type(value) is dict and set(value) == {"optionId", "confirmed"}
            and type(value["optionId"]) is str and value["confirmed"] is True)


class AssetsTest(unittest.TestCase):
    def setUp(self):
        _, _, run = fixture()
        self.run = replace(run, versions=VERSIONS)
        self.calls = []
        def execute(value, owner):
            self.calls.append(value)
            return {"selectedOptionId": value["optionId"], "confirmed": True}
        self.spec = OperationSpec(execute, valid_input,
                                  lambda result: type(result) is dict and result.get("confirmed") is True,
                                  lambda definition: True,
                                  model_allowed=False, action_allowed=True)
        self.reader = Reader()
        self.definition = {"nodes": [
            {"nodeId": self.run.entry_node_id, "skillKey": "plan"},
            {"nodeId": "copy", "skillKey": "copy"},
        ]}
        self.assets = RuntimeAssets(
            self.reader, self.run, {"confirm": self.spec}, self.definition,
        )
        card = {"cardId": "card", "nodeId": self.run.entry_node_id,
                "interactionId": "interaction",
                "data": {"options": [{"value": "allowed", "label": "Allowed"}]}}
        self.item = Interaction(
            self.run.context(), "interaction", "card", "v1", self.run.thread_id, VERSIONS,
            display_json=json.dumps(card),
        )

    def test_confirmation_cannot_be_called_by_model(self):
        with self.assertRaisesRegex(ActionRejected, "ABILITY_NOT_MODEL_CALLABLE"):
            self.assets.execute_ability("confirm", {"optionId": "allowed", "confirmed": True},
                                        self.run.context())
        self.assertEqual([], self.calls)

    def test_action_validates_saved_options_and_strict_boolean(self):
        config = self.assets.action(self.item, "confirm")
        self.assertTrue(config.validate_input({"optionId": "allowed", "confirmed": True}))
        for inputs in ({"optionId": "foreign", "confirmed": True},
                       {"optionId": "allowed", "confirmed": 1},
                       {"optionId": "allowed", "confirmed": True, "userId": "foreign"}):
            self.assertFalse(config.validate_input(inputs))
        self.assertEqual(VERSIONS, config.effective_versions)
        self.assertTrue(config.completes_interaction)
        self.assertEqual([], self.calls)  # Configuration lookup does not execute.

    def test_changed_application_subset_is_not_silently_replaced(self):
        self.reader.application_version = "v2"
        with self.assertRaisesRegex(ActionRejected, "RESET_REQUIRED"):
            self.assets.action(self.item, "confirm")
        self.assertEqual([], self.calls)

    def test_changed_run_closure_rejects_before_resolution_dispatch(self):
        self.reader.current = (("WORKFLOW:w", "v2"),)
        with self.assertRaisesRegex(ActionRejected, "RESET_REQUIRED"):
            self.assets.action(self.item, "confirm")
        self.assertEqual([], self.calls)

    def test_bound_node_replaces_only_the_trusted_node_scope(self):
        assets = RuntimeAssets(
            self.reader, self.run, {"confirm": self.spec}, self.definition,
            bound_node_id="copy",
        )
        bound = assets.context(self.run.context())
        self.assertEqual("copy", bound.invocation_scope.node_id)
        self.assertEqual(self.run.owner, bound.trusted_context)
        self.assertEqual(self.run.run_id, bound.invocation_scope.run_id)
