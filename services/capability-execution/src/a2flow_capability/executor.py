"""Fail-closed orchestration for immutable published capability plans."""

from __future__ import annotations

from a2flow_capability.bindings import bind_request
from a2flow_capability.models import (
    CapabilityExecutionError,
    CapabilityTransport,
    CapabilityTransportError,
    ExecutionErrorCode,
    ExecutionResult,
    JsonObject,
    JsonValue,
    PreparedExecution,
    PublishedPlan,
    TrustedContext,
)


class CapabilityExecutor:
    """Validate, bind and execute one published gRPC capability plan."""

    def __init__(self, transport: CapabilityTransport) -> None:
        self._transport = transport

    def prepare(
        self, plan: PublishedPlan, arguments: JsonObject, context: TrustedContext
    ) -> PreparedExecution:
        """Build a transient, credential-free preview without calling transport."""
        self._validate_environment(plan, context)
        effective_arguments, business_request = bind_request(plan, arguments, context)
        return PreparedExecution(
            effective_arguments=effective_arguments,
            business_request=business_request,
        )

    def execute(
        self, plan: PublishedPlan, arguments: JsonObject, context: TrustedContext
    ) -> ExecutionResult:
        """Return Java-compatible stable result semantics without business-code guessing."""
        try:
            self._validate_runtime_client(plan, context)
            prepared = self.prepare(plan, arguments, context)
            data = self._transport.execute(plan, prepared.business_request, context)
            return self._result(plan, context, success=True, data=data)
        except CapabilityExecutionError as failure:
            return self._result(
                plan,
                context,
                success=False,
                error_code=failure.code,
                message=failure.detail,
            )
        except CapabilityTransportError as failure:
            return self._result(
                plan,
                context,
                success=False,
                error_code=failure.code,
                message=failure.detail,
            )
        except TimeoutError:
            return self._result(
                plan,
                context,
                success=False,
                error_code=ExecutionErrorCode.TRANSPORT_TIMEOUT,
                message="gRPC execution timed out",
            )
        except Exception:
            return self._result(
                plan,
                context,
                success=False,
                error_code=ExecutionErrorCode.TRANSPORT_ERROR,
                message="gRPC execution failed",
            )

    @staticmethod
    def _validate_environment(plan: PublishedPlan, context: TrustedContext) -> None:
        if context.environment is not plan.resolved_environment:
            raise CapabilityExecutionError(
                ExecutionErrorCode.RELEASE_ENVIRONMENT_INVALID,
                "cross-environment capability fallback is forbidden",
            )

    @staticmethod
    def _validate_runtime_client(plan: PublishedPlan, context: TrustedContext) -> None:
        if context.client not in {"PC", "APP"} or plan.client_type != context.client:
            raise CapabilityExecutionError(
                ExecutionErrorCode.CAPABILITY_CLIENT_NOT_SUPPORTED,
                "runtime client does not match the published capability contract",
            )

    @staticmethod
    def _result(
        plan: PublishedPlan,
        context: TrustedContext,
        *,
        success: bool,
        data: JsonValue = None,
        error_code: ExecutionErrorCode | None = None,
        message: str | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            success=success,
            action_code=plan.action_code,
            source_id=plan.source_id,
            source_digest=plan.source_digest,
            capability_version=plan.capability_version,
            client_type=plan.client_type,
            requested_environment=context.environment,
            resolved_environment=plan.resolved_environment,
            request_id=context.request_id,
            data=data if success else None,
            error_code=error_code,
            message=message,
        )
