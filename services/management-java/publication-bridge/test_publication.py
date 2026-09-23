"""Integration test against two NEW local databases, using actual deployed Python packages."""
import base64
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from threading import Thread
import urllib.error
import urllib.request
import zipfile

import psycopg
from a2flow_asset_store import PostgresAssetRepository
from a2flow_asset_store.reader import AssetReader
from a2flow_asset_store.records import AssetError, canonical, digest
from deploy.assets import bundle_validator
from activity_planning_demo.bundle import make_bundle
from activity_planning_demo import APPLICATION_KEY, BUDGET_KEY
from skillweave_contracts import TrustedContext

from bridge import Destination, HTTPServer, Publisher, handler


def main():
    port = int(sys.argv[1])
    destinations = {env: Destination(env, "publication_" + env.lower(),
                    f"host=127.0.0.1 port={port} dbname=publication_{env.lower()}", "publication-test")
                    for env in ("PRT", "ONLINE")}
    validator = bundle_validator()
    for destination in destinations.values():
        repository = PostgresAssetRepository(destination.dsn, environment=destination.environment,
                                             database=destination.database, validator=validator)
        repository.setup()
        with psycopg.connect(destination.dsn) as connection:
            connection.execute(Path(__file__).with_name("migrations").joinpath("V001__publication_receipts.sql").read_text())
    publisher = Publisher(destinations, validator)
    token = secrets.token_urlsafe(40)
    server = HTTPServer(("127.0.0.1", 0), handler(publisher, token))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"

    def call(path, value, authentication=token):
        request = urllib.request.Request(url + path, data=canonical(value),
                headers={"Authorization": "Bearer " + authentication, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("smoke-skill/SKILL.md", "# Smoke skill\nExplain the supplied text.\n")
        archive.writestr("smoke-skill/references/data.bin", b"\x00\x01\xff")
    package = buffer.getvalue()
    request = {"key": "smoke-skill", "environment": "PRT", "sourceId": "build-one",
               "sourceDigest": digest(b"snapshot-one"),
               "snapshot": {"componentBindings": [], "capabilityBindings": []},
               "requestId": "request-one", "packageDigest": digest(package),
               "packageBase64": base64.b64encode(package).decode(),
               "expectedServingDigest": call("/selection", {"key": "smoke-skill", "environment": "PRT"})["servingDigest"]}
    try:
        try:
            call("/publish", request, "invalid")
            raise AssertionError("unauthorized publish")
        except urllib.error.HTTPError as error:
            assert error.code == 401
        first = call("/publish", request)
        assert first["published"]
        retry = dict(request, expectedServingDigest=first["servingDigest"])
        assert call("/publish", retry) == first  # lost response recovery does not republish
        for bad, code in ((dict(request, sourceId="different"), "REQUEST_ID_CONFLICT"),
                          (dict(request, requestId="stale", sourceId="next"), "STALE_SERVING_SELECTION"),
                          (dict(request, requestId="bad-package", packageDigest=digest(b"wrong")), "PACKAGE_DIGEST_OR_SIZE_INVALID")):
            try:
                publisher.publish(bad)
                raise AssertionError("expected rejection")
            except AssetError as error:
                assert error.code == code, error.code
        for env, destination in destinations.items():
            if env == "ONLINE":
                online = dict(request, environment=env, requestId="online-request")
                online["expectedServingDigest"] = call("/selection", {"key": "smoke-skill", "environment": env})["servingDigest"]
                call("/publish", online)
            repository = PostgresAssetRepository(destination.dsn, environment=env, database=destination.database, validator=validator)
            reader = AssetReader(repository, destination.namespace)
            material = reader.load_skill("smoke-skill", TrustedContext(user_id=1, environment=env))
            assert material is not None
            resolved = reader.resolve_asset("SKILL", "smoke-skill", TrustedContext(user_id=1, environment=env))
            assert resolved["contentDigest"] == first["contentDigest"]
            assert resolved["selection"] == ("PRT_CURRENT" if env == "PRT" else "ONLINE_STABLE")
        destination = destinations["PRT"]
        with psycopg.connect(destination.dsn) as connection:
            connection.execute("ALTER TABLE a2flow_management_publication_receipts ADD CONSTRAINT reject_test_receipt CHECK(request_id <> 'receipt-insert-fail')")
        failed = dict(request, sourceId="new-build", requestId="receipt-insert-fail", expectedServingDigest=first["servingDigest"])
        try:
            publisher.publish(failed)
            raise AssertionError("receipt failure must roll back serving")
        except psycopg.errors.CheckViolation:
            pass
        assert publisher.selection({"key": "smoke-skill", "environment": "PRT"})["servingDigest"] == first["servingDigest"]
        with psycopg.connect(destination.dsn) as connection:
            assert connection.execute("SELECT count(*) FROM a2flow_asset_versions WHERE namespace=%s AND kind='SKILL' AND asset_key='smoke-skill'", (destination.namespace,)).fetchone() == (1,)
        bound_destination = Destination("PRT", destination.database, destination.dsn, "bound-test")
        bound_repository = PostgresAssetRepository(destination.dsn, environment="PRT", database=destination.database, validator=validator)
        bundle = make_bundle("PRT")
        bundle["namespace"] = bound_destination.namespace
        bound_repository.import_bundle(bundle, expected_namespace=bound_destination.namespace, dry_run=False)
        bound_publisher = Publisher({**destinations, "PRT": bound_destination}, validator)
        bound_request = deepcopy(request)
        bound_request["requestId"] = "bound-request"
        bound_request["snapshot"] = {"componentBindings": [{"assetType": "A2UI_APPLICATION", "componentName": APPLICATION_KEY}],
                                     "capabilityBindings": [{"capabilityCode": BUDGET_KEY}]}
        bound_request["expectedServingDigest"] = bound_publisher.selection({"key": "smoke-skill", "environment": "PRT"})["servingDigest"]
        bound_publisher.publish(bound_request)
        bound = AssetReader(bound_repository, "bound-test").resolve_asset("SKILL", "smoke-skill", TrustedContext(user_id=1, environment="PRT"))
        assert {(dep["kind"], dep["key"]) for dep in bound["dependencies"]} == {("APPLICATION", APPLICATION_KEY), ("ABILITY", BUDGET_KEY)}
        assert len(bound["recordedVersions"]) > 3  # existing Application/Component/Ability closure is preserved
        missing = deepcopy(bound_request)
        missing["requestId"] = "missing-dependency"
        missing["sourceId"] = "missing-dependency-build"
        missing["snapshot"]["capabilityBindings"] = [{"capabilityCode": "not-published"}]
        missing["expectedServingDigest"] = bound_publisher.selection({"key": "smoke-skill", "environment": "PRT"})["servingDigest"]
        try:
            bound_publisher.publish(missing)
            raise AssertionError("missing target dependency must reject")
        except AssetError as error:
            assert error.code == "MISSING_DEPENDENCY"
        unsupported = deepcopy(request)
        unsupported["requestId"] = "unsupported-binding"
        unsupported["snapshot"]["componentBindings"] = [{"assetType": "CARD_COMPONENT", "componentName": "card"}]
        try:
            publisher.publish(unsupported)
            raise AssertionError("cannot erase unsupported component semantics")
        except AssetError as error:
            assert error.code == "LEGACY_COMPONENT_RUNTIME_MAPPING_UNSUPPORTED"
        wrong = Publisher({**destinations, "PRT": Destination("PRT", destinations["ONLINE"].database,
                            destinations["ONLINE"].dsn, destination.namespace),
                            "ONLINE": Destination("ONLINE", destination.database, destination.dsn, destination.namespace)}, validator)
        try:
            wrong.selection({"key": "smoke-skill", "environment": "PRT"})
            raise AssertionError("environment mismatch must reject")
        except AssetError as error:
            assert error.code == "DATABASE_ENVIRONMENT_MISMATCH"
        # The management RPC profile retains full compiler JSON, not the MVP
        # four-component shape. Both new routes hit real separate databases.
        for env in ("PRT", "ONLINE"):
            ability_payload = json.dumps({"draftId": "rpc-ability", "draft": {
                "basicInfo": {"actionCode": "rpc.demo.query"}, "futureField": {"preserved": True}}})
            ability = {"kind": "ABILITY", "key": "rpc.demo.query", "environment": env,
                       "assetKey": "rpc-ability", "sourceId": "rpc-build-1",
                       "sourceDigest": digest(b"canonical-authoring-identity"),
                       "payloadDigest": digest(ability_payload.encode()), "payloadJson": ability_payload,
                       "requestId": "rpc-ability-publish", "expectedServingDigest":
                       call("/asset/selection", {"kind": "ABILITY", "key": "rpc.demo.query", "environment": env})["servingDigest"]}
            ability_receipt = call("/asset/publish", ability)
            assert call("/asset/publish", ability) == ability_receipt
            application_payload = json.dumps({"appCode": "rpc.demo.card",
                "catalog": {"catalogId": "test-catalog", "digest": "test-digest"},
                "componentTypes": ["Column", "Text"], "loadBindings": [],
                "actionBindings": [{"capability": {"actionCode": "rpc.demo.query"},
                                    "extension": {"retain": True}}]})
            app = {**ability, "kind": "APPLICATION", "key": "rpc.demo.card", "assetKey": "rpc.demo.card",
                   "sourceId": "rpc-app-1", "sourceDigest": digest(application_payload.encode()),
                   "payloadDigest": digest(application_payload.encode()),
                   "payloadJson": application_payload, "requestId": "rpc-app-publish",
                   "expectedServingDigest": call("/asset/selection", {
                       "kind": "APPLICATION", "key": "rpc.demo.card", "environment": env})["servingDigest"]}
            call("/asset/publish", app)
            destination = destinations[env]
            rpc_repository = PostgresAssetRepository(destination.dsn, environment=env,
                database=destination.database, validator=validator)
            resolved = AssetReader(rpc_repository, destination.namespace).resolve_asset(
                "APPLICATION", "rpc.demo.card", TrustedContext(user_id=1, environment=env))
            assert resolved["definition"]["payloadJson"] == application_payload
            assert len(resolved["recordedVersions"]) == 2
        print("PASS: RPC compiler publications retained losslessly with environment-local dependency closure")
        if os.environ.get("JAVA_TEST_CLASSPATH"):
            subprocess.run([os.environ["JAVA_TEST_BIN"], "-cp", os.environ["JAVA_TEST_CLASSPATH"],
                "dev.a2flow.management.lifecycle.publish.PublicationHttpAdapterTest"], check=True,
                env={**os.environ, "A2FLOW_PUBLICATION_BRIDGE_URL": url,
                     "A2FLOW_PUBLICATION_BRIDGE_TOKEN": token})
        print("PASS: real PRT/ONLINE publication, Python reader + dependency closure, HTTP auth, idempotency, CAS, atomic rollback, environment mismatch, unsupported mapping rejection")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
