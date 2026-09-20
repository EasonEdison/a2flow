"""Run stop/restart, strict records and Action commit-boundary offline tests."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from threading import Event
import unittest
from unittest.mock import Mock, patch

from skillweave_contracts import TrustedContext
from agent_workflow_runtime import ActionRejected, ActionService
from agent_workflow_runtime.lifecycle import RunStoppedControl, RunRecord
from agent_workflow_runtime.native_control import ControlledRunRunner, RunGraphBinding, guarded_node
from agent_workflow_runtime.postgres_lifecycle import decode_record, encode_record, PostgresRunRepository
from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from lifecycle_support import fixture
from support import Configuration, Executor, Repository, interaction, request


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.repository, self.lifecycle, self.run = fixture()
        self.owner = self.run.owner

    def test_no_card_stop_is_durable_authorized_and_never_success(self):
        for owner in (TrustedContext(1012, "PRT"), TrustedContext(self.owner.user_id, "ONLINE")):
            with self.assertRaises(ActionRejected):
                self.lifecycle.stop(owner, self.run.run_id, "stop")
        stopped = self.lifecycle.stop(self.owner, self.run.run_id, "stop")
        self.assertEqual("STOPPED", stopped["status"])
        self.assertFalse(stopped["inFlightCallsStillPending"])
        self.assertEqual(stopped, self.lifecycle.stop(self.owner, self.run.run_id, "stop"))
        with self.assertRaises(RunStoppedControl):
            self.lifecycle.succeed(self.owner, self.run.run_id)
        for kind in ("NODE", "ROUTER", "MODEL", "TOOL", "ACTION", "RETRY", "FINALIZER"):
            with self.subTest(kind=kind), self.assertRaises(RunStoppedControl):
                self.lifecycle.admit(self.owner, self.run.run_id, "node-test", kind)

    def test_inflight_actual_result_survives_stop_without_progress(self):
        fact = self.lifecycle.admit(self.owner, self.run.run_id, "node-test", "MODEL")
        result = self.lifecycle.stop(self.owner, self.run.run_id, "stop")
        self.assertEqual(1, result["inFlightCallCount"])
        self.lifecycle.finish(self.owner, self.run.run_id, fact.operation_id, {"actual": 7})
        self.assertEqual("STOPPED", self.lifecycle.snapshot(self.owner, self.run.run_id)["status"])
        self.assertFalse(self.lifecycle.snapshot(self.owner, self.run.run_id)["inFlightCallsStillPending"])
        self.assertEqual('{"actual":7}', self.repository.get_operation(
            self.owner, self.run.run_id, fact.operation_id).result_json)

    def test_stopped_restart_never_reads_old_input_versions_or_facts(self):
        self.lifecycle.stop(self.owner, self.run.run_id, "stop")
        raw = self.repository.runs[(self.owner, self.run.run_id)]
        raw["initial_inputs_json"] = "corrupt prior context"
        raw["versions"] = "corrupt prior versions"
        self.repository.forbid_run_read.add(self.run.run_id)
        self.repository.forbid_fact_read.add(self.run.run_id)
        resolved = []
        def current(owner, key):
            resolved.append((owner, key))
            return (("WORKFLOW:sample", "v2"),)
        new, fresh = self.lifecycle.allocate(
            self.owner, "restart", self.run.definition_key, {"new": 1}, "node-test", current,
            stopped_run_id=self.run.run_id,
        )
        duplicate, again = self.lifecycle.allocate(
            self.owner, "restart", self.run.definition_key, {"new": 1}, "node-test", current,
            stopped_run_id=self.run.run_id,
        )
        self.assertTrue(fresh)
        self.assertFalse(again)
        self.assertEqual(new, duplicate)
        self.assertNotEqual(self.run.run_id, new.run_id)
        self.assertNotEqual(self.run.thread_id, new.thread_id)
        self.assertEqual((("WORKFLOW:sample", "v2"),), new.versions)
        self.assertEqual('{"new":1}', new.initial_inputs_json)
        self.assertEqual(1, len(resolved))
        with self.assertRaisesRegex(ActionRejected, "CONTROL_REQUEST_CONFLICT"):
            self.lifecycle.allocate(self.owner, "restart", self.run.definition_key,
                                    {"new": 2}, "node-test", current, stopped_run_id=self.run.run_id)

    def test_pg_restart_projection_never_selects_old_document_fields(self):
        repo = PostgresRunRepository("offline")
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = {
            "user_id": self.owner.user_id, "environment": self.owner.environment,
            "run_id": self.run.run_id, "status": "STOPPED", "definition_key": self.run.definition_key,
        }
        repo._local.connection, repo._local.owner = connection, self.owner
        result = repo.restart_identity(self.owner, self.run.run_id)
        statement = connection.execute.call_args.args[0]
        self.assertNotIn("SELECT document", statement)
        self.assertNotIn("initial_inputs", statement)
        self.assertNotIn("versions", statement)
        self.assertEqual("STOPPED", result["status"])

    def test_active_read_keeps_strict_validation_even_if_restart_projection_is_narrow(self):
        for change in ({"revision": True}, {"versions": "corrupt"}, {"initial_inputs_json": "bad"},
                       {"status": "UNKNOWN"}, {"extra": "forbidden"}):
            with self.subTest(change=change), self.assertRaises(ActionRejected):
                decode_record({**encode_record(self.run), **change}, RunRecord)

    def test_other_baseexception_and_forged_stop_are_not_classified_as_stopped(self):
        runner = ControlledRunRunner(self.lifecycle, None, None)
        for error in (KeyboardInterrupt(), SystemExit(), RunStoppedControl(self.run.run_id)):
            class Graph:
                def invoke(self, *args, **kwargs):
                    raise error
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)):
                runner.invoke(self.run, RunGraphBinding(Graph(), self.lifecycle), {})
        self.assertEqual("RUNNING", self.lifecycle.read(self.owner, self.run.run_id).status)

    def test_native_old_resume_rejects_before_graph_is_called(self):
        self.lifecycle.stop(self.owner, self.run.run_id, "stop")
        graph = Mock()
        result = ControlledRunRunner(self.lifecycle, None, None).invoke(
            self.run, graph, Command(resume={"old": True}))
        self.assertEqual("STOPPED", result["status"])
        graph.invoke.assert_not_called()


class ActionStopTest(unittest.TestCase):
    def test_stop_does_not_wait_for_action_admission_lock_and_late_actual_is_saved(self):
        runs, lifecycle, run = fixture()
        repo, config, executor = Repository(), Configuration(), Executor()
        service = ActionService(repo, config, executor, lambda *_: self.fail("must not resume"), lifecycle=lifecycle)
        item = replace(interaction(config), context=run.context(), graph_thread_id=run.thread_id)
        service.register(item)
        entered, release = Event(), Event()
        def hook():
            # Both test repositories have committed reservation before dispatch.
            self.assertEqual("EXECUTING", repo.get(item.key).attempts[0].status)
            self.assertEqual(0, runs.scope_depth)
            self.assertEqual("IN_FLIGHT", runs.operations(run.owner, run.run_id)[0].status)
            entered.set()
            if not release.wait(3):
                raise AssertionError("test release timed out")
        executor.hook = hook
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(service.submit, request(item), run.owner)
            self.assertTrue(entered.wait(3))
            stopped = lifecycle.stop(run.owner, run.run_id, "stop")
            self.assertTrue(stopped["inFlightCallsStillPending"])
            self.assertFalse(future.done())
            release.set()
            with self.assertRaises(RunStoppedControl):
                future.result(timeout=3)
        self.assertTrue(repo.get(item.key).attempts[-1].business_success)
        self.assertEqual("STOPPED", lifecycle.read(run.owner, run.run_id).status)
        self.assertEqual("RETURNED", runs.operations(run.owner, run.run_id)[0].status)
        with self.assertRaises(RunStoppedControl):
            service.submit(request(item), run.owner)


class FreshGraphTest(unittest.TestCase):
    def test_real_fresh_factory_blank_state_new_config_and_duplicate_invokes_once(self):
        runs, lifecycle, old = fixture()
        unknown = lifecycle.admit(old.owner, old.run_id, "node-test", "ACTION")
        lifecycle.finish(old.owner, old.run_id, unknown.operation_id, None, status="UNCONFIRMED")
        lifecycle.stop(old.owner, old.run_id, "stop")
        runs.forbid_run_read.add(old.run_id)
        runs.forbid_fact_read.add(old.run_id)
        factory_calls, business_calls = [], []
        class NoOldCheckpoint(MemorySaver):
            def get_tuple(self, config):
                if config["configurable"]["thread_id"] == old.thread_id:
                    raise AssertionError("old checkpoint read")
                return super().get_tuple(config)
        def factory(run, life):
            factory_calls.append(run)
            def business(state):
                self.assertEqual({"fresh": "input"}, state)
                self.assertEqual((("WORKFLOW:sample", "v2"),), run.versions)
                business_calls.append(run.run_id)
                return {"newResult": True}
            builder = StateGraph(dict)
            builder.add_node("entry", guarded_node(life, run.context(), business))
            builder.add_edge(START, "entry")
            builder.add_edge("entry", END)
            return RunGraphBinding(builder.compile(checkpointer=NoOldCheckpoint()), life), json.loads(run.initial_inputs_json)
        runner = ControlledRunRunner(lifecycle, factory, lambda *_: (("WORKFLOW:sample", "v2"),))
        def restart():
            return runner.start(old.owner, "restart", old.definition_key, {"fresh": "input"},
                                "node-test", stopped_run_id=old.run_id)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: restart(), range(2)))
        self.assertEqual(results[0]["runId"], results[1]["runId"])
        self.assertNotEqual(old.run_id, results[0]["runId"])
        self.assertNotEqual(old.thread_id, results[0]["threadId"])
        self.assertEqual(1, len(factory_calls))
        self.assertEqual(1, len(business_calls))
        self.assertEqual("STOPPED", runs.runs[(old.owner, old.run_id)]["status"])


class ControlledBindingTest(unittest.TestCase):
    def test_raw_graph_and_legacy_action_service_are_not_af04_entries(self):
        _, life, run = fixture()
        runner = ControlledRunRunner(life, None, None)
        graph = Mock()
        with self.assertRaisesRegex(ActionRejected, "CONTROLLED_GRAPH_BINDING_REQUIRED"):
            runner.invoke(run, graph, {})
        graph.invoke.assert_not_called()
        legacy = ActionService(Repository(), Configuration(), Executor(), None)
        with self.assertRaisesRegex(ActionRejected, "CONTROLLED_ACTION_BINDING_REQUIRED"):
            runner.action(run, legacy, {})

    def test_original_fatal_survives_failed_operation_and_control_receipt_saves(self):
        _, life, run = fixture()
        fatal = KeyboardInterrupt("synthetic")
        def fail():
            raise fatal
        with patch.object(life, "finish", side_effect=RuntimeError("synthetic storage")):
            with self.assertRaises(KeyboardInterrupt) as raised:
                life.execute(run.context(), "NODE", fail)
        self.assertIs(fatal, raised.exception)
        def factory(*_):
            raise fatal
        runner = ControlledRunRunner(life, factory, lambda *_: run.versions)
        with patch.object(life, "control_status", side_effect=RuntimeError("synthetic storage")):
            with self.assertRaises(KeyboardInterrupt) as raised:
                runner.start(run.owner, "new-start", run.definition_key, {}, "node-test")
        self.assertIs(fatal, raised.exception)

    def test_uncertain_factory_is_not_replayed_by_duplicate_start(self):
        _, life, run = fixture()
        factory = Mock(side_effect=RuntimeError("synthetic startup failure"))
        runner = ControlledRunRunner(life, factory, lambda *_: run.versions)
        with self.assertRaises(RuntimeError):
            runner.start(run.owner, "uncertain-start", run.definition_key, {}, "node-test")
        assigned = runner.start(run.owner, "uncertain-start", run.definition_key, {}, "node-test")
        self.assertEqual("RUNNING", assigned["status"])
        self.assertEqual(1, factory.call_count)
        with life.repository.control_scope(run.owner, "uncertain-start"):
            self.assertEqual("UNCONFIRMED", life.repository.get_control(
                run.owner, "uncertain-start").status)
