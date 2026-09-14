"""Opt-in AF10 PostgreSQL integration; requires an isolated Unix socket."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import unittest

import httpx

from a2flow_asset_store import AssetError, AssetReader, PostgresAssetRepository
from a2flow_management import (
    ManagedDraft, ManagementError,
    PostgresDraftRepository, PublicationTarget, TrustedManagementContext,
)
from a2flow_management.assembly import create_management_app
from activity_planning_demo import bundle_validator
from activity_planning_demo.bundle import NAMESPACE, make_bundle


SOCKET = os.environ.get("A2FLOW_MANAGEMENT_PG_SOCKET")
PRT_DATABASE = os.environ.get(
    "A2FLOW_MANAGEMENT_PRT_DATABASE", "a2flow_mgmt_prt")
ONLINE_DATABASE = os.environ.get(
    "A2FLOW_MANAGEMENT_ONLINE_DATABASE", "a2flow_mgmt_online")


def conninfo(database):
    return "host=" + SOCKET + " dbname=" + database + " user=postgres"


async def request(app, method, path, **kwargs):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
            transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


@unittest.skipUnless(SOCKET, "isolated PostgreSQL socket not provided")
class PostgresIntegrationTests(unittest.TestCase):
    def asset_repository(self, environment, database):
        validator = bundle_validator()
        repository = PostgresAssetRepository(
            conninfo(database), environment=environment, database=database,
            validator=validator)
        repository.setup()
        result = repository.import_bundle(
            make_bundle(environment), expected_namespace=NAMESPACE,
            dry_run=False)
        self.assertIn(result["status"], {"INSERTED", "NO_CHANGE"})
        return repository

    def test_real_postgres_drafts_and_four_module_host(self):
        prt = self.asset_repository("PRT", PRT_DATABASE)
        online = self.asset_repository("ONLINE", ONLINE_DATABASE)
        online_reader = AssetReader(online, NAMESPACE)
        self.assertTrue(all(
            item["selection"] == "ONLINE_STABLE"
            for item in online_reader.list_assets(
                "SKILL", __import__("skillweave_contracts").TrustedContext(
                    "online-user", "ONLINE"))))

        drafts = PostgresDraftRepository(
            conninfo(PRT_DATABASE), environment="PRT", database=PRT_DATABASE)
        drafts.setup()
        reader = AssetReader(prt, NAMESPACE)
        identity = TrustedManagementContext(
            "admin-1", "PRT", frozenset({"ADMIN"}))
        assembly = create_management_app(
            reader=reader, drafts=drafts, namespace=NAMESPACE,
            identity_resolver=lambda scope: identity)

        session = asyncio.run(request(
            assembly.app, "GET", "/management/session"))
        self.assertEqual(200, session.status_code)
        for kind, key in {
                "SKILL": "activity-planning/plan",
                "ABILITY": "activity-planning.budget",
                "APPLICATION": "activity-planning.confirm",
                "WORKFLOW": "activity-planning",
        }.items():
            listed = asyncio.run(request(
                assembly.app, "GET", "/management/assets/" + kind))
            self.assertEqual(200, listed.status_code, listed.text)
            detail = asyncio.run(request(
                assembly.app, "GET", "/management/assets/" + kind + "/" +
                key.replace("/", "%2F")))
            self.assertEqual(200, detail.status_code, detail.text)

        before = prt.read(NAMESPACE)
        initial = assembly.service.get_draft(
            identity, "SKILL", "activity-planning/plan")
        saved = assembly.service.save_draft(
            identity, "SKILL", "activity-planning/plan", 0,
            initial.document)
        observed = drafts.get(
            NAMESPACE, "SKILL", "activity-planning/plan")
        self.assertEqual(saved.content_digest, observed.content_digest)
        self.assertEqual(saved.document, observed.document)

        candidates = [
            ManagedDraft.create(
                "SKILL", "activity-planning/plan", 1,
                saved.document, "admin-" + str(index))
            for index in (2, 3)
        ]

        def update(candidate):
            try:
                return drafts.save(NAMESPACE, candidate, 1).revision
            except ManagementError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(update, candidates))
        self.assertEqual(1, outcomes.count(2))
        self.assertEqual(1, outcomes.count("DRAFT_REVISION_CONFLICT"))

        plan = assembly.service.prepare_publication(
            identity, "SKILL", "activity-planning/plan", 2,
            PublicationTarget("PRT", "v2", "CURRENT"))
        self.assertEqual("v2", plan.candidate["versionId"])
        after = prt.read(NAMESPACE)
        self.assertEqual(before.serving_data, after.serving_data)
        self.assertEqual(
            [(asset.identity, asset.content_digest) for asset in before.assets],
            [(asset.identity, asset.content_digest) for asset in after.assets])

        wrong_database = PostgresAssetRepository(
            conninfo(PRT_DATABASE), environment="PRT",
            database=ONLINE_DATABASE, validator=bundle_validator())
        with self.assertRaisesRegex(AssetError, "DATABASE_MISMATCH"):
            wrong_database.read(NAMESPACE)
        wrong_environment = PostgresDraftRepository(
            conninfo(PRT_DATABASE), environment="ONLINE",
            database=PRT_DATABASE)
        with self.assertRaisesRegex(
                ManagementError, "DATABASE_ENVIRONMENT_MISMATCH"):
            wrong_environment.get(
                NAMESPACE, "SKILL", "activity-planning/plan")


if __name__ == "__main__":
    unittest.main()
