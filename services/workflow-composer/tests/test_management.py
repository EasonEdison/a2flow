"""Focused AF10 Workflow management tests."""
from copy import deepcopy
import unittest

from a2flow_asset_store import AssetError
from a2flow_management import (
    ManagedDraft,
    ManagementError,
    ManagementService,
    MemoryDraftRepository,
    PublicationTarget,
    TrustedManagementContext,
)
from a2flow_workflow_composer import create_workflow_feature


WORKFLOW_KEY = "activity-planning"
NAMESPACE = "a2flow-mvp-activity-planning"
DEFINITION = {
    "definitionKey": WORKFLOW_KEY,
    "entryNodeId": "plan",
    "nodes": [
        {"nodeId": "plan", "skillKey": "activity-planning/plan"},
        {"nodeId": "copy", "skillKey": "activity-planning/copy"},
    ],
}


class FakeValidator:
    def validate_definition(self, kind, key, definition):
        nodes = definition.get("nodes")
        if (kind != "WORKFLOW" or key != definition.get("definitionKey")
                or type(nodes) is not list or not 2 <= len(nodes) <= 8
                or definition.get("entryNodeId") != nodes[0].get("nodeId")
                or len({node.get("nodeId") for node in nodes}) != len(nodes)):
            raise AssetError("UNSUPPORTED_WORKFLOW")


class FakeReader:
    def __init__(self):
        self.publish_calls = 0

    def list_assets(self, kind, context):
        return ({
            "kind": "WORKFLOW", "key": WORKFLOW_KEY,
            "assetId": "workflow-activity-planning", "versionId": "v1",
            "contentDigest": "sha256:" + "1" * 64,
            "selection": "PRT_CURRENT",
        },)

    def resolve_asset(self, kind, key, context):
        if kind == "WORKFLOW" and key == WORKFLOW_KEY:
            return {
                "kind": kind, "key": key,
                "assetId": "workflow-activity-planning",
                "versionId": "v1",
                "contentDigest": "sha256:" + "1" * 64,
                "definition": deepcopy(DEFINITION),
                "dependencies": [
                    {"kind": "SKILL", "key": "activity-planning/plan"},
                    {"kind": "SKILL", "key": "activity-planning/copy"},
                ],
                "selection": "PRT_CURRENT",
                "recordedVersions": (("SKILL:skill-plan", "v1"),),
            }
        if kind == "SKILL" and key in {
                "activity-planning/plan", "activity-planning/copy"}:
            return {"kind": kind, "key": key, "assetId": "skill-" + key}
        raise AssetError("ASSET_NOT_FOUND")


