"""Offline HTTP contract tests; no listener, database or publication write."""
import asyncio
import unittest

import httpx

from a2flow_management import (
    ManagedDraft, ManagementFeature, ManagementService, PublicationPlan,
    TrustedManagementContext, ValidationReport,
)
from a2flow_management.http import BODY_LIMIT, create_app


class Feature(ManagementFeature):
    kind = "SKILL"

    def __init__(self):
        self.document = {"name": "demo"}
        self.draft = ManagedDraft.create(
            "SKILL", "demo/skill", 1, self.document, "admin-1")

    def list_published(self, context):
        return ({"key": "demo/skill"},)

    def get_published(self, context, key):
        return {"key": key, "versionId": "v1"}

    def get_draft(self, context, key):
        return self.draft

    def save_draft(self, context, key, expected_revision, document):
        self.draft = ManagedDraft.create(
            "SKILL", key, expected_revision + 1, document, context.user_id)
        return self.draft

    def validate_draft(self, context, key):
        return ValidationReport.success(self.draft.document)

    def prepare_publication(self, context, key, expected_revision, target):
        return PublicationPlan.create(
            "SKILL", key, expected_revision, target,
            {"kind": "SKILL", "key": key, "versionId": target.version_id})


async def request(app, method, path, **kwargs):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
            transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.identity = {"value": None}
        self.feature = Feature()
        self.app = create_app(
            ManagementService([self.feature]),
            identity_resolver=lambda scope: self.identity["value"])

    def call(self, method, path, **kwargs):
        return asyncio.run(request(self.app, method, path, **kwargs))

    def test_missing_identity_fails_closed(self):
        response = self.call("GET", "/management/assets/SKILL")
        self.assertEqual(401, response.status_code)
        self.assertEqual("TRUSTED_CONTEXT_REQUIRED", response.json()["error"]["code"])

    def test_user_browses_but_cannot_write_even_with_spoofed_headers(self):
        self.identity["value"] = TrustedManagementContext(
            "user-1", "PRT", frozenset({"USER"}))
        response = self.call(
            "GET", "/management/assets/SKILL/demo%2Fskill",
            headers={"x-role": "ADMIN", "x-user-id": "admin-1"})
        self.assertEqual(200, response.status_code)
        self.assertEqual("demo/skill", response.json()["key"])
        response = self.call(
            "PUT", "/management/assets/SKILL/demo%2Fskill/draft",
            headers={"x-role": "ADMIN"},
            json={"expectedRevision": 1, "document": {"name": "changed"}})
        self.assertEqual(403, response.status_code)
        self.assertEqual("ADMIN_REQUIRED", response.json()["error"]["code"])

    def test_admin_draft_validate_and_prepare_is_not_publish(self):
        self.identity["value"] = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))
        saved = self.call(
            "PUT", "/management/assets/SKILL/demo%2Fskill/draft",
            json={"expectedRevision": 1, "document": {"name": "changed"}})
        self.assertEqual(200, saved.status_code)
        validated = self.call(
            "POST", "/management/assets/SKILL/demo%2Fskill/validate")
        self.assertTrue(validated.json()["valid"])
        prepared = self.call(
            "POST", "/management/assets/SKILL/demo%2Fskill/publication-plans",
            json={"expectedRevision": 2, "target": {
                "environment": "PRT", "versionId": "v2",
                "channel": "CURRENT", "grayUserIds": []}})
        self.assertEqual(200, prepared.status_code)
        self.assertFalse(prepared.json()["published"])
        self.assertEqual("PREPARED_NOT_PUBLISHED", prepared.json()["status"])

    def test_cross_environment_and_validation_errors_are_4xx(self):
        self.identity["value"] = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))
        response = self.call(
            "POST", "/management/assets/SKILL/demo%2Fskill/publication-plans",
            json={"expectedRevision": 1, "target": {
                "environment": "ONLINE", "versionId": "v2",
                "channel": "STABLE", "grayUserIds": []}})
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "TARGET_ENVIRONMENT_MISMATCH", response.json()["error"]["code"])
        response = self.call("GET", "/management/assets/SKILL/%20")
        self.assertEqual(400, response.status_code)

    def test_body_and_query_are_bounded(self):
        self.identity["value"] = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))
        response = self.call(
            "PUT", "/management/assets/SKILL/demo%2Fskill/draft",
            content=b"x" * (BODY_LIMIT + 1),
            headers={"content-type": "application/json"})
        self.assertEqual(413, response.status_code)
        response = self.call("GET", "/management/assets/SKILL?role=ADMIN")
        self.assertEqual(400, response.status_code)


if __name__ == "__main__":
    unittest.main()
