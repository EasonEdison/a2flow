"""Focused checks for the shared Ability execution kernel."""

from dataclasses import replace
from types import SimpleNamespace
import unittest

from skillweave_contracts import TrustedContext

from agent_workflow_runtime.ability_execution import (
    ACTION_AUTHORIZATION,
    MODEL_AUTHORIZATION,
    OperationSpec,
    execute_ability,
)
from agent_workflow_runtime.asset_adapters import OperationSpec as CompatibleOperationSpec
from agent_workflow_runtime.models import ActionRejected


def ability(*, policies=None, credentials=None, bindings=None):
    return SimpleNamespace(
        asset_id="calculate",
        version_id="v1",
        operation_ref="local.calculate",
        publication_metadata=SimpleNamespace(ability_key="demo.calculate"),
        definition={
            "credentialRequirements": [] if credentials is None else credentials,
            "inputBindings": [
                {
                    "source": "MODEL_ARGUMENT",
                    "sourcePath": "/value",
                    "targetPath": "/value",
                }
            ] if bindings is None else bindings,
            "defaultSuccessPolicyRef": "accepted",
            "resultInterpretationPolicies": [{
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "policyRef": "accepted",
                "operator": "JSON_POINTER_EQUALS",
                "jsonPointer": "/accepted",
                "expectedLiteral": True,
            }] if policies is None else policies,
        },
    )


def valid_input(value):
    return type(value) is dict and set(value) == {"value"} and type(value["value"]) is int


def valid_result(value):
    return (
        type(value) is dict
        and set(value) == {"accepted", "doubled"}
        and type(value["accepted"]) is bool
        and type(value["doubled"]) is int
    )


class AbilityExecutionTest(unittest.TestCase):
    def setUp(self):
        self.owner = TrustedContext(1001, "PRT")
        self.calls = []

        def execute(arguments, owner):
            self.calls.append((arguments, owner))
            arguments["value"] = -1
            return {"accepted": True, "doubled": 2}

        self.operation = OperationSpec(
            execute,
            valid_input,
            valid_result,
            lambda definition: definition["defaultSuccessPolicyRef"] == "accepted",
            model_allowed=True,
            action_allowed=False,
        )

    def test_model_execution_isolated_and_operation_spec_import_compatible(self):
        self.assertIs(OperationSpec, CompatibleOperationSpec)
        arguments = {"value": 1}
        response = execute_ability(
            ability(), self.operation, arguments, self.owner,
            authorization=MODEL_AUTHORIZATION,
        )
        self.assertEqual(
            {"abilityKey": "demo.calculate", "output": {"accepted": True, "doubled": 2},
             "versionId": "v1"},
            response,
        )
        self.assertEqual({"value": 1}, arguments)
        self.assertEqual(self.owner, self.calls[0][1])

    def test_authorization_is_explicit_for_model_and_action(self):
        action_operation = replace(
            self.operation, model_allowed=False, action_allowed=True,
        )
        response = execute_ability(
            ability(), action_operation, {"value": 1}, self.owner,
            authorization=ACTION_AUTHORIZATION,
        )
        self.assertTrue(response["output"]["accepted"])
        for operation, authorization, code in (
            (action_operation, MODEL_AUTHORIZATION, "ABILITY_NOT_MODEL_CALLABLE"),
            (self.operation, ACTION_AUTHORIZATION, "ABILITY_NOT_ACTION_CALLABLE"),
            (self.operation, "SYSTEM", "INVALID_ABILITY_AUTHORIZATION"),
        ):
            with self.subTest(authorization=authorization), self.assertRaisesRegex(
                ActionRejected, code,
            ):
                execute_ability(
                    ability(), operation, {"value": 1}, self.owner,
                    authorization=authorization,
                )

    def test_owner_must_be_exact_trusted_context(self):
        class DerivedOwner(TrustedContext):
            pass

        for owner in (
            {"userId": "1001", "environment": "PRT"},
            SimpleNamespace(user_id=1001, environment="PRT"),
            DerivedOwner(1001, "PRT"),
        ):
            with self.subTest(owner=type(owner).__name__), self.assertRaisesRegex(
                ActionRejected, "TRUSTED_CONTEXT_REQUIRED",
            ):
                execute_ability(
                    ability(), self.operation, {"value": 1}, owner,
                    authorization=MODEL_AUTHORIZATION,
                )
        self.assertEqual([], self.calls)

    def test_definition_input_and_registered_operation_fail_closed(self):
        cases = (
            (ability(credentials=[{"slotId": "token"}]), self.operation,
             {"value": 1}, "UNSUPPORTED_ABILITY_BINDING"),
            (ability(bindings=[{"source": "AUTHORIZATION_CONTEXT",
                                "sourcePath": "/userId", "targetPath": "/value"}]),
             self.operation, {"value": 1}, "UNSUPPORTED_ABILITY_BINDING"),
            (ability(), replace(self.operation, validate_definition=lambda _: False),
             {"value": 1}, "UNSUPPORTED_ABILITY_PROFILE"),
            (ability(), object(), {"value": 1}, "OPERATION_NOT_REGISTERED"),
            (ability(), self.operation, {"value": "1"}, "INVALID_ABILITY_INPUT"),
        )
        for resolved, operation, arguments, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(ActionRejected, code):
                execute_ability(
                    resolved, operation, arguments, self.owner,
                    authorization=MODEL_AUTHORIZATION,
                )
        self.assertEqual([], self.calls)

    def test_result_validation_policy_and_policy_resolution_fail_closed(self):
        false_result = replace(
            self.operation,
            execute=lambda _arguments, _owner: {"accepted": False, "doubled": 2},
        )
        invalid_result = replace(
            self.operation,
            execute=lambda _arguments, _owner: {"accepted": True},
        )
        for resolved, operation, policy_ref, code in (
            (ability(), false_result, None, "ABILITY_RESULT_NOT_SUCCESS"),
            (ability(), invalid_result, None, "ABILITY_RESULT_NOT_SUCCESS"),
            (ability(), self.operation, "missing", "RESULT_POLICY_NOT_FOUND"),
        ):
            with self.subTest(code=code), self.assertRaisesRegex(ActionRejected, code):
                execute_ability(
                    resolved, operation, {"value": 1}, self.owner,
                    authorization=MODEL_AUTHORIZATION,
                    success_policy_ref=policy_ref,
                )


if __name__ == "__main__":
    unittest.main()
