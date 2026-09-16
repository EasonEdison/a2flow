"""Container entry point for the PRT-only private management deployment."""

import json
import os
from pathlib import Path
import stat
import sys

from psycopg.conninfo import make_conninfo


def _required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_HOST_CONFIGURATION:" + name)
    return value


def _secret(name):
    path = Path(_required(name))
    descriptor = None
    try:
        if not path.is_absolute():
            raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        no_follow = getattr(os, "O_NOFOLLOW", None)
        if no_follow is None:
            raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name)
        descriptor = os.open(path, flags | no_follow)
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077):
            raise RuntimeError("SECRET_FILE_PERMISSIONS:" + name)
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            value = stream.read(4097).rstrip(b"\r\n")
    except RuntimeError:
        raise
    except OSError:
        raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (not value or len(value) > 4096
            or any(byte < 0x21 or byte > 0x7e for byte in value)):
        raise RuntimeError("SECRET_FILE_INVALID:" + name)
    return value.decode("ascii")


def _configure_database():
    environment = _required("A2FLOW_MANAGEMENT_ENVIRONMENT")
    if environment != "PRT":
        raise RuntimeError("MANAGEMENT_COMPOSE_PRT_ONLY")
    socket_directory = _required(
        "A2FLOW_MANAGEMENT_DATABASE_SOCKET_DIRECTORY")
    if not Path(socket_directory).is_absolute():
        raise RuntimeError("INVALID_MANAGEMENT_DATABASE_SOCKET_DIRECTORY")
    conninfo = make_conninfo(
        host=socket_directory,
        dbname=_required("A2FLOW_MANAGEMENT_DATABASE_NAME"),
        user=_required("A2FLOW_MANAGEMENT_DATABASE_USER"),
        password=_secret("A2FLOW_MANAGEMENT_POSTGRES_PASSWORD_FILE"),
    )
    os.environ["A2FLOW_MANAGEMENT_DATABASE_URL"] = conninfo
    return conninfo


def _initialize(conninfo):
    from a2flow_asset_store import PostgresAssetRepository
    from activity_planning_demo import bundle_validator
    from activity_planning_demo.package_bundle import make_package_bundle
    from a2flow_management import PostgresDraftRepository

    environment = _required("A2FLOW_MANAGEMENT_ENVIRONMENT")
    database = _required("A2FLOW_MANAGEMENT_DATABASE_NAME")
    namespace = _required("A2FLOW_MANAGEMENT_ASSET_NAMESPACE")
    validator = bundle_validator()
    document = make_package_bundle(environment)
    assets = PostgresAssetRepository(
        conninfo, environment=environment, database=database,
        validator=validator,
    )
    assets.setup()
    preview = assets.import_bundle(
        document, expected_namespace=namespace, dry_run=True)
    applied = assets.import_bundle(
        document, expected_namespace=namespace, dry_run=False)
    observed = assets.read(namespace)
    PostgresDraftRepository(
        conninfo, environment=environment, database=database).setup()
    print(json.dumps({
        "status": applied["status"],
        "dryRunStatus": preview["status"],
        "environment": environment,
        "namespace": namespace,
        "assetCount": len(observed.assets),
        "servingCount": len(observed.serving),
        "draftSchema": "INITIALIZED",
    }, sort_keys=True, separators=(",", ":")))


def _serve():
    raw_port = _required("A2FLOW_MANAGEMENT_LISTEN_PORT")
    try:
        port = int(raw_port)
    except ValueError:
        raise RuntimeError("INVALID_MANAGEMENT_LISTEN_PORT") from None
    if not 1024 <= port <= 65535 or str(port) != raw_port:
        raise RuntimeError("INVALID_MANAGEMENT_LISTEN_PORT")
    os.execvp("python", [
        "python", "-m", "uvicorn",
        "deploy.management.app:create_app_from_environment",
        "--factory", "--host", "127.0.0.1", "--port", raw_port,
        "--no-access-log",
    ])


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in (["serve"], ["initialize"]):
        raise RuntimeError("INVALID_MANAGEMENT_COMMAND")
    conninfo = _configure_database()
    if arguments == ["initialize"]:
        _initialize(conninfo)
    else:
        _serve()


if __name__ == "__main__":
    main()
