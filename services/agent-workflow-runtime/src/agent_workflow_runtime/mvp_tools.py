"""Closed MVP08 Tools over trusted asset and Action ports."""

from hashlib import sha256
import json
from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from langgraph.types import interrupt
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from skillweave_contracts import TrustedInvocationContext
from skillweave_contracts.models import parse_identifier, parse_skill_key

from .models import ActionRejected, Interaction


def _identifier(value):
    return parse_identifier(value, path="$")


Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=128),
                       AfterValidator(_identifier)]


def _skill_key(value):
    return parse_skill_key(value, path="$")


SkillKey = Annotated[str, Field(strict=True, min_length=1, max_length=128),
                     AfterValidator(_skill_key)]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class UseSkillModelArgs(_Closed):
    skillKey: SkillKey


class UseSkillArgs(UseSkillModelArgs):
    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)
    runtime: ToolRuntime[TrustedInvocationContext]


class AbilityModelArgs(_Closed):
    abilityKey: Identifier
    arguments: dict[str, Any]


class AbilityArgs(AbilityModelArgs):
    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)
    runtime: ToolRuntime[TrustedInvocationContext]


class RenderModelArgs(_Closed):
    applicationKey: Identifier
    data: dict[str, Any]


class RenderArgs(RenderModelArgs):
    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)
    runtime: ToolRuntime[TrustedInvocationContext]


def validators():
    return {
        "use_skill": lambda value: UseSkillModelArgs.model_validate(value, strict=True),
        "execute_ability": lambda value: AbilityModelArgs.model_validate(value, strict=True),
        "render_application": lambda value: RenderModelArgs.model_validate(value, strict=True),
    }


def validate_choice_data(value):
    if type(value) is not dict or set(value) != {"prompt", "options"}:
        raise ActionRejected("INVALID_APPLICATION_DATA")
    if type(value["prompt"]) is not str or not 1 <= len(value["prompt"]) <= 2000:
        raise ActionRejected("INVALID_APPLICATION_DATA")
    options = value["options"]
    if type(options) is not list or not 2 <= len(options) <= 8:
        raise ActionRejected("INVALID_APPLICATION_DATA")
    for option in options:
        if (type(option) is not dict or set(option) != {"label", "value"}
                or type(option["label"]) is not str or not 1 <= len(option["label"]) <= 2000
                or type(option["value"]) is not str or not 1 <= len(option["value"]) <= 128):
            raise ActionRejected("INVALID_APPLICATION_DATA")
    if len({option["value"] for option in options}) != len(options):
        raise ActionRejected("INVALID_APPLICATION_DATA")
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _profile(application, application_validator):
    if application_validator(application) is not True:
        raise ActionRejected("UNSUPPORTED_APPLICATION_PROFILE")
    return application["surfaceTemplate"]



