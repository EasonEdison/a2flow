"""Explicit, transactional B Chat v2 migration; no Agent/business execution.

Stop old writers and back up the database before calling this operation. Conflicts
roll back the whole migration. Archived legacy rows remain in this database;
cleanup=True is an explicit irreversible schema cutover, requiring that backup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .persistence_types import ConnectionFactory, DatabaseConnection, DatabaseRow
from .turn_registry import encoded

_VERSION = "chat-state-v2"
_TABLES = ("chat_turns", "processing_turns", "chat_requests", "chat_continuations")


def _conflict(code: str) -> None:
    # 错误只带稳定分类，不把用户输入或真实结果写入日志。
    raise ValueError("CHAT_MIGRATION_CONFLICT:" + code)


def _pair(c: DatabaseConnection, row: DatabaseRow) -> tuple[DatabaseRow, DatabaseRow]:
    rows = c.execute(
        "SELECT m.*,c.user_id FROM messages m JOIN conversations c ON c.id=m.conversation_id "
        "WHERE m.id IN (%s,%s)",
        (row["input_message_id"], row["assistant_message_id"]),
    ).fetchall()
    by_id = {m["id"]: m for m in rows}
    user = by_id.get(row["input_message_id"])
    assistant = by_id.get(row["assistant_message_id"])
    if (
        user is None
        or assistant is None
        or user["role"] != "user"
        or assistant["role"] != "assistant"
        or any(
            m["user_id"] != row["user_id"] or m["conversation_id"] != row["conversation_id"]
            for m in rows
        )
    ):
        _conflict("MESSAGE_PAIR")
    assert user is not None and assistant is not None
    return user, assistant


def _context(c: DatabaseConnection, row: DatabaseRow) -> dict[str, Any]:
    task = c.execute(
        "SELECT * FROM processing_tasks WHERE task_id=%s", (row["task_id"],)
    ).fetchone()
    if task is None or any(
        task[k] != row[k] for k in ("user_id", "environment", "conversation_id")
    ):
        _conflict("PROCESSING_SCOPE")
    assert task is not None
    return {
        "taskId": task["task_id"],
        "activityId": task["activity_id"],
        "runId": task["run_id"],
        "attentionId": task["attention_id"],
        "conversationId": str(task["conversation_id"]),
        "objective": task["objective"],
        "status": task["status"],
    }


def migrate_chat_state(factory: ConnectionFactory, *, cleanup: bool = False) -> dict[str, int]:
    """Install/backfill/cut over atomically; no historical execution is authorized."""
    result = {"turns": 0, "blocked": 0, "requests": 0, "continuations": 0}
    with factory() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtextextended('chat-state-v2',0))")
        c.execute(
            "CREATE TABLE IF NOT EXISTS chat_schema_migrations(version text PRIMARY KEY,applied_at timestamptz NOT NULL DEFAULT now(),cleaned boolean NOT NULL DEFAULT false)"
        )
        applied = c.execute(
            "SELECT cleaned FROM chat_schema_migrations WHERE version=%s", (_VERSION,)
        ).fetchone()
        if applied and (not cleanup or applied["cleaned"]):
            return result
        if not applied:
            # 先冻结旧表快照，再建缺失的产品结构；归档仅存本库，不输出业务数据。
            c.execute(
                "CREATE TABLE IF NOT EXISTS chat_migration_archive(version text NOT NULL,table_name text NOT NULL,row_number bigint NOT NULL,document jsonb NOT NULL,PRIMARY KEY(version,table_name,row_number))"
            )
            for table in _TABLES:
                exists = c.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
                assert exists is not None
                if exists["name"]:
                    c.execute(
                        f"INSERT INTO chat_migration_archive SELECT %s,%s,row_number() OVER (),to_jsonb(t) FROM {table} t",
                        (_VERSION, table),
                    )
            c.execute(Path(__file__).with_name("schema.sql").read_text())
            c.execute(
                "ALTER TABLE chat_turns ADD COLUMN IF NOT EXISTS source_kind text, ADD COLUMN IF NOT EXISTS source_key text, ADD COLUMN IF NOT EXISTS source_digest text, ADD COLUMN IF NOT EXISTS processing_task_id text REFERENCES processing_tasks(task_id)"
            )
            c.execute(
                "ALTER TABLE chat_turns ALTER COLUMN request_id DROP NOT NULL, ALTER COLUMN request_digest DROP NOT NULL"
            )
            c.execute("ALTER TABLE chat_requests ALTER COLUMN assistant_message_id DROP NOT NULL")
            c.execute("ALTER TABLE chat_continuations ADD COLUMN IF NOT EXISTS state text")
            processing = {
                p["input_message_id"]: p
                for p in c.execute("SELECT * FROM processing_turns").fetchall()
            }
            turns = c.execute("SELECT * FROM chat_turns ORDER BY input_message_id").fetchall()
            for row in turns:
                _pair(c, row)
                if row["source_kind"] is not None and row["request_id"] is None:
                    # 新版本登记的来源已经自洽，不再要求旧 processing_turns 的副本。
                    if row["processing_task_id"]:
                        context = _context(c, {**row, "task_id": row["processing_task_id"]})
                        if (
                            row["processing_context"] is None
                            or row["processing_context"].get("taskId") != context["taskId"]
                        ):
                            _conflict("PROCESSING_CONTEXT")
                    continue
                prefix, sep, key = row["request_id"].partition(":")
                kinds = {
                    "message": "USER_MESSAGE",
                    "processing": "PROCESSING",
                    "card": "CARD_CONTINUATION",
                }
                if not sep or prefix not in kinds or not key:
                    _conflict("SOURCE_IDENTITY")
                old = processing.pop(row["input_message_id"], None)
                task_id, context = None, row["processing_context"]
                digest = row["request_digest"]
                if old:
                    if (
                        any(
                            old[k] != row[k]
                            for k in (
                                "user_id",
                                "environment",
                                "conversation_id",
                                "assistant_message_id",
                            )
                        )
                        or old["request_id"] != ("card:" + key if prefix == "card" else key)
                        or prefix not in {"card", "processing"}
                    ):
                        _conflict("PROCESSING_TURN")
                    task_id = old["task_id"]
                    actual = _context(c, old)
                    if context is not None and context.get("taskId") != task_id:
                        _conflict("PROCESSING_CONTEXT")
                    context = context or actual
                    digest = old["request_digest"]
                elif context is not None:
                    _conflict("PROCESSING_EVIDENCE_MISSING")
                if prefix == "processing" and task_id is None:
                    _conflict("PROCESSING_EVIDENCE_MISSING")
                if row["source_kind"] is not None and (
                    row["source_kind"] != kinds[prefix]
                    or row["source_key"] != key
                    or row["source_digest"] != digest
                    or row["processing_task_id"] != task_id
                ):
                    _conflict("SOURCE_ALREADY_DIFFERENT")
                c.execute(
                    "UPDATE chat_turns SET source_kind=%s,source_key=%s,source_digest=%s,processing_task_id=%s,processing_context=%s::jsonb WHERE input_message_id=%s",
                    (
                        kinds[prefix],
                        key,
                        digest,
                        task_id,
                        encoded(context),
                        row["input_message_id"],
                    ),
                )
                result["turns"] += 1
            # 更老部署只有处理轮次：保留消息与真实业务回执，但没有原生轮次证据不能重跑。
            for row in processing.values():
                user, _ = _pair(c, row)
                context = _context(c, row)
                is_card = row["request_id"].startswith("card:")
                key = row["request_id"][5:] if is_card else row["request_id"]
                c.execute(
                    "INSERT INTO chat_turns(input_message_id,assistant_message_id,user_id,environment,conversation_id,request_id,request_digest,source_kind,source_key,source_digest,processing_task_id,processing_context,run_references,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,'NEEDS_REVIEW')",
                    (
                        row["input_message_id"],
                        row["assistant_message_id"],
                        row["user_id"],
                        row["environment"],
                        row["conversation_id"],
                        "card:" + key if is_card else "processing:" + key,
                        row["request_digest"],
                        "CARD_CONTINUATION" if is_card else "PROCESSING",
                        key,
                        row["request_digest"],
                        row["task_id"],
                        encoded(context),
                        encoded(user["content"].get("runReferences", [])),
                    ),
                )
                result["blocked"] += 1
            for row in c.execute("SELECT * FROM chat_requests").fetchall():
                turn = c.execute(
                    "SELECT * FROM chat_turns WHERE input_message_id=%s", (row["input_message_id"],)
                ).fetchone()
                if turn is None:
                    _pair(c, row)
                    c.execute(
                        "INSERT INTO chat_turns(input_message_id,assistant_message_id,user_id,environment,conversation_id,request_id,request_digest,source_kind,source_key,source_digest,status) VALUES(%s,%s,%s,%s,%s,%s,%s,'USER_MESSAGE',%s,%s,'NEEDS_REVIEW')",
                        (
                            row["input_message_id"],
                            row["assistant_message_id"],
                            row["user_id"],
                            row["environment"],
                            row["conversation_id"],
                            "message:" + row["client_request_id"],
                            row["request_digest"],
                            row["client_request_id"],
                            row["request_digest"],
                        ),
                    )
                    result["blocked"] += 1
                elif any(
                    row[k] != turn[k] for k in ("user_id", "environment", "conversation_id")
                ) or row["assistant_message_id"] not in (None, turn["assistant_message_id"]):
                    _conflict("REQUEST_MAPPING")
                result["requests"] += 1
            c.execute(
                "UPDATE chat_continuations SET state=CASE WHEN materialized THEN 'MATERIALIZED' WHEN recovery_status='NEEDS_REVIEW' THEN 'NEEDS_REVIEW' ELSE 'PENDING' END WHERE state IS NULL"
            )
            result["continuations"] = c.execute(
                "SELECT count(*) AS n FROM chat_continuations"
            ).fetchone()["n"]
            c.execute(
                "ALTER TABLE chat_turns ALTER COLUMN source_kind SET NOT NULL,ALTER COLUMN source_key SET NOT NULL,ALTER COLUMN source_digest SET NOT NULL"
            )
            c.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS chat_turns_source ON chat_turns(user_id,environment,conversation_id,source_kind,source_key)"
            )
            c.execute(
                "ALTER TABLE chat_continuations ALTER COLUMN state SET NOT NULL,ALTER COLUMN state SET DEFAULT 'PENDING'"
            )
            c.execute("INSERT INTO chat_schema_migrations(version) VALUES(%s)", (_VERSION,))
        if cleanup:
            # 仅显式离线清理旧结构；归档和外部备份是回退依据，绝不 DROP CASCADE。
            c.execute("DROP TABLE IF EXISTS processing_turns")
            c.execute(
                "ALTER TABLE chat_turns DROP COLUMN IF EXISTS request_id,DROP COLUMN IF EXISTS request_digest"
            )
            c.execute("ALTER TABLE chat_requests DROP COLUMN IF EXISTS assistant_message_id")
            c.execute(
                "ALTER TABLE chat_continuations DROP COLUMN IF EXISTS materialized,DROP COLUMN IF EXISTS recovery_status"
            )
            c.execute(
                "UPDATE chat_schema_migrations SET cleaned=true WHERE version=%s", (_VERSION,)
            )
    return result
