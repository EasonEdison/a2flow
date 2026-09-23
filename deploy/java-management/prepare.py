"""Explicit new management DB/config preparation; never migrate legacy assets.

Run as the deployment owner inside the reviewed Python image with the existing
PostgreSQL socket and private secrets mounted. Back up existing databases first.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo


def write_private(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content)


def env_file(path: Path, values: dict[str, str]) -> None:
    if any("'" in value or "\n" in value for value in values.values()):
        raise ValueError("INVALID_ENV_VALUE")
    write_private(path, "".join(f"{key}='{value}'\n" for key, value in values.items()))


def prepare(directory: Path, origin: str) -> None:
    if not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_DIRECTORY_REQUIRED")
    if (directory / "java.env").exists():
        raise ValueError("CONFIG_ALREADY_EXISTS_NO_OVERWRITE")
    password = Path("/run/secrets/app_postgres_password").read_text().strip()
    connection = make_conninfo(host="/run/postgresql", user="a2flow_realchat",
                              dbname="postgres", password=password)
    management_password, account_password, bridge_token = (secrets.token_urlsafe(32) for _ in range(3))
    with psycopg.connect(connection, autocommit=True) as database:
        if database.execute("SELECT 1 FROM pg_database WHERE datname='a2flow_java_management'").fetchone():
            raise ValueError("MANAGEMENT_DATABASE_ALREADY_EXISTS")
        if database.execute("SELECT 1 FROM pg_roles WHERE rolname IN ('a2flow_java_owner','a2flow_java_accounts')").fetchone():
            raise ValueError("DEPLOYMENT_ROLE_ALREADY_EXISTS")
        # Keep recovery material before side effects; a partial run is never rerun blindly.
        write_private(directory / "new-role-credentials.json", json.dumps({
            "management": management_password, "accounts": account_password}))
        for name, secret in (("a2flow_java_owner", management_password), ("a2flow_java_accounts", account_password)):
            database.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(name), sql.Literal(secret)))
        database.execute("ALTER ROLE a2flow_java_accounts SET default_transaction_read_only=on")
        database.execute("CREATE DATABASE a2flow_java_management OWNER a2flow_java_owner")
    account_dsn = make_conninfo(connection, dbname="a2flow_realchat_prt")
    with psycopg.connect(account_dsn) as database:
        database.execute("GRANT CONNECT ON DATABASE a2flow_realchat_prt TO a2flow_java_accounts")
        database.execute("GRANT USAGE ON SCHEMA public TO a2flow_java_accounts")
        database.execute("GRANT SELECT ON public.users, public.sessions TO a2flow_java_accounts")
    jdbc_suffix = "?socketFactory=org.newsclub.net.unix.AFUNIXSocketFactory%24FactoryArg&socketFactoryArg=/run/postgresql/.s.PGSQL.5432&sslmode=disable"
    env_file(directory / "java.env", {
        "A2FLOW_ENVIRONMENT": "PRT", "A2FLOW_MANAGEMENT_NAMESPACE": "a2flow-management",
        "A2FLOW_MANAGEMENT_JDBC_URL": "jdbc:postgresql://localhost/a2flow_java_management" + jdbc_suffix,
        "A2FLOW_MANAGEMENT_DB_USER": "a2flow_java_owner", "A2FLOW_MANAGEMENT_DB_PASSWORD": management_password,
        "A2FLOW_MANAGEMENT_DB_POOL_SIZE": "3",
        "A2FLOW_ACCOUNT_JDBC_URL": "jdbc:postgresql://localhost/a2flow_realchat_prt" + jdbc_suffix,
        "A2FLOW_ACCOUNT_DB_USER": "a2flow_java_accounts", "A2FLOW_ACCOUNT_DB_PASSWORD": account_password,
        "A2FLOW_ACCOUNT_DB_POOL_SIZE": "2", "A2FLOW_MANAGEMENT_CONFIG": "/run/a2flow/management.json",
        "A2FLOW_MANAGEMENT_PORT": "8790", "A2FLOW_MANAGEMENT_STATIC_DIR": "/opt/management-static",
        "A2FLOW_MANAGEMENT_BROWSER_ORIGINS": origin, "A2FLOW_ACCOUNT_LOGIN_ORIGIN": "http://127.0.0.1:8780",
        "A2FLOW_PUBLICATION_BRIDGE_URL": "http://127.0.0.1:8792", "A2FLOW_PUBLICATION_BRIDGE_TOKEN": bridge_token,
        "A2FLOW_RUNTIME_RPC_MODE": "MTLS", "A2FLOW_RUNTIME_RPC_PORT": "8793",
        "A2FLOW_RUNTIME_RPC_CERT_FILE": "/run/a2flow/rpc/server.pem",
        "A2FLOW_RUNTIME_RPC_KEY_FILE": "/run/a2flow/rpc/server-key.pem",
        "A2FLOW_RUNTIME_RPC_ENGINE_CA_FILE": "/run/a2flow/rpc/ca.pem",
        "A2FLOW_CAPABILITY_GRPC_TARGETS_JSON": "{}",
    })
    publication = {"A2FLOW_PUBLICATION_VALIDATOR_FACTORY": "deploy.assets:bundle_validator",
                   "A2FLOW_PUBLICATION_BRIDGE_PORT": "8792", "A2FLOW_PUBLICATION_BRIDGE_TOKEN": bridge_token}
    for environment in ("PRT", "ONLINE"):
        name = "a2flow_realchat_" + environment.lower()
        publication.update({f"A2FLOW_PUBLICATION_{environment}_DATABASE": name,
                            f"A2FLOW_PUBLICATION_{environment}_DSN": make_conninfo(connection, dbname=name),
                            f"A2FLOW_PUBLICATION_{environment}_NAMESPACE": "a2flow-mvp-activity-planning"})
    env_file(directory / "publication.env", publication)
    env_file(directory / "bside.env", {
        "A2FLOW_ENVIRONMENT": "PRT", "A2FLOW_DATABASE_NAME": "a2flow_realchat_prt",
        "A2FLOW_DATABASE_USER": "a2flow_realchat", "A2FLOW_POSTGRES_PASSWORD_FILE": "/run/secrets/app_postgres_password",
        "A2FLOW_ASSET_NAMESPACE": "a2flow-mvp-activity-planning", "A2FLOW_USER_ID": "101",
        "A2FLOW_DEEPSEEK_KEY_FILE": "/run/secrets/deepseek_key", "A2FLOW_PEPPER_FILE": "/run/secrets/pepper",
        "A2FLOW_INTERNAL_TOKEN_FILE": "/run/secrets/internal_token", "A2FLOW_LISTEN_PORT": "8785",
        "A2FLOW_BSIDE_DATABASE_NAME": "a2flow_realchat_prt", "A2FLOW_BSIDE_ENVIRONMENT": "PRT",
        "A2FLOW_BSIDE_ASSET_NAMESPACE": "a2flow-mvp-activity-planning",
        "A2FLOW_BSIDE_VALIDATOR_FACTORY": "deploy.assets:bundle_validator",
        "A2FLOW_BSIDE_BROWSER_ORIGIN": origin, "A2FLOW_BSIDE_BROWSER_ORIGINS": origin,
        "A2FLOW_BSIDE_SESSION_SECONDS": "7200", "A2FLOW_BSIDE_RUNTIME_URL": "http://127.0.0.1:8782",
        "A2FLOW_EMPLOYEE_STATIC_DIRECTORY": "/opt/a2flow/static/employee",
        "A2FLOW_ENGINE_RPC_TARGET": "127.0.0.1:8793", "A2FLOW_ENGINE_RPC_MODE": "MTLS",
        "A2FLOW_ENGINE_RPC_CA_FILE": "/run/a2flow-rpc/ca.pem",
        "A2FLOW_ENGINE_RPC_CERT_FILE": "/run/a2flow-rpc/engine.pem",
        "A2FLOW_ENGINE_RPC_KEY_FILE": "/run/a2flow-rpc/engine-key.pem",
    })
    write_private(directory / "management.json", json.dumps({"workspaceRoot": "/tmp/skill-projection",
        "workspaceChangeGuard": {}, "pages": {"HADES_SKILL_FACTORY": {
            "specialists": [{"id": "101", "name": "通用数字员工", "digitalEmployeeId": "101"}],
            "businessDomains": [{"value": "general", "label": "通用业务"}],
            "capabilityDomains": [{"value": "general", "label": "通用能力"}]}}}, ensure_ascii=False))
    print("NEW_MANAGEMENT_DATABASE_AND_PRIVATE_CONFIG_PREPARED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-directory", type=Path, required=True)
    parser.add_argument("--browser-origin", required=True)
    options = parser.parse_args()
    prepare(options.private_directory, options.browser_origin)
