"""Candidate probe: compile each Workflow branch as a native subgraph."""

import operator
import unittest
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class SubgraphParallelState(TypedDict):
    """Append-only trace shared by parent and branch subgraphs."""

    trace: Annotated[list[str], operator.add]


class SubgraphParallelProbeTest(unittest.TestCase):
    """Characterizes branch-local progression under a sibling interrupt."""

    def test_b_subgraph_reaches_b2_while_a_subgraph_waits(self) -> None:
        """Candidate: each branch is one native parent node, not a scheduler."""

        def wait_a(state: SubgraphParallelState) -> SubgraphParallelState:
            del state
            interrupt({"interactionId": "interaction-a", "nodeId": "A"})
            return {"trace": ["A_RESUMED"]}

        branch_a_builder = StateGraph(SubgraphParallelState)
        branch_a_builder.add_node("wait_a", wait_a)
        branch_a_builder.add_edge(START, "wait_a")
        branch_a_builder.add_edge("wait_a", END)
        branch_a = branch_a_builder.compile()

        def run_b1(state: SubgraphParallelState) -> SubgraphParallelState:
            del state
            return {"trace": ["B1"]}

        def run_b2(state: SubgraphParallelState) -> SubgraphParallelState:
            del state
            return {"trace": ["B2"]}

        branch_b_builder = StateGraph(SubgraphParallelState)
        branch_b_builder.add_node("run_b1", run_b1)
        branch_b_builder.add_node("run_b2", run_b2)
        branch_b_builder.add_edge(START, "run_b1")
        branch_b_builder.add_edge("run_b1", "run_b2")
        branch_b_builder.add_edge("run_b2", END)
        branch_b = branch_b_builder.compile()

        def join(state: SubgraphParallelState) -> SubgraphParallelState:
            del state
            return {"trace": ["JOIN"]}

        parent_builder = StateGraph(SubgraphParallelState)
        parent_builder.add_node("branch_a", branch_a)
        parent_builder.add_node("branch_b", branch_b)
        parent_builder.add_node("join", join)
        parent_builder.add_edge(START, "branch_a")
        parent_builder.add_edge(START, "branch_b")
        parent_builder.add_edge(["branch_a", "branch_b"], "join")
        parent_builder.add_edge("join", END)
        graph = parent_builder.compile(checkpointer=MemorySaver())

        state = graph.invoke(
            {"trace": []},
            {"configurable": {"thread_id": "subgraph-parallel-probe-1"}},
        )

        self.assertEqual(1, len(state["__interrupt__"]))
        self.assertEqual(
            {"interactionId": "interaction-a", "nodeId": "A"},
            state["__interrupt__"][0].value,
        )
        self.assertEqual(["B1", "B2"], state["trace"])
        self.assertNotIn("JOIN", state["trace"])
