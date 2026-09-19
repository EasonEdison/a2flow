"""Conversation-scoped chat tools: use_skill + propose_workflow_run.

The workflow-run tools (execute_ability / render_application) are deliberately
absent from chat: they bind to a run/node and to LangGraph interrupts, neither
of which exists in an ordinary conversation. Chat skills reuse the same
contracts-level use_skill entry as workflow nodes, with a CONVERSATION
invocation scope. propose_workflow_run only emits a structured proposal event;
it never starts a run.
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
):
    """(use_skill, propose_workflow_run) bound to one conversation context."""

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
        result = use_skill(
            UseSkillRequest(skill_key=skillKey), _invocation(), reader
        )
        mapping = result.to_mapping()
        return (
            json.dumps(mapping.get("content", {}), ensure_ascii=False, sort_keys=True),
            {
                "skillKey": skillKey,
                "versionId": mapping.get("versionId"),
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

    return use_skill_tool, propose_tool
