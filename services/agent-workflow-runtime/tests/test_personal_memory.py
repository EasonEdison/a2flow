import os
import unittest
from uuid import uuid4

from langchain_core.messages import AIMessageChunk
from skillweave_contracts.models import TrustedContext
from agent_workflow_runtime.personal_memory import PersonalMemory, MemoryConflict
from agent_workflow_runtime.chat.loop import ChatLoop
from test_chat_loop import FakeFactory, FakeModel, FakeMaterialPort, skill_material


class MemoryMiddlewareTests(unittest.TestCase):
    def test_preferences_are_dynamic_and_not_checkpoint_messages(self):
        class Memory:
            entries = [{"id": "tone", "text": "prefer concise answers"}]
            def for_agent(self, owner):
                self.owner = owner
                return self.entries
        memory = Memory()
        owner = TrustedContext(user_id="user-a", environment="PRT")
        model = FakeModel([AIMessageChunk(content="reply")])
        loop = ChatLoop(
            model_factory=FakeFactory([model]), model_reference="deepseek-v4-flash",
            owner=owner, conversation_id="one", reader=FakeMaterialPort(skill_material()),
            control_request_id="one", personal_memory=memory,
        )
        loop.turn("hello")
        self.assertEqual(owner, memory.owner)
        self.assertIn("prefer concise answers", str(model.observed[0][0].content))
        self.assertNotIn("prefer concise answers", str([m.content for m in loop.history]))
        memory.entries = []
        model2 = FakeModel([AIMessageChunk(content="reply")])
        loop2 = ChatLoop(
            model_factory=FakeFactory([model2]), model_reference="deepseek-v4-flash",
            owner=owner, conversation_id="two", reader=FakeMaterialPort(skill_material()),
            control_request_id="two", personal_memory=memory,
        )
        loop2.turn("hello again")
        self.assertNotIn("prefer concise answers", str(model2.observed[0][0].content))


@unittest.skipUnless(os.environ.get("A2FLOW_TEST_CHAT_DSN"), "disposable PG required")
class MemoryPostgresTests(unittest.TestCase):
    def test_native_store_controls_isolation_and_stale_write(self):
        memory = PersonalMemory(os.environ["A2FLOW_TEST_CHAT_DSN"])
        memory.setup()
        user = "user.name-" + str(uuid4())
        owner = TrustedContext(user_id=user, environment="PRT")
        self.assertEqual({"enabled": False, "revision": 0, "entries": []}, memory.view(owner))
        entry = {"id": "tone", "text": "concise"}
        memory.replace(owner, revision=0, enabled=True, entries=[entry])
        self.assertEqual([entry], memory.for_agent(owner))
        for other in (
            TrustedContext(user_id=user, environment="ONLINE"),
            TrustedContext(user_id="other", environment="PRT"),
        ):
            self.assertEqual([], memory.for_agent(other))
        memory.replace(owner, revision=1, enabled=False, entries=[entry])
        self.assertEqual([], memory.for_agent(owner))
        self.assertEqual([entry], memory.view(owner)["entries"])
        memory.replace(owner, revision=2, enabled=False, entries=[])
        with self.assertRaises(MemoryConflict):
            memory.replace(owner, revision=1, enabled=True, entries=[entry])
        restarted = PersonalMemory(os.environ["A2FLOW_TEST_CHAT_DSN"])
        self.assertEqual([], restarted.view(owner)["entries"])
        self.assertEqual(3, restarted.view(owner)["revision"])

    def test_input_limits(self):
        memory = PersonalMemory(os.environ["A2FLOW_TEST_CHAT_DSN"])
        owner = TrustedContext(user_id="fixture", environment="PRT")
        for entries in ([{"id": "../bad", "text": "x"}],
                        [{"id": "x", "text": "x"*1001}],
                        [{"id": "x", "text": "a"}, {"id": "x", "text": "b"}]):
            with self.assertRaises(ValueError):
                memory.replace(owner, revision=0, enabled=True, entries=entries)