def build_tools(assets, action_service, application_validator,
                application_data_validator=None) -> tuple[BaseTool, BaseTool, BaseTool]:
    if not callable(application_validator):
        raise ValueError("APPLICATION_VALIDATOR_REQUIRED")
    if application_data_validator is not None and not callable(application_data_validator):
        raise ValueError("APPLICATION_DATA_VALIDATOR_INVALID")
    @tool("use_skill", args_schema=UseSkillArgs, response_format="content_and_artifact")
    def use_skill(skillKey: str, runtime: ToolRuntime[TrustedInvocationContext]):
        """Load the instruction and resources for this authorized Skill."""
        value = assets.skill(skillKey, runtime.context)
        return json.dumps(value["content"], ensure_ascii=False, sort_keys=True), {
            "contractRevision": value["contractRevision"], "artifact": value["artifact"]}

    @tool("execute_ability", args_schema=AbilityArgs, response_format="content_and_artifact")
    def execute_ability(abilityKey: str, arguments: dict[str, Any],
                        runtime: ToolRuntime[TrustedInvocationContext]):
        """Run one explicitly registered local Ability."""
        value = assets.execute_ability(abilityKey, arguments, runtime.context)
        return json.dumps(value["output"], ensure_ascii=False, sort_keys=True), {
            "abilityKey": value["abilityKey"], "versionId": value["versionId"]}

    @tool("render_application", args_schema=RenderArgs, response_format="content_and_artifact")
    def render_application(applicationKey: str, data: dict[str, Any],
                           runtime: ToolRuntime[TrustedInvocationContext]):
        """Persist one configured interactive or display-only node card."""
        context = assets.context(runtime.context)
        resolved = assets.application(applicationKey, context)
        application = resolved["application"]
        policy = application["renderPolicy"]
        interactive = policy == {
            "tool": "render_application", "interactionMode": "INTERACTIVE",
            "requiresPause": True,
        }
        display_only = policy == {
            "tool": "render_application", "interactionMode": "DISPLAY_ONLY",
            "requiresPause": False,
        }
        if not interactive and not display_only:
            raise ActionRejected("UNSUPPORTED_APPLICATION_PROFILE")
        template = _profile(application, application_validator)
        if application_data_validator is None:
            safe_data = validate_choice_data(data)
        elif application_data_validator(application, data) is True:
            safe_data = json.loads(json.dumps(data, ensure_ascii=False, allow_nan=False))
        else:
            raise ActionRejected("INVALID_APPLICATION_DATA")
        if not runtime.tool_call_id:
            raise ActionRejected("TOOL_CALL_ID_REQUIRED")
        scope = context.invocation_scope
        material = json.dumps([scope.run_id, scope.node_id, context.control_request_id,
                               applicationKey, resolved["resolvedVersion"]["versionId"],
                               runtime.tool_call_id], separators=(",", ":"), ensure_ascii=True)
        digest = sha256(material.encode()).hexdigest()
        interaction_id, card_id = "interaction:" + digest, "card:" + digest
        actions = assets.card_actions(applicationKey, context) if interactive else []
        if (interactive and len(actions) != 1) or (display_only and actions):
            raise ActionRejected("UNSUPPORTED_APPLICATION_PROFILE")
        card = {
            "cardId": card_id, "nodeId": scope.node_id, "interactionId": interaction_id,
            "applicationKey": applicationKey,
            "applicationVersion": resolved["resolvedVersion"]["versionId"],
            "protocolProfile": "a2flow.mvp08.v1",
            "componentCatalogRef": application["asset"]["componentCatalogRef"],
            "rootId": template["rootId"], "components": template["components"],
            "data": safe_data, "inputSchema": template["inputSchema"],
            "actions": actions,
            "state": "WAITING" if interactive else "READ_ONLY",
            "actionEligibility": "REVALIDATION_REQUIRED" if interactive else "NOT_OPERABLE",
        }
        saved = Interaction(
            context, interaction_id, applicationKey,
            resolved["resolvedVersion"]["versionId"],
            runtime.config["configurable"]["thread_id"],
            tuple(resolved["recordedVersions"]),
            display_json=json.dumps(card, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False),
            phase="WAITING" if interactive else "COMPLETED",
            node_waiting=interactive, resume_consumed=display_only,
        )
        action_service.register(saved)
        if display_only:
            return json.dumps({"displayed": True}, sort_keys=True), {
                "interactionId": interaction_id, "applicationKey": applicationKey,
                "versionId": saved.application_version,
            }
        action_name = actions[0]["actionName"]
        reference = {"kind": "A2UI_INTERACTION_REQUIRED", "runId": scope.run_id,
                     "nodeId": scope.node_id, "interactionId": interaction_id,
                     "applicationKey": applicationKey,
                     "versionId": saved.application_version, "actionName": action_name}
        while True:
            resumed = interrupt(reference)
            try:
                outcome = action_service.completion(saved.key, resumed,
                                                    context.trusted_context)
                break
            except ActionRejected as error:
                if error.code not in {"INVALID_RESUME_REFERENCE", "INTERACTION_NOT_COMPLETED"}:
                    raise
        result = json.loads(outcome.result_json)
        return json.dumps({"completed": True, "result": result}, ensure_ascii=False,
                          sort_keys=True), {"interactionId": interaction_id,
                                           "applicationKey": applicationKey,
                                           "versionId": saved.application_version}

    return use_skill, execute_ability, render_application
