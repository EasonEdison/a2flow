"""Projection of trusted Skill material into the approved useSkillResult shape."""

from __future__ import unicode_literals

from collections import namedtuple
import re

from skillweave_contracts import (
    CONTRACT_REVISION,
    UseSkillRequest,
    UseSkillResult,
)

from .ports import MaterialPort, SkillMaterial
from .resources import PackageEntry, validate_package_entries

ASSET_TYPE_SKILL = "SKILL"
ENVIRONMENT_PRT = "PRT"
ENVIRONMENT_ONLINE = "ONLINE"
SELECTION_PRT_CURRENT = "PRT_CURRENT"
SELECTION_ONLINE_STABLE = "ONLINE_STABLE"
SELECTION_ONLINE_GRAY = "ONLINE_GRAY"
SCOPE_CONVERSATION = "CONVERSATION"
INSTRUCTION_LOGICAL_PATH = "SKILL.md"
SCOPE_WORKFLOW = "WORKFLOW"

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class TrustedContext(namedtuple("_TrustedContext", ("user_id", "environment"))):
    """Server-supplied identity and environment shape, not provenance proof."""

    __slots__ = ()


class InvocationScope(namedtuple(
        "_InvocationScope",
        ("kind", "conversation_id", "run_id", "node_id"))):
    """Server-supplied invocation scope for conversation or Workflow calls."""

    __slots__ = ()

    def __new__(
            cls,
            kind,
            conversation_id=None,
            run_id=None,
            node_id=None):
        return super(InvocationScope, cls).__new__(
            cls,
            kind,
            conversation_id,
            run_id,
            node_id,
        )


class TrustedInvocationContext(namedtuple(
        "_TrustedInvocationContext",
        (
            "contract_revision",
            "trusted_context",
            "invocation_scope",
            "control_request_id",
        ))):
    """Immutable context injected separately from model input."""

    __slots__ = ()


class TrustedResolutionEvidence(namedtuple(
        "_TrustedResolutionEvidence",
        (
            "skill_key",
            "asset_id",
            "version_id",
            "content_digest",
            "environment",
            "selection",
            "evidence_ref",
        ))):
    """Immutable resolution evidence supplied by the trusted material adapter."""

    __slots__ = ()


class SkillRegistryValidationError(ValueError):
    """Local fail-closed validation error; not a shared wire error contract."""

    def __init__(self, code, message):
        super(SkillRegistryValidationError, self).__init__(message)
        self.code = code


def _fail(code, message):
    raise SkillRegistryValidationError(code, message)


def _valid_identifier(value):
    return isinstance(value, str) and bool(_IDENTIFIER_PATTERN.fullmatch(value))


def _validate_context(context):
    if not isinstance(context, TrustedInvocationContext):
        _fail(
            "INVALID_TRUSTED_CONTEXT",
            "trusted invocation context has an unsupported type",
        )
    if context.contract_revision != CONTRACT_REVISION:
        _fail(
            "INVALID_CONTRACT_REVISION",
            "trusted context uses an unsupported contract revision",
        )
    trusted = context.trusted_context
    if not isinstance(trusted, TrustedContext):
        _fail("INVALID_TRUSTED_CONTEXT", "trustedContext is required")
    if not _valid_identifier(trusted.user_id):
        _fail("INVALID_TRUSTED_CONTEXT", "trusted userId is invalid")
    if trusted.environment not in (ENVIRONMENT_PRT, ENVIRONMENT_ONLINE):
        _fail("INVALID_TRUSTED_CONTEXT", "trusted environment is invalid")
    if not _valid_identifier(context.control_request_id):
        _fail("INVALID_TRUSTED_CONTEXT", "controlRequestId is invalid")
    scope = context.invocation_scope
    if not isinstance(scope, InvocationScope):
        _fail("INVALID_INVOCATION_SCOPE", "invocationScope is required")
    if scope.kind == SCOPE_CONVERSATION:
        if (
                not _valid_identifier(scope.conversation_id)
                or scope.run_id is not None
                or scope.node_id is not None):
            _fail(
                "INVALID_INVOCATION_SCOPE",
                "conversation scope requires only conversationId",
            )
    elif scope.kind == SCOPE_WORKFLOW:
        if (
                not _valid_identifier(scope.run_id)
                or not _valid_identifier(scope.node_id)
                or (
                    scope.conversation_id is not None
                    and not _valid_identifier(scope.conversation_id)
                )):
            _fail(
                "INVALID_INVOCATION_SCOPE",
                "Workflow scope requires runId and nodeId",
            )
    else:
        _fail("INVALID_INVOCATION_SCOPE", "invocation scope kind is invalid")


