"""Offline card lifecycle contract plus opt-in disposable PostgreSQL coverage."""

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from threading import RLock
import unittest
from uuid import uuid4

from skillweave_contracts import TrustedContext

from agent_workflow_runtime.application_runtime import PreparedApplication
from agent_workflow_runtime.chat.cards import ActionObservation, ChatCardStore
from agent_workflow_runtime.models import ActionRejected


def prepared(*, interactive=True, prompt="Choose"):
    display = {
        "applicationKey": "choice-card", "applicationVersion": "version-1",
        "protocolProfile": "a2flow.mvp08.v1", "componentCatalogRef": "catalog-1",
        "rootId": "root", "components": [{"id": "root", "component": "Text"}],
        "data": {"prompt": prompt, "options": [
            {"label": "First", "value": "first"},
            {"label": "Second", "value": "second"},
        ]},
        "inputSchema": {"type": "object"},
        "actions": ([{"actionName": "confirm", "inputSchema": {"type": "object"}}]
                    if interactive else []),
    }
    return PreparedApplication("choice-card", "version-1", interactive,
        json.dumps(display, sort_keys=True, separators=(",", ":")))


def metadata(conversation="conversation-1", *, tool_call="tool-1"):
    return {"skillKey": "assistant/choice",
            "conversationId": conversation, "controlRequestId": "turn-1",
            "toolCallId": tool_call,
            "observation": {"description": "Choose one option",
                            "arguments": {"prompt": "Choose"}},
            "binding": {"operationRef": "ability.confirm", "secret": "server-only"}}


class MemoryStorage:
    """Test-only, rollback-capable backend; production has no memory fallback."""

    def __init__(self):
        self.cards, self.requests, self.order = {}, {}, []
        self.observations, self.observation_heads = {}, {}
        self.lock, self.setup_called = RLock(), False

    def setup(self):
        self.setup_called = True

    @contextmanager
    def transaction(self):
        with self.lock:
            snapshot = deepcopy((self.cards, self.requests, self.order,
                                 self.observations, self.observation_heads))
            try:
                yield MemoryTransaction(self)
            except BaseException:
                (self.cards, self.requests, self.order, self.observations,
                 self.observation_heads) = snapshot
                raise


class MemoryTransaction:
    def __init__(self, storage):
        self.storage = storage

    @staticmethod
    def card_key(scope, card_id):
        return (*scope, card_id)

    def insert_card(self, card):
        key = self.card_key((card["environment"], card["user_id"],
                             card["conversation_id"]), card["card_id"])
        if key in self.storage.cards:
            return False
        self.storage.cards[key] = deepcopy(card)
        self.storage.order.append(key)
        return True

    def get_card(self, scope, card_id, lock=False):
        value = self.storage.cards.get(self.card_key(scope, card_id))
        return None if value is None else deepcopy(value)

    def list_cards(self, scope):
        return [deepcopy(self.storage.cards[key]) for key in self.storage.order
                if key[:3] == scope]

    def update_card(self, card):
        key = self.card_key((card["environment"], card["user_id"],
                             card["conversation_id"]), card["card_id"])
        if key not in self.storage.cards:
            raise AssertionError("missing card")
        self.storage.cards[key] = deepcopy(card)

    def insert_request(self, request):
        key = (request["environment"], request["user_id"],
               request["conversation_id"], request["card_id"], request["request_id"])
        if key in self.storage.requests:
            raise AssertionError("duplicate request")
        self.storage.requests[key] = deepcopy(request)

    def get_request(self, scope, card_id, request_id, lock=False):
        value = self.storage.requests.get((*scope, card_id, request_id))
        return None if value is None else deepcopy(value)

    def update_request(self, request):
        key = (request["environment"], request["user_id"],
               request["conversation_id"], request["card_id"], request["request_id"])
        if key not in self.storage.requests:
            raise AssertionError("missing request")
        self.storage.requests[key] = deepcopy(request)

    def append_observation(self, scope, event_id, payload):
        event_key = (*scope, event_id)
        existing = self.storage.observations.get(event_key)
        if existing is not None:
            if existing["payload"] != payload:
                raise AssertionError("observation conflict")
            return deepcopy(existing)
        sequence = self.storage.observation_heads.get(scope, 1)
        self.storage.observation_heads[scope] = sequence + 1
        row = {"sequence": sequence, "event_id": event_id,
               "payload": deepcopy(payload)}
        self.storage.observations[event_key] = row
        return deepcopy(row)

    def list_observations(self, scope, after_sequence, limit):
        rows = [deepcopy(value) for key, value in self.storage.observations.items()
                if key[:3] == scope and value["sequence"] > after_sequence]
        return sorted(rows, key=lambda item: item["sequence"])[:limit]


