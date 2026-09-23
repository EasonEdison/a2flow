"""Java release selection must not be replaced with Python inventory pointers."""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from a2flow_asset_store.records import Asset, AssetError, Bundle
from agent_workflow_runtime.rpc_assets import RpcAssetReader
from agent_workflow_runtime.rpc_client import ReleaseIdentity
from skillweave_contracts import TrustedContext


def application(source: str) -> Asset:
    definition = {"runtimeProfile": "a2flow.java-rpc.v1", "assetKey": "app",
                  "sourceId": source, "sourceDigest": source + "-digest"}
    return Asset("APPLICATION", "app", "app-id", source,
                 json.dumps({"definition": definition}).encode(), "inventory-digest")


class RpcAssetsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rpc = Mock()
        self.owner = TrustedContext(9223372036854775807, "ONLINE")
        self.reader = RpcAssetReader(SimpleNamespace(environment="ONLINE"), "rpc-test", self.rpc)
        self.stable, self.gray = application("stable"), application("gray")
        # Deliberately stale inventory: it is not a second Java gray router.
        self.bundle = Bundle("rpc-test", "ONLINE", (self.stable, self.gray), b'[]')

    def select(self, source: str, environment: str = "ONLINE") -> None:
        self.rpc.describe.return_value = SimpleNamespace(release=ReleaseIdentity(
            "app", source, source + "-digest", source + "-build", environment))

    def test_authoritative_gray_selection_uses_exact_retained_material(self) -> None:
        self.select("gray")
        actual, selection = self.reader._resolve(self.bundle, self.owner, "APPLICATION", "app")
        self.assertEqual(actual, self.gray)
        self.assertEqual(selection, "JAVA_PUBLISHED")
        self.assertEqual(self.rpc.describe.call_args.args[:2], (self.owner, "app"))

    def test_stable_does_not_implicitly_select_newest_inventory_version(self) -> None:
        self.select("stable")
        actual, _ = self.reader._resolve(self.bundle, self.owner, "APPLICATION", "app")
        self.assertEqual(actual, self.stable)

    def test_missing_material_has_no_latest_or_stable_fallback(self) -> None:
        self.select("missing")
        with self.assertRaisesRegex(AssetError, "JAVA_PUBLISHED_MATERIAL_MISSING"):
            self.reader._resolve(self.bundle, self.owner, "APPLICATION", "app")

    def test_online_never_reads_prt_selection(self) -> None:
        self.select("gray", "PRT")
        with self.assertRaisesRegex(AssetError, "ENVIRONMENT_MISMATCH"):
            self.reader._resolve(self.bundle, self.owner, "APPLICATION", "app")

    def test_duplicate_identity_is_rejected(self) -> None:
        self.select("gray")
        duplicated = Bundle("rpc-test", "ONLINE", (self.gray, self.gray), b'[]')
        with self.assertRaisesRegex(AssetError, "JAVA_PUBLISHED_MATERIAL_MISSING"):
            self.reader._resolve(duplicated, self.owner, "APPLICATION", "app")


if __name__ == "__main__":
    unittest.main()
