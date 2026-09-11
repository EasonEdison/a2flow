"""Scripted DB protocol gates, explicitly not a live PostgreSQL verification."""

from contextlib import contextmanager
import unittest

from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.postgres_progress import PostgresProgress, cursor, execution_id, page_limit
from agent_workflow_runtime.progress_writer import encoded
from support import context


SEGMENT = "a" * 32


def record(text="中"):
    return {"kind": "TEXT_DELTA", "observedAt": "2026-09-09T00:00:00+00:00",
            "payload": {"modelCallId": "m", "text": text}}


class Result:
    def __init__(self, value):
        self.value = value
    def fetchone(self):
        return self.value
    def fetchall(self):
        return self.value


class Connection:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []
        self.closed = self.committed = self.rolled_back = False

    @contextmanager
    def transaction(self):
        try:
            yield
        except BaseException:
            self.rolled_back = True
            raise
        else:
            self.committed = True

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql.startswith("SET TRANSACTION"):
            return Result(None)
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return Result(answer)

    def close(self):
        self.closed = True


class PostgresProgressTest(unittest.TestCase):
    def repo(self, answers):
        connection = Connection(answers)
        self.connection = connection
        self.options = {}
        def connect(*args, **kwargs):
            self.options.update(kwargs)
            return connection
        return PostgresProgress("synthetic-unused", connection_factory=connect)

    def binding(self):
        return {"userId": "test-user", "environment": "PRT", "runId": "run-test",
                "nodeId": "node-test", "executionId": SEGMENT, "nodeOperationId": "node-operation"}

    def head(self, last=0, **changes):
        return {"last_seq": last, "catalog_seq": 1, "sealed": False,
                "incomplete": False, "observation_outcome": None, **changes}

    def history(self, repo, **kwargs):
        return repo.history(context().trusted_context, "run-test", "node-test", SEGMENT, **kwargs)

    def test_owner_scoped_read_transaction_closed_before_export(self):
        repo = self.repo([{"run_id": "run-test"}, self.head(1), [{"seq": 1, "document": record()}]])
        result = self.history(repo)
        self.assertEqual(SEGMENT + ":1", result["nextCursor"])
        self.assertTrue(self.connection.closed and self.connection.committed)
        self.assertIn("READ ONLY", self.connection.calls[0][0])
        for _, params in self.connection.calls[1:]:
            self.assertEqual(("test-user", "PRT", "run-test"), params[:3])

    def test_future_and_cross_segment_cursors_fail_closed(self):
        repo = self.repo([{"run_id": "run-test"}, self.head(1)])
        with self.assertRaisesRegex(ActionRejected, "FUTURE_PROGRESS_CURSOR"):
            self.history(repo, after=SEGMENT + ":2")
        self.assertTrue(self.connection.closed)
        with self.assertRaisesRegex(ActionRejected, "INVALID_PROGRESS_CURSOR"):
            cursor("b"*32 + ":1", SEGMENT)
        for value in (True, 0, 101, "10"):
            with self.assertRaises(ActionRejected):
                page_limit(value)
        for value in ("uuid", "A"*32, None):
            with self.assertRaises(ActionRejected):
                execution_id(value)

    def test_byte_limited_history_keeps_records_whole_and_cursor_exact(self):
        rows = [{"seq": i, "document": record("中" * 5000)} for i in range(1, 101)]
        repo = self.repo([{"run_id": "run-test"}, self.head(100), rows])
        result = self.history(repo)
        self.assertLess(len(encoded(result)), 256 * 1024)
        self.assertTrue(result["hasMore"])
        self.assertGreater(len(result["records"]), 0)
        self.assertLess(len(result["records"]), 100)
        self.assertEqual(SEGMENT + ":" + str(result["records"][-1]["seq"]), result["nextCursor"])
        self.assertEqual("中" * 5000, result["records"][-1]["payload"]["text"])

    def test_invalid_or_missing_committed_record_is_not_silent_poll_loop(self):
        for rows in ([], [{"seq": 2, "document": record()}],
                     [{"seq": 1, "document": {**record(), "raw": "PRIVATE"}}]):
            with self.subTest(rows=rows):
                repo = self.repo([{"run_id": "run-test"}, self.head(1), rows])
                with self.assertRaisesRegex(ActionRejected, "PROGRESS_INTEGRITY_ERROR"):
                    self.history(repo)

    def test_atomic_batch_uses_head_lock_and_single_insert(self):
        repo = self.repo([self.head(4), [], None, None])
        repo.append(self.binding(), "batch", [record("one"), record("two")], seal="RETURNED")
        calls = self.connection.calls
        self.assertIn("FOR UPDATE", calls[0][0])
        inserts = [(sql, params) for sql, params in calls if "INSERT INTO runtime_display_records" in sql]
        self.assertEqual(1, len(inserts))
        self.assertEqual((5, 6), (inserts[0][1][5], inserts[0][1][15]))
        self.assertEqual(6, calls[-1][1][0])
        self.assertTrue(self.connection.committed and self.connection.closed)
        self.assertIn("statement_timeout=750", self.options["options"])
        self.assertFalse(any("runtime_runs" in sql for sql, _ in calls))

    def test_batch_insert_failure_rolls_back_and_does_not_advance_head(self):
        repo = self.repo([self.head(4), [], RuntimeError("synthetic insert failure")])
        with self.assertRaises(RuntimeError):
            repo.append(self.binding(), "batch", [record()])
        self.assertTrue(self.connection.rolled_back and self.connection.closed)
        self.assertFalse(any("UPDATE runtime_capture_heads SET last_seq=%s" in sql
                             for sql, _ in self.connection.calls))

    def test_private_catalog_head_orders_creation_without_business_row_lock(self):
        repo = self.repo([None, None, self.head(), None, {"last_seq": 7}, None,
                          self.head(), [], None, None])
        repo.append(self.binding(), "batch", [record()])
        calls = self.connection.calls
        self.assertTrue(any("last_seq=last_seq+1" in sql for sql, _ in calls))
        private_locks = [params for sql, params in calls if "FOR UPDATE" in sql and params[-2:] == ("", "")]
        self.assertEqual(1, len(private_locks))
        self.assertFalse(any("runtime_runs" in sql for sql, _ in calls))
        self.assertTrue(self.connection.committed)

    def test_repeated_batch_and_empty_seal_are_idempotent_and_conflicts_reject(self):
        from hashlib import sha256
        for records in ([], [record()]):
            digest = sha256(encoded({"records": records, "seal": "RETURNED", "incomplete": False})).hexdigest()
            head = self.head(len(records), sealed=True, last_batch_id="batch", last_batch_digest=digest)
            repo = self.repo([head])
            repo.append(self.binding(), "batch", records, seal="RETURNED")
            self.assertEqual(1, len(self.connection.calls))
            self.assertTrue(self.connection.committed)
            repo = self.repo([head])
            with self.assertRaisesRegex(ActionRejected, "PROGRESS_BATCH_IDENTITY_CONFLICT"):
                repo.append(self.binding(), "batch", records, seal="UNCONFIRMED")
            self.assertTrue(self.connection.rolled_back)
