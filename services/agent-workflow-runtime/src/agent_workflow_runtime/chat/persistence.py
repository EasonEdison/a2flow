"""PostgreSQL conversation admission around the native LangGraph saver.

The session lock spans the entire worker turn, not the HTTP connection. A
crashed/incomplete turn is blocked instead of automatically replaying tools.
"""

from contextlib import contextmanager
from hashlib import sha256
import json
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from langgraph.checkpoint.postgres import PostgresSaver

from ..service import require_owner


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_conversations (
    environment text NOT NULL,
    user_id BIGINT NOT NULL,
    conversation_id text NOT NULL,
    thread_id text NOT NULL UNIQUE,
    state text NOT NULL CHECK (state IN ('READY', 'RUNNING', 'FAILED')),
    last_turn_id text,
    PRIMARY KEY (environment, user_id, conversation_id)
);
CREATE TABLE IF NOT EXISTS agent_chat_turns (
    environment text NOT NULL,
    user_id BIGINT NOT NULL,
    conversation_id text NOT NULL,
    turn_id text NOT NULL,
    state text NOT NULL CHECK (state IN ('RUNNING', 'COMPLETED', 'NEEDS_REVIEW')),
    events jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    PRIMARY KEY (environment, user_id, conversation_id, turn_id)
)
"""


class ConversationAdmissionError(Exception):
    pass


class ConversationStore:
    def __init__(self, conninfo):
        self._conninfo = conninfo

    def setup(self):
        with psycopg.connect(self._conninfo, autocommit=True,
                             connect_timeout=5) as connection:
            connection.execute(SCHEMA)
            PostgresSaver(connection).setup()

    @staticmethod
    def _identity(owner, conversation_id, turn_id):
        require_owner(owner)
        if not isinstance(conversation_id, str) or not conversation_id:
            raise ValueError("CONVERSATION_ID_REQUIRED")
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("TURN_ID_REQUIRED")
        identity = (owner.environment, owner.user_id, conversation_id)
        lock_key = int.from_bytes(
            sha256(json.dumps(identity).encode()).digest()[:8], "big", signed=True,
        )
        return identity, lock_key

    def inspect_turn(self, owner, conversation_id, turn_id):
        """Inspect facts under the execution lock; never infer safety from age.

        Missing turn evidence is retryable only if the whole conversation has no
        unfinished execution. Legacy completed turns without a replay payload
        remain review-only rather than being presented as new work.
        """
        identity, lock_key = self._identity(owner, conversation_id, turn_id)
        with psycopg.connect(self._conninfo, autocommit=True,
                             row_factory=dict_row, connect_timeout=5) as connection:
            acquired = connection.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired", (lock_key,),
            ).fetchone()["acquired"]
            if not acquired:
                return {"status": "BUSY", "events": []}
            try:
                turn = connection.execute(
                    "SELECT state,events FROM agent_chat_turns WHERE "
                    "environment=%s AND user_id=%s AND conversation_id=%s AND turn_id=%s",
                    (*identity, turn_id),
                ).fetchone()
                if turn:
                    if turn["state"] == "COMPLETED" and turn["events"]:
                        return {"status": "COMPLETED", "events": turn["events"]}
                    return {"status": "NEEDS_REVIEW", "events": []}
                conversation = connection.execute(
                    "SELECT state,last_turn_id FROM agent_conversations WHERE "
                    "environment=%s AND user_id=%s AND conversation_id=%s", identity,
                ).fetchone()
                if conversation and (conversation["state"] != "READY"
                                     or conversation["last_turn_id"] == turn_id):
                    return {"status": "NEEDS_REVIEW", "events": []}
                if conversation and conversation["last_turn_id"] is not None:
                    row = connection.execute(
                        "SELECT thread_id FROM agent_conversations WHERE environment=%s "
                        "AND user_id=%s AND conversation_id=%s", identity,
                    ).fetchone()
                    if PostgresSaver(connection).get_tuple({
                        "configurable": {"thread_id": row["thread_id"]},
                    }) is None:
                        return {"status": "NEEDS_REVIEW", "events": []}
                return {"status": "NOT_STARTED", "events": []}
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))

    @contextmanager
    def session(self, owner, conversation_id, turn_id, *, completion_events=None):
        identity, lock_key = self._identity(owner, conversation_id, turn_id)
        # A dedicated connection keeps this session-level lock through model IO.
        with psycopg.connect(self._conninfo, autocommit=True,
                             row_factory=dict_row, connect_timeout=5) as connection:
            locked = connection.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired", (lock_key,),
            ).fetchone()["acquired"]
            if not locked:
                raise ConversationAdmissionError("CONVERSATION_BUSY")
            try:
                connection.execute(
                    "INSERT INTO agent_conversations "
                    "(environment,user_id,conversation_id,thread_id,state) "
                    "VALUES (%s,%s,%s,%s,'READY') ON CONFLICT DO NOTHING",
                    (*identity, str(uuid4())),
                )
                row = connection.execute(
                    "SELECT thread_id,state,last_turn_id FROM agent_conversations "
                    "WHERE environment=%s AND user_id=%s AND conversation_id=%s",
                    identity,
                ).fetchone()
                prior = connection.execute(
                    "SELECT state FROM agent_chat_turns WHERE environment=%s "
                    "AND user_id=%s AND conversation_id=%s AND turn_id=%s",
                    (*identity, turn_id),
                ).fetchone()
                if prior and prior["state"] == "COMPLETED":
                    raise ConversationAdmissionError("TURN_ALREADY_COMPLETED")
                if prior or row["state"] != "READY":
                    raise ConversationAdmissionError("CONVERSATION_REQUIRES_REVIEW")
                if row["last_turn_id"] == turn_id:
                    raise ConversationAdmissionError("TURN_ALREADY_COMPLETED")
                saver = PostgresSaver(connection)
                if row["last_turn_id"] is not None and saver.get_tuple({
                    "configurable": {"thread_id": row["thread_id"]},
                }) is None:
                    raise ConversationAdmissionError("CONVERSATION_CHECKPOINT_MISSING")
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO agent_chat_turns "
                        "(environment,user_id,conversation_id,turn_id,state) "
                        "VALUES (%s,%s,%s,%s,'RUNNING')", (*identity, turn_id),
                    )
                    connection.execute(
                        "UPDATE agent_conversations SET state='RUNNING',last_turn_id=%s "
                        "WHERE environment=%s AND user_id=%s AND conversation_id=%s",
                        (turn_id, *identity),
                    )
                try:
                    yield saver, row["thread_id"]
                    if completion_events is not None and (
                        not completion_events or completion_events[-1].get("type") != "done"
                        or any(event.get("type") == "error" for event in completion_events)
                    ):
                        raise ConversationAdmissionError("TURN_COMPLETION_EVIDENCE_MISSING")
                    # Persist the final projection before releasing admission. A
                    # lost B-side response can now be repaired without agent IO.
                    with connection.transaction():
                        connection.execute(
                            "UPDATE agent_chat_turns SET state='COMPLETED',events=%s,"
                            "completed_at=now() WHERE environment=%s AND user_id=%s "
                            "AND conversation_id=%s AND turn_id=%s",
                            (Jsonb(completion_events or []), *identity, turn_id),
                        )
                        connection.execute(
                            "UPDATE agent_conversations SET state='READY' "
                            "WHERE environment=%s AND user_id=%s AND conversation_id=%s",
                            identity,
                        )
                except BaseException:
                    with connection.transaction():
                        connection.execute(
                            "UPDATE agent_chat_turns SET state='NEEDS_REVIEW' "
                            "WHERE environment=%s AND user_id=%s AND conversation_id=%s "
                            "AND turn_id=%s", (*identity, turn_id),
                        )
                        connection.execute(
                            "UPDATE agent_conversations SET state='FAILED' "
                            "WHERE environment=%s AND user_id=%s AND conversation_id=%s",
                            identity,
                        )
                    raise
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
