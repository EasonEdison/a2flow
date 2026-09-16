import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "deploy/management/compose.yaml").read_text()
DOCKERFILE = (ROOT / "deploy/management/Dockerfile").read_text()


class ManagementPackagingTest(unittest.TestCase):
    def test_postgres_has_no_network_or_published_port(self):
        postgres = COMPOSE.split("  management:", 1)[0]
        self.assertIn("network_mode: none", postgres)
        self.assertIn("listen_addresses=", postgres)
        self.assertIn("postgres_data:/var/lib/postgresql/data", postgres)
        self.assertNotIn("ports:", postgres)

    def test_host_uses_loopback_preserving_host_network(self):
        management = COMPOSE.split("  management:", 1)[1].split(
            "  initialize:", 1)[0]
        self.assertIn("network_mode: host", management)
        self.assertNotIn("ports:", management)
        self.assertIn("A2FLOW_MANAGEMENT_HOST_PORT:-8766", management)
        self.assertIn("A2FLOW_MANAGEMENT_BROWSER_PORT:-14177", management)
        self.assertIn("postgres_socket:/run/postgresql", management)

    def test_secrets_and_static_are_external(self):
        self.assertNotIn("A2FLOW_MANAGEMENT_DATABASE_URL:", COMPOSE)
        self.assertIn("management_postgres_password", COMPOSE)
        self.assertIn("management_auth_token", COMPOSE)
        self.assertIn("A2FLOW_MANAGEMENT_STATIC_HOST_DIRECTORY", COMPOSE)
        self.assertNotIn("DEEPSEEK", COMPOSE)
        self.assertNotIn("MODEL_", COMPOSE)

    def test_image_contains_only_management_dependency_roots(self):
        self.assertIn("services/management-api", DOCKERFILE)
        self.assertIn("services/skill-registry", DOCKERFILE)
        self.assertIn("services/capability-registry", DOCKERFILE)
        self.assertIn("services/a2ui-composer", DOCKERFILE)
        self.assertIn("services/workflow-composer", DOCKERFILE)
        self.assertNotIn("services/agent-workflow-runtime", DOCKERFILE)
        self.assertNotIn("apps/digital-employee", DOCKERFILE)
        self.assertIn("--no-deps --require-hashes", DOCKERFILE)


if __name__ == "__main__":
    unittest.main()
