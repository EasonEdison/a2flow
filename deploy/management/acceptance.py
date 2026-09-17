import argparse
from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time


IMAGE = "public.ecr.aws/docker/library/postgres@sha256:7bade6d532592ca8ce7ee32def7399dad2607c4ea5583839fc4352a095a11ea6"
OWNER = "a2flow-management-acceptance"
PREFIX = "a2flow-management-accept-"
PG_CASES = (
    "test_four_kind_http_drafts_prepare_and_user_denial",
    "test_four_kind_immutable_publication_serving_cas_and_rollback",
    "test_online_stable_gray_finish_rollback_and_isolation",
    "test_dependency_invalid_publication_is_atomic_for_each_environment.PRT",
    "test_dependency_invalid_publication_is_atomic_for_each_environment.ONLINE",
    "test_concurrent_create_same_key_is_atomic_conflict",
    "test_first_edit_of_imported_asset_creates_draft",
    "test_create_waits_for_uncommitted_import_then_rejects",
)


@dataclass
class FixtureOwnership:
    invocation_id: str
    container_name: str
    container_id: str | None = None
    directory: Path | None = None
    creation_attempted: bool = False


def _run(arguments, *, timeout=60, check=True, environment=None):
    result = subprocess.run(
        arguments, capture_output=True, text=True, timeout=timeout,
        env=environment,
    )
    if check and result.returncode:
        raise RuntimeError("COMMAND_FAILED")
    return result


def _docker(*arguments, **kwargs):
    return _run(["docker", *arguments], **kwargs)


def _inspect(container_id):
    result = _docker("container", "inspect", container_id, check=False)
    if result.returncode:
        raise RuntimeError("CONTAINER_INSPECTION_FAILED")
    try:
        values = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("CONTAINER_INSPECTION_FAILED") from error
    if len(values) != 1:
        raise RuntimeError("CONTAINER_INSPECTION_FAILED")
    return values[0]


def _require_unused_container_name(name):
    result = _docker(
        "container", "ls", "--all", "--quiet", "--filter", "name=^/" + name + "$",
        check=False,
    )
    if result.returncode:
        raise RuntimeError("CONTAINER_NAME_CHECK_FAILED")
    if result.stdout.strip():
        raise RuntimeError("FIXTURE_CONTAINER_ALREADY_EXISTS")


def _check_python_dependencies():
    required = ("fastapi", "httpx", "psycopg", "pydantic")
    if any(importlib.util.find_spec(name) is None for name in required):
        raise RuntimeError("PYTHON_DEPENDENCIES_REQUIRED")


def _check_local_docker_endpoint():
    inherited = os.environ.get("DOCKER_HOST")
    if inherited and not inherited.startswith(("unix://", "npipe://")):
        raise RuntimeError("REMOTE_DOCKER_ENDPOINT_REJECTED")
    context = os.environ.get("DOCKER_CONTEXT")
    arguments = ["context", "inspect"]
    if context:
        arguments.append(context)
    inspected = _docker(*arguments, check=False)
    if inspected.returncode:
        raise RuntimeError("DOCKER_CONTEXT_INSPECTION_FAILED")
    try:
        values = json.loads(inspected.stdout)
        endpoint = values[0]["Endpoints"]["docker"]["Host"]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("DOCKER_CONTEXT_INSPECTION_FAILED") from error
    if not endpoint.startswith(("unix://", "npipe://")):
        raise RuntimeError("REMOTE_DOCKER_ENDPOINT_REJECTED")


def _safe_output(path):
    target = Path(path)
    if not target.is_absolute() or target.exists() or target.is_symlink():
        raise RuntimeError("NEW_ABSOLUTE_OUTPUT_DIRECTORY_REQUIRED")
    parent = target.parent.resolve(strict=True)
    if parent.is_symlink() or not parent.is_dir():
        raise RuntimeError("SAFE_OUTPUT_PARENT_REQUIRED")
    target.mkdir(mode=0o700)
    return target


def _write_secret(directory, name, value):
    path = directory / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii") as stream:
        stream.write(value)
    return path


def _conninfo(socket_directory, database, password):
    from psycopg.conninfo import make_conninfo

    return make_conninfo(
        host=str(socket_directory), dbname=database, user="postgres",
        password=password,
    )


def _wait(socket_directory, password):
    from psycopg import connect

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with connect(
                    _conninfo(socket_directory, "postgres", password),
                    connect_timeout=2) as connection:
                return connection.execute("SHOW server_version").fetchone()[0]
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("POSTGRES_NOT_READY")


