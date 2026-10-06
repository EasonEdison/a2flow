"""Opt-in real PostgreSQL tests. Use a disposable database, never live data."""

import os
import unittest
from uuid import uuid4

from langchain_core.messages import AIMessageChunk
from skillweave_contracts.models import TrustedContext
from agent_workflow_runtime.chat.persistence import (
    ConversationStore, ConversationAdmissionError,
)
from agent_workflow_runtime.chat.loop import ChatLoop
from test_chat_loop import FakeModel, FakeFactory, FakeMaterialPort, skill_material


@unittest.skipUnless(os.environ.get("A2FLOW_TEST_CHAT_DSN"), "disposable PG required")
class PostgresConversationTests(unittest.TestCase):
    def setUp(self):
        self.store = ConversationStore(os.environ["A2FLOW_TEST_CHAT_DSN"])
        self.store.setup()
        self.owner = TrustedContext(user_id=9223372036854775807, environment="PRT")
        self.conversation = str(uuid4())

    def turn(self, owner, turn_id, text, loader=None):
        # New store and model instance simulate a different worker process.
        store = ConversationStore(os.environ["A2FLOW_TEST_CHAT_DSN"])
        with store.session(owner, self.conversation, turn_id) as (saver, thread):
            loop = ChatLoop(
                model_factory=FakeFactory([FakeModel([AIMessageChunk(content="reply")])]),
                model_reference="deepseek-v4-flash", owner=owner,
                conversation_id=self.conversation,
                reader=FakeMaterialPort(skill_material()), control_request_id=turn_id,
                checkpointer=saver, thread_id=thread, history_loader=loader,
            )
            loop.turn(text)
            return thread, loop.history

    def test_rebuild_isolation_duplicate_and_migration(self):
        imports = []
        def loader():
            imports.append(True)
            return []
        first, _ = self.turn(self.owner, "1", "first", loader)
        second, messages = self.turn(self.owner, "2", "second", loader)
        self.assertEqual(first, second)
        self.assertEqual([True], imports)
        self.assertEqual(["first", "reply", "second", "reply"],
                         [m.content for m in messages])
        with self.assertRaisesRegex(ConversationAdmissionError, "TURN_ALREADY_COMPLETED"):
            self.turn(self.owner, "2", "second")
        for other in (
            TrustedContext(user_id=1005, environment="PRT"),
            TrustedContext(user_id=self.owner.user_id, environment="ONLINE"),
        ):
            thread, messages = self.turn(other, "1", "isolated")
            self.assertNotEqual(first, thread)
            self.assertEqual(["isolated", "reply"], [m.content for m in messages])

    def test_busy_and_failed_turn_never_replays(self):
        with self.assertRaisesRegex(RuntimeError, "fixture failure"):
            with self.store.session(self.owner, self.conversation, "1"):
                with self.assertRaisesRegex(ConversationAdmissionError, "CONVERSATION_BUSY"):
                    with self.store.session(self.owner, self.conversation, "2"):
                        self.fail("must not admit competing worker")
                raise RuntimeError("fixture failure")
        with self.assertRaisesRegex(ConversationAdmissionError, "CONVERSATION_REQUIRES_REVIEW"):
            self.turn(self.owner, "3", "must not replay")

    def test_fresh_identity_columns_are_bigint(self):
        import psycopg
        from importlib.resources import files
        from agent_workflow_runtime import postgres, postgres_lifecycle, postgres_progress
        with psycopg.connect(os.environ["A2FLOW_TEST_CHAT_DSN"], autocommit=True) as connection:
            connection.execute(files("a2flow_bside").joinpath("schema.sql").read_text())
            for group in (postgres.DDL, postgres_lifecycle.DDL, postgres_progress.DDL):
                for statement in group:
                    connection.execute(statement)
            rows = connection.execute(
                "SELECT table_name,column_name,data_type FROM information_schema.columns "
                "WHERE table_schema=%s AND column_name IN (%s,%s)",
                ("public", "user_id", "updated_by"),
            ).fetchall()
        self.assertGreaterEqual(len(rows), 14)
        for table, column, kind in rows:
            with self.subTest(table=table, column=column):
                self.assertEqual("bigint", kind)

    def test_legacy_migration_has_owner_cutoff_and_no_200_row_truncation(self):
        from importlib.resources import files
        import psycopg
        from psycopg.rows import dict_row
        from a2flow_bside.repositories import MessagesRepository
        dsn = os.environ["A2FLOW_TEST_CHAT_DSN"]
        with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as connection:
            connection.execute(files("a2flow_bside").joinpath("schema.sql").read_text())
            conversation = connection.execute(
                "INSERT INTO conversations(user_id) VALUES(%s) RETURNING id",
                (self.owner.user_id,),
            ).fetchone()["id"]
            connection.execute(
                "INSERT INTO messages(conversation_id,role,content) "
                "SELECT %s,'user',jsonb_build_object('text',repeat('x',5001)) "
                "FROM generate_series(1,250)", (conversation,),
            )
        repo = MessagesRepository(lambda: psycopg.connect(dsn, row_factory=dict_row))
        current = repo.append(conversation_id=conversation, role="user",
                              content={"text": "current", "delivery": "submitted"})
        rows = repo.legacy_history(self.owner.user_id, conversation, current["id"])
        self.assertEqual(250, len(rows))
        self.assertEqual(5001, len(rows[0]["content"]["text"]))
        self.assertEqual([], repo.legacy_history(1005, conversation, current["id"]))
        self.assertEqual(250, len(repo.legacy_history(
            self.owner.user_id, conversation, current["id"] + 1)))
