"""Concrete PostgreSQL and message shapes shared by B-side composition.

SQL field values and open JSON payloads are dynamic at the driver boundary;
service dependencies themselves never use these bags as a substitute for a type.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, NotRequired, TypeAlias, TypedDict

from psycopg import Connection

# 动态字段仅保留在 SQL 边界, 连接和连接工厂仍使用具体 PostgreSQL 类型。
DatabaseRow: TypeAlias = dict[str, Any]
DatabaseConnection: TypeAlias = Connection[DatabaseRow]
ConnectionFactory: TypeAlias = Callable[[], DatabaseConnection]


# 声明消息固定字段; 可选列保留缺失语义, 不一律填入空值。
class MessageRecord(TypedDict):
    id: int
    role: str
    content: dict[str, Any]
    # 引用字段区分运行、卡片与恢复消息, 不能只凭文本识别关系。
    ref_kind: NotRequired[str | None]
    ref_id: NotRequired[str | None]
    created_at: NotRequired[datetime]
    conversation_id: NotRequired[int]


def message_record(row: DatabaseRow | None) -> MessageRecord:
    """Decode the known SQL message columns; retain optional column presence."""
    # 未查询到消息属于异常, 不制造空消息供后续执行。
    if row is None:
        raise ValueError("CHAT_MESSAGE_MISSING")
    result = MessageRecord(id=row["id"], role=row["role"], content=row["content"])
    # 仅复制实际查询包含的可选列, 兼容不同 SQL 返回字段集合。
    if "ref_kind" in row:
        result["ref_kind"] = row["ref_kind"]
    if "ref_id" in row:
        result["ref_id"] = row["ref_id"]
    # 保留时间与会话归属供历史展示和任务关联使用。
    if "created_at" in row:
        result["created_at"] = row["created_at"]
    if "conversation_id" in row:
        result["conversation_id"] = row["conversation_id"]
    return result
