"""Strict published A2UI build and runtime boundary models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from a2flow_capability.models import (
    Environment,
    ExecutionResult,
    TrustedContext,
)
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

JsonObject = dict[str, JsonValue]


class A2uiError(RuntimeError):
    """Stable, content-safe runtime error."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail or code
        super().__init__(self.detail)


class _PublishedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class InteractionMode(StrEnum):
    DISPLAY_ONLY = "DISPLAY_ONLY"
    INTERACTIVE = "INTERACTIVE"


class MappingSource(StrEnum):
    ACTION_CONTEXT = "ACTION_CONTEXT"
    APP_PARAMS = "APP_PARAMS"
    TRUSTED_CONTEXT = "TRUSTED_CONTEXT"
    CONSTANT = "CONSTANT"
    CAPABILITY_PREVIOUS_RESULT = "CAPABILITY_PREVIOUS_RESULT"


class RequestTransformType(StrEnum):
    STRING_PREFIX = "STRING_PREFIX"
    ARRAY_FILTER_BY_BOOLEAN_MASK = "ARRAY_FILTER_BY_BOOLEAN_MASK"


class ResultAdapterType(StrEnum):
    MESSAGE_TEMPLATE = "MESSAGE_TEMPLATE"
    A2UI_PASSTHROUGH = "A2UI_PASSTHROUGH"


class ResultSource(StrEnum):
    CAPABILITY_DATA = "CAPABILITY_DATA"
    CAPABILITY_META = "CAPABILITY_META"
    TRUSTED_CONTEXT = "TRUSTED_CONTEXT"
    ACTION_CONTEXT = "ACTION_CONTEXT"
    CONSTANT = "CONSTANT"


class ResultTransformType(StrEnum):
    MINOR_UNIT_TO_DECIMAL_STRING = "MINOR_UNIT_TO_DECIMAL_STRING"
    ARRAY_TO_CHILDREN_PREFIX = "ARRAY_TO_CHILDREN_PREFIX"
    BOOLEAN_ARRAY_TRUE_COUNT = "BOOLEAN_ARRAY_TRUE_COUNT"
    PAGINATION_STATE = "PAGINATION_STATE"
    NUMBER_TO_STRING = "NUMBER_TO_STRING"


class ResultOutcome(StrEnum):
    ADAPTER_PIPELINE = "ADAPTER_PIPELINE"
    NO_UI_MESSAGES = "NO_UI_MESSAGES"


class ShowInputSource(StrEnum):
    APP_PARAMS = "APP_PARAMS"
    TRUSTED_CONTEXT = "TRUSTED_CONTEXT"
    CONSTANT = "CONSTANT"


class CatalogRef(_PublishedModel):
    catalog_id: str = Field(alias="catalogId", min_length=1)
    revision: str = Field(min_length=1)
    digest: str = Field(min_length=1)
    catalog_source_type: str = Field(alias="catalogSourceType", min_length=1)
    component_origins: dict[str, str] = Field(alias="componentOrigins")


class SurfaceDeclaration(_PublishedModel):
    surface_id: str = Field(alias="surfaceId", min_length=1)
    root_component_id: str = Field(alias="rootComponentId", min_length=1)
    footer_component_ids: tuple[str, ...] = Field(default=(), alias="footerComponentIds")


class ShowInputBinding(_PublishedModel):
    target_message_index: int = Field(alias="targetMessageIndex", ge=0)
    target_path: str = Field(alias="targetPath", min_length=1)
    source: ShowInputSource
    source_path: str | None = Field(default=None, alias="sourcePath")
    required: bool
    constant_value: JsonValue = Field(default=None, alias="constantValue")


class RequestTransform(_PublishedModel):
    type: RequestTransformType
    prefix: str | None = None
    mask_source_path: str | None = Field(default=None, alias="maskSourcePath")


class RequestMapping(_PublishedModel):
    source: MappingSource
    source_path: str | None = Field(default=None, alias="sourcePath")
    target_path: str = Field(alias="targetPath", min_length=1)
    constant_value: JsonValue = Field(default=None, alias="constantValue")
    transform: RequestTransform | None = None


class CapabilityRef(_PublishedModel):
    action_code: str = Field(alias="actionCode", min_length=1)


class ResultTransform(_PublishedModel):
    type: ResultTransformType
    scale: int | None = None
    component_ids: tuple[str, ...] | None = Field(default=None, alias="componentIds")
    page_size: int | float | None = Field(default=None, alias="pageSize")
    page_number: int | float | None = Field(default=None, alias="pageNumber")
    action_page_path: str | None = Field(default=None, alias="actionPagePath")


