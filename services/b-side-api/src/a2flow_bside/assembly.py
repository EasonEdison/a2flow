"""Composition root for the b-side service (environment factory).

Mirrors the management preview host's fail-closed style: every value is an
explicit protected configuration; import performs no connection or listener
work. The workflow catalog reads the current environment's published
WORKFLOW assets through the reviewed AssetReader.
"""

from __future__ import annotations

import importlib
import re

import psycopg

from skillweave_contracts import TrustedContext

from a2flow_asset_store import AssetReader, PostgresAssetRepository

from .app import create_app
from .config import BsideConfig
from .repositories import (
    ConversationsRepository,
    MessagesRepository,
    NotificationsRepository,
    RunOwnershipRepository,
    SchedulesRepository,
    SessionsRepository,
    UsersRepository,
)
from .runtime_client import HttpRuntimeClient

_FACTORY = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:"
    r"[A-Za-z_][A-Za-z0-9_]*"
)


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
    """Uvicorn factory; every value is explicit protected configuration."""
    config = BsideConfig.from_environment()
    validator = _load_validator(
        _required("A2FLOW_BSIDE_VALIDATOR_FACTORY"))
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

    connection_factory = lambda: psycopg.connect(
        config.conninfo, connect_timeout=5,
        options="-c statement_timeout=10000 -c lock_timeout=5000",
        application_name="a2flow-b-side-api")

    return create_app(
        users=UsersRepository(connection_factory),
        sessions=SessionsRepository(connection_factory),
        conversations=ConversationsRepository(connection_factory),
        messages=MessagesRepository(connection_factory),
        schedules=SchedulesRepository(connection_factory),
        notifications=NotificationsRepository(connection_factory),
        run_ownership=RunOwnershipRepository(connection_factory),
        runtime_client=HttpRuntimeClient(config.runtime_url),
        workflow_catalog=workflow_catalog,
        pepper=config.pepper,
        browser_origin=config.browser_origin,
        environment=config.environment,
        session_seconds=config.session_seconds,
    )


def _required(name: str) -> str:
    import os
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_BSIDE_CONFIGURATION:" + name)
    return value
