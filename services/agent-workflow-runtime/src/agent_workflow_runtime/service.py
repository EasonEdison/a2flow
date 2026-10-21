"""Transport-neutral service; host-supplied execution sessions own SDK resources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING
from collections.abc import Callable
from contextlib import AbstractContextManager

from skillweave_contracts import TrustedContext
from skillweave_contracts.models import parse_identifier
from skillweave_contracts.validation import ContractValidationError

from .models import ActionRejected, ActionRequest, json_copy
from .native_control import ControlledRunRunner
from .lifecycle import RunLifecycle, RunRecord
from .actions import ActionService

if TYPE_CHECKING:
    from .postgres_progress import PostgresProgress


def require_owner(owner: object) -> TrustedContext:
    if type(owner) is not TrustedContext:
        raise ActionRejected("TRUSTED_CONTEXT_REQUIRED")
    return owner


def identifier(value: object) -> str:
    if type(value) is not str or not value or len(value) > 256:
        raise ActionRejected("INVALID_SERVICE_INPUT")
    return value


def control_identifier(value: object) -> str:
    """Reuse the existing shared control ID contract, not generic asset/input rules."""
    try:
        return parse_identifier(value, path="$.controlRequestId")
    except ContractValidationError:
        raise ActionRejected("INVALID_SERVICE_INPUT") from None


class ProjectionPort(Protocol):
    """Independent committed reads; never enter an execution/admission scope."""

    def run(self, owner: TrustedContext, run_id: str) -> dict[str, Any]: ...
    def control(self, owner: TrustedContext, control_id: str) -> dict[str, Any]: ...
    def restart_identity(self, owner: TrustedContext, run_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ExecutionSession:
    """Trusted context manager yield value, never accepted from an HTTP request.

    The host owns checkpointer connections until the synchronous call ends.
    action_service(run) must bind the same lifecycle and controlled native graph.
    """

    runner: ControlledRunRunner
    action_service: Callable[[RunRecord], ActionService]


class RuntimeService:
    def __init__(
        self, lifecycle: RunLifecycle, projection: ProjectionPort,
        execution_session: Callable[[TrustedContext], AbstractContextManager[ExecutionSession]],
        resolve_entry: Callable[[TrustedContext, str], str],
        *, progress: PostgresProgress | None = None,
        validate_inputs: Callable[[TrustedContext, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.lifecycle = lifecycle
        self.projection = projection
        self.execution_session = execution_session
        self.resolve_entry = resolve_entry
        self.progress = progress
        self.validate_inputs = validate_inputs

    def _runner(self, session: ExecutionSession) -> ControlledRunRunner:
        runner = session.runner
        if not isinstance(runner, ControlledRunRunner) or runner.lifecycle is not self.lifecycle:
            raise ActionRejected("CONTROLLED_SERVICE_BINDING_REQUIRED")
        return runner

    def inspect(self, owner: TrustedContext, run_id: str) -> dict[str, Any]:
        return self.projection.run(require_owner(owner), identifier(run_id))

    def control(self, owner: TrustedContext, control_id: str) -> dict[str, Any]:
        # No execution session, definition resolver, graph, or control lock.
        return self.projection.control(require_owner(owner), control_identifier(control_id))

    def start(self, owner: TrustedContext, control_id: str, definition_key: str, inputs: dict[str, Any]) -> dict[str, Any]:
        require_owner(owner)
        control_identifier(control_id)
        identifier(definition_key)
        if type(inputs) is not dict:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        inputs = json_copy(inputs)
        if self.validate_inputs is not None:
            self.validate_inputs(owner, definition_key, inputs)
        entry = identifier(self.resolve_entry(owner, definition_key))
        with self.execution_session(owner) as session:
            response = self._runner(session).start(
                owner, control_id, definition_key, inputs, entry,
            )
        # Never serialize the runner's checkpoint/thread or business outcome.
        return self.inspect(owner, response["runId"])

    def stop(self, owner: TrustedContext, run_id: str, control_id: str) -> dict[str, Any]:
        require_owner(owner)
        identifier(run_id)
        control_identifier(control_id)
        response = self.lifecycle.stop(owner, run_id, control_id)
        # Stop does not depend on the potentially busy interaction projection.
        return {"runId": response["runId"], "lifecycle": response["status"],
                "delivery": "RETURNED"}

    def restart(self, owner: TrustedContext, run_id: str, control_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        require_owner(owner)
        identifier(run_id)
        control_identifier(control_id)
        if type(inputs) is not dict:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        inputs = json_copy(inputs)
        # A narrow identity read, not old inputs/results/version/checkpoint reuse.
        old = self.projection.restart_identity(owner, run_id)
        definition = identifier(old["definitionKey"])
        if self.validate_inputs is not None:
            self.validate_inputs(owner, definition, inputs)
        entry = identifier(self.resolve_entry(owner, definition))
        with self.execution_session(owner) as session:
            response = self._runner(session).start(
                owner, control_id, definition, inputs, entry, stopped_run_id=run_id,
            )
        return self.inspect(owner, response["runId"])

    def action(self, owner: TrustedContext, run_id: str, node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        require_owner(owner)
        identifier(run_id)
        identifier(node_id)
        if type(payload) is not dict or set(payload) != {
            "interactionId", "actionName", "controlRequestId", "inputs",
        }:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        bound = {**payload, "runId": run_id, "nodeId": node_id}
        control_identifier(bound["controlRequestId"])
        ActionRequest.from_mapping(bound)
        run = self.lifecycle.read(owner, run_id)
        if run.status != "RUNNING":
            raise ActionRejected("RUN_STOPPED" if run.status == "STOPPED" else "RUN_NOT_ACTIVE")
        with self.execution_session(owner) as session:
            runner = self._runner(session)
            runner.action(run, session.action_service(run), bound)
        return self.inspect(owner, run_id)

    def progress_catalog(self, owner: TrustedContext, run_id: str, *, after: str | None = None, limit: int = 100) -> dict[str, Any]:
        require_owner(owner)
        if self.progress is None:
            raise ActionRejected("PROGRESS_UNAVAILABLE")
        return self.progress.catalog(owner, identifier(run_id), after=after, limit=limit)

    def progress_history(self, owner: TrustedContext, run_id: str, node_id: str, execution_id: str, *, after: str | None = None, limit: int = 100) -> dict[str, Any]:
        require_owner(owner)
        if self.progress is None:
            raise ActionRejected("PROGRESS_UNAVAILABLE")
        return self.progress.history(owner, identifier(run_id), identifier(node_id), execution_id,
                                     after=after, limit=limit)
