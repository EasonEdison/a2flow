"""Opt-in actual PostgreSQL + independent OS process acceptance tests.

Offline discovery SKIPS these tests. Only an explicitly released PG window may
set A2FLOW_RUNTIME03_SOCKET / A2FLOW_RUNTIME03_PASSWORD_FILE.
"""

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
from pg_process_worker import connection, conninfo, event, value


@unittest.skipUnless(os.environ.get("A2FLOW_RUNTIME03_SOCKET"), "requires separately authorized PG window")
class PostgresProcessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PostgresInteractionRepository(conninfo()).setup()
        with connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS runtime_probe_events (
                run_id TEXT NOT NULL, name TEXT NOT NULL, value BIGINT NOT NULL,
                PRIMARY KEY (run_id,name))""")
        with PostgresSaver.from_conn_string(conninfo()) as saver:
            saver.setup()
        cls.peak = 0
        cls.observer_error = None
        cls.stop = Event()

        def observe():
            try:
                with connection() as conn:
                    while not cls.stop.wait(.005):
                        row = conn.execute("""SELECT count(*) AS count FROM pg_stat_activity
                            WHERE usename=current_user AND datname=current_database()""").fetchone()
                        cls.peak = max(cls.peak, row["count"])
            except Exception as error:
                cls.observer_error = type(error).__name__
        cls.observer = Thread(target=observe)
        cls.observer.start()

    @classmethod
    def tearDownClass(cls):
        cls.stop.set()
        cls.observer.join(5)
        if cls.observer.is_alive() or cls.observer_error:
            raise AssertionError("connection observer failed")
        if cls.peak > 8:
            raise AssertionError("role connection budget exceeded")
        print(json.dumps({"observedRuntimeConnectionPeak": cls.peak, "sampleIntervalMs": 5,
                          "includesObserver": True, "claim": "observed peak, not exact transient maximum"}))

    def setUp(self):
        self.run_id = "runtime03-" + uuid4().hex
        self.children = []

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.communicate(timeout=5)

    def start(self, mode, **options):
        worker = str(Path(__file__).with_name("pg_process_worker.py"))
        child = subprocess.Popen([sys.executable, worker, mode, self.run_id, json.dumps(options)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.children.append(child)
        return child

    def finish(self, child):
        stdout, stderr = child.communicate(timeout=35)
        self.assertEqual(0, child.returncode, "worker failed without safe evidence")
        self.assertFalse(stderr, "worker emitted unexpected stderr (not replayed)")
        result = json.loads(stdout)
        self.assertNotIn("probe_error", result, result)
        return result

    def call(self, mode, **options):
        return self.finish(self.start(mode, **options))

    def wait_for(self, name):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if value(self.run_id, name):
                return
            time.sleep(.02)
        self.fail("bounded probe barrier timeout: " + name)

    def terminate_lock(self):
        pid = value(self.run_id, "lock_pid")
        self.assertGreater(pid, 0)
        with connection() as conn:
            row = conn.execute("""SELECT pid FROM pg_stat_activity
                WHERE pid=%s AND usename=current_user AND datname=current_database()
                  AND application_name='a2flow-runtime03'""", (pid,)).fetchone()
            self.assertIsNotNone(row, "target must be exact owned runtime lock backend")
            self.assertTrue(conn.execute("SELECT pg_terminate_backend(%s) AS stopped", (pid,)).fetchone()["stopped"])

    def test_new_process_reads_waiting_and_completed(self):
        self.call("register")
        self.assertTrue(all(i["phase"] == "WAITING" for i in self.call("read")["items"]))
        result = self.call("submit", action="confirm_route_choice")
        self.assertEqual("RETURNED", result["resume_status"])
        items = self.call("read")["items"]
        first = next(i for i in items if i["interaction_id"] == "first")
        self.assertEqual("COMPLETED", first["phase"])
        self.assertTrue(first["resume_consumed"])
        self.assertEqual(1, value(self.run_id, "executor"))

    def test_two_processes_same_request_dispatch_once_and_conflict_persists(self):
        self.call("register")
        first, second = self.start("submit"), self.start("submit")
        self.assertEqual("EXECUTED", self.finish(first)["status"])
        self.assertEqual("EXECUTED", self.finish(second)["status"])
        self.assertEqual(1, value(self.run_id, "executor"))
        self.assertEqual("CONTROL_REQUEST_CONFLICT", self.call("submit", selection="right")["rejected"])

    def test_two_cards_concurrent_updates_survive(self):
        self.call("register")
        first, second = self.start("submit"), self.start("submit", card="second")
        self.assertEqual("EXECUTED", self.finish(first)["status"])
        self.assertEqual("EXECUTED", self.finish(second)["status"])
        self.assertEqual(2, value(self.run_id, "executor"))
        self.assertEqual([1, 1], [len(i["attempts"]) for i in self.call("read")["items"]])

    def test_owner_environment_versions_stopped_reject_before_executor(self):
        self.call("register")
        for options in ({"owner": True}, {"environment": True}, {"stale": 1},
                        {"stale": 2}, {"stale": 3}, {"stopped": True}):
            self.assertIn("rejected", self.call("submit", **options))
        self.assertEqual(0, value(self.run_id, "executor"))

    def test_executor_uncertainty_persists_and_blocks_other_card_without_pollution(self):
        self.call("register")
        self.assertEqual("EXECUTION_UNCONFIRMED", self.call("submit", fault="executor_failure")["status"])
        self.assertEqual("EXECUTION_UNCONFIRMED", self.call("submit")["status"])
        self.assertEqual("RUN_OPERATION_PENDING_OR_UNCONFIRMED", self.call("submit", card="second")["rejected"])
        second = next(i for i in self.call("read")["items"] if i["interaction_id"] == "second")
        self.assertEqual([], second["attempts"])
        self.assertEqual(1, value(self.run_id, "executor"))

    def test_crashed_process_executing_is_not_redispatched(self):
        self.call("register")
        child = self.start("submit", fault="execution_loss")
        self.wait_for("entered")
        child.kill()  # Only the exact subprocess this test created.
        child.communicate(timeout=5)
        self.assertEqual("EXECUTION_UNCONFIRMED", self.call("submit")["status"])
        self.assertEqual("RUN_OPERATION_PENDING_OR_UNCONFIRMED", self.call("submit", card="second")["rejected"])
        self.assertEqual(1, value(self.run_id, "executor"))

    def test_admission_connection_loss_fails_closed_after_inflight_executor(self):
        self.call("register")
        child = self.start("submit", fault="execution_loss")
        self.wait_for("entered")
        self.terminate_lock()
        self.assertEqual("EXECUTION_UNCONFIRMED", self.call("submit")["status"])
        event(self.run_id, "release")
        self.assertEqual("LOCK_CONNECTION_LOST", self.finish(child)["rejected"])
        first = next(i for i in self.call("read")["items"] if i["interaction_id"] == "first")
        self.assertEqual("EXECUTING", first["attempts"][0]["status"])
        self.assertEqual(1, value(self.run_id, "executor"))

    def test_real_sync_saver_skill_interaction_action_resume_without_b_replay(self):
        self.assertEqual({"trace": ["B1", "B2"], "interrupts": 1}, self.call("graph_start"))
        self.assertEqual(1, value(self.run_id, "skill"))
        resumed = self.call("graph_resume")
        self.assertFalse(resumed["next"])
        self.assertEqual("JOIN", resumed["trace"][-1])
        for name in ("skill", "B1", "B2", "A", "executor"):
            self.assertEqual(1, value(self.run_id, name), name)

    def test_inflight_graph_can_finish_after_lock_loss_but_no_returned_or_redispatch(self):
        self.call("graph_start")
        child = self.start("graph_loss")
        self.wait_for("graph_entered")
        self.terminate_lock()
        records = self.call("read")["items"]
        card = records[0]["interaction_id"]
        repeated = self.call("submit", card=card, action="confirm_route_choice")
        self.assertEqual("DISPATCHING", repeated["resume_status"])
        # Registration is allowed for a trusted native Tool; new Action is not.
        self.call("register")
        self.assertEqual("RUN_OPERATION_PENDING_OR_UNCONFIRMED", self.call("submit", card="second")["rejected"])
        event(self.run_id, "release")
        self.assertEqual("LOCK_CONNECTION_LOST", self.finish(child)["rejected"])
        graph = self.call("graph_read")
        self.assertFalse(graph["next"])
        self.assertEqual("JOIN", graph["trace"][-1])
        record = next(i for i in self.call("read")["items"] if i["interaction_id"] == card)
        self.assertEqual("DISPATCHING", record["attempts"][0]["resume_status"])
        self.assertTrue(record["resume_consumed"])
        for name in ("skill", "B1", "B2", "A", "executor"):
            self.assertEqual(1, value(self.run_id, name), name)
