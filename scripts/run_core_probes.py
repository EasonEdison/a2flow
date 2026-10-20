#!/usr/bin/env python3
"""Run bounded synthetic probes; never accepts an installation DSN or model key."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
import uuid

# Preserve the exported mount path: Colima may share /tmp without /private/tmp.
ROOT = Path(os.path.abspath(__file__)).parents[1]
OWNER = "a2flow.core-probes"
REDACTIONS: list[str] = []
JAVA_PROBES = (
    ("capability-approval", "CapabilityApprovalGuardProbe", "dev.a2flow.management.capabilityrpc"),
    ("package-restore", "PackageRestoreGuardProbe", "dev.a2flow.management.lifecycle.artifact"),
)


class ProbeFailure(RuntimeError):
    pass


def command(argv: list[str], *, timeout: int = 60, env=None) -> str:
    """Bound child processes including their descendants; never use a shell."""
    with subprocess.Popen(argv, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, start_new_session=True) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise ProbeFailure(f"{Path(argv[0]).name}: deadline exceeded ({timeout}s)") from None
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise
        if process.returncode:
            # Only these fixed synthetic probes run here. Bound diagnostics and
            # remove generated credentials before they reach logs or artifacts.
            detail = stderr[-2000:]
            for value in REDACTIONS:
                detail = detail.replace(value, "[redacted]")
            detail = re.sub(r"(?i)(password\s*=\s*)\S+", r"\1[redacted]", detail)
            raise ProbeFailure(f"{Path(argv[0]).name}: exit {process.returncode}: {detail.strip()}")
        return stdout


def result_json(output: str) -> dict:
    for line in reversed(output.splitlines()):
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict):
            return result
    raise ProbeFailure("Probe returned no JSON result")


def clean_environment() -> dict[str, str]:
    # No provider keys, PG settings, Java agent injection or Python optimization.
    return {key: os.environ[key] for key in
            ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "JAVA_HOME") if key in os.environ}


def remove_containers(docker: list[str], run_id: str) -> None:
    ids = command([*docker, "ps", "-aq", "--filter", f"label={OWNER}.run={run_id}",
                   "--filter", f"label={OWNER}.owner=runner"]).split()
    if ids:
        command([*docker, "rm", "-f", *ids])


@contextmanager
def isolated_postgres(args, report: dict):
    docker = ["docker"]
    if args.docker_context:
        docker += ["--context", args.docker_context]
    labels = ["--label", f"{OWNER}.run={args.run_id}", "--label", f"{OWNER}.owner=runner"]
    pg = f"a2flow-core-probes-{args.run_id}-pg"
    if command([*docker, "ps", "-aq", "--filter", f"label={OWNER}.run={args.run_id}"]).strip():
        report["cleanup"] = "not attempted: pre-existing run resources preserved"
        raise ProbeFailure("Run ID already owns containers; choose another ID or inspect explicit cleanup")
    # The private directory is outside the source tree, never an uploaded artifact.
    with tempfile.TemporaryDirectory(prefix="a2flow-core-probes-", dir=args.scratch_dir) as directory:
        private = Path(directory).absolute()
        if private.resolve().is_relative_to(ROOT.resolve()):
            raise ProbeFailure("Private scratch directory must be outside the source checkout")
        password = secrets.token_hex(24)
        REDACTIONS.append(password)
        env_file = private / "postgres.env"
        env_file.write_text(f"POSTGRES_USER=probe\nPOSTGRES_PASSWORD={password}\n")
        env_file.chmod(0o600)
        try:
            command([*docker, "run", "-d", "--name", pg, *labels, "--network", "none",
                     "--memory", "512m", "--cpus", "1", "--env-file", str(env_file),
                     "--tmpfs", "/var/lib/postgresql/data:rw,size=256m",
                     args.postgres_image, "-c", "shared_buffers=32MB"], timeout=120)
            deadline = time.monotonic() + 90
            while True:
                try:
                    command([*docker, "exec", pg, "pg_isready", "-U", "probe"], timeout=5)
                    break
                except ProbeFailure:
                    if time.monotonic() >= deadline:
                        raise ProbeFailure("PostgreSQL readiness deadline exceeded") from None
                    time.sleep(1)
            yield docker, labels, pg, private, password
        finally:
            remove_containers(docker, args.run_id)
            report["cleanup"] = "containers removed; private directory removed on context exit"


def postgres_probes(args, report: dict) -> None:
    with isolated_postgres(args, report) as resources:
        docker, labels, pg, private, password = resources
        paths = [".", "packages/contracts/src", "packages/asset-store/src", "packages/rpc-contracts/src",
                 "services/b-side-api/src", "services/agent-workflow-runtime/src",
                 "services/capability-execution/src", "services/a2ui-execution/src",
                 "services/scheduler-mq/src", "services/skill-registry/src",
                 "services/capability-registry/src", "services/a2ui-composer/src"]
        probes = (
            ("account-guard", "a2flow_auth_probe_ci",
             ["scripts/verify_account_guard.py", "--dsn-file", "/private/probe.dsn",
              "--allow-disposable-database"]),
            ("runtime-outbox", "a2flow_outbox_probe_ci",
             ["openspec/changes/portfolio-runtime-outbox/probe.py"]),
            ("capability-approval", "a2flow_capability_probe_ci",
             ["scripts/verify_capability_approval.py", "--dsn-file", "/private/probe.dsn",
              "--allow-disposable-database"]),
            ("chat-write-approval", None, ["scripts/verify_chat_write_approval.py"]),
            ("workflow-write-approval", None, ["scripts/verify_workflow_write_approval.py"]),
            ("a2ui-write-preflight", None, ["scripts/verify_a2ui_write_preflight.py"]),
        )
        for name, database, entry in probes:
            if args.python_probe != "all" and name != args.python_probe:
                continue
            dsn_file = private / "probe.dsn"
            probe_env = private / "probe.env"
            if database:
                command([*docker, "exec", pg, "createdb", "-U", "probe", database])
                dsn = f"host=127.0.0.1 dbname={database} user=probe password={password} connect_timeout=5"
                dsn_file.write_text(dsn)
                dsn_file.chmod(0o600)
                probe_env.write_text("A2FLOW_PROBE_DATABASE_URL=" + dsn + "\n")
            else:
                dsn_file.unlink(missing_ok=True)
                probe_env.write_text("")
            probe_env.chmod(0o600)
            output = command([
                *docker, "run", "--rm", "--name", f"a2flow-core-probes-{args.run_id}-{name}",
                *labels, "--network", f"container:{pg}" if database else "none",
                "--memory", "768m", "--cpus", "1",
                "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--tmpfs", "/tmp:rw,size=128m,mode=1777", "--user", f"{os.getuid()}:{os.getgid()}",
                "--mount", f"type=bind,src={args.source_root},dst=/workspace,readonly",
                "--mount", f"type=bind,src={private},dst=/private,readonly",
                "--workdir", "/workspace", "--env-file", str(probe_env),
                "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--env", "PYTHONPATH=" + ":".join("/workspace/" + path for path in paths),
                "--entrypoint", "python", args.python_image, *entry,
            ], timeout=args.probe_timeout)
            result = result_json(output)
            if name == "account-guard" and (result.get("result") != "PASS"
                                            or result.get("probeSchemaRemoved") is not True):
                raise ProbeFailure("Account guard result did not confirm success and cleanup")
            if name == "runtime-outbox":
                checks = result.get("checks", {})
                if (not isinstance(checks, dict) or not checks
                        or any(value != "PASS" for value in checks.values())
                        or result.get("externalSends") != 0 or result.get("businessCalls") != 0):
                    raise ProbeFailure("Outbox result did not confirm all invariants")
            if database is None and (result.get("result") != "PASS" or result.get("probe") != name
                                     or not isinstance(result.get("checks"), int) or result["checks"] < 1):
                raise ProbeFailure(f"{name}: missing PASS result")
            if name == "capability-approval" and (result.get("result") != "PASS"
                                                or result.get("postgres") is not True
                                                or result.get("probeResourcesRemoved") is not True):
                raise ProbeFailure("Actual capability executor/PG probe did not pass with cleanup")
            report["probes"][name] = result
            print(f"PASS: {name}", flush=True)
            # Each script removes its own schema; independently verify this.
            if database:
                check_schemas_removed(docker, pg, database)


def check_schemas_removed(docker: list[str], pg: str, database: str) -> None:
    count = command([*docker, "exec", pg, "psql", "-U", "probe", "-d", database,
                     "-Atc", "SELECT count(*) FROM pg_namespace WHERE nspname "
                     "NOT IN ('public','information_schema') AND nspname NOT LIKE 'pg_%'"])
    if count.strip() != "0":
        raise ProbeFailure("Probe schema remains in its disposable database")


def java_postgres_probe(args, report: dict, classes: str, main_class: str) -> str:
    with isolated_postgres(args, report) as resources:
        docker, labels, pg, private, password = resources
        command([*docker, "exec", pg, "createdb", "-U", "probe", "a2flow_approval_probe"])
        env_file = private / "java.env"
        env_file.write_text("A2FLOW_PROBE_DB_PASSWORD=" + password + "\n")
        env_file.chmod(0o600)
        classpath = ("/probe-classes:/workspace/services/management-java/target/classes:"
                     "/workspace/services/management-java/target/dependency/*")
        output = command([
            *docker, "run", "--rm", "--name", f"a2flow-core-probes-{args.run_id}-approval",
            *labels, "--network", f"container:{pg}", "--memory", "512m", "--cpus", "1",
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--tmpfs", "/tmp:rw,size=64m,mode=1777", "--user", f"{os.getuid()}:{os.getgid()}",
            "--mount", f"type=bind,src={args.source_root},dst=/workspace,readonly",
            "--mount", f"type=bind,src={classes},dst=/probe-classes,readonly",
            "--workdir", "/workspace", "--env-file", str(env_file),
            "--entrypoint", "java", args.java_image, "-ea", "-cp", classpath, main_class,
            "jdbc:postgresql://127.0.0.1:5432/a2flow_approval_probe", "probe",
        ], timeout=args.probe_timeout)
        check_schemas_removed(docker, pg, "a2flow_approval_probe")
        return output


def java_probes(args, report: dict) -> None:
    base = ROOT / "services/management-java"
    classpath = str(base / "target/classes") + os.pathsep + str(base / "target/dependency/*")
    with tempfile.TemporaryDirectory(prefix="a2flow-core-java-", dir=args.scratch_dir) as classes:
        for name, filename, package in JAVA_PROBES:
            if args.java_probe != "all" and name != args.java_probe:
                continue
            source = base / f"backend/storage/db/tests/{filename}.java"
            if not source.is_file():
                raise ProbeFailure(f"Required probe missing: {filename}.java")
            command(["javac", "--release", "17", "-cp", classpath, "-d", classes, str(source)],
                    timeout=120, env=clean_environment())
            if name == "capability-approval":
                output = java_postgres_probe(args, report, classes, f"{package}.{filename}")
            else:
                output = command(["java", "-ea", "-cp", classes + os.pathsep + classpath,
                                  f"{package}.{filename}"], timeout=args.probe_timeout,
                                 env=clean_environment())
            result = result_json(output)
            if result.get("result") != "PASS":
                raise ProbeFailure(f"{name}: missing PASS result")
            if name == "capability-approval" and result.get("postgres") is not True:
                raise ProbeFailure("Approval probe did not exercise PostgreSQL")
            report["probes"][name] = result
            print(f"PASS: {name}", flush=True)
    report["cleanup"] = ("temporary Java classes removed" if args.java_probe == "package-restore"
                         else "temporary Java classes, PostgreSQL containers and private files removed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("postgres", "java"), default="postgres")
    parser.add_argument("--python-probe", choices=("all", "account-guard", "runtime-outbox",
                        "capability-approval", "chat-write-approval", "workflow-write-approval",
                        "a2ui-write-preflight"),
                        default="all", help="Local focused reproduction; CI always selects all")
    parser.add_argument("--java-probe", choices=("all", "capability-approval", "package-restore"),
                        default="all", help="Local focused reproduction; CI always selects all")
    parser.add_argument("--docker-context")
    parser.add_argument("--postgres-image", default="postgres:16.6-bookworm")
    parser.add_argument("--python-image", default="a2flow-core-probes:local")
    parser.add_argument("--java-image", default="eclipse-temurin:17-jre-jammy")
    parser.add_argument("--run-id", default=uuid.uuid4().hex)
    parser.add_argument("--scratch-dir", type=Path)
    parser.add_argument("--source-root", type=Path, default=ROOT,
                        help="Equivalent source path shared with Docker (for VM/symlink mounts)")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "artifacts/core-probes")
    parser.add_argument("--probe-timeout", type=int, default=300)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", args.run_id):
        parser.error("run-id must be 1-48 lowercase letters, digits or hyphens")
    if not 1 <= args.probe_timeout <= 600:
        parser.error("probe-timeout must be between 1 and 600 seconds")
    if not args.source_root.is_absolute() or args.source_root.resolve() != ROOT.resolve():
        parser.error("source-root must be an absolute equivalent path to this runner's checkout")
    if args.cleanup:
        docker = ["docker"] + (["--context", args.docker_context] if args.docker_context else [])
        remove_containers(docker, args.run_id)
        return 0
    report = {"suite": args.suite, "runId": args.run_id, "result": "FAIL",
              "probes": {}, "cleanup": "not confirmed"}
    if args.suite == "java":
        report["requestedProbes"] = args.java_probe
    else:
        report["requestedProbes"] = args.python_probe
    def interrupted(signum, frame):
        raise ProbeFailure(f"Interrupted by signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        (postgres_probes if args.suite == "postgres" else java_probes)(args, report)
        report["result"] = "PASS"
    except (ProbeFailure, OSError, KeyboardInterrupt) as error:
        # No tracebacks/connection strings in artifacts.
        report["error"] = str(error) if isinstance(error, ProbeFailure) else type(error).__name__
    finally:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        (args.report_dir / f"{args.suite}.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
