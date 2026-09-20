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
from skill_registry import PackageEntry, PackageEntryDescriptor


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
        raw = SKILL_MD.encode()
        instruction = PackageEntry(PackageEntryDescriptor(
            "skill-instructions", "SKILL.md", "text/markdown",
            len(raw), digest(raw)), raw)
        return SimpleNamespace(
            instruction_entry=instruction,
            resource_entries=(), required_tool_names=("execute_ability",),
            resolution_evidence=evidence)

    def asset_exists(self, kind, key, context):
        return kind == "SKILL" and key == "activity-planning/plan"

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
        self.drafts = MemoryDraftRepository("PRT")
        self.feature = create_skill_feature(
            self.reader, self.drafts, "a2flow-mvp-activity-planning")
        self.service = ManagementService([self.feature])
        self.admin = TrustedManagementContext(
            101, "PRT", frozenset({"ADMIN"}))
        self.user = TrustedManagementContext(
            102, "PRT", frozenset({"USER"}))

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

    def test_admin_creates_draft_only_skill_and_user_listing_stays_published_only(self):
        created = self.service.create_draft(
            self.admin, "SKILL", "new/skill")
        self.assertEqual(1, created.revision)
        self.assertEqual("new/skill", created.key)
        self.assertEqual(created, self.service.get_draft(
            self.admin, "SKILL", "new/skill"))
        admin_keys = {item.get("key", item.get("skillKey"))
                      for item in self.service.list_published(self.admin, "SKILL")}
        user_keys = {item.get("key", item.get("skillKey"))
                     for item in self.service.list_published(self.user, "SKILL")}
        self.assertIn("new/skill", admin_keys)
        self.assertNotIn("new/skill", user_keys)
        with self.assertRaisesRegex(ManagementError, "DRAFT_ALREADY_EXISTS"):
            self.service.create_draft(self.admin, "SKILL", "new/skill")
        with self.assertRaisesRegex(ManagementError, "ADMIN_REQUIRED"):
            self.service.create_draft(self.user, "SKILL", "other/skill")

    def test_create_rejects_existing_asset_without_resolving_user_route(self):
        class ExistingReader(FakeReader):
            def asset_exists(inner, kind, key, context):
                return key == "gray-only/skill"
            def resolve_asset(inner, kind, key, context):
                if key == "gray-only/skill":
                    raise ManagementError("SELECTED_VERSION_MISSING", 404)
                return super().resolve_asset(kind, key, context)

        service = ManagementService([create_skill_feature(
            ExistingReader(), MemoryDraftRepository("PRT"),
            "a2flow-mvp-activity-planning")])
        with self.assertRaisesRegex(ManagementError, "ASSET_ALREADY_EXISTS"):
            service.create_draft(self.admin, "SKILL", "gray-only/skill")

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

    def test_invalid_draft_remains_comparable_without_publish_validation(self):
        invalid = self.draft_document()
        invalid["metadata"]["description"] = "does not match frontmatter"
        compared = self.service.comparison_document(
            self.admin, "SKILL", "activity-planning/plan", invalid)
        self.assertEqual(invalid, compared)

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

    def test_publication_validates_the_same_draft_snapshot(self):
        first = self.drafts.save(
            "a2flow-mvp-activity-planning",
            __import__("a2flow_management").ManagedDraft.create(
                "SKILL", "activity-planning/plan", 1,
                self.draft_document(), 101), 0)
        second = __import__("a2flow_management").ManagedDraft.create(
            "SKILL", "activity-planning/plan", 2,
            {**self.draft_document(), "skillMd": SKILL_MD + "\\nchanged"},
            101)

        class MovingDrafts:
            environment = "PRT"
            def __init__(inner):
                inner.calls = 0
            def get(inner, namespace, kind, key):
                inner.calls += 1
                return first if inner.calls == 1 else second
            def save(inner, namespace, draft, expected_revision):
                raise AssertionError("publication must not save")

        moving = MovingDrafts()
        service = ManagementService([
            create_skill_feature(self.reader, moving,
                                 "a2flow-mvp-activity-planning")])
        plan = service.prepare_publication(
            self.admin, "SKILL", "activity-planning/plan", 1,
            PublicationTarget("PRT", "v2", "CURRENT"))
        self.assertEqual(1, plan.draft_revision)
        self.assertEqual(1, moving.calls)

    def test_wrong_environment_rejected_before_draft_io(self):
        class CountingDrafts:
            environment = "PRT"
            def __init__(inner):
                inner.calls = 0
            def get(inner, namespace, kind, key):
                inner.calls += 1
                raise AssertionError("must reject before get")
            def save(inner, namespace, draft, expected_revision):
                inner.calls += 1
                raise AssertionError("must reject before save")

        drafts = CountingDrafts()
        service = ManagementService([
            create_skill_feature(self.reader, drafts,
                                 "a2flow-mvp-activity-planning")])
        online = TrustedManagementContext(
            101, "ONLINE", frozenset({"ADMIN"}))
        with self.assertRaisesRegex(ManagementError, "DRAFT_ENVIRONMENT_MISMATCH"):
            service.get_draft(
                online, "SKILL", "activity-planning/plan")
        self.assertEqual(0, drafts.calls)


if __name__ == "__main__":
    unittest.main()
