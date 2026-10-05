"""Offline chat-loop tests with a scripted model and a fake material port."""

from __future__ import unicode_literals

import asyncio
import hashlib
import json
import unittest
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace

from agent_workflow_runtime.assembly import build_agent
from agent_workflow_runtime.chat import (
    DONE,
    ERROR,
    TEXT_DELTA,
    TOOL_CALL,
    WORKFLOW_CONFIRM,
    ChatLoop,
    ChatLoopError,
    ListEmitter,
    build_chat_tools,
)
from agent_workflow_runtime.chat.events import (
    TOOL_CALL_FINISHED,
    TOOL_CALL_STARTED,
    public_event_value,
    public_tool_result,
)
from agent_workflow_runtime.chat.loop import (
    _ACTION_OBSERVATION_MARKER,
    _OBSERVATION_CURSOR,
    _action_observation_message,
    _ChatObservationStateMiddleware,
    _read_observations,
    _tool_result,
)
from agent_workflow_runtime.deepseek_model import DeepSeekProtocolError
from agent_workflow_runtime.models import ActionRejected
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessageChunk,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGenerationChunk
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.types import Command
from pydantic import Field
from skill_registry.ports import MaterialPort, SkillMaterial
from skill_registry.resources import (
    PackageEntry,
    PackageEntryDescriptor,
)
from skill_registry.use_skill import TrustedResolutionEvidence
from skillweave_contracts.models import TrustedContext

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

    def admitted_tool_names(self) -> frozenset[str]:
        return frozenset({"execute_ability"})

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
        from langchain_core.messages import AIMessage, HumanMessage
        from langgraph.checkpoint.memory import InMemorySaver
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
            [FakeModel([
                AIMessageChunk(content="你好", id="model-final-1"),
                AIMessageChunk(content="，世界", id="model-final-1"),
            ])]
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
        self.assertEqual(
            {"text": "你好", "modelMessageId": "model-final-1"},
            emitter.events[0][1],
        )
        self.assertEqual("model-final-1", emitter.events[-1][1][
            "finalModelMessageId"
        ])
        self.assertEqual(2, len(loop.history))
        self.assertEqual("human", loop.history[0].type)

    def test_provider_reasoning_is_visible_without_forwarding_opaque_fields(self):
        emitter = ListEmitter()
        chunk = AIMessageChunk(content="answer", id="model-answer-1", additional_kwargs={
            "reasoning_content": "provider explanation", "secret": "never forwarded"})
        loop = ChatLoop(model_factory=FakeFactory([FakeModel([chunk])]),
            model_reference="deepseek-v4-flash", owner=OWNER,
            conversation_id="conv1", reader=FakeMaterialPort(skill_material()),
            control_request_id="chatctrl1", emitter=emitter)
        loop.turn("hello")
        self.assertIn(("reasoning_delta", {
            "text": "provider explanation", "modelMessageId": "model-answer-1",
        }), emitter.events)
        self.assertNotIn("never forwarded", str(emitter.events))

    def test_public_event_value_bounds_nested_frozen_values_and_secrets(self):
        from types import MappingProxyType

        value = MappingProxyType({
            "items": tuple({"name": f"item-{index}"} for index in range(30)),
            "nested": {"authorization": "Bearer private", "visible": "ok"},
        })

        projected = public_event_value(value)

        self.assertEqual("[REDACTED]", projected["nested"]["authorization"])
        self.assertEqual("ok", projected["nested"]["visible"])
        self.assertEqual(21, len(projected["items"]))
        self.assertNotIn("Bearer private", str(projected))
        self.assertEqual(
            {"type": "nonFiniteNumber"}, public_event_value(float("nan")),
        )

    def test_tool_result_preserves_full_json_and_plain_text(self):
        text = "visible result " * 6_000
        _, raw_text, _ = _tool_result(ToolMessage(
            content=text,
            tool_call_id="long-text",
        ), "long-text")
        self.assertEqual(text, public_tool_result(raw_text))

        result = {
            "items": [
                {"index": index, "content": "x" * 600}
                for index in range(30)
            ],
            "nested": {"one": {"two": {"three": {"four": "kept"}}}},
        }
        _, raw_json, _ = _tool_result(ToolMessage(
            content=json.dumps(result),
            tool_call_id="long-json",
        ), "long-json")
        self.assertEqual(result, public_tool_result(raw_json))

    def test_tool_result_redacts_nested_and_text_credentials_only(self):
        result = {
            "authorization": "Bearer json-secret",
            "nested": {
                "clientSecret": "json-client-secret",
                "access_token": "json-access-token",
                "apiKey": "json-api-key",
                "token": "json-token",
                "tokenCount": 7,
                "visible": ["kept", {"password": "json-password"}],
            },
        }
        projected = public_tool_result(result)
        self.assertEqual("[REDACTED]", projected["authorization"])
        self.assertEqual("[REDACTED]", projected["nested"]["clientSecret"])
        self.assertEqual("[REDACTED]", projected["nested"]["access_token"])
        self.assertEqual("[REDACTED]", projected["nested"]["apiKey"])
        self.assertEqual("[REDACTED]", projected["nested"]["token"])
        self.assertEqual(7, projected["nested"]["tokenCount"])
        self.assertEqual("kept", projected["nested"]["visible"][0])
        self.assertEqual(
            "[REDACTED]", projected["nested"]["visible"][1]["password"],
        )

        text = (
            "visible line\nAuthorization: Bearer header-secret\n"
            "password=assignment-secret access_token=query-secret&next=kept\n"
            'embedded={"token":"embedded-secret","tokenCount":7}\n'
            "raw Bearer raw-secret and sk-1234567890abcdefghijkl"
        )
        redacted = public_tool_result(text)
        self.assertIn("visible line", redacted)
        self.assertIn("next=kept", redacted)
        for secret in (
            "header-secret", "assignment-secret", "query-secret",
            "embedded-secret", "raw-secret", "sk-1234567890abcdefghijkl",
        ):
            self.assertNotIn(secret, redacted)
        self.assertIn('"tokenCount":7', redacted)

    def test_command_result_projects_only_matching_tool_message(self):
        command = Command(update={"messages": [
            ToolMessage(content='{"ignored":true}', tool_call_id="other"),
            ToolMessage(
                content='{"businessSuccess":false,"receipt":"public"}',
                tool_call_id="call-1", status="success",
                artifact={"secret": "artifact-not-projected"},
            ),
        ], "privateState": {"secret": "not projected"}})

        status, raw, business_success = _tool_result(command, "call-1")

        self.assertEqual("success", status)
        self.assertEqual({"businessSuccess": False, "receipt": "public"}, raw)
        self.assertFalse(business_success)
        self.assertNotIn("privateState", str(raw))
        self.assertNotIn("artifact-not-projected", str(raw))


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
        started = next(p for k, p in emitter.events if k == TOOL_CALL_STARTED)
        finished = next(p for k, p in emitter.events if k == TOOL_CALL_FINISHED)
        self.assertEqual("call-1", started["toolCallId"])
        self.assertEqual("propose_workflow_run", started["name"])
        self.assertEqual("returned", finished["lifecycleStatus"])
        self.assertEqual("success", finished["toolMessageStatus"])
        self.assertGreaterEqual(finished["durationMs"], 0)
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

    def test_allowlisted_transport_rejection_stops_without_redispatch(self) -> None:
        emitter = ListEmitter()
        assets = RejectingChatAssets("TRANSPORT_ERROR")
        loop = ChatLoop(
            model_factory=FakeFactory([FakeModel([
                self._ability_call("transport-error"),
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

        self.assertEqual("TRANSPORT_ERROR", str(raised.exception))
        self.assertEqual(1, assets.dispatches)
        self.assertEqual(
            {"code": "TRANSPORT_ERROR", "reason": "ActionRejected"},
            emitter.events[-1][1],
        )
        self.assertNotIn("never-emit-this-argument", str(emitter.events))

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


@dataclass(frozen=True)
class Observation:
    sequence: int
    event_id: str
    kind: str
    card_id: str
    application_key: str
    request_id: str | None = None
    action_name: str | None = None
    description: str | None = None
    arguments: dict | None = None
    status: str | None = None
    result: object = None
    capability_success: bool | None = None
    business_success: bool | None = None
    presentation_status: str | None = None
    capability_error_code: str | None = None
    presentation_error_code: str | None = None
    error_code: str | None = None


class ChatObservationTests(unittest.TestCase):
    @staticmethod
    def _loop(*, saver, thread_id, model, loader):
        return ChatLoop(
            model_factory=FakeFactory([model]),
            model_reference="deepseek-v4-flash",
            owner=OWNER,
            conversation_id="conv-observations",
            reader=FakeMaterialPort(skill_material()),
            control_request_id="observation-turn",
            checkpointer=saver,
            thread_id=thread_id,
            observation_loader=loader,
        )

    def test_empty_checkpoint_commits_actions_before_user_and_does_not_repeat(self):
        from langgraph.checkpoint.memory import InMemorySaver

        observations = [
            Observation(
                10, "render-1", "RENDERED", "card-1", "draft-editor",
            ),
            Observation(
                20,
                "action-1",
                "ACTION",
                "card-1",
                "draft-editor",
                request_id="request-1",
                action_name="save",
                description="Save the edited draft",
                arguments={"artifactId": "artifact-1", "revision": 4},
                status="COMPLETED",
                result={"savedRevision": 5},
                capability_success=True,
                business_success=True,
            ),
        ]
        calls = []

        def loader(after_sequence):
            calls.append(after_sequence)
            return [
                item for item in observations
                if item.sequence > after_sequence
            ][:100]

        saver = InMemorySaver()
        first_model = FakeModel([AIMessageChunk(content="first reply")])
        first = self._loop(
            saver=saver,
            thread_id="observation-thread",
            model=first_model,
            loader=loader,
        )
        self.assertEqual("first reply", first.turn("continue"))
        human_contents = [
            message.content for message in first_model.observed[0]
            if message.type == "human"
        ]
        self.assertIn(_ACTION_OBSERVATION_MARKER, human_contents[0])
        self.assertIn('"executionArguments"', human_contents[0])
        self.assertIn('"systemOutcome"', human_contents[0])
        self.assertEqual("continue", human_contents[1])
        self.assertNotIn("render-1", "\n".join(human_contents))

        second_model = FakeModel([AIMessageChunk(content="second reply")])
        second = self._loop(
            saver=saver,
            thread_id="observation-thread",
            model=second_model,
            loader=loader,
        )
        self.assertEqual("second reply", second.turn("continue again"))
        all_content = "\n".join(
            str(message.content) for message in second_model.observed[0]
        )
        self.assertEqual(1, all_content.count(_ACTION_OBSERVATION_MARKER))
        self.assertEqual([0, 20], calls)

    def test_private_cursor_survives_remove_all_messages(self):
        from langgraph.checkpoint.memory import InMemorySaver

        saver = InMemorySaver()
        calls = []
        observation = Observation(
            41,
            "action-41",
            "ACTION",
            "card-41",
            "draft-editor",
            action_name="save",
            status="COMPLETED",
            capability_success=True,
            business_success=True,
        )

        def loader(after_sequence):
            calls.append(after_sequence)
            return [observation] if after_sequence == 0 else []

        model = FakeModel([AIMessageChunk(content="first")])
        graph = build_agent(
            model,
            (),
            {},
            harness_profile_key=model.configuration.harness_profile_key,
            checkpointer=saver,
            middleware=[_ChatObservationStateMiddleware(
                loader,
                HumanMessage(content="first user"),
            )],
        )
        config = {"configurable": {"thread_id": "summarized-thread"}}
        list(graph.stream(
            {"messages": []}, config=config, stream_mode=["messages", "values"],
        ))
        graph.update_state(config, {
            "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES)],
        })
        snapshot = graph.get_state(config)
        self.assertEqual([], snapshot.values["messages"])
        checkpoint = saver.get_tuple(config)
        self.assertEqual(
            41,
            checkpoint.checkpoint["channel_values"][_OBSERVATION_CURSOR],
        )

        second_model = FakeModel([AIMessageChunk(content="second")])
        second_graph = build_agent(
            second_model,
            (),
            {},
            harness_profile_key=second_model.configuration.harness_profile_key,
            checkpointer=saver,
            middleware=[_ChatObservationStateMiddleware(
                loader,
                HumanMessage(content="second user"),
            )],
        )
        list(second_graph.stream(
            {"messages": []}, config=config, stream_mode=["messages", "values"],
        ))
        self.assertEqual([0, 41], calls)
        self.assertNotIn(
            _ACTION_OBSERVATION_MARKER,
            "\n".join(str(message.content) for message in second_model.observed[0]),
        )

    def test_model_failure_keeps_observation_checkpoint_and_does_not_resume(self):
        from langgraph.checkpoint.memory import InMemorySaver

        observation = Observation(
            1,
            "action-failed-model",
            "ACTION",
            "card-1",
            "draft-editor",
            action_name="save",
            arguments={"artifactId": "artifact-1"},
            status="COMPLETED",
            result={"saved": True},
            capability_success=True,
            business_success=True,
        )
        calls = []

        def loader(after_sequence):
            calls.append(after_sequence)
            return [observation] if after_sequence == 0 else []

        saver = InMemorySaver()
        failed = self._loop(
            saver=saver,
            thread_id="failed-thread",
            model=FakeModel([], raise_on_stream=True),
            loader=loader,
        )
        with self.assertRaisesRegex(ChatLoopError, "MODEL_STREAM_FAILED"):
            failed.turn("trigger failure")

        unused_model = FakeModel([AIMessageChunk(content="must not resume")])
        blocked = self._loop(
            saver=saver,
            thread_id="failed-thread",
            model=unused_model,
            loader=loader,
        )
        with self.assertRaisesRegex(ChatLoopError, "MODEL_STREAM_FAILED"):
            blocked.turn("new text")
        self.assertEqual([], unused_model.observed)
        self.assertEqual([0], calls)

    def test_attended_runner_reads_incremental_observations_without_system_dump(self):
        from langgraph.checkpoint.memory import InMemorySaver

        from deploy.attended.chat_runner import ChatLoopRunner

        saver = InMemorySaver()

        class ConversationStore:
            @contextmanager
            def session(self, owner, conversation_id, turn_id):
                del owner, conversation_id, turn_id
                yield saver, "runner-observation-thread"

        first_model = FakeModel([AIMessageChunk(content="first")])
        second_model = FakeModel([AIMessageChunk(content="second")])

        class ModelFactory:
            def __init__(self):
                self.models = [first_model, second_model]

            def create(self, reference, owner):
                del reference, owner
                return self.models.pop(0)

        observation = Observation(
            7,
            "runner-action",
            "ACTION",
            "runner-card",
            "draft-editor",
            request_id="runner-request",
            action_name="save",
            description="Save the draft",
            arguments={"artifactId": "artifact-7"},
            status="COMPLETED",
            result={"revision": 8},
            capability_success=True,
            business_success=True,
        )
        calls = []

        def load(owner, conversation_id, *, after_sequence, limit):
            calls.append((owner, conversation_id, after_sequence, limit))
            return [observation] if after_sequence == 0 else []

        runner = ChatLoopRunner(
            model_factory=ModelFactory(),
            model_reference="deepseek-v4-flash",
            environment="PRT",
            reader=FakeMaterialPort(skill_material()),
            conversation_store=ConversationStore(),
            history_loader=lambda *args: [],
            observation_loader=load,
            system_prompt="base prompt",
        )

        async def run(text, turn_id):
            return [event async for event in runner.iterate(
                user_id=OWNER.user_id,
                conversation_id=99,
                text=text,
                turn_id=turn_id,
            )]

        first_events = asyncio.run(run("first user", "1"))
        second_events = asyncio.run(run("second user", "2"))
        self.assertEqual("done", first_events[-1]["type"])
        self.assertEqual("done", second_events[-1]["type"])
        self.assertEqual([0, 7], [call[2] for call in calls])
        self.assertTrue(all(call[3] == 100 for call in calls))
        first_humans = [
            str(message.content) for message in first_model.observed[0]
            if message.type == "human"
        ]
        self.assertIn(_ACTION_OBSERVATION_MARKER, first_humans[0])
        self.assertEqual("first user", first_humans[1])
        second_content = "\n".join(
            str(message.content) for message in second_model.observed[0]
        )
        self.assertEqual(1, second_content.count(_ACTION_OBSERVATION_MARKER))
        self.assertNotIn("Recent saved Application states", second_content)

    def test_unknown_action_keeps_error_without_inventing_result(self):
        message = _action_observation_message(Observation(
            1,
            "unknown-action",
            "ACTION",
            "card-unknown",
            "draft-editor",
            request_id="request-unknown",
            action_name="export",
            arguments={"format": "MARKDOWN"},
            status="UNKNOWN",
            capability_success=None,
            business_success=None,
            error_code="ACTION_OUTCOME_UNKNOWN",
        ))
        fact = json.loads(str(message.content).split("\n", 2)[-1])
        self.assertEqual("UNKNOWN", fact["systemOutcome"]["status"])
        self.assertEqual(
            "ACTION_OUTCOME_UNKNOWN",
            fact["systemOutcome"]["platformErrorCode"],
        )
        self.assertIsNone(fact["systemOutcome"]["capabilitySuccess"])
        self.assertIsNone(fact["systemOutcome"]["businessSuccess"])
        self.assertNotIn("result", fact["systemOutcome"])
        self.assertNotIn("functionDescription", fact)

    def test_presentation_failure_keeps_actual_business_result_and_error(self):
        message = _action_observation_message(Observation(
            2,
            "presentation-failure",
            "ACTION",
            "card-presentation",
            "draft-editor",
            request_id="request-presentation",
            action_name="save",
            arguments={"artifactId": "artifact-2"},
            status="SUCCEEDED",
            result={"revision": 3},
            capability_success=True,
            business_success=True,
            presentation_status="FAILED",
            presentation_error_code="RESULT_ADAPTER_FAILED",
            error_code="ACTION_PRESENTATION_FAILED",
        ))
        fact = json.loads(str(message.content).split("\n", 2)[-1])
        outcome = fact["systemOutcome"]
        self.assertEqual({"revision": 3}, outcome["result"])
        self.assertTrue(outcome["capabilitySuccess"])
        self.assertTrue(outcome["businessSuccess"])
        self.assertEqual("FAILED", outcome["presentationStatus"])
        self.assertEqual(
            "RESULT_ADAPTER_FAILED", outcome["presentationErrorCode"],
        )
        self.assertEqual(
            "ACTION_PRESENTATION_FAILED", outcome["platformErrorCode"],
        )

    def test_observation_reader_drains_all_pages_without_silent_truncation(self):
        observations = [
            Observation(
                sequence,
                f"render-{sequence}",
                "RENDERED",
                f"card-{sequence}",
                "draft-editor",
            )
            for sequence in range(1, 102)
        ]
        calls = []

        def loader(after_sequence):
            calls.append(after_sequence)
            return [
                observation for observation in observations
                if observation.sequence > after_sequence
            ][:100]

        loaded = _read_observations(loader, 0)
        self.assertEqual(101, len(loaded))
        self.assertEqual([0, 100], calls)

    def test_real_card_store_observations_flow_into_native_history(self):
        from agent_workflow_runtime.chat.cards import (
            ActionObservation,
            ChatCardStore,
        )
        from langgraph.checkpoint.memory import InMemorySaver
        from test_chat_cards import MemoryStorage, metadata, prepared

        conversation = "store-observation-conversation"
        store = ChatCardStore(
            "unused",
            environment="PRT",
            _storage=MemoryStorage(),
        )
        store.setup()
        card = store.save(
            OWNER,
            conversation,
            prepared(),
            metadata(conversation),
        )
        store.claim(
            OWNER,
            conversation,
            card["cardId"],
            "store-request",
            "confirm",
            {"optionId": "second"},
            0,
        )
        store.finish(
            OWNER,
            conversation,
            card["cardId"],
            "store-request",
            {"artifactId": "artifact-store", "revision": 3},
            True,
            True,
            observation=ActionObservation(
                arguments={"artifactId": "artifact-store", "revision": 2},
                result={"artifactId": "artifact-store", "revision": 3},
                capability_success=True,
                business_success=True,
                description="Save the selected artifact",
            ),
        )

        model = FakeModel([AIMessageChunk(content="observed")])
        loop = ChatLoop(
            model_factory=FakeFactory([model]),
            model_reference="deepseek-v4-flash",
            owner=OWNER,
            conversation_id=conversation,
            reader=FakeMaterialPort(skill_material()),
            control_request_id="store-observation-turn",
            checkpointer=InMemorySaver(),
            thread_id="store-observation-thread",
            observation_loader=lambda cursor: store.list_observations(
                OWNER,
                conversation,
                after_sequence=cursor,
                limit=100,
            ),
        )
        self.assertEqual("observed", loop.turn("continue from saved action"))
        content = "\n".join(
            str(message.content) for message in model.observed[0]
        )
        self.assertIn("Save the selected artifact", content)
        self.assertIn('"capabilitySuccess": true', content)
        self.assertIn('"businessSuccess": true', content)
        self.assertIn('"revision": 3', content)
        self.assertEqual(1, content.count(_ACTION_OBSERVATION_MARKER))


if __name__ == "__main__":
    unittest.main()
