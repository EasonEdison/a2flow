"""AF04 opt-in PG OS-process probes; discovery never creates resources."""

import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
import time
import unittest
from uuid import uuid4

from langgraph.checkpoint.postgres import PostgresSaver
from agent_workflow_runtime.postgres import PostgresInteractionRepository
from agent_workflow_runtime.postgres_lifecycle import PostgresRunRepository
from pg_lifecycle_worker import connection, conninfo, event, value


def cleanup_children(children):
    """Reap every exact owned Popen even if setUp or another cleanup failed."""
    failures = []
    for child in children:
        try:
            try:
                if child.poll() is None:
                    try:
                        child.terminate()
                    except ProcessLookupError:
                        pass
            finally:
                try:
                    child.communicate(timeout=5)
                except BaseException as wait_error:
                    # A timeout or failed wait still gets a bounded kill/reap
                    # attempt. This Popen was created and registered by us.
                    try:
                        try:
                            child.kill()
                        except ProcessLookupError:
                            pass
                    finally:
                        child.communicate(timeout=5)
                    if not isinstance(wait_error, subprocess.TimeoutExpired):
                        raise
        except BaseException as error:
            failures.append(error)
    if failures:
        failures[0].add_note("AF04_OWNED_CHILD_CLEANUP_FAILURE_COUNT=" + str(len(failures)))
        raise failures[0]