def _validate_resolution_evidence(request, trusted_context, evidence):
    if not isinstance(evidence, TrustedResolutionEvidence):
        _fail(
            "INVALID_RESOLUTION_EVIDENCE",
            "trusted resolution evidence has an unsupported type",
        )
    if evidence.skill_key != request.skill_key:
        _fail(
            "RESOLUTION_SKILL_MISMATCH",
            "resolved evidence does not match the requested Skill",
        )
    for value in (
            evidence.asset_id,
            evidence.version_id,
            evidence.evidence_ref,
    ):
        if not _valid_identifier(value):
            _fail(
                "INVALID_RESOLUTION_EVIDENCE",
                "resolution evidence contains an invalid identifier",
            )
    if (
            not isinstance(evidence.content_digest, str)
            or not _DIGEST_PATTERN.fullmatch(evidence.content_digest)):
        _fail(
            "INVALID_RESOLUTION_EVIDENCE",
            "artifact contentDigest must be lowercase sha256 evidence",
        )
    allowed = {
        ENVIRONMENT_PRT: (SELECTION_PRT_CURRENT,),
        ENVIRONMENT_ONLINE: (
            SELECTION_ONLINE_STABLE,
            SELECTION_ONLINE_GRAY,
        ),
    }
    if (
            evidence.environment not in allowed
            or evidence.selection not in allowed[evidence.environment]):
        _fail(
            "INVALID_RESOLUTION_EVIDENCE",
            "environment and selection are inconsistent",
        )
    if evidence.environment != trusted_context.environment:
        _fail(
            "RESOLUTION_ENVIRONMENT_MISMATCH",
            "resolved evidence must match the trusted environment",
        )


def _validate_material(material):
    if not isinstance(material, SkillMaterial):
        _fail("INVALID_SKILL_MATERIAL", "material port returned an invalid value")
    if not isinstance(material.instruction_entry, PackageEntry):
        _fail(
            "INVALID_SKILL_MATERIAL",
            "Skill instructions must be supplied as a package entry",
        )
    if (
            not isinstance(material.resource_entries, tuple)
            or any(
                not isinstance(entry, PackageEntry)
                for entry in material.resource_entries
            )):
        _fail(
            "INVALID_SKILL_MATERIAL",
            "Skill resources must be an immutable tuple of package entries",
        )
    if not isinstance(material.required_tool_names, tuple):
        _fail(
            "INVALID_REQUIRED_TOOL_NAMES",
            "required Tool names must be an immutable tuple",
        )
    if (
            any(not _valid_identifier(name) for name in material.required_tool_names)
            or len(material.required_tool_names)
            != len(set(material.required_tool_names))):
        _fail(
            "INVALID_REQUIRED_TOOL_NAMES",
            "required Tool names must be unique approved identifiers",
        )


def _resource_handle(resource):
    return {
        "handleId": resource.handle_id,
        "accessMode": resource.access_mode,
        "logicalPath": resource.logical_path,
        "mediaType": resource.media_type,
        "byteSize": resource.byte_size,
        "contentDigest": resource.content_digest,
    }


def _project_result(instructions, material, evidence, verified_resources):
    content = {
        "instructions": instructions,
        "resources": [
            _resource_handle(resource) for resource in verified_resources
        ],
    }
    if material.required_tool_names:
        content["requiredToolNames"] = list(material.required_tool_names)
    return {
        "contractRevision": CONTRACT_REVISION,
        "content": content,
        "artifact": {
            "skillKey": evidence.skill_key,
            "resolvedVersion": {
                "asset": {
                    "assetType": ASSET_TYPE_SKILL,
                    "assetId": evidence.asset_id,
                },
                "versionId": evidence.version_id,
            },
            "contentDigest": evidence.content_digest,
            "environment": evidence.environment,
            "selection": evidence.selection,
            "evidenceRef": evidence.evidence_ref,
        },
    }


def use_skill(request, context, material_port, resource_limits=None):
    """Load, validate, and project one Skill without granting execution rights."""

    if not isinstance(request, UseSkillRequest):
        _fail("INVALID_USE_SKILL_REQUEST", "request has an unsupported type")
    _validate_context(context)
    if not isinstance(material_port, MaterialPort):
        _fail("INVALID_MATERIAL_PORT", "material port has an unsupported type")

    material = material_port.load_skill(
        request.skill_key,
        context.trusted_context,
    )
    _validate_material(material)
    _validate_resolution_evidence(
        request,
        context.trusted_context,
        material.resolution_evidence,
    )
    verified_entries = validate_package_entries(
        (material.instruction_entry,) + material.resource_entries,
        resource_limits,
    )
    verified_instruction = verified_entries[0]
    if (
            verified_instruction.logical_path != INSTRUCTION_LOGICAL_PATH
            or verified_instruction.text is None
            or not verified_instruction.text):
        _fail(
            "INVALID_SKILL_INSTRUCTIONS",
            "Skill instructions must be non-empty UTF-8 text from SKILL.md",
        )
    verified_resources = verified_entries[1:]
    return UseSkillResult.from_mapping(
        _project_result(
            verified_instruction.text,
            material,
            material.resolution_evidence,
            verified_resources,
        )
    )
