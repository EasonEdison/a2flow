"""Native Chat execution facts, guarded by a session-wide PostgreSQL lock.

Product delivery is not stored here. Completed results can repair display, but
neither a missing checkpoint nor an unknown execution is automatically replayed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from hashlib import sha256
from typing import Any
from uuid import uuid4

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from skillweave_contracts import TrustedContext
from skillweave_contracts.chat_result import (
    ChatTurnResult,
    RuntimeTurnInspection,
    validate_result,
)

from ..service import require_owner

# 日常忙碌与阻断从轮次推导, 会话只拥有身份与检查点关联。
SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_conversations (
    environment text NOT NULL,
    user_id BIGINT NOT NULL,
    conversation_id text NOT NULL,
    thread_id text NOT NULL UNIQUE,
    PRIMARY KEY (environment, user_id, conversation_id)
);
CREATE TABLE IF NOT EXISTS agent_chat_turns (
    environment text NOT NULL,
    user_id BIGINT NOT NULL,
    conversation_id text NOT NULL,
    turn_id text NOT NULL,
    state text NOT NULL CHECK (state IN ('RUNNING', 'COMPLETED', 'NEEDS_REVIEW')),
    result jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    PRIMARY KEY (environment, user_id, conversation_id, turn_id)
)
"""


Connection = psycopg.Connection[dict[str, Any]]
Identity = tuple[str, int, str]


class ConversationAdmissionError(Exception):
    pass


class ConversationStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def setup(self) -> None:
        """Install the current schema; incompatible databases require explicit operator action."""
        with psycopg.connect(
            self._conninfo, autocommit=True, row_factory=dict_row, connect_timeout=5
        ) as connection:
            # 先核对全部结构,再创建表。不能把未知旧数据隐式清空或当作新库。
            expected = {
                "agent_conversations": {"environment", "user_id", "conversation_id", "thread_id"},
                "agent_chat_turns": {
                    "environment",
                    "user_id",
                    "conversation_id",
                    "turn_id",
                    "state",
                    "result",
                    "started_at",
                    "completed_at",
                },
            }
            for table, fields in expected.items():
                rows = connection.execute(
                    "SELECT column_name FROM information_schema.columns WHERE "
                    "table_schema=current_schema() AND table_name=%s",
                    (table,),
                ).fetchall()
                if rows and {row["column_name"] for row in rows} != fields:
                    raise ConversationAdmissionError("CHAT_STATE_SCHEMA_MISMATCH")
            connection.execute(SCHEMA)
            PostgresSaver(connection).setup()

    @staticmethod
    def _identity(
        owner: TrustedContext, conversation_id: str, turn_id: str
    ) -> tuple[Identity, int]:
        require_owner(owner)
        if not isinstance(conversation_id, str) or not conversation_id:
            raise ValueError("CONVERSATION_ID_REQUIRED")
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("TURN_ID_REQUIRED")
        identity = (owner.environment, owner.user_id, conversation_id)
        lock_key = int.from_bytes(
            sha256(json.dumps(identity).encode()).digest()[:8], "big", signed=True
        )
        return identity, lock_key

    @staticmethod
    def _blocked(
        connection: Connection, identity: Identity, conversation: Mapping[str, Any]
    ) -> str | None:
        # 即使检查目标轮次不存在,同一会话的未知执行也必须阻止新模型调用。
        turns = connection.execute(
            "SELECT state,result FROM agent_chat_turns WHERE environment=%s "
            "AND user_id=%s AND conversation_id=%s",
            identity,
        ).fetchall()
        if any(turn["state"] != "COMPLETED" for turn in turns):
            return "CONVERSATION_REQUIRES_REVIEW"
        for turn in turns:
            try:
                validate_result(turn["result"])
            except (ValueError, TypeError):
                return "CONVERSATION_RESULT_INVALID"
        checkpoint = PostgresSaver(connection).get_tuple(
            {
                "configurable": {"thread_id": conversation["thread_id"]},
            }
        )
        if turns and checkpoint is None:
            return "CONVERSATION_CHECKPOINT_MISSING"
        if not turns and checkpoint is not None:
            return "CONVERSATION_TURN_EVIDENCE_MISSING"
        return None

    def inspect_turn(
        self, owner: TrustedContext, conversation_id: str, turn_id: str
    ) -> RuntimeTurnInspection:
        identity, lock_key = self._identity(owner, conversation_id, turn_id)
        with psycopg.connect(
            self._conninfo, autocommit=True, row_factory=dict_row, connect_timeout=5
        ) as connection:
            acquired = connection.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired", (lock_key,)
            ).fetchone()
            if acquired is None or not acquired["acquired"]:
                return {"status": "BUSY"}
            try:
                turn = connection.execute(
                    "SELECT state,result FROM agent_chat_turns WHERE environment=%s "
                    "AND user_id=%s AND conversation_id=%s AND turn_id=%s",
                    (*identity, turn_id),
                ).fetchone()
                if turn:
                    if turn["state"] == "COMPLETED":
                        try:
                            result = validate_result(turn["result"])
                            if result["turnId"] != turn_id:
                                raise ValueError("CHAT_RESULT_TURN_ID_MISMATCH")
                            return {"status": "COMPLETED", "result": result}
                        except (ValueError, TypeError):
                            pass
                    return {"status": "NEEDS_REVIEW"}
                conversation = connection.execute(
                    "SELECT thread_id FROM agent_conversations WHERE "
                    "environment=%s AND user_id=%s AND conversation_id=%s",
                    identity,
                ).fetchone()
                if conversation and self._blocked(connection, identity, conversation):
                    return {"status": "NEEDS_REVIEW"}
                if (
                    conversation is None
                    and connection.execute(
                        "SELECT 1 FROM agent_chat_turns WHERE environment=%s AND user_id=%s "
                        "AND conversation_id=%s LIMIT 1",
                        identity,
                    ).fetchone()
                ):
                    return {"status": "NEEDS_REVIEW"}
                return {"status": "NOT_STARTED"}
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))

    @contextmanager
    def session(
        self,
        owner: TrustedContext,
        conversation_id: str,
        turn_id: str,
        *,
        completion_result: Callable[[], ChatTurnResult],
    ) -> Iterator[tuple[PostgresSaver, str]]:
        """Hold admission through native IO and complete result commit."""
        identity, lock_key = self._identity(owner, conversation_id, turn_id)
        with psycopg.connect(
            self._conninfo, autocommit=True, row_factory=dict_row, connect_timeout=5
        ) as connection:
            acquired = connection.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired", (lock_key,)
            ).fetchone()
            if acquired is None or not acquired["acquired"]:
                raise ConversationAdmissionError("CONVERSATION_BUSY")
            try:
                connection.execute(
                    "INSERT INTO agent_conversations "
                    "(environment,user_id,conversation_id,thread_id) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (*identity, str(uuid4())),
                )
                row = connection.execute(
                    "SELECT thread_id FROM agent_conversations WHERE "
                    "environment=%s AND user_id=%s AND conversation_id=%s",
                    identity,
                ).fetchone()
                if row is None:
                    raise ConversationAdmissionError("CONVERSATION_MISSING")
                prior = connection.execute(
                    "SELECT state FROM agent_chat_turns WHERE environment=%s AND user_id=%s "
                    "AND conversation_id=%s AND turn_id=%s",
                    (*identity, turn_id),
                ).fetchone()
                if prior and prior["state"] == "COMPLETED":
                    raise ConversationAdmissionError("TURN_ALREADY_COMPLETED")
                if prior:
                    raise ConversationAdmissionError("CONVERSATION_REQUIRES_REVIEW")
                blocked = self._blocked(connection, identity, row)
                if blocked:
                    raise ConversationAdmissionError(blocked)
                saver = PostgresSaver(connection)
                # RUNNING 是先于模型/工具的执行事实;崩溃后不能凭租约时间重新进入。
                connection.execute(
                    "INSERT INTO agent_chat_turns "
                    "(environment,user_id,conversation_id,turn_id,state) "
                    "VALUES (%s,%s,%s,%s,'RUNNING')",
                    (*identity, turn_id),
                )
                try:
                    yield saver, row["thread_id"]
                    result = validate_result(completion_result())
                    if result["turnId"] != turn_id:
                        raise ValueError("CHAT_RESULT_TURN_ID_MISMATCH")
                    # 在释放会话锁之前提交完整快照;B 端失败只能修复展示,不重跑原生轮次。
                    connection.execute(
                        "UPDATE agent_chat_turns SET state='COMPLETED',result=%s,"
                        "completed_at=now() WHERE environment=%s AND user_id=%s "
                        "AND conversation_id=%s AND turn_id=%s",
                        (Jsonb(result), *identity, turn_id),
                    )
                except BaseException:
                    connection.execute(
                        "UPDATE agent_chat_turns SET state='NEEDS_REVIEW' WHERE environment=%s "
                        "AND user_id=%s AND conversation_id=%s AND turn_id=%s",
                        (*identity, turn_id),
                    )
                    raise
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
