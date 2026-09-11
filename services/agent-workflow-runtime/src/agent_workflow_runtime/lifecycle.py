"""Synchronous run control. Operation facts are an audit ledger, not a scheduler."""

from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
import json
from typing import Protocol
from uuid import uuid4

from skillweave_contracts import TrustedContext, TrustedInvocationContext
from .models import ActionRejected, json_copy


class RunStoppedControl(BaseException):
    """Private control flow, deliberately outside ordinary business Exception retries."""

    def __init__(self, run_id):
        self.run_id = run_id
        super().__init__("RUN_STOPPED")


@dataclass(frozen=True)
class RunRecord:
    owner: TrustedContext
    run_id: str
    thread_id: str
    definition_key: str
    entry_node_id: str
    initial_inputs_json: str
    versions: tuple[tuple[str, str], ...]
    initial_control_id: str
    status: str = "RUNNING"
    revision: int = 0

    def context(self, node_id=None):
        return TrustedInvocationContext.from_mapping({
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
            "trustedContext": self.owner.to_mapping(),
            "invocationScope": {"kind": "WORKFLOW", "runId": self.run_id, "nodeId": self.entry_node_id if node_id is None else node_id},
            "controlRequestId": self.initial_control_id,
        })


@dataclass(frozen=True)
class RunControl:
    control_id: str
    payload_json: str
    run_id: str
    status: str = "DISPATCHING"


@dataclass(frozen=True)
class OperationFact:
    operation_id: str
    node_id: str
    kind: str
    admitted_revision: int
    status: str = "IN_FLIGHT"
    result_json: str | None = None


class RunLifecyclePort(Protocol):
    """All access occurs in a repository-owned short committed transaction.

    run_scope locks the run row; control_scope serializes one trusted control ID.
    No external model/tool/graph call can occur inside either scope. The PG adapter
    uses an independent connection, never an AF03 admission savepoint.
    """

    def run_scope(self, owner, run_id): ...
    def control_scope(self, owner, control_id): ...
    def get_run(self, owner, run_id, *, for_update=False): ...
    def restart_identity(self, owner, run_id): ...
    def put_run(self, run): ...
    def get_control(self, owner, control_id): ...
    def put_control(self, owner, control): ...
    def get_operation(self, owner, run_id, operation_id): ...
    def put_operation(self, owner, run_id, operation): ...
    def operations(self, owner, run_id): ...


