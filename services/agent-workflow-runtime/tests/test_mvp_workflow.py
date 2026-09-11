"""Offline native subgraph composition checks for the MVP workflow loader."""

import unittest

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, interrupt

from agent_workflow_runtime.native_control import ControlledRunRunner, RunGraphBinding
from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.workflow_loader import compose_workflow, node_operation_id
from lifecycle_support import fixture


class Views:
    def __init__(self):
        self.on_complete = None
        self.statuses = {}
        self.outputs = {}
        self.ensure_calls = 0

    def ensure(self, run, definition, versions):
        self.ensure_calls += 1

    def node(self, owner, run_id, node_id, status):
        self.statuses[node_id] = status

    def complete(self, owner, run_id, node_id, content):
        if self.on_complete is not None:
            self.on_complete(node_id)
        self.statuses[node_id] = "SUCCEEDED"
        self.outputs[node_id] = content


def child(handler):
    builder = StateGraph(MessagesState)
    builder.add_node("work", handler)
    builder.add_edge(START, "work")
    builder.add_edge("work", END)
    return builder.compile()


class WorkflowLoaderTest(unittest.TestCase):
    def test_node_fact_and_view_span_native_subgraph_interrupt(self):
        repository, lifecycle, run = fixture()
        views = Views()

        def plan(state):
            selected = interrupt({"kind": "select"})
            return {"messages": [AIMessage(content="planned " + selected)]}

        def copy(state):
            self.assertEqual("planned chosen", state["messages"][-1].content)
            return {"messages": [AIMessage(content="promotional copy")]}

        definition = {
            "definitionKey": run.definition_key,
            "entryNodeId": run.entry_node_id,
            "nodes": [
                {"nodeId": run.entry_node_id, "skillKey": "activity-planning/plan"},
                {"nodeId": "copy", "skillKey": "activity-planning/copy"},
            ],
        }
        views.on_complete = lambda node_id: self.assertEqual(
            "RETURNED",
            repository.get_operation(
                run.owner, run.run_id, node_operation_id(run.run_id, node_id),
            ).status,
        )
        agents = {
            run.entry_node_id: RunGraphBinding(child(plan), lifecycle),
            "copy": RunGraphBinding(child(copy), lifecycle),
        }
        graph = compose_workflow(
            run, lifecycle, definition, agents, views, MemorySaver(),
        )
        runner = ControlledRunRunner(lifecycle, None, None)
        waiting = runner.invoke(
            run, graph, {"messages": [{"role": "user", "content": "plan"}]},
        )
        pending = waiting["__interrupt__"][0]
        fact = repository.get_operation(
            run.owner, run.run_id, node_operation_id(run.run_id, run.entry_node_id),
        )
        self.assertEqual("IN_FLIGHT", fact.status)
        self.assertEqual("RUNNING", views.statuses[run.entry_node_id])
        self.assertNotIn("copy", views.statuses)

        result = runner.invoke(
            run, graph, Command(resume={pending.id: "chosen"}),
        )
        self.assertEqual("promotional copy", result["messages"][-1].content)
        self.assertEqual(
            {run.entry_node_id: "SUCCEEDED", "copy": "SUCCEEDED"}, views.statuses,
        )
        self.assertEqual(
            {run.entry_node_id: "planned chosen", "copy": "promotional copy"},
            views.outputs,
        )
        facts = repository.operations(run.owner, run.run_id)
        self.assertEqual(
            {"RETURNED"},
            {fact.status for fact in facts if fact.kind == "NODE"},
        )
        self.assertEqual("SUCCEEDED", lifecycle.read(run.owner, run.run_id).status)
        self.assertEqual(1, views.ensure_calls)

    def test_rejects_duplicate_nodes_and_run_entry_mismatch(self):
        _, lifecycle, run = fixture()
        agent = RunGraphBinding(
            child(lambda state: {"messages": [AIMessage(content="unused")]}),
            lifecycle,
        )
        cases = (
            ({"entryNodeId": run.entry_node_id, "nodes": [
                {"nodeId": run.entry_node_id, "skillKey": "one"},
                {"nodeId": run.entry_node_id, "skillKey": "two"},
            ]}, {run.entry_node_id: agent}),
            ({"entryNodeId": "other", "nodes": [
                {"nodeId": "other", "skillKey": "one"},
                {"nodeId": "copy", "skillKey": "two"},
            ]}, {"other": agent, "copy": agent}),
        )
        for definition, agents in cases:
            with self.subTest(definition=definition), self.assertRaisesRegex(
                ActionRejected, "UNSUPPORTED_WORKFLOW_DEFINITION",
            ):
                compose_workflow(
                    run, lifecycle, definition, agents, Views(), MemorySaver(),
                )
