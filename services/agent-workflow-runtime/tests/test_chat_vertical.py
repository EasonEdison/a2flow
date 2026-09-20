"""Native SDK + canonical assets + real disposable PostgreSQL, no paid model."""

import os
import unittest
from uuid import uuid4

from a2flow_asset_store import AssetReader
from activity_planning_demo import APPLICATION_KEY, BUDGET_KEY, application_validator, application_data_validator, bundle_validator
from activity_planning_demo.bundle import make_bundle, NAMESPACE
from agent_workflow_runtime.chat.assets import ChatAssets
from agent_workflow_runtime.chat.cards import ChatCardStore
from agent_workflow_runtime.chat.actions import ChatActionService
from agent_workflow_runtime.chat.loop import ChatLoop
from agent_workflow_runtime.chat.persistence import ConversationStore
from agent_workflow_runtime.chat.events import ListEmitter
from agent_workflow_runtime.models import ActionRejected
from deploy.mvp.operations import operations
from test_chat_skill_execution import OWNER, Factory, ScriptedModel, _call


class BundleRepository:
    environment = "PRT"
    def __init__(self):
        self.validator = bundle_validator()
        self.bundle = self.validator.validate(make_bundle("PRT"),
            expected_namespace=NAMESPACE, expected_environment="PRT")
    def read(self, namespace):
        assert namespace == NAMESPACE
        return self.bundle


@unittest.skipUnless(os.environ.get("A2FLOW_TEST_CHAT_CARDS_DSN"), "disposable PostgreSQL required")
class ChatVerticalTest(unittest.TestCase):
    def test_attended_runner_forwards_saved_card_and_wait_before_transport_done(self):
        import asyncio
        from deploy.attended.chat_runner import ChatLoopRunner
        dsn = os.environ["A2FLOW_TEST_CHAT_CARDS_DSN"]
        store = ChatCardStore(dsn, environment="PRT")
        store.setup()
        conversations = ConversationStore(dsn)
        conversations.setup()
        reader = AssetReader(BundleRepository(), NAMESPACE)
        registry = operations()
        model = ScriptedModel(rounds=[
            [_call(0, "runner-skill", "use_skill", {"skillKey": "activity-planning/plan"})],
            [_call(0, "runner-card", "render_application", {"applicationKey": APPLICATION_KEY,
                "data": {"prompt": "Choose", "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]}})],
        ])
        def assets(owner, conversation, control):
            return ChatAssets(reader, registry, owner, conversation, control,
                lambda prepared, metadata: store.save(owner, conversation, prepared, metadata),
                application_validator, application_data_validator)
        runner = ChatLoopRunner(model_factory=Factory(model), model_reference="deepseek-v4-flash",
            environment="PRT", reader=reader, conversation_store=conversations,
            history_loader=lambda *args: [], assets_factory=assets,
            card_context=lambda *args: [{"cardId": "historical-card", "status": "COMPLETED", "result": {"accepted": True}}])
        conversation = str(uuid4())
        async def execute():
            return [event async for event in runner.iterate(user_id=OWNER.user_id,
                conversation_id=conversation, text="Prepare", turn_id="1")]
        events = asyncio.run(execute())
        kinds = [event["type"] for event in events]
        self.assertLess(kinds.index("application_rendered"), kinds.index("waiting_action"))
        self.assertEqual("done", kinds[-1])
        card = next(event["card"] for event in events if event["type"] == "application_rendered")
        self.assertEqual(card, store.read(OWNER, conversation, card["cardId"]))
        self.assertIn("historical-card", str(model.observed[0]))

    def test_sdk_skill_ability_card_action_and_restart_read(self):
        dsn = os.environ["A2FLOW_TEST_CHAT_CARDS_DSN"]
        store = ChatCardStore(dsn, environment="PRT")
        store.setup()
        conversations = ConversationStore(dsn)
        conversations.setup()
        conversation = str(uuid4())
        reader = AssetReader(BundleRepository(), NAMESPACE)
        specs = operations()
        def assets_factory(owner, conversation_id, control="chat-action"):
            return ChatAssets(reader, specs, owner, conversation_id, control,
                lambda prepared, metadata: store.save(owner, conversation_id, prepared, metadata),
                application_validator, application_data_validator)
        model = ScriptedModel(rounds=[
            [_call(0, "skill", "use_skill", {"skillKey": "activity-planning/plan"})],
            [_call(0, "budget", "execute_ability", {"abilityKey": BUDGET_KEY,
                "arguments": {"participants": 3, "budgetMinor": 1000}})],
            [_call(0, "card", "render_application", {"applicationKey": APPLICATION_KEY,
                "data": {"prompt": "Choose a plan", "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]}})],
        ])
        emitter = ListEmitter()
        with conversations.session(OWNER, conversation, "1") as (saver, thread_id):
            loop = ChatLoop(model_factory=Factory(model), model_reference="deepseek-v4-flash",
                owner=OWNER, conversation_id=conversation, reader=reader,
                control_request_id="chat-1", emitter=emitter, checkpointer=saver, thread_id=thread_id,
                chat_assets=assets_factory(OWNER, conversation, "chat-1"))
            loop.turn("Please prepare a plan")
        self.assertEqual(3, len(model.observed))
        cards = ChatCardStore(dsn, environment="PRT").list(OWNER, conversation)
        self.assertEqual(1, len(cards))
        card = cards[0]
        self.assertEqual("WAITING_ACTION", card["status"])
        action = card["display"]["actions"][0]["actionName"]
        service = ChatActionService(store, assets_factory)
        payload = dict(request_id="request-1", action_name=action,
                       inputs={"optionId": "a", "confirmed": True}, expected_revision=0)
        completed = service.execute(OWNER, conversation, card["cardId"], **payload)
        self.assertEqual("COMPLETED", completed["status"])
        self.assertEqual("a", completed["display"]["data"]["optionId"])
        self.assertEqual(completed, service.execute(OWNER, conversation, card["cardId"], **payload))
        self.assertEqual(completed, ChatCardStore(dsn, environment="PRT").read(OWNER, conversation, card["cardId"]))
        with self.assertRaises(ActionRejected):
            service.execute(OWNER, conversation, card["cardId"], **{**payload, "request_id": "different"})
        # The native checkpoint remains usable after an interactive turn ends;
        # a new user message is not a fabricated Workflow resume.
        from langchain_core.messages import AIMessageChunk
        next_model = ScriptedModel(rounds=[[AIMessageChunk(content="Saved card received")]])
        with conversations.session(OWNER, conversation, "2") as (saver, thread_id):
            next_loop = ChatLoop(model_factory=Factory(next_model), model_reference="deepseek-v4-flash",
                owner=OWNER, conversation_id=conversation, reader=reader,
                control_request_id="chat-2", checkpointer=saver, thread_id=thread_id,
                chat_assets=assets_factory(OWNER, conversation, "chat-2"))
            self.assertEqual("Saved card received", next_loop.turn("What happened?"))
