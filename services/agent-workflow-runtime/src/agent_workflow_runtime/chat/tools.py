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
    ConversationInvocationScope,
    TrustedContext,
    TrustedInvocationContext,
    UseSkillRequest,
    parse_identifier,
    parse_skill_key,
)

from .events import WORKFLOW_CONFIRM
from ..mvp_tools import AbilityArgs, AbilityModelArgs, RenderArgs, RenderModelArgs
from ..models import json_copy

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


def build_chat_tools(
    *,
    reader,
    trusted_context: TrustedContext,
    conversation_id: str,
    control_request_id: str,
    chat_assets=None,
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
        "render_application",
        args_schema=RenderArgs,
        response_format="content_and_artifact",
    )
    def render_application_tool(
        applicationKey: str,
        data: dict[str, Any],
        runtime: ToolRuntime[TrustedInvocationContext],
    ):
        """Prepare and persist one Skill-bound conversation Application."""
        chat_assets.validate_context(runtime.context)
        saved = chat_assets.render_application(
            applicationKey, data, runtime.tool_call_id,
        )
        emitter = _EMITTER.get()
        if emitter is not None:
            emitter.emit("application_rendered", {"card": json_copy(saved)})
        rendered = chat_assets.render_observation(saved["cardId"])
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
                "applicationKey": applicationKey,
                "cardId": saved["cardId"],
            },
        )

    return (
        use_skill_tool,
        propose_tool,
        execute_ability_tool,
        render_application_tool,
    )