class ChatCardContract:
    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        self.store = self.make_store()
        self.store.setup()
        self.owner = TrustedContext(1009, "PRT")
        self.conversation = "conversation-" + uuid4().hex

    def save(self, **kwargs):
        values = metadata(self.conversation, **kwargs)
        return self.store.save(self.owner, self.conversation, prepared(), values)

    def assert_code(self, code, operation):
        with self.assertRaises(ActionRejected) as raised:
            operation()
        self.assertEqual(code, raised.exception.code)

    def test_save_is_deterministic_isolated_and_public(self):
        source = metadata(self.conversation)
        card = self.store.save(self.owner, self.conversation, prepared(), source)
        source["binding"]["secret"] = "changed"
        self.assertEqual({"cardId", "conversationId", "display", "status"},
                         set(card))
        self.assertEqual("WAITING_ACTION", card["status"])
        self.assertEqual(card, self.store.save(
            self.owner, self.conversation, prepared(), metadata(self.conversation)))
        self.assertEqual([card], self.store.list(self.owner, self.conversation))
        self.assertEqual(card, self.store.read(self.owner, self.conversation,
                                               card["cardId"]))
        internal = self.store.get_binding(self.owner, self.conversation, card["cardId"])
        self.assertEqual("server-only", internal["metadata"]["binding"]["secret"])
        self.assertEqual([], self.store.list(TrustedContext(1010, "PRT"),
                                             self.conversation))
        self.assertIsNone(self.store.read(self.owner, self.conversation + "-other",
                                          card["cardId"]))
        self.assert_code("CARD_REPLAY_CONFLICT", lambda: self.store.save(
            self.owner, self.conversation, prepared(prompt="Changed"),
            metadata(self.conversation)))

    def test_chat_card_exposes_durable_turn_relation_without_internal_metadata(self):
        values = metadata(self.conversation)
        values["controlRequestId"] = "chat-42"

        card = self.store.save(
            self.owner, self.conversation, prepared(), values,
        )

        self.assertEqual("42", card["turnId"])
        self.assertNotIn("controlRequestId", card)
        self.assertEqual("42", self.store.read(
            self.owner, self.conversation, card["cardId"],
        )["turnId"])

    def test_claim_commits_before_dispatch_and_finish_is_idempotent(self):
        card = self.save()
        claim = self.store.claim(self.owner, self.conversation, card["cardId"],
            "request-1", "confirm", {"optionId": "second", "ignored": "not-patched"})
        self.assertTrue(claim["dispatch"])
        self.assertEqual("EXECUTING", claim["card"]["status"])
        self.assert_code("ACTION_REQUEST_BUSY", lambda: self.store.claim(
            self.owner, self.conversation, card["cardId"], "request-1", "confirm",
            {"optionId": "second", "ignored": "not-patched"}))
        result = {"accepted": True, "receipt": "business-result"}
        finished = self.store.finish(self.owner, self.conversation, card["cardId"],
                                     "request-1", result, True, True)
        self.assertEqual("COMPLETED", finished["status"])
        self.assertEqual(result, finished["result"])
        self.assertEqual("second", finished["display"]["data"]["optionId"])
        self.assertNotIn("ignored", finished["display"]["data"])
        self.assertEqual(finished, self.store.finish(
            self.owner, self.conversation, card["cardId"], "request-1",
            result, True, True))
        cached = self.store.claim(self.owner, self.conversation, card["cardId"],
            "request-1", "confirm", {"optionId": "second", "ignored": "not-patched"})
        self.assertFalse(cached["dispatch"])
        self.assertEqual(result, cached["result"])
        self.assert_code("ACTION_REQUEST_CONFLICT", lambda: self.store.claim(
            self.owner, self.conversation, card["cardId"], "request-1", "confirm",
            {"optionId": "first"}))
        observations = self.store.list_observations(
            self.owner, self.conversation, after_sequence=0)
        self.assertEqual(["RENDERED", "ACTION"], [item.kind for item in observations])
        self.assertEqual([1, 2], [item.sequence for item in observations])
        self.assertEqual("request-1", observations[1].request_id)
        self.assertIsNone(observations[1].arguments)
        self.assertEqual(result, observations[1].result)

    def test_business_failure_waits_and_accepts_a_new_request(self):
        card = self.save()
        self.store.claim(self.owner, self.conversation, card["cardId"],
                         "request-1", "confirm", {})
        waiting = self.store.finish(self.owner, self.conversation, card["cardId"],
            "request-1", {"accepted": False}, False, True)
        self.assertEqual("WAITING_ACTION", waiting["status"])
        claim = self.store.claim(self.owner, self.conversation, card["cardId"],
                                 "request-2", "confirm", {})
        self.assertEqual("EXECUTING", claim["card"]["status"])

    def test_exception_marks_unknown_and_never_redispatches(self):
        card = self.save()
        self.store.claim(self.owner, self.conversation, card["cardId"],
                         "request-1", "confirm", {})
        failed = self.store.fail(self.owner, self.conversation, card["cardId"],
                                 "request-1", "BUSINESS_DISPATCH_EXCEPTION")
        self.assertEqual("UNKNOWN", failed["status"])
        self.assertNotIn("result", failed)
        self.assertEqual(failed, self.store.fail(
            self.owner, self.conversation, card["cardId"], "request-1",
            "BUSINESS_DISPATCH_EXCEPTION"))
        self.assert_code("ACTION_OUTCOME_UNKNOWN", lambda: self.store.claim(
            self.owner, self.conversation, card["cardId"], "request-1", "confirm", {}))
        self.assert_code("CARD_TERMINAL", lambda: self.store.claim(
            self.owner, self.conversation, card["cardId"], "request-2", "confirm", {}))
        self.assert_code("ACTION_FAILURE_CONFLICT", lambda: self.store.fail(
            self.owner, self.conversation, card["cardId"], "request-1", "OTHER_ERROR"))
        observations = self.store.list_observations(
            self.owner, self.conversation, after_sequence=1)
        self.assertEqual(1, len(observations))
        self.assertEqual("UNKNOWN", observations[0].status)
        self.assertEqual("BUSINESS_DISPATCH_EXCEPTION", observations[0].error_code)

    def test_selection_and_ingress_are_fail_closed(self):
        card = self.save()
        self.store.claim(self.owner, self.conversation, card["cardId"],
                         "request-1", "confirm", {"optionId": "missing"})
        self.assert_code("INVALID_OPTION_ID", lambda: self.store.finish(
            self.owner, self.conversation, card["cardId"], "request-1", {}, True, True))
        self.assertEqual("EXECUTING", self.store.read(
            self.owner, self.conversation, card["cardId"])["status"])
        self.assertEqual(["RENDERED"], [item.kind for item in self.store.list_observations(
            self.owner, self.conversation, after_sequence=0)])
        self.assert_code("CARD_ENVIRONMENT_MISMATCH", lambda: self.store.list(
            TrustedContext(self.owner.user_id, "ONLINE"), self.conversation))
        self.assert_code("TRUSTED_CONTEXT_REQUIRED", lambda: self.store.list(
            {"userId": self.owner.user_id, "environment": "PRT"}, self.conversation))

    def test_display_only_has_no_action_lifecycle(self):
        card = self.store.save(self.owner, self.conversation, prepared(interactive=False),
                               metadata(self.conversation))
        self.assertEqual("DISPLAY_ONLY", card["status"])
        self.assert_code("CARD_NOT_ACTIONABLE", lambda: self.store.claim(
            self.owner, self.conversation, card["cardId"], "request-1",
            "confirm", {}))


