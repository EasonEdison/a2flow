import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from skillweave_contracts import (
    APPROVED_DEFINITION_NAMES,
    CONTRACT_REVISION,
    ContractValidationError,
    ResultInterpretationPolicySet,
    TrustedInvocationContext,
    UseSkillRequest,
    UseSkillResult,
    ValidationIssue,
    load_approved_schema,
    load_definition_schema,
    parse_definition,
)


def valid_policy_set():
    return {
        "resultInterpretationPolicies": [
            {
                "contractRevision": CONTRACT_REVISION,
                "policyRef": "schema_policy_demo",
                "operator": "SCHEMA_VALID",
            },
            {
                "contractRevision": CONTRACT_REVISION,
                "policyRef": "success_policy_demo",
                "operator": "JSON_POINTER_EQUALS",
                "jsonPointer": "/status",
                "expectedLiteral": "SUCCEEDED",
            },
        ],
        "defaultSuccessPolicyRef": "success_policy_demo",
    }


def valid_skill_result():
    return {
        "contractRevision": CONTRACT_REVISION,
        "content": {
            "instructions": "Produce a brief from the authorized evidence.",
            "resources": [
                {
                    "handleId": "material_demo_001",
                    "accessMode": "READ_ONLY",
                    "logicalPath": "references/output-format.md",
                    "mediaType": "text/markdown",
                    "byteSize": 494,
                    "contentDigest": "sha256:" + "b" * 64,
                }
            ],
            "requiredToolNames": ["execute_ability"],
        },
        "artifact": {
            "skillKey": "demo/evidence-first-brief",
            "resolvedVersion": {
                "asset": {"assetType": "SKILL", "assetId": "skill_demo"},
                "versionId": "skill_v2",
            },
            "contentDigest": "sha256:" + "4" * 64,
            "environment": "ONLINE",
            "selection": "ONLINE_GRAY",
            "evidenceRef": "evidence_demo_001",
        },
    }


class RequestAndContextTests(unittest.TestCase):
    def test_request_is_strict_closed_and_round_trips(self):
        model = UseSkillRequest.from_mapping({"skillKey": "demo/evidence-first-brief"})

        self.assertEqual(model.to_mapping(), {"skillKey": "demo/evidence-first-brief"})
        with self.assertRaises(FrozenInstanceError):
            model.skill_key = "changed"

        for invalid in (
            {"skillKey": 7},
            {"skillKey": "demo/evidence-first-brief", "environment": "ONLINE"},
            {"skillKey": "demo/evidence-first-brief\n"},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ContractValidationError):
                UseSkillRequest.from_mapping(invalid)

    def test_trusted_invocation_context_preserves_server_only_scope(self):
        payload = {
            "contractRevision": CONTRACT_REVISION,
            "trustedContext": {"userId": '1011', "environment": "PRT"},
            "invocationScope": {
                "kind": "WORKFLOW",
                "conversationId": "conversation_1",
                "runId": "run_1",
                "nodeId": "node_1",
            },
            "controlRequestId": "control_1",
        }

        model = TrustedInvocationContext.from_mapping(payload)

        self.assertEqual(model.to_mapping(), payload)
        self.assertEqual(model.invocation_scope.kind, "WORKFLOW")

    def test_context_rejects_coercion_and_unknown_server_fields(self):
        payload = {
            "contractRevision": CONTRACT_REVISION,
            "trustedContext": {
                "userId": 12,
                "environment": "ONLINE",
                "serverVersion": "v1",
            },
            "invocationScope": {"kind": "CONVERSATION", "conversationId": "c_1"},
            "controlRequestId": "control_1",
        }

        with self.assertRaises(ContractValidationError) as raised:
            TrustedInvocationContext.from_mapping(payload)

        self.assertTrue(raised.exception.issues)
        self.assertTrue(all(issue.path.startswith("$") for issue in raised.exception.issues))

    def test_workflow_scope_rejects_explicit_null_conversation_id(self):
        payload = {
            "contractRevision": CONTRACT_REVISION,
            "trustedContext": {"userId": '1011', "environment": "ONLINE"},
            "invocationScope": {
                "kind": "WORKFLOW",
                "conversationId": None,
                "runId": "run_1",
                "nodeId": "node_1",
            },
            "controlRequestId": "control_1",
        }

        with self.assertRaises(ContractValidationError):
            TrustedInvocationContext.from_mapping(payload)


class SkillResultTests(unittest.TestCase):
    def test_skill_result_is_strict_and_round_trips(self):
        payload = valid_skill_result()

        model = UseSkillResult.from_mapping(payload)
        payload["content"]["resources"].clear()
        first_output = model.to_mapping()
        first_output["content"]["resources"].clear()

        self.assertEqual(len(model.content.resources), 1)
        self.assertEqual(len(model.to_mapping()["content"]["resources"]), 1)

    def test_duplicate_resource_logical_path_is_rejected(self):
        payload = valid_skill_result()
        duplicate = dict(payload["content"]["resources"][0])
        duplicate["handleId"] = "material_demo_002"
        payload["content"]["resources"].append(duplicate)

        with self.assertRaises(ContractValidationError) as raised:
            UseSkillResult.from_mapping(payload)

        self.assertIn("duplicate_resource_path", {issue.code for issue in raised.exception.issues})

    def test_artifact_environment_and_selection_must_match(self):
        payload = valid_skill_result()
        payload["artifact"]["environment"] = "PRT"

        with self.assertRaises(ContractValidationError) as raised:
            UseSkillResult.from_mapping(payload)

        self.assertIn("invalid_selection", {issue.code for issue in raised.exception.issues})

    def test_integer_fields_do_not_accept_boolean_or_string_coercion(self):
        for invalid_size in (True, "494"):
            payload = valid_skill_result()
            payload["content"]["resources"][0]["byteSize"] = invalid_size
            with self.subTest(value=invalid_size), self.assertRaises(ContractValidationError):
                UseSkillResult.from_mapping(payload)


