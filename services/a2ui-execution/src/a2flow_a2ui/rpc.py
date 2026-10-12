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
from pydantic import ValidationError

from .models import (
    A2uiError,
    ApplicationRelease,
    DefinitionSource,
    GeneratedCandidate,
    GeneratedDefinition,
    GenerationScope,
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


def _scope(value: a2ui_pb2.GenerationScope) -> GenerationScope:
    try:
        return GenerationScope(
            conversationId=value.conversation_id,
            workflowRunId=value.workflow_run_id,
            nodeId=value.node_id,
        )
    except ValidationError:
        raise A2uiError("A2UI_GENERATION_SCOPE_INVALID") from None


def _scope_rpc(value: GenerationScope) -> a2ui_pb2.GenerationScope:
    return a2ui_pb2.GenerationScope(
        conversation_id=value.conversation_id,
        workflow_run_id=value.workflow_run_id,
        node_id=value.node_id,
    )


def _candidate(value: bytes) -> GeneratedCandidate:
    if len(value) > 256 * 1024:
        raise A2uiError("A2UI_GENERATION_SIZE_LIMIT")
    try:
        return GeneratedCandidate.model_validate(_object(value))
    except ValidationError:
        raise A2uiError("A2UI_GENERATION_CANDIDATE_SHAPE_INVALID") from None


def _definition_model(value: a2ui_pb2.GeneratedDefinition) -> GeneratedDefinition:
    if not value.HasField("owner_user_id") or not value.HasField("scope"):
        raise A2uiError("A2UI_GENERATED_CARD_SCOPE_MISMATCH")
    try:
        return GeneratedDefinition(
            originAppCode=value.origin_app_code,
            candidate=_candidate(value.candidate_json),
            scope=_scope(value.scope),
            ownerUserId=value.owner_user_id,
            environment=_environment(value.environment),
            artifactDigest=value.artifact_digest,
        )
    except ValidationError:
        raise A2uiError("A2UI_GENERATED_CARD_SCOPE_MISMATCH") from None


def _definition_rpc(value: GeneratedDefinition) -> a2ui_pb2.GeneratedDefinition:
    return a2ui_pb2.GeneratedDefinition(
        origin_app_code=value.origin_app_code,
        candidate_json=_json(value.candidate.model_dump(by_alias=True)),
        scope=_scope_rpc(value.scope),
        owner_user_id=value.owner_user_id,
        environment=(
            capability_pb2.PRT if value.environment is Environment.PRT else capability_pb2.ONLINE
        ),
        artifact_digest=value.artifact_digest,
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
        composer_draft_effects=[
            a2ui_pb2.ComposerDraftEffect(
                type=item.type.value,
                mode=item.mode.value,
                request_id=item.request_id,
                text=item.text,
            )
            for item in value.composer_draft_effects
        ],
        definition_source=(
            a2ui_pb2.GENERATED
            if value.definition_source is DefinitionSource.GENERATED
            else a2ui_pb2.PUBLISHED
        ),
    )
    if value.generated_definition is not None:
        response.generated_definition.CopyFrom(_definition_rpc(value.generated_definition))
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

    def DescribeGenerationSource(
        self,
        request: a2ui_pb2.DescribeGenerationSourceRequest,
        context: grpc.ServicerContext,
    ) -> a2ui_pb2.GenerationSource:
        def execute() -> a2ui_pb2.GenerationSource:
            published, contract = self._service.describe_generation_source(
                request.origin_app_code, _context(request.context)
            )
            return a2ui_pb2.GenerationSource(
                origin_release=_release(published.release),
                catalog=a2ui_pb2.CatalogDescriptor(
                    protocol_version=published.build.protocol_version,
                    catalog_id=published.build.catalog.catalog_id,
                    catalog_revision=published.build.catalog.revision,
                    catalog_digest=published.build.catalog.digest,
                ),
                generation_contract_json=_json(contract.model_dump(by_alias=True)),
            )

        return self._respond(context, execute, stage="describe_generation_source")

    def ActivateGenerated(
        self,
        request: a2ui_pb2.ActivateGeneratedRequest,
        context: grpc.ServicerContext,
    ) -> a2ui_pb2.RuntimeResponse:
        return self._respond(
            context,
            lambda: _response(
                self._service.activate_generated(
                    request.origin_app_code,
                    _object(request.params_json),
                    _candidate(request.candidate_json),
                    _scope(request.scope),
                    _context(request.context),
                )
            ),
            stage="activate_generated",
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
            if not card.HasField("user_id") or (
                not card.app_code and not card.HasField("generated_definition")
            ):
                raise A2uiError("A2UI_CARD_CONTEXT_MISMATCH")
            trusted = TrustedCard(
                card.user_id,
                card.app_code,
                _object(card.params_json),
                _messages(card.snapshot_json),
                _definition_model(card.generated_definition)
                if card.HasField("generated_definition")
                else None,
                _scope(card.scope) if card.HasField("scope") else None,
            )
            return _response(
                self._service.act(
                    trusted,
                    request.correlation_id,
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