class WorkflowManagementTests(unittest.TestCase):
    def setUp(self):
        self.reader = FakeReader()
        self.drafts = MemoryDraftRepository("PRT")
        self.service = ManagementService([create_workflow_feature(
            self.reader, self.drafts, NAMESPACE, FakeValidator())])
        self.admin = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))
        self.user = TrustedManagementContext(
            "user-1", "PRT", frozenset({"USER"}))

    def document(self, topology="SEQUENTIAL"):
        return {
            "definitionKey": WORKFLOW_KEY,
            "topology": topology,
            "nodes": deepcopy(DEFINITION["nodes"]),
        }

    def test_user_browses_published_but_cannot_author(self):
        listed = self.service.list_published(self.user, "WORKFLOW")
        detail = self.service.get_published(
            self.user, "WORKFLOW", WORKFLOW_KEY)

        self.assertEqual(WORKFLOW_KEY, listed[0]["key"])
        self.assertEqual(DEFINITION, detail["definition"])
        with self.assertRaisesRegex(ManagementError, "ADMIN_REQUIRED"):
            self.service.get_draft(
                self.user, "WORKFLOW", WORKFLOW_KEY)

    def test_sequential_draft_validates_and_prepares_without_publishing(self):
        saved = self.service.save_draft(
            self.admin, "WORKFLOW", WORKFLOW_KEY, 0, self.document())
        report = self.service.validate_draft(
            self.admin, "WORKFLOW", WORKFLOW_KEY)
        plan = self.service.prepare_publication(
            self.admin, "WORKFLOW", WORKFLOW_KEY, saved.revision,
            PublicationTarget("PRT", "v2", "CURRENT"))

        self.assertTrue(report.valid)
        self.assertEqual(DEFINITION, report.normalized["definition"])
        self.assertEqual(DEFINITION, plan.candidate["definition"])
        self.assertEqual("v2", plan.candidate["versionId"])
        self.assertEqual([
            {"kind": "SKILL", "key": "activity-planning/plan"},
            {"kind": "SKILL", "key": "activity-planning/copy"},
        ], plan.candidate["dependencies"])
        self.assertEqual(0, self.reader.publish_calls)

    def test_planned_topologies_save_but_cannot_prepare(self):
        for topology in ("AI_ROUTING", "BRANCH", "PARALLEL"):
            with self.subTest(topology=topology):
                drafts = MemoryDraftRepository("PRT")
                service = ManagementService([create_workflow_feature(
                    self.reader, drafts, NAMESPACE, FakeValidator())])
                saved = service.save_draft(
                    self.admin, "WORKFLOW", WORKFLOW_KEY, 0,
                    self.document(topology))
                report = service.validate_draft(
                    self.admin, "WORKFLOW", WORKFLOW_KEY)

                self.assertEqual(1, saved.revision)
                self.assertFalse(report.valid)
                self.assertEqual("UNSUPPORTED_WORKFLOW_TOPOLOGY",
                                 report.issues[0]["code"])
                with self.assertRaisesRegex(
                        ManagementError, "DRAFT_NOT_PUBLISHABLE"):
                    service.prepare_publication(
                        self.admin, "WORKFLOW", WORKFLOW_KEY, 1,
                        PublicationTarget("PRT", "v2", "CURRENT"))

    def test_missing_published_skill_blocks_validation(self):
        document = self.document()
        document["nodes"][1]["skillKey"] = "missing/skill"
        self.service.save_draft(
            self.admin, "WORKFLOW", WORKFLOW_KEY, 0, document)

        report = self.service.validate_draft(
            self.admin, "WORKFLOW", WORKFLOW_KEY)

        self.assertFalse(report.valid)
        self.assertEqual("ASSET_NOT_FOUND", report.issues[0]["code"])

    def test_revision_and_environment_fail_closed_before_io(self):
        self.service.save_draft(
            self.admin, "WORKFLOW", WORKFLOW_KEY, 0, self.document())
        with self.assertRaisesRegex(ManagementError, "DRAFT_REVISION_CONFLICT"):
            self.service.save_draft(
                self.admin, "WORKFLOW", WORKFLOW_KEY, 0, self.document())
        with self.assertRaisesRegex(
                ManagementError, "TARGET_ENVIRONMENT_MISMATCH"):
            self.service.prepare_publication(
                self.admin, "WORKFLOW", WORKFLOW_KEY, 1,
                PublicationTarget("ONLINE", "v2", "STABLE"))

        class CountingDrafts:
            environment = "PRT"
            calls = 0
            def get(inner, namespace, kind, key):
                inner.calls += 1
                raise AssertionError("must reject before draft IO")
            def save(inner, namespace, draft, expected_revision):
                inner.calls += 1
                raise AssertionError("must reject before draft IO")

        counting = CountingDrafts()
        service = ManagementService([create_workflow_feature(
            self.reader, counting, NAMESPACE, FakeValidator())])
        online = TrustedManagementContext(
            "admin-1", "ONLINE", frozenset({"ADMIN"}))
        with self.assertRaisesRegex(
                ManagementError, "DRAFT_ENVIRONMENT_MISMATCH"):
            service.get_draft(online, "WORKFLOW", WORKFLOW_KEY)
        self.assertEqual(0, counting.calls)

    def test_prepare_uses_one_immutable_draft_snapshot(self):
        first = ManagedDraft.create(
            "WORKFLOW", WORKFLOW_KEY, 1, self.document(), "admin-1")
        second = ManagedDraft.create(
            "WORKFLOW", WORKFLOW_KEY, 2,
            self.document("PARALLEL"), "admin-1")

        class MovingDrafts:
            environment = "PRT"
            def __init__(inner):
                inner.calls = 0
            def get(inner, namespace, kind, key):
                inner.calls += 1
                return first if inner.calls == 1 else second
            def save(inner, namespace, draft, expected_revision):
                raise AssertionError("prepare must not write")

        moving = MovingDrafts()
        service = ManagementService([create_workflow_feature(
            self.reader, moving, NAMESPACE, FakeValidator())])
        plan = service.prepare_publication(
            self.admin, "WORKFLOW", WORKFLOW_KEY, 1,
            PublicationTarget("PRT", "v2", "CURRENT"))

        self.assertEqual(1, moving.calls)
        self.assertEqual(1, plan.draft_revision)
        self.assertEqual("SEQUENTIAL", first.document["topology"])


if __name__ == "__main__":
    unittest.main()
