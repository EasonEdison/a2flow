from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TypeAlias

from .validation import (
    ContractValidationError,
    ValidationIssue,
    fail,
    require_array,
    require_enum,
    require_integer,
    require_object,
    require_string,
)


CONTRACT_REVISION = "SW-CONTRACTS-P1-CANDIDATE.1"

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_SKILL_KEY = re.compile(r"[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*")
_CONTENT_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_LOGICAL_PATH = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*")
_JSON_POINTER = re.compile(r"(?:/(?:[^~/]|~0|~1)*)+")


def _match(value: str, pattern: re.Pattern[str], *, path: str, code: str) -> str:
    if pattern.fullmatch(value) is None:
        fail(path, code, "value does not match the approved contract pattern")
    return value


def parse_contract_revision(value: object, *, path: str = "$") -> str:
    parsed = require_string(value, path=path)
    if parsed != CONTRACT_REVISION:
        fail(path, "invalid_contract_revision", f"expected {CONTRACT_REVISION}")
    return parsed


def parse_identifier(value: object, *, path: str = "$") -> str:
    parsed = require_string(value, path=path, min_length=1, max_length=128)
    return _match(parsed, _IDENTIFIER, path=path, code="invalid_identifier")


def parse_skill_key(value: object, *, path: str = "$") -> str:
    parsed = require_string(value, path=path, min_length=1, max_length=128)
    return _match(parsed, _SKILL_KEY, path=path, code="invalid_skill_key")


def _parse_digest(value: object, *, path: str) -> str:
    parsed = require_string(value, path=path)
    return _match(parsed, _CONTENT_DIGEST, path=path, code="invalid_content_digest")


def _parse_logical_path(value: object, *, path: str) -> str:
    parsed = require_string(value, path=path, min_length=1, max_length=1024)
    if (
        _LOGICAL_PATH.fullmatch(parsed) is None
        or parsed.startswith("/")
        or "\\" in parsed
        or any(part in {".", ".."} for part in parsed.split("/"))
    ):
        fail(path, "invalid_logical_path", "expected a normalized package-relative logical path")
    return parsed


@dataclass(frozen=True, slots=True)
class TrustedContext:
    user_id: str
    environment: str

    def __post_init__(self) -> None:
        parse_identifier(self.user_id, path="$.userId")
        require_enum(self.environment, path="$.environment", allowed=frozenset({"PRT", "ONLINE"}))

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "TrustedContext":
        data = require_object(
            value, path=_path, required=frozenset({"userId", "environment"})
        )
        return cls(
            user_id=parse_identifier(data["userId"], path=f"{_path}.userId"),
            environment=require_enum(
                data["environment"],
                path=f"{_path}.environment",
                allowed=frozenset({"PRT", "ONLINE"}),
            ),
        )

    def to_mapping(self) -> dict[str, object]:
        return {"userId": self.user_id, "environment": self.environment}


@dataclass(frozen=True, slots=True)
class ConversationInvocationScope:
    conversation_id: str
    kind: str = "CONVERSATION"

    def __post_init__(self) -> None:
        require_enum(self.kind, path="$.kind", allowed=frozenset({"CONVERSATION"}))
        parse_identifier(self.conversation_id, path="$.conversationId")

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "ConversationInvocationScope":
        data = require_object(
            value, path=_path, required=frozenset({"kind", "conversationId"})
        )
        require_enum(data["kind"], path=f"{_path}.kind", allowed=frozenset({"CONVERSATION"}))
        return cls(conversation_id=parse_identifier(data["conversationId"], path=f"{_path}.conversationId"))

    def to_mapping(self) -> dict[str, object]:
        return {"kind": self.kind, "conversationId": self.conversation_id}