def _fixture_plan(invocation_id):
    plan = {}
    for index, case in enumerate(PG_CASES, start=1):
        token = re.sub(r"[^a-z0-9]", "_", case.lower())
        plan[case] = {
            "database": f"a2flow_mgmt_{index}_{invocation_id[:12]}",
            "namespace": f"a2flow-accept-{token}-{invocation_id}",
            "fixtureId": invocation_id,
        }
    return plan


def _create_databases(socket_directory, password, plan):
    from psycopg import connect, sql

    with connect(
            _conninfo(socket_directory, "postgres", password),
            autocommit=True) as connection:
        for item in plan.values():
            name = item["database"]
            existing = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone()
            if existing is not None:
                raise RuntimeError("FIXTURE_DATABASE_ALREADY_EXISTS")
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    for item in plan.values():
        with connect(_conninfo(socket_directory, item["database"], password)) as connection:
            connection.execute(
                "CREATE TABLE a2flow_acceptance_fixture "
                "(fixture_id text PRIMARY KEY, namespace text NOT NULL)")
            connection.execute(
                "INSERT INTO a2flow_acceptance_fixture(fixture_id, namespace) VALUES (%s, %s)",
                (item["fixtureId"], item["namespace"]))


def _acquire_container_id(ownership, cidfile):
    if not cidfile.is_file():
        return
    container_id = cidfile.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
        raise RuntimeError("CONTAINER_ID_INVALID")
    ownership.container_id = container_id


def _container_matches(observed, ownership):
    labels = observed.get("Config", {}).get("Labels") or {}
    return (
        observed.get("Id") == ownership.container_id
        and observed.get("Name") == "/" + ownership.container_name
        and labels.get("a2flow.owner") == OWNER
        and labels.get("a2flow.invocation") == ownership.invocation_id
    )


def _cleanup(ownership):
    errors = []
    container_safe = not ownership.creation_attempted
    if ownership.creation_attempted and ownership.container_id is None:
        errors.append("CONTAINER_CREATION_UNCONFIRMED")
    elif ownership.container_id is not None:
        try:
            observed = _inspect(ownership.container_id)
        except subprocess.TimeoutExpired:
            errors.append("CONTAINER_INSPECTION_TIMEOUT")
        except OSError:
            errors.append("CONTAINER_INSPECTION_OS_ERROR")
        except RuntimeError as error:
            errors.append(_sanitized_cleanup_error(error))
        else:
            if not _container_matches(observed, ownership):
                errors.append("CONTAINER_OWNERSHIP_MISMATCH")
            else:
                try:
                    removed = _docker(
                        "rm", "--force", ownership.container_id, check=False)
                except subprocess.TimeoutExpired:
                    errors.append("CONTAINER_REMOVE_TIMEOUT")
                except OSError:
                    errors.append("CONTAINER_REMOVE_OS_ERROR")
                else:
                    if removed.returncode:
                        errors.append("CONTAINER_REMOVE_FAILED")
                    else:
                        container_safe = True
    directory = ownership.directory
    if directory is not None and directory.exists():
        try:
            marker = directory / ".owner"
            directory_owned = (
                not directory.is_symlink() and marker.is_file()
                and marker.read_text(encoding="ascii") == ownership.invocation_id
            )
        except (OSError, UnicodeError):
            errors.append("FIXTURE_DIRECTORY_INSPECTION_FAILED")
        else:
            if not directory_owned:
                errors.append("FIXTURE_DIRECTORY_OWNERSHIP_MISMATCH")
            elif container_safe:
                try:
                    shutil.rmtree(directory)
                except OSError:
                    errors.append("FIXTURE_DIRECTORY_REMOVE_FAILED")
    return errors


def _sanitized_cleanup_error(error):
    allowed = {"CONTAINER_INSPECTION_FAILED"}
    return str(error) if str(error) in allowed else "CONTAINER_CLEANUP_FAILED"


def _record_cleanup(result, errors, ownership=None):
    result["cleanup"] = "FAIL" if errors else "PASS"
    if errors:
        result["status"] = "FAILED"
        result["cleanupErrors"] = errors
        if ownership is not None:
            recovery = {
                "invocationId": ownership.invocation_id,
                "containerName": ownership.container_name,
            }
            if ownership.container_id is not None:
                recovery["containerId"] = ownership.container_id
            if ownership.directory is not None and ownership.directory.exists():
                recovery["fixtureDirectory"] = str(ownership.directory)
            result["recovery"] = recovery


def _pythonpath(root):
    paths = (
        "packages/contracts/src",
        "packages/asset-store/src",
        "services/skill-registry/src",
        "services/capability-registry/src",
        "services/a2ui-composer/src",
        "services/workflow-composer/src",
        "services/management-api/src",
        "examples/activity-planning",
    )
    return os.pathsep.join(str(root / path) for path in paths)


