"""Final-result integrity and native admission on real disposable PostgreSQL."""

import copy
import hashlib
import json
import os
import unittest
from uuid import uuid4

import psycopg
from agent_workflow_runtime.chat.persistence import ConversationAdmissionError, ConversationStore
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from skillweave_contracts import TrustedContext
from skillweave_contracts.chat_result import (
    result_from_events,
    validate_result,
)

OBSOLETE_SCHEMA = """
CREATE TABLE agent_conversations (
 environment text NOT NULL,user_id bigint NOT NULL,conversation_id text NOT NULL,
 thread_id text NOT NULL UNIQUE,state text NOT NULL CHECK(state IN ('READY','RUNNING','FAILED')),
 last_turn_id text, PRIMARY KEY(environment,user_id,conversation_id));
"""


def events():
    return [
        {"type": "reasoning_delta", "modelMessageId": "model-process", "text": "check facts"},
        {"type": "text_delta", "modelMessageId": "model-process", "text": "checking"},
        {
            "type": "tool_call_started",
            "toolCallId": "tool-read",
            "name": "synthetic.read",
            "startedAt": "2026-10-22T00:00:00Z",
            "arguments": {"id": "synthetic"},
        },
        {
            "type": "tool_call_finished",
            "toolCallId": "tool-read",
            "name": "synthetic.read",
            "startedAt": "2026-10-22T00:00:00Z",
            "finishedAt": "2026-10-22T00:00:01Z",
            "durationMs": 1000,
            "lifecycleStatus": "returned",
            "toolMessageStatus": "success",
            "businessSuccess": True,
            "result": {"synthetic": "saved receipt"},
        },
        {
            "type": "application_rendered",
            "card": {
                "cardId": "card-synthetic",
                "status": "WAITING_ACTION",
                "display": {"title": "Missing input"},
            },
        },
        {
            "type": "personal_workflow_created",
            "workflow": {
                "definitionKey": "personal-wf-synthetic",
                "source": "PERSONAL",
                "name": "Synthetic workflow",
                "defaultRequirement": "Review result",
                "nodes": [
                    {
                        "nodeId": "read",
                        "type": "BUSINESS_CAPABILITY",
                        "abilityKey": "synthetic.read",
                    }
                ],
            },
        },
        {"type": "waiting_action", "cardId": "card-synthetic"},
        {"type": "text_delta", "modelMessageId": "model-final", "text": "saved summary"},
        {"type": "done", "content": "saved summary", "finalModelMessageId": "model-final"},
    ]