@dataclass(frozen=True, slots=True)
class WorkflowInvocationScope:
    run_id: str
    node_id: str
    conversation_id: str | None = None
    kind: str = "WORKFLOW"

    def __post_init__(self) -> None:
        require_enum(self.kind, path="$.kind", allowed=frozenset({"WORKFLOW"}))
        parse_identifier(self.run_id, path="$.runId")
        parse_identifier(self.node_id, path="$.nodeId")
        if self.conversation_id is not None:
            parse_identifier(self.conversation_id, path="$.conversationId")

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "WorkflowInvocationScope":
        data = require_object(
            value,
            path=_path,
            required=frozenset({"kind", "runId", "nodeId"}),
            optional=frozenset({"conversationId"}),
        )
        require_enum(data["kind"], path=f"{_path}.kind", allowed=frozenset({"WORKFLOW"}))
        return cls(
            run_id=parse_identifier(data["runId"], path=f"{_path}.runId"),
            node_id=parse_identifier(data["nodeId"], path=f"{_path}.nodeId"),
            conversation_id=(
                parse_identifier(data["conversationId"], path=f"{_path}.conversationId")
                if "conversationId" in data
                else None
            ),
        )

    def to_mapping(self) -> dict[str, object]:
        result: dict[str, object] = {"kind": self.kind, "runId": self.run_id, "nodeId": self.node_id}
        if self.conversation_id is not None:
            result["conversationId"] = self.conversation_id
        return result


InvocationScope: TypeAlias = ConversationInvocationScope | WorkflowInvocationScope


def parse_invocation_scope(value: object, *, path: str = "$") -> InvocationScope:
    data = require_object(
        value,
        path=path,
        required=frozenset({"kind"}),
        optional=frozenset({"conversationId", "runId", "nodeId"}),
    )
    kind = require_string(data["kind"], path=f"{path}.kind")
    if kind == "CONVERSATION":
        return ConversationInvocationScope.from_mapping(value, _path=path)
    if kind == "WORKFLOW":
        return WorkflowInvocationScope.from_mapping(value, _path=path)
    fail(f"{path}.kind", "invalid_value", "expected CONVERSATION or WORKFLOW")


@dataclass(frozen=True, slots=True)
class TrustedInvocationContext:
    trusted_context: TrustedContext
    invocation_scope: InvocationScope
    control_request_id: str
    contract_revision: str = CONTRACT_REVISION

    def __post_init__(self) -> None:
        parse_contract_revision(self.contract_revision, path="$.contractRevision")
        if not isinstance(self.trusted_context, TrustedContext):
            fail("$.trustedContext", "invalid_type", "expected TrustedContext")
        if not isinstance(self.invocation_scope, (ConversationInvocationScope, WorkflowInvocationScope)):
            fail("$.invocationScope", "invalid_type", "expected an invocation scope")
        parse_identifier(self.control_request_id, path="$.controlRequestId")

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "TrustedInvocationContext":
        data = require_object(
            value,
            path=_path,
            required=frozenset(
                {"contractRevision", "trustedContext", "invocationScope", "controlRequestId"}
            ),
        )
        return cls(
            contract_revision=parse_contract_revision(
                data["contractRevision"], path=f"{_path}.contractRevision"
            ),
            trusted_context=TrustedContext.from_mapping(
                data["trustedContext"], _path=f"{_path}.trustedContext"
            ),
            invocation_scope=parse_invocation_scope(
                data["invocationScope"], path=f"{_path}.invocationScope"
            ),
            control_request_id=parse_identifier(
                data["controlRequestId"], path=f"{_path}.controlRequestId"
            ),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "contractRevision": self.contract_revision,
            "trustedContext": self.trusted_context.to_mapping(),
            "invocationScope": self.invocation_scope.to_mapping(),
            "controlRequestId": self.control_request_id,
        }


@dataclass(frozen=True, slots=True)
class UseSkillRequest:
    skill_key: str

    def __post_init__(self) -> None:
        parse_skill_key(self.skill_key, path="$.skillKey")

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "UseSkillRequest":
        data = require_object(value, path=_path, required=frozenset({"skillKey"}))
        return cls(skill_key=parse_skill_key(data["skillKey"], path=f"{_path}.skillKey"))

    def to_mapping(self) -> dict[str, object]:
        return {"skillKey": self.skill_key}


