"""SQL shape/transaction tests with a recording connection; not live PG proof."""

from contextlib import contextmanager
import unittest

from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.postgres_projection import PostgresProjection
from agent_workflow_runtime.projections import snapshot
from support import context


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, batches):
        self.batches = list(batches)
        self.statements = []
        self.closed = False
        self.in_transaction = False

    @contextmanager
    def transaction(self):
        self.in_transaction = True
        try:
            yield
        finally:
            self.in_transaction = False

    def execute(self, sql, params=None):
        if not self.in_transaction:
            raise AssertionError("read outside transaction")
        self.statements.append((sql, params))
        return Cursor([] if sql.startswith("SET TRANSACTION") else self.batches.pop(0))

    def close(self):
        self.closed = True


class ProjectionTest(unittest.TestCase):
    def adapter(self, batches):
        connection = Connection(batches)
        calls = []
        def connect(conninfo, **kwargs):
            calls.append(kwargs)
            return connection
        return PostgresProjection("synthetic-not-a-DSN", connection_factory=connect), connection, calls

    def test_single_readonly_repeatable_snapshot_safe_paths_owner_and_limits(self):
        adapter, connection, calls = self.adapter([
            [{"run_id": "run-test", "status": "RUNNING", "revision": 0,
              "initial_control_id": "start", "initial_control_status": "DISPATCHING"}],
            [{"node_id": "node-test", "kind": "NODE", "status": "INTERRUPTED", "count": 1}], [],
        ])
        result = adapter.run(context().trusted_context, "run-test")
        self.assertEqual("COMMITTED_SNAPSHOT", result["consistency"])
        self.assertEqual("NOT_INSPECTED", result["nativeExecution"]["waiting"])
        self.assertEqual("NOT_ESTABLISHED", result["nativeExecution"]["liveness"])
        self.assertEqual("INTERRUPTED", result["operationHistory"]["items"][0]["recordedStatus"])
        self.assertTrue(connection.closed)
        self.assertEqual(4, len(connection.statements))
        self.assertEqual("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY", connection.statements[0][0])
        sql = " ".join(text for text, _ in connection.statements).lower()
        for forbidden in ("for update", "pg_advisory", "result_json", "checkpoint", "select document ", "initial_inputs_json"):
            self.assertNotIn(forbidden, sql)
        for statement, params in connection.statements[1:]:
            self.assertEqual(("test-user", "PRT", "run-test"), params[:3])
        self.assertEqual(101, connection.statements[-1][1][-1])
        self.assertEqual(101, connection.statements[-2][1][-1])
        self.assertEqual(2, calls[0]["connect_timeout"])
        self.assertIn("statement_timeout=1500", calls[0]["options"])

    def test_control_is_one_owner_filtered_read_no_lock_or_factory(self):
        adapter, connection, _ = self.adapter([[{"run_id": "run-test", "status": "DISPATCHING"}]])
        value = adapter.control(context().trusted_context, "start")
        self.assertEqual("DISPATCHING", value["delivery"])
        self.assertEqual(2, len(connection.statements))
        self.assertEqual(("test-user", "PRT", "start"), connection.statements[1][1])
        self.assertNotIn("payload_json", connection.statements[1][0])
        self.assertTrue(connection.closed)

    def test_missing_owner_and_unknown_read_no_existence_leak(self):
        adapter, connection, calls = self.adapter([])
        with self.assertRaisesRegex(ActionRejected, "TRUSTED_CONTEXT_REQUIRED"):
            adapter.run(None, "missing")
        self.assertEqual([], calls)
        adapter, connection, _ = self.adapter([[]])
        with self.assertRaisesRegex(ActionRejected, "RUN_NOT_FOUND"):
            adapter.run(context().trusted_context, "missing")
        self.assertEqual(2, len(connection.statements))
        self.assertTrue(connection.closed)

    def test_narrow_restart_does_not_select_old_context(self):
        adapter, connection, _ = self.adapter([[{
            "run_id": "run-test", "status": "STOPPED", "definition_key": "sample.definition",
        }]])
        self.assertEqual({"runId": "run-test", "definitionKey": "sample.definition"},
                         adapter.restart_identity(context().trusted_context, "run-test"))
        sql = connection.statements[1][0]
        for forbidden in ("inputs", "versions", "thread_id", "result", "checkpoint"):
            self.assertNotIn(forbidden, sql)

    def test_failed_query_redacts_and_closes_without_retry(self):
        adapter, connection, calls = self.adapter([])
        with self.assertRaisesRegex(ActionRejected, "^PROJECTION_UNAVAILABLE$"):
            adapter.run(context().trusted_context, "run-test")
        self.assertTrue(connection.closed)
        self.assertEqual(1, len(calls))

    def test_bounded_history_is_explicit_and_stopped_cards_are_not_operable(self):
        operations = [{"node_id": "node-"+str(i), "kind": "NODE", "status": "INTERRUPTED", "count": 1}
                      for i in range(101)]
        cards = [{"node_id": "node-test", "interaction_id": "card-"+str(i), "phase": "WAITING",
                  "run_active": True, "node_waiting": True, "attempt_count": 0} for i in range(101)]
        result = snapshot({"run_id": "run-test", "status": "STOPPED", "revision": 1,
                           "initial_control_id": "start", "initial_control_status": "RETURNED"}, operations, cards)
        self.assertTrue(result["operationHistory"]["truncated"])
        self.assertTrue(result["interactions"]["truncated"])
        self.assertEqual(100, len(result["interactions"]["items"]))
        self.assertTrue(all(c["actionEligibility"] == "NOT_OPERABLE" for c in result["interactions"]["items"]))
        self.assertEqual("NOT_INSPECTED", result["nativeExecution"]["waiting"])
