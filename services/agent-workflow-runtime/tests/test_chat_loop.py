"""Offline chat-loop tests with a scripted model and a fake material port."""

from __future__ import unicode_literals

import hashlib
import json
import unittest
from types import SimpleNamespace

from langchain_core.messages import AIMessageChunk
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGenerationChunk
from pydantic import Field

from skill_registry.ports import MaterialPort, SkillMaterial
from skill_registry.resources import (
    PackageEntry,
    PackageEntryDescriptor,
)
from skill_registry.use_skill import TrustedResolutionEvidence
from skillweave_contracts.models import TrustedContext

from agent_workflow_runtime.chat import (
    ChatLoop,
    ChatLoopError,
    ListEmitter,
    build_chat_tools,
    DONE,
    ERROR,
    TEXT_DELTA,
    TOOL_CALL,
    WORKFLOW_CONFIRM,
)
from agent_workflow_runtime.deepseek_model import DeepSeekProtocolError
from agent_workflow_runtime.models import ActionRejected

OWNER = TrustedContext(user_id=1009, environment="PRT")


def sha256_digest(content):
    return "sha256:" + hashlib.sha256(content).hexdigest()


def package_entry(logical_path, content, handle_id="material-1"):
    return PackageEntry(
        descriptor=PackageEntryDescriptor(
            handle_id=handle_id,
            logical_path=logical_path,
            media_type="text/markdown",
            declared_byte_size=len(content),
            declared_content_digest=sha256_digest(content),
        ),
        content=content,
    )


class FakeMaterialPort(MaterialPort):
    def __init__(self, material):
        self.material = material
        self.calls = []

    def load_skill(self, skill_key, trusted_context):
        self.calls.append((skill_key, trusted_context))
        return self.material


def skill_material():
    return SkillMaterial(
        instruction_entry=package_entry(
            "SKILL.md",
            b"Use the evidence, then write a concise brief.",
            handle_id="skill-instructions",
        ),
        resource_entries=(
            package_entry("references/source.md", "可信材料".encode("utf-8")),
        ),
        required_tool_names=("execute_ability",),
        resolution_evidence=TrustedResolutionEvidence(
            skill_key="demo/evidence-first-brief",
            asset_id="skill-evidence-first-brief",
            version_id="version-20260907",
            content_digest=sha256_digest(b"canonical-package"),
            environment="PRT",
            selection="PRT_CURRENT",
            evidence_ref="evidence-20260907",
        ),
    )


class FakeModel(BaseChatModel):
    rounds: list
    raise_on_stream: bool = False
    protocol_error_code: str | None = None
    tools: list = Field(default_factory=list)
    observed: list = Field(default_factory=list)

    def __init__(
        self,
        chunks: list[AIMessageChunk],
        *,
        raise_on_stream: bool = False,
        protocol_error_code: str | None = None,
    ) -> None:
        super().__init__(
            rounds=[list(chunks)],
            raise_on_stream=raise_on_stream,
            protocol_error_code=protocol_error_code,
        )

    @property
    def configuration(self):
        return SimpleNamespace(harness_profile_key="fakemodel")

    @property
    def _llm_type(self):
        return "fake"

    def bind_tools(self, tools, **kwargs):
        self.tools = list(tools)
        return self

    def _generate(self, messages, **kwargs):
        raise AssertionError("Expected native streaming")

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.observed.append(list(messages))
        if self.raise_on_stream:
            raise RuntimeError("provider down with secret-input")
        if self.protocol_error_code is not None:
            raise DeepSeekProtocolError(self.protocol_error_code)
        for chunk in self.rounds.pop(0):
            yield ChatGenerationChunk(message=chunk)


class FakeFactory:
    def __init__(self, models):
        self.models = list(models)
        self.created = []

    def create(self, reference, owner):
        self.created.append((reference, owner))
        model = self.models.pop(0)
        for remaining in self.models:
            model.rounds.extend(remaining.rounds)
        self.models.clear()
        return model


