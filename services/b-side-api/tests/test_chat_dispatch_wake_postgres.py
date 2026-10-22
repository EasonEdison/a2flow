"""Disposable PostgreSQL scheduling tests with explicitly scripted native facts."""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from a2flow_bside.chat_application import ChatApplicationService
from a2flow_bside.durable_chat import DurableChat, DurableDispatcher
from a2flow_bside.repositories import MessagesRepository
from a2flow_bside.route_models import ChatCardAction, MessageSend
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from skillweave_contracts.chat_result import result_from_events

HERE = Path(__file__).resolve().parent
METRICS: dict[str, object] = {}


def connection(dsn, schema):
    return psycopg.connect(dsn, row_factory=dict_row, options="-c search_path=" + schema)


class CountingStore(DurableChat):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scans = 0
        self.materializations = 0
        self.finished_materializations = 0
        self.materialization_times = []
        self.scan_times = []
        self.fail_scan_once = False
        self.mutex = threading.Lock()

    def candidates(self, **kwargs):
        with self.mutex:
            self.scans += 1
            self.scan_times.append(time.perf_counter())
            fail, self.fail_scan_once = self.fail_scan_once, False
        if fail:
            raise psycopg.OperationalError("synthetic reconciliation read failure")
        return super().candidates(**kwargs)

    def materialize(self, *args, **kwargs):
        with self.mutex:
            self.materializations += 1
            self.materialization_times.append(time.perf_counter())
        try:
            return super().materialize(*args, **kwargs)
        finally:
            with self.mutex:
                self.finished_materializations += 1


class DatabaseRunner:
    """Recording fake native port; PostgreSQL receipts reveal every iteration."""

    def __init__(self, factory, *, gate=None):
        self.factory = factory
        self.gate = gate
        self.started = []
        self.inspections = []

    async def inspect_turn(self, **kwargs):
        key = kwargs["turn_id"]
        self.inspections.append((key, time.perf_counter()))

        def read():
            with self.factory() as c:
                return c.execute(
                    "SELECT state,result FROM wake_native_facts WHERE turn_id=%s", (key,)
                ).fetchone()

        row = await asyncio.to_thread(read)
        return (
            {"status": "NOT_STARTED"}
            if row is None
            else {
                "status": row["state"],
                **({"result": row["result"]} if row["state"] == "COMPLETED" else {}),
            }
        )

    async def iterate(self, **kwargs):
        key = kwargs["turn_id"]

        def started():
            with self.factory() as c:
                c.execute(
                    "INSERT INTO wake_native_calls(turn_id,process_id) VALUES(%s,%s)",
                    (key, os.getpid()),
                )
                c.execute(
                    "INSERT INTO wake_native_facts(turn_id,state) VALUES(%s,'BUSY') "
                    "ON CONFLICT(turn_id) DO UPDATE SET state='BUSY'",
                    (key,),
                )

        await asyncio.to_thread(started)
        self.started.append((key, time.perf_counter()))
        if self.gate is not None and kwargs["text"].startswith("hold"):
            await self.gate.wait()
        public = [
            {
                "type": "text_delta",
                "text": "synthetic saved result",
                "modelMessageId": "model-" + key,
            },
            {
                "type": "done",
                "content": "synthetic saved result",
                "finalModelMessageId": "model-" + key,
            },
        ]
        result = result_from_events(public, turn_id=key)

        def completed():
            with self.factory() as c:
                c.execute(
                    "UPDATE wake_native_facts SET state='COMPLETED',result=%s WHERE turn_id=%s",
                    (Jsonb(result), key),
                )

        await asyncio.to_thread(completed)
        for event in public:
            yield event


def commit_then_crash(dsn, schema, cid):
    store = DurableChat(lambda: connection(dsn, schema), environment="PRT")
    store.receive(
        user_id=1,
        conversation_id=cid,
        request_id="committed-before-crash",
        payload={"text": "lost wake"},
        references=[],
    )
    os._exit(17)  # Deliberately bypass every cleanup/notify after the committed inbox.


def competing_dispatch(dsn, schema, input_id, start):
    factory = lambda: connection(dsn, schema)
    store = DurableChat(factory, environment="PRT")
    start.wait(8)
    asyncio.run(
        DurableDispatcher(store, MessagesRepository(factory), DatabaseRunner(factory)).dispatch(
            store.get(input_id)
        )
    )


