"""Management-only PostgreSQL records and native LangGraph checkpoints.

A session advisory lock spans worker execution. Failed checkpoints are never resumed:
a later, explicit user turn starts a new native thread with durable history facts.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from typing import Any, cast
from uuid import uuid4

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row

from .models import MAX_TURNS, AgentError, AgentIdentity, encode, identifier

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
 namespace text NOT NULL, environment text NOT NULL, user_id bigint NOT NULL,
 id text NOT NULL, create_request_id text NOT NULL, title text NOT NULL,
 created_at bigint NOT NULL, updated_at bigint NOT NULL,
 PRIMARY KEY(namespace,environment,user_id,id),
 UNIQUE(namespace,environment,user_id,create_request_id)
);
CREATE TABLE IF NOT EXISTS turns (
 namespace text NOT NULL, environment text NOT NULL, user_id bigint NOT NULL,
 conversation_id text NOT NULL, turn_id text NOT NULL, request_id text NOT NULL,
 status text NOT NULL CHECK(status IN ('RUNNING','COMPLETED','FAILED','UNKNOWN')),
 message text NOT NULL, final_text text NOT NULL DEFAULT '', error_code text NOT NULL DEFAULT '',
 thread_id text NOT NULL, created_at bigint NOT NULL, updated_at bigint NOT NULL,
 PRIMARY KEY(namespace,environment,user_id,conversation_id,request_id), UNIQUE(turn_id)
);
CREATE TABLE IF NOT EXISTS events (
 sequence bigserial PRIMARY KEY, namespace text NOT NULL, environment text NOT NULL,
 user_id bigint NOT NULL, conversation_id text NOT NULL, turn_id text NOT NULL,
 type text NOT NULL, payload_json jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS events_conversation ON events(namespace,environment,user_id,conversation_id,sequence);
CREATE TABLE IF NOT EXISTS mutations (
 namespace text NOT NULL, environment text NOT NULL, user_id bigint NOT NULL,
 conversation_id text NOT NULL, request_id text NOT NULL, turn_id text NOT NULL,
 name text NOT NULL, arguments_json jsonb NOT NULL, status text NOT NULL,
 result_json jsonb NOT NULL, PRIMARY KEY(namespace,environment,user_id,conversation_id,request_id)
);
"""


def now() -> int:
    return int(time.time() * 1000)


