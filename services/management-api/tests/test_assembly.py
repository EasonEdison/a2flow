"""Four-module HTTP assembly integration with validated demo assets."""
import asyncio
import unittest

import httpx

from a2flow_asset_store import AssetReader
from a2flow_management import (
    MemoryDraftRepository, TrustedManagementContext,
)
from a2flow_management.assembly import create_management_app
from activity_planning_demo import bundle_validator
from activity_planning_demo.bundle import NAMESPACE, make_bundle


class BundleRepository:
    def __init__(self):
        self.environment = "PRT"
        self.validator = bundle_validator()
        self.bundle = self.validator.validate(
            make_bundle("PRT"), expected_namespace=NAMESPACE,
            expected_environment="PRT")

    def read(self, namespace):
        if namespace != NAMESPACE:
            raise AssertionError("unexpected namespace")
        return self.bundle

    def publication_history(self, *args):
        raise AssertionError("not used in assembly browse tests")

    def publish_candidate(self, *args):
        raise AssertionError("not used in assembly browse tests")

    def rollback_configuration(self, *args):
        raise AssertionError("not used in assembly browse tests")


async def request(app, method, path, **kwargs):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
            transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.identity = {"value": TrustedManagementContext(
            "user-1", "PRT", frozenset({"USER"}))}
        self.repository = BundleRepository()
        self.reader = AssetReader(self.repository, NAMESPACE)
        self.drafts = MemoryDraftRepository("PRT")
        self.assembly = create_management_app(
            reader=self.reader, drafts=self.drafts, namespace=NAMESPACE,
            identity_resolver=lambda scope: self.identity["value"])

    def call(self, method, path, **kwargs):
        return asyncio.run(request(self.assembly.app, method, path, **kwargs))

    def test_session_is_server_authoritative_and_component_not_registered(self):
        response = self.call(
            "GET", "/management/session",
            headers={"x-role": "ADMIN", "x-environment": "ONLINE"})
        self.assertEqual(200, response.status_code)
        self.assertEqual({
            "userId": "user-1", "environment": "PRT",
            "registeredKinds": ["ABILITY", "APPLICATION", "SKILL", "WORKFLOW"],
            "canAuthor": False,
        }, response.json())

    def test_session_rejects_identity_for_another_environment(self):
        self.identity["value"] = TrustedManagementContext(
            "user-1", "ONLINE", frozenset({"USER"}))
        response = self.call("GET", "/management/session")
        self.assertEqual(403, response.status_code)
        self.assertEqual(
            "TRUSTED_ENVIRONMENT_MISMATCH",
            response.json()["error"]["code"])

    def test_real_reader_lists_and_resolves_all_four_modules(self):
        keys = {
            "SKILL": "activity-planning/plan",
            "ABILITY": "activity-planning.budget",
            "APPLICATION": "activity-planning.confirm",
            "WORKFLOW": "activity-planning",
        }
        for kind, key in keys.items():
            with self.subTest(kind=kind):
                listed = self.call("GET", "/management/assets/" + kind)
                self.assertEqual(200, listed.status_code, listed.text)
                self.assertTrue(listed.json())
                detail = self.call(
                    "GET", "/management/assets/" + kind + "/" +
                    key.replace("/", "%2F"))
                self.assertEqual(200, detail.status_code, detail.text)

    def test_user_write_is_rejected_before_draft_io(self):
        response = self.call(
            "PUT", "/management/assets/SKILL/activity-planning%2Fplan/draft",
            json={"expectedRevision": 0, "document": {}})
        self.assertEqual(403, response.status_code)
        self.assertEqual("ADMIN_REQUIRED", response.json()["error"]["code"])
        self.assertIsNone(self.drafts.get(
            NAMESPACE, "SKILL", "activity-planning/plan"))

    def test_assembly_rejects_environment_and_namespace_mismatch(self):
        with self.assertRaisesRegex(Exception, "DRAFT_ENVIRONMENT_MISMATCH"):
            create_management_app(
                reader=self.reader, drafts=MemoryDraftRepository("ONLINE"),
                namespace=NAMESPACE, identity_resolver=lambda scope: None)
        with self.assertRaisesRegex(Exception, "READER_NAMESPACE_MISMATCH"):
            create_management_app(
                reader=self.reader, drafts=self.drafts,
                namespace="another-namespace",
                identity_resolver=lambda scope: None)


if __name__ == "__main__":
    unittest.main()
