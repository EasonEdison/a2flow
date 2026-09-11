"""Ports required by authored Ability validation."""

from collections.abc import Mapping, Sequence
from typing import Protocol

from .models import AdapterOperationDescriptor, ValidationIssue


class AdapterOperationCatalogPort(Protocol):
    """Looks up trusted operation metadata without invoking the operation."""

    def lookup(self, operation_ref: str) -> AdapterOperationDescriptor | None:
        """Return the descriptor for an authored operation reference."""

        ...


class ResultPolicySetValidatorPort(Protocol):
    """Delegates shared policy-set validation to the Contracts package."""

    def validate(
        self,
        policy_set: Mapping[str, object],
    ) -> Sequence[ValidationIssue]:
        """Return shared structural and semantic validation issues."""

        ...
