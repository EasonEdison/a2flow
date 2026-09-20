"""Shared, transport-neutral Ability operation execution.

Callers own Ability resolution, release/version admission, and selection of an
``OperationSpec`` from a trusted registry.  This module does not resolve URLs,
credentials, assets, conversations, runs, or nodes.

The ``ACTION`` authorization mode is available to shared callers, but the
Workflow ``ActionService`` intentionally keeps its existing attempt/outcome
state machine; it must not be replaced by this fail-fast model-call helper.
"""

from dataclasses import dataclass
from typing import Callable

from skillweave_contracts import TrustedContext
from skillweave_contracts.models import parse_result_interpretation_policy

from .models import ActionRejected, json_copy
from .policy import business_succeeded


MODEL_AUTHORIZATION = "MODEL"
ACTION_AUTHORIZATION = "ACTION"


@dataclass(frozen=True)
class OperationSpec:
    """Backend-registered operation and its closed validation policy."""

    execute: Callable
    validate_input: Callable
    validate_result: Callable
    validate_definition: Callable
    model_allowed: bool = False
    action_allowed: bool = False


@dataclass(frozen=True)
class _SuccessEvaluation:
    """Minimal policy input; version admission belongs to the caller."""

    validate_result: Callable
    success_policy: object


def validate_ability_definition(ability, operation):
    """Validate the bounded execution profile without resolving an operation."""

    if not isinstance(operation, OperationSpec):
        raise ActionRejected("OPERATION_NOT_REGISTERED")
    definition = ability.definition
    # This runtime slice has no approved credential or context remapping
    # profile.  Reject authored behavior rather than silently dropping it.
    if definition["credentialRequirements"] or any(
        binding["source"] != "MODEL_ARGUMENT"
        or binding["targetPath"] != binding["sourcePath"]
        for binding in definition["inputBindings"]
    ):
        raise ActionRejected("UNSUPPORTED_ABILITY_BINDING")
    if operation.validate_definition(definition) is not True:
        raise ActionRejected("UNSUPPORTED_ABILITY_PROFILE")
    return definition


def result_policy(ability, policy_ref):
    """Resolve exactly one authored result policy from a resolved Ability."""

    policies = [
        policy
        for policy in ability.definition["resultInterpretationPolicies"]
        if policy["policyRef"] == policy_ref
    ]
    if len(policies) != 1:
        raise ActionRejected("RESULT_POLICY_NOT_FOUND")
    return parse_result_interpretation_policy(policies[0])


def _authorize(operation, authorization):
    if authorization == MODEL_AUTHORIZATION:
        if not operation.model_allowed:
            raise ActionRejected("ABILITY_NOT_MODEL_CALLABLE")
        return
    if authorization == ACTION_AUTHORIZATION:
        if not operation.action_allowed:
            raise ActionRejected("ABILITY_NOT_ACTION_CALLABLE")
        return
    raise ActionRejected("INVALID_ABILITY_AUTHORIZATION")


def execute_ability(
    ability,
    operation,
    arguments,
    owner,
    *,
    authorization,
    success_policy_ref=None,
):
    """Execute one pre-admitted Ability through a registered operation.

    The caller must check the current version/closure and bind ``ability`` to
    the requested key before entering this function.  ``owner`` is a trusted
    backend value and is never inferred from arguments or model output.
    """

    if type(owner) is not TrustedContext:
        raise ActionRejected("TRUSTED_CONTEXT_REQUIRED")
    definition = validate_ability_definition(ability, operation)
    _authorize(operation, authorization)
    if operation.validate_input(arguments) is not True:
        raise ActionRejected("INVALID_ABILITY_INPUT")

    policy_ref = (
        definition["defaultSuccessPolicyRef"]
        if success_policy_ref is None
        else success_policy_ref
    )
    policy = result_policy(ability, policy_ref)
    result = json_copy(operation.execute(json_copy(arguments), owner))
    evaluation = _SuccessEvaluation(operation.validate_result, policy)
    if not business_succeeded(evaluation, result):
        raise ActionRejected("ABILITY_RESULT_NOT_SUCCESS")
    return {
        "abilityKey": ability.publication_metadata.ability_key,
        "output": result,
        "versionId": ability.version_id,
    }