class PolicyTests(unittest.TestCase):
    def test_policy_set_is_strict_and_round_trips(self):
        payload = valid_policy_set()

        model = ResultInterpretationPolicySet.from_mapping(payload)

        self.assertEqual(model.to_mapping(), payload)
        self.assertEqual(model.default_success_policy_ref, "success_policy_demo")

    def test_duplicate_policy_ref_and_dangling_default_are_rejected(self):
        duplicate = valid_policy_set()
        duplicate["resultInterpretationPolicies"][1]["policyRef"] = "schema_policy_demo"
        dangling = valid_policy_set()
        dangling["defaultSuccessPolicyRef"] = "missing_policy"

        for payload, code in (
            (duplicate, "duplicate_policy_ref"),
            (dangling, "unresolved_default_policy"),
        ):
            with self.subTest(code=code), self.assertRaises(ContractValidationError) as raised:
                ResultInterpretationPolicySet.from_mapping(payload)
            self.assertIn(code, {issue.code for issue in raised.exception.issues})

    def test_policy_operator_shape_and_literal_type_are_not_coerced(self):
        invalid_schema = valid_policy_set()
        invalid_schema["resultInterpretationPolicies"][0]["expectedLiteral"] = True
        invalid_literal = valid_policy_set()
        invalid_literal["resultInterpretationPolicies"][1]["expectedLiteral"] = {"status": "ok"}

        for payload in (invalid_schema, invalid_literal):
            with self.assertRaises(ContractValidationError):
                ResultInterpretationPolicySet.from_mapping(payload)

        for invalid_number in (float("nan"), float("inf"), float("-inf")):
            payload = valid_policy_set()
            payload["resultInterpretationPolicies"][1]["expectedLiteral"] = invalid_number
            with self.subTest(value=invalid_number), self.assertRaises(ContractValidationError):
                ResultInterpretationPolicySet.from_mapping(payload)


class ErrorContractTests(unittest.TestCase):
    def test_error_issues_are_defensively_copied_and_read_only(self):
        caller_issues = [ValidationIssue(path="$.skillKey", code="invalid", message="bad")]

        error = ContractValidationError(caller_issues)
        caller_issues.clear()

        self.assertEqual(len(error.issues), 1)
        with self.assertRaises(AttributeError):
            error.issues = ()


class SchemaAndDispatchTests(unittest.TestCase):
    def test_approved_schema_loader_exposes_only_released_definitions(self):
        schema = load_approved_schema()

        self.assertIn("useSkillResult", schema["definitions"])
        self.assertIn("resultInterpretationPolicySet", schema["definitions"])
        self.assertNotIn("controlRequest", schema["definitions"])
        skill_key_schema = load_definition_schema("skillKey")
        self.assertEqual(skill_key_schema["$ref"], "#/definitions/skillKey")
        self.assertEqual(skill_key_schema["definitions"]["skillKey"]["type"], "string")
        with self.assertRaises(KeyError):
            load_definition_schema("controlRequest")

    def test_composite_definition_schema_has_no_dangling_local_refs(self):
        schema = load_definition_schema("trustedContext")

        self.assertEqual(schema["$ref"], "#/definitions/trustedContext")

        def local_refs(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "$ref" and isinstance(item, str):
                        yield item
                    else:
                        yield from local_refs(item)
            elif isinstance(value, list):
                for item in value:
                    yield from local_refs(item)

        for ref in local_refs(schema):
            self.assertTrue(ref.startswith("#/definitions/"), ref)
            self.assertIn(ref.rsplit("/", 1)[-1], schema["definitions"])

    def test_explicit_definition_dispatch_has_no_generic_fallback(self):
        parsed = parse_definition("useSkillRequest", {"skillKey": "demo/evidence"})

        self.assertIsInstance(parsed, UseSkillRequest)
        with self.assertRaises(KeyError):
            parse_definition("controlRequest", {})

        for definition_name in APPROVED_DEFINITION_NAMES:
            with self.subTest(definition=definition_name):
                try:
                    parse_definition(definition_name, None)
                except ContractValidationError:
                    pass
                except KeyError as error:
                    self.fail(f"approved definition has no parser: {error}")

    def test_all_released_synthetic_cases_match_the_thin_adapter(self):
        contracts_root = Path(__file__).resolve().parents[2]
        with (contracts_root / "tests" / "cases.json").open(encoding="utf-8") as handle:
            cases = json.load(handle)
        released_cases = [
            case for case in cases if case["definition"] in APPROVED_DEFINITION_NAMES
        ]

        self.assertTrue(released_cases)
        for case in released_cases:
            with self.subTest(name=case["name"]):
                with (contracts_root / "tests" / case['fixture']).open(encoding="utf-8") as handle:
                    payload = json.load(handle)
                try:
                    parse_definition(case["definition"], payload)
                    actual_valid = True
                except ContractValidationError:
                    actual_valid = False
                self.assertEqual(actual_valid, case["expectedValid"])


if __name__ == "__main__":
    unittest.main()