class OfflineChatCardTests(ChatCardContract, unittest.TestCase):
    def test_rpc_display_action_persists_snapshot_and_private_session_atomically(self):
        base = prepared(interactive=False)
        display = base.display()
        display["protocolProfile"] = "a2flow.java-rpc.v1"
        display["snapshotMessages"] = [{"surface": "before"}]
        display["actions"] = [{"surfaceId": "main", "componentId": "button", "actionName": "save"}]
        value = PreparedApplication(base.application_key, base.application_version, False, json.dumps(display))
        private = metadata(self.conversation)
        private.update(applicationKey=base.application_key, applicationVersion=base.application_version,
                       rpc={"session": {"token": "private-session"}})
        saved = self.store.save(self.owner, self.conversation, value, private)
        inputs = {"surfaceId": "main", "sourceComponentId": "button", "context": {"amount": "9223372036854775807"}}
        claim = self.store.claim(self.owner, self.conversation, saved["cardId"], "rpc-request", "save", inputs)
        self.assertTrue(claim["dispatch"])
        display["snapshotMessages"] = [{"surface": "after"}]
        value = PreparedApplication(base.application_key, base.application_version, False, json.dumps(display))
        observation = ActionObservation(
            description="Save manuscript",
            arguments={"title": "Nested", "body": {"text": "safe"}},
            result={"artifactId": "artifact-1"},
            capability_success=True,
            business_success=True,
        )
        done = self.store.finish(self.owner, self.conversation, saved["cardId"], "rpc-request", {"saved": True},
                                 True, False, prepared=value, binding_metadata=private,
                                 observation=observation)
        self.assertEqual(done["status"], "DISPLAY_ONLY")
        self.assertEqual(done["display"]["snapshotMessages"], [{"surface": "after"}])
        self.assertNotIn("private-session", json.dumps(done))
        self.assertEqual(self.store.replay(self.owner, self.conversation, saved["cardId"],
                                          "rpc-request", "save", inputs), done)
        self.assertEqual(self.store.get_binding(self.owner, self.conversation, saved["cardId"])["metadata"], private)
        observed = self.store.list_observations(
            self.owner, self.conversation, after_sequence=1)[0]
        self.assertEqual(observation.arguments, observed.arguments)
        self.assertEqual(observation.result, observed.result)
        self.assertTrue(observed.capability_success)
        self.assertTrue(observed.business_success)
        self.assertNotIn("private-session", json.dumps(observed.result))

    def make_store(self):
        self.memory = MemoryStorage()
        return ChatCardStore("unused-test-dsn", environment="PRT",
                             _storage=self.memory)


