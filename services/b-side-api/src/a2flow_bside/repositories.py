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
from skillweave_contracts.user_id import require_user_id

from .errors import BsideError


def _iso(value):
    return value.isoformat() if isinstance(value, dt.datetime) else value


class UsersRepository:
    def __init__(self, connection_factory: Callable):
        self._factory = connection_factory

    def create(self, *, username: str, password_hash: str,
               role: str = "USER") -> int:
        """Insert and return the signed 64-bit database user identity."""
        with self._factory() as connection:
            try:
                row = connection.execute(
                    "SELECT nextval(pg_get_serial_sequence('users', 'id')) "
                    "AS user_id"
                ).fetchone()
                user_id = require_user_id(row["user_id"])
                connection.execute(
                    "INSERT INTO users (id, user_id, username, password_hash, role) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (user_id, user_id, username, password_hash, role))
                return user_id
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

    def create(self, *, token_sha256: str, user_id: int,
               expires_at: dt.datetime) -> None:
        require_user_id(user_id)
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

    def create(self, *, user_id: int, title: str | None) -> dict:
        require_user_id(user_id)
        with self._factory() as connection:
            row = connection.execute(
                "INSERT INTO conversations (user_id, title) VALUES (%s, %s) "
                "RETURNING id, title, created_at",
                (user_id, title)).fetchone()
        return dict(row)

    def list_for(self, user_id: int, limit: int = 50) -> list[dict]:
        require_user_id(user_id)
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT id, title, created_at FROM conversations "
                "WHERE user_id = %s ORDER BY id DESC LIMIT %s",
                (user_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def owner(self, conversation_id: int) -> int | None:
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
                "SELECT * FROM (SELECT id, role, content, ref_kind, ref_id, created_at "
                "FROM messages WHERE conversation_id = %s "
                "ORDER BY id DESC LIMIT %s) recent ORDER BY id ASC",
                (conversation_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def update_delivery(self, *, conversation_id: int, message_id: int,
                        content: dict) -> None:
        with self._factory() as connection:
            changed = connection.execute(
                "UPDATE messages SET content=%s::jsonb "
                "WHERE conversation_id=%s AND id=%s AND role='assistant'",
                (json.dumps(content), conversation_id, message_id),
            ).rowcount
            if changed != 1:
                raise ValueError("CHAT_MESSAGE_MISSING")

    def legacy_history(self, user_id: int, conversation_id: int,
                       before_id: int) -> list[dict]:
        """One-time migration input, not a second live model history source."""
        require_user_id(user_id)
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT m.id,m.role,m.content FROM messages m "
                "JOIN conversations c ON c.id=m.conversation_id "
                "WHERE c.user_id=%s AND c.id=%s AND m.id<%s "
                "AND m.role IN ('user','assistant') "
                "AND NOT (m.content ? 'delivery') ORDER BY m.id",
                (user_id, conversation_id, before_id),
            ).fetchall()
        return [dict(row) for row in rows]


class SchedulesRepository:
    _COLUMNS = frozenset({
        "enabled", "rule_type", "rule_json", "timezone", "input_text",
        "next_run_at", "last_run_at",
    })

    def __init__(self, connection_factory: Callable):
        self._factory = connection_factory

    def create(self, *, user_id: int, workflow_key: str, environment: str,
               rule_type: str, rule_json: dict, timezone: str,
               input_text: str, next_run_at: dt.datetime) -> dict:
        require_user_id(user_id)
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

    def list_for(self, user_id: int, limit: int = 100) -> list[dict]:
        require_user_id(user_id)
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

    def update(self, schedule_id: int, user_id: int, **fields) -> dict | None:
        require_user_id(user_id)
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

    def delete(self, schedule_id: int, user_id: int) -> bool:
        require_user_id(user_id)
        with self._factory() as connection:
            cursor = connection.execute(
                "DELETE FROM workflow_schedules WHERE id = %s AND user_id = %s",
                (schedule_id, user_id))
        return cursor.rowcount > 0


class NotificationsRepository:
    def __init__(self, connection_factory: Callable):
        self._factory = connection_factory

    def list_for(self, user_id: int, limit: int = 50) -> list[dict]:
        require_user_id(user_id)
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT n.id, n.kind, n.title, n.body, n.ref_type, "
                "CASE WHEN n.ref_type='run' THEN COALESCE("
                "(SELECT r.control_id FROM run_ownership r "
                "WHERE r.run_id=n.ref_id AND r.user_id=n.user_id LIMIT 1), n.ref_id) "
                "ELSE n.ref_id END AS ref_id, n.read, n.created_at "
                "FROM notifications n WHERE n.user_id = %s "
                "ORDER BY n.read ASC, n.created_at DESC LIMIT %s",
                (user_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def mark_read(self, notification_id: int, user_id: int) -> bool:
        require_user_id(user_id)
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

    def create(self, *, control_id: str, user_id: int,
               workflow_key: str) -> None:
        require_user_id(user_id)
        with self._factory() as connection:
            connection.execute(
                "INSERT INTO run_ownership (control_id, user_id, workflow_key)"
                " VALUES (%s, %s, %s)",
                (control_id, user_id, workflow_key))

    def reserve(self, *, control_id: str, user_id: int, workflow_key: str) -> None:
        """Idempotently bind a scheduled control before remote dispatch."""
        require_user_id(user_id)
        with self._factory() as connection:
            connection.execute(
                "INSERT INTO run_ownership (control_id, user_id, workflow_key) "
                "VALUES (%s, %s, %s) ON CONFLICT (control_id) DO NOTHING",
                (control_id, user_id, workflow_key),
            )
            row = connection.execute(
                "SELECT user_id, workflow_key FROM run_ownership WHERE control_id = %s",
                (control_id,),
            ).fetchone()
            if row is None or row["user_id"] != user_id or row["workflow_key"] != workflow_key:
                raise BsideError("RUN_CONTROL_ID_CONFLICT", 409)

    def owner_by_run(self, run_id: str) -> int | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id FROM run_ownership WHERE run_id = %s", (run_id,),
            ).fetchone()
        return row["user_id"] if row is not None else None

    def list_for(self, user_id: int, limit: int = 50) -> list[dict]:
        require_user_id(user_id)
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

    def owned_by(self, user_id: int, control_id: str) -> bool:
        require_user_id(user_id)
        with self._factory() as connection:
            row = connection.execute(
                "SELECT 1 FROM run_ownership "
                "WHERE user_id = %s AND control_id = %s",
                (user_id, control_id)).fetchone()
        return row is not None

    def owner(self, control_id: str) -> int | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id FROM run_ownership WHERE control_id = %s",
                (control_id,)).fetchone()
        return row["user_id"] if row is not None else None