class RejectingChatAssets:
    def __init__(self, code: str) -> None:
        self.code = code
        self.dispatches = 0

    def begin_turn(self) -> None:
        return None

    def waiting_action(self) -> None:
        return None

    def validate_context(self, context: object) -> None:
        del context

    def execute_ability(
        self,
        ability_key: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        del ability_key, arguments
        self.dispatches += 1
        raise ActionRejected(self.code)


def tool_call_chunk(index, call_id, name, args_text):
    return {
        "index": index,
        "id": call_id,
        "name": name,
        "args": args_text,
        "type": "tool_call_chunk",
    }


class PlainTextTurnTests(unittest.TestCase):
    def test_checkpoint_rebuild_imports_legacy_only_once(self):
        from langgraph.checkpoint.memory import InMemorySaver
        from langchain_core.messages import HumanMessage, AIMessage
        saver = InMemorySaver()
        imports = []
        def legacy():
            imports.append(True)
            return [HumanMessage(content="old"), AIMessage(content="old reply")]
        def turn(text, reply):
            model = FakeModel([AIMessageChunk(content=reply)])
            loop = ChatLoop(
                model_factory=FakeFactory([model]), model_reference="deepseek-v4-flash",
                owner=OWNER, conversation_id="conv1",
                reader=FakeMaterialPort(skill_material()), control_request_id=text,
                checkpointer=saver, thread_id="server-owned-thread",
                history_loader=legacy,
            )
            loop.turn(text)
            return loop
        turn("first", "first reply")
        second = turn("second", "second reply")
        self.assertEqual([True], imports)
        self.assertEqual(["old", "old reply", "first", "first reply", "second", "second reply"],
                         [m.content for m in second.history])

    def test_plain_reply_streams_deltas_and_done(self):
        emitter = ListEmitter()
        factory = FakeFactory(
            [FakeModel([AIMessageChunk(content="你好"), AIMessageChunk(content="，世界")])]
        )
        loop = ChatLoop(
            model_factory=factory, model_reference="deepseek-v4-flash",
            owner=OWNER, conversation_id="conv1", reader=FakeMaterialPort(skill_material()),
            control_request_id="chatctrl1", emitter=emitter,
        )
        reply = loop.turn("打个招呼")
        self.assertEqual("你好，世界", reply)
        kinds = [kind for kind, _ in emitter.events]
        self.assertEqual([TEXT_DELTA, TEXT_DELTA, DONE], kinds)
        self.assertEqual("你好", emitter.events[0][1]["text"])
        self.assertEqual(2, len(loop.history))
        self.assertEqual("human", loop.history[0].type)

    def test_provider_reasoning_is_visible_without_forwarding_opaque_fields(self):
        emitter = ListEmitter()
        chunk = AIMessageChunk(content="answer", additional_kwargs={
            "reasoning_content": "provider explanation", "secret": "never forwarded"})
        loop = ChatLoop(model_factory=FakeFactory([FakeModel([chunk])]),
            model_reference="deepseek-v4-flash", owner=OWNER,
            conversation_id="conv1", reader=FakeMaterialPort(skill_material()),
            control_request_id="chatctrl1", emitter=emitter)
        loop.turn("hello")
        self.assertIn(("reasoning_delta", {"text": "provider explanation"}), emitter.events)
        self.assertNotIn("never forwarded", str(emitter.events))


class WorkflowConfirmTests(unittest.TestCase):
    def test_propose_emits_confirm_and_never_starts(self):
        emitter = ListEmitter()
        chunks_round1 = [
            AIMessageChunk(content="我建议运行活动策划工作流。"),
            AIMessageChunk(
                content="",
                tool_call_chunks=[
                    tool_call_chunk(
                        0, "call-1", "propose_workflow_run",
                        json.dumps({"workflowKey": "activity-package-demo", "title": "周末活动"}),
                    )
                ],
            ),
        ]
        factory = FakeFactory(
            [
                FakeModel(chunks_round1),
                FakeModel([AIMessageChunk(content="好的，提案已生成，等你确认。")]),
            ]
        )
        loop = ChatLoop(
            model_factory=factory, model_reference="deepseek-v4-flash",
            owner=OWNER, conversation_id="conv1",
            reader=FakeMaterialPort(skill_material()),
            control_request_id="chatctrl1", emitter=emitter,
        )
        reply = loop.turn("帮我跑一下活动策划")
        self.assertEqual("好的，提案已生成，等你确认。", reply)
        confirm = next(p for k, p in emitter.events if k == WORKFLOW_CONFIRM)
        self.assertEqual({"workflowKey": "activity-package-demo", "title": "周末活动"}, confirm)
        # tool_call events expose the tool name only, never arguments.
        tool_events = [p for k, p in emitter.events if k == TOOL_CALL]
        self.assertEqual([{"tool": "propose_workflow_run"}], tool_events)
        # no transport-visible payload leaks tool arguments beyond the whitelist.
        for kind, payload in emitter.events:
            self.assertNotIn("args", payload)
        self.assertEqual(DONE, emitter.events[-1][0])
        self.assertEqual(1, len(factory.created))
        self.assertEqual(1, sum(m.type == "human" for m in loop.history))
        self.assertEqual(["human", "ai", "tool", "ai"],
                         [m.type for m in loop.history])


class UseSkillConversationScopeTests(unittest.TestCase):
    def test_use_skill_runs_with_conversation_scope(self):
        reader = FakeMaterialPort(skill_material())
        emitter = ListEmitter()
        chunks_round1 = [
            AIMessageChunk(
                content="",
                tool_call_chunks=[
                    tool_call_chunk(
                        0, "call-1", "use_skill",
                        json.dumps({"skillKey": "demo/evidence-first-brief"}),
                    )
                ],
            ),
        ]
        factory = FakeFactory(
            [
                FakeModel(chunks_round1),
                FakeModel([AIMessageChunk(content="技能已加载，为你总结。")]),
            ]
        )
        loop = ChatLoop(
            model_factory=factory, model_reference="deepseek-v4-flash",
            owner=OWNER, conversation_id="conv1", reader=reader,
            control_request_id="chatctrl1", emitter=emitter,
        )
        reply = loop.turn("加载证据简报技能")
        self.assertEqual("技能已加载，为你总结。", reply)
        self.assertEqual(1, len(reader.calls))
        skill_key, trusted = reader.calls[0]
        self.assertEqual("demo/evidence-first-brief", skill_key)
        # The registry port receives the server-supplied owner.
        self.assertEqual(1009, trusted.user_id)
        self.assertEqual("PRT", trusted.environment)
        self.assertIn(TOOL_CALL, [kind for kind, _ in emitter.events])


class ErrorBoundaryTests(unittest.TestCase):
    @staticmethod
    def _ability_call(call_id: str) -> AIMessageChunk:
        return AIMessageChunk(
            content="",
            tool_call_chunks=[tool_call_chunk(
                0,
                call_id,
                "execute_ability",
                json.dumps({
                    "abilityKey": "demo.invalid",
                    "arguments": {"secret": "never-emit-this-argument"},
                }),
            )],
        )

    def test_allowlisted_tool_argument_rejection_stops_without_redispatch(self) -> None:
        emitter = ListEmitter()
        assets = RejectingChatAssets("ARGUMENT_INVALID")
        factory = FakeFactory([
            FakeModel([self._ability_call("invalid-1")]),
            FakeModel([self._ability_call("must-not-dispatch")]),
        ])
        loop = ChatLoop(
            model_factory=factory,
            model_reference="deepseek-v4-flash",
            owner=OWNER,
            conversation_id="conv1",
            reader=FakeMaterialPort(skill_material()),
            control_request_id="chatctrl1",
            emitter=emitter,
            chat_assets=assets,
        )

        with self.assertRaises(ChatLoopError) as raised:
            loop.turn("call the ability")

        self.assertEqual("ARGUMENT_INVALID", str(raised.exception))
        self.assertEqual(1, assets.dispatches)
        self.assertEqual(
            {"code": "ARGUMENT_INVALID", "reason": "ActionRejected"},
            emitter.events[-1][1],
        )
        self.assertNotIn("never-emit-this-argument", str(emitter.events))
        self.assertNotIn("never-emit-this-argument", str(raised.exception))

    def test_unallowlisted_action_rejection_remains_generic(self) -> None:
        emitter = ListEmitter()
        assets = RejectingChatAssets("PRIVATE_secret-input")
        loop = ChatLoop(
            model_factory=FakeFactory([FakeModel([
                self._ability_call("private-rejection"),
            ])]),
            model_reference="deepseek-v4-flash",
            owner=OWNER,
            conversation_id="conv1",
            reader=FakeMaterialPort(skill_material()),
            control_request_id="chatctrl1",
            emitter=emitter,
            chat_assets=assets,
        )

        with self.assertRaises(ChatLoopError) as raised:
            loop.turn("call the ability")

        self.assertEqual(1, assets.dispatches)
        self.assertEqual("MODEL_STREAM_FAILED", str(raised.exception))
        self.assertEqual("MODEL_STREAM_FAILED", emitter.events[-1][1]["code"])
        self.assertNotIn("PRIVATE_secret-input", str(emitter.events))
        self.assertNotIn("PRIVATE_secret-input", str(raised.exception))

    def test_allowlisted_provider_protocol_rejection_is_specific_and_terminal(self) -> None:
        emitter = ListEmitter()
        loop = ChatLoop(
            model_factory=FakeFactory([FakeModel(
                [], protocol_error_code="DUPLICATE_TOOL_ARGUMENT",
            )]),
            model_reference="deepseek-v4-flash",
            owner=OWNER,
            conversation_id="conv1",
            reader=FakeMaterialPort(skill_material()),
            control_request_id="chatctrl1",
            emitter=emitter,
        )

        with self.assertRaises(ChatLoopError) as raised:
            loop.turn("hello")

        self.assertEqual("DUPLICATE_TOOL_ARGUMENT", str(raised.exception))
        self.assertEqual(
            {"code": "DUPLICATE_TOOL_ARGUMENT", "reason": "DeepSeekProtocolError"},
            emitter.events[-1][1],
        )

    def test_unallowlisted_provider_code_remains_generic(self) -> None:
        emitter = ListEmitter()
        loop = ChatLoop(
            model_factory=FakeFactory([FakeModel(
                [], protocol_error_code="PRIVATE_secret-input",
            )]),
            model_reference="deepseek-v4-flash",
            owner=OWNER,
            conversation_id="conv1",
            reader=FakeMaterialPort(skill_material()),
            control_request_id="chatctrl1",
            emitter=emitter,
        )

        with self.assertRaises(ChatLoopError) as raised:
            loop.turn("hello")

        self.assertEqual("MODEL_STREAM_FAILED", str(raised.exception))
        self.assertEqual("MODEL_STREAM_FAILED", emitter.events[-1][1]["code"])
        self.assertNotIn("PRIVATE_secret-input", str(emitter.events))
        self.assertNotIn("PRIVATE_secret-input", str(raised.exception))

    def test_forged_runtime_argument_is_rejected_before_tool(self):
        reader = FakeMaterialPort(skill_material())
        first = FakeModel([AIMessageChunk(
            content="", tool_call_chunks=[tool_call_chunk(
                0, "forged", "use_skill",
                json.dumps({"skillKey": "demo/evidence-first-brief",
                            "runtime": {"userId": '1005'}}),
            )],
        )])
        factory = FakeFactory([first, FakeModel([AIMessageChunk(content="拒绝")])])
        loop = ChatLoop(
            model_factory=factory, model_reference="deepseek-v4-flash",
            owner=OWNER, conversation_id="conv1", reader=reader,
            control_request_id="chatctrl1",
        )
        loop.turn("你好")
        self.assertEqual([], reader.calls)
        self.assertEqual("error", loop.history[2].status)
        from agent_workflow_runtime.assembly import IMPLICIT_DEEP_AGENT_TOOLS
        self.assertFalse({t.name for t in first.tools} & IMPLICIT_DEEP_AGENT_TOOLS)

    def test_native_reasoning_and_tool_pairing_are_preserved(self):
        first = FakeModel([AIMessageChunk(
            content="", additional_kwargs={"reasoning_content": "fixture reasoning"},
            tool_call_chunks=[tool_call_chunk(
                0, "native-call", "propose_workflow_run",
                json.dumps({"workflowKey": "demo", "title": "Demo"}),
            )],
        )])
        loop = ChatLoop(
            model_factory=FakeFactory([first, FakeModel([AIMessageChunk(content="done")])]),
            model_reference="deepseek-v4-flash", owner=OWNER,
            conversation_id="conv1", reader=FakeMaterialPort(skill_material()),
            control_request_id="chatctrl1",
        )
        loop.turn("proposal")
        self.assertEqual("fixture reasoning",
                         loop.history[1].additional_kwargs["reasoning_content"])
        self.assertEqual(loop.history[1].tool_calls[0]["id"],
                         loop.history[2].tool_call_id)
        self.assertEqual(1, sum(m.type == "human" for m in first.observed[-1]))

    def test_model_stream_failure_emits_error(self):
        emitter = ListEmitter()
        factory = FakeFactory([FakeModel([], raise_on_stream=True)])
        loop = ChatLoop(
            model_factory=factory, model_reference="deepseek-v4-flash",
            owner=OWNER, conversation_id="conv1",
            reader=FakeMaterialPort(skill_material()),
            control_request_id="chatctrl1", emitter=emitter,
        )
        with self.assertRaises(ChatLoopError):
            loop.turn("你好")
        self.assertEqual(ERROR, emitter.events[-1][0])
        self.assertEqual("MODEL_STREAM_FAILED", emitter.events[-1][1]["code"])
        self.assertNotIn("secret-input", str(emitter.events))

    def test_empty_message_rejected(self):
        loop = ChatLoop(
            model_factory=FakeFactory([]), model_reference="deepseek-v4-flash",
            owner=OWNER, conversation_id="conv1",
            reader=FakeMaterialPort(skill_material()),
            control_request_id="chatctrl1",
        )
        with self.assertRaises(ChatLoopError):
            loop.turn("   ")


class ToolConstructionTests(unittest.TestCase):
    def test_chat_tools_are_conversation_scoped(self):
        reader = FakeMaterialPort(skill_material())
        use_skill_tool, propose_tool = build_chat_tools(
            reader=reader,
            trusted_context=OWNER,
            conversation_id="conv1",
            control_request_id="chatctrl1",
        )
        self.assertEqual("use_skill", use_skill_tool.name)
        self.assertEqual("propose_workflow_run", propose_tool.name)
        # Propose does not need the reader and emits only via the bound emitter.
        from agent_workflow_runtime.chat.tools import _EMITTER
        emitter = ListEmitter()
        token = _EMITTER.set(emitter)
        try:
            from langchain.tools import ToolRuntime
            from skillweave_contracts.models import (
                ConversationInvocationScope,
                TrustedInvocationContext,
            )
            invocation = TrustedInvocationContext(
                trusted_context=OWNER,
                invocation_scope=ConversationInvocationScope(
                    conversation_id="conv1"
                ),
                control_request_id="chatctrl1",
            )
            runtime = ToolRuntime(
                state=None, context=invocation,
                config={"configurable": {"thread_id": "conv1"}},
                stream_writer=None, tool_call_id="call-9", store=None,
            )
            message = propose_tool.invoke(
                {
                    "name": "propose_workflow_run",
                    "args": {
                        "workflowKey": "activity-package-demo",
                        "title": "T",
                        "runtime": runtime,
                    },
                    "id": "call-9",
                    "type": "tool_call",
                }
            )
            content = message.content
        finally:
            _EMITTER.reset(token)
        self.assertEqual(WORKFLOW_CONFIRM, emitter.events[0][0])
        self.assertIn("proposed", content)


if __name__ == "__main__":
    unittest.main()
