from copy import deepcopy
from dataclasses import FrozenInstanceError
import unittest

from capability_registry import (
    AbilityDefinitionValidator,
    AdapterOperationDescriptor,
)


def valid_ability_payload():
    return {
        "abilityKey": "demo.catalog.lookup",
        "modelArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
            },
        },
        "resolvedInputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["query", "userId"],
            "properties": {
                "query": {"type": "string"},
                "userId": {"type": "string"},
            },
        },
        "outputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["ok"],
            "properties": {
                "ok": {"type": "boolean"},
            },
        },
        "inputBindings": [
            {
                "targetPath": "/query",
                "source": "MODEL_ARGUMENT",
                "sourcePath": "/query",
            },
            {
                "targetPath": "/userId",
                "source": "TRUSTED_CONTEXT",
                "sourcePath": "/userId",
            },
        ],
        "credentialRequirements": [
            {
                "slotId": "demoRead",
                "required": True,
            },
        ],
        "adapterOperationRef": "demo.catalog.lookup.read",
        "resultInterpretationPolicies": [
            {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "policyRef": "okTrue",
                "operator": "JSON_POINTER_EQUALS",
                "jsonPointer": "/ok",
                "expectedLiteral": True,
            },
        ],
        "defaultSuccessPolicyRef": "okTrue",
    }


class RecordingPolicySetValidator:
    def __init__(self):
        self.seen_policy_set = None

    def validate(self, policy_set):
        self.seen_policy_set = policy_set
        return ()


class FixedOperationCatalog:
    def __init__(self, descriptor):
        self.descriptor = descriptor

    def lookup(self, operation_ref):
        if operation_ref == self.descriptor.operation_ref:
            return self.descriptor
        return None


class MissingOperationCatalog:
    def lookup(self, operation_ref):
        return None


class AbilityDefinitionValidatorHappyPathTests(unittest.TestCase):
    def test_valid_definition_builds_immutable_publication_metadata(self):
        policy_validator = RecordingPolicySetValidator()
        operation = AdapterOperationDescriptor(
            operation_ref="demo.catalog.lookup.read",
            input_paths=frozenset({"/query", "/userId"}),
            credential_slots=frozenset({"demoRead"}),
        )
        validator = AbilityDefinitionValidator(
            operation_catalog=FixedOperationCatalog(operation),
            policy_set_validator=policy_validator,
        )

        result = validator.validate(valid_ability_payload())
        self.assertTrue(result.is_valid)
        self.assertEqual((), result.issues)
        self.assertEqual("demo.catalog.lookup", result.metadata.ability_key)
        self.assertEqual("demo.catalog.lookup.read", result.metadata.adapter_operation_ref)
        self.assertEqual(("/query",), result.metadata.model_argument_paths)
        self.assertEqual(("/userId",), result.metadata.trusted_context_paths)
        self.assertEqual(("demoRead",), result.metadata.credential_slots)
        self.assertEqual(("okTrue",), result.metadata.result_policy_refs)
        self.assertEqual("okTrue", result.metadata.default_success_policy_ref)
        self.assertEqual(
            {
                "resultInterpretationPolicies": valid_ability_payload()["resultInterpretationPolicies"],
                "defaultSuccessPolicyRef": "okTrue",
            },
            policy_validator.seen_policy_set,
        )
        with self.assertRaises(FrozenInstanceError):
            result.metadata.ability_key = "changed"


