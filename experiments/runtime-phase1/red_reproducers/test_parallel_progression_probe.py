"""Minimal SDK probe for independent parallel branch progression."""

import operator
import unittest
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class ParallelProbeState(TypedDict):
    """Append-only execution trace for the synthetic graph."""

    trace: Annotated[list[str], operator.add]


class ParallelProgressionProbeTest(unittest.TestCase):
    """Characterizes whether one interrupt blocks a sibling's next superstep."""

    def test_sibling_reaches_b2_while_a_waits_and_join_stays_closed(self) -> None:
        """Break caught: an A interrupt freezes independent B progression."""

        def wait_a(state: ParallelProbeState) -> ParallelProbeState:
            del state
            interrupt({"interactionId": "interaction-a", "nodeId": "A"})
            return {"trace": ["A_RESUMED"]}

        def run_b1(state: ParallelProbeState) -> ParallelProbeState:
            del state
            return {"trace": ["B1"]}

        def run_b2(state: ParallelProbeState) -> ParallelProbeState:
            del state
            return {"trace": ["B2"]}

        def join(state: ParallelProbeState) -> ParallelProbeState:
            del state
            return {"trace": ["JOIN"]}

        builder = StateGraph(ParallelProbeState)
        builder.add_node("wait_a", wait_a)
        builder.add_node("run_b1", run_b1)
        builder.add_node("run_b2", run_b2)
        builder.add_node("join", join)
        builder.add_edge(START, "wait_a")
        builder.add_edge(START, "run_b1")
        builder.add_edge("run_b1", "run_b2")
        builder.add_edge(["wait_a", "run_b2"], "join")
        builder.add_edge("join", END)
        graph = builder.compile()

        state = graph.invoke({"trace": []})

        self.assertEqual(1, len(state["__interrupt__"]))
        self.assertEqual(["B1", "B2"], state["trace"])
        self.assertNotIn("JOIN", state["trace"])