@dataclass(frozen=True, slots=True)
class AuthorizedMaterialHandle:
    handle_id: str
    logical_path: str
    media_type: str
    byte_size: int
    content_digest: str
    access_mode: str = "READ_ONLY"

    def __post_init__(self) -> None:
        parse_identifier(self.handle_id, path="$.handleId")
        require_enum(self.access_mode, path="$.accessMode", allowed=frozenset({"READ_ONLY"}))
        _parse_logical_path(self.logical_path, path="$.logicalPath")
        require_string(self.media_type, path="$.mediaType", min_length=1, max_length=128)
        require_integer(self.byte_size, path="$.byteSize", minimum=0)
        _parse_digest(self.content_digest, path="$.contentDigest")

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "AuthorizedMaterialHandle":
        data = require_object(
            value,
            path=_path,
            required=frozenset(
                {"handleId", "accessMode", "logicalPath", "mediaType", "byteSize", "contentDigest"}
            ),
        )
        return cls(
            handle_id=parse_identifier(data["handleId"], path=f"{_path}.handleId"),
            access_mode=require_enum(
                data["accessMode"], path=f"{_path}.accessMode", allowed=frozenset({"READ_ONLY"})
            ),
            logical_path=_parse_logical_path(data["logicalPath"], path=f"{_path}.logicalPath"),
            media_type=require_string(
                data["mediaType"], path=f"{_path}.mediaType", min_length=1, max_length=128
            ),
            byte_size=require_integer(data["byteSize"], path=f"{_path}.byteSize", minimum=0),
            content_digest=_parse_digest(data["contentDigest"], path=f"{_path}.contentDigest"),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "handleId": self.handle_id,
            "accessMode": self.access_mode,
            "logicalPath": self.logical_path,
            "mediaType": self.media_type,
            "byteSize": self.byte_size,
            "contentDigest": self.content_digest,
        }


@dataclass(frozen=True, slots=True)
class SkillAssetRef:
    asset_id: str
    asset_type: str = "SKILL"

    def __post_init__(self) -> None:
        require_enum(self.asset_type, path="$.assetType", allowed=frozenset({"SKILL"}))
        parse_identifier(self.asset_id, path="$.assetId")

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "SkillAssetRef":
        data = require_object(value, path=_path, required=frozenset({"assetType", "assetId"}))
        require_enum(data["assetType"], path=f"{_path}.assetType", allowed=frozenset({"SKILL"}))
        return cls(asset_id=parse_identifier(data["assetId"], path=f"{_path}.assetId"))

    def to_mapping(self) -> dict[str, object]:
        return {"assetType": self.asset_type, "assetId": self.asset_id}


@dataclass(frozen=True, slots=True)
class SkillAssetVersionRef:
    asset: SkillAssetRef
    version_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.asset, SkillAssetRef):
            fail("$.asset", "invalid_type", "expected SkillAssetRef")
        parse_identifier(self.version_id, path="$.versionId")

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "SkillAssetVersionRef":
        data = require_object(value, path=_path, required=frozenset({"asset", "versionId"}))
        return cls(
            asset=SkillAssetRef.from_mapping(data["asset"], _path=f"{_path}.asset"),
            version_id=parse_identifier(data["versionId"], path=f"{_path}.versionId"),
        )

    def to_mapping(self) -> dict[str, object]:
        return {"asset": self.asset.to_mapping(), "versionId": self.version_id}


@dataclass(frozen=True, slots=True)
class UseSkillContent:
    instructions: str
    resources: tuple[AuthorizedMaterialHandle, ...]
    required_tool_names: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        require_string(self.instructions, path="$.instructions", min_length=1)
        if not isinstance(self.resources, tuple) or not all(
            isinstance(item, AuthorizedMaterialHandle) for item in self.resources
        ):
            fail("$.resources", "invalid_type", "expected an immutable tuple of material handles")
        logical_paths = [item.logical_path for item in self.resources]
        if len(logical_paths) != len(set(logical_paths)):
            fail("$.resources", "duplicate_resource_path", "resources contains duplicate logicalPath")
        if self.required_tool_names is not None:
            if not isinstance(self.required_tool_names, tuple):
                fail("$.requiredToolNames", "invalid_type", "expected an immutable tuple")
            for index, name in enumerate(self.required_tool_names):
                parse_identifier(name, path=f"$.requiredToolNames[{index}]")
            if len(self.required_tool_names) != len(set(self.required_tool_names)):
                fail("$.requiredToolNames", "duplicate_item", "requiredToolNames must be unique")

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "UseSkillContent":
        data = require_object(
            value,
            path=_path,
            required=frozenset({"instructions", "resources"}),
            optional=frozenset({"requiredToolNames"}),
        )
        resources = require_array(data["resources"], path=f"{_path}.resources")
        required_tool_names: tuple[str, ...] | None = None
        if "requiredToolNames" in data:
            names = require_array(data["requiredToolNames"], path=f"{_path}.requiredToolNames")
            required_tool_names = tuple(
                parse_identifier(name, path=f"{_path}.requiredToolNames[{index}]")
                for index, name in enumerate(names)
            )
        return cls(
            instructions=require_string(
                data["instructions"], path=f"{_path}.instructions", min_length=1
            ),
            resources=tuple(
                AuthorizedMaterialHandle.from_mapping(item, _path=f"{_path}.resources[{index}]")
                for index, item in enumerate(resources)
            ),
            required_tool_names=required_tool_names,
        )

    def to_mapping(self) -> dict[str, object]:
        result: dict[str, object] = {
            "instructions": self.instructions,
            "resources": [item.to_mapping() for item in self.resources],
        }
        if self.required_tool_names is not None:
            result["requiredToolNames"] = list(self.required_tool_names)
        return result


