"""Focused compatibility tests for shared asset identities and typed boundaries."""

import json
import unittest

from a2flow_asset_store.records import Bundle
from a2flow_management.contracts import ManagementError
from a2flow_management.http_models import Target
from skillweave_contracts import AssetIdentity


class AssetKernelTypeTests(unittest.TestCase):
    def test_http_user_id_string_becomes_domain_integer(self) -> None:
        request = Target.model_validate(
            {
                "environment": "ONLINE",
                "versionId": "v2",
                "channel": "GRAY",
                "grayUserIds": ["9007199254740993"],
            }
        )

        target = request.to_domain()

        self.assertEqual((9007199254740993,), target.gray_user_ids)
        self.assertEqual(["9007199254740993"], target.to_mapping()["grayUserIds"])

    def test_http_target_preserves_domain_validation_codes(self) -> None:
        request = Target.model_validate(
            {
                "environment": "PRT",
                "versionId": "v2",
                "channel": "GRAY",
                "grayUserIds": ["101"],
            }
        )

        with self.assertRaisesRegex(ManagementError, "INVALID_PRT_TARGET"):
            request.to_domain()

    def test_bundle_serving_reconstructs_typed_user_ids(self) -> None:
        serving = json.dumps(
            [
                {
                    "kind": "SKILL",
                    "key": "activity-package/choose-plan",
                    "current": None,
                    "stable": "v1",
                    "gray": "v2",
                    "grayUserIds": ["9007199254740993"],
                }
            ]
        ).encode()
        bundle = Bundle("a2flow", "ONLINE", (), serving)

        self.assertEqual([9007199254740993], bundle.serving[0]["grayUserIds"])
        self.assertEqual(
            AssetIdentity("SKILL", "activity-package/choose-plan"),
            AssetIdentity(bundle.serving[0]["kind"], bundle.serving[0]["key"]),
        )


if __name__ == "__main__":
    unittest.main()
