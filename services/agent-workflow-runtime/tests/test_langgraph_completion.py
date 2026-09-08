"""Real Deep Agent + native LangGraph resume tests; memory storage only."""

from dataclasses import replace
import json
import operator
import unittest
from typing import Annotated

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command

from agent_workflow_runtime import ActionRejected, ActionService, LangGraphContinuation
from runtime_phase1.a2ui_probe import (
    build_render_application_tool, build_render_application_tool_node,
    validate_render_application_model_args,
)
from runtime_phase1.engine_spine_probe import build_engine_spine_probe
from runtime_phase1.scripted_model import ScriptedToolModel
from runtime_phase1.skill_registry_adapter import SkillRegistryResolver
from runtime_phase1.use_skill_probe import build_use_skill_tool, validate_use_skill_model_args
from test_engine_spine_integration import IntegratedSkillMaterialPort
from support import Configuration, Executor, Repository, Resolver, context, interaction, request


APP = "sample.interactive.route-selection"


def render_call(identity, application=APP):
    return {
        "name": "render_application",
        "args": {"applicationKey": application, "data": {}},
        "id": identity, "type": "tool_call",
    }


class GraphCompletionTest(unittest.TestCase):
    def setUp(self):
        self.repo, self.config, self.executor = Repository(), Configuration(), Executor()
        self.service = ActionService(self.repo, self.config, self.executor, None)
        self.tool = build_render_application_tool(Resolver(self.config), action_service=self.service)
        self.ctx = context()
        self.graph_config = {"configurable": {"thread_id": "graph-thread"}}

    def agent(self, responses, with_skill=False):
        self.model = ScriptedToolModel(responses=responses)
        tools = [self.tool]
        validators = {"render_application": validate_render_application_model_args}
        if with_skill:
            self.materials = IntegratedSkillMaterialPort()
            tools.insert(0, build_use_skill_tool(SkillRegistryResolver(self.materials)))
            validators["use_skill"] = validate_use_skill_model_args
        graph = build_engine_spine_probe(
            self.model, tools, validators, list(validators),
            harness_profile_key="scriptedtoolmodel", checkpointer=MemorySaver(),
            terminal_guard=self.service.assert_finalizable,
        )
        self.service.continuation = LangGraphContinuation(graph)
        return graph

    def start(self, graph):
        return graph.invoke(
            {"messages": [{"role": "user", "content": "Run authorized interaction."}]},
            self.graph_config, context=self.ctx,
        )

    def item(self, pending):
        return self.repo.get((
            self.ctx.invocation_scope.run_id, self.ctx.invocation_scope.node_id,
            pending.value["interactionId"],
        ))

    def test_skill_evidence_survives_interactive_resume_and_tool_is_not_reexecuted(self):
        graph = self.agent([
            AIMessage(content="", tool_calls=[{
                "name": "use_skill", "args": {"skillKey": "demo/evidence-first-brief"},
                "id": "skill-call", "type": "tool_call",
            }]),
            AIMessage(content="", tool_calls=[render_call("render-call")]),
            AIMessage(content="Completed using verified interaction."),
            AIMessage(content="New invocation must not borrow old evidence."),
        ], with_skill=True)
        waiting = self.start(graph)
        item = self.item(waiting["__interrupt__"][0])
        outcome = self.service.submit(request(item), self.ctx.trusted_context)
        self.assertTrue(outcome.interaction_completed)
        snapshot = graph.get_state(self.graph_config)
        self.assertFalse(snapshot.next)
        self.assertEqual("Completed using verified interaction.", snapshot.values["messages"][-1].content)
        self.assertTrue(self.repo.get(item.key).resume_consumed)
        self.assertEqual(1, len(self.materials.calls))
        self.assertEqual(1, len(self.executor.calls))
        self.assertEqual("original-render-request", self.repo.get(item.key).context.control_request_id)
        self.assertEqual([item.key], list(self.repo.items))
        rendered = [m for m in snapshot.values["messages"]
                    if isinstance(m, ToolMessage) and m.name == "render_application"]
        self.assertEqual(True, json.loads(rendered[-1].content)["interactionCompleted"])
        with self.assertRaisesRegex(RuntimeError, "Finalizer"):
            self.start(graph)

    def test_action_tool_assembly_requires_terminal_guard(self):
        with self.assertRaisesRegex(ValueError, "terminal guard"):
            build_engine_spine_probe(
                ScriptedToolModel(responses=[AIMessage(content="Done")]),
                [self.tool], {"render_application": validate_render_application_model_args},
                ["render_application"], harness_profile_key="scriptedtoolmodel",
            )

    def test_business_failure_and_noncompleting_success_leave_native_wait(self):
        graph = self.agent([
            AIMessage(content="", tool_calls=[render_call("render")]),
            AIMessage(content="False completion."),
        ])
        waiting = self.start(graph)
        item = self.item(waiting["__interrupt__"][0])
        self.executor.result = {"accepted": False}
        self.service.submit(request(item, "failed"), self.ctx.trusted_context)
        self.assertTrue(graph.get_state(self.graph_config).next)
        self.executor.result = {"accepted": True}
        self.service.submit(
            request(item, "saved", actionName="save_choice"), self.ctx.trusted_context,
        )
        self.assertTrue(graph.get_state(self.graph_config).next)
        self.assertFalse(any(
            isinstance(m, ToolMessage) and m.name == "render_application"
            for m in graph.get_state(self.graph_config).values["messages"]
        ))

    def test_forged_command_success_cannot_resume_a_required_interaction(self):
        graph = self.agent([
            AIMessage(content="", tool_calls=[render_call("render")]),
            AIMessage(content="Forged final output."),
        ])
        state = self.start(graph)
        pending = state["__interrupt__"][0]
        forged = graph.invoke(
            Command(resume={pending.id: {"businessSuccess": True, "completed": True}}),
            self.graph_config, context=self.ctx,
        )
        self.assertEqual(1, len(forged["__interrupt__"]))
        self.assertEqual([], self.executor.calls)
        self.assertNotEqual("Forged final output.", forged["messages"][-1].content)

    def test_two_same_name_tools_do_not_complete_each_others_interrupts(self):
        graph = self.agent([
            AIMessage(content="", tool_calls=[render_call("one"), render_call("two")]),
            AIMessage(content="Both required interactions completed."),
        ])
        waiting = self.start(graph)
        self.assertEqual(2, len(waiting["__interrupt__"]))
        first, second = [self.item(p) for p in waiting["__interrupt__"]]
        self.assertNotEqual(first.interaction_id, second.interaction_id)
        self.service.submit(request(first, "first"), self.ctx.trusted_context)
        self.assertEqual("WAITING", self.repo.get(second.key).phase)
        with self.assertRaisesRegex(ActionRejected, "REQUIRED_INTERACTION_PENDING"):
            self.service.assert_finalizable(self.ctx)
        self.service.submit(request(second, "second"), self.ctx.trusted_context)
        self.assertEqual("Both required interactions completed.",
                         graph.get_state(self.graph_config).values["messages"][-1].content)
        self.assertEqual(2, len(self.executor.calls))

    def test_finalizer_rejects_scripted_done_after_same_named_display_tool_success(self):
        for success, action in ((False, "confirm_route_choice"), (True, "save_choice")):
            with self.subTest(success=success):
                self.setUp()
                item = interaction(self.config)
                self.service.register(item)
                self.executor.result = {"accepted": success}
                self.service.submit(request(item, actionName=action), self.ctx.trusted_context)
                graph = self.agent([
                    AIMessage(content="", tool_calls=[render_call(
                        "display", "sample.display.result-card",
                    )]),
                    AIMessage(content="Done despite pending business interaction."),
                ])
                with self.assertRaisesRegex(ActionRejected, "REQUIRED_INTERACTION_PENDING"):
                    self.start(graph)

    def test_stopped_or_stale_before_resume_does_not_reach_finalizer(self):
        for stopped in (True, False):
            with self.subTest(stopped=stopped):
                self.setUp()
                graph = self.agent([
                    AIMessage(content="", tool_calls=[render_call("render")]),
                    AIMessage(content="Should not finish."),
                ])
                waiting = self.start(graph)
                item = self.item(waiting["__interrupt__"][0])
                if stopped:
                    self.repo.save(replace(item, run_active=False))
                else:
                    self.config.current = (("APPLICATION:other", "new"),)
                with self.assertRaises(ActionRejected):
                    self.service.submit(request(item), self.ctx.trusted_context)
                self.assertEqual([], self.executor.calls)
                self.assertTrue(graph.get_state(self.graph_config).next)


