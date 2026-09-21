"""Regression coverage for the generic authoring relation projection."""

import unittest

from a2flow_management.contracts import ManagedDraft, ManagementError
from a2flow_management.relations import draft_relations


class DraftRelationTests(unittest.TestCase):
    def test_skill_bindings_share_the_generic_relation_shape(self) -> None:
        draft = ManagedDraft.create(
            "SKILL",
            "activity-package/choose-plan",
            2,
            {
                "abilityBindings": ["activity.plan.list"],
                "applicationBindings": ["activity-package.choose-plan"],
            },
            101,
        )

        relations = draft_relations("a2flow", draft, 3)

        self.assertEqual(
            (
                ("ABILITY", "activity.plan.list", "SKILL_ABILITY"),
                (
                    "APPLICATION",
                    "activity-package.choose-plan",
                    "SKILL_APPLICATION",
                ),
            ),
            tuple(
                (item["targetKind"], item["targetKey"], item["relationType"]) for item in relations
            ),
        )
        self.assertTrue(all(item["sourceRevision"] == 3 for item in relations))

    def test_application_and_workflow_use_the_same_projection(self) -> None:
        application = ManagedDraft.create(
            "APPLICATION",
            "activity-package.choose-plan",
            0,
            {
                "dependencies": [
                    {"kind": "COMPONENT", "key": "ChoicePicker"},
                    {"kind": "ABILITY", "key": "activity.plan.list"},
                ]
            },
            101,
        )
        workflow = ManagedDraft.create(
            "WORKFLOW",
            "activity-package",
            0,
            {
                "nodes": [
                    {"skillKey": "activity-package/choose-plan"},
                    {"skillKey": "activity-package/confirm-schedule"},
                ]
            },
            101,
        )

        application_relations = draft_relations("a2flow", application, 1)
        workflow_relations = draft_relations("a2flow", workflow, 1)

        self.assertEqual(
            {"APPLICATION_ABILITY", "APPLICATION_COMPONENT"},
            {item["relationType"] for item in application_relations},
        )
        self.assertEqual(
            {"WORKFLOW_SKILL"},
            {item["relationType"] for item in workflow_relations},
        )

    def test_workspace_files_do_not_create_asset_relations(self) -> None:
        draft = ManagedDraft.create(
            "SKILL",
            "activity-package/choose-plan",
            0,
            {"abilityBindings": [], "applicationBindings": []},
            101,
        )

        self.assertEqual((), draft_relations("skill-workspace:a2flow", draft, 1))

    def test_invalid_binding_shape_fails_closed(self) -> None:
        draft = ManagedDraft.create(
            "SKILL",
            "activity-package/choose-plan",
            0,
            {"abilityBindings": "activity.plan.list"},
            101,
        )

        with self.assertRaisesRegex(ManagementError, "INVALID_BINDINGS"):
            draft_relations("a2flow", draft, 1)


if __name__ == "__main__":
    unittest.main()