@unittest.skipUnless(os.environ.get("A2FLOW_TEST_CHAT_CARDS_DSN"),
                     "disposable PG required")
class PostgresChatCardTests(ChatCardContract, unittest.TestCase):
    def make_store(self):
        return ChatCardStore(os.environ["A2FLOW_TEST_CHAT_CARDS_DSN"],
                             environment="PRT")

    def test_claim_survives_new_store_without_redispatch(self):
        card = self.save()
        self.store.claim(self.owner, self.conversation, card["cardId"],
                         "request-crash", "confirm", {})
        restarted = self.make_store()
        self.assert_code("ACTION_REQUEST_BUSY", lambda: restarted.claim(
            self.owner, self.conversation, card["cardId"], "request-crash",
            "confirm", {}))
        executing = restarted.read(self.owner, self.conversation, card["cardId"])
        self.assertEqual("EXECUTING", executing["status"])
        unknown = restarted.fail(self.owner, self.conversation, card["cardId"],
                                  "request-crash", "PROCESS_TERMINATED")
        self.assertEqual("UNKNOWN", unknown["status"])

    def test_concurrent_cards_allocate_one_committed_conversation_sequence(self):
        first = self.save(tool_call="tool-concurrent-1")
        second = self.save(tool_call="tool-concurrent-2")
        self.store.claim(self.owner, self.conversation, first["cardId"],
                         "request-concurrent-1", "confirm", {})
        self.store.claim(self.owner, self.conversation, second["cardId"],
                         "request-concurrent-2", "confirm", {})

        def finish(card_id, request_id):
            return self.store.finish(
                self.owner, self.conversation, card_id, request_id,
                {"requestId": request_id}, True, True,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(finish, first["cardId"], "request-concurrent-1"),
                pool.submit(finish, second["cardId"], "request-concurrent-2"),
            ]
            for future in futures:
                future.result(timeout=5)

        observations = self.store.list_observations(
            self.owner, self.conversation, after_sequence=0,
        )
        self.assertEqual([1, 2, 3, 4], [item.sequence for item in observations])
        self.assertEqual(4, len({item.event_id for item in observations}))


if __name__ == "__main__":
    unittest.main()
