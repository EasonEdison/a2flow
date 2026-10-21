"""Crash-boundary checks with disposable PostgreSQL and scripted native Agent IO."""

import asyncio
import multiprocessing
import os
import unittest
from uuid import uuid4

from langchain_core.messages import AIMessageChunk
from skillweave_contracts import TrustedContext
from agent_workflow_runtime.chat.persistence import ConversationStore, ConversationAdmissionError
from deploy.attended.chat_runner import ChatLoopRunner
from test_chat_loop import FakeFactory, FakeModel, FakeMaterialPort, skill_material


def _crash_after_admission(dsn, conversation, admitted, release):
    store = ConversationStore(dsn)
    owner = TrustedContext(user_id=19001, environment="PRT")
    with store.session(owner, conversation, "1"):
        admitted.set()
        release.wait(10)
        os._exit(7)  # No context cleanup: emulate lost worker, not caught error.


@unittest.skipUnless(os.environ.get("A2FLOW_TEST_CHAT_DSN"), "disposable PG required")
class DurableChatRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ["A2FLOW_TEST_CHAT_DSN"]
        self.store = ConversationStore(self.dsn)
        self.store.setup()
        self.owner = TrustedContext(user_id=19001, environment="PRT")
        self.conversation = str(uuid4())

    def inspect(self, turn="1"):
        return self.store.inspect_turn(self.owner, self.conversation, turn)

    def test_native_completion_repairs_projection_without_model_reentry(self):
        model = FakeModel([AIMessageChunk(content="saved answer")])
        runner = ChatLoopRunner(
            model_factory=FakeFactory([model]), model_reference="deepseek-v4-flash",
            environment="PRT", reader=FakeMaterialPort(skill_material()),
            conversation_store=self.store, history_loader=lambda *args: [],
        )
        async def run(turn):
            return [e async for e in runner.iterate(
                user_id=self.owner.user_id, conversation_id=self.conversation,
                turn_id=turn, text="synthetic request")]
        self.assertEqual("NOT_STARTED", self.inspect()["status"])
        original = asyncio.run(run("1"))
        self.assertEqual("done", original[-1]["type"])
        # New worker can repair the entire delivery after the original transport
        # is gone; inspect does not instantiate or invoke a model.
        fresh = ConversationStore(self.dsn)
        recovered = fresh.inspect_turn(self.owner, self.conversation, "1")
        self.assertEqual({"status": "COMPLETED", "events": original}, recovered)
        calls = len(model.observed)
        duplicate = asyncio.run(run("1"))
        self.assertEqual("TURN_ALREADY_COMPLETED", duplicate[-1]["code"])
        self.assertEqual(calls, len(model.observed))
        self.assertEqual("NOT_STARTED", self.inspect("2")["status"])
        self.assertEqual("NOT_STARTED", fresh.inspect_turn(
            TrustedContext(user_id=19002, environment="PRT"), self.conversation, "1"
        )["status"])

    def test_lock_authority_and_crash_do_not_create_retry_permission(self):
        context = multiprocessing.get_context("fork")
        admitted, release = context.Event(), context.Event()
        process = context.Process(target=_crash_after_admission,
                                  args=(self.dsn, self.conversation, admitted, release))
        process.start()
        try:
            self.assertTrue(admitted.wait(10))
            self.assertEqual("BUSY", self.inspect()["status"])
            self.assertEqual("BUSY", self.inspect("2")["status"])
            release.set()
            process.join(10)
            self.assertEqual(7, process.exitcode)
            self.assertEqual("NEEDS_REVIEW", self.inspect()["status"])
            self.assertEqual("NEEDS_REVIEW", self.inspect("2")["status"])
            with self.assertRaisesRegex(ConversationAdmissionError, "REQUIRES_REVIEW"):
                with self.store.session(self.owner, self.conversation, "1"):
                    self.fail("crashed execution must not be replayed")
        finally:
            if process.is_alive():
                process.kill()
            process.join()

    def test_incomplete_terminal_evidence_never_releases_ready(self):
        with self.assertRaisesRegex(ConversationAdmissionError, "EVIDENCE_MISSING"):
            with self.store.session(self.owner, self.conversation, "1", completion_events=[]):
                pass
        self.assertEqual("NEEDS_REVIEW", self.inspect()["status"])

    def test_failed_turn_does_not_erase_older_completed_projection(self):
        events = [{"type": "waiting_action", "cardId": "synthetic-card"},
                  {"type": "done", "content": "", "finalModelMessageId": None}]
        with self.store.session(self.owner, self.conversation, "1", completion_events=events):
            pass
        # Test admission stops at missing checkpoint instead of guessing a new
        # agent run is safe. The completed projection remains recoverable.
        with self.assertRaisesRegex(ConversationAdmissionError, "CHECKPOINT_MISSING"):
            with self.store.session(self.owner, self.conversation, "2"):
                self.fail("must not recreate missing agent context")
        self.assertEqual(events, self.inspect()["events"])
        with self.assertRaisesRegex(ConversationAdmissionError, "TURN_ALREADY_COMPLETED"):
            with self.store.session(self.owner, self.conversation, "1"):
                self.fail("old turn cannot be admitted")