@dataclass(frozen=True, slots=True)
class UseSkillArtifact:
    skill_key: str
    resolved_version: SkillAssetVersionRef
    content_digest: str
    environment: str
    selection: str
    evidence_ref: str

    def __post_init__(self) -> None:
        parse_skill_key(self.skill_key, path="$.skillKey")
        if not isinstance(self.resolved_version, SkillAssetVersionRef):
            fail("$.resolvedVersion", "invalid_type", "expected SkillAssetVersionRef")
        _parse_digest(self.content_digest, path="$.contentDigest")
        require_enum(self.environment, path="$.environment", allowed=frozenset({"PRT", "ONLINE"}))
        require_enum(
            self.selection,
            path="$.selection",
            allowed=frozenset({"PRT_CURRENT", "ONLINE_STABLE", "ONLINE_GRAY"}),
        )
        if self.environment == "PRT" and self.selection != "PRT_CURRENT":
            fail("$.selection", "invalid_selection", "PRT requires PRT_CURRENT")
        if self.environment == "ONLINE" and self.selection not in {"ONLINE_STABLE", "ONLINE_GRAY"}:
            fail("$.selection", "invalid_selection", "ONLINE requires ONLINE_STABLE or ONLINE_GRAY")
        parse_identifier(self.evidence_ref, path="$.evidenceRef")

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "UseSkillArtifact":
        data = require_object(
            value,
            path=_path,
            required=frozenset(
                {"skillKey", "resolvedVersion", "contentDigest", "environment", "selection", "evidenceRef"}
            ),
        )
        return cls(
            skill_key=parse_skill_key(data["skillKey"], path=f"{_path}.skillKey"),
            resolved_version=SkillAssetVersionRef.from_mapping(
                data["resolvedVersion"], _path=f"{_path}.resolvedVersion"
            ),
            content_digest=_parse_digest(data["contentDigest"], path=f"{_path}.contentDigest"),
            environment=require_enum(
                data["environment"], path=f"{_path}.environment", allowed=frozenset({"PRT", "ONLINE"})
            ),
            selection=require_enum(
                data["selection"],
                path=f"{_path}.selection",
                allowed=frozenset({"PRT_CURRENT", "ONLINE_STABLE", "ONLINE_GRAY"}),
            ),
            evidence_ref=parse_identifier(data["evidenceRef"], path=f"{_path}.evidenceRef"),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "skillKey": self.skill_key,
            "resolvedVersion": self.resolved_version.to_mapping(),
            "contentDigest": self.content_digest,
            "environment": self.environment,
            "selection": self.selection,
            "evidenceRef": self.evidence_ref,
        }


@dataclass(frozen=True, slots=True)
class UseSkillResult:
    content: UseSkillContent
    artifact: UseSkillArtifact
    contract_revision: str = CONTRACT_REVISION

    def __post_init__(self) -> None:
        parse_contract_revision(self.contract_revision, path="$.contractRevision")
        if not isinstance(self.content, UseSkillContent):
            fail("$.content", "invalid_type", "expected UseSkillContent")
        if not isinstance(self.artifact, UseSkillArtifact):
            fail("$.artifact", "invalid_type", "expected UseSkillArtifact")

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "UseSkillResult":
        data = require_object(
            value,
            path=_path,
            required=frozenset({"contractRevision", "content", "artifact"}),
        )
        return cls(
            contract_revision=parse_contract_revision(
                data["contractRevision"], path=f"{_path}.contractRevision"
            ),
            content=UseSkillContent.from_mapping(data["content"], _path=f"{_path}.content"),
            artifact=UseSkillArtifact.from_mapping(data["artifact"], _path=f"{_path}.artifact"),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "contractRevision": self.contract_revision,
            "content": self.content.to_mapping(),
            "artifact": self.artifact.to_mapping(),
        }


