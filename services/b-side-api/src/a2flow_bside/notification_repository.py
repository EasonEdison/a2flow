"""Typed notification persistence; HTTP serialization stays outside the repository."""

from dataclasses import dataclass
from datetime import datetime

import psycopg
from sqlalchemy import BigInteger, DateTime, Text, case, create_engine, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool
from skillweave_contracts.user_id import require_user_id


class Base(DeclarativeBase):
    """Mappings only. Existing SQL migrations remain the DDL authority."""


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


class RunOwnershipRow(Base):
    """Read projection; intentionally maps only the columns used for navigation."""

    __tablename__ = "run_ownership"

    control_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    run_id: Mapped[str | None] = mapped_column(Text)


@dataclass(frozen=True, slots=True)
class NotificationView:
    id: int
    kind: str
    title: str
    body: str
    ref_type: str | None
    ref_id: str | None
    read: bool
    created_at: datetime


def notification_engine(conninfo: str) -> Engine:
    """Keep the existing short-lived connection policy and database timeouts.

    The creator preserves libpq conninfo (including Unix sockets) without URL
    conversion. No connection opens until a repository method is called.
    """
    def connect() -> psycopg.Connection[tuple[object, ...]]:
        return psycopg.connect(
            conninfo, connect_timeout=5,
            options="-c statement_timeout=10000 -c lock_timeout=5000",
            application_name="a2flow-b-side-api",
        )

    return create_engine(
        "postgresql+psycopg://", creator=connect, poolclass=NullPool,
        hide_parameters=True,
    )


class NotificationsRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_for(self, user_id: int, limit: int = 50) -> list[NotificationView]:
        require_user_id(user_id)
        control_id = (
            select(RunOwnershipRow.control_id)
            .where(
                RunOwnershipRow.run_id == NotificationRow.ref_id,
                RunOwnershipRow.user_id == NotificationRow.user_id,
            )
            .limit(1).correlate(NotificationRow).scalar_subquery()
        )
        reference = case(
            (NotificationRow.ref_type == "run", func.coalesce(control_id, NotificationRow.ref_id)),
            else_=NotificationRow.ref_id,
        )
        statement = (
            select(NotificationRow, reference)
            .where(NotificationRow.user_id == user_id)
            .order_by(NotificationRow.read.asc(), NotificationRow.created_at.desc())
            .limit(limit)
        )
        with Session(self._engine) as session:
            return [
                NotificationView(
                    id=item.id, kind=item.kind, title=item.title, body=item.body,
                    ref_type=item.ref_type, ref_id=ref_id, read=item.read,
                    created_at=item.created_at,
                )
                for item, ref_id in session.execute(statement).tuples()
            ]

    def mark_read(self, notification_id: int, user_id: int) -> bool:
        require_user_id(user_id)
        statement = (
            update(NotificationRow)
            .where(NotificationRow.id == notification_id, NotificationRow.user_id == user_id)
            .values(read=True).returning(NotificationRow.id)
        )
        with Session(self._engine) as session, session.begin():
            return session.execute(statement).scalar_one_or_none() is not None
