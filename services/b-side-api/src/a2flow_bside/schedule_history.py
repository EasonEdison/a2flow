"""Read-only schedule trigger projection. Runtime owns execution status."""

from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel

from sqlalchemy import BigInteger, DateTime, Text, and_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from skillweave_contracts.user_id import require_user_id


class Base(DeclarativeBase):
    pass


class TriggerRow(Base):
    __tablename__ = "scheduler_outbox"
    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OwnerRow(Base):
    __tablename__ = "run_ownership"
    control_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    run_id: Mapped[str | None] = mapped_column(Text)


@dataclass(frozen=True, slots=True)
class ScheduleTrigger:
    schedule_id: str
    control_id: str
    run_id: str | None
    scheduled_at: str
    delivery_state: str
    input_text: str


class ScheduleRunView(BaseModel):
    scheduleId: str
    controlId: str
    runId: str | None
    scheduledAt: str
    deliveryState: str
    lifecycle: str | None
    inputText: str


class ScheduleHistoryRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read(
        self, user_id: int, environment: str, *, schedule_id: int | None = None,
        before: datetime | None = None, limit: int = 20,
    ) -> list[ScheduleTrigger]:
        require_user_id(user_id)
        payload = TriggerRow.payload
        schedule = payload["schedule_id"].astext
        statement = (
            select(
                schedule, TriggerRow.message_id, OwnerRow.run_id,
                payload["scheduled_at"].astext, TriggerRow.state,
                payload["input_text"].astext,
            )
            .outerjoin(OwnerRow, and_(
                OwnerRow.control_id == TriggerRow.message_id,
                OwnerRow.user_id == user_id,
            ))
            .where(
                payload["kind"].astext == "start_workflow",
                payload["user_id"].astext == str(user_id),
                payload["environment"].astext == environment,
            )
        )
        if schedule_id is None:
            # One latest trigger per schedule, not one query per card.
            statement = statement.distinct(schedule).order_by(
                schedule, TriggerRow.created_at.desc(), TriggerRow.message_id.desc()
            )
        else:
            statement = statement.where(schedule == str(schedule_id))
            if before is not None:
                statement = statement.where(
                    payload["scheduled_at"].astext.cast(DateTime(timezone=True)) < before
                )
            statement = statement.order_by(TriggerRow.created_at.desc()).limit(limit)
        with Session(self._engine) as session:
            return [ScheduleTrigger(*row) for row in session.execute(statement).tuples()]