def _test_environment(root, plan_file, password_file):
    environment = {}
    for name in ("PATH", "HOME", "TMPDIR", "SYSTEMROOT", "WINDIR"):
        if name in os.environ:
            environment[name] = os.environ[name]
    environment.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": _pythonpath(root),
        "A2FLOW_MANAGEMENT_PG_REQUIRED": "1",
        "A2FLOW_MANAGEMENT_PG_FIXTURE_PLAN": str(plan_file),
        "A2FLOW_MANAGEMENT_PG_PASSWORD_FILE": str(password_file),
    })
    return environment


def _test_evidence(stdout, stderr, returncode):
    text = stdout + "\n" + stderr
    match = re.search(r"Ran (\d+) tests?", text)
    if match is None or int(match.group(1)) == 0:
        raise RuntimeError("POSTGRES_NO_TESTS_EXECUTED")
    if re.search(r"skipped\s*=\s*[1-9]", text, re.IGNORECASE):
        raise RuntimeError("POSTGRES_TESTS_SKIPPED")
    failures = sorted(set(re.findall(r"^(test[^ ]+) .*\.\.\. (?:FAIL|ERROR)$", text, re.MULTILINE)))
    return {
        "testCount": int(match.group(1)),
        "failingCaseIds": failures,
        "testExitCode": returncode,
    }


def _sanitized_error(error):
    allowed = {
        "PYTHON_DEPENDENCIES_REQUIRED", "REMOTE_DOCKER_ENDPOINT_REJECTED",
        "DOCKER_CONTEXT_INSPECTION_FAILED", "DOCKER_CLI_REQUIRED",
        "DOCKER_DAEMON_REQUIRED", "CACHED_POSTGRES_IMAGE_REQUIRED",
        "FIXTURE_CONTAINER_ALREADY_EXISTS", "CONTAINER_NAME_CHECK_FAILED",
        "CONTAINER_ID_INVALID",
        "CONTAINER_INSPECTION_FAILED", "CONTAINER_OWNERSHIP_MISMATCH",
        "FIXTURE_ISOLATION_MISMATCH", "POSTGRES_NOT_READY",
        "FIXTURE_DATABASE_ALREADY_EXISTS", "POSTGRES_ACCEPTANCE_TIMEOUT",
        "POSTGRES_NO_TESTS_EXECUTED", "POSTGRES_TESTS_SKIPPED",
        "POSTGRES_ACCEPTANCE_FAILED", "DOCKER_RUN_TIMEOUT", "DOCKER_RUN_OS_ERROR",
    }
    return str(error) if str(error) in allowed else type(error).__name__


