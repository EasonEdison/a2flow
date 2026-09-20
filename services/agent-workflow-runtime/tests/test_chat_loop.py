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

OWNER = TrustedContext(user_id="u1", environment="PRT")


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
    tools: list = Field(default_factory=list)
    observed: list = Field(default_factory=list)

    def __init__(self, chunks, *, raise_on_stream=False):
        super().__init__(rounds=[list(chunks)], raise_on_stream=raise_on_stream)

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
            raise RuntimeError("provider down")
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


def tool_call_chunk(index, call_id, name, args_text):
    return {
        "index": index,
        "id": call_id,
        "name": name,
        "args": args_text,
        "type": "tool_call_chunk",
    }


class PlainTextTurnTests(unittest.TestCase):
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
        self.assertEqual("u1", trusted.user_id)
        self.assertEqual("PRT", trusted.environment)
        self.assertIn(TOOL_CALL, [kind for kind, _ in emitter.events])


class ErrorBoundaryTests(unittest.TestCase):
    def test_forged_runtime_argument_is_rejected_before_tool(self):
        reader = FakeMaterialPort(skill_material())
        first = FakeModel([AIMessageChunk(
            content="", tool_call_chunks=[tool_call_chunk(
                0, "forged", "use_skill",
                json.dumps({"skillKey": "demo/evidence-first-brief",
                            "runtime": {"userId": "other-user"}}),
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
