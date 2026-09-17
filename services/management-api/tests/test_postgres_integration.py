"""Opt-in management acceptance using provisioner-owned per-case databases."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest

import httpx
from psycopg import connect
from psycopg.conninfo import make_conninfo

from a2flow_asset_store import AssetReader, PostgresAssetRepository
from a2flow_asset_store.records import canonical, digest
from a2flow_management import PostgresDraftRepository, TrustedManagementContext
from a2flow_management.assembly import create_management_app
from activity_planning_demo import bundle_validator
from activity_planning_demo.bundle import make_bundle
from skillweave_contracts import TrustedContext


PLAN_FILE = os.environ.get("A2FLOW_MANAGEMENT_PG_FIXTURE_PLAN")
PASSWORD_FILE = os.environ.get("A2FLOW_MANAGEMENT_PG_PASSWORD_FILE")
REQUIRED = os.environ.get("A2FLOW_MANAGEMENT_PG_REQUIRED") == "1"
CONFIGURED = all((PLAN_FILE, PASSWORD_FILE))
if REQUIRED and not CONFIGURED:
    raise RuntimeError(
        "REAL_POSTGRES_REQUIRED: run through deploy.management.acceptance"
    )


FIXTURES = {}
SOCKET = None
if CONFIGURED:
    plan_path = Path(PLAN_FILE)
    if not plan_path.is_file() or plan_path.stat().st_mode & 0o077:
        raise RuntimeError("POSTGRES_FIXTURE_PLAN_MUST_BE_OWNER_ONLY")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    SOCKET = plan.get("socket")
    FIXTURES = plan.get("cases", {})
    if set(FIXTURES) != {
            "test_four_kind_http_drafts_prepare_and_user_denial",
            "test_four_kind_immutable_publication_serving_cas_and_rollback",
            "test_online_stable_gray_finish_rollback_and_isolation",
            "test_dependency_invalid_publication_is_atomic_for_each_environment.PRT",
            "test_dependency_invalid_publication_is_atomic_for_each_environment.ONLINE",
    }:
        raise RuntimeError("POSTGRES_FIXTURE_PLAN_INVALID")


def conninfo(database):
    password_path = Path(PASSWORD_FILE)
    metadata = password_path.stat()
    if not password_path.is_file() or metadata.st_mode & 0o077:
        raise RuntimeError("POSTGRES_PASSWORD_FILE_MUST_BE_OWNER_ONLY")
    password = password_path.read_text(encoding="ascii").strip()
    return make_conninfo(
        host=SOCKET, dbname=database, user="postgres", password=password)


async def request(app, method, path, **kwargs):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
            transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


@unittest.skipUnless(CONFIGURED, "isolated PostgreSQL fixture not provided")
class PostgresIntegrationTests(unittest.TestCase):
    keys = {
        "SKILL": "activity-planning/copy",
        "ABILITY": "activity-planning.budget",
        "APPLICATION": "activity-planning.confirm",
        "WORKFLOW": "activity-planning",
    }

    def fixture(self, case):
        fixture = FIXTURES[case]
        database = fixture["database"]
        namespace = fixture["namespace"]
        fixture_id = fixture["fixtureId"]
        with connect(conninfo(database), autocommit=True, connect_timeout=5) as connection:
            observed = connection.execute(
                "SELECT fixture_id,namespace FROM a2flow_acceptance_fixture"
            ).fetchall()
        self.assertEqual([(fixture_id, namespace)], observed)
        return database, namespace

    def repository(self, environment, database, namespace):
        repository = PostgresAssetRepository(
            conninfo(database), environment=environment, database=database,
            validator=bundle_validator())
        repository.setup()
        with repository._connection() as connection:
            count = connection.execute(
                "SELECT count(*) FROM a2flow_asset_versions WHERE namespace=%s",
                (namespace,)).fetchone()[0]
        self.assertEqual(0, count, "owned case fixture must start unused")
        bundle = make_bundle(environment)
        bundle["namespace"] = namespace
        repository.import_bundle(
            bundle, expected_namespace=namespace, dry_run=False)
        drafts = PostgresDraftRepository(
            conninfo(database), environment=environment, database=database)
        drafts.setup()
        return repository, drafts

    def app(self, repository, drafts, identity, namespace):
        return create_management_app(
            reader=AssetReader(repository, namespace), drafts=drafts,
            namespace=namespace, identity_resolver=lambda scope: identity).app

    def call(self, app, method, path, **kwargs):
        return asyncio.run(request(app, method, path, **kwargs))

    def path(self, kind, key, suffix=""):
        return "/management/assets/" + kind + "/" + key.replace("/", "%2F") + suffix

    def candidate(self, document, kind, key, version):
        value = deepcopy(next(
            item for item in document["assets"]
            if (item["kind"], item["key"]) == (kind, key)))
        value["versionId"] = version
        value["contentDigest"] = digest(canonical({
            field: item for field, item in value.items()
            if field != "contentDigest"
        }))
        return value

    def test_four_kind_http_drafts_prepare_and_user_denial(self):
        database, namespace = self.fixture(
            "test_four_kind_http_drafts_prepare_and_user_denial")
        repository, drafts = self.repository("PRT", database, namespace)
        admin = TrustedManagementContext(
            "accept-admin", "PRT", frozenset({"ADMIN"}))
        user = TrustedManagementContext(
            "accept-reader", "PRT", frozenset({"USER"}))
        app = self.app(repository, drafts, admin, namespace)
        before = repository.read(namespace)

        for kind, key in self.keys.items():
            with self.subTest(kind=kind):
                draft_path = self.path(kind, key, "/draft")
                initial = self.call(app, "GET", draft_path)
                self.assertEqual(200, initial.status_code, initial.text)
                saved = self.call(app, "PUT", draft_path, json={
                    "expectedRevision": 0,
                    "document": initial.json()["document"],
                })
                self.assertEqual(200, saved.status_code, saved.text)
                self.assertEqual(1, saved.json()["revision"])
                observed = drafts.get(namespace, kind, key)
                self.assertEqual(saved.json()["contentDigest"], observed.content_digest)
                stale = self.call(app, "PUT", draft_path, json={
                    "expectedRevision": 0,
                    "document": initial.json()["document"],
                })
                self.assertEqual(409, stale.status_code, stale.text)
                self.assertEqual(
                    "DRAFT_REVISION_CONFLICT", stale.json()["error"]["code"])
                validated = self.call(
                    app, "POST", self.path(kind, key, "/validate"))
                self.assertEqual(200, validated.status_code, validated.text)
                self.assertTrue(validated.json()["valid"])
                prepared = self.call(
                    app, "POST", self.path(kind, key, "/publication-plans"),
                    json={
                        "expectedRevision": 1,
                        "target": {
                            "environment": "PRT", "versionId": "accept-v2",
                            "channel": "CURRENT", "grayUserIds": [],
                        },
                    })
                self.assertEqual(200, prepared.status_code, prepared.text)
                self.assertEqual("PREPARED_NOT_PUBLISHED", prepared.json()["status"])
                self.assertFalse(prepared.json()["published"])

        after = repository.read(namespace)
        self.assertEqual(before.serving_data, after.serving_data)
        self.assertEqual(
            [asset.identity for asset in before.assets],
            [asset.identity for asset in after.assets])
        denied_app = self.app(repository, drafts, user, namespace)
        denied = self.call(
            denied_app, "PUT", self.path("SKILL", self.keys["SKILL"], "/draft"),
            json={"expectedRevision": 1, "document": {}},
        )
        self.assertEqual(403, denied.status_code)
        self.assertEqual("ADMIN_REQUIRED", denied.json()["error"]["code"])

    def test_four_kind_immutable_publication_serving_cas_and_rollback(self):
        database, namespace = self.fixture(
            "test_four_kind_immutable_publication_serving_cas_and_rollback")
        repository, drafts = self.repository("PRT", database, namespace)
        identity = TrustedManagementContext(
            "accept-admin", "PRT", frozenset({"ADMIN"}))
        app = self.app(repository, drafts, identity, namespace)
        source = make_bundle("PRT")

        for index, (kind, key) in enumerate(self.keys.items(), start=1):
            with self.subTest(kind=kind):
                history = self.call(
                    app, "GET", self.path(kind, key, "/versions"))
                self.assertEqual(200, history.status_code, history.text)
                candidate = self.candidate(
                    source, kind, key, "accept-published-" + str(index))
                target = {
                    "environment": "PRT", "versionId": candidate["versionId"],
                    "channel": "CURRENT", "grayUserIds": [],
                }
                published = self.call(
                    app, "POST", self.path(kind, key, "/publications"), json={
                        "expectedServingDigest": history.json()["servingDigest"],
                        "candidate": candidate, "target": target,
                    })
                self.assertEqual(200, published.status_code, published.text)
                stale = self.call(
                    app, "POST", self.path(kind, key, "/rollbacks"), json={
                        "expectedServingDigest": history.json()["servingDigest"],
                        "target": {**target, "versionId": "v1"},
                    })
                self.assertEqual(409, stale.status_code, stale.text)
                current = self.call(
                    app, "GET", self.path(kind, key, "/versions"))
                self.assertEqual(
                    ["v1", candidate["versionId"]],
                    [item["versionId"] for item in current.json()["versions"]])
                rolled_back = self.call(
                    app, "POST", self.path(kind, key, "/rollbacks"), json={
                        "expectedServingDigest": current.json()["servingDigest"],
                        "target": {**target, "versionId": "v1"},
                    })
                self.assertEqual(200, rolled_back.status_code, rolled_back.text)
                self.assertEqual("ROLLED_BACK", rolled_back.json()["status"])

        with repository._connection() as connection:
            rows = connection.execute(
                "SELECT kind,asset_key,count(*) FROM a2flow_asset_versions "
                "WHERE namespace=%s GROUP BY kind,asset_key", (namespace,)).fetchall()
        counts = {(kind, key): count for kind, key, count in rows}
        for identity in self.keys.items():
            self.assertEqual(2, counts[identity])

    def test_online_stable_gray_finish_rollback_and_isolation(self):
        database, namespace = self.fixture(
            "test_online_stable_gray_finish_rollback_and_isolation")
        online, drafts = self.repository("ONLINE", database, namespace)
        key = self.keys["SKILL"]
        source = make_bundle("ONLINE")
        candidate = self.candidate(source, "SKILL", key, "accept-gray-v2")
        history = online.publication_history(namespace, "SKILL", key)
        gray_target = {
            "environment": "ONLINE", "versionId": "accept-gray-v2",
            "channel": "GRAY", "grayUserIds": ["accept-gray-user"],
        }
        online.publish_candidate(
            namespace, "SKILL", key, candidate, gray_target,
            history["servingDigest"])
        reader = AssetReader(online, namespace)
        gray = reader.resolve_asset(
            "SKILL", key, TrustedContext("accept-gray-user", "ONLINE"))
        stable = reader.resolve_asset(
            "SKILL", key, TrustedContext("accept-stable-user", "ONLINE"))
        self.assertEqual(("accept-gray-v2", "ONLINE_GRAY"),
                         (gray["versionId"], gray["selection"]))
        self.assertEqual(("v1", "ONLINE_STABLE"),
                         (stable["versionId"], stable["selection"]))
        during = online.publication_history(namespace, "SKILL", key)
        finished = online.publish_candidate(
            namespace, "SKILL", key, candidate,
            {**gray_target, "channel": "STABLE", "grayUserIds": []},
            during["servingDigest"])
        self.assertEqual("accept-gray-v2", finished["serving"]["stable"])
        self.assertIsNone(finished["serving"]["gray"])
        rolled_back = online.rollback_configuration(
            namespace, "SKILL", key, "v1",
            {**gray_target, "versionId": "v1", "channel": "STABLE",
             "grayUserIds": []}, finished["servingDigest"])
        self.assertEqual("v1", rolled_back["serving"]["stable"])
        with self.assertRaises(Exception):
            reader.resolve_asset(
                "SKILL", key, TrustedContext("accept-gray-user", "PRT"))

    def test_dependency_invalid_publication_is_atomic_for_each_environment(self):
        for environment in ("PRT", "ONLINE"):
            with self.subTest(environment=environment):
                database, namespace = self.fixture(
                    "test_dependency_invalid_publication_is_atomic_for_each_environment."
                    + environment)
                repository, drafts = self.repository(
                    environment, database, namespace)
                key = "activity-planning.confirm"
                candidate = self.candidate(
                    make_bundle(environment), "ABILITY", key,
                    "accept-invalid-" + environment.lower())
                before = repository.publication_history(namespace, "ABILITY", key)
                target = {
                    "environment": environment,
                    "versionId": candidate["versionId"],
                    "channel": "CURRENT" if environment == "PRT" else "STABLE",
                    "grayUserIds": [],
                }
                with self.assertRaisesRegex(
                        Exception, "SERVING_DEPENDENCY_MISMATCH"):
                    repository.publish_candidate(
                        namespace, "ABILITY", key, candidate, target,
                        before["servingDigest"])
                after = repository.publication_history(namespace, "ABILITY", key)
                self.assertEqual(before, after)
                with repository._connection() as connection:
                    count = connection.execute(
                        "SELECT count(*) FROM a2flow_asset_versions WHERE namespace=%s "
                        "AND kind='ABILITY' AND asset_key=%s AND version_id=%s",
                        (namespace, key, candidate["versionId"])).fetchone()[0]
                self.assertEqual(0, count)


if __name__ == "__main__":
    unittest.main()
