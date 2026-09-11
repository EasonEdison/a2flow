"""Single explicitly authorized isolated PG window; no deployment or auto-start.

Run only as admin after main-brain grants this exact window. --cleanup performs
only verified task-owned cleanup. --help is read-only. No credential CLI values.
"""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time

from runtime_phase1.postgres_parallel_probe import bootstrap_probe_database, _connection_string


CONTAINER = "a2flow-runtime03-pg"
VOLUME = "a2flow-runtime03-pgdata"
PRIVATE = Path("/home/admin/OpenSource/.tmp/af-runtime-03-pg")
IMAGE = "public.ecr.aws/docker/library/postgres@sha256:7bade6d532592ca8ce7ee32def7399dad2607c4ea5583839fc4352a095a11ea6"
LABEL = "a2flow.owner=oss-agent-workflow-runtime-af03"
REPO = Path("/home/admin/OpenSource/repos/.parallel/oss-agent-workflow-runtime/platform")
OWNER = "oss-agent-workflow-runtime-af03"
PYTHON = "/home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python"


@dataclass(frozen=True)
class WindowSpec:
    """Explicit task-owned targets; shared safety implementation, no global mutation."""
    container: str
    volume: str
    private: Path
    owner: str
    env_prefix: str
    test_pattern: str


def window_spec(window=None):
    # Resolve defaults at call time to preserve AF03 injected-fault fixtures.
    return window if window is not None else WindowSpec(
        CONTAINER, VOLUME, PRIVATE, OWNER, "A2FLOW_RUNTIME03", "test_postgres_integration.py",
    )


