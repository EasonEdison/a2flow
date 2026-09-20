"""S1 event publishing: envelope, sinks, and the five trusted boundary points."""

import unittest
from types import SimpleNamespace
from uuid import UUID

from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphInterrupt
from langgraph.types import Interrupt
from langgraph.graph import END, START, MessagesState, StateGraph

from agent_workflow_runtime import (
    DomainEvent, Interaction, LangGraphContinuation, NullSink, RecordingSink,
    NODE_UNBLOCKED, NODE_WAITING, RUN_FAILED, RUN_FINISHED, RUN_STARTED,
    RUN_STOPPED,
)
from agent_workflow_runtime.lifecycle import RunLifecycle
from agent_workflow_runtime.native_control import ControlledRunRunner, RunGraphBinding
from lifecycle_support import RunRepository
from support import context


def _waiting_graph(run):
    def wait(state):
        raise GraphInterrupt([Interrupt(value={
            "interactionId": "i1", "runId": run.run_id, "nodeId": "node-test",
            "applicationKey": "app.key", "versionId": "v1",
        })])

    graph = StateGraph(MessagesState)
    graph.add_node("node-test", wait)
    graph.add_edge(START, "node-test")
    graph.add_edge("node-test", END)
    return graph.compile(checkpointer=MemorySaver())


def _completing_graph():
    def done(state):
        return state

    graph = StateGraph(MessagesState)
    graph.add_node("node-test", done)
    graph.add_edge(START, "node-test")
    graph.add_edge("node-test", END)
    return graph.compile(checkpointer=MemorySaver())


class DomainEventTests(unittest.TestCase):
    def test_create_fills_identity_fields_and_copies_payload(self):
        payload = {"nodeId": "node-test"}
        event = DomainEvent.create(
            RUN_STARTED, "run-1", "sample.definition", 1008, "PRT",
            payload=payload,
        )
        self.assertEqual(RUN_STARTED, event.event_type)
        self.assertEqual("run-1", event.run_id)
        self.assertEqual("sample.definition", event.workflow_key)
        self.assertEqual(1008, event.user_id)
        self.assertEqual("PRT", event.environment)
        self.assertIsInstance(event.event_id, UUID)
        self.assertIsNotNone(event.occurred_at.tzinfo)
        payload["nodeId"] = "mutated"
        self.assertEqual({"nodeId": "node-test"}, event.payload)

    def test_event_ids_are_unique_and_null_sink_is_noop(self):
        first = DomainEvent.create(RUN_STARTED, "r", "w", 101, "PRT")
        second = DomainEvent.create(RUN_STARTED, "r", "w", 101, "PRT")
        self.assertNotEqual(first.event_id, second.event_id)
        sink = NullSink()
        self.assertIsNone(sink.publish(first))

    def test_recording_sink_preserves_order(self):
        sink = RecordingSink()
        events = [
            DomainEvent.create(kind, "r", "w", 101, "PRT")
            for kind in (RUN_STARTED, NODE_WAITING, RUN_FINISHED)
        ]
        for event in events:
            sink.publish(event)
        self.assertEqual(
            [RUN_STARTED, NODE_WAITING, RUN_FINISHED],
            [event.event_type for event in sink.events],
        )


