"""Current RPC Workflow host and typed durable scheduler delivery wiring.

Card completion enqueues resume on the card transaction. Lifecycle notifications
use the same database outbox. Import performs no DDL or listener startup.
"""

from __future__ import annotations

import os
import json

import psycopg
from pydantic import SecretStr

from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from agent_workflow_runtime.chat.cards import CardCompletion
from agent_workflow_runtime.events import DomainEvent
from agent_workflow_runtime.rpc_client import RpcClient
from a2flow_scheduler.contracts import NotificationCommand, ResumeWorkflow
from a2flow_scheduler.outbox import PostgresOutbox, enqueue_on_card_transaction
from a2flow_scheduler.persistence import scheduler_engine
from agent_workflow_runtime.workflow_rpc_host import RpcWorkflowHost
from agent_workflow_runtime.internal_identity import private_identity
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.personal_memory import PersonalMemory


class WorkflowBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    runId: str
    nodeId: str


def completed_card(connection: psycopg.Connection[Any], completion: CardCompletion) -> None:
    value = completion.metadata.get("workflow")
    if value is None:
        return
    binding = WorkflowBinding.model_validate(value)
    identity = json.dumps([completion.owner.environment, str(completion.owner.user_id),
                           completion.card_id, completion.request_id])
    enqueue_on_card_transaction(connection, ResumeWorkflow(
        message_id="resume:" + sha256(identity.encode()).hexdigest(),
        user_id=completion.owner.user_id, environment=completion.owner.environment,
        run_id=binding.runId, node_id=binding.nodeId,
        interaction_id=completion.card_id, card_id=completion.card_id,
        action_request_id=completion.request_id,
    ))


class SchedulerEventSink:
    def __init__(self, conninfo: str) -> None:
        self.outbox = PostgresOutbox(scheduler_engine(conninfo))

    def publish(self, event: DomainEvent) -> None:
        names: dict[str, Literal["waiting", "completed", "failed", "stopped"]] = {
            "NODE_WAITING": "waiting", "RUN_FINISHED": "completed",
            "RUN_FAILED": "failed", "RUN_STOPPED": "stopped",
        }
        kind = names.get(event.event_type)
        if kind is None:
            return
        with self.outbox.transaction() as session:
            self.outbox.enqueue(NotificationCommand(
                message_id="event:" + str(event.event_id), user_id=event.user_id,
                run_id=event.run_id, event=kind,
                title={"waiting": "工作流等待操作", "completed": "工作流已完成",
                       "failed": "工作流执行失败", "stopped": "工作流已停止"}[kind],
                body="请查看工作流运行详情。",
            ), session=session)


def create_app_from_environment():
    """Uvicorn factory: reviewed mvp assembly + optional queue event sink."""
    from deploy.mvp import app as mvp
    sink = SchedulerEventSink(mvp.conninfo)
    def configuration(reference, owner):
        if reference != "deepseek-v4-flash" or owner.environment != mvp.environment:
            raise RuntimeError("MODEL_CONFIGURATION_NOT_FOUND")
        return {
            "model_id": reference, "credential_ref": "env:DEEPSEEK_API_KEY",
            "timeout_seconds": 30.0,
            "options": {"thinking": "enabled", "reasoning_effort": "low",
                        "max_tokens": 4096},
        }

    def secret(reference, owner):
        if reference != "env:DEEPSEEK_API_KEY" or owner.environment != mvp.environment:
            raise RuntimeError("MODEL_CREDENTIAL_UNAVAILABLE")
        return SecretStr(mvp.required("DEEPSEEK_API_KEY"))

    class ModelFactory:
        def create(self, reference, owner):
            if owner.environment != mvp.environment:
                raise RuntimeError("MODEL_CONFIGURATION_NOT_FOUND")
            if mvp.compose_mode:
                # Keep the configured shared request budget for every principal.
                return mvp.BoundedDeepSeekFactory(owner).create(reference, owner)
            return DeepSeekModelFactory(configuration, secret).create(reference, owner)

    host = RpcWorkflowHost(
        rpc=RpcClient.from_environment(os.environ),
        completion_observer=completed_card,
        conninfo=mvp.conninfo,
        database=mvp.required("A2FLOW_DATABASE_NAME"),
        environment=mvp.environment,
        namespace=os.environ.get(
            "A2FLOW_ASSET_NAMESPACE", "a2flow-mvp-activity-planning"
        ),
        bundle_validator=mvp.bundle_validator(),
        application_validator=mvp.application_validator,
        operation_specs=mvp.operations(),
        model_factory=ModelFactory(),
        identity_resolver=private_identity(mvp.environment),
        application_data_validator=mvp.application_data_validator,
        static_directory=os.environ.get("A2FLOW_STATIC_DIRECTORY"),
        unexpected_error_observer=mvp.error_observer,
        event_sink=sink,
        # Attended B-side and Runtime use the same database and native Store.
        # Setup belongs to the seed command; never create tables per request.
        personal_memory=PersonalMemory(mvp.conninfo),
    )
    return host.create_app()
