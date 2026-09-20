"""Focused declarative COMPONENT catalog management tests."""

from types import SimpleNamespace
import unittest

from a2flow_management import (
    ManagementError,
    ManagementService,
    MemoryDraftRepository,
    PublicationTarget,
    TrustedManagementContext,
)
from a2ui_composer import component_validator, create_component_feature


KEY = "activity-planning.basic"
PROFILE = "a2flow.mvp08.v1"


def definition(components=None):
    return {
        "catalogKey": KEY,
        "protocolProfileRef": PROFILE,
        "components": components or ["Column", "Text", "ChoicePicker", "Button"],
    }


class Validator:
    def validate_definition(self, kind, key, value):
        if kind != "COMPONENT" or component_validator(value) is not True:
            raise ManagementError("INVALID_COMPONENT")


class Reader:
    namespace = "activity-planning"

    def __init__(self):
        self.repository = SimpleNamespace(
            environment="PRT", validator=Validator())
        self.published = definition()

    def list_assets(self, kind, context):
        return ({"kind": kind, "key": KEY, "assetId": "component-basic",
                 "versionId": "v1", "contentDigest": "sha256:" + "1" * 64,
                 "selection": "PRT_CURRENT"},)

    def resolve_asset(self, kind, key, context):
        if (kind, key) != ("COMPONENT", KEY):
            raise ManagementError("ASSET_NOT_FOUND", 404)
        return {
            "kind": kind, "key": key, "assetId": "component-basic",
            "versionId": "v1", "contentDigest": "sha256:" + "1" * 64,
            "definition": self.published, "dependencies": [],
            "selection": "PRT_CURRENT", "recordedVersions": (
                ("COMPONENT:component-basic", "v1"),),
        }

    def asset_exists(self, kind, key, context):
        return (kind, key) == ("COMPONENT", KEY)


class ComponentCatalogManagementTests(unittest.TestCase):
    def setUp(self):
        self.reader = Reader()
        self.drafts = MemoryDraftRepository("PRT")
        self.service = ManagementService([create_component_feature(
            self.reader, self.drafts, "activity-planning")])
        self.admin = TrustedManagementContext(
            101, "PRT", frozenset({"ADMIN"}))
        self.user = TrustedManagementContext(
            102, "PRT", frozenset({"USER"}))

    def test_user_reads_common_detail_envelope_but_cannot_author(self):
        self.assertEqual(KEY, self.service.list_published(
            self.user, "COMPONENT")[0]["key"])
        detail = self.service.get_published(self.user, "COMPONENT", KEY)
        self.assertEqual(definition(), detail["definition"])
        self.assertEqual(
            {"Button", "ChoicePicker", "Column", "Text"},
            {item["name"] for item in detail["componentDeclarations"]})
        with self.assertRaisesRegex(ManagementError, "ADMIN_REQUIRED"):
            self.service.get_draft(self.user, "COMPONENT", KEY)

    def test_admin_saves_subset_validates_and_prepares_publication(self):
        subset = definition(["Column", "Text"])
        saved = self.service.save_draft(
            self.admin, "COMPONENT", KEY, 0, subset)
        report = self.service.validate_draft(
            self.admin, "COMPONENT", KEY)
        self.assertTrue(report.valid)
        plan = self.service.prepare_publication(
            self.admin, "COMPONENT", KEY, saved.revision,
            PublicationTarget("PRT", "v2", "CURRENT"))
        self.assertEqual(subset, plan.candidate["definition"])
        self.assertEqual([], plan.candidate["dependencies"])

    def test_unknown_renderer_component_is_rejected_before_save(self):
        with self.assertRaisesRegex(
                ManagementError, "COMPONENT_NOT_IMPLEMENTED"):
            self.service.save_draft(
                self.admin, "COMPONENT", KEY, 0,
                definition(["Column", "RemoteScriptWidget"]))
        self.assertIsNone(self.drafts.get(
            "activity-planning", "COMPONENT", KEY))

    def test_wrong_environment_rejects_before_draft_io(self):
        online = TrustedManagementContext(
            101, "ONLINE", frozenset({"ADMIN"}))
        with self.assertRaisesRegex(
                ManagementError, "DRAFT_ENVIRONMENT_MISMATCH"):
            self.service.get_draft(online, "COMPONENT", KEY)


if __name__ == "__main__":
    unittest.main()
