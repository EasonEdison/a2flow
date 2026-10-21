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
