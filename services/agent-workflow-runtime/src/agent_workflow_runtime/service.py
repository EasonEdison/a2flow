"""Transport-neutral service; host-supplied execution sessions own SDK resources."""

from dataclasses import dataclass
from typing import Protocol

from skillweave_contracts import TrustedContext

from .models import ActionRejected, ActionRequest, json_copy
from .native_control import ControlledRunRunner


def require_owner(owner):
    if type(owner) is not TrustedContext:
        raise ActionRejected("TRUSTED_CONTEXT_REQUIRED")
    return owner


def identifier(value):
    if type(value) is not str or not value or len(value) > 256:
        raise ActionRejected("INVALID_SERVICE_INPUT")
    return value


class ProjectionPort(Protocol):
    """Independent committed reads; never enter an execution/admission scope."""

    def run(self, owner, run_id): ...
    def control(self, owner, control_id): ...
    def restart_identity(self, owner, run_id): ...


@dataclass(frozen=True)
class ExecutionSession:
    """Trusted context manager yield value, never accepted from an HTTP request.

    The host owns checkpointer connections until the synchronous call ends.
    action_service(run) must bind the same lifecycle and controlled native graph.
    """

    runner: ControlledRunRunner
    action_service: object


class RuntimeService:
    def __init__(self, lifecycle, projection: ProjectionPort, execution_session, resolve_entry):
        self.lifecycle = lifecycle
        self.projection = projection
        self.execution_session = execution_session
        self.resolve_entry = resolve_entry

    def _runner(self, session):
        runner = session.runner
        if not isinstance(runner, ControlledRunRunner) or runner.lifecycle is not self.lifecycle:
            raise ActionRejected("CONTROLLED_SERVICE_BINDING_REQUIRED")
        return runner

    def inspect(self, owner, run_id):
        return self.projection.run(require_owner(owner), identifier(run_id))

    def control(self, owner, control_id):
        # No execution session, definition resolver, graph, or control lock.
        return self.projection.control(require_owner(owner), identifier(control_id))

    def start(self, owner, control_id, definition_key, inputs):
        require_owner(owner)
        identifier(control_id)
        identifier(definition_key)
        if type(inputs) is not dict:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        inputs = json_copy(inputs)
        entry = identifier(self.resolve_entry(owner, definition_key))
        with self.execution_session(owner) as session:
            response = self._runner(session).start(
                owner, control_id, definition_key, inputs, entry,
            )
        # Never serialize the runner's checkpoint/thread or business outcome.
        return self.inspect(owner, response["runId"])

    def stop(self, owner, run_id, control_id):
        require_owner(owner)
        identifier(run_id)
        identifier(control_id)
        response = self.lifecycle.stop(owner, run_id, control_id)
        # Stop does not depend on the potentially busy interaction projection.
        return {"runId": response["runId"], "lifecycle": response["status"],
                "delivery": "RETURNED"}

    def restart(self, owner, run_id, control_id, inputs):
        require_owner(owner)
        identifier(run_id)
        identifier(control_id)
        if type(inputs) is not dict:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        inputs = json_copy(inputs)
        # A narrow identity read, not old inputs/results/version/checkpoint reuse.
        old = self.projection.restart_identity(owner, run_id)
        definition = identifier(old["definitionKey"])
        entry = identifier(self.resolve_entry(owner, definition))
        with self.execution_session(owner) as session:
            response = self._runner(session).start(
                owner, control_id, definition, inputs, entry, stopped_run_id=run_id,
            )
        return self.inspect(owner, response["runId"])

    def action(self, owner, run_id, node_id, payload):
        require_owner(owner)
        identifier(run_id)
        identifier(node_id)
        if type(payload) is not dict or set(payload) != {
            "interactionId", "actionName", "controlRequestId", "inputs",
        }:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        bound = {**payload, "runId": run_id, "nodeId": node_id}
        ActionRequest.from_mapping(bound)
        run = self.lifecycle.read(owner, run_id)
        if run.status != "RUNNING":
            raise ActionRejected("RUN_STOPPED" if run.status == "STOPPED" else "RUN_NOT_ACTIVE")
        with self.execution_session(owner) as session:
            runner = self._runner(session)
            runner.action(run, session.action_service(run), bound)
        return self.inspect(owner, run_id)
