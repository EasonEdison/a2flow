"""Release control-plane isolation and candidate integrity checks."""
import unittest
from unittest.mock import Mock
from a2flow_management.contracts import (
    ManagementError, PublicationPlan, PublicationTarget, TrustedManagementContext,
)
from a2flow_management.releases import ReleaseService


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.context = TrustedManagementContext(101, "PRT", frozenset({"ADMIN"}))
        self.target = PublicationTarget("ONLINE", "v2", "STABLE")
        self.source = Mock(environment="PRT", database="prt")
        self.online = Mock(environment="ONLINE", database="online")
        self.service = Mock()
        self.candidate = {"kind": "ABILITY", "key": "test", "versionId": "v2"}
        self.service.prepare_publication.return_value = PublicationPlan.create(
            "ABILITY", "test", 3, PublicationTarget("PRT", "v2", "CURRENT"), self.candidate)
        self.online.publication_history.return_value = {"servingDigest": "sha256:" + "0" * 64}
        self.online.check_candidate.return_value = {"published": False, "status": "PREPARED_NOT_PUBLISHED"}
        self.releases = ReleaseService(self.service,
            {"PRT": self.source, "ONLINE": self.online}, "demo", "PRT")

    def test_checks_target_without_writing_either_environment(self):
        result = self.releases.check(self.context, "ONLINE", "ABILITY", "test", 3, self.target)
        self.assertFalse(result["published"])
        self.online.check_candidate.assert_called_once()
        self.online.publish_candidate.assert_not_called()
        self.source.publish_candidate.assert_not_called()
        self.assertEqual("PRT", self.service.prepare_publication.call_args.args[-1].environment)

    def test_publication_writes_only_online(self):
        self.releases.publish(self.context, "ONLINE", "ABILITY", "test", 3,
                              self.target, self.candidate, "sha256:" + "0" * 64)
        self.online.publish_candidate.assert_called_once()
        self.source.publish_candidate.assert_not_called()

    def test_tampered_candidate_rejected(self):
        with self.assertRaisesRegex(ManagementError, "PREPARED_CANDIDATE_MISMATCH"):
            self.releases.publish(self.context, "ONLINE", "ABILITY", "test", 3,
                                  self.target, {}, "sha256:" + "0" * 64)
        self.online.publish_candidate.assert_not_called()

    def test_stale_source_revision_rejected_before_target_write(self):
        self.service.prepare_publication.side_effect = ManagementError("DRAFT_REVISION_CONFLICT", 409)
        with self.assertRaisesRegex(ManagementError, "DRAFT_REVISION_CONFLICT"):
            self.releases.publish(self.context, "ONLINE", "ABILITY", "test", 2,
                                  self.target, self.candidate, "sha256:" + "0" * 64)
        self.online.publish_candidate.assert_not_called()

    def test_missing_target_and_non_admin_are_rejected(self):
        releases = ReleaseService(self.service, {"PRT": self.source}, "demo", "PRT")
        self.assertFalse(releases.targets(self.context)["targets"][1]["available"])
        with self.assertRaisesRegex(ManagementError, "RELEASE_TARGET_UNAVAILABLE"):
            releases.check(self.context, "ONLINE", "ABILITY", "test", 3, self.target)
        with self.assertRaisesRegex(ManagementError, "ADMIN_REQUIRED"):
            self.releases.targets(TrustedManagementContext(101, "PRT", frozenset({"USER"})))

    def test_database_identity_must_be_separate(self):
        self.online.database = "prt"
        with self.assertRaisesRegex(ManagementError, "RELEASE_DATABASES_MUST_BE_SEPARATE"):
            ReleaseService(self.service, {"PRT": self.source, "ONLINE": self.online}, "demo", "PRT")

    def test_target_dependency_rejection_is_not_auto_published(self):
        from a2flow_asset_store.records import AssetError
        self.online.check_candidate.side_effect = AssetError("SERVING_DEPENDENCY_MISMATCH")
        with self.assertRaisesRegex(ManagementError, "SERVING_DEPENDENCY_MISMATCH"):
            self.releases.check(self.context, "ONLINE", "ABILITY", "test", 3, self.target)
        self.source.publish_candidate.assert_not_called()
        self.online.publish_candidate.assert_not_called()

    def test_target_http_route_preserves_slash_key_and_revision(self):
        from fastapi.testclient import TestClient
        from a2flow_management.http import create_app
        releases = Mock()
        releases.check.return_value = {"status": "PREPARED_NOT_PUBLISHED", "published": False}
        app = create_app(self.service, identity_resolver=lambda scope: self.context,
                         releases=releases)
        with TestClient(app) as client:
            response = client.post(
                "/management/release-targets/ONLINE/assets/SKILL/demo/test/publication-checks",
                json={"expectedRevision": 3, "target": {"environment": "ONLINE",
                      "versionId": "v2", "channel": "STABLE", "grayUserIds": []}})
        self.assertEqual(200, response.status_code)
        self.assertEqual(("ONLINE", "SKILL", "demo/test", 3), releases.check.call_args.args[1:5])

    def test_real_release_service_http_confirmation_contract(self):
        from fastapi.testclient import TestClient
        from a2flow_management.http import create_app
        serving_digest = "sha256:" + "0" * 64
        self.online.check_candidate.return_value = {
            "status": "PREPARED_NOT_PUBLISHED", "published": False,
            "expectedServingDigest": serving_digest,
        }
        # Exercise real HTTP serialization, ReleaseService.check and
        # PublicationPlan; only the persistence and source feature ports are fakes.
        app = create_app(self.service, identity_resolver=lambda scope: self.context,
                         releases=self.releases)
        with TestClient(app) as client:
            response = client.post(
                "/management/release-targets/ONLINE/assets/ABILITY/test/publication-checks",
                json={"expectedRevision": 3, "target": {"environment": "ONLINE",
                      "versionId": "v2", "channel": "STABLE", "grayUserIds": []}})
        self.assertEqual(200, response.status_code)
        result = response.json()
        self.assertEqual("PREPARED_NOT_PUBLISHED", result["status"])
        self.assertIs(False, result["published"])
        self.assertEqual(3, result["preparedRevision"])
        self.assertEqual(serving_digest, result["expectedServingDigest"])
        self.assertEqual({"kind": "ABILITY", "key": "test", "versionId": "v2",
                          "contentDigest": result["contentDigest"]},
                         result["candidateIdentity"])
        self.assertEqual(self.candidate, result["candidate"])
        self.online.publish_candidate.assert_not_called()
