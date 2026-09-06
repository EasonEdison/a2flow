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


def invalid_policy_set():
    return {
        "resultInterpretationPolicies": [
            {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "policyRef": "duplicate",
                "operator": "SCHEMA_VALID",
            },
            {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "policyRef": "duplicate",
                "operator": "JSON_POINTER_EQUALS",
                "jsonPointer": "/ok",
                "expectedLiteral": True,
            },
        ],
        "defaultSuccessPolicyRef": "missing",
    }


class SharedResultPolicySetValidatorTests(unittest.TestCase):
    def setUp(self):
        self.validator = SharedResultPolicySetValidator()

    def test_valid_policy_set_returns_immutable_empty_issues(self):
        issues = self.validator.validate(valid_policy_set())

        self.assertEqual((), issues)
        self.assertIsInstance(issues, tuple)

    def test_invalid_policy_set_preserves_shared_issue_details(self):
        payload = invalid_policy_set()
        with self.assertRaises(ContractValidationError) as raised:
            ResultInterpretationPolicySet.from_mapping(payload)
        expected_issues = tuple(
            (issue.path, issue.code, issue.message)
            for issue in raised.exception.issues
        )

        actual_issues = self.validator.validate(payload)

        self.assertGreaterEqual(len(actual_issues), 2)
        self.assertEqual(
            expected_issues,
            tuple(
                (issue.path, issue.code, issue.message)
                for issue in actual_issues
            ),
        )
        self.assertEqual(
            {
                "/defaultSuccessPolicyRef",
                "/resultInterpretationPolicies/1/policyRef",
            },
            {issue.path for issue in actual_issues},
        )


if __name__ == "__main__":
    unittest.main()