@dataclass(frozen=True, slots=True)
class SchemaValidPolicy:
    policy_ref: str
    operator: str = "SCHEMA_VALID"
    contract_revision: str = CONTRACT_REVISION

    def __post_init__(self) -> None:
        parse_contract_revision(self.contract_revision, path="$.contractRevision")
        parse_identifier(self.policy_ref, path="$.policyRef")
        require_enum(self.operator, path="$.operator", allowed=frozenset({"SCHEMA_VALID"}))

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "SchemaValidPolicy":
        data = require_object(
            value,
            path=_path,
            required=frozenset({"contractRevision", "policyRef", "operator"}),
        )
        require_enum(data["operator"], path=f"{_path}.operator", allowed=frozenset({"SCHEMA_VALID"}))
        return cls(
            contract_revision=parse_contract_revision(
                data["contractRevision"], path=f"{_path}.contractRevision"
            ),
            policy_ref=parse_identifier(data["policyRef"], path=f"{_path}.policyRef"),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "contractRevision": self.contract_revision,
            "policyRef": self.policy_ref,
            "operator": self.operator,
        }


JsonLiteral: TypeAlias = str | int | float | bool | None


def _parse_json_literal(value: object, *, path: str) -> JsonLiteral:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    fail(path, "invalid_literal", "expected a finite JSON string, number, boolean, or null")


@dataclass(frozen=True, slots=True)
class JsonPointerEqualsPolicy:
    policy_ref: str
    json_pointer: str
    expected_literal: JsonLiteral
    operator: str = "JSON_POINTER_EQUALS"
    contract_revision: str = CONTRACT_REVISION

    def __post_init__(self) -> None:
        parse_contract_revision(self.contract_revision, path="$.contractRevision")
        parse_identifier(self.policy_ref, path="$.policyRef")
        require_enum(self.operator, path="$.operator", allowed=frozenset({"JSON_POINTER_EQUALS"}))
        parsed = require_string(self.json_pointer, path="$.jsonPointer", min_length=1)
        _match(parsed, _JSON_POINTER, path="$.jsonPointer", code="invalid_json_pointer")
        _parse_json_literal(self.expected_literal, path="$.expectedLiteral")

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "JsonPointerEqualsPolicy":
        data = require_object(
            value,
            path=_path,
            required=frozenset(
                {"contractRevision", "policyRef", "operator", "jsonPointer", "expectedLiteral"}
            ),
        )
        require_enum(
            data["operator"], path=f"{_path}.operator", allowed=frozenset({"JSON_POINTER_EQUALS"})
        )
        pointer = require_string(data["jsonPointer"], path=f"{_path}.jsonPointer", min_length=1)
        return cls(
            contract_revision=parse_contract_revision(
                data["contractRevision"], path=f"{_path}.contractRevision"
            ),
            policy_ref=parse_identifier(data["policyRef"], path=f"{_path}.policyRef"),
            json_pointer=_match(
                pointer, _JSON_POINTER, path=f"{_path}.jsonPointer", code="invalid_json_pointer"
            ),
            expected_literal=_parse_json_literal(
                data["expectedLiteral"], path=f"{_path}.expectedLiteral"
            ),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "contractRevision": self.contract_revision,
            "policyRef": self.policy_ref,
            "operator": self.operator,
            "jsonPointer": self.json_pointer,
            "expectedLiteral": self.expected_literal,
        }


ResultInterpretationPolicy: TypeAlias = SchemaValidPolicy | JsonPointerEqualsPolicy