def canonical(value):
    return json.dumps(json_copy(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def actual_json(value):
    """Explicit evidence encoding; no pickled or executable result representations."""
    from langchain_core.messages import BaseMessage, message_to_dict
    from langchain_core.outputs import LLMResult
    from langgraph.types import Command, Send
    if isinstance(value, BaseMessage):
        return actual_json(message_to_dict(value))
    if isinstance(value, LLMResult):
        return actual_json(value.model_dump(mode="json"))
    if isinstance(value, Command):
        return {"type": "Command", "update": actual_json(value.update),
                "goto": actual_json(value.goto), "graph": value.graph,
                "resume": actual_json(value.resume)}
    if isinstance(value, Send):
        return {"type": "Send", "node": value.node, "arg": actual_json(value.arg)}
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            raise ActionRejected("INVALID_OPERATION_RESULT")
        return {key: actual_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [actual_json(item) for item in value]
    return json_copy(value)


class RunLifecycle:
    def __init__(self, repository: RunLifecyclePort):
        self.repository = repository
        self._fatal_lock = Lock()
        self._fatals = {}

    def observe_fatal(self, owner, run_id, error):
        if isinstance(error, RunStoppedControl) or isinstance(error, Exception):
            return
        with self._fatal_lock:
            self._fatals.setdefault((owner, run_id), []).append(error)

    def raise_observed_fatal(self, owner, run_id):
        # The synchronous native executor may suppress sibling fatal exceptions
        # when another task failed first. Each owned boundary records them here.
        with self._fatal_lock:
            errors = self._fatals.get((owner, run_id), ())
        if errors:
            raise errors[0]

    @staticmethod
    def _active(run):
        if run is None:
            raise ActionRejected("RUN_NOT_FOUND")
        if run.status == "STOPPED":
            raise RunStoppedControl(run.run_id)
        if run.status != "RUNNING":
            raise ActionRejected("RUN_NOT_ACTIVE")

    def read(self, owner, run_id):
        with self.repository.run_scope(owner, run_id):
            run = self.repository.get_run(owner, run_id)
            if run is None:
                raise ActionRejected("RUN_NOT_FOUND")
            return run

    def assert_active(self, owner, run_id):
        with self.repository.run_scope(owner, run_id):
            self._active(self.repository.get_run(owner, run_id))

    @contextmanager
    def admission(self, owner, run_id, node_id, kind, *, operation_id=None):
        """Reserve ONE actual invocation and commit before the caller dispatches.

        The caller may persist an AF03 EXECUTING record while this short run lock
        is held. That save commits on its independent admission connection. Scope
        exit then commits this fact. No savepoint is advertised as durable.
        """
        with self.repository.run_scope(owner, run_id):
            run = self.repository.get_run(owner, run_id)
            self._active(run)
            fact = OperationFact(operation_id or uuid4().hex, node_id, kind, run.revision)
            if self.repository.get_operation(owner, run_id, fact.operation_id) is not None:
                raise ActionRejected("OPERATION_ID_CONFLICT")
            self.repository.put_operation(owner, run_id, fact)
            yield fact

    def admit(self, owner, run_id, node_id, kind, *, operation_id=None):
        with self.admission(owner, run_id, node_id, kind, operation_id=operation_id) as fact:
            pass
        return fact

    def finish(self, owner, run_id, operation_id, result, *, status="RETURNED"):
        """Save actual outcome even after STOPPED; the first terminal fact is immutable."""
        from dataclasses import replace
        document = canonical(actual_json(result))
        with self.repository.run_scope(owner, run_id):
            fact = self.repository.get_operation(owner, run_id, operation_id)
            if fact is None:
                raise ActionRejected("OPERATION_NOT_FOUND")
            if fact.status != "IN_FLIGHT":
                # E.g. SDK emits on_llm_error after our post-result stop signal.
                return fact
            saved = replace(fact, status=status, result_json=document)
            self.repository.put_operation(owner, run_id, saved)
            return saved

    def execute(self, context, kind, handler):
        scope, owner = context.invocation_scope, context.trusted_context
        if scope.kind != "WORKFLOW":
            raise ActionRejected("WORKFLOW_BINDING_REQUIRED")
        fact = self.admit(owner, scope.run_id, scope.node_id, kind)
        try:
            if kind == "NODE":
                from .progress_observer import observe_node
                with observe_node(context, fact.operation_id):
                    result = handler()
            else:
                result = handler()
        except BaseException as error:
            from langgraph.errors import GraphInterrupt
            self.observe_fatal(owner, scope.run_id, error)
            try:
                self.finish(owner, scope.run_id, fact.operation_id, {"errorType": type(error).__name__},
                            status="INTERRUPTED" if isinstance(error, GraphInterrupt) else "UNCONFIRMED")
            except Exception:
                error.add_note("RUN_OPERATION_FACT_SAVE_UNCONFIRMED")
            raise
        self.finish(owner, scope.run_id, fact.operation_id, result)
        self.assert_active(owner, scope.run_id)
        return result

    def stop(self, owner, run_id, control_id):
        from dataclasses import replace
        payload = canonical({"operation": "STOP", "runId": run_id})
        with self.repository.control_scope(owner, control_id):
            existing = self.repository.get_control(owner, control_id)
            if existing is not None:
                if existing.payload_json != payload:
                    raise ActionRejected("CONTROL_REQUEST_CONFLICT")
            else:
                run = self.repository.get_run(owner, run_id, for_update=True)
                if run is None:
                    raise ActionRejected("RUN_NOT_FOUND")
                if run.status not in {"RUNNING", "STOPPED"}:
                    raise ActionRejected("RUN_ALREADY_TERMINAL")
                if run.status != "STOPPED":
                    self.repository.put_run(replace(run, status="STOPPED", revision=run.revision + 1))
                self.repository.put_control(owner, RunControl(control_id, payload, run_id, "RETURNED"))
        # The response never equates STOPPED to "all in-flight work has finished".
        return self.snapshot(owner, run_id)

    def snapshot(self, owner, run_id):
        with self.repository.run_scope(owner, run_id):
            run = self.repository.get_run(owner, run_id)
            if run is None:
                raise ActionRejected("RUN_NOT_FOUND")
            pending = tuple(f.operation_id for f in self.repository.operations(owner, run_id)
                            if f.status == "IN_FLIGHT" and f.kind in {"MODEL", "TOOL", "ACTION"})
            return {"runId": run_id, "threadId": run.thread_id, "status": run.status,
                    "inFlightCallsStillPending": bool(pending), "inFlightCallCount": len(pending)}

    def succeed(self, owner, run_id):
        from dataclasses import replace
        with self.repository.run_scope(owner, run_id):
            run = self.repository.get_run(owner, run_id)
            self._active(run)
            self.repository.put_run(replace(run, status="SUCCEEDED", revision=run.revision + 1))

    def allocate(self, owner, control_id, definition_key, inputs, entry_node_id, resolve_versions,
                 *, stopped_run_id=None):
        """Fresh stopped-run restart, not a rule freezing every future restart source."""
        payload = canonical({"operation": "RESTART_AFTER_STOP" if stopped_run_id else "START",
                             "stoppedRunId": stopped_run_id, "definitionKey": definition_key,
                             "inputs": inputs, "entryNodeId": entry_node_id})
        with self.repository.control_scope(owner, control_id):
            existing = self.repository.get_control(owner, control_id)
            if existing is not None:
                if existing.payload_json != payload:
                    raise ActionRejected("CONTROL_REQUEST_CONFLICT")
                return self.repository.get_run(owner, existing.run_id), False
            if stopped_run_id is not None:
                old = self.repository.restart_identity(owner, stopped_run_id)
                if old is None:
                    raise ActionRejected("RUN_NOT_FOUND")
                if old["status"] != "STOPPED":
                    raise ActionRejected("RESTART_SOURCE_OUTSIDE_THIS_SLICE")
                if old["definitionKey"] != definition_key:
                    raise ActionRejected("RUN_DEFINITION_MISMATCH")
            versions = tuple(resolve_versions(owner, definition_key))
            if not versions or len(dict(versions)) != len(versions):
                raise ActionRejected("INVALID_RUN_CONFIGURATION")
            run = RunRecord(owner, uuid4().hex, uuid4().hex, definition_key, entry_node_id,
                            canonical(inputs), versions, control_id)
            self.repository.put_run(run)
            self.repository.put_control(owner, RunControl(control_id, payload, run.run_id))
            return run, True

    def control_status(self, owner, control_id, status):
        from dataclasses import replace
        with self.repository.control_scope(owner, control_id):
            control = self.repository.get_control(owner, control_id)
            if control is None:
                raise ActionRejected("CONTROL_NOT_FOUND")
            self.repository.put_control(owner, replace(control, status=status))
