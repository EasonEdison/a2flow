"""Scheduler mappings; existing SQL migrations remain the DDL authority."""

from datetime import datetime

import psycopg
from sqlalchemy import BigInteger, DateTime, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


class OutboxRow(Base):
    __tablename__ = "scheduler_outbox"
    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    channel: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(Text)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScheduleRow(Base):
    __tablename__ = "workflow_schedules"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    workflow_key: Mapped[str] = mapped_column(Text)
    environment: Mapped[str] = mapped_column(Text)
    rule_type: Mapped[str] = mapped_column(Text)
    rule_json: Mapped[dict[str, object]] = mapped_column(JSONB)
    timezone: Mapped[str] = mapped_column(Text)
    input_text: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool]
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NotificationRow(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    ref_type: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[str | None] = mapped_column(Text)
    read: Mapped[bool]
    idempotency_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def scheduler_engine(conninfo: str) -> Engine:
    def connect() -> psycopg.Connection[tuple[object, ...]]:
        return psycopg.connect(conninfo)

    return create_engine(
        "postgresql+psycopg://",
        creator=connect,
        poolclass=NullPool,
        hide_parameters=True,
    )
