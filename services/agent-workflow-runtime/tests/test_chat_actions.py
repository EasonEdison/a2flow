from dataclasses import replace
from types import SimpleNamespace
import unittest

from agent_workflow_runtime.chat.actions import ChatActionService
from agent_workflow_runtime.ability_execution import OperationSpec
from agent_workflow_runtime.models import ActionRejected
from skillweave_contracts import TrustedContext
from test_ability_execution import ability


class Store:
    def __init__(self):
        self.card = {"cardId": "c", "display": {"applicationKey": "app", "applicationVersion": "v1",
                     "data": {"options": [{"value": "a"}]}}}
        self.dispatched = False
        self.failures = []

    def get_binding(self, *args):
        return {"card": self.card, "metadata": {"skillKey": "skill", "recordedVersions": [["SKILL:s", "v1"]]}}

    def claim(self, *args):
        dispatch = not self.dispatched
        self.dispatched = True
        return {"dispatch": dispatch, "card": self.card}

    def finish(self, owner, conversation, card, request, result, success, completes):
        self.card.update(result=result, status="COMPLETED" if success and completes else "WAITING_ACTION")
        return self.card

    def fail(self, *args):
        self.failures.append(args[-1])


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.calls = []
        self.checks = []
        self.policy = {"successPolicyRef": "accepted", "completeInteractionOnSuccess": True}
        self.operation = OperationSpec(lambda inputs, owner: self.calls.append((inputs, owner)) or {"accepted": True},
            lambda inputs: set(inputs) == {"optionId"}, lambda result: isinstance(result, dict), lambda _: True,
            action_allowed=True)
        self.assets = SimpleNamespace(admit_skill=lambda _: None,
            check_versions=lambda versions: self.checks.append(versions),
            action_binding=lambda app, name: ({"resolvedVersion": {"versionId": "v1"}}, self.policy, ability(), self.operation))
        self.service = ChatActionService(self.store, lambda *args: self.assets)

    def execute(self, inputs=None):
        return self.service.execute(TrustedContext(1, "PRT"), "1", "c", request_id="r",
            action_name="select", inputs=inputs or {"optionId": "a"}, expected_revision=0)

    def test_real_result_completes_and_cached_claim_does_not_dispatch_again(self):
        self.assertEqual("COMPLETED", self.execute()["status"])
        self.execute()
        self.assertEqual(1, len(self.calls))
        self.assertGreaterEqual(len(self.checks), 3)

    def test_business_false_is_saved_and_does_not_complete(self):
        self.operation = replace(self.operation, execute=lambda *args: {"accepted": False})
        self.assertEqual("WAITING_ACTION", self.execute()["status"])
        self.assertEqual({"accepted": False}, self.store.card["result"])

    def test_success_without_completion_stays_interactive(self):
        self.policy["completeInteractionOnSuccess"] = False
        self.assertEqual("WAITING_ACTION", self.execute()["status"])

    def test_unoffered_choice_never_dispatches(self):
        with self.assertRaisesRegex(ActionRejected, "INVALID_ACTION_INPUT"):
            self.execute({"optionId": "forged"})
        self.assertFalse(self.store.dispatched)

    def test_dispatch_exception_is_unknown_not_retry(self):
        def fail(*args):
            raise RuntimeError("private backend details")
        self.operation = replace(self.operation, execute=fail)
        with self.assertRaisesRegex(ActionRejected, "ACTION_OUTCOME_UNKNOWN"):
            self.execute()
        self.assertEqual(["ACTION_OUTCOME_UNKNOWN"], self.store.failures)

    def test_changed_release_never_claims(self):
        def reject(versions):
            raise ActionRejected("RESET_REQUIRED")
        self.assets.check_versions = reject
        with self.assertRaisesRegex(ActionRejected, "RESET_REQUIRED"):
            self.execute()
        self.assertFalse(self.store.dispatched)
