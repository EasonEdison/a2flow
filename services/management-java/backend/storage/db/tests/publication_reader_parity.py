"""Read isolated Java JDBC test rows with the actual Python Runtime asset reader.

Run after PublicationJdbcAdapterTest. Requires psycopg and PUBLICATION_TEST_CLASSPATH;
PUBLICATION_TEST_PG_PORT defaults to the isolated fixture port 55439. No DDL/writes.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import random
import struct
import subprocess
import sys

root = Path(__file__).resolve().parents[6]
for relative in ("packages/contracts/src", "packages/asset-store/src",
                 "services/skill-registry/src", "services/capability-registry/src"):
    sys.path.insert(0, str(root / relative))

from a2flow_asset_store import AssetReader, BundleValidator, PostgresAssetRepository
from a2flow_asset_store.records import canonical, digest
from skillweave_contracts import TrustedContext


def reject_legacy(_definition):
    raise AssertionError("fixture must only contain Java-profile assets and Skills")


validator = BundleValidator(None, application_validator=reject_legacy,
                            component_validator=reject_legacy)
for environment in ("PRT", "ONLINE"):
    database = "publication_" + environment.lower()
    repository = PostgresAssetRepository(
        f"host=127.0.0.1 port={os.environ.get('PUBLICATION_TEST_PG_PORT', '55439')} dbname={database}",
        environment=environment, database=database, validator=validator)
    bundle = repository.read("java-publication-test")
    reader = AssetReader(repository, "java-publication-test")
    context = TrustedContext(user_id=1, environment=environment)
    assert reader.list_skills(context)[0]["skillKey"] == "java-client-skill"
    for asset in bundle.assets:
        assert digest(canonical(asset.document)) == asset.content_digest
        if asset.kind in {"ABILITY", "APPLICATION"}:
            definition = asset.definition
            assert asset.version_id == "java-" + hashlib.sha256(canonical([
                definition["sourceId"], definition["sourceDigest"]])).hexdigest()
    if environment == "PRT":
        assert {asset.kind for asset in bundle.assets} == {"SKILL", "ABILITY", "APPLICATION"}
        assert reader.list_assets("APPLICATION", context)[0]["key"] == "application-parity"

random.seed(61006)
fixtures = [{"中文": "留存😀", "\uffff": 1, "😀": 2, "a": [None, True, 1, -0.0],
             "controls": "".join(chr(value) for value in range(32))},
            [1e-7, 1e-6, 1e-5, 1e-4, 1e15, 1e16, 1e23, 5e-324, 1.7976931348623157e308]]
for _ in range(5000):
    number = struct.unpack("!d", random.randbytes(8))[0]
    if math.isfinite(number):
        fixtures.append({"value": number})
expected = [canonical(fixture).decode() for fixture in fixtures]
java = os.environ.get("PUBLICATION_TEST_JAVA", "java")
result = subprocess.run([java, "-cp", os.environ["PUBLICATION_TEST_CLASSPATH"],
                         "dev.a2flow.management.lifecycle.publish.PublicationMaterialTest", "--canonical"],
                        input="\n".join(expected) + "\n", text=True, capture_output=True, check=True)
observed = result.stdout.splitlines()
assert len(observed) == len(expected)
for source, actual in zip(expected, observed):
    assert source == actual, (source, actual)
print(f"PASS: Python Runtime reader validates Java Skill/Ability/Application rows in both DBs; {len(expected)} canonical numeric/Unicode fixtures")