class BoundaryEventTests(unittest.TestCase):
    def setUp(self):
        self.repository = RunRepository()
        self.sink = RecordingSink()
        self.lifecycle = RunLifecycle(self.repository, event_sink=self.sink)
        self.owner = context().trusted_context
        self.resolve = lambda owner, key: (("WORKFLOW:sample", "v1"),)

    def test_run_started_published_once_on_fresh_allocate(self):
        run, fresh = self.lifecycle.allocate(
            self.owner, "start-control", "sample.definition", {"fresh": True},
            "node-test", self.resolve,
        )
        self.assertTrue(fresh)
        duplicate, again = self.lifecycle.allocate(
            self.owner, "start-control", "sample.definition", {"fresh": True},
            "node-test", self.resolve,
        )
        self.assertFalse(again)
        self.assertEqual(run.run_id, duplicate.run_id)
        started = [e for e in self.sink.events if e.event_type == RUN_STARTED]
        self.assertEqual(1, len(started))
        event = started[0]
        self.assertEqual(run.run_id, event.run_id)
        self.assertEqual("sample.definition", event.workflow_key)
        self.assertEqual(1008, event.user_id)
        self.assertEqual("PRT", event.environment)
        self.assertEqual({"entryNodeId": "node-test"}, event.payload)

    def test_run_finished_on_succeed(self):
        run, _ = self.lifecycle.allocate(
            self.owner, "start-control", "sample.definition", {"fresh": True},
            "node-test", self.resolve,
        )
        self.lifecycle.succeed(self.owner, run.run_id)
        finished = [e for e in self.sink.events if e.event_type == RUN_FINISHED]
        self.assertEqual(1, len(finished))
        self.assertEqual(run.run_id, finished[0].run_id)

    def test_run_stopped_published_once_and_idempotent_stop_is_silent(self):
        run, _ = self.lifecycle.allocate(
            self.owner, "start-control", "sample.definition", {"fresh": True},
            "node-test", self.resolve,
        )
        self.lifecycle.stop(self.owner, run.run_id, "stop-control")
        self.lifecycle.stop(self.owner, run.run_id, "stop-control")
        stopped = [e for e in self.sink.events if e.event_type == RUN_STOPPED]
        self.assertEqual(1, len(stopped))
        self.assertEqual(run.run_id, stopped[0].run_id)

    def test_node_waiting_through_runner(self):
        def waiting_factory(current, lc):
            return RunGraphBinding(_waiting_graph(current), lc), {"messages": []}

        runner = ControlledRunRunner(self.lifecycle, waiting_factory, self.resolve)
        runner.start(self.owner, "waiting-control", "sample.definition",
                     {"fresh": True}, "node-test")
        waiting = [e for e in self.sink.events if e.event_type == NODE_WAITING]
        self.assertEqual(1, len(waiting))
        started = [e for e in self.sink.events if e.event_type == RUN_STARTED]
        self.assertEqual(started[0].run_id, waiting[0].run_id)
        self.assertEqual({"nodeId": "node-test"}, waiting[0].payload)
        self.assertFalse([e for e in self.sink.events if e.event_type == RUN_FINISHED])

    def test_run_finished_via_completing_runner(self):
        def completing_factory(current, lc):
            return RunGraphBinding(_completing_graph(), lc), {"messages": []}

        runner = ControlledRunRunner(self.lifecycle, completing_factory, self.resolve)
        runner.start(self.owner, "complete-control", "sample.definition",
                     {"fresh": True}, "node-test")
        finished = [e for e in self.sink.events if e.event_type == RUN_FINISHED]
        self.assertEqual(1, len(finished))

    def test_run_failed_when_execution_crashes(self):
        def boom_factory(current, lc):
            raise RuntimeError("boom")

        runner = ControlledRunRunner(self.lifecycle, boom_factory, self.resolve)
        with self.assertRaises(RuntimeError):
            runner.start(self.owner, "boom-control", "sample.definition",
                         {"fresh": True}, "node-test")
        failed = [e for e in self.sink.events if e.event_type == RUN_FAILED]
        self.assertEqual(1, len(failed))
        self.assertEqual({"reason": "RuntimeError"}, failed[0].payload)

    def test_node_unblocked_through_continuation(self):
        run, _ = self.lifecycle.allocate(
            self.owner, "start-control", "sample.definition", {"fresh": True},
            "node-test", self.resolve,
        )
        interaction = Interaction(
            run.context("node-test"), "interaction-test", "app.key", "v1",
            run.thread_id, (),
        )

        class FakeGraph:
            def __init__(self, snapshot):
                self.snapshot = snapshot
                self.invokes = []

            def get_state(self, config, subgraphs=False):
                if subgraphs:
                    return self.snapshot
                return SimpleNamespace(next=())

            def invoke(self, *args, **kwargs):
                self.invokes.append(args)
                return {}

        snapshot = SimpleNamespace(tasks=[
            SimpleNamespace(
                interrupts=[SimpleNamespace(
                    id="int-1",
                    value={"interactionId": "interaction-test",
                           "runId": run.run_id, "nodeId": "node-test",
                           "applicationKey": "app.key", "versionId": "v1"},
                )],
                state=SimpleNamespace(),
            ),
        ])
        fake = FakeGraph(snapshot)
        binding = RunGraphBinding(fake, self.lifecycle)
        continuation = LangGraphContinuation(binding, lifecycle=self.lifecycle)
        continuation(interaction, "resume-control")

        types = [e.event_type for e in self.sink.events]
        self.assertEqual([RUN_STARTED, NODE_UNBLOCKED, RUN_FINISHED], types)
        unblocked = self.sink.events[1]
        self.assertEqual(run.run_id, unblocked.run_id)
        self.assertEqual({"nodeId": "node-test"}, unblocked.payload)
        self.assertEqual(1, len(fake.invokes))


if __name__ == "__main__":
    unittest.main()
