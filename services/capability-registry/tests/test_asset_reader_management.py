"""Cross-module Ability management checks against the real AssetReader."""
from copy import deepcopy
import unittest

from a2flow_asset_store import AssetError, AssetReader
from a2flow_asset_store.records import canonical, digest
from a2flow_management import (
    ManagementService,
    MemoryDraftRepository,
    TrustedManagementContext,
)
from activity_planning_demo import BUDGET_KEY, bundle_validator
from activity_planning_demo.bundle import NAMESPACE, make_bundle
from capability_registry.management import create_ability_feature
from skillweave_contracts import TrustedContext


class MemoryAssetRepository:
    """Read-only repository double containing one already validated Bundle."""

    def __init__(self, bundle, validator):
        self.environment = bundle.environment
        self.bundle = bundle
        self.validator = validator
        self.read_calls = 0

    def read(self, namespace):
        self.read_calls += 1
        if namespace != self.bundle.namespace:
            raise AssertionError("unexpected namespace")
        return self.bundle


def repository(document):
    validator = bundle_validator()
    bundle = validator.validate(
        document,
        expected_namespace=NAMESPACE,
        expected_environment=document["environment"],
    )
    return MemoryAssetRepository(bundle, validator)


def resign(asset):
    value = {key: value for key, value in asset.items()
             if key != "contentDigest"}
    asset["contentDigest"] = digest(canonical(value))


class AssetReaderAbilityManagementTests(unittest.TestCase):
    def test_real_reader_lists_and_opens_example_abilities_through_service(self):
        assets = repository(make_bundle("PRT"))
        reader = AssetReader(assets, NAMESPACE)
        service = ManagementService([create_ability_feature(
            reader,
            MemoryDraftRepository("PRT"),
            NAMESPACE,
            assets.validator.ability,
        )])
        user = TrustedManagementContext(
            "user-1", "PRT", frozenset({"USER"}))

        listed = service.list_published(user, "ABILITY")
        detail = service.get_published(user, "ABILITY", BUDGET_KEY)

        self.assertIn(BUDGET_KEY, {item["key"] for item in listed})
        self.assertTrue(all(set(item) == {
            "kind", "key", "assetId", "versionId",
            "contentDigest", "selection",
        } for item in listed))
        self.assertEqual("PRT_CURRENT", next(
            item for item in listed if item["key"] == BUDGET_KEY)["selection"])
        self.assertEqual(BUDGET_KEY,
                         detail["definition"]["adapterOperationRef"])

    def test_online_list_resolves_stable_or_gray_by_trusted_user(self):
        document = make_bundle("ONLINE")
        source = next(asset for asset in document["assets"]
                      if asset["kind"] == "ABILITY"
                      and asset["key"] == BUDGET_KEY)
        gray = deepcopy(source)
        gray["versionId"] = "v2"
        resign(gray)
        document["assets"].append(gray)
        state = next(item for item in document["serving"]
                     if item["kind"] == "ABILITY"
                     and item["key"] == BUDGET_KEY)
        state["gray"] = "v2"
        state["grayUserIds"] = ["gray-user"]
        assets = repository(document)
        reader = AssetReader(assets, NAMESPACE)

        gray_list = reader.list_assets(
            "ABILITY", TrustedContext("gray-user", "ONLINE"))
        stable_list = reader.list_assets(
            "ABILITY", TrustedContext("stable-user", "ONLINE"))
        gray_item = next(item for item in gray_list
                         if item["key"] == BUDGET_KEY)
        stable_item = next(item for item in stable_list
                           if item["key"] == BUDGET_KEY)

        self.assertEqual(("v2", "ONLINE_GRAY"),
                         (gray_item["versionId"], gray_item["selection"]))
        self.assertEqual(("v1", "ONLINE_STABLE"),
                         (stable_item["versionId"], stable_item["selection"]))

    def test_wrong_environment_and_unknown_kind_fail_before_read(self):
        assets = repository(make_bundle("PRT"))
        reader = AssetReader(assets, NAMESPACE)

        with self.assertRaisesRegex(AssetError, "ENVIRONMENT_MISMATCH"):
            reader.list_assets(
                "ABILITY", TrustedContext("user-1", "ONLINE"))
        with self.assertRaisesRegex(AssetError, "UNKNOWN_ASSET_KIND"):
            reader.list_assets(
                "EXECUTABLE", TrustedContext("user-1", "PRT"))
        self.assertEqual(0, assets.read_calls)


if __name__ == "__main__":
    unittest.main()
