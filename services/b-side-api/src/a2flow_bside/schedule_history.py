"""Read-only schedule trigger projection. Runtime owns execution status."""

from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel

from sqlalchemy import BigInteger, DateTime, Text, and_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from skillweave_contracts.user_id import require_user_id


# 这里只定义只读投影映射, 数据库表结构仍由正式迁移管理。
class Base(DeclarativeBase):
    pass


# 触发事实来自 scheduler_outbox, 投递状态与真实运行状态分开。
class TriggerRow(Base):
    __tablename__ = "scheduler_outbox"
    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# 归属表将调度消息的控制请求号关联到实际运行号。
class OwnerRow(Base):
    __tablename__ = "run_ownership"
    control_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    run_id: Mapped[str | None] = mapped_column(Text)


@dataclass(frozen=True, slots=True)
# 冻结一次触发的保存事实, 不在查询历史时重建或重新触发。
class ScheduleTrigger:
    schedule_id: str
    control_id: str
    run_id: str | None
    scheduled_at: str
    delivery_state: str
    input_text: str


# 面向页面同时提供投递、生命周期和原需求, 避免只显示不可读标识。
class ScheduleRunView(BaseModel):
    scheduleId: str
    controlId: str
    runId: str | None
    scheduledAt: str
    deliveryState: str
    lifecycle: str | None
    inputText: str


# 历史仓库只读取已保存触发, 执行层仍是运行状态的权威。
class ScheduleHistoryRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read(
        self, user_id: int, environment: str, *, schedule_id: int | None = None,
        before: datetime | None = None, limit: int = 20,
    ) -> list[ScheduleTrigger]:
        # 查询始终按可信用户和环境过滤, 防止跨账号看到计划输入。
        require_user_id(user_id)
        payload = TriggerRow.payload
        schedule = payload["schedule_id"].astext
        # 批量联查触发与归属; 尚无运行号时保留原触发记录。
        statement = (
            select(
                schedule, TriggerRow.message_id, OwnerRow.run_id,
                payload["scheduled_at"].astext, TriggerRow.state,
                payload["input_text"].astext,
            )
            # 左连接不删除尚未完成投递的触发, 关联同时核对所有者。
            .outerjoin(OwnerRow, and_(
                OwnerRow.control_id == TriggerRow.message_id,
                OwnerRow.user_id == user_id,
            ))
            # 仅选择启动工作流的调度消息, 不混入其他 outbox 事件。
            .where(
                payload["kind"].astext == "start_workflow",
                payload["user_id"].astext == str(user_id),
                payload["environment"].astext == environment,
            )
        )
        # 列表场景每个计划取最近一次, 详情场景则读取指定计划历史。
        if schedule_id is None:
            # One latest trigger per schedule, not one query per card.
            statement = statement.distinct(schedule).order_by(
                schedule, TriggerRow.created_at.desc(), TriggerRow.message_id.desc()
            )
        else:
            statement = statement.where(schedule == str(schedule_id))
            # 时间游标只读取更早触发, 查询结果按创建时间倒序并限制数量。
            if before is not None:
                statement = statement.where(
                    payload["scheduled_at"].astext.cast(DateTime(timezone=True)) < before
                )
            statement = statement.order_by(TriggerRow.created_at.desc()).limit(limit)
        # 会话范围内一次取完结果, 再转换为固定触发记录。
        with Session(self._engine) as session:
            return [ScheduleTrigger(*row) for row in session.execute(statement).tuples()]
