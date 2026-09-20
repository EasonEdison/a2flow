"""Offline card lifecycle contract plus opt-in disposable PostgreSQL coverage."""

from contextlib import contextmanager
from copy import deepcopy
import json
import os
from threading import RLock
import unittest
from uuid import uuid4

from skillweave_contracts import TrustedContext

from agent_workflow_runtime.application_runtime import PreparedApplication
from agent_workflow_runtime.chat.cards import ChatCardStore
from agent_workflow_runtime.models import ActionRejected


def prepared(*, interactive=True, prompt="Choose"):
    display = {
        "applicationKey": "choice-card", "applicationVersion": "version-1",
        "protocolProfile": "a2flow.mvp08.v1", "componentCatalogRef": "catalog-1",
        "rootId": "root", "components": [{"id": "root", "component": "Text"}],
        "data": {"prompt": prompt, "options": [
            {"label": "First", "optionId": "first"},
            {"label": "Second", "optionId": "second"},
        ]},
        "inputSchema": {"type": "object"},
        "actions": ([{"actionName": "confirm", "inputSchema": {"type": "object"}}]
                    if interactive else []),
    }
    return PreparedApplication("choice-card", "version-1", interactive,
        json.dumps(display, sort_keys=True, separators=(",", ":")))


def metadata(conversation="conversation-1", *, tool_call="tool-1"):
    return {"skillKey": "assistant/choice",
            "recordedVersions": [["SKILL:assistant/choice", "version-1"],
                                 ["APPLICATION:choice-card", "version-1"]],
            "conversationId": conversation, "controlRequestId": "turn-1",
            "toolCallId": tool_call,
            "binding": {"operationRef": "ability.confirm", "secret": "server-only"}}


