import unittest

from capability_registry import SharedResultPolicySetValidator
from skillweave_contracts import (
    ContractValidationError,
    ResultInterpretationPolicySet,
)


def valid_policy_set():
    return {
        "resultInterpretationPolicies": [
            {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "policyRef": "schemaValid",
                "operator": "SCHEMA_VALID",
            },
        ],
        "defaultSuccessPolicyRef": "schemaValid",
    }


def invalid_policy_sets():
    duplicate = valid_policy_set()
    duplicate["resultInterpretationPolicies"].append(
        {
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
            "policyRef": "schemaValid",
            "operator": "JSON_POINTER_EQUALS",
            "jsonPointer": "/ok",
            "expectedLiteral": True,
        },
    )
    dangling = valid_policy_set()
    dangling["defaultSuccessPolicyRef"] = "missing"
    return (
        (
            duplicate,
            "$.resultInterpretationPolicies",
            "duplicate_policy_ref",
        ),
        (
            dangling,
            "$.defaultSuccessPolicyRef",
            "unresolved_default_policy",
        ),
    )


class SharedResultPolicySetValidatorTests(unittest.TestCase):
    def setUp(self):
        self.validator = SharedResultPolicySetValidator()

    def test_valid_policy_set_returns_immutable_empty_issues(self):
        issues = self.validator.validate(valid_policy_set())

        self.assertEqual((), issues)
        self.assertIsInstance(issues, tuple)

    def test_invalid_policy_sets_preserve_shared_issue_details(self):
        for payload, expected_path, expected_code in invalid_policy_sets():
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(ContractValidationError) as raised:
                    ResultInterpretationPolicySet.from_mapping(payload)
                expected_issues = tuple(
                    (issue.path, issue.code, issue.message)
                    for issue in raised.exception.issues
                )

                actual_issues = self.validator.validate(payload)

                self.assertEqual(
                    expected_issues,
                    tuple(
                        (issue.path, issue.code, issue.message)
                        for issue in actual_issues
                    ),
                )
                self.assertEqual(
                    ((expected_path, expected_code),),
                    tuple(
                        (issue.path, issue.code)
                        for issue in actual_issues
                    ),
                )
                self.assertIsInstance(actual_issues, tuple)


if __name__ == "__main__":
    unittest.main()
