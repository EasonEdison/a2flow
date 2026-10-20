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
from typing import Any

from pydantic import BaseModel, ConfigDict
from agent_workflow_runtime.chat.cards import CardCompletion
from agent_workflow_runtime.rpc_client import RpcClient
from a2flow_scheduler.contracts import ResumeWorkflow
from a2flow_scheduler.outbox import enqueue_on_card_transaction
from deploy.attended.runtime_events import SchedulerEventSink
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


def create_app_from_environment():
    """Uvicorn factory: reviewed mvp assembly + optional queue event sink."""
    from deploy.mvp import app as mvp
    sink = SchedulerEventSink()
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
        transactional_event_writer=sink.publish,
        # Attended B-side and Runtime use the same database and native Store.
        # Setup belongs to the seed command; never create tables per request.
        personal_memory=PersonalMemory(mvp.conninfo),
    )
    return host.create_app()
