"""Offline HTTP contract tests; no listener, database or publication write."""
import asyncio
import time
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

    def create_draft(self, context, key):
        self.draft = ManagedDraft.create(
            "SKILL", key, 1, {"name": ""}, context.user_id)
        return self.draft

    def save_draft(self, context, key, expected_revision, document):
        self.draft = ManagedDraft.create(
            "SKILL", key, expected_revision + 1, document, context.user_id)
        return self.draft

    def validate_draft(self, context, key):
        return ValidationReport.success(self.draft.document)

    def comparison_document(self, context, key, document):
        return document

    def retained_comparison_document(self, context, key, document):
        return document["definition"]

    def prepare_publication(self, context, key, expected_revision, target):
        return PublicationPlan.create(
            "SKILL", key, expected_revision, target,
            {"kind": "SKILL", "key": key, "versionId": target.version_id})


async def request(app, method, path, **kwargs):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
            transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


class Publications:
    def __init__(self):
        self.calls = []

    def history(self, context, kind, key):
        self.calls.append(("history", context.user_id, kind, key))
        return {"kind": kind, "key": key, "versions": [],
                "servingDigest": "sha256:" + "0" * 64}

    def version(self, context, kind, key, version_id):
        self.calls.append(("version", context.user_id, kind, key, version_id))
        return {"kind": kind, "key": key, "versionId": version_id,
                "contentDigest": "sha256:" + "1" * 64,
                "document": {"kind": kind, "key": key, "versionId": version_id,
                             "assetId": "skill-demo", "contentDigest": "sha256:" + "1" * 64,
                             "definition": {"name": "retained"}, "dependencies": []}}

    def publish(self, context, kind, key, candidate, target, expected):
        self.calls.append(("publish", context.user_id, kind, key))
        return {"status": "PUBLISHED", "published": True,
                "businessCompensated": False}

    def rollback(self, context, kind, key, target, expected):
        self.calls.append(("rollback", context.user_id, kind, key))
        return {"status": "ROLLED_BACK", "published": True,
                "businessCompensated": False}


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.identity = {"value": None}
        self.feature = Feature()
        self.publications = Publications()
        self.app = create_app(
            ManagementService([self.feature]),
            identity_resolver=lambda scope: self.identity["value"],
            publications=self.publications)

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

    def test_history_read_and_explicit_admin_publish_rollback(self):
        digest_value = "sha256:" + "0" * 64
        self.identity["value"] = TrustedManagementContext(
            "user-1", "PRT", frozenset({"USER"}))
        history = self.call(
            "GET", "/management/assets/SKILL/demo%2Fskill/versions")
        self.assertEqual(200, history.status_code)
        body = {"expectedServingDigest": digest_value,
                "candidate": {"kind": "SKILL"},
                "target": {"environment": "PRT", "versionId": "v2",
                           "channel": "CURRENT", "grayUserIds": []}}
        denied = self.call(
            "POST", "/management/assets/SKILL/demo%2Fskill/publications",
            json=body)
        self.assertEqual(403, denied.status_code)
        self.identity["value"] = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))
        published = self.call(
            "POST", "/management/assets/SKILL/demo%2Fskill/publications",
            json=body)
        self.assertEqual("PUBLISHED", published.json()["status"])
        rolled_back = self.call(
            "POST", "/management/assets/SKILL/demo%2Fskill/rollbacks",
            json={"expectedServingDigest": digest_value,
                  "target": body["target"]})
        self.assertEqual("ROLLED_BACK", rolled_back.json()["status"])
        self.assertFalse(rolled_back.json()["businessCompensated"])

    def test_admin_creates_encoded_draft_and_user_is_denied(self):
        self.identity["value"] = TrustedManagementContext(
            "user-1", "PRT", frozenset({"USER"}))
        denied = self.call(
            "POST", "/management/assets/SKILL/new%2Fskill/draft")
        self.assertEqual(403, denied.status_code)
        self.identity["value"] = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))
        created = self.call(
            "POST", "/management/assets/SKILL/new%2Fskill/draft")
        self.assertEqual(200, created.status_code)
        self.assertEqual("new/skill", created.json()["key"])
        self.assertEqual(1, created.json()["revision"])

    def test_first_publication_flow_uses_exact_empty_cas_and_candidate(self):
        empty_digest = "sha256:74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b"

        class StatefulPublications(Publications):
            def __init__(inner):
                super().__init__()
                inner.version_id = None

            def history(inner, context, kind, key):
                if inner.version_id is None:
                    return {"kind": kind, "key": key, "versions": [],
                            "serving": None, "servingDigest": empty_digest}
                return {"kind": kind, "key": key, "versions": [{
                    "versionId": inner.version_id, "assetId": "skill-created",
                    "contentDigest": "sha256:" + "1" * 64,
                }], "serving": {"current": inner.version_id, "stable": None,
                                  "gray": None, "grayUserIds": []},
                        "servingDigest": "sha256:" + "2" * 64}

            def publish(inner, context, kind, key, candidate, target, expected):
                inner.calls.append(("publish", kind, key, candidate, target, expected))
                inner.version_id = target.version_id
                return {"status": "PUBLISHED", "published": True,
                        "businessCompensated": False}

        self.identity["value"] = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))
        publications = StatefulPublications()
        app = create_app(
            ManagementService([self.feature]),
            identity_resolver=lambda scope: self.identity["value"],
            publications=publications)
        created = asyncio.run(request(
            app, "POST", "/management/assets/SKILL/new%2Ffirst/draft"))
        self.assertEqual(1, created.json()["revision"])
        saved = asyncio.run(request(
            app, "PUT", "/management/assets/SKILL/new%2Ffirst/draft",
            json={"expectedRevision": 1, "document": {"name": "configured"}}))
        self.assertEqual(2, saved.json()["revision"])
        validated = asyncio.run(request(
            app, "POST", "/management/assets/SKILL/new%2Ffirst/validate"))
        self.assertTrue(validated.json()["valid"])
        prepared = asyncio.run(request(
            app, "POST", "/management/assets/SKILL/new%2Ffirst/publication-plans",
            json={"expectedRevision": 2, "target": {
                "environment": "PRT", "versionId": "first-v1",
                "channel": "CURRENT", "grayUserIds": []}}))
        self.assertEqual(2, prepared.json()["draftRevision"])
        published = asyncio.run(request(
            app, "POST", "/management/assets/SKILL/new%2Ffirst/publications",
            json={"expectedServingDigest": empty_digest,
                  "candidate": prepared.json()["candidate"],
                  "target": prepared.json()["target"]}))
        self.assertEqual("PUBLISHED", published.json()["status"])
        publish_call = publications.calls[-1]
        self.assertEqual(empty_digest, publish_call[-1])
        self.assertEqual(prepared.json()["candidate"], publish_call[3])
        history = asyncio.run(request(
            app, "GET", "/management/assets/SKILL/new%2Ffirst/versions"))
        self.assertEqual(["first-v1"], [
            item["versionId"] for item in history.json()["versions"]])

    def test_retained_version_requires_exact_version_without_latest_fallback(self):
        self.identity["value"] = TrustedManagementContext(
            "user-1", "PRT", frozenset({"USER"}))
        response = self.call(
            "GET", "/management/assets/SKILL/demo%2Fskill/versions/v1")
        self.assertEqual(200, response.status_code)
        self.assertEqual("v1", response.json()["versionId"])
        self.assertEqual(
            ("version", "user-1", "SKILL", "demo/skill", "v1"),
            self.publications.calls[-1])

    def test_comparison_documents_use_the_same_authored_representation(self):
        self.identity["value"] = TrustedManagementContext(
            "user-1", "PRT", frozenset({"USER"}))
        denied = self.call(
            "POST", "/management/assets/SKILL/demo%2Fskill/comparison-documents",
            json={"document": {"name": "draft"}})
        self.assertEqual(403, denied.status_code)
        self.identity["value"] = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))
        draft = self.call(
            "POST", "/management/assets/SKILL/demo%2Fskill/comparison-documents",
            json={"document": {"name": "draft"}})
        self.assertEqual({"name": "draft"}, draft.json())
        retained = self.call(
            "GET", "/management/assets/SKILL/demo%2Fskill/versions/v1")
        self.assertEqual({"name": "retained"}, retained.json()["document"])

    def test_draft_only_admin_history_uses_empty_cas_without_fabricated_version(self):
        class MissingPublications(Publications):
            def history(inner, context, kind, key):
                raise __import__("a2flow_management").ManagementError(
                    "ASSET_NOT_FOUND", 404)

        self.identity["value"] = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))
        app = create_app(
            ManagementService([self.feature]),
            identity_resolver=lambda scope: self.identity["value"],
            publications=MissingPublications())
        response = asyncio.run(request(
            app, "GET", "/management/assets/SKILL/demo%2Fskill/versions"))
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.json()["versions"])
        self.assertEqual("sha256:74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b", response.json()["servingDigest"])

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

    def test_slow_sync_service_does_not_block_event_loop(self):
        self.identity["value"] = TrustedManagementContext(
            "user-1", "PRT", frozenset({"USER"}))
        original = self.feature.list_published

        def slow(context):
            time.sleep(0.15)
            return original(context)

        self.feature.list_published = slow

        async def scenario():
            started = time.monotonic()
            pending = asyncio.create_task(request(
                self.app, "GET", "/management/assets/SKILL"))
            await asyncio.sleep(0.02)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 0.08)
            self.assertFalse(pending.done())
            response = await pending
            self.assertEqual(200, response.status_code)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
