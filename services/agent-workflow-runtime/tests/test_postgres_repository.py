"""Offline protocol/serialization/fault tests; NOT PostgreSQL runtime evidence."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import json
import unittest

from agent_workflow_runtime import ActionRejected, ActionService
from agent_workflow_runtime.models import ActionRequest, Attempt
from agent_workflow_runtime.postgres import PostgresInteractionRepository, lock_key
from agent_workflow_runtime.serialization import decode, encode
from support import Configuration, Executor, Repository, interaction, request


class Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return [] if self.row is None else [self.row]


class Connection:
    def __init__(self):
        self.closed = self.broken = False
        self.held = False
        self.in_transaction = False
        self.fail_commit = False
        self.document = None
        self.committed = None
        self.calls = []
        self.transactions = 0

    def execute(self, statement, params=None):
        if self.closed or self.broken:
            raise RuntimeError("SYNTHETIC_SECRET_MUST_NOT_APPEAR")
        self.calls.append((statement, params, self.in_transaction))
        if "pg_advisory_lock(" in statement:
            self.held = True
        if "pg_advisory_unlock(" in statement:
            self.held = False
        if "AS held" in statement:
            return Cursor({"held": self.held})
        if "SELECT document" in statement:
            return Cursor(None if self.document is None else {"document": self.document})
        if "INSERT INTO runtime_interactions" in statement:
            self.document = params[-1].obj
        if "RETURNING control_request_id" in statement:
            return Cursor({"control_request_id": params[5]})
        return Cursor(None)

    @contextmanager
    def transaction(self):
        self.transactions += 1
        self.in_transaction = True
        try:
            yield
            if self.fail_commit:
                raise RuntimeError("SYNTHETIC_SECRET_MUST_NOT_APPEAR")
            self.committed = deepcopy(self.document)
        finally:
            self.in_transaction = False

    def close(self):
        self.closed = True
        self.held = False


class Factory:
    def __init__(self):
        self.connections = []
        self.kwargs = []

    def __call__(self, *args, **kwargs):
        connection = Connection()
        self.connections.append(connection)
        self.kwargs.append(kwargs)
        return connection


class SerializationTest(unittest.TestCase):
    def setUp(self):
        self.item = interaction(Configuration())
        self.attempt = Attempt(ActionRequest.from_mapping(request(self.item)), "EXECUTED",
                               True, True, '{"accepted":true}', "UNCONFIRMED")
        self.item = replace(self.item, attempts=(self.attempt,), phase="COMPLETED",
                            completion_request_id="request-1", resume_started=True)

    def test_round_trip_preserves_wait_outcomes_and_context(self):
        self.assertEqual(self.item, decode(encode(self.item)))
        self.assertEqual(interaction(Configuration()), decode(encode(interaction(Configuration()))))

    def test_display_snapshot_v2_and_legacy_v1_are_both_readable(self):
        empty = interaction(Configuration())
        displayed = replace(empty, display_json='{"cardId":"card"}')
        document = encode(displayed)
        self.assertEqual(2, document["schemaVersion"])
        self.assertEqual(displayed, decode(document))
        legacy = encode(empty)
        legacy["schemaVersion"] = 1
        del legacy["display_json"]
        self.assertEqual(empty, decode(legacy))

    def test_display_only_completion_round_trips_without_forging_action_completion(self):
        empty = interaction(Configuration())
        scope = empty.context.invocation_scope
        card = {
            "interactionId": empty.interaction_id,
            "applicationKey": empty.application_key,
            "applicationVersion": empty.application_version,
            "nodeId": scope.node_id,
            "state": "READ_ONLY",
            "actionEligibility": "NOT_OPERABLE",
            "actions": [],
        }
        displayed = replace(
            empty, display_json=json.dumps(card), phase="COMPLETED",
            node_waiting=False, resume_consumed=True,
        )
        self.assertEqual(displayed, decode(encode(displayed)))
        for change in (
            {"run_active": False},
            {"node_waiting": True},
            {"resume_started": True},
            {"display_json": json.dumps({**card, "actions": [{}]})},
            {"display_json": json.dumps({**card, "nodeId": '1004'})},
        ):
            with self.subTest(change=change), self.assertRaisesRegex(
                ActionRejected, "INVALID_STORED_RECORD",
            ):
                encode(replace(displayed, **change))

    def test_display_snapshot_must_be_a_json_object(self):
        empty = interaction(Configuration())
        for value in ("[]", "NaN", "{"):
            with self.subTest(value=value), self.assertRaisesRegex(
                ActionRejected, "INVALID_STORED_RECORD",
            ):
                encode(replace(empty, display_json=value))

    def test_closed_schema_and_scalar_types_reject(self):
        for change in (
            {"schemaVersion": True}, {"schemaVersion": 3}, {"extra": "field"},
            {"run_active": 1}, {"phase": "UNKNOWN"}, {"recorded_versions": []},
            {"completion_request_id": "unknown"},
        ):
            with self.subTest(change=change), self.assertRaisesRegex(ActionRejected, "INVALID_STORED_RECORD"):
                decode({**encode(self.item), **change})

    def test_corrupt_completion_cannot_forge_finalizer_admission(self):
        empty = interaction(Configuration())
        for change in ({"phase": "COMPLETED", "resume_started": True, "resume_consumed": True},
                       {"phase": "COMPLETED"}, {"resume_consumed": True},
                       {"resume_started": True}):
            document = {**encode(empty), **change}
            with self.subTest(change=change), self.assertRaisesRegex(ActionRejected, "INVALID_STORED_RECORD"):
                decode(document)
        for change in ({"completion_request_id": None}, {"resume_started": False, "resume_consumed": True}):
            with self.assertRaises(ActionRejected):
                decode({**encode(self.item), **change})
        document = encode(self.item)
        document["attempts"][0]["interaction_completed"] = False
        with self.assertRaises(ActionRejected):
            decode(document)
        with self.assertRaises(ActionRejected):
            encode(replace(empty, phase="COMPLETED", resume_started=True, resume_consumed=True))
        # The committed completion BEFORE dispatch reservation remains valid.
        pending_dispatch = replace(self.item, resume_started=False,
                                   attempts=(replace(self.attempt, resume_status="NOT_REQUESTED"),))
        self.assertEqual(pending_dispatch, decode(encode(pending_dispatch)))

    def test_malformed_attempt_binding_canonical_json_and_bool_reject(self):
        for field, value in (("business_success", 1), ("status", "RETRY"),
                             ("resume_status", "OK"), ("result_json", "NaN")):
            document = encode(self.item)
            document["attempts"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ActionRejected):
                decode(document)
        document = encode(self.item)
        document["attempts"][0]["request"]["run_id"] = "other-run"
        with self.assertRaises(ActionRejected):
            decode(document)
        document = encode(self.item)
        document["attempts"][0]["request"]["inputs_json"] = '{"selection": "left"}'
        with self.assertRaises(ActionRejected):
            decode(document)


class ConnectionLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.factory = Factory()
        self.repo = PostgresInteractionRepository("unused-offline", connection_factory=self.factory)
        self.item = interaction(Configuration())
        self.owner = self.item.context.trusted_context

    def test_scopes_dedicated_commits_short_and_owner_filtered(self):
        with self.repo.scope(self.owner, self.item.key[0]):
            connection = self.factory.connections[-1]
            self.repo.save(self.item)
            self.assertEqual(encode(self.item), connection.committed)
            self.assertFalse(connection.in_transaction)
            self.assertEqual(self.item, self.repo.get(self.item.key, self.owner))
            self.assertEqual(1, connection.transactions)
            reads = [(sql, params) for sql, params, _ in connection.calls if "SELECT document" in sql]
            self.assertTrue(all(params[:2] == (self.owner.user_id, self.owner.environment) for _, params in reads))
            with self.assertRaisesRegex(ActionRejected, "NESTED_REPOSITORY_SCOPE"):
                with self.repo.scope(self.owner, self.item.key[0]):
                    pass
        self.assertTrue(connection.closed)
        self.assertTrue(any("pg_advisory_unlock" in sql for sql, _, _ in connection.calls))
        self.assertTrue(self.factory.kwargs[0]["autocommit"])

    def test_loss_never_reconnects_or_writes_and_closes(self):
        with self.assertRaisesRegex(ActionRejected, "LOCK_CONNECTION_LOST"):
            with self.repo.scope(self.owner, self.item.key[0]):
                connection = self.factory.connections[-1]
                connection.broken = True
                self.repo.save(self.item)
        self.assertEqual(1, len(self.factory.connections))
        self.assertTrue(connection.closed)
        self.assertEqual(0, connection.transactions)

    def test_lost_continuation_blocks_new_admission_connection(self):
        with self.assertRaisesRegex(ActionRejected, "LOCK_CONNECTION_LOST"):
            with self.repo.continuation_scope(self.owner, self.item.key[0]):
                self.factory.connections[-1].held = False
                with self.repo.scope(self.owner, self.item.key[0]):
                    self.fail("must not enter")
        self.assertEqual(1, len(self.factory.connections))

    def test_uncertain_commit_poisoned_scope_cannot_retry(self):
        with self.assertRaisesRegex(ActionRejected, "LOCK_CONNECTION_LOST"):
            with self.repo.scope(self.owner, self.item.key[0]):
                connection = self.factory.connections[-1]
                connection.fail_commit = True
                with self.assertRaisesRegex(ActionRejected, "REPOSITORY_COMMIT_UNCONFIRMED") as raised:
                    self.repo.save(self.item)
                self.assertNotIn("SYNTHETIC_SECRET", str(raised.exception))
                self.repo.get(self.item.key, self.owner)
        self.assertEqual(1, len(self.factory.connections))
        self.assertTrue(connection.closed)

    def test_no_unscoped_reads_writes_or_implicit_setup(self):
        with self.assertRaisesRegex(ActionRejected, "REPOSITORY_SCOPE_REQUIRED"):
            self.repo.get(self.item.key, self.owner)
        with self.assertRaises(ActionRejected):
            self.repo.save(self.item)
        self.assertEqual([], self.factory.connections)

    def test_locks_are_stable_and_namespaced(self):
        self.assertEqual(lock_key(self.owner, "r", "admission"), lock_key(self.owner, "r", "admission"))
        self.assertNotEqual(lock_key(self.owner, "r", "admission"), lock_key(self.owner, "r", "continuation"))


class RunGateTest(unittest.TestCase):
    def setUp(self):
        self.repo, self.config, self.executor = Repository(), Configuration(), Executor()
        self.service = ActionService(self.repo, self.config, self.executor, lambda item, rid: None)
        self.first, self.second = interaction(self.config, "first"), interaction(self.config, "second")
        self.owner = self.first.context.trusted_context
        self.service.register(self.first)
        self.service.register(self.second)

    def test_pending_or_uncertain_run_rejects_without_reservation(self):
        for status, delivery in (("EXECUTING", "NOT_REQUESTED"),
                                 ("EXECUTION_UNCONFIRMED", "NOT_REQUESTED"),
                                 ("EXECUTED", "DISPATCHING"), ("EXECUTED", "UNCONFIRMED")):
            attempt = Attempt(ActionRequest.from_mapping(request(self.first)), status,
                              resume_status=delivery)
            self.repo.save(replace(self.first, attempts=(attempt,)))
            with self.subTest(status=status, delivery=delivery):
                repeated = self.service.submit(request(self.first), self.owner)
                self.assertEqual("EXECUTION_UNCONFIRMED" if status == "EXECUTING" else status,
                                 repeated.status)
                with self.assertRaisesRegex(ActionRejected, "RUN_OPERATION_PENDING_OR_UNCONFIRMED"):
                    self.service.submit(request(self.second), self.owner)
                self.assertEqual((), self.repo.get(self.second.key).attempts)
                self.assertEqual([], self.executor.calls)

    def test_normal_same_run_cards_continue_after_returned(self):
        self.service.submit(request(self.first), self.owner)
        self.service.submit(request(self.second), self.owner)
        self.assertEqual(2, len(self.executor.calls))

    def test_healthy_inflight_gate_then_completion_and_later_card(self):
        def continuation(item, rid):
            with self.assertRaisesRegex(ActionRejected, "RUN_OPERATION_PENDING_OR_UNCONFIRMED"):
                self.service.submit(request(self.second, "premature"), self.owner)
            self.assertEqual((), self.repo.get(self.second.key).attempts)
            self.service.completion(item.key, {"controlRequestId": rid}, self.owner)
        self.service.continuation = continuation
        self.service.submit(request(self.first), self.owner)
        self.assertTrue(self.repo.get(self.first.key).resume_consumed)
        self.service.continuation = lambda item, rid: None
        self.service.submit(request(self.second), self.owner)
        self.assertEqual(2, len(self.executor.calls))


class PgGraphHarnessOfflineTest(unittest.TestCase):
    def test_pg_graph_shape_reassembles_with_native_checkpoint_in_memory_only(self):
        from collections import Counter
        from unittest.mock import patch
        from langgraph.checkpoint.memory import MemorySaver
        from pg_process_worker import bound_item, graph_for
        counts = Counter()
        repo, config, executor = Repository(), Configuration(), Executor()
        service = ActionService(repo, config, executor, None)
        item = bound_item(config, "offline-harness")
        saver = MemorySaver()
        graph_config = {"configurable": {"thread_id": "offline-harness"}}
        with patch("pg_process_worker.event", side_effect=lambda run, name, value=1: counts.update({name: value})):
            graph = graph_for(saver, repo, config, service, "offline-harness")
            waiting = graph.invoke({"messages": [{"role": "user", "content": "Probe"}], "trace": []},
                                   graph_config, context=item.context)
            self.assertEqual(["B1", "B2"], waiting["trace"])
            self.assertEqual(1, len(waiting["__interrupt__"]))
            rebuilt = graph_for(saver, repo, config, service, "offline-harness", resume=True)
            saved = next(iter(repo.items.values()))
            service.submit(request(saved), saved.context.trusted_context)
            snapshot = rebuilt.get_state(graph_config)
            self.assertFalse(snapshot.next)
            self.assertEqual("JOIN", snapshot.values["trace"][-1])
            self.assertEqual({"skill": 1, "B1": 1, "B2": 1, "A": 1}, dict(counts))
            self.assertEqual(1, len(executor.calls))
