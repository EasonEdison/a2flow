"""Typed structural admission for management draft documents.

These models validate identity and relation-bearing structure without dumping a
new document. The original JSON object remains the canonical value stored by the
draft repository; publication validators continue to own business completeness.
"""

from typing import Literal, TypeAlias, overload

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError
from skillweave_contracts import AssetKind
from skillweave_contracts.asset_types import JsonObject

from .contracts import ManagementError


class DraftStructure(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class SkillMetadata(DraftStructure):
    name: str
    description: str


class SkillDraftDocument(DraftStructure):
    metadata: SkillMetadata
    skillMd: str
    requiredToolNames: list[str] = Field(max_length=64)
    abilityBindings: list[str] = Field(max_length=64)
    applicationBindings: list[str] = Field(max_length=64)
    resources: list[JsonValue] = Field(max_length=127)


class AbilityInputBinding(DraftStructure):
    targetPath: str
    source: str
    sourcePath: str


class AbilityCredentialRequirement(DraftStructure):
    slotId: str
    required: bool


class AbilityDraftDocument(DraftStructure):
    model_config = ConfigDict(extra="forbid", strict=True)

    abilityKey: str
    adapterOperationRef: str
    credentialRequirements: list[AbilityCredentialRequirement]
    defaultSuccessPolicyRef: str
    inputBindings: list[AbilityInputBinding]
    modelArgumentSchema: JsonValue
    outputSchema: JsonValue
    resolvedInputSchema: JsonValue
    resultInterpretationPolicies: list[JsonValue]


class ComponentDefinition(DraftStructure):
    catalogKey: str
    protocolProfileRef: str
    components: list[str]


class ComponentDraftDocument(DraftStructure):
    definition: ComponentDefinition
    dependencies: list[JsonValue]


class ApplicationAsset(DraftStructure):
    kind: Literal["APPLICATION"]
    applicationKey: str
    protocolProfileRef: str | None = None
    componentCatalogRef: str | None = None


class ApplicationDefinition(DraftStructure):
    asset: ApplicationAsset


class ApplicationDependency(DraftStructure):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["ABILITY", "COMPONENT"]
    key: str


class ApplicationDraftDocument(DraftStructure):
    definition: ApplicationDefinition
    dependencies: list[ApplicationDependency] = Field(max_length=128)


class WorkflowNode(DraftStructure):
    model_config = ConfigDict(extra="forbid", strict=True)

    nodeId: str
    skillKey: str


class WorkflowDraftDocument(DraftStructure):
    definitionKey: str
    topology: str
    nodes: list[WorkflowNode] = Field(max_length=64)


class SkillRelationProjection(DraftStructure):
    abilityBindings: list[str] = Field(max_length=64)
    applicationBindings: list[str] = Field(max_length=64)


class ApplicationRelationProjection(DraftStructure):
    dependencies: list[ApplicationDependency] = Field(max_length=128)


class WorkflowRelationNode(DraftStructure):
    skillKey: str


class WorkflowRelationProjection(DraftStructure):
    nodes: list[WorkflowRelationNode] = Field(max_length=64)


ValidatedDraftDocument: TypeAlias = (
    SkillDraftDocument
    | AbilityDraftDocument
    | ComponentDraftDocument
    | ApplicationDraftDocument
    | WorkflowDraftDocument
)


def _validation_code(kind: AssetKind, error: ValidationError) -> str:
    first = error.errors(include_url=False)[0]
    path = tuple(str(item) for item in first.get("loc", ()))
    if kind == "SKILL":
        if path and path[0] in {"abilityBindings", "applicationBindings"}:
            return "INVALID_BINDINGS"
        return "INVALID_DRAFT_FIELDS"
    if kind == "ABILITY":
        if path and path[0] == "credentialRequirements":
            return "UNTRUSTED_ABILITY_REFERENCE"
        return "INVALID_ABILITY_DRAFT_FIELDS"
    if kind == "APPLICATION":
        if path and path[0] == "dependencies":
            return "INVALID_DEPENDENCIES"
        if path[:2] == ("definition", "asset"):
            return "INVALID_APPLICATION_ASSET"
        return "INVALID_DRAFT_FIELDS"
    if kind == "COMPONENT":
        return "INVALID_COMPONENT_DRAFT_FIELDS"
    if path and path[0] == "topology":
        return "INVALID_WORKFLOW_TOPOLOGY"
    if path and path[0] == "nodes":
        return "INVALID_WORKFLOW_NODE"
    return "INVALID_WORKFLOW_DRAFT_FIELDS"


@overload
def parse_draft_structure(
    kind: Literal["SKILL"], key: str, document: JsonObject
) -> SkillDraftDocument: ...


@overload
def parse_draft_structure(
    kind: Literal["ABILITY"], key: str, document: JsonObject
) -> AbilityDraftDocument: ...


@overload
def parse_draft_structure(
    kind: Literal["COMPONENT"], key: str, document: JsonObject
) -> ComponentDraftDocument: ...


@overload
def parse_draft_structure(
    kind: Literal["APPLICATION"], key: str, document: JsonObject
) -> ApplicationDraftDocument: ...


@overload
def parse_draft_structure(
    kind: Literal["WORKFLOW"], key: str, document: JsonObject
) -> WorkflowDraftDocument: ...


@overload
def parse_draft_structure(
    kind: AssetKind, key: str, document: JsonObject
) -> ValidatedDraftDocument: ...


def parse_draft_structure(
    kind: AssetKind, key: str, document: JsonObject
) -> ValidatedDraftDocument:
    model: type[ValidatedDraftDocument]
    if kind == "SKILL":
        model = SkillDraftDocument
    elif kind == "ABILITY":
        model = AbilityDraftDocument
    elif kind == "COMPONENT":
        model = ComponentDraftDocument
    elif kind == "APPLICATION":
        model = ApplicationDraftDocument
    else:
        model = WorkflowDraftDocument
    try:
        parsed = model.model_validate(document, strict=True)
    except ValidationError as error:
        raise ManagementError(_validation_code(kind, error)) from None
    if isinstance(parsed, AbilityDraftDocument) and parsed.abilityKey != key:
        raise ManagementError("ABILITY_KEY_MISMATCH")
    if isinstance(parsed, ComponentDraftDocument) and parsed.definition.catalogKey != key:
        raise ManagementError("COMPONENT_CATALOG_KEY_MISMATCH")
    if (
        isinstance(parsed, ApplicationDraftDocument)
        and parsed.definition.asset.applicationKey != key
    ):
        raise ManagementError("APPLICATION_KEY_MISMATCH")
    if isinstance(parsed, WorkflowDraftDocument) and parsed.definitionKey != key:
        raise ManagementError("WORKFLOW_KEY_MISMATCH")
    return parsed


def draft_reference_targets(
    kind: AssetKind, document: JsonObject
) -> tuple[tuple[AssetKind, str], ...]:
    """Read only relation-bearing fields without requiring a publishable draft."""

    try:
        if kind == "SKILL":
            skill = SkillRelationProjection.model_validate(document, strict=True)
            return (
                *(("ABILITY", key) for key in skill.abilityBindings),
                *(("APPLICATION", key) for key in skill.applicationBindings),
            )
        if kind == "APPLICATION":
            application = ApplicationRelationProjection.model_validate(document, strict=True)
            return tuple(
                (dependency.kind, dependency.key) for dependency in application.dependencies
            )
        if kind == "WORKFLOW":
            workflow = WorkflowRelationProjection.model_validate(document, strict=True)
            return tuple(("SKILL", node.skillKey) for node in workflow.nodes)
        return ()
    except ValidationError as error:
        raise ManagementError(_validation_code(kind, error)) from None
