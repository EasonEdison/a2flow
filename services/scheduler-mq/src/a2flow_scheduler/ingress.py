"""Validated HTTP boundary; dispatch and status reads use the same control ID."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from typing import Literal

from pydantic import ValidationError

from a2flow_scheduler.contracts import CommandModel, ResumeWorkflow, StartWorkflow
from a2flow_scheduler.delivery import Admission, AdmissionBusy


class CapacityError(CommandModel):
    code: Literal["CAPACITY_EXHAUSTED"]


class CapacityRejection(CommandModel):
    error: CapacityError


class StartRequest(CommandModel):
    requestId: str
    userId: str
    workflowKey: str
    input: str
    environment: str


class ResumeRequest(CommandModel):
    requestId: str
    actionRequestId: str
    userId: str
    environment: str
    nodeId: str
    interactionId: str


class ResumeStatus(CommandModel):
    runId: str
    delivery: Literal["NOT_REQUESTED", "DISPATCHING", "UNCONFIRMED", "RETURNED"]
    resumeConsumed: bool


class BsideCommandClient:
    def __init__(self, base_url: str, token: str) -> None:
        if not base_url.startswith(("https://", "http://")) or not token:
            raise ValueError("INVALID_WORKFLOW_INGRESS_CONFIGURATION")
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _read(self, request: urllib.request.Request) -> Admission:
        return Admission.model_validate_json(self._read_bytes(request))

    def _read_bytes(self, request: urllib.request.Request) -> bytes:
        request.add_header("x-a2flow-internal-token", self.token)
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload: object = response.read()
                if not isinstance(payload, bytes):
                    raise ValueError("INVALID_INGRESS_RESPONSE")
                return payload
        except urllib.error.HTTPError as exc:
            if request.get_method() == "POST" and exc.code == 503:
                try:
                    CapacityRejection.model_validate_json(exc.read(65536))
                except ValidationError:
                    raise exc from None
                raise AdmissionBusy("CAPACITY_EXHAUSTED") from exc
            raise

    def start(self, command: StartWorkflow) -> Admission:
        request = StartRequest(
            requestId=command.message_id,
            userId=str(command.user_id),
            workflowKey=command.workflow_key,
            input=command.input_text,
            environment=command.environment,
        )
        return self._read(
            urllib.request.Request(
                self.base_url + "/api/internal/runs",
                data=request.model_dump_json().encode(),
                method="POST",
            )
        )

    def reconcile(self, command: StartWorkflow | ResumeWorkflow) -> Admission | None:
        if isinstance(command, ResumeWorkflow):
            path = "/api/internal/runs/" + urllib.parse.quote(command.run_id, safe="")
            path += "/cards/" + urllib.parse.quote(command.card_id, safe="") + "/resume-status"
            path += "?" + urllib.parse.urlencode(
                {
                    "userId": str(command.user_id),
                    "environment": command.environment,
                    "nodeId": command.node_id,
                    "interactionId": command.interaction_id,
                    "requestId": command.message_id,
                    "actionRequestId": command.action_request_id,
                }
            )
        else:
            path = "/api/internal/runs/" + urllib.parse.quote(command.message_id, safe="")
        try:
            if isinstance(command, ResumeWorkflow):
                status = ResumeStatus.model_validate_json(
                    self._read_bytes(urllib.request.Request(self.base_url + path))
                )
                if status.runId != command.run_id:
                    raise ValueError("RESUME_STATUS_RUN_ID_MISMATCH")
                if status.delivery == "RETURNED":
                    return Admission(controlRequestId=command.message_id, status="SUBMITTED")
                return None
            return self._read(urllib.request.Request(self.base_url + path))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def resume(self, command: ResumeWorkflow) -> Admission:
        request = ResumeRequest(
            requestId=command.message_id,
            actionRequestId=command.action_request_id,
            userId=str(command.user_id),
            environment=command.environment,
            nodeId=command.node_id,
            interactionId=command.interaction_id,
        )
        path = "/api/internal/runs/" + urllib.parse.quote(command.run_id, safe="")
        path += "/cards/" + urllib.parse.quote(command.card_id, safe="") + "/resume"
        return self._read(
            urllib.request.Request(
                self.base_url + path, data=request.model_dump_json().encode(), method="POST"
            )
        )
