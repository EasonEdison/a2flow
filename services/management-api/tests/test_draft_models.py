"""Structural draft DTO and relation-projection regression coverage."""

import copy
import unittest

from a2flow_management.contracts import ManagementError
from a2flow_management.draft_models import (
    draft_reference_targets,
    parse_draft_structure,
)


class DraftModelTests(unittest.TestCase):
    def test_skill_parse_is_validation_only_and_keeps_unknown_fields(self) -> None:
        document = {
            "metadata": {"name": "choose-plan", "description": "choose", "extension": 1},
            "skillMd": "---\nname: choose-plan\ndescription: choose\n---\n",
            "requiredToolNames": ["execute_ability"],
            "abilityBindings": ["activity.plan.list"],
            "applicationBindings": ["activity-package.choose-plan"],
            "resources": [],
            "extension": {"kept": True},
        }
        before = copy.deepcopy(document)

        parsed = parse_draft_structure("SKILL", "activity-package/choose-plan", document)

        self.assertEqual(["activity.plan.list"], parsed.abilityBindings)
        self.assertEqual(before, document)
        self.assertEqual({"kept": True}, parsed.model_extra["extension"])

    def test_identity_mismatches_keep_stable_management_errors(self) -> None:
        workflow = {
            "definitionKey": "different",
            "topology": "SEQUENTIAL",
            "nodes": [],
        }

        with self.assertRaises(ManagementError) as captured:
            parse_draft_structure("WORKFLOW", "activity-package", workflow)

        self.assertEqual("WORKFLOW_KEY_MISMATCH", captured.exception.code)

    def test_reference_projection_accepts_partial_snapshots_without_defaults(self) -> None:
        skill = {
            "abilityBindings": ["activity.plan.list"],
            "applicationBindings": ["activity-package.choose-plan"],
        }
        workflow = {"nodes": [{"skillKey": "activity-package/choose-plan"}]}

        self.assertEqual(
            (
                ("ABILITY", "activity.plan.list"),
                ("APPLICATION", "activity-package.choose-plan"),
            ),
            draft_reference_targets("SKILL", skill),
        )
        self.assertEqual(
            (("SKILL", "activity-package/choose-plan"),),
            draft_reference_targets("WORKFLOW", workflow),
        )

    def test_invalid_relation_shapes_fail_before_repository_write(self) -> None:
        with self.assertRaises(ManagementError) as captured:
            draft_reference_targets(
                "APPLICATION",
                {"dependencies": [{"kind": "ABILITY", "key": 7}]},
            )

        self.assertEqual("INVALID_DEPENDENCIES", captured.exception.code)

    def test_non_publishable_business_values_remain_saveable_structure(self) -> None:
        component = {
            "definition": {
                "catalogKey": "activity.catalog",
                "protocolProfileRef": "unsupported-yet-structural",
                "components": [],
            },
            "dependencies": [],
        }
        workflow = {
            "definitionKey": "activity-package",
            "topology": "FUTURE_TOPOLOGY",
            "nodes": [],
        }

        self.assertEqual(
            "unsupported-yet-structural",
            parse_draft_structure(
                "COMPONENT", "activity.catalog", component
            ).definition.protocolProfileRef,
        )
        self.assertEqual(
            "FUTURE_TOPOLOGY",
            parse_draft_structure("WORKFLOW", "activity-package", workflow).topology,
        )


if __name__ == "__main__":
    unittest.main()
