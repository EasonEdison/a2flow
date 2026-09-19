"""scheduler-mq process entry and small HTTP client (env-configured).

The process runs four bounded iterations in a loop:
trigger (advisory-locked), run_workflow consumer, domain-event consumer, and
the wait-timeout monitor. All intervals, endpoints and secrets come from the
environment; nothing has a default.
"""

from __future__ import annotations

import datetime as dt
import json as jsonlib
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


class RemoteHttpError(Exception):
    """Non-2xx response from a platform service."""


class BsideHttpClient:
    """Minimal JSON HTTP client toward the b-side API (run start / stop)."""

    def __init__(
        self, base_url: str, *, timeout: float = 10.0, opener=None
    ) -> None:
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise ValueError("INVALID_BSIDE_URL")
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._opener = opener or urllib.request.urlopen

    def post(self, path: str, *, json: dict) -> dict:
        body = jsonlib.dumps(json, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._base + path, data=body, method="POST"
        )
        request.add_header("Content-Type", "application/json")
        try:
            with self._opener(request, timeout=self._timeout) as response:
                status = getattr(response, "status", None) or response.code
                payload = response.read().decode("utf-8")
        except (urllib.error.URLError, OSError) as exc:
            raise RemoteHttpError("REMOTE_UNAVAILABLE") from exc
        if not 200 <= status < 300:
            raise RemoteHttpError(f"REMOTE_STATUS_{status}")
        try:
            return jsonlib.loads(payload) if payload else {}
        except ValueError:
            return {}


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_SCHEDULER_CONFIGURATION:" + name)
    return value


def _optional_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise RuntimeError("INVALID_SCHEDULER_CONFIGURATION:" + name) from None
    if value <= 0:
        raise RuntimeError("INVALID_SCHEDULER_CONFIGURATION:" + name)
    return value


@dataclass(frozen=True)
class SchedulerSettings:
    database_url: str
    bside_url: str
    lark_url: str | None
    lark_secret: str | None
    trigger_seconds: float
    monitor_seconds: float
    timeout_hours: float

    @classmethod
    def from_environment(cls) -> "SchedulerSettings":
        return cls(
            database_url=_required("A2FLOW_SCHEDULER_DATABASE_URL"),
            bside_url=_required("A2FLOW_SCHEDULER_BSIDE_URL"),
            lark_url=os.environ.get("A2FLOW_LARK_WEBHOOK_URL") or None,
            lark_secret=os.environ.get("A2FLOW_LARK_SECRET") or None,
            trigger_seconds=_optional_float(
                "A2FLOW_SCHEDULER_TRIGGER_SECONDS", 30.0
            ),
            monitor_seconds=_optional_float(
                "A2FLOW_SCHEDULER_MONITOR_SECONDS", 300.0
            ),
            timeout_hours=_optional_float("A2FLOW_WAIT_TIMEOUT_HOURS", 24.0),
        )


def _connect(settings: SchedulerSettings):
    import psycopg

    dsn = settings.database_url
    secret_path = os.environ.get("A2FLOW_SCHEDULER_POSTGRES_PASSWORD_FILE")
    if secret_path:
        with open(secret_path, "r", encoding="utf-8") as stream:
            dsn = psycopg.conninfo.make_conninfo(dsn, password=stream.read().strip())
    return psycopg.connect(dsn, autocommit=True)


def _build_lark(settings: SchedulerSettings):
    from a2flow_scheduler import lark as lark_module

    if not settings.lark_url:
        return None
    return lark_module.LarkWebhookClient(
        settings.lark_url, secret=settings.lark_secret
    )


def run_once(
    *,
    settings: SchedulerSettings,
    conn,
    queue,
    http,
    lark,
    now: dt.datetime,
) -> None:
    from a2flow_scheduler import loops

    loops.run_trigger_iteration(conn=conn, queue=queue, now=now)
    loops.run_workflow_consumer_iteration(conn=conn, queue=queue, http=http)
    loops.run_event_consumer_iteration(conn=conn, queue=queue, lark=lark)
    loops.run_monitor_iteration(
        conn=conn, http=http, timeout_hours=settings.timeout_hours, now=now
    )


def main() -> None:
    from a2flow_bside.queue import PostgresQueueClient

    settings = SchedulerSettings.from_environment()
    http = BsideHttpClient(settings.bside_url)
    lark = _build_lark(settings)
    with _connect(settings) as conn:
        queue = PostgresQueueClient(conn)
        while True:
            run_once(
                settings=settings,
                conn=conn,
                queue=queue,
                http=http,
                lark=lark,
                now=dt.datetime.now(dt.timezone.utc),
            )
            time.sleep(settings.trigger_seconds)


if __name__ == "__main__":
    main()
