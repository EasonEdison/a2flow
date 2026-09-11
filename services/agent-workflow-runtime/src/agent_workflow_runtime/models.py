"""Internal immutable Action records; identity always comes from backend context."""

from dataclasses import dataclass
import json
from typing import Callable

from skillweave_contracts import TrustedContext, TrustedInvocationContext
from skillweave_contracts.models import (
    JsonPointerEqualsPolicy, ResultInterpretationPolicy, SchemaValidPolicy,
)


class ActionRejected(RuntimeError):
    """Stable non-sensitive admission or delivery failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def json_copy(value: object) -> object:
    """Reject non-JSON data and isolate mutable inputs before external calls."""
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (ValueError, TypeError, RecursionError):
        raise ActionRejected("INVALID_JSON") from None


@dataclass(frozen=True)
class ActionRequest:
    """Closed ingress data, not the unapproved shared Action schema."""

    run_id: str
    node_id: str
    interaction_id: str
    action_name: str
    control_request_id: str
    inputs_json: str

    @classmethod
    def from_mapping(cls, value: object) -> "ActionRequest":
        keys = {
            "runId", "nodeId", "interactionId", "actionName",
            "controlRequestId", "inputs",
        }
        if not isinstance(value, dict) or set(value) != keys:
            raise ActionRejected("INVALID_ACTION_REQUEST")
        for key in keys - {"inputs"}:
            item = value[key]
            if not isinstance(item, str) or not item or len(item) > 256:
                raise ActionRejected("INVALID_ACTION_REQUEST")
        if not isinstance(value["inputs"], dict):
            raise ActionRejected("INVALID_ACTION_INPUT")
        return cls(
            value["runId"], value["nodeId"], value["interactionId"],
            value["actionName"], value["controlRequestId"],
            json.dumps(json_copy(value["inputs"]), sort_keys=True, separators=(",", ":")),
        )

    @property
    def key(self) -> tuple[str, str, str]:
        return self.run_id, self.node_id, self.interaction_id


@dataclass(frozen=True)
class Attempt:
    """Saved control-request history, including execution and delivery uncertainty."""

    request: ActionRequest
    status: str
    business_success: bool = False
    interaction_completed: bool = False
    result_json: str | None = None
    resume_status: str = "NOT_REQUESTED"


@dataclass(frozen=True)
class Interaction:
    """Backend-owned wait binding and history; stores no caller-selected identity."""

    context: TrustedInvocationContext
    interaction_id: str
    application_key: str
    application_version: str
    graph_thread_id: str
    recorded_versions: tuple[tuple[str, str], ...]
    display_json: str | None = None
    phase: str = "WAITING"
    run_active: bool = True
    node_waiting: bool = True
    attempts: tuple[Attempt, ...] = ()
    completion_request_id: str | None = None
    resume_started: bool = False
    resume_consumed: bool = False

    @property
    def key(self) -> tuple[str, str, str]:
        scope = self.context.invocation_scope
        return scope.run_id, scope.node_id, self.interaction_id


@dataclass(frozen=True)
class ActionConfig:
    """Trusted resolved configuration; validators are backend adapters, never input."""

    action_name: str
    operation_ref: str
    effective_versions: tuple[tuple[str, str], ...]
    success_policy: ResultInterpretationPolicy
    completes_interaction: bool
    validate_input: Callable[[object], bool]
    validate_result: Callable[[object], bool]

    def __post_init__(self) -> None:
        if not isinstance(self.success_policy, (JsonPointerEqualsPolicy, SchemaValidPolicy)):
            raise ValueError("unsupported success policy")
        if not callable(self.validate_input) or not callable(self.validate_result):
            raise ValueError("configured validators are required")
        if type(self.completes_interaction) is not bool:
            raise ValueError("completion flag must be a boolean")
        if not self.operation_ref or not self.action_name:
            raise ValueError("Action configuration requires a bound operation")
        keys = [key for key, _ in self.effective_versions]
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("effective version closure must be nonempty and unique")
