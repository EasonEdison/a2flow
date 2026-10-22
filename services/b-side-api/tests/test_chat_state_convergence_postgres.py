"""Real PostgreSQL transactions and historical upgrades; no model/business IO."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from a2flow_bside.durable_chat import DurableChat, DurableDispatcher
from a2flow_bside.errors import BsideError
from a2flow_bside.processing_tasks import ProcessingTasksRepository
from a2flow_bside.repositories import MessagesRepository

HERE = Path(__file__).resolve().parent


class Activities:
    def get(self, **kwargs):
        return {"runId": "synthetic-run", "attentionItems": [
            {"attentionId": "synthetic-attention", "kind": "business"}
        ]}


@unittest.skipUnless(os.environ.get("A2FLOW_CONVERGENCE_DSN"), "disposable PG required")
class ChatStateConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ["A2FLOW_CONVERGENCE_DSN"]
        self.schema = "state_product_" + uuid4().hex
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        self.install((HERE.parent / "src/a2flow_bside/schema.sql").read_text())
        self.store = DurableChat(self.factory, environment="PRT")
        self.messages = MessagesRepository(self.factory)
        self.processing = ProcessingTasksRepository(self.factory, Activities())

    def drop_schema(self):
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def factory(self):
        return psycopg.connect(self.dsn, row_factory=dict_row,
                               options="-c search_path=" + self.schema)

    def install(self, source):
        with self.factory() as connection:
            connection.execute(source)

    def conversation(self, user_id=1):
        with self.factory() as connection:
            return connection.execute("INSERT INTO conversations(user_id) VALUES(%s) RETURNING id",
                                      (user_id,)).fetchone()["id"]

    def receive(self, cid, key="request", text="synthetic input", store=None):
        return (store or self.store).receive(user_id=1, conversation_id=cid,
                                            request_id=key, payload={"text": text}, references=[])

    def test_concurrent_duplicate_and_scope_source_identity(self):
        cid = self.conversation()
        with ThreadPoolExecutor(max_workers=8) as pool:
            turns = list(pool.map(lambda _: self.receive(cid), range(16)))
        self.assertEqual(1, len({row["input_message_id"] for row in turns}))
        with self.factory() as connection:
            self.assertEqual(2, connection.execute(
                "SELECT count(*) AS n FROM messages WHERE conversation_id=%s", (cid,)
            ).fetchone()["n"])
        self.assertEqual("USER_MESSAGE", turns[0]["source_kind"])
        self.assertTrue(turns[0]["source_digest"])
        with self.assertRaises(BsideError) as conflict:
            self.receive(cid, text="different input")
        self.assertEqual("CHAT_REQUEST_CONFLICT", conflict.exception.code)
        with self.assertRaises(BsideError):
            self.store.receive(user_id=2, conversation_id=cid, request_id="request",
                               payload={"text": "synthetic input"}, references=[])
        other = DurableChat(self.factory, environment="ONLINE")
        self.assertIsNone(other.request(user_id=1, conversation_id=cid, request_id="request",
                                        payload={"text": "synthetic input"}))
        self.assertIsNone(self.store.request(user_id=2, conversation_id=cid, request_id="request",
                                             payload={"text": "synthetic input"}))

    def test_multiple_client_ids_share_processing_turn_and_conflict(self):
        cid = self.conversation()
        base = dict(user_id=1, environment="PRT", conversation_id=str(cid),
                    request_id="processing-same", text="handle synthetic anomaly", references=[],
                    target={"activityId": "synthetic-activity", "attentionId": "synthetic-attention"})
        def receive(index):
            payload = {"text": base["text"], "processingRequestId": "processing-same",
                       "clientRequestId": "client-" + str(index)}
            return self.processing.begin_turn(**base, client_request_id=payload["clientRequestId"],
                                               client_payload=payload)
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(receive, range(12)))
        self.assertEqual(1, sum(item[0] for item in accepted))
        self.assertEqual(1, len({item[2]["id"] for item in accepted}))
        input_id = accepted[0][2]["id"]
        with self.factory() as connection:
            turns = connection.execute("SELECT * FROM chat_turns WHERE conversation_id=%s", (cid,)).fetchall()
            self.assertEqual(1, len(turns))
            self.assertEqual("PROCESSING", turns[0]["source_kind"])
            self.assertEqual(accepted[0][1]["taskId"], turns[0]["processing_task_id"])
            self.assertEqual(12, connection.execute("SELECT count(*) AS n FROM chat_requests WHERE conversation_id=%s",
                                                    (cid,)).fetchone()["n"])
            self.assertEqual(2, connection.execute("SELECT count(*) AS n FROM messages WHERE conversation_id=%s",
                                                   (cid,)).fetchone()["n"])
        for index in range(12):
            payload = {"text": base["text"], "processingRequestId": "processing-same",
                       "clientRequestId": "client-" + str(index)}
            row = self.store.request(user_id=1, conversation_id=cid,
                                     request_id=payload["clientRequestId"], payload=payload)
            self.assertEqual(input_id, row["input_message_id"])
            self.assertEqual(turns[0]["assistant_message_id"], row["assistant_message_id"])
        with self.assertRaises(BsideError):
            self.processing.begin_turn(**{**base, "text": "changed"},
                                       client_request_id="another-client",
                                       client_payload={"text": "changed"})
        with self.assertRaises(BsideError):
            self.processing.begin_turn(**{**base, "request_id": "new-processing"},
                                       client_request_id="client-0", client_payload={"text": "changed"})
        with self.factory() as connection:
            self.assertEqual(2, connection.execute("SELECT count(*) AS n FROM messages WHERE conversation_id=%s",
                                                   (cid,)).fetchone()["n"])

    def test_final_projection_and_turn_complete_are_one_transaction(self):
        turn = self.receive(self.conversation())
        generation = self.store.claim_generation(turn["input_message_id"])
        self.store.set_status(turn["input_message_id"], "RUNNING", generation)
        args = dict(conversation_id=turn["conversation_id"], message_id=turn["assistant_message_id"])
        partial = {"text": "saved partial", "delivery": "running", "parts": []}
        self.store.save_projection(turn["input_message_id"], generation, **args, content=partial)
        # An actual PostgreSQL trigger aborts after the terminal message update.
        # Neither final projection nor dispatch completion may leak from rollback.
        self.install("""CREATE FUNCTION reject_completion() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.status='COMPLETED' THEN RAISE EXCEPTION 'synthetic commit failure'; END IF;
            RETURN NEW; END $$;
            CREATE TRIGGER reject_completion BEFORE UPDATE OF status ON chat_turns
            FOR EACH ROW EXECUTE FUNCTION reject_completion();""")
        with self.assertRaises(psycopg.Error):
            self.store.save_projection(turn["input_message_id"], generation, **args,
                                       content={"text": "terminal", "delivery": "completed", "parts": []})
        self.assertEqual("RUNNING", self.store.get(turn["input_message_id"])["status"])
        self.assertEqual(partial, self.store.pair(turn)[1]["content"])
        self.install("DROP TRIGGER reject_completion ON chat_turns; DROP FUNCTION reject_completion();")
        final = {"text": "terminal", "delivery": "completed", "parts": []}
        self.store.save_projection(turn["input_message_id"], generation, **args, content=final)
        self.assertEqual("COMPLETED", self.store.get(turn["input_message_id"])["status"])
        self.assertEqual(final, self.store.pair(turn)[1]["content"])

    def test_final_projection_checks_message_conversation_and_generation(self):
        turn = self.receive(self.conversation())
        foreign = self.receive(self.conversation())
        first = self.store.claim_generation(turn["input_message_id"])
        current = self.store.claim_generation(turn["input_message_id"])
        self.store.set_status(turn["input_message_id"], "RUNNING", current)
        args = dict(conversation_id=turn["conversation_id"], message_id=turn["assistant_message_id"])
        final = {"text": "terminal", "delivery": "completed", "parts": []}
        for generation, values in [
            (first, args),
            (current, {**args, "message_id": foreign["assistant_message_id"]}),
            (current, {**args, "conversation_id": foreign["conversation_id"]}),
        ]:
            with self.assertRaises((RuntimeError, BsideError)):
                self.store.save_projection(turn["input_message_id"], generation, **values, content=final)
        self.assertEqual("RUNNING", self.store.get(turn["input_message_id"])["status"])
        self.assertEqual("queued", self.store.pair(turn)[1]["content"]["delivery"])
        self.assertEqual("queued", self.store.pair(foreign)[1]["content"]["delivery"])
        self.store.save_projection(turn["input_message_id"], current, **args, content=final)
        with self.assertRaises(RuntimeError):
            self.store.event(turn["input_message_id"], {"sequence": 2, "type": "text_delta", "text": "stale"}, first)
        self.store.set_status(turn["input_message_id"], "NEEDS_REVIEW", first)
        self.assertEqual("COMPLETED", self.store.get(turn["input_message_id"])["status"])

    def test_completed_sse_resubscription_reads_saved_facts(self):
        turn = self.receive(self.conversation())
        generation = self.store.claim_generation(turn["input_message_id"])
        self.store.set_status(turn["input_message_id"], "RUNNING", generation)
        final = {"text": "synthetic saved result", "delivery": "waiting_action", "parts": []}
        self.store.save_projection(turn["input_message_id"], generation,
                                   conversation_id=turn["conversation_id"],
                                   message_id=turn["assistant_message_id"], content=final)
        self.assertEqual("COMPLETED", self.store.get(turn["input_message_id"])["status"])
        async def read():
            return [json.loads(line[6:]) async for line in self.store.stream(turn)
                    if line.startswith("data:")]
        first, second = asyncio.run(read()), asyncio.run(read())
        self.assertEqual(first, second)
        self.assertEqual("done", first[-1]["type"])
        self.assertEqual("waiting_action", first[-1]["content"]["delivery"])
        self.assertEqual(final, self.store.pair(turn)[1]["content"])

    def test_continuation_crash_during_task_binding_recovers_once(self):
        from types import SimpleNamespace
        from agent_workflow_runtime.chat.cards import DDL
        self.install(";\n".join(DDL))
        cid = self.conversation()
        _, context, _, _ = self.processing.begin_turn(
            user_id=1, environment="PRT", conversation_id=str(cid), request_id="prepare",
            text="handle", references=[], client_request_id="prepare-client", client_payload={"text": "handle"}, target={"activityId": "synthetic-activity",
                                                  "attentionId": "synthetic-attention"})
        task_id = context["taskId"]
        with self.factory() as connection:
            connection.execute("INSERT INTO chat_a2ui_cards(environment,user_id,conversation_id,card_id,"
                               "display,binding_metadata,status,revision,save_fingerprint) "
                               "VALUES('PRT',1,%s,'card-binding','{}',%s::jsonb,'COMPLETED',1,'synthetic')",
                               (str(cid), json.dumps({"processingTaskId": task_id})))
            connection.execute("INSERT INTO processing_cards(user_id,environment,conversation_id,card_id,task_id) "
                               "VALUES(1,'PRT',%s,'card-binding',%s)", (cid, task_id))
        completion = SimpleNamespace(owner=SimpleNamespace(user_id=1), conversation_id=str(cid),
                                     card_id="card-binding", request_id="submit-once",
                                     metadata={"definitionSource": "TEMPORARY"})
        with self.factory() as connection:
            self.store.observe_completion(connection, completion)
        self.install("""CREATE FUNCTION reject_continuation() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.source_kind='CARD_CONTINUATION' THEN RAISE EXCEPTION 'synthetic binding crash'; END IF;
            RETURN NEW; END $$;
            CREATE TRIGGER reject_continuation BEFORE INSERT ON chat_turns
            FOR EACH ROW EXECUTE FUNCTION reject_continuation();""")
        self.store.materialize(self.messages, self.processing)
        with self.factory() as connection:
            self.assertEqual("PENDING", connection.execute("SELECT state FROM chat_continuations").fetchone()["state"])
            self.assertEqual(0, connection.execute("SELECT count(*) AS n FROM chat_turns WHERE source_kind='CARD_CONTINUATION'").fetchone()["n"])
        self.install("DROP TRIGGER reject_continuation ON chat_turns; DROP FUNCTION reject_continuation(); "
                     "UPDATE chat_continuations SET next_attempt_at=now();")
        # A replacement worker reuses the persisted intent and any saved message pair.
        replacement = DurableChat(self.factory, environment="PRT")
        replacement.materialize(self.messages, self.processing)
        replacement.materialize(self.messages, self.processing)
        with self.factory() as connection:
            turns = connection.execute("SELECT * FROM chat_turns WHERE source_kind='CARD_CONTINUATION'").fetchall()
            self.assertEqual(1, len(turns))
            self.assertEqual(task_id, turns[0]["processing_task_id"])
            self.assertEqual("MATERIALIZED", connection.execute("SELECT state FROM chat_continuations").fetchone()["state"])
            self.assertEqual(2, connection.execute("SELECT count(*) AS n FROM messages WHERE ref_kind='temporary_interaction'").fetchone()["n"])
            self.assertNotEqual("RESOLVED", connection.execute("SELECT status FROM processing_tasks WHERE task_id=%s", (task_id,)).fetchone()["status"])

    def test_incompatible_schema_is_rejected_without_modifying_saved_rows(self):
        # An obsolete shape is deliberately rejected, not upgraded at request time.
        self.install("DROP SCHEMA " + self.schema + " CASCADE; CREATE SCHEMA " + self.schema + ";")
        self.install("CREATE TABLE chat_turns(input_message_id bigint PRIMARY KEY,status text,request_id text); "
                     "INSERT INTO chat_turns VALUES(7,'RUNNING','saved-old-input'); "
                     "CREATE TABLE chat_continuations(reference text,materialized boolean);")
        with self.assertRaises((RuntimeError, ValueError, BsideError, psycopg.Error)):
            self.store.check_ready()
        with self.factory() as connection:
            self.assertEqual({"input_message_id": 7, "status": "RUNNING", "request_id": "saved-old-input"},
                             dict(connection.execute("SELECT * FROM chat_turns").fetchone()))
            self.assertEqual({"input_message_id", "status", "request_id"}, {
                r["column_name"] for r in connection.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name='chat_turns'",
                    (self.schema,))})

    def test_native_completed_repairs_only_snapshot_without_runner_reentry(self):
        from skillweave_contracts.chat_result import result_from_events
        turn = self.receive(self.conversation())
        result = result_from_events([
            {"type": "text_delta", "modelMessageId": "model-saved", "text": "native saved result"},
            {"type": "done", "content": "native saved result", "finalModelMessageId": "model-saved"},
        ], turn_id=str(turn["input_message_id"]))
        class CompletedRunner:
            calls = 0
            async def inspect_turn(self, **kwargs):
                return {"status": "COMPLETED", "result": result}
            async def iterate(self, **kwargs):
                self.calls += 1
                raise AssertionError("completed native turn must not reenter runner")
                yield
        runner = CompletedRunner()
        dispatcher = DurableDispatcher(self.store, self.messages, runner)
        asyncio.run(dispatcher.dispatch(turn))
        asyncio.run(dispatcher.dispatch(turn))
        self.assertEqual(0, runner.calls)
        self.assertEqual("COMPLETED", self.store.get(turn["input_message_id"])["status"])
        content = self.store.pair(turn)[1]["content"]
        self.assertEqual("native saved result", content["text"])
        self.assertEqual("text:" + str(turn["assistant_message_id"]) + ":1", content["parts"][0]["id"])
        self.assertEqual(str(turn["input_message_id"]), content["execution"]["turnId"])

    def test_live_dispatch_and_snapshot_repair_have_identical_complete_projection(self):
        from test_chat_result_postgres import events
        from skillweave_contracts.chat_result import result_from_events
        from a2flow_bside.chat_delivery import restore_content
        turn = self.receive(self.conversation())
        stream = events()
        result = result_from_events(stream, turn_id=str(turn["input_message_id"]))
        class NativeRunner:
            calls = 0
            async def inspect_turn(self, **kwargs):
                return {"status": "NOT_STARTED"}
            async def iterate(self, **kwargs):
                self.calls += 1
                for event in stream:
                    yield event
        runner = NativeRunner()
        asyncio.run(DurableDispatcher(self.store, self.messages, runner).dispatch(turn))
        user, assistant = self.store.pair(turn)
        self.assertEqual("COMPLETED", self.store.get(turn["input_message_id"])["status"])
        self.assertEqual(1, runner.calls)
        self.assertEqual(restore_content(result, input_message=user, assistant_message=assistant),
                         assistant["content"])
        with self.factory() as connection:
            rows = connection.execute("SELECT sequence,dispatch_generation FROM chat_turn_events WHERE input_message_id=%s ORDER BY sequence",
                                      (turn["input_message_id"],)).fetchall()
            self.assertEqual(len(rows), len({r["sequence"] for r in rows}))
            self.assertTrue(all(r["dispatch_generation"] == 1 for r in rows))
