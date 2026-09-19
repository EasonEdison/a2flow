"""Attended b-side composition: b-side app wired with the real chat runner.

Mirrors a2flow_bside.assembly but injects ChatLoopRunner (runtime chat engine)
instead of leaving the runner unwired. Composition-root code only.
"""

from __future__ import annotations

import importlib
import os
import re

import psycopg
from psycopg.rows import dict_row

from skillweave_contracts import TrustedContext

from a2flow_asset_store import AssetReader, PostgresAssetRepository
from a2flow_bside.app import create_app
from a2flow_bside.config import BsideConfig
from a2flow_bside.repositories import (
    ConversationsRepository,
    MessagesRepository,
    NotificationsRepository,
    RunOwnershipRepository,
    SchedulesRepository,
    SessionsRepository,
    UsersRepository,
)
from a2flow_bside.runtime_client import HttpRuntimeClient

from deploy.mvp import app as mvp

from .chat_runner import ChatLoopRunner

_FACTORY = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:"
    r"[A-Za-z_][A-Za-z0-9_]*"
)


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_BSIDE_CONFIGURATION:" + name)
    return value


def _load_validator(reference: str):
    if not isinstance(reference, str) or not _FACTORY.fullmatch(reference):
        raise RuntimeError("INVALID_BSIDE_VALIDATOR_FACTORY")
    module_name, attribute = reference.split(":", 1)
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
        validator = factory()
    except Exception:
        raise RuntimeError("BSIDE_VALIDATOR_UNAVAILABLE") from None
    if not callable(getattr(validator, "validate", None)):
        raise RuntimeError("BSIDE_VALIDATOR_UNAVAILABLE")
    return validator


def create_app_from_environment():
    config = BsideConfig.from_environment()
    validator = _load_validator(_required("A2FLOW_BSIDE_VALIDATOR_FACTORY"))
    repository = PostgresAssetRepository(
        config.conninfo,
        environment=config.environment,
        database=_required("A2FLOW_BSIDE_DATABASE_NAME"),
        validator=validator,
    )
    reader = AssetReader(repository, config.namespace)

    def workflow_catalog(user_id: str):
        owner = TrustedContext.from_mapping({
            "userId": user_id, "environment": config.environment})
        return [dict(item) for item in reader.list_workflows(owner)]

    chat_runner = ChatLoopRunner(
        model_factory=mvp.model_factory,
        model_reference="deepseek-v4-flash",
        environment=config.environment,
        reader=reader,
    )

    def _password_dsn():
        secret_path = os.environ.get("A2FLOW_BSIDE_POSTGRES_PASSWORD_FILE")
        if not secret_path:
            return config.conninfo
        with open(secret_path, "r", encoding="utf-8") as stream:
            password = stream.read().strip()
        return psycopg.conninfo.make_conninfo(config.conninfo, password=password)

    conninfo = _password_dsn()
    connection_factory = lambda: psycopg.connect(
        conninfo, row_factory=dict_row, connect_timeout=5,
        options="-c statement_timeout=10000 -c lock_timeout=5000",
        application_name="a2flow-b-side-api",
    )

    return create_app(
        users=UsersRepository(connection_factory),
        sessions=SessionsRepository(connection_factory),
        conversations=ConversationsRepository(connection_factory),
        messages=MessagesRepository(connection_factory),
        schedules=SchedulesRepository(connection_factory),
        notifications=NotificationsRepository(connection_factory),
        run_ownership=RunOwnershipRepository(connection_factory),
        runtime_client=HttpRuntimeClient(config.runtime_url),
        chat_runner=chat_runner,
        workflow_catalog=workflow_catalog,
        pepper=config.pepper,
        browser_origin=config.browser_origin,
        environment=config.environment,
        session_seconds=config.session_seconds,
    )
