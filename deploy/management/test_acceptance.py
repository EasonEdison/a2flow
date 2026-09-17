import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from deploy.management import acceptance


class AcceptanceGuardTests(unittest.TestCase):
    def report(self, output):
        return json.loads(
            (output / "management-acceptance.json").read_text(encoding="utf-8"))

    def test_requires_explicit_opt_in_before_creating_output(self):
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "result"
            self.assertEqual(2, acceptance.main([
                "--output-directory", str(output),
            ]))
            self.assertFalse(output.exists())

    def test_missing_python_dependency_prevents_docker_calls(self):
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "result"
            with patch(
                    "deploy.management.acceptance._check_python_dependencies",
                    side_effect=RuntimeError("PYTHON_DEPENDENCIES_REQUIRED")), \
                    patch("deploy.management.acceptance._docker") as docker:
                self.assertEqual(1, acceptance.main([
                    "--authorized-isolated-fixture",
                    "--output-directory", str(output),
                ]))
            docker.assert_not_called()
            report = self.report(output)
            self.assertEqual("NOT_RUN", report["status"])
            self.assertEqual("PYTHON_DEPENDENCIES_REQUIRED", report["error"])
            self.assertEqual("NOT_RUN", report["postgres"])

    def test_remote_docker_host_prevents_docker_calls(self):
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "result"
            with patch.dict(os.environ, {"DOCKER_HOST": "tcp://remote:2375"}), \
                    patch("deploy.management.acceptance._check_python_dependencies"), \
                    patch("deploy.management.acceptance._docker") as docker:
                self.assertEqual(1, acceptance.main([
                    "--authorized-isolated-fixture",
                    "--output-directory", str(output),
                ]))
            docker.assert_not_called()
            self.assertEqual("REMOTE_DOCKER_ENDPOINT_REJECTED", self.report(output)["error"])

    def test_missing_docker_cli_reports_not_run_without_fixture(self):
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "result"
            with patch("deploy.management.acceptance._check_python_dependencies"), \
                    patch("deploy.management.acceptance.shutil.which", return_value=None):
                self.assertEqual(1, acceptance.main([
                    "--authorized-isolated-fixture",
                    "--output-directory", str(output),
                ]))
            report = self.report(output)
            self.assertEqual("NOT_RUN", report["status"])
            self.assertEqual("DOCKER_CLI_REQUIRED", report["error"])
            self.assertEqual("NOT_RUN", report["postgres"])
            self.assertEqual("PASS", report["cleanup"])

    def test_missing_daemon_reports_not_run_without_fixture(self):
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "result"
            unavailable = subprocess.CompletedProcess(
                ["docker", "info"], 1, "", "daemon unavailable")
            local_context = subprocess.CompletedProcess(
                ["docker", "context", "inspect"], 0,
                '[{"Endpoints":{"docker":{"Host":"unix:///tmp/docker.sock"}}}]', "")
            with patch("deploy.management.acceptance._check_python_dependencies"), \
                    patch("deploy.management.acceptance.shutil.which", return_value="docker"), \
                    patch("deploy.management.acceptance._docker",
                          side_effect=[local_context, unavailable]):
                self.assertEqual(1, acceptance.main([
                    "--authorized-isolated-fixture",
                    "--output-directory", str(output),
                ]))
            report = self.report(output)
            self.assertEqual("DOCKER_DAEMON_REQUIRED", report["error"])
            self.assertEqual("NOT_RUN", report["configuration"])
            self.assertEqual("NOT_RUN", report["postgres"])

    def test_container_name_collision_and_query_failure_are_distinct(self):
        collision = subprocess.CompletedProcess(
            ["docker", "ps"], 0, "existing-id\n", "")
        failure = subprocess.CompletedProcess(["docker", "ps"], 1, "", "failed")
        with patch("deploy.management.acceptance._docker", return_value=collision):
            with self.assertRaisesRegex(RuntimeError, "FIXTURE_CONTAINER_ALREADY_EXISTS"):
                acceptance._require_unused_container_name("fixture")
        with patch("deploy.management.acceptance._docker", return_value=failure):
            with self.assertRaisesRegex(RuntimeError, "CONTAINER_NAME_CHECK_FAILED"):
                acceptance._require_unused_container_name("fixture")

    def test_cleanup_rejects_mismatched_container_identity_without_removal(self):
        ownership = acceptance.FixtureOwnership(
            invocation_id="expected", container_name="fixture",
            container_id="abc123", directory=None)
        observed = {
            "Id": "abc123",
            "Name": "/fixture",
            "Config": {"Labels": {
                "a2flow.owner": acceptance.OWNER,
                "a2flow.invocation": "other",
            }},
        }
        with patch("deploy.management.acceptance._inspect", return_value=observed), \
                patch("deploy.management.acceptance._docker") as docker:
            errors = acceptance._cleanup(ownership)
        self.assertEqual(["CONTAINER_OWNERSHIP_MISMATCH"], errors)
        docker.assert_not_called()

    def test_cleanup_does_not_remove_container_without_acquired_id(self):
        ownership = acceptance.FixtureOwnership(
            invocation_id="run", container_name="fixture",
            container_id=None, directory=None)
        with patch("deploy.management.acceptance._inspect") as inspect, \
                patch("deploy.management.acceptance._docker") as docker:
            self.assertEqual([], acceptance._cleanup(ownership))
        inspect.assert_not_called()
        docker.assert_not_called()

    def test_cleanup_reports_inspect_failure_without_removal(self):
        ownership = acceptance.FixtureOwnership(
            invocation_id="run", container_name="fixture",
            container_id="abc123", directory=None)
        with patch("deploy.management.acceptance._inspect",
                   side_effect=RuntimeError("CONTAINER_INSPECTION_FAILED")), \
                patch("deploy.management.acceptance._docker") as docker:
            errors = acceptance._cleanup(ownership)
        self.assertEqual(["CONTAINER_INSPECTION_FAILED"], errors)
        docker.assert_not_called()

    def test_cleanup_removes_only_exact_verified_container_and_directory(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent) / "fixture"
            directory.mkdir()
            (directory / ".owner").write_text("run-id", encoding="ascii")
            ownership = acceptance.FixtureOwnership(
                invocation_id="run-id", container_name="fixture",
                container_id="abc123", directory=directory)
            observed = {
                "Id": "abc123",
                "Name": "/fixture",
                "Config": {"Labels": {
                    "a2flow.owner": acceptance.OWNER,
                    "a2flow.invocation": "run-id",
                }},
            }
            removed = subprocess.CompletedProcess(["docker", "rm"], 0, "", "")
            with patch("deploy.management.acceptance._inspect", return_value=observed), \
                    patch("deploy.management.acceptance._docker", return_value=removed) as docker:
                self.assertEqual([], acceptance._cleanup(ownership))
            docker.assert_called_once_with("rm", "--force", "abc123", check=False)
            self.assertFalse(directory.exists())

    def test_cleanup_after_partial_container_creation_uses_cidfile(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent)
            cidfile = directory / "container.cid"
            cidfile.write_text("abc123abc123\n", encoding="ascii")
            ownership = acceptance.FixtureOwnership(
                invocation_id="run", container_name="fixture", directory=directory)
            acceptance._acquire_container_id(ownership, cidfile)
        self.assertEqual("abc123abc123", ownership.container_id)

    def test_cleanup_failure_overrides_verified_status(self):
        result = {"status": "VERIFIED", "postgres": "PASS"}
        acceptance._record_cleanup(result, ["CONTAINER_REMOVE_FAILED"])
        self.assertEqual("FAILED", result["status"])
        self.assertEqual("FAIL", result["cleanup"])
        self.assertEqual(["CONTAINER_REMOVE_FAILED"], result["cleanupErrors"])

    def test_fixture_plan_has_distinct_database_and_namespace_per_case(self):
        plan = acceptance._fixture_plan("run-token")
        self.assertEqual(len(acceptance.PG_CASES), len(plan))
        self.assertEqual(len(plan), len({item["database"] for item in plan.values()}))
        self.assertEqual(len(plan), len({item["namespace"] for item in plan.values()}))
        self.assertTrue(all(item["fixtureId"] == "run-token" for item in plan.values()))

    def test_test_evidence_rejects_zero_tests_and_skips(self):
        with self.assertRaisesRegex(RuntimeError, "POSTGRES_NO_TESTS_EXECUTED"):
            acceptance._test_evidence("Ran 0 tests", "", 0)
        with self.assertRaisesRegex(RuntimeError, "POSTGRES_TESTS_SKIPPED"):
            acceptance._test_evidence("Ran 4 tests", "OK (skipped=1)", 0)

    def test_direct_pg_entry_requires_owned_fixture_plan(self):
        source = (Path(__file__).resolve().parents[2]
                  / "services/management-api/tests/test_postgres_integration.py")
        text = source.read_text(encoding="utf-8")
        self.assertIn("A2FLOW_MANAGEMENT_PG_FIXTURE_PLAN", text)
        self.assertNotIn("A2FLOW_MANAGEMENT_PRT_DATABASE", text)
        self.assertNotIn("A2FLOW_MANAGEMENT_ONLINE_DATABASE", text)
        self.assertIn("a2flow_acceptance_fixture", text)

    def test_timeout_is_sanitized_and_never_verified(self):
        error = subprocess.TimeoutExpired(["python", "suite"], 300)
        self.assertEqual("TimeoutExpired", acceptance._sanitized_error(error))
        result = {"status": "NOT_RUN", "postgres": "NOT_RUN"}
        acceptance._record_cleanup(result, ["FIXTURE_DIRECTORY_REMOVE_FAILED"])
        self.assertEqual("FAILED", result["status"])

    def test_run_timeout_without_cidfile_writes_failed_report_and_retains_fixture(self):
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "result"
            fixture = Path(parent) / "fixture"
            fixture.mkdir()
            completed = subprocess.CompletedProcess(["docker"], 0, "", "")

            def docker(*arguments, **kwargs):
                if arguments[0] == "run":
                    raise subprocess.TimeoutExpired(["docker", "run"], 60)
                return completed

            with patch("deploy.management.acceptance._check_python_dependencies"), \
                    patch("deploy.management.acceptance.shutil.which", return_value="docker"), \
                    patch("deploy.management.acceptance._check_local_docker_endpoint"), \
                    patch("deploy.management.acceptance._require_unused_container_name"), \
                    patch("deploy.management.acceptance.tempfile.mkdtemp", return_value=str(fixture)), \
                    patch("deploy.management.acceptance._docker", side_effect=docker):
                exit_code = acceptance.main([
                    "--authorized-isolated-fixture",
                    "--output-directory", str(output),
                ])

            report = self.report(output)
            self.assertEqual(1, exit_code)
            self.assertEqual("FAILED", report["status"])
            self.assertEqual("DOCKER_RUN_TIMEOUT", report["error"])
            self.assertEqual("FAIL", report["cleanup"])
            self.assertEqual("NOT_RUN", report["postgres"])
            self.assertIn("CONTAINER_CREATION_UNCONFIRMED", report["cleanupErrors"])
            self.assertEqual(str(fixture), report["recovery"]["fixtureDirectory"])
            self.assertEqual(report["recovery"]["containerName"], report["containerName"])
            self.assertNotIn("database", json.dumps(report).lower())
            self.assertTrue(fixture.exists())

    def test_main_reports_cleanup_inspect_timeout_and_retains_fixture(self):
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "result"
            fixture = Path(parent) / "fixture"
            fixture.mkdir()
            cid = "abc123abc123"

            def docker(*arguments, **kwargs):
                if arguments[0] == "run":
                    (fixture / "container.cid").write_text(cid, encoding="ascii")
                    raise RuntimeError("COMMAND_FAILED")
                return subprocess.CompletedProcess(["docker"], 0, "", "")

            with patch("deploy.management.acceptance._check_python_dependencies"), \
                    patch("deploy.management.acceptance.shutil.which", return_value="docker"), \
                    patch("deploy.management.acceptance._check_local_docker_endpoint"), \
                    patch("deploy.management.acceptance._require_unused_container_name"), \
                    patch("deploy.management.acceptance.tempfile.mkdtemp", return_value=str(fixture)), \
                    patch("deploy.management.acceptance._docker", side_effect=docker), \
                    patch("deploy.management.acceptance._inspect",
                          side_effect=subprocess.TimeoutExpired(["docker", "inspect"], 60)):
                exit_code = acceptance.main([
                    "--authorized-isolated-fixture",
                    "--output-directory", str(output),
                ])

            report = self.report(output)
            self.assertEqual(1, exit_code)
            self.assertEqual("FAILED", report["status"])
            self.assertEqual("RuntimeError", report["error"])
            self.assertEqual(["CONTAINER_INSPECTION_TIMEOUT"], report["cleanupErrors"])
            self.assertEqual(cid, report["recovery"]["containerId"])
            self.assertTrue(fixture.exists())

    def test_main_reports_remove_failure_and_retains_fixture(self):
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "result"
            fixture = Path(parent) / "fixture"
            fixture.mkdir()
            cid = "abc123abc123"
            observed = {
                "Id": cid,
                "Name": "/" + acceptance.PREFIX + "run-id",
                "Config": {"Labels": {
                    "a2flow.owner": acceptance.OWNER,
                    "a2flow.invocation": "run-id",
                }},
                "HostConfig": {
                    "NetworkMode": "none",
                    "Memory": 256 * 1024 * 1024,
                    "MemorySwap": 256 * 1024 * 1024,
                },
                "NetworkSettings": {"Ports": {}},
            }

            def docker(*arguments, **kwargs):
                if arguments[0] == "run":
                    (fixture / "container.cid").write_text(cid, encoding="ascii")
                    return subprocess.CompletedProcess(["docker"], 0, cid, "")
                if arguments[0] == "rm":
                    return subprocess.CompletedProcess(["docker"], 1, "", "")
                return subprocess.CompletedProcess(["docker"], 0, "", "")

            with patch("deploy.management.acceptance.secrets.token_hex", return_value="run-id"), \
                    patch("deploy.management.acceptance._check_python_dependencies"), \
                    patch("deploy.management.acceptance.shutil.which", return_value="docker"), \
                    patch("deploy.management.acceptance._check_local_docker_endpoint"), \
                    patch("deploy.management.acceptance._require_unused_container_name"), \
                    patch("deploy.management.acceptance.tempfile.mkdtemp", return_value=str(fixture)), \
                    patch("deploy.management.acceptance._docker", side_effect=docker), \
                    patch("deploy.management.acceptance._inspect", return_value=observed), \
                    patch("deploy.management.acceptance._wait",
                          side_effect=RuntimeError("POSTGRES_NOT_READY")):
                exit_code = acceptance.main([
                    "--authorized-isolated-fixture",
                    "--output-directory", str(output),
                ])

            report = self.report(output)
            self.assertEqual(1, exit_code)
            self.assertEqual("FAILED", report["status"])
            self.assertEqual("POSTGRES_NOT_READY", report["error"])
            self.assertEqual(["CONTAINER_REMOVE_FAILED"], report["cleanupErrors"])
            self.assertEqual(str(fixture), report["recovery"]["fixtureDirectory"])
            self.assertTrue(fixture.exists())

    def test_main_successful_cleanup_removes_fixture_and_has_no_recovery(self):
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "result"
            fixture = Path(parent) / "fixture"
            fixture.mkdir()
            cid = "abc123abc123"
            observed = {
                "Id": cid,
                "Name": "/" + acceptance.PREFIX + "run-id",
                "Config": {"Labels": {
                    "a2flow.owner": acceptance.OWNER,
                    "a2flow.invocation": "run-id",
                }},
                "HostConfig": {
                    "NetworkMode": "none",
                    "Memory": 256 * 1024 * 1024,
                    "MemorySwap": 256 * 1024 * 1024,
                },
                "NetworkSettings": {"Ports": {}},
            }

            def docker(*arguments, **kwargs):
                if arguments[0] == "run":
                    (fixture / "container.cid").write_text(cid, encoding="ascii")
                return subprocess.CompletedProcess(["docker"], 0, "", "")

            test_result = subprocess.CompletedProcess(
                ["python", "suite"], 0, "Ran 5 tests in 0.1s\nOK\n", "")
            with patch("deploy.management.acceptance.secrets.token_hex", return_value="run-id"), \
                    patch("deploy.management.acceptance._check_python_dependencies"), \
                    patch("deploy.management.acceptance.shutil.which", return_value="docker"), \
                    patch("deploy.management.acceptance._check_local_docker_endpoint"), \
                    patch("deploy.management.acceptance._require_unused_container_name"), \
                    patch("deploy.management.acceptance.tempfile.mkdtemp", return_value=str(fixture)), \
                    patch("deploy.management.acceptance._docker", side_effect=docker), \
                    patch("deploy.management.acceptance._inspect", return_value=observed), \
                    patch("deploy.management.acceptance._wait", return_value="17.2"), \
                    patch("deploy.management.acceptance._create_databases"), \
                    patch("deploy.management.acceptance._run", return_value=test_result):
                exit_code = acceptance.main([
                    "--authorized-isolated-fixture",
                    "--output-directory", str(output),
                ])

            report = self.report(output)
            self.assertEqual(0, exit_code)
            self.assertEqual("VERIFIED", report["status"])
            self.assertEqual("PASS", report["cleanup"])
            self.assertNotIn("recovery", report)
            self.assertFalse(fixture.exists())

    def test_main_marks_started_postgres_timeout_failed(self):
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "result"
            fixture = Path(parent) / "fixture"
            fixture.mkdir()
            cid = "abc123abc123"
            observed = {
                "Id": cid,
                "Name": "/" + acceptance.PREFIX + "run-id",
                "Config": {"Labels": {
                    "a2flow.owner": acceptance.OWNER,
                    "a2flow.invocation": "run-id",
                }},
                "HostConfig": {
                    "NetworkMode": "none",
                    "Memory": 256 * 1024 * 1024,
                    "MemorySwap": 256 * 1024 * 1024,
                },
                "NetworkSettings": {"Ports": {}},
            }

            def docker(*arguments, **kwargs):
                if arguments[0] == "run":
                    (fixture / "container.cid").write_text(cid, encoding="ascii")
                return subprocess.CompletedProcess(["docker"], 0, "", "")

            with patch("deploy.management.acceptance.secrets.token_hex", return_value="run-id"), \
                    patch("deploy.management.acceptance._check_python_dependencies"), \
                    patch("deploy.management.acceptance.shutil.which", return_value="docker"), \
                    patch("deploy.management.acceptance._check_local_docker_endpoint"), \
                    patch("deploy.management.acceptance._require_unused_container_name"), \
                    patch("deploy.management.acceptance.tempfile.mkdtemp", return_value=str(fixture)), \
                    patch("deploy.management.acceptance._docker", side_effect=docker), \
                    patch("deploy.management.acceptance._inspect", return_value=observed), \
                    patch("deploy.management.acceptance._wait", return_value="17.2"), \
                    patch("deploy.management.acceptance._create_databases"), \
                    patch("deploy.management.acceptance._run",
                          side_effect=subprocess.TimeoutExpired(["python", "suite"], 300)):
                exit_code = acceptance.main([
                    "--authorized-isolated-fixture",
                    "--output-directory", str(output),
                ])

            report = self.report(output)
            self.assertEqual(1, exit_code)
            self.assertEqual("FAILED", report["status"])
            self.assertEqual("FAIL", report["postgres"])
            self.assertEqual("POSTGRES_ACCEPTANCE_TIMEOUT", report["error"])
            self.assertEqual("PASS", report["cleanup"])
            self.assertFalse(fixture.exists())

    def test_child_environment_excludes_external_credentials(self):
        with patch.dict(os.environ, {
                "PATH": "/bin", "HOME": "/tmp/home",
                "DATABASE_URL": "secret", "OPENAI_API_KEY": "secret",
                "DOCKER_HOST": "tcp://remote:2375"}, clear=True):
            environment = acceptance._test_environment(
                Path("/repo"), Path("/fixture.json"), Path("/password"))
        self.assertEqual("/bin", environment["PATH"])
        self.assertNotIn("DATABASE_URL", environment)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("DOCKER_HOST", environment)
        self.assertEqual("1", environment["A2FLOW_MANAGEMENT_PG_REQUIRED"])


if __name__ == "__main__":
    unittest.main()