def command(args, *, timeout=30, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        # Never expose Docker/bootstrap arbitrary output or file contents.
        raise RuntimeError("controlled command failed")
    return result


def docker(*args, **kwargs):
    return command(["sudo", "-n", "docker", *args], **kwargs)


def inspect(kind, name):
    result = docker(kind, "inspect", name, check=False)
    if not result.returncode:
        return json.loads(result.stdout)[0]
    # Exact Docker 26.1.3 responses verified against these absent owned targets.
    # Any daemon/permission/transport error is UNKNOWN, never absence evidence.
    absent = {
        "container": "Error response from daemon: No such container: " + name,
        "volume": "Error response from daemon: get " + name + ": no such volume",
        "image": "Error response from daemon: No such image: " + name,
    }
    if (result.returncode == 1 and result.stderr.strip() == absent.get(kind)
            and result.stdout.strip() in {"", "[]"}):
        return None
    raise RuntimeError("RESOURCE_INSPECTION_UNKNOWN")


def private_file(name, value, *, window=None):
    path = window_spec(window).private / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(value)
    return path


def memory():
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value, *_ = line.split()
        values[key.rstrip(":")] = int(value)
    return values["MemAvailable"], values["SwapTotal"] - values["SwapFree"]


def owned_private(*, window=None):
    spec = window_spec(window)
    PRIVATE, OWNER = spec.private, spec.owner
    return (not PRIVATE.is_symlink() and PRIVATE.resolve() == PRIVATE
            and (PRIVATE / ".owner").read_text() == OWNER)


def cleanup(*, window=None):
    spec = window_spec(window)
    CONTAINER, VOLUME, PRIVATE, OWNER = spec.container, spec.volume, spec.private, spec.owner
    # Validate all resources BEFORE removing any. Missing targets are idempotent.
    container, volume = inspect("container", CONTAINER), inspect("volume", VOLUME)
    if container and container["Config"]["Labels"].get("a2flow.owner") != OWNER:
        raise RuntimeError("container ownership mismatch")
    if volume and volume["Labels"].get("a2flow.owner") != OWNER:
        raise RuntimeError("volume ownership mismatch")
    if PRIVATE.exists() and not owned_private(window=window):
        raise RuntimeError("private directory ownership mismatch")
    image_owned = PRIVATE.exists() and (PRIVATE / ".image-owned").exists()
    if container:
        docker("stop", "--time", "5", CONTAINER, check=False)
        docker("rm", CONTAINER)
    if volume:
        docker("volume", "rm", VOLUME)
    image_removed = False
    if image_owned:
        image_removed = docker("image", "rm", IMAGE, check=False).returncode == 0
    if PRIVATE.exists():
        socket = PRIVATE / "socket"
        if socket.is_symlink():
            socket.unlink()  # Remove only the link, never follow it.
        elif socket.exists():
            try:
                shutil.rmtree(socket)
            except PermissionError:
                # PG may own/chmod this bind mount. Only the validated exact socket
                # subtree may use privileged deletion, after the container is gone.
                if socket.is_symlink() or socket.resolve() != PRIVATE / "socket":
                    raise RuntimeError("socket cleanup target changed") from None
                command(["sudo", "-n", "rm", "-r", "--one-file-system", "--", str(socket)])
            if socket.exists():
                raise RuntimeError("CLEANUP_SOCKET_RESIDUAL")
        shutil.rmtree(PRIVATE)  # Exact validated task dir, never its parent.
    if inspect("container", CONTAINER) or inspect("volume", VOLUME) or PRIVATE.exists():
        raise RuntimeError("cleanup verification failed")
    print(json.dumps({"cleanup": "verified", "container": CONTAINER, "volume": VOLUME,
                      "privateDirectory": str(PRIVATE), "ownedImageRemoved": image_removed,
                      "secureEraseClaim": False}), flush=True)


def check_budget(started, initial_swap, volume_path):
    available, swap = memory()
    if time.monotonic() - started >= 900 or available < 512 * 1024 or swap - initial_swap > 128 * 1024:
        raise RuntimeError("window resource/time stop threshold")
    size = command(["sudo", "-n", "du", "-sk", volume_path]).stdout.split()[0]
    if int(size) > 1024 * 1024:
        raise RuntimeError("window data size stop threshold")
    return available, swap, int(size)


def group_members(group_id, marker, *, window=None):
    """Validate every live group member using the unique inherited window marker."""
    members = []
    expected = (window_spec(window).env_prefix + "_WINDOW_ID=" + marker).encode()
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = path.read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) != group_id or int(fields[3]) != group_id or fields[0] == "Z":
                continue
            environment = path.with_name("environ").read_bytes().split(b"\0")
            if expected not in environment or path.stat().st_uid != os.getuid():
                raise RuntimeError("process group ownership mismatch")
            members.append(int(path.parent.name))
        except FileNotFoundError:
            continue
    return members


def stop_owned_group(child, marker, *, window=None):
    if child is None:
        return
    # start_new_session=True made pid both the group and session ID. The unique
    # inherited marker protects against PID/group reuse after the parent exits.
    for signum in (signal.SIGTERM, signal.SIGKILL):
        if group_members(child.pid, marker, window=window):
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            continue
        if not group_members(child.pid, marker, window=window):
            return
    if group_members(child.pid, marker, window=window) or child.poll() is None:
        raise RuntimeError("OWNED_TEST_PROCESS_RESIDUAL")


def credential_log_check(passwords, *, window=None):
    spec = window_spec(window)
    CONTAINER, OWNER = spec.container, spec.owner
    container = inspect("container", CONTAINER)
    if container is None:
        print(json.dumps({"credentialLogCheck": "NOT_RUN", "reason": "container absent"}), flush=True)
        return
    if container["Config"]["Labels"].get("a2flow.owner") != OWNER:
        raise RuntimeError("credential log target ownership mismatch")
    captured = docker("logs", CONTAINER, check=False)
    passed = bool(passwords) and captured.returncode == 0 and not any(
        password in captured.stdout or password in captured.stderr for password in passwords
    )
    print(json.dumps({"credentialLogCheck": "PASS" if passed else "FAIL"}), flush=True)
    if not passed:
        raise RuntimeError("CREDENTIAL_LOG_CHECK_FAILED")


