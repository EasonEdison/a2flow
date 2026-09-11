"""Small MVP08 ports over the asset package; no scenario implementation in core."""

from dataclasses import dataclass
from typing import Callable
import json

from skill_registry import (
    InvocationScope as RegistryScope, TrustedContext as RegistryOwner,
    TrustedInvocationContext as RegistryContext, UseSkillRequest, use_skill,
)
from skillweave_contracts.models import parse_result_interpretation_policy

from .models import ActionConfig, ActionRejected, json_copy
from .policy import business_succeeded
from .service import require_owner


@dataclass(frozen=True)
class OperationSpec:
    execute: Callable
    validate_input: Callable
    validate_result: Callable
    validate_definition: Callable
    model_allowed: bool = False
    action_allowed: bool = False


class RuntimeAssets:
    def __init__(self, reader, run, operations, definition, *, bound_node_id=None):
        self.reader, self.run = reader, run
        self.operations, self.definition = dict(operations), json_copy(definition)
        node_ids = frozenset(node["nodeId"] for node in self.definition["nodes"])
        if bound_node_id is not None and bound_node_id not in node_ids:
            raise ValueError("BOUND_NODE_NOT_FOUND")
        self.bound_node_id = bound_node_id

    def current_versions(self):
        return tuple(self.reader.versions(self.run.owner, self.run.definition_key))

    def check_versions(self):
        if dict(self.current_versions()) != dict(self.run.versions):
            raise ActionRejected("RESET_REQUIRED")

    def _context(self, context):
        require_owner(context.trusted_context)
        if (context.trusted_context != self.run.owner
                or context.invocation_scope.kind != "WORKFLOW"
                or context.invocation_scope.run_id != self.run.run_id):
            raise ActionRejected("RUN_BINDING_MISMATCH")
        self.check_versions()
        return self.run.context(self.bound_node_id) if self.bound_node_id is not None else context

    def context(self, context):
        return self._context(context)

    def skill(self, skill_key, context):
        context = self._context(context)
        node = next((n for n in self.definition["nodes"]
                     if n["nodeId"] == context.invocation_scope.node_id), None)
        if node is None or node["skillKey"] != skill_key:
            raise ActionRejected("SKILL_NOT_ALLOWED")
        scope = context.invocation_scope
        trusted = RegistryContext(
            context.contract_revision,
            RegistryOwner(context.trusted_context.user_id, context.trusted_context.environment),
            RegistryScope(kind=scope.kind, run_id=scope.run_id, node_id=scope.node_id,
                          conversation_id=getattr(scope, "conversation_id", None)),
            context.control_request_id,
        )
        return use_skill(UseSkillRequest(skill_key=skill_key), trusted, self.reader).to_mapping()

    def application(self, key, context):
        context = self._context(context)
        resolved = self.reader.resolve_application(key, context)
        current = dict(self.current_versions())
        recorded = tuple(resolved["recordedVersions"])
        if not recorded or any(current.get(key) != version for key, version in recorded):
            raise ActionRejected("RESET_REQUIRED")
        # Validated subset resolution is augmented by the full run closure.
        resolved = {**resolved, "recordedVersions": tuple(current.items())}
        application = resolved["application"]
        if (application["asset"]["applicationKey"] != key
                or application["asset"]["protocolProfileRef"] != "a2flow.mvp08.v1"):
            raise ActionRejected("UNSUPPORTED_APPLICATION_PROFILE")
        return resolved

    def _ability(self, ability_key, context):
        context = self._context(context)
        ability = self.reader.resolve_ability(ability_key, context)
        if ability.publication_metadata.ability_key != ability_key:
            raise ActionRejected("ABILITY_BINDING_MISMATCH")
        if f"ABILITY:{ability.asset_id}" not in dict(self.run.versions):
            raise ActionRejected("ABILITY_NOT_ALLOWED")
        definition = ability.definition
        # MVP has no credential/context remapping profile. Reject instead of
        # ignoring an authored binding that would change operation inputs.
        if definition["credentialRequirements"] or any(
            b["source"] != "MODEL_ARGUMENT" or b["targetPath"] != b["sourcePath"]
            for b in definition["inputBindings"]
        ):
            raise ActionRejected("UNSUPPORTED_ABILITY_BINDING")
        spec = self.operations.get(ability.operation_ref)
        if not isinstance(spec, OperationSpec):
            raise ActionRejected("OPERATION_NOT_REGISTERED")
        if spec.validate_definition(definition) is not True:
            raise ActionRejected("UNSUPPORTED_ABILITY_PROFILE")
        return ability, spec

    @staticmethod
    def _policy(ability, policy_ref):
        policies = [p for p in ability.definition["resultInterpretationPolicies"]
                    if p["policyRef"] == policy_ref]
        if len(policies) != 1:
            raise ActionRejected("RESULT_POLICY_NOT_FOUND")
        return parse_result_interpretation_policy(policies[0])

    def execute_ability(self, ability_key, arguments, context):
        ability, spec = self._ability(ability_key, context)
        if not spec.model_allowed:
            raise ActionRejected("ABILITY_NOT_MODEL_CALLABLE")
        if spec.validate_input(arguments) is not True:
            raise ActionRejected("INVALID_ABILITY_INPUT")
        self.check_versions()
        result = json_copy(spec.execute(json_copy(arguments), self.run.owner))
        config = ActionConfig(
            "model-operation", ability.operation_ref, self.current_versions(),
            self._policy(ability, ability.definition["defaultSuccessPolicyRef"]),
            False, spec.validate_input, spec.validate_result,
        )
        if not business_succeeded(config, result):
            raise ActionRejected("ABILITY_RESULT_NOT_SUCCESS")
        return {"abilityKey": ability_key, "output": result, "versionId": ability.version_id}

    def versions(self, interaction):
        self._context(interaction.context)
        return self.current_versions()

    def action(self, interaction, action_name):
        resolved = self.application(interaction.application_key, interaction.context)
        if resolved["resolvedVersion"]["versionId"] != interaction.application_version:
            raise ActionRejected("RESET_REQUIRED")
        matches = [p for p in resolved["application"]["actionPolicies"] if p["actionName"] == action_name]
        if len(matches) != 1:
            raise ActionRejected("ACTION_NOT_ALLOWED")
        policy = matches[0]
        key, separator, version = policy["abilityReleaseRef"].rpartition("@")
        if not separator or not key or not version:
            raise ActionRejected("INVALID_ABILITY_RELEASE")
        ability, spec = self._ability(key, interaction.context)
        if ability.version_id != version or not spec.action_allowed:
            raise ActionRejected("ACTION_NOT_ALLOWED")
        if interaction.display_json is None:
            raise ActionRejected("CARD_NOT_FOUND")
        card = json.loads(interaction.display_json)
        allowed = frozenset(option["value"] for option in card["data"]["options"])
        def valid_input(value):
            return (spec.validate_input(value) is True and value.get("optionId") in allowed
                    and value.get("confirmed") is True)
        completes = policy["completeInteractionOnSuccess"]
        if type(completes) is not bool:
            raise ActionRejected("INVALID_ACTION_POLICY")
        return ActionConfig(action_name, ability.operation_ref, self.current_versions(),
                            self._policy(ability, policy["successPolicyRef"]), completes,
                            valid_input, spec.validate_result)

    def executor(self, config, inputs, owner):
        if owner != self.run.owner:
            raise ActionRejected("NOT_AUTHORIZED")
        spec = self.operations.get(config.operation_ref)
        if not isinstance(spec, OperationSpec) or not spec.action_allowed:
            raise ActionRejected("OPERATION_NOT_REGISTERED")
        return spec.execute(inputs, owner)