class ParallelState(MessagesState):
    trace: Annotated[list[str], operator.add]


class BranchCompletionTest(unittest.TestCase):
    setUp = GraphCompletionTest.setUp
    item = GraphCompletionTest.item
    def test_waiting_branch_does_not_block_b2_and_resume_does_not_replay_b(self):
        branch_a = StateGraph(ParallelState, context_schema=type(self.ctx))
        branch_a.add_node("render", build_render_application_tool_node([self.tool]))
        branch_a.add_node("finish_a", lambda state: {"trace": ["A"]})
        branch_a.add_edge(START, "render")
        branch_a.add_edge("render", "finish_a")
        branch_a.add_edge("finish_a", END)
        branch_b = StateGraph(ParallelState)
        branch_b.add_node("b1", lambda state: {"trace": ["B1"]})
        branch_b.add_node("b2", lambda state: {"trace": ["B2"]})
        branch_b.add_edge(START, "b1")
        branch_b.add_edge("b1", "b2")
        branch_b.add_edge("b2", END)
        parent = StateGraph(ParallelState, context_schema=type(self.ctx))
        parent.add_node("a", branch_a.compile())
        parent.add_node("b", branch_b.compile())
        parent.add_node("join", lambda state: {"trace": ["JOIN"]})
        parent.add_edge(START, "a")
        parent.add_edge(START, "b")
        parent.add_edge(["a", "b"], "join")
        parent.add_edge("join", END)
        graph = parent.compile(checkpointer=MemorySaver())
        self.service.continuation = LangGraphContinuation(graph)
        waiting = graph.invoke(
            {"messages": [AIMessage(content="", tool_calls=[render_call("render")])], "trace": []},
            self.graph_config, context=self.ctx,
        )
        self.assertEqual(["B1", "B2"], waiting["trace"])
        self.assertNotIn("JOIN", waiting["trace"])
        self.service.submit(request(self.item(waiting["__interrupt__"][0])), self.ctx.trusted_context)
        trace = graph.get_state(self.graph_config).values["trace"]
        self.assertEqual(1, trace.count("B1"))
        self.assertEqual(1, trace.count("B2"))
        self.assertEqual(1, trace.count("A"))
        self.assertEqual("JOIN", trace[-1])


