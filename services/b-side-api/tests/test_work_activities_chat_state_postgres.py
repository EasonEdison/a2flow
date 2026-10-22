"""Real SQL read/processing closure over synthetic facts; no model or business IO."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg
from a2flow_bside.chat_wake import ChatWake
from a2flow_bside.durable_chat import DurableChat
from a2flow_bside.errors import BsideError
from a2flow_bside.notification_repository import NotificationsRepository
from a2flow_bside.processing_tasks import ProcessingTasksRepository
from a2flow_bside.work_activities import WorkActivitiesRepository
from agent_workflow_runtime.chat.cards import DDL as CHAT_CARD_DDL
from agent_workflow_runtime.lifecycle import (
    OperationFact,
    RunControl,
    RunRecord,
    actual_json,
    canonical,
)
from agent_workflow_runtime.postgres import DDL as INTERACTION_DDL
from agent_workflow_runtime.postgres_lifecycle import DDL as RUN_DDL
from agent_workflow_runtime.postgres_lifecycle import encode_record
from agent_workflow_runtime.ui_projection import DDL as VIEW_DDL
from agent_workflow_runtime.ui_projection import change_node, initial_view, put_output
from agent_workflow_runtime.workflow_attention import DDL as ATTENTION_DDL
from langchain_core.messages import ToolMessage
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from skillweave_contracts import TrustedContext
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(os.environ.get("A2FLOW_CONVERGENCE_DSN"), "disposable PostgreSQL required")
class WorkActivitiesChatStateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dsn = os.environ["A2FLOW_CONVERGENCE_DSN"]
        self.schema = "activity_chat_state_" + uuid4().hex
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        # Use the shipping DDL; no hand-written replacement schema hides join errors.
        with self.factory() as connection:
            connection.execute(
                (ROOT / "services/b-side-api/src/a2flow_bside/schema.sql").read_text()
            )
            for statement in (
                *RUN_DDL,
                *INTERACTION_DDL,
                *VIEW_DDL,
                *ATTENTION_DDL,
                *CHAT_CARD_DDL,
            ):
                connection.execute(statement)
            connection.execute(
                (ROOT / "services/scheduler-mq/src/a2flow_scheduler/schema.sql").read_text()
            )
        self.activities = WorkActivitiesRepository(self.factory)
        self.processing = ProcessingTasksRepository(self.factory, self.activities)
        self.wake = ChatWake()
        self.addCleanup(self.wake.close)
        self.durable = DurableChat(self.factory, environment="PRT", wake=self.wake)
        self.seed_workflow()

    def factory(self):
        return psycopg.connect(
            self.dsn, row_factory=dict_row, options="-c search_path=" + self.schema
        )

    def drop_schema(self):
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )

    def seed_workflow(self):
        self.run_id = "synthetic-workflow-run"
        self.control_id = "synthetic-scheduled-control"
        self.attention_id = "synthetic-business-attention"
        run = RunRecord(
            owner=TrustedContext(1, "PRT"),
            run_id=self.run_id,
            thread_id="synthetic-thread",
            definition_key="synthetic-anomaly-review",
            entry_node_id="query",
            initial_inputs_json=canonical({"synthetic": True}),
            versions=(("WORKFLOW:synthetic-anomaly-review", "v1"),),
            initial_control_id=self.control_id,
            status="SUCCEEDED",
            revision=3,
        )
        control = RunControl(self.control_id, run.initial_inputs_json, self.run_id, "RETURNED")
        tool = ToolMessage(
            name="execute_ability",
            tool_call_id="synthetic-query-call",
            content=canonical({"synthetic": True, "success": True, "needsReview": True}),
        )
        fact = OperationFact(
            "synthetic-query-operation",
            "query",
            "TOOL",
            1,
            "RETURNED",
            canonical(actual_json(tool)),
        )
        view = initial_view(
            run,
            {
                "displayName": "Synthetic anomaly review",
                "nodes": [{"nodeId": "query", "skillKey": "synthetic-query"}],
            },
            run.versions,
        )
        change_node(view, "query", "SUCCEEDED", "Synthetic query returned")
        put_output(view, "query", "MODEL_TEXT", "Synthetic result requires manual review")
        with self.factory() as connection:
            connection.execute(
                "INSERT INTO users(user_id,username,password_hash) VALUES(1,'synthetic-user','synthetic-disabled-login')"
            )
            self.cid = connection.execute(
                "INSERT INTO conversations(user_id,title) VALUES(1,'Synthetic follow-up') RETURNING id"
            ).fetchone()["id"]
            connection.execute(
                "INSERT INTO runtime_runs VALUES(%s,%s,%s,%s,%s)",
                (1, "PRT", self.run_id, run.thread_id, Jsonb(encode_record(run))),
            )
            connection.execute(
                "INSERT INTO runtime_run_controls VALUES(%s,%s,%s,%s)",
                (1, "PRT", self.control_id, Jsonb(encode_record(control))),
            )
            connection.execute(
                "INSERT INTO runtime_operation_facts VALUES(%s,%s,%s,%s,%s)",
                (1, "PRT", self.run_id, fact.operation_id, Jsonb(encode_record(fact))),
            )
            connection.execute(
                "INSERT INTO runtime_mvp_views(user_id,environment,run_id,catalog_seq,revision,document) "
                "VALUES(1,'PRT',%s,1,3,%s)",
                (self.run_id, Jsonb(view)),
            )
            connection.execute(
                "INSERT INTO runtime_workflow_attentions(attention_id,user_id,environment,run_id,node_id,title,summary,evidence_refs) "
                "VALUES(%s,1,'PRT',%s,'query','Synthetic anomaly','Synthetic review needed',%s)",
                (self.attention_id, self.run_id, Jsonb(["tool:synthetic-query-call"])),
            )
            connection.execute(
                "INSERT INTO run_ownership(control_id,user_id,workflow_key,run_id,environment,source_type) "
                "VALUES(%s,1,%s,%s,'PRT','manual')",
                (self.control_id, run.definition_key, self.run_id),
            )
            connection.execute(
                "INSERT INTO scheduler_outbox(message_id,channel,payload,state) VALUES(%s,'workflow',%s,'completed')",
                (
                    self.control_id,
                    Jsonb(
                        {
                            "kind": "start_workflow",
                            "user_id": "1",
                            "environment": "PRT",
                            "schedule_id": "synthetic-plan",
                            "scheduled_at": "2026-10-22T01:00:00+00:00",
                        }
                    ),
                ),
            )
            self.notification_id = connection.execute(
                "INSERT INTO notifications(user_id,kind,title,body,ref_type,ref_id,idempotency_key) "
                "VALUES(1,'workflow_attention','Synthetic notification','Synthetic only','run',%s,'synthetic-notification') RETURNING id",
                (self.run_id,),
            ).fetchone()["id"]

    def begin_turn(self, request_id="synthetic-processing-1", task_id=None):
        reference = self.activities.get_result(
            user_id=1, environment="PRT", activity_id=self.control_id
        )
        return self.processing.begin_turn(
            user_id=1,
            environment="PRT",
            conversation_id=str(self.cid),
            request_id=request_id,
            text="Review synthetic anomaly",
            references=[reference],
            target={"activityId": self.control_id, "attentionId": self.attention_id}
            if task_id is None
            else None,
            task_id=task_id,
            client_request_id="client:" + request_id,
            client_payload={"text": "Review synthetic anomaly", "processingRequestId": request_id},
        )

    def finish_turn(self, user, assistant):
        generation = self.durable.claim_generation(user["id"])
        self.durable.save_projection(
            user["id"],
            generation,
            conversation_id=self.cid,
            message_id=assistant["id"],
            content={
                **assistant["content"],
                "text": "Synthetic follow-up complete",
                "delivery": "completed",
            },
        )

    def attention(self, activity):
        return next(a for a in activity["attentionItems"] if a["attentionId"] == self.attention_id)

    async def test_activity_sql_links_latest_turn_receipt_and_explicit_resolution(self):
        baseline = self.activities.get_result(
            user_id=1, environment="PRT", activity_id=self.control_id
        )
        self.assertEqual("scheduled", baseline["sourceType"])
        self.assertEqual("SUCCEEDED", baseline["runStatus"])
        self.assertEqual("AVAILABLE", baseline["attentionEvidence"][0]["availability"])
        self.assertTrue(
            json.loads(json.loads(baseline["resultPage"])["attentionEvidence"][0]["toolResult"])[
                "synthetic"
            ]
        )
        created, context, user, assistant = self.begin_turn()
        self.assertTrue(created)
        task_id = context["taskId"]
        calls = []

        def synthetic_receipt(request_id):
            calls.append(request_id)
            return {
                "synthetic": True,
                "success": True,
                "requestId": request_id,
                "actionCode": "synthetic.review.read",
                "resolvedEnvironment": "PRT",
                "data": {"reviewed": True},
            }

        envelope = self.processing.execute_operation(
            user_id=1,
            environment="PRT",
            conversation_id=str(self.cid),
            task_id=task_id,
            turn_id=str(user["id"]),
            tool_call_id="synthetic-follow-up-call",
            ability_key="synthetic.review.read",
            arguments={"synthetic": True},
            invoke=synthetic_receipt,
        )
        self.assertEqual("RETURNED", envelope["status"])
        self.assertEqual(1, len(calls))
        self.finish_turn(user, assistant)
        item = self.activities.get(user_id=1, environment="PRT", activity_id=self.control_id)
        task = self.attention(item)["processingTasks"][0]
        self.assertEqual(
            (task_id, "RESULT_RECORDED", "completed"),
            (task["taskId"], task["status"], task["deliveryStatus"]),
        )
        listing = self.activities.list_runs(user_id=1, environment="PRT", group="attention")
        self.assertEqual(task, self.attention(listing["items"][0])["processingTasks"][0])
        result = self.activities.get_result(
            user_id=1, environment="PRT", activity_id=self.control_id
        )
        saved_task = json.loads(result["resultPage"])["processingTasks"][0]
        self.assertEqual(task_id, saved_task["taskId"])
        self.assertEqual(envelope["result"], saved_task["operations"][0]["result"])
        self.assertNotEqual(baseline["resultRevision"], result["resultRevision"])
        # A newer unfinished turn blocks resolution even when the earlier one completed.
        _, _, next_user, next_assistant = self.begin_turn("synthetic-processing-2", task_id)
        self.assertEqual(
            "running",
            self.processing.get(user_id=1, environment="PRT", task_id=task_id)["deliveryStatus"],
        )
        with self.assertRaises(BsideError) as blocked:
            self.processing.resolve(
                user_id=1, environment="PRT", task_id=task_id, summary="Synthetic review resolved"
            )
        self.assertEqual("PROCESSING_RESULT_NOT_CONFIRMED", blocked.exception.code)
        self.finish_turn(next_user, next_assistant)
        resolved = self.processing.resolve(
            user_id=1, environment="PRT", task_id=task_id, summary="Synthetic review resolved"
        )
        self.assertEqual("RESOLVED", resolved["status"])
        result = self.activities.get_result(
            user_id=1, environment="PRT", activity_id=self.control_id
        )
        task = json.loads(result["resultPage"])["processingTasks"][0]
        self.assertEqual("RESOLVED", task["status"])
        self.assertEqual("Synthetic review resolved", task["resolutionSummary"])
        self.assertEqual(envelope["result"], task["operations"][0]["result"])
        self.assertEqual(1, len(calls))

    async def test_notification_read_and_attention_ack_do_not_resolve_source_task(self):
        _, context, user, _ = self.begin_turn()
        engine = create_engine(
            "postgresql+psycopg://",
            poolclass=NullPool,
            hide_parameters=True,
            creator=lambda: psycopg.connect(self.dsn, options="-c search_path=" + self.schema),
        )
        self.addCleanup(engine.dispose)
        notifications = NotificationsRepository(engine)
        first = notifications.list_for(1)[0]
        self.assertEqual(self.control_id, first.ref_id)
        self.assertFalse(first.read)
        self.assertEqual([], notifications.list_for(2))
        self.assertFalse(notifications.mark_read(self.notification_id, 2))
        self.assertTrue(notifications.mark_read(self.notification_id, 1))
        self.assertTrue(notifications.list_for(1)[0].read)
        activity = self.activities.get(user_id=1, environment="PRT", activity_id=self.control_id)
        self.assertFalse(self.attention(activity)["acknowledged"])
        self.activities.acknowledge(
            user_id=1,
            environment="PRT",
            activity_id=self.control_id,
            attention_id=self.attention_id,
        )
        activity = self.activities.get(user_id=1, environment="PRT", activity_id=self.control_id)
        self.assertTrue(self.attention(activity)["acknowledged"])
        self.assertEqual("SUCCEEDED", activity["runStatus"])
        task = self.processing.get(user_id=1, environment="PRT", task_id=context["taskId"])
        self.assertEqual("OPEN", task["status"])
        self.assertIsNone(task["resolvedAt"])
        self.assertEqual([], task["operations"])
        self.assertEqual("QUEUED", self.durable.get(user["id"])["status"])
        with self.assertRaises(BsideError):
            self.processing.resolve(
                user_id=1,
                environment="PRT",
                task_id=context["taskId"],
                summary="Synthetic read only",
            )
        with self.assertRaises(BsideError):
            self.activities.get(user_id=2, environment="PRT", activity_id=self.control_id)
        with self.assertRaises(BsideError):
            self.activities.get(user_id=1, environment="ONLINE", activity_id=self.control_id)
