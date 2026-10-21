"""Composition root for the b-side service (environment factory).

Mirrors the management preview host's fail-closed style: every value is an
explicit protected configuration; import performs no connection or listener
work. The workflow catalog reads the current environment's published
WORKFLOW assets through the reviewed AssetReader.
"""

from __future__ import annotations

import importlib
import os
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import psycopg
from a2flow_asset_store import AssetReader, BundleValidator, PostgresAssetRepository
from fastapi import FastAPI
from psycopg.rows import dict_row
from skillweave_contracts import TrustedContext

from .account_guard import AccountGuardConfig, PostgresAccountGuard
from .app import create_app
from .chat_runner import ChatRunner, RuntimeTurnInspection
from .config import BsideConfig
from .notification_repository import NotificationsRepository, notification_engine
from .persistence_types import DatabaseConnection
from .repositories import (
    ConversationsRepository,
    MessagesRepository,
    RunOwnershipRepository,
    SchedulesRepository,
    SessionsRepository,
    UsersRepository,
)
from .runtime_client import HttpRuntimeClient
from .schedule_history import ScheduleHistoryRepository

_FACTORY = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:"
    r"[A-Za-z_][A-Za-z0-9_]*"
)


def _load_validator(reference: str) -> BundleValidator:
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


class _UnavailableChatRunner:
    """Fail-closed placeholder: chat is unavailable until wired by the
    deployment composition (deploy.attended.bside_app)."""

    async def inspect_turn(
        self,
        *,
        user_id: int,
        conversation_id: int,
        turn_id: str,
    ) -> RuntimeTurnInspection:
        # An unwired engine cannot establish native admission or completed facts.
        return {"status": "NEEDS_REVIEW", "events": []}

    async def iterate(
        self,
        *,
        user_id: int,
        conversation_id: int,
        text: str,
        turn_id: str,
        run_references: Sequence[Mapping[str, Any]] = (),
        processing_context: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "error", "code": "CHAT_RUNNER_NOT_WIRED"}


def create_app_from_environment(*, chat_runner: ChatRunner | None = None) -> FastAPI:
    """Uvicorn factory; every value is explicit protected configuration."""
    config = BsideConfig.from_environment()
    validator = _load_validator(_required("A2FLOW_BSIDE_VALIDATOR_FACTORY"))
    repository = PostgresAssetRepository(
        config.conninfo,
        environment=config.environment,
        database=_required("A2FLOW_BSIDE_DATABASE_NAME"),
        validator=validator,
    )
    base_reader = AssetReader(repository, config.namespace)

    def workflow_catalog(user_id: int) -> list[dict[str, Any]]:
        owner = TrustedContext.from_mapping({"userId": user_id, "environment": config.environment})
        return [dict(item) for item in reader.list_workflows(owner)]

    def connection_factory() -> DatabaseConnection:
        return psycopg.connect(
            config.conninfo,
            row_factory=dict_row,
            connect_timeout=5,
            options="-c statement_timeout=10000 -c lock_timeout=5000",
            application_name="a2flow-b-side-api",
        )

    from a2flow_asset_store.personal_workflows import (
        PersonalWorkflowReader,
        PersonalWorkflowRepository,
    )

    reader = PersonalWorkflowReader(
        base_reader,
        PersonalWorkflowRepository(
            connection_factory,
            namespace=config.namespace,
            environment=config.environment,
            validator=validator,
        ),
    )

    account_guard = PostgresAccountGuard(
        connection_factory,
        pepper=config.pepper,
        environment=config.environment,
        config=AccountGuardConfig.from_environment(os.environ),
    )
    account_guard.check_ready()

    return create_app(
        account_guard=account_guard,
        users=UsersRepository(connection_factory),
        sessions=SessionsRepository(connection_factory),
        conversations=ConversationsRepository(connection_factory),
        messages=MessagesRepository(connection_factory),
        schedules=SchedulesRepository(connection_factory),
        notifications=NotificationsRepository(notification_engine(config.conninfo)),
        schedule_history=ScheduleHistoryRepository(notification_engine(config.conninfo)),
        run_ownership=RunOwnershipRepository(connection_factory),
        runtime_client=HttpRuntimeClient(config.runtime_url),
        workflow_catalog=workflow_catalog,
        pepper=config.pepper,
        browser_origin=config.browser_origin,
        browser_origins=config.browser_origins,
        environment=config.environment,
        chat_runner=chat_runner if chat_runner is not None else _UnavailableChatRunner(),
        session_seconds=config.session_seconds,
    )


def _required(name: str) -> str:
    import os

    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_BSIDE_CONFIGURATION:" + name)
    return value
