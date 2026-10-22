"""One transaction-local registry for product turns and client request aliases."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from skillweave_contracts.chat_state import TurnSource

from .errors import BsideError
from .persistence_types import DatabaseConnection, DatabaseRow, MessageRecord


def encoded(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class TurnRegistry:
    """Caller holds the conversation row lock and owns the commit boundary."""

    @staticmethod
    def insert(
        c: DatabaseConnection,
        *,
        user_id: int,
        environment: str,
        conversation_id: int,
        source_kind: TurnSource,
        source_key: str,
        source_digest: str,
        input_message: MessageRecord,
        assistant_message: MessageRecord,
        references: Sequence[Mapping[str, Any]] = (),
        processing_context: Mapping[str, Any] | None = None,
    ) -> DatabaseRow:
        task_id = processing_context["taskId"] if processing_context else None
        c.execute(
            "INSERT INTO chat_turns(user_id,environment,conversation_id,"
            "source_kind,source_key,source_digest,processing_task_id,input_message_id,assistant_message_id,"
            "run_references,processing_context) VALUES "
            "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) "
            "ON CONFLICT DO NOTHING",
            (
                user_id,
                environment,
                conversation_id,
                source_kind.value,
                source_key,
                source_digest,
                task_id,
                input_message["id"],
                assistant_message["id"],
                encoded(list(references)),
                encoded(processing_context),
            ),
        )
        row = c.execute(
            "SELECT * FROM chat_turns WHERE user_id=%s AND environment=%s AND conversation_id=%s "
            "AND source_kind=%s AND source_key=%s",
            (user_id, environment, conversation_id, source_kind.value, source_key),
        ).fetchone()
        # 冲突不覆盖输入、上下文或消息身份, 整个准入事务回滚。
        if (
            row is None
            or row["source_digest"] != source_digest
            or row["input_message_id"] != input_message["id"]
            or row["assistant_message_id"] != assistant_message["id"]
            or row["processing_task_id"] != task_id
        ):
            raise BsideError("CHAT_SOURCE_CONFLICT", 409)
        return row

    @staticmethod
    def map_request(
        c: DatabaseConnection,
        *,
        user_id: int,
        environment: str,
        conversation_id: int,
        request_id: str,
        payload: Mapping[str, Any],
        input_message: MessageRecord,
    ) -> None:
        request_digest = digest(payload)
        c.execute(
            "INSERT INTO chat_requests(user_id,environment,conversation_id,client_request_id,"
            "request_digest,input_message_id) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (
                user_id,
                environment,
                conversation_id,
                request_id,
                request_digest,
                input_message["id"],
            ),
        )
        row = c.execute(
            "SELECT request_digest,input_message_id FROM chat_requests "
            "WHERE user_id=%s AND environment=%s "
            "AND conversation_id=%s AND client_request_id=%s",
            (user_id, environment, conversation_id, request_id),
        ).fetchone()
        if (
            row is None
            or row["request_digest"] != request_digest
            or row["input_message_id"] != input_message["id"]
        ):
            raise BsideError("CHAT_REQUEST_CONFLICT", 409)
        # 一个处理来源可有多个客户端别名, 首个输入消息的展示标记保持稳定。
        c.execute(
            "UPDATE messages SET content=content || %s::jsonb "
            "WHERE id=%s AND NOT content ? 'clientRequestId'",
            (encoded({"clientRequestId": request_id}), input_message["id"]),
        )