class MessageTemplateBinding(_PublishedModel):
    target_path: str = Field(alias="targetPath", min_length=1)
    source: ResultSource
    source_path: str | None = Field(default=None, alias="sourcePath")
    required: bool
    constant_value: JsonValue = Field(default=None, alias="constantValue")
    transform: ResultTransform | None = None


class EmittedActionDeclaration(_PublishedModel):
    surface_id: str = Field(alias="surfaceId", min_length=1)
    source_component_id: str = Field(alias="sourceComponentId", min_length=1)
    action_code: str = Field(alias="actionCode", min_length=1)
    context_schema: JsonObject = Field(alias="contextSchema")


class ResultAdapter(_PublishedModel):
    adapter_id: str = Field(alias="adapterId", min_length=1)
    order: int = Field(gt=0)
    type: ResultAdapterType
    template_code: str | None = Field(default=None, alias="templateCode")
    template_revision: str | None = Field(default=None, alias="templateRevision")
    template_digest: str | None = Field(default=None, alias="templateDigest")
    message_template: JsonObject | None = Field(default=None, alias="messageTemplate")
    bindings: tuple[MessageTemplateBinding, ...] | None = None
    source: ResultSource | None = None
    source_path: str | None = Field(default=None, alias="sourcePath")
    cardinality: str | None = None
    required: bool = False
    emitted_action_declarations: tuple[EmittedActionDeclaration, ...] = Field(
        default=(), alias="emittedActionDeclarations"
    )


class BusinessPredicateVersion(StrEnum):
    JSON_POINTER_V1 = "JSON_POINTER_V1"


class BusinessPredicateSource(StrEnum):
    CAPABILITY_DATA = "CAPABILITY_DATA"


class BusinessPredicateOperator(StrEnum):
    EQUALS = "EQUALS"
    GREATER_THAN = "GREATER_THAN"
    IS_ARRAY = "IS_ARRAY"


class PredicateClause(_PublishedModel):
    source: BusinessPredicateSource
    source_path: str = Field(alias="sourcePath", min_length=1)
    operator: BusinessPredicateOperator
    expected_value: JsonValue = Field(alias="expectedValue")


class BusinessPredicate(_PublishedModel):
    version: BusinessPredicateVersion
    all_of: tuple[PredicateClause, ...] = Field(alias="allOf", min_length=1)


class SuccessBranch(_PublishedModel):
    branch_id: str = Field(alias="branchId", min_length=1)
    when: BusinessPredicate
    outcome: ResultOutcome
    result_adapters: tuple[ResultAdapter, ...] = Field(alias="resultAdapters")
    complete_workflow_interaction_on_success: bool = Field(
        alias="completeWorkflowInteractionOnSuccess"
    )


class ActionBinding(_PublishedModel):
    binding_id: str = Field(alias="bindingId", min_length=1)
    surface_id: str = Field(alias="surfaceId", min_length=1)
    source_component_id: str = Field(alias="sourceComponentId", min_length=1)
    action_code: str = Field(alias="actionCode", min_length=1)
    declaration_digest: str = Field(alias="declarationDigest", min_length=1)
    allowed_source_component_ids: tuple[str, ...] = Field(alias="allowedSourceComponentIds")
    context_schema: JsonObject = Field(alias="contextSchema")
    capability: CapabilityRef
    request_mappings: tuple[RequestMapping, ...] = Field(alias="requestMappings")
    success_outcome: ResultOutcome = Field(alias="successOutcome")
    failure_outcome: ResultOutcome = Field(alias="failureOutcome")
    result_adapters: tuple[ResultAdapter, ...] = Field(alias="resultAdapters")
    failure_result_adapters: tuple[ResultAdapter, ...] = Field(alias="failureResultAdapters")
    business_success_predicate: BusinessPredicate | None = Field(
        default=None, alias="businessSuccessPredicate"
    )
    complete_workflow_interaction_on_success: bool = Field(
        alias="completeWorkflowInteractionOnSuccess"
    )
    success_branches: tuple[SuccessBranch, ...] = Field(default=(), alias="successBranches")


class LoadBinding(_PublishedModel):
    binding_id: str = Field(alias="bindingId", min_length=1)
    capability: CapabilityRef
    request_mappings: tuple[RequestMapping, ...] = Field(alias="requestMappings")
    success_outcome: ResultOutcome = Field(alias="successOutcome")
    failure_outcome: ResultOutcome = Field(alias="failureOutcome")
    result_adapters: tuple[ResultAdapter, ...] = Field(alias="resultAdapters")
    failure_result_adapters: tuple[ResultAdapter, ...] = Field(alias="failureResultAdapters")


