"""Runtime compatibility checks for the integrated SW-P1-SUBSET-01 adapter."""

import json
import unittest
from pathlib import Path
from typing import Any

from skillweave_contracts import ContractValidationError, parse_definition


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPOSITORY_ROOT / "packages/contracts/tests"
APPROVED_CASE_DEFINITIONS = {
    "authorizedMaterialHandle",
    "trustedContext",
    "trustedInvocationContext",
    "useSkillRequest",
    "useSkillResult",
}


class ContractSubsetCompatibilityTest(unittest.TestCase):
    """Keeps Runtime consumption aligned to the integrated neutral adapter."""

    def test_approved_subset_fixtures_match_expected_validity(self) -> None:
        """Break caught: Runtime consumption drifts from reviewed neutral fixtures."""

        cases: list[dict[str, Any]] = json.loads(
            (FIXTURE_ROOT / "cases.json").read_text(encoding="utf-8")
        )
        checked = 0
        for case in cases:
            if case["definition"] not in APPROVED_CASE_DEFINITIONS:
                continue
            checked += 1
            payload = json.loads(
                (FIXTURE_ROOT / case["fixture"]).read_text(encoding="utf-8")
            )
            with self.subTest(name=case["name"]):
                if case["expectedValid"]:
                    parse_definition(case["definition"], payload)
                else:
                    with self.assertRaises(ContractValidationError):
                        parse_definition(case["definition"], payload)

        self.assertEqual(15, checked)
