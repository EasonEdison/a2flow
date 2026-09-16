"""Direct publication authorization tests; no database or listener."""
import unittest

from a2flow_management import (
    ManagementError, PublicationTarget, TrustedManagementContext,
)
from a2flow_management.publication import PublicationService


class Repository:
    environment = "PRT"

    def __init__(self):
        self.calls = 0

    def publication_history(self, *args):
        self.calls += 1
        return {}

    def publish_candidate(self, *args):
        self.calls += 1
        return {}

    def rollback_configuration(self, *args):
        self.calls += 1
        return {}


class PublicationServiceTests(unittest.TestCase):
    def test_direct_operations_reject_context_for_another_environment(self):
        repository = Repository()
        service = PublicationService(repository, "activity-planning")
        context = TrustedManagementContext(
            "admin-1", "ONLINE", frozenset({"ADMIN"}))
        target = PublicationTarget("ONLINE", "v2", "STABLE")

        operations = (
            lambda: service.history(
                context, "SKILL", "activity-planning/plan"),
            lambda: service.publish(
                context, "SKILL", "activity-planning/plan", {}, target,
                "sha256:" + "0" * 64),
            lambda: service.rollback(
                context, "SKILL", "activity-planning/plan", target,
                "sha256:" + "0" * 64),
        )
        for operation in operations:
            with self.subTest():
                with self.assertRaisesRegex(
                        ManagementError, "TRUSTED_ENVIRONMENT_MISMATCH"):
                    operation()
        self.assertEqual(0, repository.calls)



if __name__ == "__main__":
    unittest.main()
