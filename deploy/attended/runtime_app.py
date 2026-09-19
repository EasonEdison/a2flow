"""Attended runtime host: MvpRuntimeHost assembly plus the PostgreSQL event sink.

Same reviewed pieces as deploy/mvp/app.py (flash model, trusted identity,
activity-package operations); additionally constructs the host with a
PostgresEventSink toward the b-side queue database when
A2FLOW_EVENT_QUEUE_DATABASE_URL is configured. Import performs no DDL and no
listener start.
"""

from __future__ import annotations

import os

import psycopg

from agent_workflow_runtime.event_sink_postgres import PostgresEventSink
from agent_workflow_runtime.mvp_assembly import MvpRuntimeHost
from deploy.mvp import app as mvp


def _event_sink():
    dsn = os.environ.get("A2FLOW_EVENT_QUEUE_DATABASE_URL")
    if not dsn:
        return None
    secret_path = os.environ.get("A2FLOW_EVENT_QUEUE_PASSWORD_FILE")
    if secret_path:
        with open(secret_path, "r", encoding="utf-8") as stream:
            dsn = psycopg.conninfo.make_conninfo(dsn, password=stream.read().strip())
    connection = psycopg.connect(dsn, autocommit=True)
    return PostgresEventSink(connection)


def create_app_from_environment():
    """Uvicorn factory: reviewed mvp assembly + optional queue event sink."""
    sink = _event_sink()
    host = MvpRuntimeHost(
        conninfo=mvp.conninfo,
        database=mvp.required("A2FLOW_DATABASE_NAME"),
        environment=mvp.environment,
        namespace=os.environ.get(
            "A2FLOW_ASSET_NAMESPACE", "a2flow-mvp-activity-planning"
        ),
        bundle_validator=mvp.bundle_validator(),
        application_validator=mvp.application_validator,
        operation_specs=mvp.operations(),
        model_factory=mvp.model_factory,
        identity_resolver=lambda scope: mvp.owner,
        application_data_validator=mvp.application_data_validator,
        static_directory=os.environ.get("A2FLOW_STATIC_DIRECTORY"),
        unexpected_error_observer=mvp.error_observer,
        event_sink=sink,
    )
    return host.create_app()
