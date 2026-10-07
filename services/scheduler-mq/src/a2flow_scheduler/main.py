"""Cron/outbox/Redis worker. Only transport publication and status reads retry."""

from __future__ import annotations

import logging
import os
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from redis import Redis

from a2flow_scheduler.contracts import NotificationCommand
from a2flow_scheduler.delivery import consume_one, reconcile_unknown
from a2flow_scheduler.ingress import BsideCommandClient
from a2flow_scheduler.lark import LarkWebhookClient
from a2flow_scheduler.outbox import PostgresOutbox
from a2flow_scheduler.scheduler import trigger_due
from a2flow_scheduler.streams import RedisStreamTransport, StreamChannel

LOG = logging.getLogger(__name__)


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_SCHEDULER_CONFIGURATION:" + name)
    return value


def secret(name: str) -> str:
    path = os.environ.get(name + "_FILE")
    return Path(path).read_text().strip() if path else required(name)


@dataclass(frozen=True)
class SchedulerSettings:
    database_url: str
    redis_url: str
    namespace: str
    bside_url: str
    internal_token: str
    interval: float

    @classmethod
    def from_environment(cls) -> SchedulerSettings:
        interval = float(os.environ.get("A2FLOW_SCHEDULER_TRIGGER_SECONDS", "5"))
        if not 0 < interval <= 60:
            raise ValueError("INVALID_SCHEDULER_TRIGGER_SECONDS")
        dsn = required("A2FLOW_SCHEDULER_DATABASE_URL")
        password_file = os.environ.get("A2FLOW_SCHEDULER_POSTGRES_PASSWORD_FILE")
        if password_file:
            dsn = psycopg.conninfo.make_conninfo(
                dsn, password=Path(password_file).read_text().strip()
            )
        return cls(
            dsn,
            secret("A2FLOW_SCHEDULER_REDIS_URL"),
            required("A2FLOW_SCHEDULER_STREAM_NAMESPACE"),
            required("A2FLOW_SCHEDULER_BSIDE_URL"),
            secret("A2FLOW_SCHEDULER_INTERNAL_TOKEN"),
            interval,
        )


class LarkNotifications:
    def __init__(self, url: str, signing_secret: str | None) -> None:
        self.client = LarkWebhookClient(url, secret=signing_secret)

    def send_notification(self, command: NotificationCommand) -> None:
        self.client.send(
            {
                "config": {"wide_screen_mode": True},
                "header": {
                    "template": "blue",
                    "title": {"tag": "plain_text", "content": command.title},
                },
                "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": command.body}}],
            },
            dedup_key=command.message_id,
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = SchedulerSettings.from_environment()
    client = Redis.from_url(
        settings.redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=5
    )
    transport = RedisStreamTransport(
        client, namespace=settings.namespace, consumer=f"{socket.gethostname()}:{os.getpid()}"
    )
    ingress = BsideCommandClient(settings.bside_url, settings.internal_token)
    lark_url = os.environ.get("A2FLOW_LARK_WEBHOOK_URL")
    sender = LarkNotifications(lark_url, os.environ.get("A2FLOW_LARK_SECRET")) if lark_url else None
    while True:
        try:
            transport.initialize()
            with psycopg.connect(settings.database_url, autocommit=True) as connection:
                outbox = PostgresOutbox(connection)
                trigger_due(outbox, datetime.now(UTC))
                outbox.publish(transport)
                for channel in StreamChannel:
                    for _ in range(50):
                        if not consume_one(outbox, transport, channel, ingress, sender):
                            break
                reconcile_unknown(outbox, ingress)
        except Exception as exc:
            # Do not log credentials, payloads or provider response bodies.
            LOG.error("Scheduler pass failed: %s", type(exc).__name__)
        time.sleep(settings.interval)


if __name__ == "__main__":
    main()
