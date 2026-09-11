"""Real synchronous Deep Agents/LangGraph stop and mixed-fatal probes."""

from collections import Counter
from threading import Barrier, Event
import time
from typing import Any, TypedDict
import unittest

from deepagents import (
    create_deep_agent, HarnessProfile, GeneralPurposeSubagentProfile, register_harness_profile,
)
from deepagents.backends import StateBackend
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, END, StateGraph

from agent_workflow_runtime.lifecycle import RunStoppedControl
from agent_workflow_runtime.native_control import (
    ControlledRunRunner, RunAdmissionMiddleware, RunGraphBinding, guarded_node, guarded_router,
)
from runtime_phase1.deep_agent_probe import IMPLICIT_DEEP_AGENT_TOOLS
from runtime_phase1.scripted_model import ScriptedToolModel
from lifecycle_support import fixture


class HookModel(ScriptedToolModel):
    hook: Any = None

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.hook:
            self.hook()
        return super()._generate(messages, stop, run_manager, **kwargs)


class NativeStopTest(unittest.TestCase):
    def setUp(self):
        self.repo, self.life, self.run = fixture()
        register_harness_profile(
            "hookmodel", HarnessProfile(excluded_tools=IMPLICIT_DEEP_AGENT_TOOLS,
                                       general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)),
        )
        register_harness_profile(
            "scriptedtoolmodel", HarnessProfile(excluded_tools=IMPLICIT_DEEP_AGENT_TOOLS,
                                               general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)),
        )
        self.runner = ControlledRunRunner(self.life, None, None)

    def facts(self, kind=None):
        result = self.repo.operations(self.run.owner, self.run.run_id)
        return [fact for fact in result if kind is None or fact.kind == kind]

    def stop(self):
        return self.life.stop(self.run.owner, self.run.run_id, "stop")

    def test_model_only_stop_after_dispatch_preserves_actual_model_response(self):
        model = HookModel(responses=[AIMessage(content="Actual late response")], hook=self.stop)
        graph = create_deep_agent(
            model=model, middleware=[RunAdmissionMiddleware(self.life)], checkpointer=MemorySaver(),
        )
        result = self.runner.invoke(self.run, RunGraphBinding(graph, self.life), {"messages": [{"role": "user", "content": "go"}]})
        self.assertEqual("STOPPED", result["status"])
        self.assertEqual(1, model.responseIndex)
        model_facts = self.facts("MODEL")
        self.assertEqual(1, len(model_facts))
        self.assertEqual("RETURNED", model_facts[0].status)
        self.assertIn("Actual late response", model_facts[0].result_json)
        self.assertEqual(0, len(self.facts("FINALIZER")))

    def test_real_summary_retry_rechecks_each_actual_model_start_after_stop(self):
        calls = []
        def first_failure():
            calls.append("actual-summary-call")
            self.stop()
            raise ValueError("synthetic summary attempt failure")
        model = HookModel(responses=[AIMessage(content="Must not execute")], hook=first_failure)
        summary = SummarizationMiddleware(
            model=model, backend=StateBackend(), trigger=("messages", 2), keep=("messages", 1),
        )
        graph = create_deep_agent(
            model=model, middleware=[summary, RunAdmissionMiddleware(self.life)],
            checkpointer=MemorySaver(),
        )
        messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": "synthetic " + str(i)}
                    for i in range(8)]
        result = self.runner.invoke(self.run, RunGraphBinding(graph, self.life), {"messages": messages})
        self.assertEqual("STOPPED", result["status"])
        self.assertEqual(["actual-summary-call"], calls)
        self.assertEqual(1, len(self.facts("MODEL")))
        self.assertEqual("UNCONFIRMED", self.facts("MODEL")[0].status)
        self.assertEqual(0, model.responseIndex)

    def test_parallel_tool_batch_preserves_both_late_results_without_next_model(self):
        entered, stopped = Event(), Event()
        @tool
        def stopper():
            """Synthetic stop-returning tool."""
            if not entered.wait(3):
                raise AssertionError("sibling not admitted")
            self.stop()
            stopped.set()
            return {"actual": "stopper-return"}
        @tool
        def late():
            """Synthetic already-admitted sibling tool."""
            entered.set()
            if not stopped.wait(3):
                raise AssertionError("stop not accepted")
            time.sleep(.05)
            return {"actual": "late-return"}
        model = ScriptedToolModel(responses=[
            AIMessage(content="", tool_calls=[
                {"name": "stopper", "args": {}, "id": "one", "type": "tool_call"},
                {"name": "late", "args": {}, "id": "two", "type": "tool_call"},
            ]),
            AIMessage(content="Must not advance"),
        ])
        graph = create_deep_agent(model=model, tools=[stopper, late],
                                  middleware=[RunAdmissionMiddleware(self.life)],
                                  checkpointer=MemorySaver())
        result = self.runner.invoke(self.run, RunGraphBinding(graph, self.life), {"messages": [{"role": "user", "content": "go"}]})
        self.assertEqual("STOPPED", result["status"])
        self.assertEqual(1, model.responseIndex)
        facts = self.facts("TOOL")
        self.assertEqual(2, len(facts))
        self.assertEqual(["RETURNED", "RETURNED"], sorted(f.status for f in facts))
        self.assertTrue(any("late-return" in f.result_json for f in facts))
        self.assertTrue(any("stopper-return" in f.result_json for f in facts))

    def test_mixed_fatal_and_stop_native_branches_do_not_hide_sibling_fatal(self):
        for fatal_type in (KeyboardInterrupt, SystemExit):
            with self.subTest(fatal_type=fatal_type.__name__):
                self.setUp()
                entered, stop_raised = Event(), Event()
                def fast(state):
                    if not entered.wait(3):
                        raise AssertionError("sibling not admitted")
                    self.stop()
                    return {"actual": "fast"}
                wrapped = guarded_node(self.life, self.run.context(), fast)
                def stop_node(state):
                    try:
                        return wrapped(state)
                    except RunStoppedControl:
                        stop_raised.set()
                        raise
                def fatal(state):
                    entered.set()
                    if not stop_raised.wait(3):
                        raise AssertionError("STOP did not precede fatal")
                    time.sleep(.05)
                    raise fatal_type("synthetic sibling fatal")
                builder = StateGraph(dict)
                builder.add_node("stopper", stop_node)
                builder.add_node("fatal", guarded_node(self.life, self.run.context(), fatal))
                builder.add_edge(START, "stopper")
                builder.add_edge(START, "fatal")
                builder.add_edge("stopper", END)
                builder.add_edge("fatal", END)
                with self.assertRaises(fatal_type):
                    self.runner.invoke(self.run, RunGraphBinding(builder.compile(checkpointer=MemorySaver()), self.life), {})
                self.assertTrue(stop_raised.is_set())
                self.assertEqual("STOPPED", self.life.read(self.run.owner, self.run.run_id).status)
                self.assertTrue(any(fatal_type.__name__ in (f.result_json or "") for f in self.facts()))

    def test_mixed_fatal_and_stop_tool_batch_does_not_hide_sibling_fatal(self):
        class Fatal(BaseException):
            pass
        entered, stopped = Event(), Event()
        @tool
        def stopper():
            """Stop this synthetic run."""
            if not entered.wait(3):
                raise AssertionError("sibling not admitted")
            self.stop()
            stopped.set()
            return "stopper actual"
        @tool
        def fatal():
            """Raise a synthetic non-stop control failure."""
            entered.set()
            if not stopped.wait(3):
                raise AssertionError("stop not accepted")
            time.sleep(.05)
            raise Fatal("synthetic")
        model = ScriptedToolModel(responses=[AIMessage(content="", tool_calls=[
            {"name": "stopper", "args": {}, "id": "one", "type": "tool_call"},
            {"name": "fatal", "args": {}, "id": "two", "type": "tool_call"},
        ])])
        graph = create_deep_agent(model=model, tools=[stopper, fatal],
                                  middleware=[RunAdmissionMiddleware(self.life)],
                                  checkpointer=MemorySaver())
        with self.assertRaises(Fatal):
            self.runner.invoke(self.run, RunGraphBinding(graph, self.life), {"messages": [{"role": "user", "content": "go"}]})
        self.assertTrue(any("Fatal" in (f.result_json or "") for f in self.facts("TOOL")))

    def test_stop_after_node_result_prevents_business_router_and_successor(self):
        counts = Counter()
        def operation(state):
            self.stop()
            return {"actual": 1}
        def route(state):
            counts["router"] += 1
            return "next"
        def successor(state):
            counts["next"] += 1
            return {}
        builder = StateGraph(dict)
        builder.add_node("entry", guarded_node(self.life, self.run.context(), operation))
        builder.add_node("next", guarded_node(self.life, self.run.context(), successor))
        builder.add_edge(START, "entry")
        builder.add_conditional_edges("entry", guarded_router(self.life, self.run.context(), route),
                                      {"next": "next"})
        builder.add_edge("next", END)
        result = self.runner.invoke(self.run, RunGraphBinding(builder.compile(checkpointer=MemorySaver()), self.life), {})
        self.assertEqual("STOPPED", result["status"])
        self.assertEqual({}, dict(counts))
        self.assertTrue(any(f.result_json == '{"actual":1}' for f in self.facts("NODE")))

    def test_parallel_workflow_nodes_bind_actual_model_facts_to_each_trusted_node(self):
        barrier = Barrier(2)
        def node_handler(label):
            def invoke(state):
                model = HookModel(
                    responses=[AIMessage(content="actual-" + label)],
                    hook=lambda: barrier.wait(timeout=3),
                )
                agent = create_deep_agent(
                    model=model, middleware=[RunAdmissionMiddleware(self.life)],
                )
                # Public RunnableConfig propagation must retain our own node
                # binding across each graph's internal "model" node.
                agent.invoke({"messages": [{"role": "user", "content": label}]},
                             context=self.run.context(label))
                return {}
            return invoke
        class BranchState(TypedDict):
            marker: int
        builder = StateGraph(BranchState)
        for label in ("branch-left", "branch-right"):
            builder.add_node(label, guarded_node(
                self.life, self.run.context(label), node_handler(label),
            ))
            builder.add_edge(START, label)
            builder.add_edge(label, END)
        self.runner.invoke(self.run, RunGraphBinding(
            builder.compile(checkpointer=MemorySaver()), self.life), {"marker": 0})
        facts = self.facts("MODEL")
        self.assertEqual(["branch-left", "branch-right"], sorted(f.node_id for f in facts))
        for fact in facts:
            self.assertIn("actual-" + fact.node_id, fact.result_json)
        self.assertEqual("SUCCEEDED", self.life.read(self.run.owner, self.run.run_id).status)
