"""Four-module HTTP assembly integration with validated demo assets."""
import asyncio
from contextlib import contextmanager
import unittest

import httpx

from a2flow_asset_store import AssetReader
from a2flow_management import (
    ManagedDraft, ManagementError, MemoryDraftRepository, PostgresDraftRepository,
    TrustedManagementContext,
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

    def retained_version(self, *args):
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


class DraftDatabaseDouble:
    def __init__(self, published=False):
        self.database = "asset_prt"
        self.environment = "PRT"
        self.published = published
        self.calls = []

    def connect(self, *args, **kwargs):
        return self

    def close(self):
        pass

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql == "SELECT current_database()":
            return DraftRows([(self.database,)])
        if sql.startswith("SELECT environment"):
            return DraftRows([(self.environment,)])
        if sql.startswith("SELECT pg_advisory"):
            return DraftRows()
        if sql.startswith("SELECT 1 FROM a2flow_asset_versions"):
            return DraftRows([(1,)] if self.published else [])
        if sql.startswith("INSERT INTO a2flow_management_drafts"):
            return DraftRows([(1,)])
        raise AssertionError("unexpected SQL " + sql)


class DraftRows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.identity = {"value": TrustedManagementContext(
            102, "PRT", frozenset({"USER"}))}
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
            "userId": "102", "environment": "PRT",
            "registeredKinds": ["ABILITY", "APPLICATION", "SKILL", "WORKFLOW"],
            "canAuthor": False,
        }, response.json())

    def test_session_rejects_identity_for_another_environment(self):
        self.identity["value"] = TrustedManagementContext(
            102, "ONLINE", frozenset({"USER"}))
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

    def test_postgres_ordinary_first_save_of_published_asset_succeeds(self):
        database = DraftDatabaseDouble(published=True)
        repository = PostgresDraftRepository(
            "not-a-real-dsn", environment="PRT", database="asset_prt",
            connection_factory=database.connect)
        draft = ManagedDraft.create(
            "SKILL", "existing/skill", 0, {"metadata": {}}, 101)
        saved = repository.save(NAMESPACE, draft, 0)
        self.assertEqual(1, saved.revision)
        statements = [sql for sql, _ in database.calls]
        self.assertFalse(any(sql.startswith("SELECT pg_advisory_xact_lock")
                             for sql in statements))
        self.assertFalse(any(sql.startswith("SELECT 1 FROM a2flow_asset_versions")
                             for sql in statements))

    def test_postgres_explicit_create_rechecks_published_asset_under_namespace_lock(self):
        database = DraftDatabaseDouble(published=True)
        repository = PostgresDraftRepository(
            "not-a-real-dsn", environment="PRT", database="asset_prt",
            connection_factory=database.connect)
        draft = ManagedDraft.create(
            "SKILL", "new/skill", 0, {"metadata": {}}, 101)
        with self.assertRaisesRegex(ManagementError, "ASSET_ALREADY_EXISTS"):
            repository.create(NAMESPACE, draft)
        statements = [sql for sql, _ in database.calls]
        lock_index = next(index for index, sql in enumerate(statements)
                          if sql.startswith("SELECT pg_advisory_xact_lock"))
        check_index = next(index for index, sql in enumerate(statements)
                           if sql.startswith("SELECT 1 FROM a2flow_asset_versions"))
        self.assertLess(lock_index, check_index)
        self.assertFalse(any(sql.startswith("INSERT INTO a2flow_management_drafts")
                             for sql in statements))

    def test_postgres_explicit_create_locks_checks_then_inserts(self):
        database = DraftDatabaseDouble()
        repository = PostgresDraftRepository(
            "not-a-real-dsn", environment="PRT", database="asset_prt",
            connection_factory=database.connect)
        draft = ManagedDraft.create(
            "SKILL", "new/skill", 0, {"metadata": {}}, 101)
        saved = repository.create(NAMESPACE, draft)
        self.assertEqual(1, saved.revision)
        ordered = [
            next(index for index, (sql, _) in enumerate(database.calls)
                 if sql.startswith(prefix))
            for prefix in (
                "SELECT pg_advisory_xact_lock",
                "SELECT 1 FROM a2flow_asset_versions",
                "INSERT INTO a2flow_management_drafts",
            )
        ]
        self.assertEqual(sorted(ordered), ordered)

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
