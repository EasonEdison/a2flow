"""Action admission, saved business outcomes and guarded interaction completion."""

from contextlib import nullcontext
from dataclasses import replace
import json

from skillweave_contracts import TrustedContext, TrustedInvocationContext

from .models import ActionRejected, ActionRequest, Attempt, Interaction, json_copy
from .policy import business_succeeded
from .ports import ConfigurationPort, ContinuationPort, ExecutorPort, InteractionRepository


class ActionService:
    """Own Action facts independently of models, transport status and graph replay."""

    def __init__(
        self, repository: InteractionRepository, configuration: ConfigurationPort,
        executor: ExecutorPort, continuation: ContinuationPort, *, lifecycle=None,
    ) -> None:
        self.repository = repository
        self.configuration = configuration
        self.executor = executor
        self.continuation = continuation
        self.lifecycle = lifecycle

    def register(self, interaction: Interaction) -> None:
        """Register one trusted card; replay never replaces history or bindings."""
        scope = interaction.context.invocation_scope
        if scope.kind != "WORKFLOW" or not interaction.graph_thread_id:
            raise ActionRejected("WORKFLOW_BINDING_REQUIRED")
        owner = interaction.context.trusted_context
        self._run_active(owner, scope.run_id)
        with self.repository.scope(owner, scope.run_id):
            existing = self.repository.get(interaction.key, owner)
            if existing is not None:
                if replace(
                    existing, phase=interaction.phase, attempts=interaction.attempts,
                    run_active=interaction.run_active, node_waiting=interaction.node_waiting,
                    completion_request_id=interaction.completion_request_id,
                    resume_started=interaction.resume_started,
                    resume_consumed=interaction.resume_consumed,
                ) != interaction:
                    raise ActionRejected("INTERACTION_BINDING_CONFLICT")
                return
            self.repository.save(interaction)

    def _run_active(self, owner, run_id):
        if self.lifecycle is not None:
            self.lifecycle.assert_active(owner, run_id)

    def _active(self, interaction: Interaction, owner: TrustedContext) -> None:
        self._run_active(owner, interaction.key[0])
        if interaction.context.trusted_context != owner:
            raise ActionRejected("NOT_AUTHORIZED")
        if not interaction.run_active:
            raise ActionRejected("RUN_STOPPED")
        if not interaction.node_waiting or interaction.phase == "INVALIDATED":
            raise ActionRejected("INTERACTION_NOT_WAITING")

    def _get(self, key: tuple[str, str, str], owner: TrustedContext) -> Interaction:
        item = self.repository.get(key, owner)
        if item is None:
            raise ActionRejected("INTERACTION_NOT_FOUND")
        return item

    def submit(self, payload: object, owner: TrustedContext) -> Attempt:
        """Execute once per saved control request; failed/uncertain delivery never reexecutes."""
        request = ActionRequest.from_mapping(payload)
        with self.repository.scope(owner, request.run_id):
            interaction = self._get(request.key, owner)
            self._active(interaction, owner)
            for attempt in interaction.attempts:
                if attempt.request.control_request_id == request.control_request_id:
                    if attempt.request != request:
                        raise ActionRejected("CONTROL_REQUEST_CONFLICT")
                    return replace(attempt, status="EXECUTION_UNCONFIRMED") if attempt.status == "EXECUTING" else attempt
            # DISPATCHING may be healthy in-flight, not a confirmed failure.
            # Reject before writing any reservation for this new request.
            for item in self.repository.for_run(owner, request.run_id):
                if any(
                    a.status in {"EXECUTING", "EXECUTION_UNCONFIRMED"}
                    or a.resume_status in {"DISPATCHING", "UNCONFIRMED"}
                    for a in item.attempts
                ):
                    raise ActionRejected("RUN_OPERATION_PENDING_OR_UNCONFIRMED")
            if interaction.phase != "WAITING":
                raise ActionRejected("INTERACTION_NOT_WAITING")
            config = self.configuration.action(interaction, request.action_name)
            if config.action_name != request.action_name:
                raise ActionRejected("ACTION_NOT_ALLOWED")
            inputs = json.loads(request.inputs_json)
            if config.validate_input(inputs) is not True:
                raise ActionRejected("INVALID_ACTION_INPUT")
            pending = Attempt(request, "EXECUTING")
            gate = (
                self.lifecycle.admission(owner, request.run_id, request.node_id, "ACTION")
                if self.lifecycle is not None else nullcontext(None)
            )
            with gate as run_operation:
                # AF03 commits on its admission connection while the short run
                # transaction is open on ANOTHER connection, not a savepoint.
                self.repository.save(replace(
                    interaction, phase="EXECUTING", attempts=(*interaction.attempts, pending),
                ))
            # Both independent commits finish before external dispatch.
            self.repository.check_scope()
            try:
                result = json_copy(self.executor(config, inputs, owner))
                success = business_succeeded(config, result)
                outcome = Attempt(
                    request, "EXECUTED", success,
                    success and config.completes_interaction,
                    json.dumps(result, allow_nan=False, sort_keys=True),
                )
            except Exception:
                # An exception may occur after a business side effect. Preserve the
                # reservation and never include arbitrary executor exception text.
                outcome = Attempt(request, "EXECUTION_UNCONFIRMED")
            except BaseException as error:
                if self.lifecycle is not None:
                    self.lifecycle.observe_fatal(owner, request.run_id, error)
                    try:
                        self.lifecycle.finish(owner, request.run_id, run_operation.operation_id,
                                              {"errorType": type(error).__name__}, status="UNCONFIRMED")
                    except Exception:
                        error.add_note("RUN_OPERATION_FACT_SAVE_UNCONFIRMED")
                raise
            if self.lifecycle is not None:
                self.lifecycle.finish(
                    owner, request.run_id, run_operation.operation_id,
                    json.loads(outcome.result_json) if outcome.result_json is not None else None,
                    status="RETURNED" if outcome.status == "EXECUTED" else "UNCONFIRMED",
                )
            latest = self._get(request.key, owner)
            self.repository.save(replace(
                latest,
                phase=("COMPLETED" if outcome.interaction_completed else "WAITING")
                if latest.phase != "INVALIDATED" else latest.phase,
                attempts=(*latest.attempts[:-1], outcome),
                completion_request_id=(
                    request.control_request_id if outcome.interaction_completed else None
                ),
            ))
            self._run_active(owner, request.run_id)
            if not outcome.interaction_completed:
                return outcome
            latest = self._get(request.key, owner)
            # Retain late business success even when progression is now prohibited.
            self._active(latest, owner)
            self.repository.save(replace(
                latest, resume_started=True,
                attempts=tuple(
                    replace(attempt, resume_status="DISPATCHING")
                    if attempt.request.control_request_id == request.control_request_id
                    else attempt for attempt in latest.attempts
                ),
            ))
        # Native Tool execution may use another SDK worker thread. Never hold the
        # admission lock across graph invocation; the replayed Tool rechecks the
        # saved claim and active state before returning success.
        with self.repository.continuation_scope(owner, request.run_id):
            try:
                current = self._get(request.key, owner)
                self._active(current, owner)
                self.repository.check_scope()
                self._run_active(owner, request.run_id)
                self.continuation(current, request.control_request_id)
                self.repository.check_scope()
                if self.lifecycle is not None:
                    from .lifecycle import RunStoppedControl
                    if self.lifecycle.read(owner, request.run_id).status == "STOPPED":
                        raise RunStoppedControl(request.run_id)
            except ActionRejected:
                self._delivery_status(request, "UNCONFIRMED", owner)
                raise
            except Exception:
                self._delivery_status(request, "UNCONFIRMED", owner)
                raise ActionRejected("RESUME_UNCONFIRMED") from None
            return self._delivery_status(request, "RETURNED", owner)

    def _delivery_status(self, request: ActionRequest, status: str, owner: TrustedContext) -> Attempt:
        """Persist delivery facts separately from business and completion policy."""
        self.repository.check_scope()
        with self.repository.scope(owner, request.run_id):
            item = self._get(request.key, owner)
            attempts = tuple(
                replace(attempt, resume_status=status)
                if attempt.request.control_request_id == request.control_request_id
                else attempt for attempt in item.attempts
            )
            self.repository.save(replace(item, attempts=attempts))
            return next(a for a in attempts if a.request == request)

    def completion(
        self, key: tuple[str, str, str], value: object,
        owner: TrustedContext,
    ) -> Attempt:
        """Resolve a resume reference against saved facts; ignore all claimed success."""
        if (
            not isinstance(value, dict)
            or set(value) != {"controlRequestId"}
            or not isinstance(value["controlRequestId"], str)
        ):
            raise ActionRejected("INVALID_RESUME_REFERENCE")
        with self.repository.scope(owner, key[0]):
            item = self._get(key, owner)
            self._active(item, owner)
            self._versions(item)
            if (
                item.phase != "COMPLETED" or not item.resume_started
                or item.completion_request_id != value["controlRequestId"]
            ):
                raise ActionRejected("INTERACTION_NOT_COMPLETED")
            for attempt in item.attempts:
                if (
                    attempt.request.control_request_id == item.completion_request_id
                    and attempt.business_success and attempt.interaction_completed
                ):
                    self.repository.save(replace(item, resume_consumed=True))
                    return attempt
            raise ActionRejected("INTERACTION_NOT_COMPLETED")

    def assert_finalizable(self, context: TrustedInvocationContext) -> None:
        """Block terminal model output while any required interaction is unresolved."""
        scope = context.invocation_scope
        if scope.kind != "WORKFLOW":
            return
        self._run_active(context.trusted_context, scope.run_id)
        with self.repository.scope(context.trusted_context, scope.run_id):
            for item in self.repository.for_node(
                context.trusted_context, scope.run_id, scope.node_id,
            ):
                self._versions(item)
                if item.node_waiting:
                    self._active(item, context.trusted_context)
                elif (not item.run_active or item.phase != "COMPLETED"
                      or item.attempts or item.completion_request_id is not None
                      or item.resume_started or not item.resume_consumed):
                    raise ActionRejected("REQUIRED_INTERACTION_PENDING")
                if item.phase != "COMPLETED" or not item.resume_consumed:
                    raise ActionRejected("REQUIRED_INTERACTION_PENDING")
