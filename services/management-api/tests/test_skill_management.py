"""Focused AF10 shared shell and Skill management tests."""
from types import SimpleNamespace
import base64
import unittest

from a2flow_asset_store.records import digest
from a2flow_management import (
    ManagementError, ManagementService, MemoryDraftRepository,
    PublicationTarget, TrustedManagementContext,
)
from a2flow_management.features.skill import create_skill_feature


SKILL_MD = """---
name: activity-plan
description: Plan an activity and request explicit confirmation.
---

# Plan
"""


def entry(raw):
    return {"handleId": "skill-instructions", "logicalPath": "SKILL.md",
            "mediaType": "text/markdown", "byteSize": len(raw),
            "contentDigest": digest(raw),
            "base64": base64.b64encode(raw).decode("ascii")}


class FakeReader:
    def __init__(self):
        self.definition = {"entries": [entry(SKILL_MD.encode())],
                           "requiredToolNames": ["execute_ability"]}
        self.dependencies = [
            {"kind": "ABILITY", "key": "activity-planning.budget"},
            {"kind": "APPLICATION", "key": "activity-planning.confirm"},
        ]

    def list_skills(self, context):
        return ({"skillKey": "activity-planning/plan",
                 "assetId": "skill-plan", "versionId": "v1"},)

    def load_skill(self, key, context):
        evidence = SimpleNamespace(
            asset_id="skill-plan", version_id="v1",
            content_digest="sha256:" + "1" * 64, selection="PRT_CURRENT")
        return SimpleNamespace(
            instruction_entry=SimpleNamespace(text=SKILL_MD),
            resource_entries=(), required_tool_names=("execute_ability",),
            resolution_evidence=evidence)

    def resolve_asset(self, kind, key, context):
        if kind == "SKILL" and key == "activity-planning/plan":
            return {"assetId": "skill-plan", "definition": self.definition,
                    "dependencies": self.dependencies}
        if (kind, key) in {
                ("ABILITY", "activity-planning.budget"),
                ("APPLICATION", "activity-planning.confirm")}:
            return {"assetId": kind.lower() + "-bound"}
        error = ManagementError("ASSET_NOT_FOUND", 404)
        raise error


class ManagementSkillTests(unittest.TestCase):
    def setUp(self):
        self.reader = FakeReader()
        self.drafts = MemoryDraftRepository()
        self.feature = create_skill_feature(
            self.reader, self.drafts, "a2flow-mvp-activity-planning")
        self.service = ManagementService([self.feature])
        self.admin = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))
        self.user = TrustedManagementContext(
            "user-1", "PRT", frozenset({"USER"}))

    def draft_document(self):
        return {
            "metadata": {"name": "activity-plan",
                         "description": "Plan an activity and request explicit confirmation."},
            "skillMd": SKILL_MD,
            "requiredToolNames": ["execute_ability"],
            "abilityBindings": ["activity-planning.budget"],
            "applicationBindings": ["activity-planning.confirm"],
            "resources": [],
        }

    def test_reader_can_browse_but_only_admin_can_open_drafts(self):
        listed = self.service.list_published(self.user, "SKILL")
        self.assertEqual("activity-planning/plan", listed[0]["skillKey"])
        detail = self.service.get_published(
            self.user, "SKILL", "activity-planning/plan")
        self.assertEqual("PRT_CURRENT", detail["resolution"]["selection"])
        with self.assertRaisesRegex(ManagementError, "ADMIN_REQUIRED"):
            self.service.get_draft(
                self.user, "SKILL", "activity-planning/plan")

    def test_draft_validation_and_publication_plan_do_not_publish(self):
        initial = self.service.get_draft(
            self.admin, "SKILL", "activity-planning/plan")
        self.assertEqual(0, initial.revision)
        invalid = self.draft_document()
        invalid["metadata"]["description"] = "does not match frontmatter"
        saved = self.service.save_draft(
            self.admin, "SKILL", "activity-planning/plan", 0, invalid)
        self.assertEqual(1, saved.revision)
        report = self.service.validate_draft(
            self.admin, "SKILL", "activity-planning/plan")
        self.assertFalse(report.valid)
        fixed = self.service.save_draft(
            self.admin, "SKILL", "activity-planning/plan", 1,
            self.draft_document())
        self.assertEqual(2, fixed.revision)
        report = self.service.validate_draft(
            self.admin, "SKILL", "activity-planning/plan")
        self.assertTrue(report.valid)
        plan = self.service.prepare_publication(
            self.admin, "SKILL", "activity-planning/plan", 2,
            PublicationTarget("PRT", "v2", "CURRENT"))
        self.assertEqual("v2", plan.candidate["versionId"])
        self.assertEqual("skill-plan", plan.candidate["assetId"])
        self.assertEqual("v1", self.reader.list_skills(None)[0]["versionId"])

    def test_optimistic_revision_and_environment_are_enforced(self):
        self.service.save_draft(
            self.admin, "SKILL", "activity-planning/plan", 0,
            self.draft_document())
        with self.assertRaisesRegex(ManagementError, "DRAFT_REVISION_CONFLICT"):
            self.service.save_draft(
                self.admin, "SKILL", "activity-planning/plan", 0,
                self.draft_document())
        with self.assertRaisesRegex(ManagementError, "TARGET_ENVIRONMENT_MISMATCH"):
            self.service.prepare_publication(
                self.admin, "SKILL", "activity-planning/plan", 1,
                PublicationTarget("ONLINE", "v2", "STABLE"))


if __name__ == "__main__":
    unittest.main()
