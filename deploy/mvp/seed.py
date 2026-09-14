"""Explicit non-overwriting operator seed command for the private Compose host."""

import json
import os

from a2flow_asset_store import PostgresAssetRepository
from a2flow_asset_store.records import canonical, digest
from activity_planning_demo import bundle_validator
from activity_planning_demo.bundle import make_bundle
from activity_planning_demo.package_bundle import make_package_bundle

from .runtime_support import database_conninfo, required


def main():
    environment = required("A2FLOW_ENVIRONMENT")
    demo = os.environ.get("A2FLOW_DEMO", "activity-package")
    builders = {
        "activity-planning": make_bundle,
        "activity-package": make_package_bundle,
    }
    if demo not in builders:
        raise RuntimeError("INVALID_HOST_CONFIGURATION:A2FLOW_DEMO")
    document = builders[demo](environment)
    namespace = required("A2FLOW_ASSET_NAMESPACE")
    validator = bundle_validator()
    validated = validator.validate(
        document, expected_namespace=namespace, expected_environment=environment,
    )
    repository = PostgresAssetRepository(
        database_conninfo(), environment=environment,
        database=required("A2FLOW_DATABASE_NAME"), validator=validator,
    )
    repository.setup()
    preview = repository.import_bundle(document, expected_namespace=namespace, dry_run=True)
    applied = repository.import_bundle(document, expected_namespace=namespace, dry_run=False)
    observed = repository.read(namespace)
    actual_assets = {
        asset.identity: {**asset.document, "contentDigest": asset.content_digest}
        for asset in observed.assets
    }
    desired_assets = {
        asset.identity: {**asset.document, "contentDigest": asset.content_digest}
        for asset in validated.assets
    }
    actual_serving = {(item["kind"], item["key"]): item for item in observed.serving}
    desired_serving = {(item["kind"], item["key"]): item for item in validated.serving}
    if (any(canonical(actual_assets.get(key)) != canonical(value)
            for key, value in desired_assets.items())
            or any(canonical(actual_serving.get(key)) != canonical(value)
                   for key, value in desired_serving.items())):
        raise RuntimeError("SEED_READBACK_MISMATCH")
    result = {
        "status": applied["status"],
        "dryRunStatus": preview["status"],
        "namespace": validated.namespace,
        "environment": validated.environment,
        "assetCount": len(validated.assets),
        "servingCount": len(validated.serving),
        "bundleDigest": digest(canonical(document)),
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