class ManagementStore:
    def __init__(self, conninfo: str, schema: str = "a2flow_management_agent") -> None:
        if not schema.replace("_", "").isalnum() or not schema.startswith(
            "a2flow_management_agent"
        ):
            raise ValueError("DEDICATED_MANAGEMENT_SCHEMA_REQUIRED")
        self._base_conninfo = conninfo
        self.schema = schema
        # Generic checkpoint table names are isolated from the B-side schema.
        self.conninfo = psycopg.conninfo.make_conninfo(
            conninfo,
            options=(
                f"-c search_path={schema} -c statement_timeout=10000 "
                "-c lock_timeout=5000 -c default_transaction_read_only=off"
            ),
        )

    def setup(self) -> None:
        with psycopg.connect(self._base_conninfo, autocommit=True, connect_timeout=5) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname=%s", (self.schema,)
            ).fetchone()
            if not exists:
                raise AgentError("MANAGEMENT_SCHEMA_NOT_PROVISIONED")
        with self.connect(autocommit=True) as conn:
            conn.execute(SCHEMA)
            PostgresSaver(conn).setup()

    def connect(self, *, autocommit: bool = False) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(
            self.conninfo, autocommit=autocommit, row_factory=dict_row, connect_timeout=5
        )

    @staticmethod
    def key(who: AgentIdentity, conversation_id: str) -> tuple[str, str, int, str]:
        return (*who.scope, identifier(conversation_id))

    def _conversation(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        who: AgentIdentity,
        cid: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any]:
        row = conn.execute(
            "SELECT * FROM conversations WHERE namespace=%s AND environment=%s AND user_id=%s AND id=%s"
            + (" FOR UPDATE" if lock else ""),
            self.key(who, cid),
        ).fetchone()
        if row is None:
            raise AgentError("CONVERSATION_NOT_FOUND")
        return cast(dict[str, Any], row)

    def create(self, who: AgentIdentity, request_id: str, title: str) -> dict[str, Any]:
        identifier(request_id)
        if not isinstance(title, str) or len(title) > 200:
            raise AgentError("INVALID_CONVERSATION_TITLE")
        title = title.strip() or "新的管理对话"
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO conversations VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (*who.scope, uuid4().hex, request_id, title, now(), now()),
            )
            row = conn.execute(
                "SELECT * FROM conversations WHERE namespace=%s AND environment=%s AND user_id=%s AND create_request_id=%s",
                (*who.scope, request_id),
            ).fetchone()
            if row["title"] != title:
                raise AgentError("REQUEST_ID_CONFLICT")
            return cast(dict[str, Any], row)

    def list_conversations(
        self, who: AgentIdentity, token: str, limit: int
    ) -> tuple[list[dict[str, Any]], str]:
        if token:
            identifier(token)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE namespace=%s AND environment=%s AND user_id=%s AND id>%s ORDER BY id LIMIT %s",
                (*who.scope, token, limit + 1),
            ).fetchall()
            return rows[:limit], rows[limit - 1]["id"] if len(rows) > limit else ""

    def existing(
        self, who: AgentIdentity, cid: str, request_id: str, message: str
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            self._conversation(conn, who, cid)
            row = conn.execute(
                "SELECT * FROM turns WHERE namespace=%s AND environment=%s AND user_id=%s AND conversation_id=%s AND request_id=%s",
                (*self.key(who, cid), request_id),
            ).fetchone()
            if row and row["message"] != message:
                raise AgentError("REQUEST_ID_CONFLICT")
            return cast(dict[str, Any], row)

    def claim(
        self, who: AgentIdentity, cid: str, request_id: str, message: str
    ) -> tuple[dict[str, Any], bool]:
        key = self.key(who, cid)
        identifier(request_id)
        if not isinstance(message, str) or not message.strip() or len(message) > 16000:
            raise AgentError("INVALID_MANAGEMENT_MESSAGE")
        with self.connect() as conn:
            self._conversation(conn, who, cid, lock=True)
            rows = conn.execute(
                "SELECT * FROM turns WHERE namespace=%s AND environment=%s AND user_id=%s AND conversation_id=%s ORDER BY created_at,turn_id",
                key,
            ).fetchall()
            for row in rows:
                if row["request_id"] == request_id:
                    if row["message"] != message:
                        raise AgentError("REQUEST_ID_CONFLICT")
                    return row, False
            if any(x["status"] == "RUNNING" for x in rows):
                raise AgentError("CONVERSATION_BUSY")
            if len(rows) >= MAX_TURNS:
                raise AgentError("CONVERSATION_TURN_LIMIT")
            thread_id = (
                rows[-1]["thread_id"] if rows and rows[-1]["status"] == "COMPLETED" else uuid4().hex
            )
            turn_id = uuid4().hex
            row = conn.execute(
                "INSERT INTO turns(namespace,environment,user_id,conversation_id,turn_id,request_id,status,message,thread_id,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,'RUNNING',%s,%s,%s,%s) RETURNING *",
                (*key, turn_id, request_id, message, thread_id, now(), now()),
            ).fetchone()
            self._event(
                conn,
                who,
                cid,
                turn_id,
                "TURN_STARTED",
                {"requestId": request_id, "message": message},
            )
            conn.execute(
                "UPDATE conversations SET updated_at=%s WHERE namespace=%s AND environment=%s AND user_id=%s AND id=%s",
                (now(), *key),
            )
            return row, True

    def _event(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        who: AgentIdentity,
        cid: str,
        turn_id: str,
        kind: str,
        payload: dict[str, Any],
    ) -> None:
        conn.execute(
            "INSERT INTO events(namespace,environment,user_id,conversation_id,turn_id,type,payload_json) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)",
            (*self.key(who, cid), turn_id, kind, encode(payload).decode()),
        )

    def event(
        self, who: AgentIdentity, cid: str, turn_id: str, kind: str, payload: dict[str, Any]
    ) -> None:
        with self.connect() as conn:
            self._event(conn, who, cid, turn_id, kind, payload)

    def finish(
        self,
        who: AgentIdentity,
        cid: str,
        turn_id: str,
        status: str,
        *,
        text: str = "",
        error: str = "",
    ) -> None:
        if len(text.encode()) > 64 * 1024:
            raise AgentError("MANAGEMENT_REPLY_TOO_LARGE")
        with self.connect() as conn:
            row = conn.execute(
                "UPDATE turns SET status=%s,final_text=%s,error_code=%s,updated_at=%s WHERE namespace=%s AND environment=%s AND user_id=%s AND conversation_id=%s AND turn_id=%s AND status='RUNNING' RETURNING turn_id",
                (status, text, error, now(), *self.key(who, cid), turn_id),
            ).fetchone()
            if row is None:
                return
            if text:
                self._event(conn, who, cid, turn_id, "ASSISTANT_MESSAGE", {"text": text})
            payload = {"status": status, "errorCode": error}
            if status != "COMPLETED":
                payload["message"] = "上一轮未完成；新消息是新一轮，不会自动重放旧操作。"
            self._event(conn, who, cid, turn_id, "TURN_" + status, payload)

    def read(self, who: AgentIdentity, cid: str, after: int, limit: int) -> dict[str, Any]:
        with self.connect() as conn:
            conversation = self._conversation(conn, who, cid)
            turns = conn.execute(
                "SELECT * FROM turns WHERE namespace=%s AND environment=%s AND user_id=%s AND conversation_id=%s ORDER BY created_at,turn_id",
                self.key(who, cid),
            ).fetchall()
            events: list[dict[str, Any]] = []
            page_bytes = 0
            has_more = False
            # Stream from PostgreSQL so a page of large results cannot consume 100 MiB.
            with conn.cursor(name="management_events_" + uuid4().hex) as cursor:
                cursor.execute(
                    "SELECT * FROM events WHERE namespace=%s AND environment=%s AND user_id=%s AND conversation_id=%s AND sequence>%s ORDER BY sequence LIMIT %s",
                    (*self.key(who, cid), after, limit + 1),
                )
                for event in cursor:
                    event_bytes = len(encode(event["payload_json"]))
                    if events and (len(events) >= limit or page_bytes + event_bytes > 1024 * 1024):
                        has_more = True
                        break
                    events.append(event)
                    page_bytes += event_bytes
            unresolved = conn.execute(
                "SELECT 1 FROM mutations WHERE namespace=%s AND environment=%s AND user_id=%s AND conversation_id=%s AND status NOT IN ('SUCCEEDED','REJECTED') LIMIT 1",
                self.key(who, cid),
            ).fetchone()
            return dict(
                conversation=conversation,
                turns=turns,
                events=events,
                next_event_seq=events[-1]["sequence"] if events else after,
                has_more=has_more,
                can_send=not any(x["status"] == "RUNNING" for x in turns)
                and len(turns) < MAX_TURNS,
                mutations_blocked=bool(unresolved),
            )

    @contextmanager
    def session(self, who: AgentIdentity, cid: str) -> Iterator[PostgresSaver]:
        lock_key = int.from_bytes(
            sha256(encode(["management", *self.key(who, cid)])).digest()[:8], "big", signed=True
        )
        with self.connect(autocommit=True) as conn:
            if not conn.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired", (lock_key,)
            ).fetchone()["acquired"]:
                raise AgentError("CONVERSATION_BUSY")
            try:
                yield PostgresSaver(conn)
            finally:
                conn.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))

    def unresolved(self, who: AgentIdentity, cid: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return cast(
                list[dict[str, Any]],
                conn.execute(
                    "SELECT * FROM mutations WHERE namespace=%s AND environment=%s AND user_id=%s AND conversation_id=%s AND status NOT IN ('SUCCEEDED','REJECTED') ORDER BY request_id",
                    self.key(who, cid),
                ).fetchall(),
            )

    def mutation(
        self,
        who: AgentIdentity,
        cid: str,
        turn_id: str,
        request_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        with self.connect() as conn:
            inserted = conn.execute(
                "INSERT INTO mutations VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'UNKNOWN','{}'::jsonb) ON CONFLICT DO NOTHING RETURNING request_id",
                (*self.key(who, cid), request_id, turn_id, name, encode(arguments).decode()),
            ).fetchone()
            row = conn.execute(
                "SELECT * FROM mutations WHERE namespace=%s AND environment=%s AND user_id=%s AND conversation_id=%s AND request_id=%s",
                (*self.key(who, cid), request_id),
            ).fetchone()
            if row["name"] != name or row["arguments_json"] != arguments:
                raise AgentError("REQUEST_ID_CONFLICT")
            return row, inserted is not None

    def receipt(
        self, who: AgentIdentity, cid: str, request_id: str, result: dict[str, Any]
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE mutations SET status=%s,result_json=%s::jsonb WHERE namespace=%s AND environment=%s AND user_id=%s AND conversation_id=%s AND request_id=%s",
                (result["status"], encode(result).decode(), *self.key(who, cid), request_id),
            )

    def receipt_facts(self, who: AgentIdentity, cid: str) -> list[dict[str, Any]]:
        # Keep exact IDs/version/status facts while excluding large editable asset bodies.
        def project(value: Any, depth: int = 0) -> Any:
            if depth > 6:
                return None
            if isinstance(value, list):
                return [project(item, depth + 1) for item in value[:20]]
            if not isinstance(value, dict):
                return (
                    value
                    if not isinstance(value, str) or len(value) <= 512
                    else "[long value omitted]"
                )
            result = {}
            for key, item in value.items():
                if key in {
                    "id",
                    "status",
                    "version",
                    "environment",
                    "name",
                    "nameCn",
                    "displayName",
                    "assetType",
                    "assetKey",
                    "success",
                    "data",
                    "result",
                    "assets",
                    "errorMsg",
                } or key.endswith(("Id", "Code", "Digest", "Version")):
                    result[key] = project(item, depth + 1)
            return result

        with self.connect() as conn:
            rows = conn.execute(
                "SELECT m.request_id,m.name,m.status,m.result_json FROM mutations m JOIN turns t ON t.turn_id=m.turn_id WHERE m.namespace=%s AND m.environment=%s AND m.user_id=%s AND m.conversation_id=%s ORDER BY t.created_at DESC,m.request_id LIMIT 80",
                self.key(who, cid),
            ).fetchall()
        return [
            dict(
                requestId=row["request_id"],
                name=row["name"],
                status=row["status"],
                receipt=project(row["result_json"]),
            )
            for row in rows
        ]

    def recover_crashed(self) -> int:
        # Called only by the singleton host holding host_lock. No model/tool replay.
        with self.connect() as conn:
            rows = conn.execute(
                "UPDATE turns SET status='UNKNOWN',error_code='HOST_RESTARTED',updated_at=%s WHERE status='RUNNING' RETURNING namespace,environment,user_id,conversation_id,turn_id",
                (now(),),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "INSERT INTO events(namespace,environment,user_id,conversation_id,turn_id,type,payload_json) VALUES (%s,%s,%s,%s,%s,'TURN_UNKNOWN',%s::jsonb)",
                    (
                        *(
                            row[k]
                            for k in [
                                "namespace",
                                "environment",
                                "user_id",
                                "conversation_id",
                                "turn_id",
                            ]
                        ),
                        json.dumps(
                            {
                                "status": "UNKNOWN",
                                "errorCode": "HOST_RESTARTED",
                                "message": "上一轮在服务重启前未完成；未自动重放。",
                            }
                        ),
                    ),
                )
            return len(rows)

    @contextmanager
    def host_lock(self) -> Iterator[None]:
        key = int.from_bytes(
            sha256(("management-host:" + self.schema).encode()).digest()[:8], "big", signed=True
        )
        with self.connect(autocommit=True) as conn:
            if not conn.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (key,)).fetchone()[
                "acquired"
            ]:
                raise AgentError("MANAGEMENT_HOST_ALREADY_RUNNING")
            try:
                yield
            finally:
                conn.execute("SELECT pg_advisory_unlock(%s)", (key,))