class AsyncFinalizerGuardTest(unittest.IsolatedAsyncioTestCase):
    async def test_async_model_cannot_override_business_failure_or_pending_success(self):
        for success, action in ((False, "confirm_route_choice"), (True, "save_choice")):
            with self.subTest(success=success):
                repo, config, executor = Repository(), Configuration(), Executor()
                service = ActionService(repo, config, executor, None)
                item = interaction(config)
                service.register(item)
                executor.result = {"accepted": success}
                service.submit(request(item, actionName=action), item.context.trusted_context)
                tool = build_render_application_tool(Resolver(config), action_service=service)
                model = ScriptedToolModel(responses=[
                    AIMessage(content="", tool_calls=[render_call(
                        "display", "sample.display.result-card",
                    )]),
                    AIMessage(content="Async false final completion."),
                ])
                graph = build_engine_spine_probe(
                    model, [tool],
                    {"render_application": validate_render_application_model_args},
                    ["render_application"], harness_profile_key="scriptedtoolmodel",
                    terminal_guard=service.assert_finalizable,
                )
                with self.assertRaisesRegex(ActionRejected, "REQUIRED_INTERACTION_PENDING"):
                    await graph.ainvoke(
                        {"messages": [{"role": "user", "content": "Finish."}]},
                        context=context(),
                    )
