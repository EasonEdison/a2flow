"""Explicit empty-installation bootstrap. Never import assets or reset accounts."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]


def run(stage: str, config: dict[str, Any]) -> None:
    names, passwords = config["names"], config["passwords"]
    installation = config["installation"]
    def dsn(kind: str, role: str | None = None) -> str:
        role = role or kind
        return make_conninfo(host="/run/postgresql", dbname=names[kind], user=names[role], password=passwords[role])
    with psycopg.connect(dsn("bootstrap"), autocommit=True) as control:
        control.execute("SELECT pg_advisory_lock(7808102001)")
        exists = control.execute("SELECT to_regclass('public.selfhost_installation')").fetchone()[0]
        if not exists:
            if stage != "databases":
                raise ValueError("Initialize databases first")
            targets = [value for key, value in names.items() if key != "bootstrap"]
            if (control.execute("SELECT 1 FROM pg_roles WHERE rolname = ANY(%s)", (targets,)).fetchone()
                    or control.execute("SELECT 1 FROM pg_database WHERE datname = ANY(%s)", (targets,)).fetchone()):
                raise ValueError("Refusing to take over existing roles or databases")
            with control.transaction():
                control.execute("CREATE TABLE selfhost_installation(singleton boolean PRIMARY KEY CHECK(singleton), identity text NOT NULL, names jsonb NOT NULL, schemas_ready boolean NOT NULL DEFAULT false)")
                control.execute("INSERT INTO selfhost_installation(singleton, identity, names) VALUES(true,%s,%s)", (installation, Jsonb(names)))
        stored = control.execute("SELECT identity,names FROM selfhost_installation WHERE singleton").fetchone()
        if stored != (installation, names):
            raise ValueError("Installation identity does not match; preserve existing data")
        if stage == "databases":
            for kind, name in names.items():
                if kind == "bootstrap":
                    continue
                row = control.execute("SELECT shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=%s", (name,)).fetchone()
                if row is None:
                    with control.transaction():
                        control.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(name), sql.Literal(passwords[kind])))
                        control.execute(sql.SQL("COMMENT ON ROLE {} IS {}").format(sql.Identifier(name), sql.Literal(installation)))
                elif row[0] != installation:
                    raise ValueError("Role is not owned by this installation")
                if kind in {"reader", "accounts"}:
                    control.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only=on").format(sql.Identifier(name)))
                    continue
                row = control.execute("SELECT pg_get_userbyid(datdba),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=%s", (name,)).fetchone()
                if row is None:
                    control.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(name), sql.Identifier(name)))
                    control.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(name), sql.Literal(installation)))
                elif row[0] != name or row[1] not in {None, installation}:
                    raise ValueError("Database ownership does not match installation")
                # A crash between CREATE DATABASE and COMMENT is resumable because
                # the pre-existing installation record reserved this exact name/owner.
                control.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(name), sql.Literal(installation)))
                control.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name)))
            print("SELFHOST_DATABASES_READY (no assets imported)")
            return
        schemas(dsn, names, config)
        control.execute("UPDATE selfhost_installation SET schemas_ready=true WHERE singleton")
        print("SELFHOST_SCHEMAS_READY (existing administrator and business data preserved)")


def apply_file(conninfo: str, relative: str) -> None:
    body = (ROOT / relative).read_text()
    digest = sha256(body.encode()).hexdigest()
    with psycopg.connect(conninfo) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS selfhost_schema_history(path text PRIMARY KEY, digest text NOT NULL)")
        row = connection.execute("SELECT digest FROM selfhost_schema_history WHERE path=%s", (relative,)).fetchone()
        if row:
            if row[0] != digest:
                raise ValueError("Changed initialization SQL requires a reviewed migration")
            return
        connection.execute(body)
        connection.execute("INSERT INTO selfhost_schema_history(path,digest) VALUES(%s,%s)", (relative, digest))


def schemas(dsn: Any, names: dict[str, str], config: dict[str, Any]) -> None:
    from deploy.assets import bundle_validator
    from a2flow_asset_store import PostgresAssetRepository
    from a2flow_asset_store.personal_workflows import PersonalWorkflowRepository
    from agent_workflow_runtime.chat.persistence import ConversationStore
    from agent_workflow_runtime.chat.cards import ChatCardStore
    from agent_workflow_runtime.personal_memory import PersonalMemory
    from agent_workflow_runtime.postgres_lifecycle import PostgresRunRepository
    from agent_workflow_runtime.postgres import PostgresInteractionRepository
    from agent_workflow_runtime.postgres_progress import PostgresProgress
    from agent_workflow_runtime.ui_projection import PostgresMvpView
    from agent_workflow_runtime.management_agent.store import ManagementStore
    from langgraph.checkpoint.postgres import PostgresSaver
    from a2flow_content.repository import PostgresContentRepository
    from a2flow_content.models import Environment

    with psycopg.connect(dsn("management")) as connection:
        if connection.execute("SELECT to_regclass('public.a2flow_java_management_schema_history')").fetchone()[0] is None:
            raise ValueError("Run management-migrate before schemas")
    apply_file(dsn("management"), "services/management-java/backend/storage/db/migration/V002__management_agent_tool_receipts.sql")
    apply_file(dsn("management"), "services/management-java/backend/storage/db/migration/V003__capability_approval_consumption.sql")
    for kind in ("prt", "online"):
        PostgresAssetRepository(dsn(kind), environment=kind.upper(), database=names[kind], validator=bundle_validator()).setup()
        apply_file(dsn(kind), "services/management-java/backend/storage/db/runtime-publication/V001__publication_receipts.sql")
    for path in ("services/b-side-api/src/a2flow_bside/schema.sql", "services/b-side-api/src/a2flow_bside/account_guard.sql", "services/scheduler-mq/src/a2flow_scheduler/schema.sql"):
        apply_file(dsn("prt"), path)
    prt = dsn("prt")
    ConversationStore(prt).setup()
    ChatCardStore(prt, environment="PRT").setup()
    PersonalMemory(prt).setup()
    PostgresRunRepository(prt).setup()
    PostgresInteractionRepository(prt).setup()
    PostgresProgress(prt).setup()
    PostgresMvpView(prt).setup()
    with PostgresSaver.from_conn_string(prt) as saver:
        saver.setup()
    PersonalWorkflowRepository(lambda: psycopg.connect(prt, row_factory=dict_row), namespace="a2flow-selfhost", environment="PRT", validator=bundle_validator()).install()
    with psycopg.connect(prt) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS a2flow_management_agent")
    ManagementStore(prt).setup()
    PostgresContentRepository(dsn("content"), environment=Environment.PRT, database=names["content"]).setup()
    with psycopg.connect(prt) as connection:
        # Explicit initial administrator only. No silent password reset or promotion.
        existing = connection.execute("SELECT user_id,password_hash,role FROM users WHERE username=%s", (config["admin"]["username"],)).fetchone()
        if existing is None:
            if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise ValueError("Initial administrator cannot be created in a populated account store")
            connection.execute("INSERT INTO users(id,user_id,username,password_hash,role) VALUES(1,1,%s,%s,'ADMIN')", (config["admin"]["username"], config["admin"]["hash"]))
            connection.execute("SELECT setval(pg_get_serial_sequence('users','id'),1,true)")
        elif existing[0] != 1 or existing[2] != "ADMIN":
            raise ValueError("Initial administrator identity or role changed; inspect rather than overwrite")
    for database, role, tables in (("prt", "accounts", ("users", "sessions")), ("prt", "reader", ("a2flow_asset_versions", "a2flow_asset_environment")), ("management", "reader", ("skill_asset_release_state",))):
        with psycopg.connect(dsn(database)) as connection:
            connection.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(names[database]), sql.Identifier(names[role])))
            connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(names[role])))
            for table in tables:
                connection.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(sql.Identifier(table), sql.Identifier(names[role])))
