"""Single-attempt command admission and read-only ambiguity reconciliation."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import ConfigDict

from a2flow_scheduler.contracts import (
    CommandModel,
    NotificationCommand,
    ResumeWorkflow,
    StartWorkflow,
)
from a2flow_scheduler.outbox import PostgresOutbox
from a2flow_scheduler.streams import RedisStreamTransport, StreamChannel


class Admission(CommandModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)
    controlRequestId: str
    status: Literal["SUBMITTED"]


class WorkflowIngress(Protocol):
    def start(self, command: StartWorkflow) -> Admission: ...
    def resume(self, command: ResumeWorkflow) -> Admission: ...
    def reconcile(self, command: StartWorkflow | ResumeWorkflow) -> Admission | None: ...


class NotificationSender(Protocol):
    def send_notification(self, command: NotificationCommand) -> None: ...


def consume_one(
    outbox: PostgresOutbox,
    transport: RedisStreamTransport,
    channel: StreamChannel,
    ingress: WorkflowIngress,
    sender: NotificationSender | None = None,
) -> bool:
    delivery = transport.receive(channel)
    if delivery is None:
        return False
    command = outbox.claim(delivery.message_id)
    if command is None:
        # Duplicate refs carry no authority to repeat a dispatch. Durable state owns recovery.
        transport.acknowledge(delivery)
        return True
    try:
        if isinstance(command, StartWorkflow):
            accepted = ingress.start(command)
            if accepted.controlRequestId != command.message_id:
                raise ValueError("CONTROL_REQUEST_ID_MISMATCH")
        elif isinstance(command, ResumeWorkflow):
            accepted = ingress.resume(command)
            if accepted.controlRequestId != command.message_id:
                raise ValueError("CONTROL_REQUEST_ID_MISMATCH")
        elif isinstance(command, NotificationCommand):
            with outbox.connection.transaction():
                outbox.connection.execute(
                    "INSERT INTO notifications "
                    "(user_id,kind,title,body,ref_type,ref_id,idempotency_key) "
                    "VALUES (%s,%s,%s,%s,'run',%s,%s) ON CONFLICT (idempotency_key) DO NOTHING",
                    (
                        command.user_id,
                        command.event,
                        command.title,
                        command.body,
                        command.run_id,
                        command.message_id,
                    ),
                )
            if sender is not None:
                sender.send_notification(command)
    except Exception:
        # Includes HTTP ambiguity and external notification ambiguity. No business retry.
        outbox.finish(command.message_id, "unknown", "DELIVERY_UNCONFIRMED")
    else:
        outbox.finish(command.message_id, "completed")
    transport.acknowledge(delivery)
    return True


def reconcile_unknown(outbox: PostgresOutbox, ingress: WorkflowIngress) -> None:
    for command in outbox.uncertain_workflows():
        if isinstance(command, NotificationCommand):
            continue
        try:
            admission = ingress.reconcile(command)
            if admission is not None and admission.controlRequestId == command.message_id:
                outbox.finish(command.message_id, "completed")
        except Exception:
            # Keep actionable durable UNKNOWN until a read proves admission.
            continue
