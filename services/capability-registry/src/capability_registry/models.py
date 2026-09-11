"""Immutable value objects for authored Ability validation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One stable validation failure located by a JSON-style path."""

    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class AdapterOperationDescriptor:
    """Trusted adapter-operation metadata; it never carries credential values."""

    operation_ref: str
    input_paths: frozenset[str]
    credential_slots: frozenset[str]


@dataclass(frozen=True, slots=True)
class AbilityPublicationMetadata:
    """Validated immutable metadata safe to place in an Ability publication."""

    ability_key: str
    adapter_operation_ref: str
    model_argument_paths: tuple[str, ...]
    trusted_context_paths: tuple[str, ...]
    credential_slots: tuple[str, ...]
    result_policy_refs: tuple[str, ...]
    default_success_policy_ref: str


@dataclass(frozen=True, slots=True)
class AbilityDefinitionValidation:
    """Validation outcome; metadata exists only when there are no issues."""

    issues: tuple[ValidationIssue, ...]
    metadata: AbilityPublicationMetadata | None

    @property
    def is_valid(self) -> bool:
        """Return whether publication metadata was produced without issues."""

        return not self.issues and self.metadata is not None
