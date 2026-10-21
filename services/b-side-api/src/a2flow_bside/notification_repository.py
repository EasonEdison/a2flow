"""Typed notification persistence; HTTP serialization stays outside the repository."""

from dataclasses import dataclass
from datetime import datetime

import psycopg
from sqlalchemy import BigInteger, DateTime, Text, case, create_engine, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool
from skillweave_contracts.user_id import require_user_id


# ORM 仅映射现有表, 不在运行请求中自动建表或修改迁移。
class Base(DeclarativeBase):
    """Mappings only. Existing SQL migrations remain the DDL authority."""


# 通知保存自己的幂等键与阅读标记, 与业务执行状态互不替代。
class NotificationRow(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    # 来源引用同时保存类型和身份, 支持从通知跳转到正确产品页面。
    ref_type: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[str | None] = mapped_column(Text)
    read: Mapped[bool]
    idempotency_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# 只映射导航需要的归属字段, 不复制完整执行层状态。
class RunOwnershipRow(Base):
    """Read projection; intentionally maps only the columns used for navigation."""

    __tablename__ = "run_ownership"

    control_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    run_id: Mapped[str | None] = mapped_column(Text)


@dataclass(frozen=True, slots=True)
# 返回不可变通知视图, HTTP 字段命名和序列化交给路由层。
class NotificationView:
    id: int
    kind: str
    title: str
    body: str
    # 视图保留来源和读取时间, 不能用标题文本猜测关联运行。
    ref_type: str | None
    ref_id: str | None
    read: bool
    created_at: datetime


# 通过 creator 保留原生 libpq 连接串语义, 包含 Unix socket 等配置。
def notification_engine(conninfo: str) -> Engine:
    """Keep the existing short-lived connection policy and database timeouts.

    The creator preserves libpq conninfo (including Unix sockets) without URL
    conversion. No connection opens until a repository method is called.
    """
    # 连接按仓库调用创建, 并限制连接、语句和锁等待时间。
    def connect() -> psycopg.Connection[tuple[object, ...]]:
        return psycopg.connect(
            conninfo, connect_timeout=5,
            options="-c statement_timeout=10000 -c lock_timeout=5000",
            application_name="a2flow-b-side-api",
        )

    # 不启用额外连接池且隐藏 SQL 参数, 避免在异常日志泄露敏感内容。
    return create_engine(
        "postgresql+psycopg://", creator=connect, poolclass=NullPool,
        hide_parameters=True,
    )


# 通知仓库负责用户隔离和阅读写入, 不调用模型或执行工具。
class NotificationsRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_for(self, user_id: int, limit: int = 50) -> list[NotificationView]:
        require_user_id(user_id)
        # 将实际运行引用映射为同用户的产品控制号, 保持前端导航兼容。
        control_id = (
            select(RunOwnershipRow.control_id)
            .where(
                RunOwnershipRow.run_id == NotificationRow.ref_id,
                RunOwnershipRow.user_id == NotificationRow.user_id,
            )
            .limit(1).correlate(NotificationRow).scalar_subquery()
        )
        # 有归属映射优先用控制号, 未找到时保留原引用, 不制造新身份。
        reference = case(
            (NotificationRow.ref_type == "run", func.coalesce(control_id, NotificationRow.ref_id)),
            else_=NotificationRow.ref_id,
        )
        # 未读优先、时间倒序读取, 并限制返回条数。
        statement = (
            select(NotificationRow, reference)
            .where(NotificationRow.user_id == user_id)
            .order_by(NotificationRow.read.asc(), NotificationRow.created_at.desc())
            .limit(limit)
        )
        # 只输出固定通知字段, 仓库不直接生成 HTTP 响应。
        with Session(self._engine) as session:
            return [
                NotificationView(
                    id=item.id, kind=item.kind, title=item.title, body=item.body,
                    ref_type=item.ref_type, ref_id=ref_id, read=item.read,
                    created_at=item.created_at,
                )
                for item, ref_id in session.execute(statement).tuples()
            ]

    # 阅读更新同时限定通知和用户, 在短事务中返回是否实际命中。
    def mark_read(self, notification_id: int, user_id: int) -> bool:
        require_user_id(user_id)
        statement = (
            update(NotificationRow)
            .where(NotificationRow.id == notification_id, NotificationRow.user_id == user_id)
            # 重复阅读保持已读状态, 不影响来源异常和任务结果。
            .values(read=True).returning(NotificationRow.id)
        )
        with Session(self._engine) as session, session.begin():
            return session.execute(statement).scalar_one_or_none() is not None