def run(output_directory):
    root = Path(__file__).resolve().parents[2]
    output = _safe_output(output_directory)
    invocation_id = secrets.token_hex(16)
    ownership = FixtureOwnership(
        invocation_id=invocation_id,
        container_name=PREFIX + invocation_id[:12],
    )
    result = {
        "schemaVersion": 1,
        "status": "NOT_RUN",
        "configuration": "NOT_RUN",
        "unit": "NOT_RUN",
        "postgres": "NOT_RUN",
        "browser": "NOT_RUN",
        "deployment": "NOT_RUN",
    }
    primary_error = None
    postgres_attempted = False
    try:
        _check_python_dependencies()
        if os.environ.get("DOCKER_HOST", "").startswith(("tcp://", "ssh://", "http://", "https://")):
            raise RuntimeError("REMOTE_DOCKER_ENDPOINT_REJECTED")
        if shutil.which("docker") is None:
            raise RuntimeError("DOCKER_CLI_REQUIRED")
        _check_local_docker_endpoint()
        daemon = _docker("info", "--format", "{{json .ServerVersion}}", check=False)
        if daemon.returncode != 0:
            raise RuntimeError("DOCKER_DAEMON_REQUIRED")
        image = _docker("image", "inspect", IMAGE, check=False)
        if image.returncode != 0:
            raise RuntimeError("CACHED_POSTGRES_IMAGE_REQUIRED")
        _require_unused_container_name(ownership.container_name)
        ownership.directory = Path(tempfile.mkdtemp(prefix=PREFIX))
        ownership.directory.chmod(0o700)
        (ownership.directory / ".owner").write_text(invocation_id, encoding="ascii")
        (ownership.directory / ".owner").chmod(0o600)
        socket_directory = ownership.directory / "socket"
        socket_directory.mkdir(mode=0o777)
        socket_directory.chmod(0o777)
        password = secrets.token_urlsafe(36)
        password_file = _write_secret(
            ownership.directory, "postgres_password", password)
        result["configuration"] = "PASS"
        result["containerName"] = ownership.container_name
        cidfile = ownership.directory / "container.cid"
        ownership.creation_attempted = True
        try:
            try:
                _docker(
                    "run", "--detach", "--pull=never", "--cidfile", str(cidfile),
                    "--name", ownership.container_name,
                    "--label", "a2flow.owner=" + OWNER,
                    "--label", "a2flow.invocation=" + invocation_id,
                    "--network", "none", "--restart", "no", "--memory", "256m",
                    "--memory-swap", "256m", "--cpus", "0.5", "--pids-limit", "128",
                    "--shm-size", "32m",
                    "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=256m",
                    "--mount", "type=bind,src=" + str(socket_directory)
                    + ",dst=/var/run/postgresql",
                    "--mount", "type=bind,src=" + str(password_file)
                    + ",dst=/run/secrets/postgres_password,readonly",
                    "--env", "POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password",
                    "--env", "POSTGRES_USER=postgres", "--env", "POSTGRES_DB=postgres",
                    "--env", "POSTGRES_INITDB_ARGS=--auth-local=scram-sha-256 --auth-host=scram-sha-256",
                    IMAGE, "-c", "listen_addresses=", "-c", "max_connections=16",
                    "-c", "shared_buffers=32MB", "-c", "log_statement=none",
                )
            except subprocess.TimeoutExpired as error:
                raise RuntimeError("DOCKER_RUN_TIMEOUT") from error
            except OSError as error:
                raise RuntimeError("DOCKER_RUN_OS_ERROR") from error
        finally:
            _acquire_container_id(ownership, cidfile)
        if ownership.container_id is None:
            raise RuntimeError("CONTAINER_ID_INVALID")
        observed = _inspect(ownership.container_id)
        if not _container_matches(observed, ownership):
            raise RuntimeError("CONTAINER_OWNERSHIP_MISMATCH")
        host = observed.get("HostConfig", {})
        if (host.get("NetworkMode") != "none"
                or observed.get("NetworkSettings", {}).get("Ports")
                or host.get("Memory") != 256 * 1024 * 1024
                or host.get("MemorySwap") != host.get("Memory")):
            raise RuntimeError("FIXTURE_ISOLATION_MISMATCH")
        version = _wait(socket_directory, password)
        plan = _fixture_plan(invocation_id)
        _create_databases(socket_directory, password, plan)
        plan_file = ownership.directory / "fixture-plan.json"
        descriptor = os.open(plan_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"socket": str(socket_directory), "cases": plan}, stream)
        postgres_attempted = True
        try:
            test = _run(
                [sys.executable,
                 str(root / "services/management-api/tests/test_postgres_integration.py"),
                 "-v"],
                timeout=300, check=False,
                environment=_test_environment(root, plan_file, password_file),
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("POSTGRES_ACCEPTANCE_TIMEOUT") from error
        evidence = _test_evidence(test.stdout, test.stderr, test.returncode)
        result.update(evidence)
        result["serverMajor"] = version.split(".", 1)[0]
        result["postgres"] = "PASS" if test.returncode == 0 else "FAIL"
        result["status"] = "VERIFIED" if test.returncode == 0 else "FAILED"
        if test.returncode:
            raise RuntimeError("POSTGRES_ACCEPTANCE_FAILED")
    except Exception as error:
        primary_error = error
        result["error"] = _sanitized_error(error)
        if postgres_attempted:
            result["postgres"] = "FAIL"
            result["status"] = "FAILED"
        elif ownership.creation_attempted:
            result["status"] = "FAILED"
        elif result["postgres"] != "FAIL":
            result["status"] = "NOT_RUN"
    finally:
        try:
            cleanup_errors = _cleanup(ownership)
        except subprocess.TimeoutExpired:
            cleanup_errors = ["CLEANUP_TIMEOUT"]
        except OSError:
            cleanup_errors = ["CLEANUP_OS_ERROR"]
        except Exception:
            cleanup_errors = ["CLEANUP_FAILED"]
        _record_cleanup(result, cleanup_errors, ownership)
        report = output / "management-acceptance.json"
        descriptor = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(result, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    if primary_error is not None or cleanup_errors:
        raise RuntimeError("ACCEPTANCE_FAILED")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorized-isolated-fixture", action="store_true")
    parser.add_argument("--output-directory", required=True)
    arguments = parser.parse_args(argv)
    if not arguments.authorized_isolated_fixture:
        print(json.dumps({
            "schemaVersion": 1, "status": "NOT_RUN",
            "error": "EXPLICIT_FIXTURE_OPT_IN_REQUIRED",
        }, sort_keys=True, separators=(",", ":")))
        return 2
    try:
        run(arguments.output_directory)
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