@unittest.skipUnless(os.environ.get("A2FLOW_RUNTIME04_SOCKET"), "requires separately authorized AF04 PG window")
class PostgresLifecycleProcessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PostgresInteractionRepository(conninfo()).setup()
        PostgresRunRepository(conninfo()).setup()
        with connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS runtime04_probe_events (
                case_id TEXT NOT NULL, name TEXT NOT NULL, value BIGINT NOT NULL,
                PRIMARY KEY(case_id,name))""")
        with PostgresSaver.from_conn_string(conninfo()) as saver:
            saver.setup()
        cls.peak, cls.observer_error, cls.observer_stop = 0, None, Event()
        def observe():
            try:
                with connection() as conn:
                    while not cls.observer_stop.wait(.005):
                        count = conn.execute("""SELECT count(*) AS n FROM pg_stat_activity
                            WHERE usename=current_user AND datname=current_database()""").fetchone()["n"]
                        cls.peak = max(cls.peak, count)
            except Exception as error:
                cls.observer_error = type(error).__name__
        cls.observer = Thread(target=observe)
        cls.observer.start()

    @classmethod
    def tearDownClass(cls):
        cls.observer_stop.set()
        cls.observer.join(5)
        if cls.observer.is_alive() or cls.observer_error or cls.peak > 8:
            raise AssertionError("AF04 connection observer or budget failed")
        print(json.dumps({"observedRuntimeConnectionPeak": cls.peak, "sampleIntervalMs": 5,
                          "includesObserver": True, "claim": "observed peak, not exact transient maximum"}))

    def setUp(self):
        self.children = []
        self.addCleanup(cleanup_children, self.children)
        self.case = "af04-" + uuid4().hex
        self.ids = self.call("allocate")

    def start(self, mode, **options):
        if hasattr(self, "ids"):
            options.setdefault("run_id", self.ids["runId"])
        child = subprocess.Popen([
            sys.executable, str(Path(__file__).with_name("pg_lifecycle_worker.py")),
            mode, self.case, json.dumps(options),
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.children.append(child)
        return child

    def finish(self, child):
        stdout, stderr = child.communicate(timeout=40)
        self.assertEqual(0, child.returncode, "AF04 child failed without safe evidence")
        self.assertFalse(stderr, "AF04 child stderr withheld")
        result = json.loads(stdout)
        self.assertNotIn("probe_error", result, result)
        return result

    def call(self, mode, **options):
        return self.finish(self.start(mode, **options))

    def wait_for(self, name):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if value(self.case, name):
                return
            time.sleep(.02)
        self.fail("bounded AF04 parent barrier timeout: " + name)

    def test_no_card_stop_owner_environment_and_dedup_are_cross_process(self):
        for wrong in ({"wrong_owner": True}, {"wrong_environment": True}):
            self.assertEqual("RUN_NOT_FOUND", self.call("stop", **wrong)["rejected"])
        first = self.call("stop")
        self.assertEqual("STOPPED", first["status"])
        self.assertFalse(first["inFlightCallsStillPending"])
        self.assertEqual(first, self.call("stop"))
        self.assertEqual("STOPPED", self.call("read")["status"])
        self.assertEqual([], self.call("read")["cards"])

    def test_long_action_stop_independent_commit_visibility_and_late_fact(self):
        self.call("graph_start")
        child = self.start("action", slow=True, action="confirm_route_choice")
        self.wait_for("action_entered")
        self.assertEqual(1, value(self.case, "commits_visible"))
        stopped = self.call("stop")
        self.assertEqual("STOPPED", stopped["status"])
        self.assertTrue(stopped["inFlightCallsStillPending"])
        self.assertIsNone(child.poll(), "stop must return while executor remains in flight")
        event(self.case, "action_release")
        self.assertEqual("STOPPED", self.finish(child)["status"])
        saved = self.call("read")
        self.assertEqual("STOPPED", saved["status"])
        attempt = saved["cards"][0]["attempts"][0]
        self.assertEqual("EXECUTED", attempt["status"])
        self.assertTrue(attempt["businessSuccess"])
        self.assertTrue(attempt["interactionCompleted"])
        self.assertEqual("COMPLETED", saved["cards"][0]["phase"])
        self.assertFalse(saved["cards"][0]["resumeConsumed"])
        self.assertEqual("NOT_REQUESTED", attempt["resumeStatus"])
        for name in ("native_resume", "finalizer", "successor"):
            self.assertEqual(0, value(self.case, name), name)
        self.assertFalse(any(f["kind"] == "FINALIZER" for f in saved["facts"]))
        facts = [f for f in saved["facts"] if f["kind"] == "ACTION"]
        self.assertEqual(1, len(facts))
        self.assertEqual("RETURNED", facts[0]["status"])
        self.assertIn("late-or-current-action", facts[0]["result"])
        self.assertEqual(1, value(self.case, "executor"))

    def test_stop_races_node_admission_and_no_success_or_new_dispatch_follows(self):
        node, stopper = self.start("node_race"), self.start("stop", race=True)
        self.wait_for("node_ready")
        self.wait_for("stop_ready")
        event(self.case, "race_release")
        self.assertEqual("STOPPED", self.finish(stopper)["status"])
        event(self.case, "node_release")
        self.assertEqual("STOPPED", self.finish(node)["status"])
        saved = self.call("read")
        self.assertEqual("STOPPED", saved["status"])
        self.assertLessEqual(value(self.case, "node_executor"), 1)
        facts = [f for f in saved["facts"] if f["kind"] == "NODE"]
        self.assertEqual(value(self.case, "node_executor"), len(facts))
        self.assertTrue(all(f["revision"] == 0 and f["status"] == "RETURNED" for f in facts))
        self.assertEqual("STOPPED", self.call("node_race")["status"])
        self.assertEqual(len(facts), value(self.case, "node_executor"))

    def test_stop_and_conditional_success_have_one_committed_winner(self):
        success, stopper = self.start("success"), self.start("stop", race=True)
        self.wait_for("success_ready")
        self.wait_for("stop_ready")
        event(self.case, "race_release")
        completed, stopped = self.finish(success), self.finish(stopper)
        saved = self.call("read")
        if saved["status"] == "STOPPED":
            self.assertEqual("RunStoppedControl", completed["observedControlSignal"])
            self.assertEqual("STOPPED", stopped["status"])
        else:
            self.assertEqual("SUCCEEDED", saved["status"])
            self.assertTrue(completed["succeeded"])
            self.assertEqual("RUN_ALREADY_TERMINAL", stopped["rejected"])

    def test_stopped_waiting_card_and_native_resume_reject_in_new_processes(self):
        self.assertEqual(1, self.call("graph_start")["interrupts"])
        self.call("stop")
        before = self.call("history_digest")
        self.assertEqual("STOPPED", self.call("action", action="confirm_route_choice")["status"])
        self.assertEqual("STOPPED", self.call("native_resume")["status"])
        self.assertEqual(0, value(self.case, "executor"))
        self.assertEqual(before, self.call("history_digest"))

    def test_fresh_restart_concurrent_control_never_reads_old_execution(self):
        self.call("graph_start")
        old_card = self.call("read")["cards"][0]["interactionId"]
        self.assertEqual("EXECUTED", self.call("action", action="save_choice")["status"])
        self.call("unknown")
        self.call("stop")
        self.call("corrupt_old")
        before = self.call("history_digest")
        options = {"source": self.ids["runId"], "old_thread": self.ids["threadId"]}
        first = self.start("restart", restart_slot="one", **options)
        second = self.start("restart", restart_slot="two", **options)
        self.wait_for("restart_ready_one")
        self.wait_for("restart_ready_two")
        event(self.case, "restart_release")
        fresh, duplicate = self.finish(first), self.finish(second)
        self.assertEqual(fresh["runId"], duplicate["runId"])
        self.assertNotEqual(self.ids["runId"], fresh["runId"])
        self.assertNotEqual(self.ids["threadId"], fresh["threadId"])
        self.assertEqual(1, value(self.case, "factory"))
        self.assertEqual("CONTROL_REQUEST_CONFLICT", self.call("restart", input="changed", **options)["rejected"])
        current = self.call("read", run_id=fresh["runId"])
        self.assertEqual(1, len(current["cards"]))
        self.assertNotEqual(old_card, current["cards"][0]["interactionId"])
        self.assertEqual("RETURNED", self.call("action", run_id=fresh["runId"],
                                            action="confirm_route_choice")["resumeStatus"])
        self.assertEqual("SUCCEEDED", self.call("read", run_id=fresh["runId"])["status"])
        self.assertEqual(2, value(self.case, "executor"))
        self.assertEqual(2, value(self.case, "skill"))
        self.assertEqual(before, self.call("history_digest"))

    def test_positive_sync_saver_action_resume_finalizer_across_processes(self):
        self.assertEqual(1, self.call("graph_start")["interrupts"])
        self.assertEqual("RUNNING", self.call("read")["status"])
        self.assertEqual("RETURNED", self.call("action", action="confirm_route_choice")["resumeStatus"])
        saved = self.call("read")
        self.assertEqual("SUCCEEDED", saved["status"])
        self.assertTrue(any(f["kind"] == "FINALIZER" and f["status"] == "RETURNED" for f in saved["facts"]))
        self.assertEqual(1, value(self.case, "executor"))
        self.assertEqual(1, value(self.case, "skill"))
        for name in ("native_resume", "finalizer", "successor"):
            self.assertEqual(1, value(self.case, name), name)

    def test_already_admitted_native_node_saves_late_result_after_stop(self):
        node = self.start("node_race")
        self.wait_for("node_ready")
        event(self.case, "race_release")
        self.wait_for("node_executor")
        self.assertEqual("STOPPED", self.call("stop")["status"])
        self.assertIsNone(node.poll())
        event(self.case, "node_release")
        self.assertEqual("STOPPED", self.finish(node)["status"])
        saved = self.call("read")
        facts = [f for f in saved["facts"] if f["kind"] == "NODE"]
        self.assertEqual(1, len(facts))
        self.assertEqual("RETURNED", facts[0]["status"])
        self.assertIn("node-result", facts[0]["result"])
        self.assertEqual("STOPPED", saved["status"])
