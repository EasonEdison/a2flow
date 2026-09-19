"""PostgreSQL repositories for b-side rows; each method owns a short connection.

Rows are userId-scoped everywhere; write methods additionally filter by
user_id so a caller bug can never mutate another user's row (defense in
depth, mirroring the management repository conventions).
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Callable

from psycopg.errors import UniqueViolation

from .errors import BsideError


def _iso(value):
    return value.isoformat() if isinstance(value, dt.datetime) else value


class UsersRepository:
    def __init__(self, connection_factory: Callable):
        self._factory = connection_factory

    def create(self, *, user_id: str, username: str, password_hash: str,
               role: str = "USER") -> None:
        with self._factory() as connection:
            try:
                connection.execute(
                    "INSERT INTO users (user_id, username, password_hash, role) "
                    "VALUES (%s, %s, %s, %s)",
                    (user_id, username, password_hash, role))
            except UniqueViolation:
                raise BsideError("USERNAME_TAKEN", 409) from None

    def find_by_username(self, username: str) -> dict | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id, username, password_hash, role "
                "FROM users WHERE username = %s", (username,)).fetchone()
        return dict(row) if row is not None else None


class SessionsRepository:
    def __init__(self, connection_factory: Callable):
        self._factory = connection_factory

    def create(self, *, token_sha256: str, user_id: str,
               expires_at: dt.datetime) -> None:
        with self._factory() as connection:
            connection.execute(
                "INSERT INTO sessions (token_sha256, user_id, expires_at) "
                "VALUES (%s, %s, %s)",
                (token_sha256, user_id, expires_at))

    def find_identity(self, token_sha256: str,
                      now: dt.datetime) -> dict | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT s.user_id, u.username, u.role "
                "FROM sessions s JOIN users u ON u.user_id = s.user_id "
                "WHERE s.token_sha256 = %s AND s.expires_at > %s",
                (token_sha256, now)).fetchone()
        if row is None:
            return None
        return {"userId": row["user_id"], "username": row["username"],
                "role": row["role"]}

    def delete(self, token_sha256: str) -> None:
        with self._factory() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_sha256 = %s",
                (token_sha256,))


class ConversationsRepository:
    def __init__(self, connection_factory: Callable):
        self._factory = connection_factory

    def create(self, *, user_id: str, title: str | None) -> dict:
        with self._factory() as connection:
            row = connection.execute(
                "INSERT INTO conversations (user_id, title) VALUES (%s, %s) "
                "RETURNING id, title, created_at",
                (user_id, title)).fetchone()
        return dict(row)

    def list_for(self, user_id: str, limit: int = 50) -> list[dict]:
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT id, title, created_at FROM conversations "
                "WHERE user_id = %s ORDER BY id DESC LIMIT %s",
                (user_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def owner(self, conversation_id: int) -> str | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id FROM conversations WHERE id = %s",
                (conversation_id,)).fetchone()
        return row["user_id"] if row is not None else None


class MessagesRepository:
    def __init__(self, connection_factory: Callable):
        self._factory = connection_factory

    def append(self, *, conversation_id: int, role: str, content: dict,
               ref_kind: str | None = None,
               ref_id: str | None = None) -> dict:
        with self._factory() as connection:
            row = connection.execute(
                "INSERT INTO messages (conversation_id, role, content, "
                "ref_kind, ref_id) VALUES (%s, %s, %s::jsonb, %s, %s) "
                "RETURNING id, role, content, ref_kind, ref_id, created_at",
                (conversation_id, role, json.dumps(content), ref_kind,
                 ref_id)).fetchone()
        return dict(row)

    def list_for(self, conversation_id: int, limit: int = 200) -> list[dict]:
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT id, role, content, ref_kind, ref_id, created_at "
                "FROM messages WHERE conversation_id = %s "
                "ORDER BY id ASC LIMIT %s",
                (conversation_id, limit)).fetchall()
        return [dict(row) for row in rows]


class SchedulesRepository:
    _COLUMNS = frozenset({
        "enabled", "rule_type", "rule_json", "timezone", "input_text",
        "next_run_at", "last_run_at",
    })

    def __init__(self, connection_factory: Callable):
        self._factory = connection_factory

    def create(self, *, user_id: str, workflow_key: str, environment: str,
               rule_type: str, rule_json: dict, timezone: str,
               input_text: str, next_run_at: dt.datetime) -> dict:
        with self._factory() as connection:
            row = connection.execute(
                "INSERT INTO workflow_schedules "
                "(user_id, workflow_key, environment, rule_type, rule_json, "
                " timezone, input_text, next_run_at) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s) "
                "RETURNING id, workflow_key, environment, rule_type, rule_json,"
                " timezone, input_text, enabled, next_run_at, last_run_at, "
                " created_at",
                (user_id, workflow_key, environment, rule_type,
                 json.dumps(rule_json), timezone, input_text, next_run_at),
            ).fetchone()
        return dict(row)

    def list_for(self, user_id: str, limit: int = 100) -> list[dict]:
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT id, workflow_key, environment, rule_type, rule_json,"
                " timezone, input_text, enabled, next_run_at, last_run_at,"
                " created_at FROM workflow_schedules WHERE user_id = %s "
                "ORDER BY id DESC LIMIT %s",
                (user_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def get(self, schedule_id: int) -> dict | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT id, user_id, workflow_key, environment, rule_type,"
                " rule_json, timezone, input_text, enabled, next_run_at,"
                " last_run_at, created_at FROM workflow_schedules "
                "WHERE id = %s", (schedule_id,)).fetchone()
        return dict(row) if row is not None else None

    def update(self, schedule_id: int, user_id: str, **fields) -> dict | None:
        unknown = set(fields) - self._COLUMNS
        if unknown or not fields:
            raise BsideError("INVALID_SCHEDULE_UPDATE", 400)
        assignments = []
        values: list[Any] = []
        for name, value in fields.items():
            assignments.append(f"{name} = %s")
            if name == "rule_json":
                value = json.dumps(value)
                assignments[-1] = f"{name} = %s::jsonb"
            values.append(value)
        values.extend([schedule_id, user_id])
        with self._factory() as connection:
            row = connection.execute(
                "UPDATE workflow_schedules SET "
                + ", ".join(assignments)
                + " WHERE id = %s AND user_id = %s "
                "RETURNING id, workflow_key, environment, rule_type, rule_json,"
                " timezone, input_text, enabled, next_run_at, last_run_at,"
                " created_at",
                values).fetchone()
        return dict(row) if row is not None else None

    def delete(self, schedule_id: int, user_id: str) -> bool:
        with self._factory() as connection:
            cursor = connection.execute(
                "DELETE FROM workflow_schedules WHERE id = %s AND user_id = %s",
                (schedule_id, user_id))
        return cursor.rowcount > 0


class NotificationsRepository:
    def __init__(self, connection_factory: Callable):
        self._factory = connection_factory

    def list_for(self, user_id: str, limit: int = 50) -> list[dict]:
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT id, kind, title, body, ref_type, ref_id, read, "
                "created_at FROM notifications WHERE user_id = %s "
                "ORDER BY read ASC, created_at DESC LIMIT %s",
                (user_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def mark_read(self, notification_id: int, user_id: str) -> bool:
        with self._factory() as connection:
            cursor = connection.execute(
                "UPDATE notifications SET read = TRUE "
                "WHERE id = %s AND user_id = %s",
                (notification_id, user_id))
        return cursor.rowcount > 0


class RunOwnershipRepository:
    """B-side ownership of Runtime control requests (v1 run identity)."""

    def __init__(self, connection_factory: Callable):
        self._factory = connection_factory

    def create(self, *, control_id: str, user_id: str,
               workflow_key: str) -> None:
        with self._factory() as connection:
            connection.execute(
                "INSERT INTO run_ownership (control_id, user_id, workflow_key)"
                " VALUES (%s, %s, %s)",
                (control_id, user_id, workflow_key))

    def list_for(self, user_id: str, limit: int = 50) -> list[dict]:
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT control_id, workflow_key, created_at, run_id "
                "FROM run_ownership WHERE user_id = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (user_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def bind_run_id(self, control_id: str, run_id: str) -> None:
        with self._factory() as connection:
            connection.execute(
                "UPDATE run_ownership SET run_id = %s "
                "WHERE control_id = %s AND run_id IS NULL",
                (run_id, control_id))

    def owner(self, control_id: str) -> str | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id FROM run_ownership WHERE control_id = %s",
                (control_id,)).fetchone()
        return row["user_id"] if row is not None else None
