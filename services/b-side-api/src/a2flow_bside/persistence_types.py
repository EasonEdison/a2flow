"""Concrete PostgreSQL and message shapes shared by B-side composition.

SQL field values and open JSON payloads are dynamic at the driver boundary;
service dependencies themselves never use these bags as a substitute for a type.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, NotRequired, TypeAlias, TypedDict

from psycopg import Connection

DatabaseRow: TypeAlias = dict[str, Any]
DatabaseConnection: TypeAlias = Connection[DatabaseRow]
ConnectionFactory: TypeAlias = Callable[[], DatabaseConnection]


class MessageRecord(TypedDict):
    id: int
    role: str
    content: dict[str, Any]
    ref_kind: NotRequired[str | None]
    ref_id: NotRequired[str | None]
    created_at: NotRequired[datetime]
    conversation_id: NotRequired[int]


def message_record(row: DatabaseRow | None) -> MessageRecord:
    """Decode the known SQL message columns; retain optional column presence."""
    if row is None:
        raise ValueError("CHAT_MESSAGE_MISSING")
    result = MessageRecord(id=row["id"], role=row["role"], content=row["content"])
    if "ref_kind" in row:
        result["ref_kind"] = row["ref_kind"]
    if "ref_id" in row:
        result["ref_id"] = row["ref_id"]
    if "created_at" in row:
        result["created_at"] = row["created_at"]
    if "conversation_id" in row:
        result["conversation_id"] = row["conversation_id"]
    return result
