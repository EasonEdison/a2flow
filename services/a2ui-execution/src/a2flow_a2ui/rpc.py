"""Typed gRPC adapter for the existing A2uiExecution contract."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TypeVar, cast

import grpc
from a2flow.a2ui.v1 import a2ui_pb2, a2ui_pb2_grpc
from a2flow.capability.v1 import capability_pb2
from a2flow_capability.models import (
    CapabilityExecutionError,
    Environment,
    JsonObject,
    JsonValue,
    TrustedContext,
)
from a2flow_capability.releases import ReleaseError, ReleaseStorageError
from a2flow_capability.rpc import json_value, parse_object, unique_object

from .models import (
    A2uiError,
    ApplicationRelease,
    PublishedApplication,
    RuntimeResult,
    RuntimeSession,
    TrustedCard,
)
from .runtime import A2uiRuntimeService

Response = TypeVar("Response")
LOG = logging.getLogger(__name__)


def _json(value: JsonValue) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _object(value: bytes) -> JsonObject:
    try:
        return parse_object(value)
    except (UnicodeError, ValueError, RecursionError):
        raise A2uiError("A2UI_REQUEST_JSON_INVALID") from None


def _messages(value: bytes) -> tuple[JsonObject, ...]:
    try:
        parsed = json_value(json.loads(value, object_pairs_hook=unique_object))
    except (UnicodeError, ValueError, RecursionError):
        raise A2uiError("A2UI_REQUEST_JSON_INVALID") from None
    if not isinstance(parsed, list) or any(not isinstance(item, dict) for item in parsed):
        raise A2uiError("A2UI_REQUEST_JSON_INVALID")
    return tuple(cast(JsonObject, item) for item in parsed)


def _environment(value: int) -> Environment:
    if value == capability_pb2.PRT:
        return Environment.PRT
    if value == capability_pb2.ONLINE:
        return Environment.ONLINE
    raise A2uiError("A2UI_ENVIRONMENT_REQUIRED")


def _context(value: capability_pb2.ExecutionContext) -> TrustedContext:
    if not value.HasField("user_id"):
        raise A2uiError("A2UI_TRUSTED_CONTEXT_REQUIRED")
    try:
        return TrustedContext(
            value.user_id, _environment(value.environment), value.request_id, value.client
        )
    except (CapabilityExecutionError, TypeError, ValueError):
        raise A2uiError("A2UI_TRUSTED_CONTEXT_REQUIRED") from None


def _release(value: ApplicationRelease) -> a2ui_pb2.ApplicationRelease:
    environment = (
        capability_pb2.PRT if value.environment is Environment.PRT else capability_pb2.ONLINE
    )
    return a2ui_pb2.ApplicationRelease(
        app_code=value.app_code,
        source_id=value.source_id,
        digest=value.digest,
        app_build_id=value.app_build_id,
        environment=environment,
    )


def _release_model(value: a2ui_pb2.ApplicationRelease) -> ApplicationRelease:
    return ApplicationRelease(
        value.app_code,
        value.source_id,
        value.digest,
        value.app_build_id,
        _environment(value.environment),
    )


def _session(value: RuntimeSession) -> a2ui_pb2.RuntimeSession:
    return a2ui_pb2.RuntimeSession(
        token=value.token,
        app_build_id=value.app_build_id,
        protocol_version=value.protocol_version,
        catalog_id=value.catalog_id,
        catalog_revision=value.catalog_revision,
        catalog_digest=value.catalog_digest,
    )


def _session_model(value: a2ui_pb2.RuntimeSession) -> RuntimeSession:
    return RuntimeSession(
        value.token,
        value.app_build_id,
        value.protocol_version,
        value.catalog_id,
        value.catalog_revision,
        value.catalog_digest,
    )


def _describe(value: PublishedApplication) -> a2ui_pb2.DescribeResponse:
    build = value.build
    return a2ui_pb2.DescribeResponse(
        release=_release(value.release),
        params_schema_json=_json(build.params_schema),
        interaction_mode=build.interaction_mode.value,
        actions=[
            a2ui_pb2.ActionDescriptor(
                surface_id=item.surface_id,
                component_id=item.source_component_id,
                action_name=item.action_code,
                context_schema_json=_json(item.context_schema),
            )
            for item in build.action_bindings
        ],
        catalog=a2ui_pb2.CatalogDescriptor(
            protocol_version=build.protocol_version,
            catalog_id=build.catalog.catalog_id,
            catalog_revision=build.catalog.revision,
            catalog_digest=build.catalog.digest,
        ),
    )


def _response(value: RuntimeResult) -> a2ui_pb2.RuntimeResponse:
    response = a2ui_pb2.RuntimeResponse(
        release=_release(value.release),
        params_json=_json(value.params),
        messages_json=_json(list(value.messages)),
        snapshot_json=_json(list(value.snapshot)),
        executions=[
            a2ui_pb2.ExecutionSummary(
                binding_id=item.binding_id,
                action_code=item.action_code,
                success=item.success,
                capability_version=item.capability_version,
                error_code=item.error_code or "",
            )
            for item in value.executions
        ],
        actions=[
            a2ui_pb2.ActionDescriptor(
                surface_id=item.surface_id,
                component_id=item.source_component_id,
                action_name=item.action_code,
                context_schema_json=_json(item.context_schema),
            )
            for item in value.actions
        ],
        complete_interaction=value.complete_interaction,
        selected_branch_id=value.selected_branch_id or "",
        catalog=a2ui_pb2.CatalogDescriptor(
            protocol_version=value.session.protocol_version,
            catalog_id=value.session.catalog_id,
            catalog_revision=value.session.catalog_revision,
            catalog_digest=value.session.catalog_digest,
        ),
        session=_session(value.session),
        interaction_mode=value.interaction_mode.value,
        business_success=value.business_success,
    )
    if value.action_observation is not None:
        observed = value.action_observation
        response.action_observation.CopyFrom(
            a2ui_pb2.ActionExecutionObservation(
                binding_id=observed.binding_id,
                action_code=observed.action_code,
                arguments_json=_json(observed.arguments),
                result_json=_json(observed.result),
                capability_success=observed.capability_success,
                capability_error_code=observed.capability_error_code or "",
                presentation_error_code=observed.presentation_error_code or "",
            )
        )
        if observed.business_success is not None:
            response.action_observation.business_success = observed.business_success
    return response


class A2uiRpcService(a2ui_pb2_grpc.A2uiExecutionServicer):
    def __init__(self, service: A2uiRuntimeService) -> None:
        self._service = service

    def Describe(
        self, request: a2ui_pb2.DescribeRequest, context: grpc.ServicerContext
    ) -> a2ui_pb2.DescribeResponse:
        return self._respond(
            context,
            lambda: _describe(self._service.describe(request.app_code, _context(request.context))),
            stage="describe",
        )

    def Activate(
        self, request: a2ui_pb2.ActivateRequest, context: grpc.ServicerContext
    ) -> a2ui_pb2.RuntimeResponse:
        return self._respond(
            context,
            lambda: _response(
                self._service.activate(
                    request.app_code,
                    _object(request.params_json),
                    request.expected_source_id,
                    request.expected_digest,
                    _context(request.context),
                )
            ),
            stage="activate",
        )

    def Act(
        self, request: a2ui_pb2.ActRequest, context: grpc.ServicerContext
    ) -> a2ui_pb2.RuntimeResponse:
        def execute() -> a2ui_pb2.RuntimeResponse:
            card = request.card
            if (
                not card.HasField("user_id")
                or not card.HasField("release")
                or not card.HasField("session")
            ):
                raise A2uiError("A2UI_CARD_CONTEXT_MISMATCH")
            release = _release_model(card.release)
            trusted = TrustedCard(
                card.user_id,
                release,
                _session_model(card.session),
                card.revision,
                _object(card.params_json),
                _messages(card.snapshot_json),
            )
            return _response(
                self._service.act(
                    trusted,
                    request.correlation_id,
                    request.runtime_session_token,
                    request.app_build_id,
                    request.expected_surface_revision,
                    request.idempotency_key,
                    _object(request.action_message_json),
                    _context(request.context),
                )
            )

        return self._respond(context, execute, stage="act")

    def _respond(
        self,
        context: grpc.ServicerContext,
        operation: Callable[[], Response],
        *,
        stage: str,
    ) -> Response:
        try:
            return operation()
        except A2uiError as error:
            LOG.warning(
                "a2ui_rpc_failed stage=%s exception_type=%s error_code=%s",
                stage,
                type(error).__name__,
                error.code,
            )
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, error.code)
        except ReleaseStorageError as error:
            LOG.warning(
                "a2ui_rpc_failed stage=%s exception_type=%s error_code=%s",
                stage,
                type(error).__name__,
                "CAPABILITY_RELEASE_STORAGE_UNAVAILABLE",
            )
            context.abort(grpc.StatusCode.UNAVAILABLE, "CAPABILITY_RELEASE_STORAGE_UNAVAILABLE")
        except ReleaseError as error:
            LOG.warning(
                "a2ui_rpc_failed stage=%s exception_type=%s error_code=%s",
                stage,
                type(error).__name__,
                error.code,
            )
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, error.code)
        except Exception as error:
            LOG.error(
                "a2ui_rpc_failed stage=%s exception_type=%s error_code=%s",
                stage,
                type(error).__name__,
                "A2UI_EXECUTION_FAILED",
            )
            context.abort(grpc.StatusCode.INTERNAL, "A2UI_EXECUTION_FAILED")
        raise AssertionError("unreachable")