class AbilityDefinitionValidatorBoundaryTests(unittest.TestCase):
    def setUp(self):
        operation = AdapterOperationDescriptor(
            operation_ref="demo.catalog.lookup.read",
            input_paths=frozenset({"/query", "/query/text", "/userId"}),
            credential_slots=frozenset({"demoRead"}),
        )
        self.validator = AbilityDefinitionValidator(
            operation_catalog=FixedOperationCatalog(operation),
            policy_set_validator=RecordingPolicySetValidator(),
        )

    def assert_invalid(self, payload, expected_code):
        result = self.validator.validate(payload)

        self.assertFalse(result.is_valid)
        self.assertIsNone(result.metadata)
        self.assertIn(expected_code, {issue.code for issue in result.issues})

    def test_rejects_model_visible_server_fields(self):
        reserved_names = (
            "userId",
            "environment",
            "credentialRef",
            "releaseVersion",
        )
        for reserved_name in reserved_names:
            with self.subTest(reserved_name=reserved_name):
                payload = deepcopy(valid_ability_payload())
                payload["modelArgumentSchema"]["properties"][reserved_name] = {
                    "type": "string",
                }
                self.assert_invalid(payload, "MODEL_ARGUMENT_RESERVED_FIELD")

    def test_rejects_unknown_ability_field(self):
        payload = deepcopy(valid_ability_payload())
        payload["credentialValue"] = "not-allowed"

        self.assert_invalid(payload, "ABILITY_FIELD_UNSUPPORTED")

    def test_rejects_credential_value_metadata(self):
        forbidden_fields = ("referenceId", "value", "secret", "token")
        for forbidden_field in forbidden_fields:
            with self.subTest(forbidden_field=forbidden_field):
                payload = deepcopy(valid_ability_payload())
                payload["credentialRequirements"][0][forbidden_field] = "not-allowed"
                self.assert_invalid(
                    payload,
                    "CREDENTIAL_REQUIREMENT_FIELD_UNSUPPORTED",
                )

    def test_rejects_non_string_top_level_field_without_crashing(self):
        payload = deepcopy(valid_ability_payload())
        payload[1] = "not-allowed"
        payload["credentialValue"] = "not-allowed"

        self.assert_invalid(payload, "ABILITY_FIELD_UNSUPPORTED")

    def test_rejects_non_scalar_binding_source_without_crashing(self):
        payload = deepcopy(valid_ability_payload())
        payload["inputBindings"][0]["source"] = ["MODEL_ARGUMENT"]

        self.assert_invalid(payload, "INPUT_BINDING_SOURCE_UNSUPPORTED")

    def test_rejects_unreleased_binding_source(self):
        payload = deepcopy(valid_ability_payload())
        payload["inputBindings"][0]["source"] = "CREDENTIAL_REFERENCE"

        self.assert_invalid(payload, "INPUT_BINDING_SOURCE_UNSUPPORTED")

    def test_rejects_undeclared_model_source_path(self):
        payload = deepcopy(valid_ability_payload())
        payload["inputBindings"][0]["sourcePath"] = "/missing"

        self.assert_invalid(payload, "MODEL_ARGUMENT_SOURCE_UNDECLARED")

    def test_rejects_unapproved_trusted_context_source(self):
        payload = deepcopy(valid_ability_payload())
        payload["inputBindings"][1]["sourcePath"] = "/authorizationContext"

        self.assert_invalid(payload, "TRUSTED_CONTEXT_SOURCE_UNSUPPORTED")

    def test_rejects_invalid_target_pointer(self):
        payload = deepcopy(valid_ability_payload())
        payload["inputBindings"][0]["targetPath"] = "query"

        self.assert_invalid(payload, "INPUT_BINDING_POINTER_INVALID")

    def test_rejects_duplicate_target_path(self):
        payload = deepcopy(valid_ability_payload())
        payload["inputBindings"][1]["targetPath"] = "/query"

        self.assert_invalid(payload, "INPUT_BINDING_TARGET_DUPLICATE")

    def test_rejects_overlapping_target_paths(self):
        payload = deepcopy(valid_ability_payload())
        payload["inputBindings"].append(
            {
                "targetPath": "/query/text",
                "source": "MODEL_ARGUMENT",
                "sourcePath": "/query",
            },
        )

        self.assert_invalid(payload, "INPUT_BINDING_TARGET_OVERLAP")

    def test_rejects_missing_adapter_operation(self):
        validator = AbilityDefinitionValidator(
            operation_catalog=MissingOperationCatalog(),
            policy_set_validator=RecordingPolicySetValidator(),
        )

        result = validator.validate(valid_ability_payload())

        self.assertFalse(result.is_valid)
        self.assertIsNone(result.metadata)
        self.assertIn(
            "ADAPTER_OPERATION_NOT_FOUND",
            {issue.code for issue in result.issues},
        )

    def test_rejects_target_path_unsupported_by_adapter_operation(self):
        payload = deepcopy(valid_ability_payload())
        payload["inputBindings"][0]["targetPath"] = "/unsupported"

        self.assert_invalid(payload, "ADAPTER_INPUT_UNSUPPORTED")

    def test_rejects_credential_slot_unsupported_by_adapter_operation(self):
        payload = deepcopy(valid_ability_payload())
        payload["credentialRequirements"][0]["slotId"] = "otherSlot"

        self.assert_invalid(payload, "CREDENTIAL_SLOT_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