def finish_window(child, marker, passwords, *, window=None):
    try:
        stop_owned_group(child, marker, window=window)
    finally:
        try:
            credential_log_check(passwords, window=window)
        finally:
            # Even process/log checks failing must attempt resource cleanup.
            cleanup(window=window)


def run_window(*, window=None):
    spec = window_spec(window)
    CONTAINER, VOLUME, PRIVATE, OWNER = spec.container, spec.volume, spec.private, spec.owner
    LABEL = "a2flow.owner=" + OWNER
    if os.getuid() == 0 or command(["id", "-un"]).stdout.strip() != "admin":
        raise RuntimeError("run as project owner admin")
    if inspect("container", CONTAINER) or inspect("volume", VOLUME) or PRIVATE.exists() or PRIVATE.is_symlink():
        raise RuntimeError("exact targets must all be absent before start")
    available, initial_swap = memory()
    if available < 768 * 1024:
        raise RuntimeError("less than 768 MiB available before start")
    image_existed = inspect("image", IMAGE) is not None
    # Preparation and the active PG lifetime share the same bounded window.
    started = time.monotonic()
    if PRIVATE.parent.is_symlink() or PRIVATE.parent.resolve() != PRIVATE.parent:
        raise RuntimeError("private parent path mismatch")
    PRIVATE.parent.mkdir(mode=0o700, exist_ok=True)
    PRIVATE.mkdir(mode=0o700, parents=False)
    private_file(".owner", OWNER, window=window)
    child = None
    window_marker = secrets.token_hex(16)
    passwords = []
    minimum_memory, maximum_swap, maximum_data = available, initial_swap, 0
    try:
        if not image_existed:
            private_file(".image-owned", "true", window=window)
            docker("pull", IMAGE, timeout=120)
        image = inspect("image", IMAGE)
        if image["Architecture"] != "amd64":
            raise RuntimeError("image architecture mismatch")
        admin_password, probe_password = secrets.token_urlsafe(36), secrets.token_urlsafe(36)
        passwords = [admin_password, probe_password]
        admin_file = private_file("admin_password", admin_password, window=window)
        probe_file = private_file("probe_password", probe_password, window=window)
        container_file = private_file("container_password", admin_password, window=window)
        # Fixed Debian PostgreSQL image uses postgres UID/GID 999; no host account change.
        command(["sudo", "-n", "chown", "999:999", str(container_file)])
        socket = PRIVATE / "socket"
        socket.mkdir(mode=0o777)
        socket.chmod(0o777)  # Parent is admin-only 0700; no public socket reachability.
        docker("volume", "create", "--label", LABEL, VOLUME)
        docker("run", "-d", "--name", CONTAINER, "--label", LABEL,
               "--network", "none", "--restart", "no",
               "--memory", "256m", "--memory-swap", "256m", "--cpus", "0.5",
               "--pids-limit", "128", "--shm-size", "32m",
               "--mount", "type=volume,src=" + VOLUME + ",dst=/var/lib/postgresql/data",
               "--mount", "type=bind,src=" + str(socket) + ",dst=/var/run/postgresql",
               "--mount", "type=bind,src=" + str(container_file) + ",dst=/run/secrets/admin_password,readonly",
               "-e", "POSTGRES_USER=runtime_admin", "-e", "POSTGRES_DB=runtime_admin",
               "-e", "POSTGRES_PASSWORD_FILE=/run/secrets/admin_password",
               "-e", "POSTGRES_INITDB_ARGS=--auth-local=scram-sha-256 --auth-host=scram-sha-256",
               IMAGE, "-c", "listen_addresses=", "-c", "max_connections=16",
               "-c", "shared_buffers=32MB", "-c", "log_statement=none")
        container = inspect("container", CONTAINER)
        host = container["HostConfig"]
        if (host["NetworkMode"] != "none" or container["NetworkSettings"]["Ports"]
                or host["Memory"] != 256 * 1024 * 1024 or host["MemorySwap"] != host["Memory"]):
            raise RuntimeError("container isolation readback mismatch")
        volume_path = inspect("volume", VOLUME)["Mountpoint"]
        deadline = time.monotonic() + 60
        import psycopg
        while True:
            check_budget(started, initial_swap, volume_path)
            try:
                with psycopg.connect(_connection_string(socket, admin_file,
                                     database="runtime_admin", user="runtime_admin"),
                                     autocommit=True) as conn:
                    version = conn.execute("SHOW server_version").fetchone()[0]
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError("PG not ready within 60 seconds") from None
                time.sleep(.5)
        if not version.startswith("17.11"):
            raise RuntimeError("unexpected PostgreSQL version")
        bootstrap_probe_database(socket, admin_file, probe_file, connection_limit=8)
        with psycopg.connect(_connection_string(socket, probe_file), autocommit=True) as conn:
            role = conn.execute("""SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolconnlimit
                FROM pg_roles WHERE rolname=current_user""").fetchone()
            if role != (False, False, False, False, 8):
                raise RuntimeError("runtime role safety readback mismatch")
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
            LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false", LANGCHAIN_TRACING="false",
            PYTHONPATH="packages/contracts/src:services/agent-workflow-runtime/src:"
                       "services/agent-workflow-runtime/tests:services/skill-registry/src:"
                       "experiments/runtime-phase1:experiments/runtime-phase1/tests")
        environment.update({
            spec.env_prefix + "_WINDOW_ID": window_marker,
            spec.env_prefix + "_SOCKET": str(socket),
            spec.env_prefix + "_PASSWORD_FILE": str(probe_file),
        })
        child = subprocess.Popen([PYTHON, "-m", "unittest", "discover",
                                  "-s", "services/agent-workflow-runtime/tests",
                                  "-p", spec.test_pattern, "-v"],
                                 cwd=REPO, env=environment, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, start_new_session=True)
        while True:
            available, swap, data = check_budget(started, initial_swap, volume_path)
            minimum_memory = min(minimum_memory, available)
            maximum_swap = max(maximum_swap, swap)
            maximum_data = max(maximum_data, data)
            try:
                stdout, stderr = child.communicate(timeout=.5)
                break
            except subprocess.TimeoutExpired:
                continue
        for password in passwords:
            stdout, stderr = stdout.replace(password, "[REDACTED]"), stderr.replace(password, "[REDACTED]")
        print(stdout, end="", flush=True)
        print(stderr, end="", flush=True)
        with psycopg.connect(_connection_string(socket, admin_file,
                             database="runtime_admin", user="runtime_admin"), autocommit=True) as conn:
            sessions = conn.execute("SELECT count(*) FROM pg_stat_activity WHERE usename='runtime_probe'").fetchone()[0]
            locks = conn.execute("SELECT count(*) FROM pg_locks WHERE locktype='advisory'").fetchone()[0]
        print(json.dumps({"serverVersion": version, "minAvailableKiB": minimum_memory,
                          "maxSwapGrowthKiB": maximum_swap - initial_swap,
                          "maxDataKiB": maximum_data, "remainingRuntimeSessions": sessions,
                          "remainingAdvisoryLocks": locks, "publishedPorts": {},
                          "elapsedSeconds": round(time.monotonic() - started, 2)}), flush=True)
        if child.returncode or sessions or locks:
            raise RuntimeError("PG acceptance or connection cleanup failed")
    finally:
        finish_window(child, window_marker, passwords, window=window)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--authorized-window", action="store_true",
                       help="requires explicit main-brain release; this flag is not authorization")
    group.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    try:
        cleanup() if args.cleanup else run_window()
    except Exception as error:
        print(json.dumps({"window": "failed", "errorType": type(error).__name__,
                          "details": "redacted; inspect bounded safe evidence"}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
