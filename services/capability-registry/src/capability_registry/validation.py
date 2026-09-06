"""Authored Ability definition validation and publication metadata assembly."""

from collections.abc import Mapping
import re

from .models import (
    AbilityDefinitionValidation,
    AbilityPublicationMetadata,
    ValidationIssue,
)
from .ports import AdapterOperationCatalogPort, ResultPolicySetValidatorPort


_ABILITY_FIELDS = frozenset(
    {
        "abilityKey",
        "adapterOperationRef",
        "credentialRequirements",
        "defaultSuccessPolicyRef",
        "inputBindings",
        "modelArgumentSchema",
        "outputSchema",
        "resolvedInputSchema",
        "resultInterpretationPolicies",
    },
)
_REQUIRED_ABILITY_FIELDS = _ABILITY_FIELDS
_RESERVED_MODEL_FIELDS = frozenset(
    {
        "authorizationContext",
        "credentialRef",
        "credentialRefs",
        "environment",
        "releaseRef",
        "releaseVersion",
        "userId",
    },
)
_ALLOWED_BINDING_SOURCES = frozenset({"MODEL_ARGUMENT", "TRUSTED_CONTEXT"})
_TRUSTED_CONTEXT_PATHS = frozenset({"/environment", "/userId"})
_IDENTIFIER_PATTERN = re.compile(r"^(?!.*[\r\n])[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_JSON_POINTER_PATTERN = re.compile(r"^(?:/(?:[^~/]|~0|~1)*)+$")


def _issue(code: str, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, path=path, message=message)


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER_PATTERN.fullmatch(value) is not None


def _pointer_for_property(property_name: str) -> str:
    return "/" + property_name.replace("~", "~0").replace("/", "~1")


def _is_pointer(value: object) -> bool:
    return isinstance(value, str) and _JSON_POINTER_PATTERN.fullmatch(value) is not None


def _pointer_root(pointer: str) -> str:
    encoded = pointer.split("/", 2)[1]
    return encoded.replace("~1", "/").replace("~0", "~")


def _iter_schema_property_names(schema: object, path: str = "/modelArgumentSchema"):
    if not isinstance(schema, Mapping):
        return
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return
    for name, child in properties.items():
        child_path = "%s/properties/%s" % (path, name)
        yield name, child_path
        for nested in _iter_schema_property_names(child, child_path):
            yield nested


def _find_target_conflicts(target_paths: list[tuple[int, str]]) -> list[ValidationIssue]:
    issues = []
    first_index_by_path = {}
    for index, target_path in target_paths:
        if target_path in first_index_by_path:
            issues.append(
                _issue(
                    "INPUT_BINDING_TARGET_DUPLICATE",
                    "/inputBindings/%d/targetPath" % index,
                    "binding targetPath must be unique",
                ),
            )
        else:

            first_index_by_path[target_path] = index

    unique_paths = tuple(first_index_by_path)
    for left_index, left_path in enumerate(unique_paths):
        for right_path in unique_paths[left_index + 1 :]:
            if right_path.startswith(left_path + "/") or left_path.startswith(right_path + "/"):
                conflicting_index = first_index_by_path[right_path]
                issues.append(
                    _issue(
                        "INPUT_BINDING_TARGET_OVERLAP",
                        "/inputBindings/%d/targetPath" % conflicting_index,
                        "binding target paths must not be ancestors of one another",
                    ),
                )
    return issues

class AbilityDefinitionValidator:
    """Validates authored metadata without executing an Ability or its policy."""

    def __init__(
        self,
        operation_catalog: AdapterOperationCatalogPort,
        policy_set_validator: ResultPolicySetValidatorPort,
    ) -> None:
        self._operation_catalog = operation_catalog
        self._policy_set_validator = policy_set_validator

    def validate(self, payload: Mapping[str, object]) -> AbilityDefinitionValidation:
        """Validate one authored definition and return immutable publication metadata."""

        issues = []
        if not isinstance(payload, Mapping):
            issue = _issue(
                "ABILITY_DEFINITION_INVALID",
                "/",
                "ability definition must be an object",
            )
            return AbilityDefinitionValidation(issues=(issue,), metadata=None)

        unsupported_fields = set(payload) - _ABILITY_FIELDS
        for field_name in sorted(
            unsupported_fields, key=lambda value: (type(value).__name__, repr(value)),
        ):
            issues.append(
                _issue(
                    "ABILITY_FIELD_UNSUPPORTED",
                    "/%s" % field_name,
                    "ability definition contains an unsupported field",
                ),
            )
        for field_name in sorted(_REQUIRED_ABILITY_FIELDS - set(payload)):
            issues.append(
                _issue(
                    "ABILITY_FIELD_REQUIRED",
                    "/%s" % field_name,
                    "ability definition field is required",
                ),
            )
        if issues:
            return AbilityDefinitionValidation(issues=tuple(issues), metadata=None)

        ability_key = payload["abilityKey"]
        if not _is_identifier(ability_key):
            issues.append(
                _issue(
                    "ABILITY_KEY_INVALID",
                    "/abilityKey",
                    "abilityKey must use the approved identifier syntax",
                ),
            )

        operation_ref = payload["adapterOperationRef"]
        if not _is_identifier(operation_ref):
            issues.append(
                _issue(
                    "ADAPTER_OPERATION_REF_INVALID",
                    "/adapterOperationRef",
                    "adapterOperationRef must use the approved identifier syntax",
                ),
            )

        model_schema = payload["modelArgumentSchema"]
        if (
            not isinstance(model_schema, Mapping)
            or model_schema.get("type") != "object"
            or model_schema.get("additionalProperties") is not False
            or not isinstance(model_schema.get("properties"), Mapping)
        ):
            issues.append(
                _issue(
                    "MODEL_ARGUMENT_SCHEMA_INVALID",
                    "/modelArgumentSchema",
                    "modelArgumentSchema must be a closed object schema",
                ),
            )
            model_properties = {}
        else:
            model_properties = model_schema["properties"]
            for property_name, property_path in _iter_schema_property_names(model_schema):
                if property_name in _RESERVED_MODEL_FIELDS:
                    issues.append(
                        _issue(
                            "MODEL_ARGUMENT_RESERVED_FIELD",
                            property_path,
                            "server-owned field must not be model-visible",
                        ),
                    )

        resolved_schema = payload["resolvedInputSchema"]
        resolved_required_paths = ()
        if not isinstance(resolved_schema, Mapping):
            issues.append(
                _issue(
                    "RESOLVED_INPUT_SCHEMA_UNSUPPORTED",
                    "/resolvedInputSchema",
                    "resolvedInputSchema must use the supported closed object profile",
                ),
            )
        else:
            resolved_properties = resolved_schema.get("properties")
            resolved_required = resolved_schema.get("required", [])
            supported_profile = (
                resolved_schema.get("type") == "object"
                and resolved_schema.get("additionalProperties") is False
                and isinstance(resolved_properties, Mapping)
                and isinstance(resolved_required, list)
                and all(isinstance(name, str) for name in resolved_required)
                and len(resolved_required) == len(set(resolved_required))
                and all(name in resolved_properties for name in resolved_required)
            )
            if not supported_profile:
                issues.append(
                    _issue(
                        "RESOLVED_INPUT_SCHEMA_UNSUPPORTED",
                        "/resolvedInputSchema",
                        "resolvedInputSchema must use the supported closed object profile",
                    ),
                )
            else:
                resolved_required_paths = tuple(
                    _pointer_for_property(name) for name in resolved_required
                )

        if not isinstance(payload["outputSchema"], Mapping):
            issues.append(
                _issue(
                    "ABILITY_SCHEMA_INVALID",
                    "/outputSchema",
                    "schema field must be an object",
                ),
            )

        bindings = payload["inputBindings"]
        model_paths = []
        trusted_paths = []
        target_paths = []
        if not isinstance(bindings, list) or not bindings:
            issues.append(
                _issue(
                    "INPUT_BINDINGS_INVALID",
                    "/inputBindings",
                    "inputBindings must be a nonempty array",
                ),
            )
            bindings = []
        for index, binding in enumerate(bindings):
            binding_path = "/inputBindings/%d" % index
            if not isinstance(binding, Mapping) or set(binding) != {
                "source",
                "sourcePath",
                "targetPath",
            }:
                issues.append(
                    _issue(
                        "INPUT_BINDING_INVALID",
                        binding_path,
                        "binding must contain only source, sourcePath and targetPath",
                    ),
                )
                continue
            source = binding["source"]
            source_path = binding["sourcePath"]
            target_path = binding["targetPath"]
            if not isinstance(source, str) or source not in _ALLOWED_BINDING_SOURCES:
                issues.append(
                    _issue(
                        "INPUT_BINDING_SOURCE_UNSUPPORTED",
                        binding_path + "/source",
                        "binding source is not released in this slice",
                    ),
                )
            if not _is_pointer(target_path):
                issues.append(
                    _issue(
                        "INPUT_BINDING_POINTER_INVALID",
                        binding_path + "/targetPath",
                        "targetPath must be a nonempty RFC 6901 JSON Pointer",
                    ),
                )
            else:
                target_paths.append((index, target_path))
            if not _is_pointer(source_path):
                issues.append(
                    _issue(
                        "INPUT_BINDING_POINTER_INVALID",
                        binding_path + "/sourcePath",
                        "sourcePath must be a nonempty RFC 6901 JSON Pointer",
                    ),
                )
                continue
            if source == "MODEL_ARGUMENT":
                if _pointer_root(source_path) not in model_properties:
                    issues.append(
                        _issue(
                            "MODEL_ARGUMENT_SOURCE_UNDECLARED",
                            binding_path + "/sourcePath",
                            "model sourcePath must reference a declared model property",
                        ),
                    )
                if (
                    _is_pointer(target_path)
                    and _pointer_root(target_path) in _RESERVED_MODEL_FIELDS
                ):
                    issues.append(
                        _issue(
                            "MODEL_ARGUMENT_TARGET_SERVER_OWNED",
                            binding_path + "/targetPath",
                            "model arguments must not construct a server-owned input",
                        ),
                    )
                if isinstance(target_path, str):
                    model_paths.append(target_path)
            elif source == "TRUSTED_CONTEXT":
                if source_path not in _TRUSTED_CONTEXT_PATHS:
                    issues.append(
                        _issue(
                            "TRUSTED_CONTEXT_SOURCE_UNSUPPORTED",
                            binding_path + "/sourcePath",
                            "trusted sourcePath is outside the approved subset",
                        ),
                    )
                if isinstance(target_path, str):
                    trusted_paths.append(target_path)
        issues.extend(_find_target_conflicts(target_paths))

        bound_target_paths = frozenset(path for _, path in target_paths)
        for required_path in resolved_required_paths:
            if required_path not in bound_target_paths:
                issues.append(
                    _issue(
                        "REQUIRED_INPUT_SOURCE_MISSING",
                        "/resolvedInputSchema/required",
                        "every required resolved input must have exactly one source",
                    ),
                )

        requirements = payload["credentialRequirements"]
        credential_slot_entries = []
        if not isinstance(requirements, list):
            issues.append(
                _issue(
                    "CREDENTIAL_REQUIREMENTS_INVALID",
                    "/credentialRequirements",
                    "credentialRequirements must be an array",
                ),
            )
            requirements = []
        for index, requirement in enumerate(requirements):
            requirement_path = "/credentialRequirements/%d" % index
            if not isinstance(requirement, Mapping) or set(requirement) != {"required", "slotId"}:
                issues.append(
                    _issue(
                        "CREDENTIAL_REQUIREMENT_FIELD_UNSUPPORTED",
                        requirement_path,
                        "credential requirement may contain only slotId and required",
                    ),
                )
                continue
            if not _is_identifier(requirement["slotId"]) or not isinstance(requirement["required"], bool):
                issues.append(
                    _issue(
                        "CREDENTIAL_REQUIREMENT_INVALID",
                        requirement_path,
                        "credential requirement has an invalid slotId or required flag",
                    ),
                )
                continue
            credential_slot_entries.append((index, requirement["slotId"]))
        credential_slots = [slot_id for _, slot_id in credential_slot_entries]

        policy_set = {
            "resultInterpretationPolicies": payload["resultInterpretationPolicies"],
            "defaultSuccessPolicyRef": payload["defaultSuccessPolicyRef"],
        }
        issues.extend(self._policy_set_validator.validate(policy_set))

        operation = None
        if _is_identifier(operation_ref):
            operation = self._operation_catalog.lookup(operation_ref)

            if operation is None:
                issues.append(
                    _issue(
                        "ADAPTER_OPERATION_NOT_FOUND",
                        "/adapterOperationRef",
                        "adapter operation was not found",
                    ),
                )
            else:
                for binding_index, target_path in target_paths:
                    if target_path not in operation.input_paths:
                        issues.append(
                            _issue(
                                "ADAPTER_INPUT_UNSUPPORTED",
                                "/inputBindings/%d/targetPath" % binding_index,
                                "adapter operation does not accept the target path",
                            ),
                        )
                for requirement_index, slot_id in credential_slot_entries:
                    if slot_id not in operation.credential_slots:
                        issues.append(
                            _issue(
                                "CREDENTIAL_SLOT_UNSUPPORTED",
                                "/credentialRequirements/%d/slotId" % requirement_index,
                                "adapter operation does not declare the credential slot",
                            ),
                        )
        policies = payload["resultInterpretationPolicies"]
        if not isinstance(policies, list):
            policies = []
        policy_refs = tuple(
            policy["policyRef"]
            for policy in policies
            if isinstance(policy, Mapping) and isinstance(policy.get("policyRef"), str)
        )

        if issues or operation is None:
            return AbilityDefinitionValidation(issues=tuple(issues), metadata=None)

        metadata = AbilityPublicationMetadata(
            ability_key=ability_key,
            adapter_operation_ref=operation.operation_ref,
            model_argument_paths=tuple(model_paths),
            trusted_context_paths=tuple(trusted_paths),
            credential_slots=tuple(credential_slots),
            result_policy_refs=policy_refs,
            default_success_policy_ref=payload["defaultSuccessPolicyRef"],
        )
        return AbilityDefinitionValidation(issues=(), metadata=metadata)