def parse_result_interpretation_policy(
    value: object, *, path: str = "$"
) -> ResultInterpretationPolicy:
    data = require_object(
        value,
        path=path,
        required=frozenset({"contractRevision", "policyRef", "operator"}),
        optional=frozenset({"jsonPointer", "expectedLiteral"}),
    )
    operator = require_string(data["operator"], path=f"{path}.operator")
    if operator == "SCHEMA_VALID":
        return SchemaValidPolicy.from_mapping(value, _path=path)
    if operator == "JSON_POINTER_EQUALS":
        return JsonPointerEqualsPolicy.from_mapping(value, _path=path)
    fail(f"{path}.operator", "invalid_value", "unsupported result policy operator")


@dataclass(frozen=True, slots=True)
class ResultInterpretationPolicySet:
    result_interpretation_policies: tuple[ResultInterpretationPolicy, ...]
    default_success_policy_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.result_interpretation_policies, tuple) or not all(
            isinstance(item, (SchemaValidPolicy, JsonPointerEqualsPolicy))
            for item in self.result_interpretation_policies
        ):
            fail(
                "$.resultInterpretationPolicies",
                "invalid_type",
                "expected an immutable tuple of result policies",
            )
        if not self.result_interpretation_policies:
            fail("$.resultInterpretationPolicies", "too_short", "at least one policy is required")
        default_ref = parse_identifier(
            self.default_success_policy_ref, path="$.defaultSuccessPolicyRef"
        )
        refs = [item.policy_ref for item in self.result_interpretation_policies]
        if len(refs) != len(set(refs)):
            fail(
                "$.resultInterpretationPolicies",
                "duplicate_policy_ref",
                "resultInterpretationPolicies contains duplicate policyRef",
            )
        if default_ref not in refs:
            fail(
                "$.defaultSuccessPolicyRef",
                "unresolved_default_policy",
                "defaultSuccessPolicyRef does not resolve",
            )

    @classmethod
    def from_mapping(cls, value: object, *, _path: str = "$") -> "ResultInterpretationPolicySet":
        data = require_object(
            value,
            path=_path,
            required=frozenset({"resultInterpretationPolicies", "defaultSuccessPolicyRef"}),
        )
        policies = require_array(
            data["resultInterpretationPolicies"], path=f"{_path}.resultInterpretationPolicies"
        )
        return cls(
            result_interpretation_policies=tuple(
                parse_result_interpretation_policy(
                    policy, path=f"{_path}.resultInterpretationPolicies[{index}]"
                )
                for index, policy in enumerate(policies)
            ),
            default_success_policy_ref=parse_identifier(
                data["defaultSuccessPolicyRef"], path=f"{_path}.defaultSuccessPolicyRef"
            ),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "resultInterpretationPolicies": [
                item.to_mapping() for item in self.result_interpretation_policies
            ],
            "defaultSuccessPolicyRef": self.default_success_policy_ref,
        }


_DEFINITION_PARSERS = {
    "contractRevision": parse_contract_revision,
    "identifier": parse_identifier,
    "trustedContext": TrustedContext.from_mapping,
    "trustedInvocationContext": TrustedInvocationContext.from_mapping,
    "invocationScope": parse_invocation_scope,
    "useSkillRequest": UseSkillRequest.from_mapping,
    "skillKey": parse_skill_key,
    "useSkillResult": UseSkillResult.from_mapping,
    "useSkillContent": UseSkillContent.from_mapping,
    "useSkillArtifact": UseSkillArtifact.from_mapping,
    "authorizedMaterialHandle": AuthorizedMaterialHandle.from_mapping,
    "skillAssetVersionRef": SkillAssetVersionRef.from_mapping,
    "resultInterpretationPolicy": parse_result_interpretation_policy,
    "resultInterpretationPolicySet": ResultInterpretationPolicySet.from_mapping,
}


def parse_definition(definition_name: str, value: object) -> object:
    """Parse one explicitly approved schema definition; no generic fallback exists."""

    try:
        parser = _DEFINITION_PARSERS[definition_name]
    except KeyError:
        raise KeyError(f"definition is not approved for this package: {definition_name}") from None
    return parser(value)


def validate_definition(definition_name: str, value: object) -> tuple[ValidationIssue, ...]:
    """Return immutable validation issues without interpreting or executing the payload."""

    try:
        parse_definition(definition_name, value)
    except ContractValidationError as error:
        return error.issues
    return ()
