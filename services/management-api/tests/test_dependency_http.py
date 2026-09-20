import asyncio
import unittest

import httpx

from a2flow_management import ManagementFeature, ManagementService, ManagedDraft, PublicationPlan, TrustedManagementContext, ValidationReport
from a2flow_management.http import create_app


class Feature(ManagementFeature):
    kind = "SKILL"

    def __init__(self):
        self.draft = ManagedDraft.create("SKILL", "team/skill", 3, {}, 101)

    def list_published(self, context): return ()
    def get_published(self, context, key): return {}
    def get_draft(self, context, key): return self.draft
    def create_draft(self, context, key): return self.draft
    def save_draft(self, context, key, expected_revision, document): return self.draft
    def validate_draft(self, context, key): return ValidationReport.success({})
    def prepare_publication(self, context, key, expected_revision, target):
        return PublicationPlan.create("SKILL", key, expected_revision, target, {
            "kind": "SKILL", "key": key, "assetId": "skill-team", "versionId": target.version_id,
            "definition": {}, "dependencies": [],
        })


class Dependencies:
    def __init__(self):
        self.calls = []

    def inspect(self, context, kind, key, **options):
        self.calls.append((context.user_id, context.environment, context.roles, kind, key, options))
        return {"root": {"kind": kind, "key": key}, "upstream": [],
                "dependents": [], "cycle": False, "truncated": False,
                "incomplete": False}


async def request(app, path, method="GET", **kwargs):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


class DependencyHttpTests(unittest.TestCase):
    def setUp(self):
        self.identity = TrustedManagementContext(102, "PRT", frozenset({"USER"}))
        self.dependencies = Dependencies()
        self.service = ManagementService([Feature()])
        self.app = create_app(
            self.service, identity_resolver=lambda scope: self.identity,
            dependencies=self.dependencies)

    def test_dependency_endpoint_uses_trusted_identity_and_slash_key(self):
        response = asyncio.run(request(
            self.app, "/management/assets/SKILL/team%2Fskill/dependencies",
            headers={"x-user-id": "spoof", "x-role": "ADMIN", "x-environment": "ONLINE"}))
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("team/skill", response.json()["root"]["key"])
        self.assertEqual((102, "PRT", frozenset({"USER"}), "SKILL", "team/skill", {}),
                         self.dependencies.calls[-1])

    def test_dependency_endpoint_rejects_query_control_of_bounds(self):
        response = asyncio.run(request(
            self.app, "/management/assets/SKILL/team%2Fskill/dependencies?maxNodes=999"))
        self.assertEqual(400, response.status_code)
        self.assertEqual("QUERY_PARAMETERS_NOT_ALLOWED", response.json()["error"]["code"])
        self.assertEqual([], self.dependencies.calls)
    def test_publication_check_reuses_validation_prepare_and_never_publishes(self):
        self.identity = TrustedManagementContext(101, "PRT", frozenset({"ADMIN"}))
        response = asyncio.run(request(
            self.app, "/management/assets/SKILL/team%2Fskill/publication-checks",
            method="POST", json={"expectedRevision": 3, "target": {
                "environment": "PRT", "versionId": "v4", "channel": "CURRENT",
                "grayUserIds": [],
            }}))
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("PREPARED_NOT_PUBLISHED", response.json()["status"])
        self.assertFalse(response.json()["published"])
        self.assertEqual(3, response.json()["preparedRevision"])
        self.assertTrue(response.json()["validation"]["valid"])
        self.assertEqual({"root_sources": ("saved-draft",)}, self.dependencies.calls[-1][-1])

    def test_publication_check_diagnostics_do_not_override_existing_validation(self):
        self.identity = TrustedManagementContext(101, "PRT", frozenset({"ADMIN"}))
        self.dependencies.inspect = lambda *args, **kwargs: {
            "root": {"kind": "SKILL", "key": "team/skill", "source": "saved-draft"},
            "upstream": [{"error": "MISSING_DEPENDENCY"}], "dependents": [],
            "cycle": False, "truncated": False, "incomplete": True,
        }
        response = asyncio.run(request(
            self.app, "/management/assets/SKILL/team%2Fskill/publication-checks",
            method="POST", json={"expectedRevision": 3, "target": {
                "environment": "PRT", "versionId": "v4", "channel": "CURRENT",
                "grayUserIds": [],
            }}))
        self.assertEqual(200, response.status_code, response.text)
        self.assertTrue(response.json()["validation"]["valid"])
        self.assertEqual("PREPARED_NOT_PUBLISHED", response.json()["status"])
        self.assertTrue(response.json()["dependencies"]["incomplete"])


if __name__ == "__main__":
    unittest.main()
