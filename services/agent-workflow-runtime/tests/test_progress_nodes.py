"""Real parallel LangGraph business-node observation attribution."""

from threading import Barrier
from typing import TypedDict
import unittest

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

from agent_workflow_runtime.native_control import ControlledRunRunner, RunGraphBinding, guarded_node
from agent_workflow_runtime.progress_observer import current_progress
from agent_workflow_runtime.progress_writer import ProgressWriter
from lifecycle_support import fixture
from test_progress_writer import Store


class State(TypedDict, total=False):
    left: bool
    right: bool


class ProgressNodesTest(unittest.TestCase):
    def test_parallel_nodes_have_distinct_trusted_segments_and_operation_associations(self):
        repository, life, run = fixture()
        display = Store()
        writer = ProgressWriter(display).start()
        self.addCleanup(writer.shutdown)
        barrier = Barrier(2)
        observed = {}
        def node(name):
            def work(state):
                scope = current_progress()
                observed[name] = (scope.execution_id, scope.context.invocation_scope.node_id)
                barrier.wait(2)
                return {name: True}
            return guarded_node(life, run.context(name), work)
        builder = StateGraph(State)
        for name in ("left", "right"):
            builder.add_node(name, node(name))
            builder.add_edge(START, name)
            builder.add_edge(name, END)
        graph = RunGraphBinding(builder.compile(checkpointer=MemorySaver()), life, writer)
        result = ControlledRunRunner(life, None, None).invoke(run, graph, {})
        self.assertEqual({"left": True, "right": True}, result)
        self.assertNotEqual(observed["left"][0], observed["right"][0])
        self.assertEqual("left", observed["left"][1])
        self.assertEqual("right", observed["right"][1])
        self.assertTrue(writer.shutdown())
        bindings = {b["nodeId"]: b for b, _, _, _ in display.calls}
        self.assertEqual({"left", "right"}, set(bindings))  # no invented entry/root segment
        facts = repository.operations(run.owner, run.run_id)
        for name, binding in bindings.items():
            self.assertTrue(any(f.node_id == name and f.kind == "NODE"
                                and f.operation_id == binding["nodeOperationId"] for f in facts))