def rehash(result):
    body = {key: value for key, value in result.items() if key != "checksum"}
    result["checksum"] = hashlib.sha256(
        json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()
    return result


@unittest.skipUnless(os.environ.get("A2FLOW_CONVERGENCE_DSN"), "disposable PG required")
class ChatResultPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.raw_dsn = os.environ["A2FLOW_CONVERGENCE_DSN"]
        self.schema = "state_native_" + uuid4().hex
        with psycopg.connect(self.raw_dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        self.dsn = make_conninfo(self.raw_dsn, options="-c search_path=" + self.schema + ",public")
        self.store = ConversationStore(self.dsn)
        self.store.setup()
        self.owner = TrustedContext(user_id=19001, environment="PRT")
        self.conversation = str(uuid4())

    def drop_schema(self):
        with psycopg.connect(self.raw_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )

    def connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def install_incompatible_schema(self):
        with self.connect() as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE; CREATE SCHEMA {};").format(
                    sql.Identifier(self.schema), sql.Identifier(self.schema)
                )
            )
            connection.execute(OBSOLETE_SCHEMA)

    def old_conversation(self, cid, state, last):
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO agent_conversations VALUES('PRT',19001,%s,%s,%s,%s)",
                (cid, "thread-" + cid, state, last),
            )

    def test_complete_snapshot_preserves_tool_card_workflow_order_without_event_array(self):
        result = result_from_events(events(), turn_id="1")
        with self.store.session(
            self.owner, self.conversation, "1", completion_result=lambda: result
        ):
            pass
        inspected = self.store.inspect_turn(self.owner, self.conversation, "1")
        self.assertEqual({"status": "COMPLETED", "result": result}, inspected)
        self.assertNotIn("events", inspected)
        content = result["content"]
        self.assertEqual("waiting_action", content["delivery"])
        self.assertEqual("saved summary", content["text"])
        self.assertEqual(
            ["text", "application", "personal_workflow", "text"],
            [part["type"] for part in content["parts"]],
        )
        call = content["execution"]["toolCalls"][0]
        self.assertEqual({"id": "synthetic"}, call["arguments"])
        self.assertEqual({"synthetic": "saved receipt"}, call["result"])
        self.assertEqual("card-synthetic", content["parts"][1]["card"]["cardId"])
        with self.connect() as connection:
            row = connection.execute("SELECT state,result FROM agent_chat_turns").fetchone()
            self.assertEqual(result, row["result"])
            columns = {
                r["column_name"]
                for r in connection.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name='agent_conversations'",
                    (self.schema,),
                )
            }
            self.assertNotIn("state", columns)
            self.assertNotIn("last_turn_id", columns)
        self.assertEqual(
            "NOT_STARTED",
            self.store.inspect_turn(
                TrustedContext(user_id=19002, environment="PRT"), self.conversation, "1"
            )["status"],
        )
        self.assertEqual(
            "NOT_STARTED",
            self.store.inspect_turn(
                TrustedContext(user_id=19001, environment="ONLINE"), self.conversation, "1"
            )["status"],
        )
        self.assertEqual(
            "NEEDS_REVIEW", self.store.inspect_turn(self.owner, self.conversation, "2")["status"]
        )

    def test_checksum_and_semantically_invalid_rehashed_results_are_rejected(self):
        original = result_from_events(events(), turn_id="1")
        broken_hash = copy.deepcopy(original)
        broken_hash["content"]["text"] = "tampered"
        with self.assertRaises(ValueError):
            validate_result(broken_hash)
        mutations = [
            lambda r: r.pop("terminal"),
            lambda r: r.update(terminal={"type": "error", "code": "synthetic"}),
            lambda r: r["content"].update(
                parts=[{"type": "application", "id": "application:missing", "cardId": "missing"}]
            ),
            lambda r: r["content"]["execution"].update(toolCalls=[{"toolCallId": "missing-start"}]),
            lambda r: r.update(finalModelMessageId="missing-model"),
            lambda r: r["content"].update(delivery="completed"),
            lambda r: r["content"].update(errorCode="UNKNOWN"),
            lambda r: r["content"]["parts"][-1].update(text="inconsistent final part"),
            lambda r: next(
                e for e in r["content"]["events"] if e["type"] == "waiting_action"
            ).update(partId=r["content"]["parts"][0]["id"]),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                candidate = copy.deepcopy(original)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    validate_result(rehash(candidate))

    def test_partial_or_failed_stream_cannot_become_terminal_snapshot(self):
        invalid = [
            [],
            [{"type": "text_delta", "text": "partial"}],
            [{"type": "error", "code": "UNKNOWN"}, {"type": "done", "content": ""}],
            [{"type": "waiting_action", "cardId": ""}, {"type": "done", "content": ""}],
            [
                {
                    "type": "tool_call_started",
                    "toolCallId": "pending",
                    "name": "synthetic.write",
                    "startedAt": "2026-10-22T00:00:00Z",
                    "arguments": {},
                },
                {"type": "done", "content": ""},
            ],
            [{"type": "done", "content": "ok"}, {"type": "text_delta", "text": "late"}],
        ]
        for value in invalid:
            with self.subTest(events=value), self.assertRaises(ValueError):
                result_from_events(value, turn_id="1")

    def test_corrupted_saved_result_blocks_new_and_existing_turn(self):
        result = result_from_events(events(), turn_id="1")
        with self.store.session(
            self.owner, self.conversation, "1", completion_result=lambda: result
        ):
            pass
        with self.connect() as connection:
            result["content"]["text"] = "corrupted"
            connection.execute("UPDATE agent_chat_turns SET result=%s", (Jsonb(result),))
        self.assertEqual(
            "NEEDS_REVIEW", self.store.inspect_turn(self.owner, self.conversation, "1")["status"]
        )
        self.assertEqual(
            "NEEDS_REVIEW", self.store.inspect_turn(self.owner, self.conversation, "2")["status"]
        )
        with self.assertRaises(ConversationAdmissionError):
            with self.store.session(
                self.owner,
                self.conversation,
                "2",
                completion_result=lambda: result_from_events(events(), turn_id="2"),
            ):
                self.fail("invalid result must not authorize execution")

    def test_incompatible_native_schema_is_rejected_without_mutating_history(self):
        self.install_incompatible_schema()
        self.old_conversation("saved-old-conversation", "FAILED", "saved-turn")
        with self.assertRaises((ValueError, RuntimeError, ConversationAdmissionError)):
            self.store.setup()
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM agent_conversations").fetchone()
            self.assertEqual("FAILED", row["state"])
            self.assertEqual("saved-turn", row["last_turn_id"])
            self.assertIsNone(
                connection.execute("SELECT to_regclass('agent_chat_turns') AS name").fetchone()[
                    "name"
                ]
            )
            self.assertEqual(
                {"environment", "user_id", "conversation_id", "thread_id", "state", "last_turn_id"},
                {
                    r["column_name"]
                    for r in connection.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name='agent_conversations'",
                        (self.schema,),
                    )
                },
            )

    def test_terminal_result_commit_failure_preserves_review_and_no_retry(self):
        result = result_from_events(events(), turn_id="1")
        with self.connect() as connection:
            connection.execute("""CREATE FUNCTION reject_native_result() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF NEW.state='COMPLETED' THEN RAISE EXCEPTION 'synthetic terminal failure'; END IF;
                RETURN NEW; END $$;
                CREATE TRIGGER reject_native_result BEFORE UPDATE ON agent_chat_turns
                FOR EACH ROW EXECUTE FUNCTION reject_native_result();""")
        with self.assertRaises(psycopg.Error):
            with self.store.session(
                self.owner, self.conversation, "1", completion_result=lambda: result
            ):
                pass
        self.assertEqual(
            "NEEDS_REVIEW", self.store.inspect_turn(self.owner, self.conversation, "1")["status"]
        )
        self.assertEqual(
            "NEEDS_REVIEW", self.store.inspect_turn(self.owner, self.conversation, "2")["status"]
        )
        with self.assertRaises(ConversationAdmissionError):
            with self.store.session(
                self.owner, self.conversation, "1", completion_result=lambda: result
            ):
                self.fail("unknown native outcome cannot be replayed")

    def test_restore_binds_product_ids_and_retains_relationships_without_mutating_native_result(
        self,
    ):
        from a2flow_bside.chat_delivery import restore_content

        result = result_from_events(events(), turn_id="101")
        original = copy.deepcopy(result)
        user = {"id": 101, "role": "user", "content": {"text": "saved"}}
        assistant = {
            "id": 102,
            "role": "assistant",
            "content": {"continuation": {"cardId": "old-card"}, "processingTaskId": "saved-task"},
        }
        content = restore_content(result, input_message=user, assistant_message=assistant)
        self.assertEqual(original, result)
        self.assertEqual("101", content["execution"]["inputMessageId"])
        self.assertEqual("102", content["execution"]["assistantMessageId"])
        self.assertEqual("saved-task", content["processingTaskId"])
        self.assertEqual({"cardId": "old-card"}, content["continuation"])
        self.assertTrue(content["parts"][0]["id"].startswith("text:102:"))
        with self.assertRaises(ValueError):
            restore_content(result, input_message={**user, "id": 103}, assistant_message=assistant)