class MemoryStorage:
    """Test-only, rollback-capable backend; production has no memory fallback."""

    def __init__(self):
        self.cards, self.requests, self.order = {}, {}, []
        self.lock, self.setup_called = RLock(), False

    def setup(self):
        self.setup_called = True

    @contextmanager
    def transaction(self):
        with self.lock:
            snapshot = deepcopy((self.cards, self.requests, self.order))
            try:
                yield MemoryTransaction(self)
            except BaseException:
                self.cards, self.requests, self.order = snapshot
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
        self.assertEqual({"cardId", "conversationId", "display", "status", "revision"},
                         set(card))
        self.assertEqual("WAITING_ACTION", card["status"])
        self.assertEqual(0, card["revision"])
        self.assertEqual(card, self.store.save(
            self.owner, self.conversation, prepared(), metadata(self.conversation)))
        self.assertEqual([card], self.store.list(self.owner, self.conversation))
        self.assertEqual(card, self.store.read(self.owner, self.conversation,
                                               card["cardId"]))
        internal = self.store.get_binding(self.owner, self.conversation, card["cardId"])
        self.assertEqual("server-only", internal["metadata"]["binding"]["secret"])
        internal["metadata"]["recordedVersions"].clear()
        self.assertEqual(2, len(self.store.get_binding(
            self.owner, self.conversation, card["cardId"])["metadata"]["recordedVersions"]))
        self.assertEqual([], self.store.list(TrustedContext(1010, "PRT"),
                                             self.conversation))
        self.assertIsNone(self.store.read(self.owner, self.conversation + "-other",
                                          card["cardId"]))
        self.assert_code("CARD_REPLAY_CONFLICT", lambda: self.store.save(
            self.owner, self.conversation, prepared(prompt="Changed"),
            metadata(self.conversation)))

    def test_claim_commits_before_dispatch_and_finish_is_idempotent(self):
        card = self.save()
        claim = self.store.claim(self.owner, self.conversation, card["cardId"],
            "request-1", "confirm", {"optionId": "second", "ignored": "not-patched"}, 0)
        self.assertTrue(claim["dispatch"])
        self.assertEqual(("EXECUTING", 1),
                         (claim["card"]["status"], claim["card"]["revision"]))
        self.assertIn("recordedVersions", claim["metadata"])
        self.assert_code("ACTION_REQUEST_BUSY", lambda: self.store.claim(
            self.owner, self.conversation, card["cardId"], "request-1", "confirm",
            {"optionId": "second", "ignored": "not-patched"}, 0))
        result = {"accepted": True, "receipt": "business-result"}
        finished = self.store.finish(self.owner, self.conversation, card["cardId"],
                                     "request-1", result, True, True)
        self.assertEqual(("COMPLETED", 2),
                         (finished["status"], finished["revision"]))
        self.assertEqual(result, finished["result"])
        self.assertEqual("second", finished["display"]["data"]["optionId"])
        self.assertNotIn("ignored", finished["display"]["data"])
        self.assertEqual(finished, self.store.finish(
            self.owner, self.conversation, card["cardId"], "request-1",
            result, True, True))
        cached = self.store.claim(self.owner, self.conversation, card["cardId"],
            "request-1", "confirm", {"optionId": "second", "ignored": "not-patched"}, 0)
        self.assertFalse(cached["dispatch"])
        self.assertEqual(result, cached["result"])
        self.assert_code("ACTION_REQUEST_CONFLICT", lambda: self.store.claim(
            self.owner, self.conversation, card["cardId"], "request-1", "confirm",
            {"optionId": "first"}, 0))

    def test_business_failure_waits_and_new_request_uses_new_revision(self):
        card = self.save()
        self.store.claim(self.owner, self.conversation, card["cardId"],
                         "request-1", "confirm", {}, 0)
        waiting = self.store.finish(self.owner, self.conversation, card["cardId"],
            "request-1", {"accepted": False}, False, True)
        self.assertEqual(("WAITING_ACTION", 2),
                         (waiting["status"], waiting["revision"]))
        self.assert_code("STALE_CARD_REVISION", lambda: self.store.claim(
            self.owner, self.conversation, card["cardId"], "request-2", "confirm", {}, 0))
        claim = self.store.claim(self.owner, self.conversation, card["cardId"],
                                 "request-2", "confirm", {}, 2)
        self.assertEqual(3, claim["card"]["revision"])

    def test_exception_marks_unknown_and_never_redispatches(self):
        card = self.save()
        self.store.claim(self.owner, self.conversation, card["cardId"],
                         "request-1", "confirm", {}, 0)
        failed = self.store.fail(self.owner, self.conversation, card["cardId"],
                                 "request-1", "BUSINESS_DISPATCH_EXCEPTION")
        self.assertEqual(("UNKNOWN", 2), (failed["status"], failed["revision"]))
        self.assertNotIn("result", failed)
        self.assertEqual(failed, self.store.fail(
            self.owner, self.conversation, card["cardId"], "request-1",
            "BUSINESS_DISPATCH_EXCEPTION"))
        self.assert_code("ACTION_OUTCOME_UNKNOWN", lambda: self.store.claim(
            self.owner, self.conversation, card["cardId"], "request-1", "confirm", {}, 0))
        self.assert_code("CARD_TERMINAL", lambda: self.store.claim(
            self.owner, self.conversation, card["cardId"], "request-2", "confirm", {}, 2))
        self.assert_code("ACTION_FAILURE_CONFLICT", lambda: self.store.fail(
            self.owner, self.conversation, card["cardId"], "request-1", "OTHER_ERROR"))

    def test_selection_and_ingress_are_fail_closed(self):
        card = self.save()
        self.store.claim(self.owner, self.conversation, card["cardId"],
                         "request-1", "confirm", {"optionId": "missing"}, 0)
        self.assert_code("INVALID_OPTION_ID", lambda: self.store.finish(
            self.owner, self.conversation, card["cardId"], "request-1", {}, True, True))
        self.assertEqual("EXECUTING", self.store.read(
            self.owner, self.conversation, card["cardId"])["status"])
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
            "confirm", {}, 0))


class OfflineChatCardTests(ChatCardContract, unittest.TestCase):
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
                         "request-crash", "confirm", {}, 0)
        restarted = self.make_store()
        self.assert_code("ACTION_REQUEST_BUSY", lambda: restarted.claim(
            self.owner, self.conversation, card["cardId"], "request-crash",
            "confirm", {}, 0))
        executing = restarted.read(self.owner, self.conversation, card["cardId"])
        self.assertEqual(("EXECUTING", 1),
                         (executing["status"], executing["revision"]))
        unknown = restarted.fail(self.owner, self.conversation, card["cardId"],
                                  "request-crash", "PROCESS_TERMINATED")
        self.assertEqual(("UNKNOWN", 2), (unknown["status"], unknown["revision"]))


if __name__ == "__main__":
    unittest.main()
