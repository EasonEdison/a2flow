"""Thin adapter from shared Contracts validation to Capability issues."""

from collections.abc import Mapping

from skillweave_contracts import (
    ContractValidationError,
    ResultInterpretationPolicySet,
)

from .models import ValidationIssue


class SharedResultPolicySetValidator:
    """Delegates policy-set shape validation without evaluating a result."""

    def validate(
        self,
        policy_set: Mapping[str, object],
    ) -> tuple[ValidationIssue, ...]:
        """Preserve every shared validation issue in Capability-domain form."""

        try:
            ResultInterpretationPolicySet.from_mapping(policy_set)
        except ContractValidationError as error:
            return tuple(
                ValidationIssue(issue.code, issue.path, issue.message)
                for issue in error.issues
            )
        return ()
