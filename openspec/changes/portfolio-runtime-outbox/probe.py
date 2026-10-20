"""Isolated PostgreSQL probe; the reference transport injects failures, never calls business.

Run with A2FLOW_PROBE_DATABASE_URL in the environment and candidate packages on
PYTHONPATH. Creates and drops only its own unique schema. No model or external
sender is invoked. The PostgreSQL role needs CREATE on the selected database.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
from typing import TypedDict
import re
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo, conninfo_to_dict
from sqlalchemy import text
from psycopg.types.json import Jsonb
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from agent_workflow_runtime.events import DomainEvent, RUN_FINISHED, NODE_WAITING, run_event_id
from agent_workflow_runtime.lifecycle import RunLifecycle
from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.postgres_lifecycle import PostgresRunRepository
from agent_workflow_runtime.postgres import DDL as INTERACTION_DDL
from agent_workflow_runtime.native_control import RunGraphBinding
from agent_workflow_runtime.waiting_notifications import (
    WaitingNotificationRecovery, publish_waiting_snapshot,
)
from a2flow_scheduler.contracts import NotificationCommand
from a2flow_scheduler.delivery import consume_one, reconcile_notifications
from a2flow_scheduler.notification_delivery import persist_notification
from a2flow_scheduler.outbox import PostgresOutbox
from a2flow_scheduler.persistence import scheduler_engine
from a2flow_scheduler.streams import StreamChannel, StreamDelivery
from deploy.attended.runtime_events import SchedulerEventSink
from skillweave_contracts import TrustedContext

ROOT = Path(__file__).resolve().parents[3]
OWNER = TrustedContext(user_id=1008, environment="PRT")


class ReferenceTransport:
    """Deterministic duplicate/ack-error reference delivery; no business payloads."""
    def __init__(self, message_id: str, fail_ack: bool = False):
        self.message_id, self.fail_ack = message_id, fail_ack
        self.used = False
        self.acks = 0

    def receive(self, channel):
        if self.used:
            return None
        self.used = True
        return StreamDelivery(channel, "probe-entry", self.message_id)

    def acknowledge(self, delivery):
        if self.fail_ack:
            raise RuntimeError("PROBE_ACK_FAILURE")
        self.acks += 1


class NoBusinessIngress:
    def start(self, command):
        raise AssertionError("Business execution is forbidden in this probe")
    resume = start
    reconcile = start


def runtime(dsn: str, schema: str, writer=None):
    def connect(conninfo, **kwargs):
        kwargs["options"] = kwargs.get("options", "") + " -c search_path=" + schema
        return psycopg.connect(conninfo, **kwargs)
    repository = PostgresRunRepository(
        dsn, connection_factory=connect,
        transactional_event_writer=writer or SchedulerEventSink().publish,
    )
    return repository, RunLifecycle(repository, event_sink=repository,
                                    waiting_validator=repository.waiting_interaction)


def allocate(lifecycle: RunLifecycle, control: str):
    return lifecycle.allocate(OWNER, control, "probe.workflow", {}, "first",
                              lambda *_: (("WORKFLOW:probe", "v1"),))[0]


def count(dsn: str, statement: str, params=()):
    with psycopg.connect(dsn) as connection:
        return connection.execute(statement, params).fetchone()[0]


def consume(dsn: str, message_id: str, fail_ack: bool = False):
    outbox = PostgresOutbox(scheduler_engine(dsn))
    transport = ReferenceTransport(message_id, fail_ack)
    try:
        consume_one(outbox, transport, StreamChannel.NOTIFICATIONS, NoBusinessIngress())
    finally:
        outbox.engine.dispose()


def child():
    # A fresh process owns new engines, connections and in-memory state.
    dsn = os.environ["A2FLOW_PROBE_ISOLATED_DSN"]
    options = conninfo_to_dict(dsn).get("options", "")
    if not re.fullmatch(r"-c search_path=portfolio_outbox_probe_[0-9a-f]{32}", options):
        raise ValueError("ISOLATED_PROBE_SCHEMA_REQUIRED")
    consume(dsn, sys.argv[2])
    print("fresh_process_consumed_reference")


def main():
    base = os.environ["A2FLOW_PROBE_DATABASE_URL"]
    schema = "portfolio_outbox_probe_" + uuid4().hex
    assert re.fullmatch(r"portfolio_outbox_probe_[0-9a-f]{32}", schema)
    dsn = make_conninfo(base, options="-c search_path=" + schema)
    results = {}
    outbox = None
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        repository, lifecycle = runtime(base, schema)
        repository.setup()
        with psycopg.connect(dsn) as connection:
            connection.execute((ROOT / "services/scheduler-mq/src/a2flow_scheduler/schema.sql").read_text())
            for statement in INTERACTION_DDL:
                connection.execute(statement)
            connection.execute("""CREATE TABLE notifications (
                id bigserial PRIMARY KEY, user_id bigint NOT NULL, kind text NOT NULL,
                title text NOT NULL, body text NOT NULL, ref_type text, ref_id text,
                read boolean NOT NULL DEFAULT false, idempotency_key text UNIQUE NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now())""")
            connection.execute("CREATE TABLE probe_commit_rejections (run_id text PRIMARY KEY)")
            connection.execute("""CREATE FUNCTION reject_selected_commit() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                    IF EXISTS (SELECT 1 FROM probe_commit_rejections WHERE run_id=NEW.run_id)
                    THEN RAISE EXCEPTION 'PROBE_DEFERRED_COMMIT_FAILURE'; END IF;
                    RETURN NEW;
                END $$""")
            connection.execute("""CREATE CONSTRAINT TRIGGER probe_deferred_rejection
                AFTER UPDATE ON runtime_runs DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW EXECUTE FUNCTION reject_selected_commit()""")
        outbox = PostgresOutbox(scheduler_engine(dsn))
        run = allocate(lifecycle, "successful-start")
        lifecycle.succeed(OWNER, run.run_id)
        event = DomainEvent.create(RUN_FINISHED, run.run_id, run.definition_key, OWNER.user_id, OWNER.environment,
                                   event_id=run_event_id(RUN_FINISHED, run.run_id, OWNER.user_id, OWNER.environment))
        message_id = "event:" + str(event.event_id)
        assert lifecycle.read(OWNER, run.run_id).status == "SUCCEEDED"
        assert count(dsn, "SELECT count(*) FROM scheduler_outbox WHERE message_id=%s", (message_id,)) == 1
        repository.publish(event)  # Same logical event remains one durable row.
        assert count(dsn, "SELECT count(*) FROM scheduler_outbox WHERE message_id=%s", (message_id,)) == 1
        results["atomic_commit_stable_identity"] = "PASS"
        wait1 = DomainEvent.create(NODE_WAITING, run.run_id, run.definition_key, OWNER.user_id, OWNER.environment)
        wait2 = DomainEvent.create(NODE_WAITING, run.run_id, run.definition_key, OWNER.user_id, OWNER.environment)
        assert wait1.event_id != wait2.event_id
        results["different_waiting_events_not_merged"] = "PASS"

        for transition in ("succeed", "stop", "fail"):
            rejected = allocate(lifecycle, "reject-" + transition)
            with psycopg.connect(dsn) as connection:
                connection.execute("INSERT INTO probe_commit_rejections VALUES (%s)", (rejected.run_id,))
            try:
                if transition == "stop":
                    lifecycle.stop(OWNER, rejected.run_id, "reject-stop-control")
                elif transition == "fail":
                    lifecycle.fail(OWNER, rejected.run_id, reason="ProbeFailure")
                else:
                    lifecycle.succeed(OWNER, rejected.run_id)
                raise AssertionError("Commit-time failure was not raised")
            except ActionRejected as error:
                assert error.code == "RUN_REPOSITORY_UNCONFIRMED"
            assert lifecycle.read(OWNER, rejected.run_id).status == "RUNNING"
            assert count(dsn, "SELECT count(*) FROM scheduler_outbox WHERE payload->>'run_id'=%s", (rejected.run_id,)) == 0
            if transition == "stop":
                assert count(dsn, "SELECT count(*) FROM runtime_run_controls WHERE control_id='reject-stop-control'") == 0
            results["deferred_commit_rollback_" + transition] = "PASS"

        env = dict(os.environ, A2FLOW_PROBE_ISOLATED_DSN=dsn)
        completed = subprocess.run([sys.executable, __file__, "--consume", message_id],
                                   env=env, capture_output=True, text=True)
        assert completed.returncode == 0, "Fresh-process delivery failed"
        assert count(dsn, "SELECT count(*) FROM notifications WHERE idempotency_key=%s", (message_id,)) == 1
        consume(dsn, message_id)
        assert count(dsn, "SELECT count(*) FROM notifications WHERE idempotency_key=%s", (message_id,)) == 1
        results["fresh_process_delivery_and_duplicate_reference"] = "PASS"

        def enqueue(suffix):
            command = NotificationCommand(message_id="probe:" + suffix, user_id=1008,
                run_id=run.run_id, event="waiting", title="Probe", body="Synthetic isolated event")
            with outbox.transaction() as session:
                outbox.enqueue(command, session=session)
            return command

        command = enqueue("ack-failure")
        try:
            consume(dsn, command.message_id, fail_ack=True)
            raise AssertionError("Expected acknowledgement error")
        except RuntimeError as error:
            assert str(error) == "PROBE_ACK_FAILURE"
        consume(dsn, command.message_id)
        assert count(dsn, "SELECT count(*) FROM notifications WHERE idempotency_key=%s", (command.message_id,)) == 1
        assert count(dsn, "SELECT count(*) FROM scheduler_outbox WHERE message_id=%s AND state='completed'", (command.message_id,)) == 1
        results["ack_failure_after_commit_duplicate_safe"] = "PASS"

        for suffix, already_saved, external in (("before-local", False, False),
                                                 ("after-local", True, False),
                                                 ("external-unknown", True, True)):
            command = enqueue(suffix)
            assert outbox.claim(command.message_id) is not None
            if already_saved:
                persist_notification(outbox, command)
            with outbox.transaction() as session:
                session.execute(text("UPDATE scheduler_outbox SET claimed_at=now()-interval '10 minutes' WHERE message_id=:id"), {"id": command.message_id})
            reconcile_notifications(outbox, external_sender_configured=external)
            assert count(dsn, "SELECT count(*) FROM notifications WHERE idempotency_key=%s", (command.message_id,)) == 1
            expected = "unknown" if external else "completed"
            assert count(dsn, "SELECT count(*) FROM scheduler_outbox WHERE message_id=%s AND state=%s", (command.message_id, expected)) == 1
            reconcile_notifications(outbox, external_sender_configured=external)
            assert count(dsn, "SELECT count(*) FROM notifications WHERE idempotency_key=%s", (command.message_id,)) == 1
            results["stale_claim_" + suffix] = "PASS"
        with psycopg.connect(dsn, autocommit=True) as checkpoint_connection:
            saver = PostgresSaver(checkpoint_connection)
            saver.setup()
            class ProbeState(TypedDict):
                value: str
            invocation_count = []
            waiting_run = allocate(lifecycle, "native-waiting")
            reference = {"runId": waiting_run.run_id, "nodeId": "first",
                         "interactionId": "probe-card", "applicationKey": "probe.app", "versionId": "v1"}
            def wait_node(state):
                invocation_count.append("synthetic-native-interrupt")
                interrupt(reference)
                raise AssertionError("The probe must never resume native business execution")
            child_builder = StateGraph(ProbeState)
            child_builder.add_node("input", wait_node)
            child_builder.add_edge(START, "input")
            child_builder.add_edge("input", END)
            parent_builder = StateGraph(ProbeState)
            parent_builder.add_node("first", child_builder.compile())
            parent_builder.add_edge(START, "first")
            parent_builder.add_edge("first", END)
            native_graph = parent_builder.compile(checkpointer=saver)
            config = {"configurable": {"thread_id": waiting_run.thread_id}}
            native_graph.invoke({"value": "synthetic"}, config)
            with psycopg.connect(dsn) as connection:
                document = {"phase": "WAITING", "run_active": True, "node_waiting": True,
                            "graph_thread_id": waiting_run.thread_id,
                            "application_key": "probe.app", "application_version": "v1"}
                connection.execute(
                    "INSERT INTO runtime_interactions VALUES (%s,%s,%s,%s,%s,%s)",
                    (1008, "PRT", waiting_run.run_id, "first", "probe-card", Jsonb(document)),
                )
            assert count(dsn, "SELECT count(*) FROM scheduler_outbox WHERE payload->>'run_id'=%s", (waiting_run.run_id,)) == 0
            class ReadOnlyGraph:
                def get_state(self, *args, **kwargs):
                    return native_graph.get_state(*args, **kwargs)
                def invoke(self, *args, **kwargs):
                    raise AssertionError("Recovery attempted graph execution")
            @contextmanager
            def read_session(owner, *, read_only=False):
                assert read_only and owner == OWNER
                yield SimpleNamespace(runner=SimpleNamespace(
                    graph_factory=lambda run, life: (RunGraphBinding(ReadOnlyGraph(), life), {})))
            faulting_scan = SimpleNamespace(waiting_candidates=lambda *args, **kwargs: [
                (1008, "missing-synthetic-run"), (1008, waiting_run.run_id),
            ])
            fair_recovery = WaitingNotificationRecovery(faulting_scan, lifecycle, read_session, "PRT")
            fair_recovery.pass_once()
            assert count(dsn, "SELECT count(*) FROM scheduler_outbox WHERE payload->>'run_id'=%s AND payload->>'event'='waiting'", (waiting_run.run_id,)) == 1
            results["one_invalid_candidate_does_not_starve_next"] = "PASS"
            recovery = WaitingNotificationRecovery(repository, lifecycle, read_session, "PRT")
            recovery.pass_once()
            assert count(dsn, "SELECT count(*) FROM scheduler_outbox WHERE payload->>'run_id'=%s AND payload->>'event'='waiting'", (waiting_run.run_id,)) == 1
            snapshot = native_graph.get_state(config, subgraphs=True)
            publish_waiting_snapshot(lifecycle, waiting_run, snapshot)
            recovery.pass_once()
            recovery.pass_once()
            assert count(dsn, "SELECT count(*) FROM scheduler_outbox WHERE payload->>'run_id'=%s AND payload->>'event'='waiting'", (waiting_run.run_id,)) == 1
            assert len(invocation_count) == 1
            results["native_nested_checkpoint_missing_notice_recovered"] = "PASS"
            results["normal_and_recovered_waiting_identity_deduplicated"] = "PASS"
            with psycopg.connect(dsn) as connection:
                connection.execute("UPDATE runtime_interactions SET document=jsonb_set(document,'{phase}','\"COMPLETED\"') WHERE run_id=%s", (waiting_run.run_id,))
                connection.execute("DELETE FROM scheduler_outbox WHERE payload->>'run_id'=%s", (waiting_run.run_id,))
            assert publish_waiting_snapshot(lifecycle, waiting_run, snapshot) == 0
            lifecycle.stop(OWNER, waiting_run.run_id, "stop-native-waiting")
            assert publish_waiting_snapshot(lifecycle, waiting_run, snapshot) == 0
            recovery.pass_once()
            recovery.pass_once()
            assert count(dsn, "SELECT count(*) FROM scheduler_outbox WHERE payload->>'run_id'=%s AND payload->>'event'='waiting'", (waiting_run.run_id,)) == 0
            assert len(invocation_count) == 1
            recovery.start()
            assert recovery.shutdown()
            results["consumed_or_stopped_native_wait_not_renotified"] = "PASS"
            results["recovery_worker_shutdown_without_execution"] = "PASS"
        print(json.dumps({"checks": results, "externalSends": 0, "businessCalls": 0,
                          "transport": "fault-injected references", "database": "real isolated PostgreSQL"}, sort_keys=True))
    finally:
        if outbox is not None:
            outbox.engine.dispose()
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--consume":
        child()
    else:
        main()
