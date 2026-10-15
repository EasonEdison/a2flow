"""Explicit node-reported attention with saved execution provenance."""
from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, ConfigDict, Field

from .lifecycle import RunRecord
from .models import ActionRejected

DDL = (
    """CREATE TABLE IF NOT EXISTS runtime_workflow_attentions (
        attention_id TEXT PRIMARY KEY, user_id BIGINT NOT NULL,
        environment TEXT NOT NULL, run_id TEXT NOT NULL, node_id TEXT NOT NULL,
        title TEXT NOT NULL, summary TEXT NOT NULL, evidence_refs JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        FOREIGN KEY (user_id,environment,run_id) REFERENCES runtime_runs)""",
    """CREATE INDEX IF NOT EXISTS runtime_workflow_attentions_owner_run
        ON runtime_workflow_attentions(user_id,environment,run_id,created_at)""",
)


class ReportAttentionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=1200)
    evidenceRefs: list[str] = Field(min_length=1, max_length=8)


class WorkflowAttentionReporter:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def report(
        self, run: RunRecord, node_id: str, tool_call_id: str,
        arguments: ReportAttentionArgs, messages: list[Any],
    ) -> dict[str, Any]:
        allowed = {
            "tool:" + message.tool_call_id
            for message in messages
            if isinstance(message, ToolMessage)
            and message.status != "error"
            and message.name in {
                "execute_ability", "render_application", "generate_a2ui", "generate_interaction",
            }
        }
        references = sorted(set(arguments.evidenceRefs))
        if any(reference not in allowed for reference in references):
            raise ActionRejected("ATTENTION_EVIDENCE_NOT_FOUND")
        if not tool_call_id:
            raise ActionRejected("TOOL_CALL_ID_REQUIRED")
        identity = json.dumps([
            run.owner.user_id, run.owner.environment, run.run_id, node_id, tool_call_id,
        ], separators=(",", ":"))
        attention_id = "attention-" + sha256(identity.encode()).hexdigest()
        with psycopg.connect(self._conninfo, row_factory=dict_row, connect_timeout=5,
                             options="-c lock_timeout=5000 -c statement_timeout=10000") as connection:
            row = connection.execute(
                "SELECT document FROM runtime_runs WHERE user_id=%s AND environment=%s "
                "AND run_id=%s FOR UPDATE",
                (run.owner.user_id, run.owner.environment, run.run_id),
            ).fetchone()
            if row is None or row["document"]["status"] != "RUNNING":
                raise ActionRejected("RUN_NOT_RUNNING")
            view = connection.execute(
                "SELECT document FROM runtime_mvp_views WHERE user_id=%s AND environment=%s AND run_id=%s",
                (run.owner.user_id, run.owner.environment, run.run_id),
            ).fetchone()
            if view is None or not any(
                node["nodeId"] == node_id and node["status"] == "RUNNING"
                for node in view["document"]["nodes"]
            ):
                raise ActionRejected("ATTENTION_NODE_NOT_RUNNING")
            connection.execute(
                "INSERT INTO runtime_workflow_attentions "
                "(attention_id,user_id,environment,run_id,node_id,title,summary,evidence_refs) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (attention_id) DO NOTHING",
                (attention_id, run.owner.user_id, run.owner.environment, run.run_id,
                 node_id, arguments.title, arguments.summary, Jsonb(references)),
            )
            saved = connection.execute(
                "SELECT title,summary,evidence_refs FROM runtime_workflow_attentions WHERE attention_id=%s",
                (attention_id,),
            ).fetchone()
            if saved != {"title": arguments.title, "summary": arguments.summary, "evidence_refs": references}:
                raise ActionRejected("ATTENTION_REPLAY_CONFLICT")
        return {"attentionId": attention_id, "reported": True, "runId": run.run_id,
                "nodeId": node_id, "evidenceRefs": references}
