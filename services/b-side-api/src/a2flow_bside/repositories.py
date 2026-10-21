"""PostgreSQL repositories for b-side rows; each method owns a short connection.

Rows are userId-scoped everywhere; write methods additionally filter by
user_id so a caller bug can never mutate another user's row (defense in
depth, mirroring the management repository conventions).
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from psycopg.errors import UniqueViolation
from skillweave_contracts.user_id import require_user_id

from .errors import BsideError
from .interaction_continuation import continuation_reference
from .persistence_types import ConnectionFactory, DatabaseRow, MessageRecord, message_record


def _iso(value: object) -> object:
    return value.isoformat() if isinstance(value, dt.datetime) else value


class UsersRepository:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    def create(self, *, username: str, password_hash: str, role: str = "USER") -> int:
        """Insert and return the signed 64-bit database user identity."""
        with self._factory() as connection:
            try:
                row = connection.execute(
                    "SELECT nextval(pg_get_serial_sequence('users', 'id')) AS user_id"
                ).fetchone()
                assert row is not None  # nextval SELECT always returns one row.
                user_id = require_user_id(row["user_id"])
                connection.execute(
                    "INSERT INTO users (id, user_id, username, password_hash, role) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (user_id, user_id, username, password_hash, role),
                )
                return user_id
            except UniqueViolation:
                raise BsideError("USERNAME_TAKEN", 409) from None

    def find_by_username(self, username: str) -> DatabaseRow | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id, username, password_hash, role FROM users WHERE username = %s",
                (username,),
            ).fetchone()
        return dict(row) if row is not None else None


class SessionsRepository:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    def create(self, *, token_sha256: str, user_id: int, expires_at: dt.datetime) -> None:
        require_user_id(user_id)
        with self._factory() as connection:
            connection.execute(
                "INSERT INTO sessions (token_sha256, user_id, expires_at) VALUES (%s, %s, %s)",
                (token_sha256, user_id, expires_at),
            )

    def find_identity(self, token_sha256: str, now: dt.datetime) -> DatabaseRow | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT s.user_id, u.username, u.role "
                "FROM sessions s JOIN users u ON u.user_id = s.user_id "
                "WHERE s.token_sha256 = %s AND s.expires_at > %s",
                (token_sha256, now),
            ).fetchone()
        if row is None:
            return None
        return {"userId": row["user_id"], "username": row["username"], "role": row["role"]}

    def delete(self, token_sha256: str) -> None:
        with self._factory() as connection:
            connection.execute("DELETE FROM sessions WHERE token_sha256 = %s", (token_sha256,))


class ConversationsRepository:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    def create(self, *, user_id: int, title: str | None) -> DatabaseRow:
        require_user_id(user_id)
        with self._factory() as connection:
            row = connection.execute(
                "INSERT INTO conversations (user_id, title) VALUES (%s, %s) "
                "RETURNING id, title, created_at",
                (user_id, title),
            ).fetchone()
        assert row is not None  # INSERT RETURNING must produce the inserted row.
        return dict(row)

    def list_for(self, user_id: int, limit: int = 50) -> list[DatabaseRow]:
        require_user_id(user_id)
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT id, title, created_at FROM conversations "
                "WHERE user_id = %s ORDER BY id DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def owner(self, conversation_id: int) -> int | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id FROM conversations WHERE id = %s", (conversation_id,)
            ).fetchone()
        return row["user_id"] if row is not None else None


class MessagesRepository:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    def append(
        self,
        *,
        conversation_id: int,
        role: str,
        content: dict[str, Any],
        ref_kind: str | None = None,
        ref_id: str | None = None,
    ) -> MessageRecord:
        with self._factory() as connection:
            row = connection.execute(
                "INSERT INTO messages (conversation_id, role, content, "
                "ref_kind, ref_id) VALUES (%s, %s, %s::jsonb, %s, %s) "
                "RETURNING id, role, content, ref_kind, ref_id, created_at",
                (conversation_id, role, json.dumps(content), ref_kind, ref_id),
            ).fetchone()
        return message_record(row)

    def claim_interaction_continuation(
        self,
        *,
        user_id: int,
        conversation_id: int,
        card_id: str,
        request_id: str,
        write_completed: bool = False,
    ) -> tuple[bool, MessageRecord, MessageRecord]:
        """Create one follow-up pair per submitted card under the conversation lock.

        Only the transaction that inserts may dispatch. Reading an existing pair
        never resumes an incomplete model turn, including after a process crash.
        """
        require_user_id(user_id)
        # A reusable A2UI card can complete several independently confirmed writes.
        # A repeated response for the same confirmation must never dispatch twice.
        reference = continuation_reference(card_id, request_id if write_completed else None)
        with self._factory() as connection:
            owner = connection.execute(
                "SELECT user_id FROM conversations WHERE id=%s FOR UPDATE",
                (conversation_id,),
            ).fetchone()
            if owner is None or owner["user_id"] != user_id:
                raise BsideError("CONVERSATION_NOT_FOUND", 404)
            rows = connection.execute(
                "SELECT id,role,content,ref_kind,ref_id,created_at FROM messages "
                "WHERE conversation_id=%s AND ref_kind='temporary_interaction' "
                "AND ref_id=%s ORDER BY id",
                (conversation_id, reference),
            ).fetchall()
            if rows:
                by_role = {row["role"]: message_record(row) for row in rows}
                if len(rows) != 2 or set(by_role) != {"user", "assistant"}:
                    raise BsideError("CHAT_CONTINUATION_UNCONFIRMED", 409)
                return False, by_role["user"], by_role["assistant"]
            marker = {"cardId": card_id, "requestId": request_id}
            contents = (
                (
                    "user",
                    {
                        "text": (
                            "写操作已完成，请根据已保存的真实执行结果继续。"
                            if write_completed
                            else "临时交互已提交，请根据已保存的交互结果继续。"
                        ),
                        "delivery": "submitted",
                    },
                ),
                (
                    "assistant",
                    {"text": "", "delivery": "running", "parts": [], "continuation": marker},
                ),
            )
            created: list[MessageRecord] = []
            for role, content in contents:
                row = connection.execute(
                    "INSERT INTO messages (conversation_id,role,content,ref_kind,ref_id) "
                    "VALUES (%s,%s,%s::jsonb,'temporary_interaction',%s) "
                    "RETURNING id,role,content,ref_kind,ref_id,created_at",
                    (conversation_id, role, json.dumps(content), reference),
                ).fetchone()
                created.append(message_record(row))
            return True, created[0], created[1]

    def list_for(self, conversation_id: int, limit: int = 200) -> list[MessageRecord]:
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT * FROM (SELECT id, role, content, ref_kind, ref_id, created_at "
                "FROM messages WHERE conversation_id = %s "
                "ORDER BY id DESC LIMIT %s) recent ORDER BY id ASC",
                (conversation_id, limit),
            ).fetchall()
        return [message_record(row) for row in rows]

    def update_delivery(
        self, *, conversation_id: int, message_id: int, content: dict[str, Any]
    ) -> None:
        with self._factory() as connection:
            changed = connection.execute(
                "UPDATE messages SET content=%s::jsonb "
                "WHERE conversation_id=%s AND id=%s AND role='assistant'",
                (json.dumps(content), conversation_id, message_id),
            ).rowcount
            if changed != 1:
                raise ValueError("CHAT_MESSAGE_MISSING")

    def legacy_history(
        self, user_id: int, conversation_id: int, before_id: int
    ) -> list[MessageRecord]:
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
        return [message_record(row) for row in rows]


class SchedulesRepository:
    _COLUMNS = frozenset(
        {
            "enabled",
            "rule_type",
            "rule_json",
            "timezone",
            "input_text",
            "next_run_at",
            "last_run_at",
        }
    )

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    def create(
        self,
        *,
        user_id: int,
        workflow_key: str,
        environment: str,
        rule_type: str,
        rule_json: dict[str, Any],
        timezone: str,
        input_text: str,
        next_run_at: dt.datetime,
    ) -> DatabaseRow:
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
                (
                    user_id,
                    workflow_key,
                    environment,
                    rule_type,
                    json.dumps(rule_json),
                    timezone,
                    input_text,
                    next_run_at,
                ),
            ).fetchone()
        assert row is not None  # INSERT RETURNING must produce the inserted row.
        return dict(row)

    def list_for(self, user_id: int, limit: int = 100) -> list[DatabaseRow]:
        require_user_id(user_id)
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT id, workflow_key, environment, rule_type, rule_json,"
                " timezone, input_text, enabled, next_run_at, last_run_at,"
                " created_at FROM workflow_schedules WHERE user_id = %s "
                "ORDER BY id DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, schedule_id: int) -> DatabaseRow | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT id, user_id, workflow_key, environment, rule_type,"
                " rule_json, timezone, input_text, enabled, next_run_at,"
                " last_run_at, created_at FROM workflow_schedules "
                "WHERE id = %s",
                (schedule_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def update(self, schedule_id: int, user_id: int, **fields: object) -> DatabaseRow | None:
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
                values,
            ).fetchone()
        return dict(row) if row is not None else None

    def delete(self, schedule_id: int, user_id: int) -> bool:
        require_user_id(user_id)
        with self._factory() as connection:
            cursor = connection.execute(
                "DELETE FROM workflow_schedules WHERE id = %s AND user_id = %s",
                (schedule_id, user_id),
            )
        return cursor.rowcount > 0


class RunOwnershipRepository:
    """B-side ownership of Runtime control requests (v1 run identity)."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    def create(self, *, control_id: str, user_id: int, workflow_key: str) -> None:
        require_user_id(user_id)
        with self._factory() as connection:
            connection.execute(
                "INSERT INTO run_ownership (control_id, user_id, workflow_key) VALUES (%s, %s, %s)",
                (control_id, user_id, workflow_key),
            )

    def reserve(
        self,
        *,
        control_id: str,
        user_id: int,
        workflow_key: str,
        environment: str | None = None,
        source_type: str = "unknown",
    ) -> None:
        """Idempotently bind a scheduled control before remote dispatch."""
        require_user_id(user_id)
        with self._factory() as connection:
            connection.execute(
                "INSERT INTO run_ownership (control_id, user_id, workflow_key, environment, source_type) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (control_id) DO NOTHING",
                (control_id, user_id, workflow_key, environment, source_type),
            )
            row = connection.execute(
                "SELECT user_id, workflow_key, environment FROM run_ownership WHERE control_id = %s",
                (control_id,),
            ).fetchone()
            if (
                row is None
                or row["user_id"] != user_id
                or row["workflow_key"] != workflow_key
                or (row["environment"] is not None and row["environment"] != environment)
            ):
                raise BsideError("RUN_CONTROL_ID_CONFLICT", 409)

    def owner_by_run(self, run_id: str) -> int | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id FROM run_ownership WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        return row["user_id"] if row is not None else None

    def list_for(self, user_id: int, limit: int = 50) -> list[DatabaseRow]:
        require_user_id(user_id)
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT control_id, workflow_key, created_at, run_id "
                "FROM run_ownership WHERE user_id = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def bind_run_id(self, control_id: str, run_id: str) -> None:
        with self._factory() as connection:
            connection.execute(
                "UPDATE run_ownership SET run_id = %s WHERE control_id = %s AND run_id IS NULL",
                (run_id, control_id),
            )

    def owned_by(self, user_id: int, control_id: str) -> bool:
        require_user_id(user_id)
        with self._factory() as connection:
            row = connection.execute(
                "SELECT 1 FROM run_ownership WHERE user_id = %s AND control_id = %s",
                (user_id, control_id),
            ).fetchone()
        return row is not None

    def owner(self, control_id: str) -> int | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id FROM run_ownership WHERE control_id = %s", (control_id,)
            ).fetchone()
        return row["user_id"] if row is not None else None
