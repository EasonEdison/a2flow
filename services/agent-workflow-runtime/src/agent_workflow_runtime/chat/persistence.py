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
from langgraph.checkpoint.postgres import PostgresSaver

from ..service import require_owner


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_conversations (
    environment text NOT NULL,
    user_id text NOT NULL,
    conversation_id text NOT NULL,
    thread_id text NOT NULL UNIQUE,
    state text NOT NULL CHECK (state IN ('READY', 'RUNNING', 'FAILED')),
    last_turn_id text,
    PRIMARY KEY (environment, user_id, conversation_id)
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

    @contextmanager
    def session(self, owner, conversation_id, turn_id):
        require_owner(owner)
        if not isinstance(conversation_id, str) or not conversation_id:
            raise ValueError("CONVERSATION_ID_REQUIRED")
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("TURN_ID_REQUIRED")
        identity = (owner.environment, owner.user_id, conversation_id)
        lock_key = int.from_bytes(
            sha256(json.dumps(identity).encode()).digest()[:8], "big", signed=True,
        )
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
                if row["state"] != "READY":
                    raise ConversationAdmissionError("CONVERSATION_REQUIRES_REVIEW")
                if row["last_turn_id"] == turn_id:
                    raise ConversationAdmissionError("TURN_ALREADY_COMPLETED")
                saver = PostgresSaver(connection)
                if row["last_turn_id"] is not None and saver.get_tuple({
                    "configurable": {"thread_id": row["thread_id"]},
                }) is None:
                    raise ConversationAdmissionError("CONVERSATION_CHECKPOINT_MISSING")
                connection.execute(
                    "UPDATE agent_conversations SET state='RUNNING',last_turn_id=%s "
                    "WHERE environment=%s AND user_id=%s AND conversation_id=%s",
                    (turn_id, *identity),
                )
                try:
                    yield saver, row["thread_id"]
                except BaseException:
                    connection.execute(
                        "UPDATE agent_conversations SET state='FAILED' "
                        "WHERE environment=%s AND user_id=%s AND conversation_id=%s",
                        identity,
                    )
                    raise
                else:
                    connection.execute(
                        "UPDATE agent_conversations SET state='READY' "
                        "WHERE environment=%s AND user_id=%s AND conversation_id=%s",
                        identity,
                    )
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