class ActionDeclaration(_PublishedModel):
    surface_id: str = Field(alias="surfaceId", min_length=1)
    source_component_id: str = Field(alias="sourceComponentId", min_length=1)
    action_code: str = Field(alias="actionCode", min_length=1)
    context_template_digest: str = Field(alias="contextTemplateDigest", min_length=1)


class CapabilitySchemaAudit(_PublishedModel):
    action_code: str = Field(alias="actionCode", min_length=1)
    model_contract_digest: str = Field(alias="modelContractDigest", min_length=1)
    result_contract_digest: str = Field(alias="resultContractDigest", min_length=1)


class ApplicationBuild(_PublishedModel):
    app_build_id: str = Field(alias="appBuildId", min_length=1)
    app_code: str = Field(alias="appCode", min_length=1)
    source_digest: str = Field(alias="sourceDigest", min_length=1)
    protocol_version: str = Field(alias="protocolVersion", pattern=r"^v0\.9\.1$")
    protocol_status: str = Field(alias="protocolStatus", min_length=1)
    protocol_source_commit: str = Field(alias="protocolSourceCommit", min_length=1)
    protocol_schema_digests: dict[str, str] = Field(alias="protocolSchemaDigests")
    publication_environment: Environment = Field(alias="publicationEnvironment")
    catalog: CatalogRef
    show_template_code: str = Field(alias="showTemplateCode", min_length=1)
    show_template_digest: str = Field(alias="showTemplateDigest", min_length=1)
    params_schema: JsonObject = Field(alias="paramsSchema")
    surface_declarations: tuple[SurfaceDeclaration, ...] = Field(alias="surfaceDeclarations")
    initial_messages: tuple[JsonObject, ...] = Field(alias="initialMessages", min_length=1)
    input_bindings: tuple[ShowInputBinding, ...] = Field(alias="inputBindings")
    component_types: tuple[str, ...] = Field(alias="componentTypes")
    capability_schema_audits: tuple[CapabilitySchemaAudit, ...] = Field(
        alias="capabilitySchemaAudits"
    )
    action_declarations: tuple[ActionDeclaration, ...] = Field(alias="actionDeclarations")
    load_bindings: tuple[LoadBinding, ...] = Field(alias="loadBindings")
    action_bindings: tuple[ActionBinding, ...] = Field(alias="actionBindings")
    interaction_mode: InteractionMode = Field(alias="interactionMode")

    @model_validator(mode="after")
    def validate_closed_identity(self) -> ApplicationBuild:
        binding_ids = [item.binding_id for item in self.load_bindings]
        binding_ids.extend(item.binding_id for item in self.action_bindings)
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("binding ids must be unique")
        action_keys = [
            (item.surface_id, item.source_component_id, item.action_code)
            for item in self.action_bindings
        ]
        if len(action_keys) != len(set(action_keys)):
            raise ValueError("action bindings must be unique per surface and action")
        return self


@dataclass(frozen=True, slots=True)
class ApplicationRelease:
    app_code: str
    source_id: str
    digest: str
    app_build_id: str
    environment: Environment


@dataclass(frozen=True, slots=True)
class PublishedApplication:
    release: ApplicationRelease
    build: ApplicationBuild


@dataclass(frozen=True, slots=True)
class RuntimeSession:
    token: str
    app_build_id: str
    protocol_version: str
    catalog_id: str
    catalog_revision: str
    catalog_digest: str


@dataclass(frozen=True, slots=True)
class TrustedCard:
    user_id: int
    release: ApplicationRelease
    session: RuntimeSession
    revision: int
    params: JsonObject
    snapshot: tuple[JsonObject, ...]


@dataclass(frozen=True, slots=True)
class ExecutionSummary:
    binding_id: str
    action_code: str
    success: bool
    capability_version: int
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    release: ApplicationRelease
    params: JsonObject
    messages: tuple[JsonObject, ...]
    snapshot: tuple[JsonObject, ...]
    executions: tuple[ExecutionSummary, ...]
    actions: tuple[EmittedActionDeclaration, ...]
    complete_interaction: bool
    selected_branch_id: str | None
    session: RuntimeSession
    interaction_mode: InteractionMode
    business_success: bool


class PublishedApplicationReader(Protocol):
    def current(self, app_code: str, context: TrustedContext) -> PublishedApplication: ...


class CapabilityInvoker(Protocol):
    def execute_action_code(
        self, action_code: str, arguments: JsonObject, context: TrustedContext
    ) -> ExecutionResult: ...
