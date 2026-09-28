"""Conversation-bound admission for Skill Ability and Application tools.

This adapter deliberately has no Workflow run, node, checkpoint or interrupt.
It resolves one active Skill from the trusted conversation owner, records that
Skill's exact dependency closure, and admits only operations bound by that
Skill.  The called operation owns business retry and idempotency semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, TypedDict

from skill_registry import (
    InvocationScope as RegistryScope,
    TrustedContext as RegistryOwner,
    TrustedInvocationContext as RegistryContext,
    UseSkillRequest,
    use_skill,
)
from skillweave_contracts import CONTRACT_REVISION, TrustedContext, TrustedInvocationContext

from ..ability_execution import (
    MODEL_AUTHORIZATION,
    OperationSpec,
    execute_ability as execute_resolved_ability,
    validate_ability_definition,
)
from ..application_runtime import ApplicationRuntime
from ..models import ActionRejected, json_copy
from ..service import require_owner
from .cards import JsonObject


_CHAT_SKILL_TOOLS = frozenset({"execute_ability", "render_application"})
_APPLICATION_CONTRACT_TOOL = "query_skill_dependencies"
_APPLICATION_USAGE = (
    "Call render_application with this appCode and params that satisfy "
    "paramsSchema."
)


class ApplicationContract(TypedDict):
    """Published model input contract for one admitted Application."""

    appCode: str
    description: str
    usage: str
    paramsSchema: JsonObject


class SkillDependencies(TypedDict):
    """Bound Application contracts returned to the model."""

    applications: list[ApplicationContract]


def _versions(value):
    """Return one deterministic, duplicate-free version closure."""

    if not isinstance(value, (list, tuple)):
        raise ActionRejected("INVALID_RECORDED_VERSIONS")
    result = []
    seen = set()
    for item in value:
        if (
            not isinstance(item, (list, tuple))
            or len(item) != 2
            or type(item[0]) is not str
            or not item[0]
            or type(item[1]) is not str
            or not item[1]
            or item[0] in seen
        ):
            raise ActionRejected("INVALID_RECORDED_VERSIONS")
        seen.add(item[0])
        result.append((item[0], item[1]))
    if not result:
        raise ActionRejected("INVALID_RECORDED_VERSIONS")
    return tuple(sorted(result))


@dataclass(frozen=True)
class _SkillAdmission:
    skill_key: str
    asset_id: str
    version_id: str
    recorded_versions: tuple[tuple[str, str], ...]
    required_tools: frozenset[str]
    ability_keys: frozenset[str]
    application_keys: frozenset[str]


class ChatAssets:
    """Resolve and execute the active Skill in one trusted conversation."""

    def __init__(
        self,
        reader: Any,
        operation_registry: dict[str, OperationSpec],
        owner: TrustedContext,
        conversation_id: str,
        control_request_id: str,
        card_sink: Callable[..., dict[str, Any]],
        application_validator: Callable[..., bool],
        data_validator: Callable[..., bool],
    ) -> None:
        require_owner(owner)
        if type(conversation_id) is not str or not conversation_id:
            raise ValueError("CONVERSATION_ID_REQUIRED")
        if type(control_request_id) is not str or not control_request_id:
            raise ValueError("CONTROL_REQUEST_ID_REQUIRED")
        if not callable(card_sink):
            raise ValueError("CARD_SINK_REQUIRED")
        if not callable(data_validator):
            raise ValueError("APPLICATION_DATA_VALIDATOR_REQUIRED")
        self._reader = reader
        self._operations = dict(operation_registry)
        self._owner = owner
        self._conversation_id = conversation_id
        self._control_request_id = control_request_id
        self._card_sink = card_sink
        self._applications = ApplicationRuntime(
            application_validator, data_validator,
        )
        self._admission: _SkillAdmission | None = None
        self._waiting_action: dict[str, Any] | None = None
        self._render_observations: dict[str, dict[str, Any]] = {}
        self._render_lock = Lock()

    @property
    def owner(self) -> TrustedContext:
        return self._owner

    @property
    def conversation_id(self) -> str:
        return self._conversation_id

    @property
    def control_request_id(self) -> str:
        return self._control_request_id

    def admitted_tool_names(self) -> frozenset[str]:
        """Return the current turn's model-callable Skill tools."""

        admitted = self._admission
        if admitted is None:
            return frozenset()
        tools = set(admitted.required_tools)
        if (
            admitted.application_keys
            and "render_application" in admitted.required_tools
        ):
            tools.add(_APPLICATION_CONTRACT_TOOL)
        return frozenset(tools)

    def begin_turn(self):
        """Clear turn-local Skill admission and interaction state."""

        self._admission = None
        with self._render_lock:
            self._waiting_action = None
            self._render_observations.clear()

    def waiting_action(self):
        with self._render_lock:
            return (
                None
                if self._waiting_action is None
                else json_copy(self._waiting_action)
            )

    def validate_context(self, context):
        """Reject a Loop/asset-factory binding mismatch before asset access."""

        if type(context) is not TrustedInvocationContext:
            raise ActionRejected("CONVERSATION_BINDING_MISMATCH")
        scope = context.invocation_scope
        if (
            context.trusted_context != self._owner
            or scope.kind != "CONVERSATION"
            or scope.conversation_id != self._conversation_id
            or context.control_request_id != self._control_request_id
        ):
            raise ActionRejected("CONVERSATION_BINDING_MISMATCH")
        return context

    def _registry_context(self):
        return RegistryContext(
            contract_revision=CONTRACT_REVISION,
            trusted_context=RegistryOwner(
                user_id=self._owner.user_id,
                environment=self._owner.environment,
            ),
            invocation_scope=RegistryScope(
                kind="CONVERSATION",
                conversation_id=self._conversation_id,
                run_id=None,
                node_id=None,
            ),
            control_request_id=self._control_request_id,
        )

    def _resolve_skill(self, skill_key):
        resolved = self._reader.resolve_asset("SKILL", skill_key, self._owner)
        if (
            type(resolved) is not dict
            or resolved.get("kind") != "SKILL"
            or resolved.get("key") != skill_key
            or type(resolved.get("assetId")) is not str
            or not resolved["assetId"]
            or type(resolved.get("versionId")) is not str
            or not resolved["versionId"]
            or type(resolved.get("definition")) is not dict
            or type(resolved.get("dependencies")) is not list
        ):
            raise ActionRejected("INVALID_SKILL_RESOLUTION")
        definition = resolved["definition"]
        tools = definition.get("requiredToolNames")
        if (
            type(tools) is not list
            or any(type(name) is not str or not name for name in tools)
            or len(tools) != len(set(tools))
            or not set(tools).issubset(_CHAT_SKILL_TOOLS)
        ):
            raise ActionRejected("SKILL_TOOLS_NOT_AVAILABLE")
        dependencies = []
        for dependency in resolved["dependencies"]:
            if (
                type(dependency) is not dict
                or set(dependency) != {"kind", "key"}
                or type(dependency["kind"]) is not str
                or type(dependency["key"]) is not str
                or not dependency["key"]
            ):
                raise ActionRejected("INVALID_SKILL_RESOLUTION")
            dependencies.append((dependency["kind"], dependency["key"]))
        recorded = _versions(resolved.get("recordedVersions"))
        if dict(recorded).get("SKILL:" + resolved["assetId"]) != resolved["versionId"]:
            raise ActionRejected("INVALID_SKILL_RESOLUTION")
        abilities = frozenset(key for kind, key in dependencies if kind == "ABILITY")
        applications = frozenset(
            key for kind, key in dependencies if kind == "APPLICATION"
        )
        if ("execute_ability" in tools) != bool(abilities):
            raise ActionRejected("SKILL_ABILITY_BINDING_MISMATCH")
        if ("render_application" in tools) != bool(applications):
            raise ActionRejected("SKILL_APPLICATION_BINDING_MISMATCH")
        return _SkillAdmission(
            skill_key,
            resolved["assetId"],
            resolved["versionId"],
            recorded,
            frozenset(tools),
            abilities,
            applications,
        )

    def admit_skill(self, skill_key: str) -> dict[str, Any]:
        """Load one Skill and atomically replace the active admission."""

        candidate = self._resolve_skill(skill_key)
        result = use_skill(
            UseSkillRequest(skill_key=skill_key),
            self._registry_context(),
            self._reader,
        ).to_mapping()
        try:
            loaded_version = result["artifact"]["resolvedVersion"]["versionId"]
        except (KeyError, TypeError):
            raise ActionRejected("INVALID_SKILL_RESOLUTION") from None
        if loaded_version != candidate.version_id:
            raise ActionRejected("RESET_REQUIRED")
        current = self._resolve_skill(skill_key)
        if current != candidate:
            raise ActionRejected("RESET_REQUIRED")
        self._admission = candidate
        return json_copy(result)

    def _require_admission(self) -> _SkillAdmission:
        if self._admission is None:
            raise ActionRejected("SKILL_NOT_ADMITTED")
        return self._admission

    def check_versions(self, expected_versions: Any = None) -> tuple[tuple[str, str], ...]:
        """Compare the current closure with admitted or persisted versions."""

        admitted = self._require_admission()
        expected = (
            admitted.recorded_versions
            if expected_versions is None
            else _versions(expected_versions)
        )
        if expected != admitted.recorded_versions:
            raise ActionRejected("RESET_REQUIRED")
        current = self._resolve_skill(admitted.skill_key).recorded_versions
        if current != expected:
            raise ActionRejected("RESET_REQUIRED")
        return current

    def _ability(self, ability_key, *, model_call):
        admitted = self._require_admission()
        if model_call and (
            "execute_ability" not in admitted.required_tools
            or ability_key not in admitted.ability_keys
        ):
            raise ActionRejected("ABILITY_NOT_ALLOWED")
        ability = self._reader.resolve_ability(ability_key, self._owner)
        if ability.publication_metadata.ability_key != ability_key:
            raise ActionRejected("ABILITY_BINDING_MISMATCH")
        if dict(admitted.recorded_versions).get(
            "ABILITY:" + ability.asset_id
        ) != ability.version_id:
            raise ActionRejected("ABILITY_NOT_ALLOWED")
        spec = self._operations.get(ability.operation_ref)
        validate_ability_definition(ability, spec)
        return ability, spec

    def execute_ability(self, ability_key, arguments):
        """Execute one model-callable Ability bound by the active Skill."""

        self.check_versions()
        ability, spec = self._ability(ability_key, model_call=True)
        return execute_resolved_ability(
            ability,
            spec,
            arguments,
            self._owner,
            authorization=MODEL_AUTHORIZATION,
            before_dispatch=self.check_versions,
        )

    def _application(self, application_key):
        admitted = self._require_admission()
        if (
            "render_application" not in admitted.required_tools
            or application_key not in admitted.application_keys
        ):
            raise ActionRejected("APPLICATION_NOT_ALLOWED")
        resolved = self._reader.resolve_application(application_key, self._owner)
        application = resolved.get("application") if type(resolved) is dict else None
        if (
            type(application) is not dict
            or application.get("asset", {}).get("applicationKey") != application_key
        ):
            raise ActionRejected("APPLICATION_BINDING_MISMATCH")
        recorded = _versions(resolved.get("recordedVersions"))
        admitted_versions = dict(admitted.recorded_versions)
        if any(admitted_versions.get(key) != version for key, version in recorded):
            raise ActionRejected("RESET_REQUIRED")
        version = resolved.get("resolvedVersion", {}).get("versionId")
        asset_id = resolved.get("resolvedVersion", {}).get("asset", {}).get("assetId")
        if (
            type(version) is not str
            or not version
            or type(asset_id) is not str
            or admitted_versions.get("APPLICATION:" + asset_id) != version
        ):
            raise ActionRejected("RESET_REQUIRED")
        return resolved

    def _application_contract(self, application_key: str) -> ApplicationContract:
        """Project one local-profile model contract from its bound release."""

        resolved = self._application(application_key)
        application = resolved["application"]
        description = application.get("description")
        template = application.get("surfaceTemplate")
        params_schema = (
            template.get("inputSchema") if type(template) is dict else None
        )
        if (
            type(description) is not str
            or type(params_schema) is not dict
        ):
            raise ActionRejected("APPLICATION_CONTRACT_INVALID")
        return {
            "appCode": application_key,
            "description": description,
            "usage": _APPLICATION_USAGE,
            "paramsSchema": json_copy(params_schema),
        }

    def query_skill_dependencies(
        self,
        application_codes: list[str],
    ) -> SkillDependencies:
        """Read current model inputs for explicitly bound Applications."""

        if (
            type(application_codes) is not list
            or not 1 <= len(application_codes) <= 20
            or any(
                type(code) is not str or not code or len(code) > 128
                for code in application_codes
            )
            or len(application_codes) != len(set(application_codes))
        ):
            raise ActionRejected("ARGUMENT_INVALID")
        admitted = self._require_admission()
        if "render_application" not in admitted.required_tools:
            raise ActionRejected("APPLICATION_NOT_ALLOWED")
        self.check_versions()
        applications = []
        for app_code in application_codes:
            if app_code not in admitted.application_keys:
                raise ActionRejected("APPLICATION_NOT_ALLOWED")
            contract = self._application_contract(app_code)
            if (
                type(contract) is not dict
                or set(contract) != {
                    "appCode", "description", "usage", "paramsSchema",
                }
                or contract.get("appCode") != app_code
                or type(contract.get("description")) is not str
                or contract.get("usage") != _APPLICATION_USAGE
                or type(contract.get("paramsSchema")) is not dict
            ):
                raise ActionRejected("APPLICATION_CONTRACT_INVALID")
            applications.append(json_copy(contract))
        self.check_versions()
        return {"applications": applications}

    def action_binding(self, application_key, action_name):
        """Resolve one server-owned Action policy for Chat Action ingress."""

        self.check_versions()
        resolved = self._application(application_key)
        policies = resolved["application"].get("actionPolicies")
        if type(policies) is not list:
            raise ActionRejected("UNSUPPORTED_APPLICATION_PROFILE")
        matches = [
            policy
            for policy in policies
            if type(policy) is dict and policy.get("actionName") == action_name
        ]
        if len(matches) != 1:
            raise ActionRejected("ACTION_NOT_ALLOWED")
        policy = matches[0]
        release = policy.get("abilityReleaseRef")
        if type(release) is not str:
            raise ActionRejected("INVALID_ABILITY_RELEASE")
        ability_key, separator, version = release.rpartition("@")
        if not separator or not ability_key or not version:
            raise ActionRejected("INVALID_ABILITY_RELEASE")
        ability, spec = self._ability(ability_key, model_call=False)
        application_versions = dict(_versions(resolved["recordedVersions"]))
        if (
            application_versions.get("ABILITY:" + ability.asset_id)
            != ability.version_id
            or ability.version_id != version
            or not spec.action_allowed
        ):
            raise ActionRejected("ACTION_NOT_ALLOWED")
        return resolved, json_copy(policy), ability, spec

    def _card_actions(self, application_key, resolved):
        actions = []
        bindings = []
        for policy in resolved["application"]["actionPolicies"]:
            _, admitted_policy, ability, _ = self.action_binding(
                application_key, policy["actionName"],
            )
            schema = json_copy(ability.definition["resolvedInputSchema"])
            for name, value in tuple(schema["properties"].items()):
                if value == {"type": "boolean", "enum": [True]}:
                    schema["properties"][name] = {"const": True}
            actions.append(
                {"actionName": admitted_policy["actionName"], "inputSchema": schema}
            )
            bindings.append(
                {
                    "actionName": admitted_policy["actionName"],
                    "abilityKey": ability.publication_metadata.ability_key,
                    "abilityVersion": ability.version_id,
                    "successPolicyRef": admitted_policy["successPolicyRef"],
                    "completeInteractionOnSuccess": admitted_policy[
                        "completeInteractionOnSuccess"
                    ],
                }
            )
        return actions, bindings

    def render_application(self, application_key, data, tool_call_id):
        """Prepare and persist one conversation card through the injected sink."""

        if type(tool_call_id) is not str or not tool_call_id:
            raise ActionRejected("TOOL_CALL_ID_REQUIRED")
        admitted = self._require_admission()
        self.check_versions()
        resolved = self._application(application_key)
        actions, bindings = self._card_actions(application_key, resolved)
        prepared = self._applications.prepare(
            application_key=application_key,
            resolved=resolved,
            data=data,
            actions=actions,
        )
        metadata = {
            "owner": {
                "userId": self._owner.user_id,
                "environment": self._owner.environment,
            },
            "conversationId": self._conversation_id,
            "controlRequestId": self._control_request_id,
            "toolCallId": tool_call_id,
            "skillKey": admitted.skill_key,
            "recordedVersions": [list(item) for item in admitted.recorded_versions],
            "applicationKey": application_key,
            "applicationVersion": prepared.application_version,
            "actionBindings": bindings,
        }
        with self._render_lock:
            if self._waiting_action is not None:
                raise ActionRejected("INTERACTION_REQUIRED")
            # This is the immediate version guard for the external persistence
            # boundary.  No model-selected identity or destination reaches it.
            self.check_versions()
            saved = json_copy(self._card_sink(prepared, json_copy(metadata)))
            if (
                type(saved) is not dict
                or type(saved.get("cardId")) is not str
                or not saved["cardId"]
            ):
                raise ActionRejected("INVALID_CARD_DESCRIPTOR")
            if prepared.interactive:
                self._waiting_action = saved
            display = prepared.display()
            self._render_observations[saved["cardId"]] = {
                "cardId": saved["cardId"],
                "applicationKey": application_key,
                "arguments": {
                    "surfaces": [{
                        "surfaceId": display["rootId"],
                        "data": display["data"],
                    }],
                },
            }
        return json_copy(saved)

    def render_observation(self, card_id: str) -> dict[str, Any]:
        """Return the turn-local rendered business state for Tool history."""

        with self._render_lock:
            observation = self._render_observations.get(card_id)
            if observation is None:
                raise ActionRejected("RENDER_OBSERVATION_NOT_AVAILABLE")
            return json_copy(observation)
