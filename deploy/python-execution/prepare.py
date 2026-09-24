"""Explicit additive PRT deployment preparation; no asset seed or account changes."""

from __future__ import annotations

import argparse
import json
import os
import secrets
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo


def write_private(path: Path, value: str) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(value)


def env_file(path: Path, values: dict[str, str]) -> None:
    if any("\n" in item or "'" in item for item in values.values()):
        raise ValueError("invalid environment configuration")
    write_private(path, "".join(f"{key}='{value}'\n" for key, value in values.items()))


def prepare(directory: Path) -> None:
    if not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise ValueError("owner-only private directory required")
    if any(directory.iterdir()):
        raise ValueError("preparation requires empty directory; never overwrite credentials")
    password = Path("/run/secrets/app_postgres_password").read_text().strip()
    base = make_conninfo(
        host="/run/postgresql", user="a2flow_realchat", dbname="postgres", password=password
    )
    content_password, execution_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with psycopg.connect(base, autocommit=True) as connection:
        if connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname IN "
            "('a2flow_content_owner','a2flow_execution_reader')"
        ).fetchone():
            raise ValueError("deployment roles already exist; inspect partial run")
        if connection.execute(
            "SELECT 1 FROM pg_database WHERE datname='a2flow_content_prt'"
        ).fetchone():
            raise ValueError("content database already exists")
        write_private(
            directory / "credentials.json",
            json.dumps({"content": content_password, "execution": execution_password}),
        )
        for role, value in (
            ("a2flow_content_owner", content_password),
            ("a2flow_execution_reader", execution_password),
        ):
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(value)
                )
            )
        connection.execute(
            "ALTER ROLE a2flow_execution_reader SET default_transaction_read_only=on"
        )
        connection.execute("CREATE DATABASE a2flow_content_prt OWNER a2flow_content_owner")
    for database, tables in (
        ("a2flow_java_management", ("skill_asset_release_state",)),
        ("a2flow_realchat_prt", ("a2flow_asset_versions", "a2flow_asset_environment")),
    ):
        with psycopg.connect(make_conninfo(base, dbname=database)) as connection:
            connection.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO a2flow_execution_reader").format(
                    sql.Identifier(database)
                )
            )
            connection.execute("GRANT USAGE ON SCHEMA public TO a2flow_execution_reader")
            for table in tables:
                connection.execute(
                    sql.SQL("GRANT SELECT ON {} TO a2flow_execution_reader").format(
                        sql.Identifier("public", table)
                    )
                )
    for filename, database, role, value in (
        ("content.dsn", "a2flow_content_prt", "a2flow_content_owner", content_password),
        ("management.dsn", "a2flow_java_management", "a2flow_execution_reader", execution_password),
        ("assets.dsn", "a2flow_realchat_prt", "a2flow_execution_reader", execution_password),
    ):
        write_private(
            directory / filename,
            make_conninfo(host="/run/postgresql", dbname=database, user=role, password=value),
        )
    common = {
        "CERT_FILE": "/run/a2flow/rpc/server.pem",
        "KEY_FILE": "/run/a2flow/rpc/server-key.pem",
        "CLIENT_CA_FILE": "/run/a2flow/rpc/ca.pem",
        "RPC_MODE": "MTLS",
    }
    env_file(
        directory / "execution.env",
        {
            **{f"A2FLOW_CAPABILITY_{key}": value for key, value in common.items()},
            "A2FLOW_CAPABILITY_DSN_FILE": "/run/a2flow/management.dsn",
            "A2FLOW_CAPABILITY_DATABASE": "a2flow_java_management",
            "A2FLOW_CAPABILITY_ENVIRONMENT": "PRT",
            "A2FLOW_CAPABILITY_TARGETS_FILE": "/run/a2flow/targets.json",
            "A2FLOW_CAPABILITY_BIND": "127.0.0.1:8794",
            "A2FLOW_RUNTIME_ASSET_DSN_FILE": "/run/a2flow/assets.dsn",
            "A2FLOW_RUNTIME_ASSET_DATABASE": "a2flow_realchat_prt",
            "A2FLOW_RUNTIME_ASSET_NAMESPACE": "a2flow-mvp-activity-planning",
        },
    )
    env_file(
        directory / "content.env",
        {
            **{f"A2FLOW_CONTENT_{key}": value for key, value in common.items()},
            "A2FLOW_CONTENT_DSN_FILE": "/run/a2flow/content.dsn",
            "A2FLOW_CONTENT_DATABASE": "a2flow_content_prt",
            "A2FLOW_CONTENT_ENVIRONMENT": "PRT",
            "A2FLOW_CONTENT_BIND": "127.0.0.1:8795",
        },
    )
    write_private(
        directory / "targets.json",
        json.dumps(
            {
                "content": {
                    "PRT": {
                        "host": "127.0.0.1",
                        "port": 8795,
                        "trustCertFile": "/run/a2flow/rpc/ca.pem",
                        "clientCertFile": "/run/a2flow/rpc/client.pem",
                        "clientKeyFile": "/run/a2flow/rpc/client-key.pem",
                    }
                }
            }
        ),
    )
    print("PRT_CONTENT_DATABASE_AND_READONLY_EXECUTION_ROLE_PREPARED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    prepare(parser.parse_args().directory)