def dispatch_with_paused_lock(dsn, schema, input_id, held, release):
    factory = lambda: connection(dsn, schema)

    class PauseStore(DurableChat):
        @contextmanager
        def lock(self, conversation_id):
            with super().lock(conversation_id) as acquired:
                if acquired:
                    held.set()
                    if not release.wait(8):
                        raise RuntimeError("paused lock test release timeout")
                yield acquired

    store = PauseStore(factory, environment="PRT")
    asyncio.run(
        DurableDispatcher(store, MessagesRepository(factory), DatabaseRunner(factory)).dispatch(
            store.get(input_id)
        )
    )


@unittest.skipUnless(os.environ.get("A2FLOW_WAKE_PROBE_DSN"), "disposable PostgreSQL required")
class ChatDispatchWakeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dsn = os.environ["A2FLOW_WAKE_PROBE_DSN"]
        self.schema = "dispatch_wake_" + uuid4().hex
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        with self.factory() as c:
            c.execute((HERE.parent / "src/a2flow_bside/schema.sql").read_text())
            c.execute(
                "CREATE TABLE wake_native_calls(id bigserial PRIMARY KEY,turn_id text NOT NULL,process_id integer NOT NULL); "
                "CREATE TABLE wake_native_facts(turn_id text PRIMARY KEY,state text NOT NULL,result jsonb);"
            )
        self.store = CountingStore(self.factory, environment="PRT")
        self.messages = MessagesRepository(self.factory)
        self.runner = DatabaseRunner(self.factory)
        self.workers = []
        self.addAsyncCleanup(self.stop_workers)

    def factory(self):
        return connection(self.dsn, self.schema)

    def drop_schema(self):
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    async def stop_workers(self):
        for stop, task, runner in self.workers:
            stop.set()
            if runner.gate is not None:
                runner.gate.set()
        for stop, task, runner in self.workers:
            await asyncio.wait_for(task, 5)

    def conversation(self):
        with self.factory() as c:
            return c.execute(
                "INSERT INTO conversations(user_id) VALUES(1) RETURNING id"
            ).fetchone()["id"]

    def receive(self, cid=None, key="request", text="synthetic input"):
        return self.store.receive(
            user_id=1,
            conversation_id=cid or self.conversation(),
            request_id=key,
            payload={"text": text},
            references=[],
        )

    def app(self, *, action=None):
        return ChatApplicationService(
            messages=self.messages,
            environment="PRT",
            work_activities=None,
            processing_tasks=None,
            chat_action=action,
            durable_chat=self.store,
        )

    async def until(self, predicate, *, timeout=4):
        deadline = time.perf_counter() + timeout
        while not predicate():
            if time.perf_counter() >= deadline:
                self.fail("timed out waiting for persisted scheduling fact")
            await asyncio.sleep(0.005)

    async def start_worker(
        self, *, runner=None, reconcile_seconds=30.0, max_concurrency=8, retry_seconds=2.0
    ):
        chosen = runner or self.runner
        stop = asyncio.Event()
        dispatcher = DurableDispatcher(
            self.store,
            self.messages,
            chosen,
            reconcile_seconds=reconcile_seconds,
            max_concurrency=max_concurrency,
            retry_seconds=retry_seconds,
        )
        task = asyncio.create_task(dispatcher.run(stop))
        self.workers.append((stop, task, chosen))
        await self.until(lambda: self.store.scans >= 1)
        return stop, task

    def call_count(self, input_id=None):
        with self.factory() as c:
            if input_id is None:
                return c.execute("SELECT count(*) AS n FROM wake_native_calls").fetchone()["n"]
            return c.execute(
                "SELECT count(*) AS n FROM wake_native_calls WHERE turn_id=%s", (str(input_id),)
            ).fetchone()["n"]

    async def completed(self, turn, *, timeout=4):
        await self.until(
            lambda: self.store.get(turn["input_message_id"])["status"] == "COMPLETED",
            timeout=timeout,
        )

    async def test_rollback_neither_wakes_nor_dispatches_and_observer_does_not_notify(self):
        await self.start_worker(reconcile_seconds=0.1)
        cid = self.conversation()
        with self.factory() as c:
            c.execute("""CREATE FUNCTION reject_message() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'synthetic admission rollback'; END $$;
                CREATE TRIGGER reject_message BEFORE INSERT ON messages FOR EACH ROW EXECUTE FUNCTION reject_message();""")
        version = self.store.wake.snapshot()
        with self.assertRaises(psycopg.Error):
            await self.app().admit_message(
                MessageSend(conversationId=cid, clientRequestId="rollback", text="rollback"), 1
            )
        self.assertEqual(version, self.store.wake.snapshot())
        completion = SimpleNamespace(
            owner=SimpleNamespace(user_id=1),
            conversation_id=str(cid),
            card_id="rollback-card",
            request_id="submit",
            metadata={"definitionSource": "TEMPORARY"},
        )
        with self.assertRaisesRegex(RuntimeError, "card rollback"):
            with self.factory() as c:
                self.store.observe_completion(c, completion)
                self.assertEqual(version, self.store.wake.snapshot())
                raise RuntimeError("card rollback")
        await asyncio.sleep(0.15)
        self.assertEqual(0, self.call_count())
        with self.factory() as c:
            self.assertEqual(0, c.execute("SELECT count(*) AS n FROM messages").fetchone()["n"])
            self.assertEqual(
                0, c.execute("SELECT count(*) AS n FROM chat_continuations").fetchone()["n"]
            )

    async def test_default_interval_wake_latency_samples_and_replayed_request(self):
        await self.start_worker()
        samples = []
        for index in range(8):
            cid = self.conversation()
            body = MessageSend(
                conversationId=cid, clientRequestId="sample-" + str(index), text="latency sample"
            )
            # Return from receive establishes the measured transaction-commit lower bound.
            turn = await asyncio.to_thread(self.receive, cid, body.clientRequestId, body.text)
            committed = time.perf_counter()
            self.store.wake.notify()
            await self.until(
                lambda: any(key == str(turn["input_message_id"]) for key, _ in self.runner.started)
            )
            dispatched = next(
                stamp for key, stamp in self.runner.started if key == str(turn["input_message_id"])
            )
            samples.append(round((dispatched - committed) * 1000, 3))
            await self.completed(turn)
        METRICS["transactionReturnToScriptedRunnerStartMs"] = samples
        METRICS["latencyConfig"] = {
            "reconcileSeconds": 30.0,
            "maxConcurrency": 8,
            "samples": len(samples),
            "native": "scripted PostgreSQL recording port",
            "retrySeconds": 2.0,
            "boundary": "transaction return and notify to scripted native-port start record",
        }
        self.assertLess(max(samples), 450, "wake scheduling regressed to a 500ms polling cycle")
        # The actual application notification is checked independently from the measured hint.
        body = MessageSend(
            conversationId=self.conversation(),
            clientRequestId="application",
            text="actual app admission",
        )
        version = self.store.wake.snapshot()
        accepted = await self.app().admit_message(body, 1)
        self.assertGreater(self.store.wake.snapshot(), version)
        await self.completed(accepted)
        calls = self.call_count()
        replay_version = self.store.wake.snapshot()
        repeat = await self.app().admit_message(body, 1)
        self.assertEqual(accepted["input_message_id"], repeat["input_message_id"])
        self.assertGreater(self.store.wake.snapshot(), replay_version)
        await asyncio.sleep(0.03)
        self.assertEqual(calls, self.call_count())

    async def test_default_idle_reconciliation_observed_for_more_than_thirty_seconds(self):
        await self.start_worker()
        start = time.perf_counter()
        await asyncio.sleep(31.2)
        duration = time.perf_counter() - start
        METRICS["idleObservation"] = {
            "configuredReconcileSeconds": 30.0,
            "observedSeconds": round(duration, 3),
            "candidateReconciliationPasses": self.store.scans,
            "executions": self.call_count(),
        }
        self.assertGreater(duration, 30)
        self.assertEqual(
            2, self.store.scans
        )  # Startup plus one actual default-period reconciliation.
        self.assertEqual(0, self.call_count())

    async def test_startup_recovers_committed_inbox_without_hint(self):
        turn = self.receive()
        await self.start_worker()
        await self.completed(turn)
        self.assertEqual(1, self.call_count(turn["input_message_id"]))

    async def test_process_crash_after_commit_before_hint_is_found_by_reconciliation(self):
        await self.start_worker(reconcile_seconds=0.12)
        cid = self.conversation()
        context = multiprocessing.get_context("spawn")
        process = context.Process(target=commit_then_crash, args=(self.dsn, self.schema, cid))
        process.start()
        await asyncio.to_thread(process.join, 10)
        if process.is_alive():
            process.kill()
            process.join()
            self.fail("crash fixture process failed to finish")
        self.assertEqual(17, process.exitcode)
        await self.until(lambda: self.call_count() == 1)
        with self.factory() as c:
            turn = c.execute("SELECT * FROM chat_turns WHERE conversation_id=%s", (cid,)).fetchone()
        await self.completed(turn)
        self.assertEqual(1, self.call_count())

    async def test_two_actual_processes_compete_for_one_persisted_turn(self):
        turn = self.receive()
        context = multiprocessing.get_context("spawn")
        start = context.Event()
        processes = [
            context.Process(
                target=competing_dispatch,
                args=(self.dsn, self.schema, turn["input_message_id"], start),
            )
            for _ in range(2)
        ]
        try:
            for process in processes:
                process.start()
            start.set()
            for process in processes:
                await asyncio.to_thread(process.join, 10)
                self.assertEqual(0, process.exitcode)
        finally:
            for process in processes:
                if process.is_alive():
                    process.kill()
                process.join()
        await self.completed(turn)
        self.assertEqual(1, self.call_count(turn["input_message_id"]))
        with self.factory() as c:
            self.assertEqual(2, c.execute("SELECT count(*) AS n FROM messages").fetchone()["n"])
        METRICS["contention"] = {
            "workers": 2,
            "startMethod": "spawn",
            "executions": 1,
            "postgres": True,
        }

    async def test_busy_retry_uses_saved_deadline_without_hot_scans(self):
        turn = self.receive()
        with self.factory() as c:
            c.execute(
                "INSERT INTO wake_native_facts(turn_id,state) VALUES(%s,'BUSY')",
                (str(turn["input_message_id"]),),
            )
        await self.start_worker()
        await self.until(lambda: len(self.runner.inspections) == 1)
        await asyncio.sleep(0.2)
        self.assertEqual(1, len(self.runner.inspections))
        self.assertLessEqual(self.store.scans, 4)
        with self.factory() as c:
            c.execute(
                "DELETE FROM wake_native_facts WHERE turn_id=%s", (str(turn["input_message_id"]),)
            )
        await self.completed(turn, timeout=3)
        timestamps = [
            stamp for key, stamp in self.runner.inspections if key == str(turn["input_message_id"])
        ]
        self.assertGreaterEqual(timestamps[1] - timestamps[0], 1.8)
        self.assertEqual(1, self.call_count())
        METRICS["busyRetry"] = {
            "observedInspectionGapSeconds": round(timestamps[1] - timestamps[0], 3),
            "executions": 1,
        }

    async def test_unknown_native_result_is_never_replayed_or_overtaken(self):
        first = self.receive()
        later = self.receive(first["conversation_id"], key="later")
        with self.factory() as c:
            c.execute(
                "INSERT INTO wake_native_facts(turn_id,state) VALUES(%s,'NEEDS_REVIEW')",
                (str(first["input_message_id"]),),
            )
        await self.start_worker(reconcile_seconds=0.08)
        await self.until(
            lambda: self.store.get(first["input_message_id"])["status"] == "NEEDS_REVIEW"
        )
        await self.until(
            lambda: self.store.get(later["input_message_id"])["status"] == "NEEDS_REVIEW"
        )
        self.store.wake.notify()
        await asyncio.sleep(0.12)
        self.assertEqual(0, self.call_count())
        self.assertEqual("unconfirmed", self.store.pair(first)[1]["content"]["delivery"])

    async def test_full_capacity_ignores_wake_storm_and_release_dispatches_next(self):
        gate = asyncio.Event()
        runner = DatabaseRunner(self.factory, gate=gate)
        first = self.receive(text="hold first")
        second = self.receive()
        await self.start_worker(runner=runner, max_concurrency=1)
        await self.until(lambda: self.call_count() == 1)
        scans = self.store.scans
        for _ in range(1000):
            self.store.wake.notify()
        await asyncio.sleep(0.12)
        self.assertEqual(scans, self.store.scans)
        self.assertEqual(1, self.call_count())
        release = time.perf_counter()
        gate.set()
        await self.completed(second)
        self.assertLess(
            next(stamp for key, stamp in runner.started if key == str(second["input_message_id"]))
            - release,
            0.45,
        )
        await self.completed(first)
        self.assertEqual(2, self.call_count())

    async def test_next_turn_of_same_conversation_runs_immediately_after_predecessor(self):
        first = self.receive()
        second = self.receive(first["conversation_id"], key="second")
        await self.start_worker(max_concurrency=2)
        await self.completed(second)
        self.assertEqual(
            [str(first["input_message_id"]), str(second["input_message_id"])],
            [key for key, _ in self.runner.started],
        )
        self.assertEqual(2, self.call_count())

    async def test_excluded_active_conversations_are_filtered_before_sql_limit(self):
        turns = [self.receive() for _ in range(33)]
        excluded = [row["conversation_id"] for row in turns[:32]]
        found = self.store.candidates(exclude_conversations=excluded, limit=1)
        self.assertEqual(
            [turns[-1]["input_message_id"]], [row["input_message_id"] for row in found]
        )
        self.assertIsNone(
            self.store.next_delay(exclude_conversations=[row["conversation_id"] for row in turns])
        )
        self.assertEqual(0.0, self.store.next_delay())
        self.assertEqual(
            turns[1]["input_message_id"],
            self.store.candidates(after_input_id=turns[0]["input_message_id"], limit=1)[0][
                "input_message_id"
            ],
        )
        self.assertEqual(
            turns[0]["input_message_id"],
            self.store.candidates(after_input_id=turns[-1]["input_message_id"], limit=1)[0][
                "input_message_id"
            ],
        )

    async def test_committed_card_action_materializes_and_continues_once(self):
        cid = self.conversation()
        completion = SimpleNamespace(
            owner=SimpleNamespace(user_id=1),
            conversation_id=str(cid),
            card_id="saved-card",
            request_id="submit-once",
            metadata={"definitionSource": "TEMPORARY"},
        )

        def action(user_id, conversation_id, card_id, payload):
            with self.factory() as c:
                self.store.observe_completion(c, completion)
            return {
                "continuation": {"cardId": card_id, "requestId": "submit-once"},
                "card": {
                    "cardId": card_id,
                    "conversationId": str(cid),
                    "status": "COMPLETED",
                    "display": {
                        "protocolProfile": "a2flow.temporary.v1",
                        "definitionSource": "TEMPORARY",
                    },
                    "result": {"status": "SUBMITTED", "values": {"choice": "synthetic"}},
                },
            }

        await self.start_worker()
        body = ChatCardAction(
            requestId="submit-once", actionName="submit", inputs={"choice": "synthetic"}
        )
        response = await self.app(action=action).execute_chat_card_action(
            1, cid, "saved-card", body
        )
        input_id = int(response["continuation"]["inputMessageId"])
        await self.completed(self.store.get(input_id))
        await self.app(action=action).execute_chat_card_action(1, cid, "saved-card", body)
        await asyncio.sleep(0.05)
        self.assertEqual(1, self.call_count())
        with self.factory() as c:
            self.assertEqual(
                "MATERIALIZED",
                c.execute("SELECT state FROM chat_continuations").fetchone()["state"],
            )
            self.assertEqual(2, c.execute("SELECT count(*) AS n FROM messages").fetchone()["n"])
            self.assertEqual(1, c.execute("SELECT count(*) AS n FROM chat_turns").fetchone()["n"])

    async def test_background_read_failure_backs_off_and_stop_awaits_owned_work(self):
        self.store.fail_scan_once = True
        with self.assertLogs("a2flow_bside.durable_chat", level="ERROR"):
            gate = asyncio.Event()
            runner = DatabaseRunner(self.factory, gate=gate)
            first = self.receive(text="hold during shutdown")
            second = self.receive()
            stop, task = await self.start_worker(
                runner=runner, max_concurrency=1, retry_seconds=0.12
            )
            await asyncio.sleep(0.04)
            self.assertEqual(1, self.store.scans)
            await self.until(lambda: self.call_count() == 1)
        stop.set()
        await asyncio.sleep(0.03)
        self.assertFalse(task.done())
        gate.set()
        await asyncio.wait_for(task, 3)
        self.assertEqual("COMPLETED", self.store.get(first["input_message_id"])["status"])
        self.assertEqual("QUEUED", self.store.get(second["input_message_id"])["status"])
        self.assertEqual(1, self.call_count())

    async def test_defer_preserves_later_deadline_and_due_claim_recheck(self):
        turn = self.receive()
        input_id = turn["input_message_id"]
        generation = self.store.claim_generation(input_id)
        self.store.defer(input_id, generation, 0.2)
        deadline = self.store.get(input_id)["next_attempt_at"]
        self.store.defer(input_id, generation, 0.01)
        self.assertEqual(deadline, self.store.get(input_id)["next_attempt_at"])
        self.store.defer(input_id, generation - 1, 100.0)
        self.assertEqual(deadline, self.store.get(input_id)["next_attempt_at"])
        self.assertIsNone(self.store.claim_generation(input_id))
        await asyncio.sleep(0.23)
        self.assertEqual(generation + 1, self.store.claim_generation(input_id))

    async def test_processing_admission_commits_shared_source_before_notifying(self):
        from a2flow_bside.processing_tasks import ProcessingTasksRepository

        class Activities:
            def get(self, **kwargs):
                return {
                    "runId": "synthetic-run",
                    "attentionItems": [{"attentionId": "attention", "kind": "business"}],
                }

            def get_result(self, **kwargs):
                return {
                    "activityId": "activity",
                    "runId": "synthetic-run",
                    "status": "COMPLETED",
                    "result": {"synthetic": True},
                    "resultPage": "synthetic saved result",
                }

        activities = Activities()
        processing = ProcessingTasksRepository(self.factory, activities)
        app = ChatApplicationService(
            messages=self.messages,
            environment="PRT",
            work_activities=activities,
            processing_tasks=processing,
            chat_action=None,
            durable_chat=self.store,
        )
        cid = self.conversation()
        body = MessageSend(
            conversationId=cid,
            clientRequestId="processing-client",
            text="handle anomaly",
            processingRequestId="processing-source",
            processingTarget={"activityId": "activity", "attentionId": "attention"},
        )
        version = self.store.wake.snapshot()
        first = await app.admit_message(body, 1)
        self.assertEqual(version + 1, self.store.wake.snapshot())
        alias = body.model_copy(update={"clientRequestId": "processing-alias"})
        version = self.store.wake.snapshot()
        repeated = await app.admit_message(alias, 1)
        self.assertEqual(version + 1, self.store.wake.snapshot())
        self.assertEqual(first["input_message_id"], repeated["input_message_id"])
        with self.factory() as c:
            self.assertEqual(
                2, c.execute("SELECT count(*) AS n FROM chat_requests").fetchone()["n"]
            )
            self.assertEqual(2, c.execute("SELECT count(*) AS n FROM messages").fetchone()["n"])
        await self.start_worker()
        await self.completed(first)
        self.assertEqual(1, self.call_count())

    async def test_losing_lock_cannot_defer_winner_paused_before_generation_claim(self):
        turn = self.receive()
        deadline = self.store.get(turn["input_message_id"])["next_attempt_at"]
        context = multiprocessing.get_context("spawn")
        held, release = context.Event(), context.Event()
        winner = context.Process(
            target=dispatch_with_paused_lock,
            args=(self.dsn, self.schema, turn["input_message_id"], held, release),
        )
        winner.start()
        try:
            self.assertTrue(await asyncio.to_thread(held.wait, 8))
            lost = await DurableDispatcher(self.store, self.messages, self.runner).dispatch(turn)
            self.assertIs(False, lost)
            self.assertEqual(deadline, self.store.get(turn["input_message_id"])["next_attempt_at"])
            self.assertEqual(0, self.store.get(turn["input_message_id"])["dispatch_generation"])
        finally:
            release.set()
            await asyncio.to_thread(winner.join, 10)
            if winner.is_alive():
                winner.kill()
                winner.join()
        self.assertEqual(0, winner.exitcode)
        await self.completed(turn)
        self.assertEqual(1, self.call_count())

    async def test_locked_oldest_turn_does_not_starve_another_conversation(self):
        first, second = self.receive(), self.receive()
        with self.store.lock(first["conversation_id"]) as acquired:
            self.assertTrue(acquired)
            await self.start_worker(max_concurrency=1, retry_seconds=0.06)
            await self.completed(second, timeout=1)
            self.assertEqual(0, self.call_count(first["input_message_id"]))
            self.assertEqual(1, self.call_count(second["input_message_id"]))
            self.assertEqual("QUEUED", self.store.get(first["input_message_id"])["status"])
        self.store.wake.notify()
        await self.completed(first)
        self.assertEqual(2, self.call_count())
        rotated = self.store.candidates(after_input_id=first["input_message_id"], limit=1)
        self.assertEqual([], rotated)

    async def test_materialization_and_failure_record_errors_finish_batch_then_back_off(self):
        poison_cid, healthy_cid = self.conversation(), self.conversation()
        with self.factory() as c:
            for card, cid in [("poison-card", poison_cid), ("healthy-card", healthy_cid)]:
                self.store.observe_completion(
                    c,
                    SimpleNamespace(
                        owner=SimpleNamespace(user_id=1),
                        conversation_id=str(cid),
                        card_id=card,
                        request_id="submit",
                        metadata={"definitionSource": "TEMPORARY"},
                    ),
                )
            c.execute("""CREATE FUNCTION reject_poison_turn() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF NEW.source_key='poison-card' THEN RAISE EXCEPTION 'synthetic preparation failure'; END IF;
                RETURN NEW; END $$;
                CREATE TRIGGER reject_poison_turn BEFORE INSERT ON chat_turns FOR EACH ROW EXECUTE FUNCTION reject_poison_turn();
                CREATE FUNCTION reject_poison_failure_record() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF NEW.card_id='poison-card' THEN RAISE EXCEPTION 'synthetic failure persistence error'; END IF;
                RETURN NEW; END $$;
                CREATE TRIGGER reject_poison_failure_record BEFORE UPDATE ON chat_continuations FOR EACH ROW EXECUTE FUNCTION reject_poison_failure_record();""")
        stop = asyncio.Event()
        dispatcher = DurableDispatcher(
            self.store, self.messages, self.runner, reconcile_seconds=30.0, retry_seconds=0.12
        )

        def healthy():
            with self.factory() as c:
                return c.execute(
                    "SELECT * FROM chat_turns WHERE conversation_id=%s", (healthy_cid,)
                ).fetchone()

        with self.assertLogs("a2flow_bside.durable_chat", level="ERROR"):
            task = asyncio.create_task(dispatcher.run(stop))
            self.workers.append((stop, task, self.runner))
            await self.until(lambda: healthy() is not None)
            # Faults are still installed: a poison intent must not starve ready work.
            await self.completed(healthy(), timeout=1.5)
            self.assertEqual(1, self.call_count())
            with self.factory() as c:
                rows = c.execute(
                    "SELECT card_id,state FROM chat_continuations ORDER BY card_id"
                ).fetchall()
                self.assertEqual(
                    [("healthy-card", "MATERIALIZED"), ("poison-card", "PENDING")],
                    [(r["card_id"], r["state"]) for r in rows],
                )
            await self.until(lambda: self.store.finished_materializations >= 2)
            gap = self.store.materialization_times[1] - self.store.materialization_times[0]
            self.assertGreaterEqual(gap, 0.10)
            METRICS["preparationFailureBackoff"] = {
                "configuredRetrySeconds": 0.12,
                "observedPassGapSeconds": round(gap, 3),
                "healthyCompletedWhileFaultRemained": True,
            }
            with self.factory() as c:
                c.execute(
                    "DROP TRIGGER reject_poison_turn ON chat_turns; DROP TRIGGER reject_poison_failure_record ON chat_continuations;"
                )
            await self.until(lambda: self.call_count() == 2)
            with self.factory() as c:
                turns = c.execute("SELECT * FROM chat_turns").fetchall()
            for turn in turns:
                await self.completed(turn)
        with self.factory() as c:
            self.assertEqual(
                2,
                c.execute(
                    "SELECT count(*) AS n FROM chat_turns WHERE status='COMPLETED'"
                ).fetchone()["n"],
            )
            self.assertEqual(4, c.execute("SELECT count(*) AS n FROM messages").fetchone()["n"])
