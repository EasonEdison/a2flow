"""Validated HTTP boundary; dispatch and status reads use the same control ID."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

from a2flow_scheduler.contracts import CommandModel, ResumeWorkflow, StartWorkflow
from a2flow_scheduler.delivery import Admission


class StartRequest(CommandModel):
    requestId: str
    userId: str
    workflowKey: str
    input: str
    environment: str


class ResumeRequest(CommandModel):
    requestId: str
    userId: str
    environment: str
    nodeId: str
    interactionId: str


class BsideCommandClient:
    def __init__(self, base_url: str, token: str) -> None:
        if not base_url.startswith(("https://", "http://")) or not token:
            raise ValueError("INVALID_WORKFLOW_INGRESS_CONFIGURATION")
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _read(self, request: urllib.request.Request) -> Admission:
        request.add_header("x-a2flow-internal-token", self.token)
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=15) as response:
            return Admission.model_validate_json(response.read())

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
            path = "/api/internal/run-controls/" + urllib.parse.quote(command.message_id, safe="")
            path += "?" + urllib.parse.urlencode(
                {"userId": str(command.user_id), "environment": command.environment}
            )
        else:
            path = "/api/internal/runs/" + urllib.parse.quote(command.message_id, safe="")
        try:
            return self._read(urllib.request.Request(self.base_url + path))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def resume(self, command: ResumeWorkflow) -> Admission:
        request = ResumeRequest(
            requestId=command.message_id,
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
