"""Cross-module Workflow management checks against the real AssetReader."""
import unittest

from a2flow_asset_store import AssetReader
from a2flow_management import (
    ManagementService,
    MemoryDraftRepository,
    PublicationTarget,
    TrustedManagementContext,
)
from a2flow_workflow_composer import create_workflow_feature
from activity_planning_demo import WORKFLOW_KEY, bundle_validator
from activity_planning_demo.bundle import NAMESPACE, make_bundle
from skillweave_contracts import TrustedContext


class MemoryAssetRepository:
    def __init__(self, bundle, validator):
        self.environment = bundle.environment
        self.bundle = bundle
        self.validator = validator

    def read(self, namespace):
        if namespace != self.bundle.namespace:
            raise AssertionError("unexpected namespace")
        return self.bundle


class AssetReaderWorkflowManagementTests(unittest.TestCase):
    def setUp(self):
        validator = bundle_validator()
        bundle = validator.validate(
            make_bundle("PRT"),
            expected_namespace=NAMESPACE,
            expected_environment="PRT",
        )
        self.assets = MemoryAssetRepository(bundle, validator)
        self.reader = AssetReader(self.assets, NAMESPACE)
        self.service = ManagementService([create_workflow_feature(
            self.reader,
            MemoryDraftRepository("PRT"),
            NAMESPACE,
            validator,
        )])
        self.user = TrustedManagementContext(
            "user-1", "PRT", frozenset({"USER"}))
        self.admin = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))

    def test_real_reader_lists_opens_and_validates_seeded_workflow(self):
        listed = self.service.list_published(self.user, "WORKFLOW")
        detail = self.service.get_published(
            self.user, "WORKFLOW", WORKFLOW_KEY)
        draft = self.service.get_draft(
            self.admin, "WORKFLOW", WORKFLOW_KEY)
        report = self.service.validate_draft(
            self.admin, "WORKFLOW", WORKFLOW_KEY)

        self.assertIn(WORKFLOW_KEY, {item["key"] for item in listed})
        self.assertEqual("PRT_CURRENT", detail["resolution"]["selection"])
        self.assertEqual("SEQUENTIAL", draft.document["topology"])
        self.assertTrue(report.valid)
        self.assertEqual(detail["definition"], report.normalized["definition"])

    def test_real_contract_accepts_prepared_runtime_definition(self):
        initial = self.service.get_draft(
            self.admin, "WORKFLOW", WORKFLOW_KEY)
        saved = self.service.save_draft(
            self.admin, "WORKFLOW", WORKFLOW_KEY, initial.revision,
            initial.document)
        plan = self.service.prepare_publication(
            self.admin, "WORKFLOW", WORKFLOW_KEY, saved.revision,
            PublicationTarget("PRT", "v2", "CURRENT"))

        definition = plan.candidate["definition"]
        self.assets.validator.validate_definition(
            "WORKFLOW", WORKFLOW_KEY, definition)
        self.assertEqual({"definitionKey", "entryNodeId", "nodes"},
                         set(definition))
        self.assertEqual([
            {"kind": "SKILL", "key": "activity-planning/plan"},
            {"kind": "SKILL", "key": "activity-planning/copy"},
        ], plan.candidate["dependencies"])
        published = self.reader.resolve_asset(
            "WORKFLOW", WORKFLOW_KEY,
            TrustedContext(self.user.user_id, self.user.environment))
        self.assertEqual("v1", published["versionId"])


if __name__ == "__main__":
    unittest.main()
