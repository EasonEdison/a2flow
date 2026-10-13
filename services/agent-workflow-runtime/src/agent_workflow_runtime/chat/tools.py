"""Conversation-scoped Tools with optional Skill execution assets.

Chat Ability and Application Tools are registered only when a trusted
``ChatAssets`` adapter is injected.  They never synthesize a Workflow run/node
or use a Workflow interrupt.  ``propose_workflow_run`` remains proposal-only.
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from skill_registry import use_skill
from skill_registry.use_skill import (
    InvocationScope as RegistryScope,
    TrustedContext as RegistryOwner,
    TrustedInvocationContext as RegistryContext,
)
from skillweave_contracts import CONTRACT_REVISION
from skillweave_contracts.models import (
    TrustedContext,
    TrustedInvocationContext,
    UseSkillRequest,
    parse_identifier,
    parse_skill_key,
)

from .events import WORKFLOW_CONFIRM
from ..mvp_tools import AbilityArgs
from ..models import ActionRejected, json_copy
from ..a2ui_generation import A2uiGenerator
from ..temporary_generation import InteractionGenerator

_EMITTER: ContextVar[Any] = ContextVar("a2flow_chat_emitter", default=None)


def _skill_key(value):
    return parse_skill_key(value, path="$")


SkillKey = Annotated[
    str, Field(strict=True, min_length=1, max_length=128),
    AfterValidator(_skill_key),
]


def _identifier(value):
    return parse_identifier(value, path="$")


Identifier = Annotated[
    str, Field(strict=True, min_length=1, max_length=128),
    AfterValidator(_identifier),
]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class UseSkillModelArgs(_Closed):
    skillKey: SkillKey


class UseSkillArgs(UseSkillModelArgs):
    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)
    runtime: ToolRuntime[TrustedInvocationContext]


class ProposeModelArgs(_Closed):
    workflowKey: Identifier
    title: Annotated[str, Field(strict=True, min_length=1, max_length=200)]


class ProposeArgs(ProposeModelArgs):
    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)
    runtime: ToolRuntime[TrustedInvocationContext]


def _unique_application_codes(values: list[str]) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError("a2uiApplicationCodeList must contain unique app codes")
    return values


ApplicationCodeList = Annotated[
    list[Identifier],
    Field(min_length=1, max_length=20),
    AfterValidator(_unique_application_codes),
]


class QuerySkillDependenciesModelArgs(_Closed):
    a2uiApplicationCodeList: ApplicationCodeList


class QuerySkillDependenciesArgs(QuerySkillDependenciesModelArgs):
    model_config = ConfigDict(
        extra="forbid", strict=True, arbitrary_types_allowed=True,
    )
    runtime: ToolRuntime[TrustedInvocationContext]


class RenderModelArgs(_Closed):
    appCode: Identifier
    params: dict[str, Any]


class RenderArgs(RenderModelArgs):
    model_config = ConfigDict(
        extra="forbid", strict=True, arbitrary_types_allowed=True,
    )
    runtime: ToolRuntime[TrustedInvocationContext]


class GenerateInteractionModelArgs(_Closed):
    intent: str = Field(min_length=1, max_length=4000)
    data: dict[str, Any]


class GenerateInteractionArgs(GenerateInteractionModelArgs):
    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)
    runtime: ToolRuntime[TrustedInvocationContext]


class GenerateModelArgs(RenderModelArgs):
    intent: str = Field(min_length=1, max_length=4000)


class GenerateArgs(GenerateModelArgs):
    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)
    runtime: ToolRuntime[TrustedInvocationContext]


def build_chat_tools(
    *,
    reader,
    trusted_context: TrustedContext,
    conversation_id: str,
    control_request_id: str,
    chat_assets=None,
    a2ui_generator: A2uiGenerator | None = None,
    interaction_generator: InteractionGenerator | None = None,
):
    """Build the legacy pair or the Skill-enabled four-tool tuple."""

    def _invocation():
        """Registry-scoped context for the contracts-level use_skill entry."""
        return RegistryContext(
            contract_revision=CONTRACT_REVISION,
            trusted_context=RegistryOwner(
                user_id=trusted_context.user_id,
                environment=trusted_context.environment,
            ),
            invocation_scope=RegistryScope(
                kind="CONVERSATION",
                conversation_id=conversation_id,
                run_id=None,
                node_id=None,
            ),
            control_request_id=control_request_id,
        )

    @tool(
        "use_skill",
        args_schema=UseSkillArgs,
        response_format="content_and_artifact",
    )
    def use_skill_tool(
        skillKey: str, runtime: ToolRuntime[TrustedInvocationContext]
    ):
        """Load this authorized Skill's instructions and resources for the conversation."""
        if chat_assets is None:
            mapping = use_skill(
                UseSkillRequest(skill_key=skillKey), _invocation(), reader
            ).to_mapping()
        else:
            chat_assets.validate_context(runtime.context)
            mapping = chat_assets.admit_skill(skillKey)
        return (
            json.dumps(mapping.get("content", {}), ensure_ascii=False, sort_keys=True),
            {
                "skillKey": skillKey,
                "versionId": mapping["artifact"]["resolvedVersion"]["versionId"],
            },
        )

    @tool(
        "propose_workflow_run",
        args_schema=ProposeArgs,
        response_format="content_and_artifact",
    )
    def propose_tool(
        workflowKey: str, title: str, runtime: ToolRuntime[TrustedInvocationContext]
    ):
        """Propose running a workflow. Emits a confirmation proposal only; never starts a run."""
        emitter = _EMITTER.get()
        if emitter is not None:
            emitter.emit(
                WORKFLOW_CONFIRM, {"workflowKey": workflowKey, "title": title}
            )
        return (
            json.dumps(
                {"proposed": True, "workflowKey": workflowKey, "title": title},
                ensure_ascii=False,
                sort_keys=True,
            ),
            {"workflowKey": workflowKey, "title": title},
        )

    if chat_assets is None:
        return use_skill_tool, propose_tool

    @tool(
        "execute_ability",
        args_schema=AbilityArgs,
        response_format="content_and_artifact",
    )
    def execute_ability_tool(
        abilityKey: str,
        arguments: dict[str, Any],
        runtime: ToolRuntime[TrustedInvocationContext],
    ):
        """Run one registered Ability bound by the active conversation Skill."""
        chat_assets.validate_context(runtime.context)
        value = chat_assets.execute_ability(abilityKey, arguments)
        return json.dumps(value["output"], ensure_ascii=False, sort_keys=True), {
            "abilityKey": value["abilityKey"],
            "versionId": value["versionId"],
        }

    @tool(
        "query_skill_dependencies",
        args_schema=QuerySkillDependenciesArgs,
        response_format="content_and_artifact",
    )
    def query_skill_dependencies_tool(
        a2uiApplicationCodeList: list[str],
        runtime: ToolRuntime[TrustedInvocationContext],
    ):
        """Query current input contracts for Skill-bound A2UI Applications before rendering."""
        chat_assets.validate_context(runtime.context)
        value = chat_assets.query_skill_dependencies(a2uiApplicationCodeList)
        return json.dumps(value, ensure_ascii=False, sort_keys=True), {
            "appCodes": list(a2uiApplicationCodeList),
        }

    @tool(
        "render_application",
        args_schema=RenderArgs,
        response_format="content_and_artifact",
    )
    def render_application_tool(
        appCode: str,
        params: dict[str, Any],
        runtime: ToolRuntime[TrustedInvocationContext],
    ):
        """Render one Skill-bound Application with params matching its queried contract."""
        chat_assets.validate_context(runtime.context)
        saved = chat_assets.render_application(
            appCode, params, runtime.tool_call_id,
        )
        return _rendered(saved, appCode)

    def _rendered(saved: dict[str, Any], appCode: str) -> tuple[str, dict[str, str]]:
        emitter = _EMITTER.get()
        if emitter is not None:
            emitter.emit("application_rendered", {"card": json_copy(saved)})
        rendered = chat_assets.render_observation(saved["cardId"])
        if (
            type(rendered) is not dict
            or rendered.get("applicationKey") != appCode
        ):
            raise ActionRejected("RENDER_OBSERVATION_MISMATCH")
        rendered = {
            "appCode": appCode,
            **{
                key: value
                for key, value in rendered.items()
                if key != "applicationKey"
            },
        }
        observation = {
            "renderedApplication": rendered,
            "applicationRole": "Conversation display or interaction.",
            "visibility": (
                "The Application was prepared and saved; this does not assert "
                "that the user viewed it."
            ),
        }
        return (
            json.dumps(
                observation,
                ensure_ascii=False,
                sort_keys=True,
            ),
            {
                "appCode": appCode,
                "cardId": saved["cardId"],
            },
        )

    @tool("generate_a2ui", args_schema=GenerateArgs, response_format="content_and_artifact")
    def generate_a2ui_tool(
        appCode: str, params: dict[str, Any], intent: str,
        runtime: ToolRuntime[TrustedInvocationContext],
    ) -> tuple[str, dict[str, str]]:
        """Design a new layout when the user asks for grouping, rearranging or redesign.

        appCode supplies this Skill's approved data/actions; params follow its queried
        contract. intent describes the desired layout. Does not publish or change assets.
        Users need not name this tool or AI. Ordinary business requests and edits to
        business content use the stable render_application, not layout generation.
        Do not retry or silently fall back after failure.
        """
        chat_assets.validate_context(runtime.context)
        if a2ui_generator is None:
            raise ActionRejected("A2UI_GENERATOR_UNAVAILABLE")
        saved = chat_assets.generate_application(
            appCode, params, intent, runtime.tool_call_id, a2ui_generator,
        )
        return _rendered(saved, appCode)

    @tool("generate_interaction", args_schema=GenerateInteractionArgs,
          response_format="content_and_artifact")
    def generate_interaction_tool(
        intent: str, data: dict[str, Any], runtime: ToolRuntime[TrustedInvocationContext],
    ) -> tuple[str, dict[str, str]]:
        """Generate a temporary display, comparison, selection or form for this task.

        No prebuilt Application or Skill is required. intent describes the interface
        and desired user input. data contains only facts/options supplied by the user
        or obtained through authorized tools; never invent business records. The
        platform validates and saves the UI. Submit returns user input to the task,
        not business success. Existing business operations still require Skill tools.
        Do not automatically retry, repair or substitute a template after failure.
        """
        chat_assets.validate_context(runtime.context)
        if interaction_generator is None:
            raise ActionRejected("A2UI_GENERATOR_UNAVAILABLE")
        saved = chat_assets.generate_interaction(
            data, intent, runtime.tool_call_id, interaction_generator,
        )
        return _rendered(saved, saved["display"]["applicationKey"])

    tools = (
        use_skill_tool,
        propose_tool,
        execute_ability_tool,
        query_skill_dependencies_tool,
        render_application_tool,
    )
    if a2ui_generator is not None:
        tools = (*tools, generate_a2ui_tool)
    return (*tools, generate_interaction_tool) if interaction_generator is not None else tools
