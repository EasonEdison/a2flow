"""Action admission, saved business outcomes and guarded interaction completion."""

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
        executor: ExecutorPort, continuation: ContinuationPort,
    ) -> None:
        self.repository = repository
        self.configuration = configuration
        self.executor = executor
        self.continuation = continuation

    def register(self, interaction: Interaction) -> None:
        """Register a trusted wait once; replay never replaces history or bindings."""
        scope = interaction.context.invocation_scope
        if scope.kind != "WORKFLOW" or not interaction.graph_thread_id:
            raise ActionRejected("WORKFLOW_BINDING_REQUIRED")
        owner = interaction.context.trusted_context
        with self.repository.scope(owner, scope.run_id):
            existing = self.repository.get(interaction.key)
            if existing is not None:
                if replace(
                    existing, phase=interaction.phase, attempts=interaction.attempts,
                    run_active=interaction.run_active, node_waiting=interaction.node_waiting,
                    completion_request_id=None, resume_started=False, resume_consumed=False,
                ) != interaction:
                    raise ActionRejected("INTERACTION_BINDING_CONFLICT")
                return
            self._versions(interaction)
            self.repository.save(interaction)

    def _versions(self, interaction: Interaction) -> None:
        recorded = interaction.recorded_versions
        if (
            not recorded
            or len(dict(recorded)) != len(recorded)
            or dict(self.configuration.versions(interaction)) != dict(recorded)
        ):
            raise ActionRejected("RESET_REQUIRED")

    @staticmethod
    def _active(interaction: Interaction, owner: TrustedContext) -> None:
        if interaction.context.trusted_context != owner:
            raise ActionRejected("NOT_AUTHORIZED")
        if not interaction.run_active:
            raise ActionRejected("RUN_STOPPED")
        if not interaction.node_waiting or interaction.phase == "INVALIDATED":
            raise ActionRejected("INTERACTION_NOT_WAITING")

    def _get(self, key: tuple[str, str, str]) -> Interaction:
        item = self.repository.get(key)
        if item is None:
            raise ActionRejected("INTERACTION_NOT_FOUND")
        return item

    def submit(self, payload: object, owner: TrustedContext) -> Attempt:
        """Execute once per saved control request; failed/uncertain delivery never reexecutes."""
        request = ActionRequest.from_mapping(payload)
        with self.repository.scope(owner, request.run_id):
            interaction = self._get(request.key)
            self._active(interaction, owner)
            self._versions(interaction)
            for attempt in interaction.attempts:
                if attempt.request.control_request_id == request.control_request_id:
                    if attempt.request != request:
                        raise ActionRejected("CONTROL_REQUEST_CONFLICT")
                    return attempt
            if interaction.phase != "WAITING":
                raise ActionRejected("INTERACTION_NOT_WAITING")
            config = self.configuration.action(interaction, request.action_name)
            if config.action_name != request.action_name:
                raise ActionRejected("ACTION_NOT_ALLOWED")
            if dict(config.effective_versions) != dict(interaction.recorded_versions):
                raise ActionRejected("RESET_REQUIRED")
            inputs = json.loads(request.inputs_json)
            if config.validate_input(inputs) is not True:
                raise ActionRejected("INVALID_ACTION_INPUT")
            # Last current-version check after all configuration/input validation.
            self._versions(interaction)
            pending = Attempt(request, "EXECUTING")
            self.repository.save(replace(
                interaction, phase="EXECUTING", attempts=(*interaction.attempts, pending),
            ))
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
            latest = self._get(request.key)
            self.repository.save(replace(
                latest,
                phase=("COMPLETED" if outcome.interaction_completed else "WAITING")
                if latest.phase != "INVALIDATED" else latest.phase,
                attempts=(*latest.attempts[:-1], outcome),
                completion_request_id=(
                    request.control_request_id if outcome.interaction_completed else None
                ),
            ))
            if not outcome.interaction_completed:
                return outcome
            latest = self._get(request.key)
            # Retain late business success even when progression is now prohibited.
            self._active(latest, owner)
            self._versions(latest)
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
        # saved claim, active state and versions before returning success.
        with self.repository.continuation_scope(owner, request.run_id):
            try:
                current = self._get(request.key)
                self._active(current, owner)
                self._versions(current)
                self.continuation(current, request.control_request_id)
            except ActionRejected:
                self._delivery_status(request, "UNCONFIRMED")
                raise
            except Exception:
                self._delivery_status(request, "UNCONFIRMED")
                raise ActionRejected("RESUME_UNCONFIRMED") from None
        return self._delivery_status(request, "RETURNED")

    def _delivery_status(self, request: ActionRequest, status: str) -> Attempt:
        """Persist delivery facts separately from business and completion policy."""
        owner = self._get(request.key).context.trusted_context
        with self.repository.scope(owner, request.run_id):
            item = self._get(request.key)
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
            item = self._get(key)
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
        for item in self.repository.for_node(
            context.trusted_context, scope.run_id, scope.node_id,
        ):
            self._active(item, context.trusted_context)
            self._versions(item)
            if item.phase != "COMPLETED" or not item.resume_consumed:
                raise ActionRejected("REQUIRED_INTERACTION_PENDING")
